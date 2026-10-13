# Manual Answer Completion Implementation Plan (Issue #12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Inline execution; one fresh review of the branch at the end.

**Goal:** When AI cannot finish a supported question, keep every valid answer, let the user answer the unresolved question from the terminal, checkpoint safely, resume the same draft later reusing validated answers, and require explicit `N/N` confirmation before submitting the whole paper.

**Architecture:** `ai/questions.py` gains two pure helpers: `question_fingerprint(q)` (identity/type/title/context/options/blank-count/child mapping) and `manual_answer_value(q, text)` (human line → typed answer validated by the existing `answer_record`). `AnswerRunner` gains a `manual_answer(question, reason)` callback and a `confirm_submit(paper, completed, total)` callback: it first reuses validated answers from a previous report of the *same task*, then runs AI for the rest, and only after all parallel work has finished prompts for unresolved prepared questions (so in-flight results are never lost and the prompt never races the live display). `TerminalUI` owns the prompt (suspend live + raw input), the `paused` status, and the submission confirmation. New reports store the source (`ai`/`manual`), the question fingerprint and `pending_manual`; submission records are always rebuilt from the fresh question structure via `answer_record`.

**Tech Stack:** Python 3.9, Rich, prompt_toolkit, unittest. No new dependencies.

**Spec:** Issue #12 + the approved feature brief in this session (2026-10-13). Supersedes only the "no manual input" part of `docs/superpowers/plans/2026-10-11-fully-ai-answering.md`.

## Global Constraints

- Reuse validated AI answers; regenerate only changed/missing questions.
- Human answers use existing `answer_record` validation; `B` stays a choice option, never "Back".
- Save/exit (explicit action, Esc, EOF, Ctrl-C) always checkpoints and never submits.
- Real service errors (auth / rate limit exhausted / global outage) keep the existing queue-stop semantics; structurally unsupported questions/media never become manually answerable.
- Always re-fetch the current paper; never trust a cached `record` for submission; re-check availability, submission status and the clock immediately before posting.
- Every paper involving manual completion (including resumed reports) asks `N/N 题已完成，交卷提交整份试卷？` with safe-cancel default before submitting.
- Pure-AI submissions keep today's semantics (no extra confirmation); report-only mode never submits.
- No new dependencies, no new subsystem/settings, existing report files are never mutated by tests.

## Review Focus

- Resuming a report whose task/account/exam changed must not attach old answers to new questions.
- A changed option list, title, blank count or parent context must regenerate that question only.
- Invalid human input must re-prompt without dropping already saved answers or submitting.
- Human waiting while the deadline expires / the browser submits the draft must stop before any POST.
- `max_workers > 1` must deliver every already-computed answer into the report before the manual prompt appears.

---

### Task 1: Question fingerprint and typed manual answer conversion

**Files:**
- Modify: `ai/questions.py`
- Test: `tests/test_manual_answer_input.py`

**Interfaces:**
- Produces: `question_fingerprint(q) -> dict`; `manual_answer_value(q, text) -> value` (raises `ValueError` with a Chinese reason).

- [ ] **Step 1: Write failing tests** for: fingerprint equal for the same question and different when title/options/context/type/blank count change; `manual_answer_value` returns `"B"` for a single choice (B is a legal choice), `["B","A"]` for multi `"ab"`, `True/False` for judgement `y/n`, a list of `blank_count` strings for `"a | b"`, the raw text for an essay; `ValueError` for empty input, unknown label, wrong blank count, multi-letter on a single choice.
- [ ] **Step 2: Run** `... -m unittest tests.test_manual_answer_input -v`; expect FAIL (`ImportError`).
- [ ] **Step 3: Implement** both helpers in `ai/questions.py`. `manual_answer_value` builds the typed value then calls the existing `answer_record(q, value)` as the final gate and returns the value.
- [ ] **Step 4: Run** the test; expect PASS. Read the output.
- [ ] **Step 5: Commit.**

### Task 2: Runner reuses validated answers from the same draft

**Files:**
- Modify: `ai/runner.py` (`previous_answer_value`, `legacy_row_matches`, `_run_paper` reuse phase, `write_report` source label)
- Test: `tests/test_manual_answer_completion.py` (new; runner cases)

**Interfaces:**
- Consumes: `question_fingerprint`, `answer_record`.
- Produces: report rows gain `source` (`"ai"`/`"manual"`) and `question_fingerprint`; a same-task previous report supplies answer values for unchanged questions.

Reuse a previous row only when the report identity matches (`exam_id`, `task_id`, and `category` when present), the question is prepared, the fingerprint is equal, or (legacy rows without a fingerprint) the row's `record.paperId` equals the fresh `paper_id`, the row has no child mapping, title and option label/text lists are identical, `record.optionSort` (when present) equals the fresh `raw_options`, and `answer_record(q, row["answer"])` succeeds. Every submission record is rebuilt with `answer_record`.

- [ ] **Step 1: Write failing tests**: 20-question paper, 19 previous valid rows + one null/no-record row of the same task → 1 AI call at most, 19 reused; a changed option list / title / blank count / parent context regenerates only that question; a different `task_id` reuses nothing; a row whose title differs is not reused; `source` is written (`ai`) and a row without `source` for a legacy report is not labelled `manual`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the reuse phase before the AI loop; skip reused positions in both serial and parallel paths; store `source`/`question_fingerprint`; print `人工答案`/`AI 答案`/`待补答` in the markdown.
- [ ] **Step 4: Run**; expect PASS plus the existing suite still green.
- [ ] **Step 5: Commit.**

### Task 3: Manual completion phase, pause/resume and submission confirmation

**Files:**
- Modify: `ai/runner.py`
- Test: `tests/test_manual_answer_completion.py`

**Interfaces:**
- Consumes: `manual_answer_value` (via the injected callback's view), `answer_record`.
- Produces: `AnswerRunner(..., manual_answer=None, confirm_submit=None)`; status `paused` with `pending_manual` rows; confirmation before POST when manual completion was involved.

- [ ] **Step 1: Write failing tests**: an unresolved supported question calls `manual_answer` once with the prepared question and a non-empty reason, then submits `N/N` records exactly once after `confirm_submit` returns True; `confirm_submit` False → `preview`, no POST, answers saved; declining then resuming (same task) posts once with 0 AI calls; `manual_answer` returning None → `paused`, `pending_manual` on disk, no POST; a service error still returns `ai_error` and never prompts; an unsupported (media) question is never prompted and blocks submission; `max_workers=2` keeps every AI answer in the report before the prompt; a deadline raised while prompting gives `error` with no POST; a pure-AI run never calls confirm.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the manual phase after the AI loop (checkpoint `paused` before calling the callback, clear `pending_manual` after a valid answer, `EOFError`/`KeyboardInterrupt` mean save-and-exit), and the confirm-before-submit branch.
- [ ] **Step 4: Run**; expect PASS.
- [ ] **Step 5: Commit.**

### Task 4: Terminal UI prompt, confirmation and `paused` status

**Files:**
- Modify: `ui.py` (labels, `prompt_region`, `manual_answer`, `confirm_submit`), `app.py` (`execute_ai` wiring)
- Test: `tests/test_manual_answer_ui.py`

**Interfaces:**
- Consumes: `manual_answer_value`.
- Produces: `TerminalUI.manual_answer(question, reason) -> value|None`; `TerminalUI.confirm_submit(paper, completed, total) -> bool`; `paused` label `待补答`.

- [ ] **Step 1: Write failing tests**: the prompt shows number/type/reason/context/title/options; `b` is parsed as choice B (not Back); an invalid line re-prompts and the valid one is returned; `:s` and EOF return None; the confirm prompt defaults to cancel and `Back`/`Cancelled` return False.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the prompt inside a `prompt_region()` context (stops the transient Live, suspends raw input, restarts after), and wire both callbacks in `app.execute_ai` via `getattr(view, ...)`.
- [ ] **Step 4: Run**; expect PASS.
- [ ] **Step 5: Commit.**

### Task 5: Reconcile older tests, docs and full suite

**Files:**
- Modify: `tests/test_fully_ai_answers.py` (approved behavior changes only), `README.md`, `docs/USAGE.md`
- Test: full suite

- [ ] **Step 1: Update only the conflicting tests**: same-task verifiable answers are now reused; a changed question regenerates alone; the runner now exposes `manual_answer` (but still no `min_confidence`).
- [ ] **Step 2: Run** `... -m unittest discover -s tests -v`; expect the whole suite green, output written to `/tmp/mooc-manual-green.log`.
- [ ] **Step 3: Document** saving/resuming in `README.md` and `docs/USAGE.md`; run `git diff --check`.
- [ ] **Step 4: Commit** and write `/tmp/mooc-manual-implementation-report.md`.
