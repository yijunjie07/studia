"""Bounded, ordered AI generation; only the caller touches paper state."""
from concurrent.futures import CancelledError, FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
import threading
import time

from ai.client import AIClient, AIError, AIServiceError
from ai.questions import model_question, prepare_question


def prepared_questions(raw_questions):
    """Prepare identities before dispatch, retaining invalid rows in paper order."""
    questions, identities = [], set()
    for number, raw in enumerate(raw_questions):
        children = raw.get('questionSubList') if isinstance(raw, dict) else None
        if children is not None and not isinstance(children, list):
            raise ValueError('子题结构未知')
        work = [(child, raw, i) for i, child in enumerate(children)] if children else [(raw, None, None)]
        for value, parent, child_number in work:
            try:
                q = prepare_question(value, number, parent, child_number)
                identity = (q['paper_id'], q['paper_sub_id'])
                if identity in identities:
                    raise ValueError('试卷包含重复试题 ID')
                identities.add(identity)
                questions.append(q)
            except (ValueError, TypeError):
                questions.append(None)
    return questions


class ParallelAnswers:
    """Keep at most one window outstanding, including unconsumed results.

    A new window starts only after the coordinator has validated and handled the
    previous one. This also prevents background dispatch during manual input.
    Each generation owns its session; retries share a cancellable service cooldown.
    """
    def __init__(self, ai, questions, max_workers, clock, allow_manual=False):
        self.config = replace(ai.config)
        self.questions = questions
        self.max_workers = max_workers
        self.clock = clock
        self.allow_manual = allow_manual
        self.fatal_error = None
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='ai-answer')
        self.stopped = threading.Event()
        self.cooldown_lock = threading.Lock()
        self.cooldown_until = 0.0
        self.results = {}
        self.futures = {}
        self.next_index = 0

    def _wait_for_service(self):
        while not self.stopped.is_set():
            with self.cooldown_lock:
                delay = self.cooldown_until - time.monotonic()
            if delay <= 0:
                return
            self.stopped.wait(delay)
        raise CancelledError()

    def _generate(self, q):
        client = AIClient(replace(self.config))
        try:
            for attempt in range(3):
                self._wait_for_service()
                if self.stopped.is_set():
                    raise CancelledError()
                try:
                    return client.answer(model_question(q))
                except AIError as exc:
                    if not exc.retryable:
                        raise
                    delay = max(attempt + 1, getattr(exc, 'retry_after', 0))
                    if isinstance(exc, AIServiceError):
                        with self.cooldown_lock:
                            self.cooldown_until = max(self.cooldown_until, time.monotonic() + delay)
                    if attempt == 2:
                        failure = type(exc)('单题重试 2 次后仍失败：' + str(exc))
                        if hasattr(exc, 'retry_after'):
                            failure.retry_after = exc.retry_after
                        raise failure from None
                    if not isinstance(exc, AIServiceError) and self.stopped.wait(delay):
                        raise CancelledError()
        finally:
            client.session.close()

    def answer(self, index):
        if index >= self.next_index:
            self.clock.check()
            stop = min(index + self.max_workers, len(self.questions))
            for position in range(index, stop):
                self.clock.check()
                if self.questions[position] is not None:
                    future = self.executor.submit(self._generate, self.questions[position])
                    self.futures[future] = position
            self.next_index = stop
            # Collect this window before returning ordered answers. Workers never
            # call progress, manual input, report writers or the platform API.
            while self.futures:
                self.clock.check()
                done, _ = wait(self.futures, timeout=0.05, return_when=FIRST_COMPLETED)
                for future in done:
                    position = self.futures.pop(future)
                    try:
                        self.results[position] = future.result()
                    except AIError as exc:
                        self.results[position] = exc
                        if isinstance(exc, AIServiceError) and not (exc.retryable and self.allow_manual):
                            self.fatal_error = exc
                            self.stopped.set()
                            for pending in self.futures:
                                pending.cancel()
                    except CancelledError:
                        self.results[position] = AIServiceError(
                            'AI 服务失败，本题已停止：' + str(self.fatal_error))
        result = self.results.pop(index)
        if isinstance(result, BaseException):
            raise result
        return result

    def close(self):
        self.stopped.set()
        for future in self.futures:
            future.cancel()
        # Active HTTP calls retain their existing connect/read timeouts. No new
        # retry starts after stop, and all owned sessions close before returning.
        self.executor.shutdown(wait=True, cancel_futures=True)
