"""智慧树问答区：浏览器里的签名调用、挑题作答、AI 出提问、发布，以及问答规则。不连真实平台。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai.client import AIResponseError
from core.auth import PlatformUnavailable
from zhs.api import AuthenticationExpired, CaptchaRequired, ZHSApiError
from zhs.qa import (ASK_PACE, MAX_REFERENCES, QaBridge, SIGNED_POST, WHO_AM_I, _clean_question,
                        answer_questions, browser_cookies, own_question_flaw, publish_questions, qa_room,
                        question_flaw, reply_flaw, worth_answering, write_questions, write_reply)

REPLY = "我觉得关键还是样本本身偏了，比如只问了常来店里的人，结论自然就往好的方向走。"
ASK = "大数据分析时，样本偏差会怎样误导企业的判断？"
QUESTIONS = ["第一章里的两个概念有什么区别？", "为什么这里要用比例而不是绝对值？"]
NOW = 1_800_000_000_000


class Page:
    """问答区页面的替身：WHO_AM_I 回答自己是谁，SIGNED_POST 按接口名交给 replies 回包。"""

    def __init__(self, replies=None, me=None, url="https://qah5.zhihuishu.com/qa.html"):
        self.replies, self.me, self.url = replies or {}, me if me is not None else {"user": 9, "role": 2}, url
        self.posts, self.visits = [], 0

    def goto(self, url, **_):
        self.visits += 1

    def wait_for_timeout(self, _):
        pass

    def evaluate(self, script, arg=None):
        if script == WHO_AM_I:
            return json.dumps(self.me) if self.me else ""
        assert script == SIGNED_POST
        url, params = arg
        path = url.rsplit("/", 1)[1]
        self.posts.append((path, params))
        reply = self.replies[path]
        reply = reply(params) if callable(reply) else reply
        return json.dumps({"status": 200, "text": json.dumps(reply)})


def bridge(page):
    qa = QaBridge("[]", course_id=7, recruit_id=8)
    qa._page = page
    qa.me = page.me or {}
    return qa


class BridgeTest(unittest.TestCase):
    def test_cookies_keep_only_zhihuishu(self):
        token = json.dumps([{"name": "a", "value": "1", "domain": ".zhihuishu.com", "expires": 99},
                            {"name": "b", "value": "2", "domain": ".example.com"},
                            {"name": "c", "value": "3", "domain": "passport.zhihuishu.com", "secure": False}])
        self.assertEqual(browser_cookies(token), [
            {"name": "a", "value": "1", "domain": ".zhihuishu.com", "path": "/", "secure": True, "expires": 99},
            {"name": "c", "value": "3", "domain": "passport.zhihuishu.com", "path": "/", "secure": False}])

    def test_opening_waits_for_the_page_and_learns_who_we_are(self):
        page = Page(me={"user": 5, "role": 2})
        qa = QaBridge("[]", course_id=7, recruit_id=8)
        qa._page = page
        qa._open()
        self.assertEqual(qa.me, {"user": 5, "role": 2})

    def test_staying_on_the_sign_in_page_means_the_login_is_gone(self):
        qa = QaBridge("[]", course_id=7, recruit_id=8)
        qa._page = Page(me={}, url="https://passport.zhihuishu.com/login?service=x")
        with self.assertRaises(AuthenticationExpired):
            qa._open()

    def test_a_page_that_never_gets_ready_is_unavailable(self):
        qa = QaBridge("[]", course_id=7, recruit_id=8)
        qa._page = page = Page(me={})
        with self.assertLogs("zhs.qa", "WARNING"), self.assertRaises(PlatformUnavailable):
            qa._open()
        self.assertEqual(page.visits, 3)

    def test_questions_page_through_and_keep_the_quiet_ones(self):
        pages = {0: {"rt": {"pageIndex": 2, "questionInfoList": [
            {"questionId": 1, "content": "甲？", "answerNum": 0, "questionUserId": 9, "createTime": 5},
            {"questionId": 2, "content": "乙？", "answerNum": 4, "questionUserId": 3, "createTime": 6}]}},
                 2: {"rt": {"pageIndex": 4, "questionInfoList": [
                     {"questionId": 3, "content": "丙？", "answerNum": 1, "questionUserId": 3, "createTime": 7}]}},
                 4: {"rt": {"questionInfoList": []}}}
        page = Page({"getRecommendList": lambda params: pages[params["pageIndex"]]})
        found = bridge(page).questions(max_answers=1, limit=10)
        self.assertEqual([(q["id"], q["mine"]) for q in found], [(1, True), (3, False)])
        self.assertEqual(found[1], {"id": 3, "content": "丙？", "answers": 1, "asker": 3, "at": 7, "mine": False})
        self.assertEqual([p["pageIndex"] for _, p in page.posts], [0, 2, 4])
        self.assertEqual(page.posts[0][1]["courseId"], 7)

    def test_questions_stop_once_there_are_enough(self):
        rows = [{"questionId": i, "content": "问？", "answerNum": 0} for i in range(5)]
        page = Page({"getRecommendList": {"rt": {"pageIndex": 5, "questionInfoList": rows}}})
        self.assertEqual(len(bridge(page).questions(max_answers=0, limit=3)), 3)
        self.assertEqual(len(page.posts), 1)

    def test_publish_and_ask_send_the_course_and_role(self):
        page = Page({"saveAnswer": {"status": "200", "rt": {"answerId": 11}},
                     "saveQuestion": {"status": "200", "rt": {"questionId": 12}}})
        qa = bridge(page)
        self.assertEqual(qa.publish("5", REPLY), 11)
        self.assertEqual(qa.ask(ASK), 12)
        answer, question = page.posts[0][1], page.posts[1][1]
        self.assertEqual((answer["qid"], answer["aContent"], answer["source"], answer["recruitId"]), (5, REPLY, 2, 8))
        self.assertEqual((question["content"], question["chapterId"], question["sourceType"]), (ASK, 0, 2))

    def test_refusals(self):
        page = Page({"saveAnswer": {"code": "1010"}, "saveQuestion": {"status": "500", "msg": "内容违规"}})
        qa = bridge(page)
        with self.assertRaises(CaptchaRequired):
            qa.publish(1, REPLY)
        with self.assertRaisesRegex(ZHSApiError, "内容违规"):
            qa.ask(ASK)

    def test_a_reloaded_page_is_opened_again_before_the_call(self):
        page = Page({"saveAnswer": {"status": "200", "rt": {"answerId": 1}}})
        answers = iter([json.dumps({"gone": True})])
        real = page.evaluate
        page.evaluate = lambda script, arg=None: next(answers) if script == SIGNED_POST and arg and not page.visits \
            else real(script, arg)
        self.assertEqual(bridge(page).publish(1, REPLY), 1)
        self.assertEqual(page.visits, 1)

    def test_a_failed_start_still_stops_playwright(self):
        playwright = Mock()
        playwright.chromium.launch.side_effect = RuntimeError("no chromium")
        with patch("playwright.sync_api.sync_playwright", return_value=Mock(start=Mock(return_value=playwright))):
            with self.assertRaises(RuntimeError):
                QaBridge("[]", course_id=7, recruit_id=8).__enter__()
        playwright.stop.assert_called_once()


class Board:
    """问答区替身：questions 按顺序给，publish/ask 记下发了什么。"""

    def __init__(self, items=(), fail=(), captcha=None, no_id=()):
        self.items, self.fail, self.captcha, self.no_id = list(items), set(fail), captcha, set(no_id)
        self.published, self.asked = [], []

    def questions(self, max_answers=1, limit=10):
        return self.items[:limit]

    def publish(self, question_id, text):
        if question_id == self.captcha:
            raise CaptchaRequired("要验证")
        if question_id in self.fail:
            raise ZHSApiError(500, "发不出去")
        self.published.append((question_id, text))
        return None if question_id in self.no_id else question_id * 10

    def ask(self, text):
        if text == self.captcha:
            raise CaptchaRequired("要验证")
        if text in self.fail:
            raise ZHSApiError(500, "发不出去")
        self.asked.append(text)
        return None if text in self.no_id else len(self.asked)


class Ai:
    def __init__(self, *answers):
        self.answers, self.prompts = list(answers) or [REPLY], []

    def answer(self, question):
        self.prompts.append(question)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return {"answer": answer}


def thread(qid, text=ASK, asker=None, at=NOW - 1000):
    return {"id": qid, "content": text, "answers": 0, "asker": asker if asker is not None else qid, "at": at}


class AnswerQuestionsTest(unittest.TestCase):
    def run_board(self, board, **kwargs):
        with patch("time.time", return_value=NOW / 1000):
            return answer_questions(board, Ai(), interval=0, voice=0, **kwargs)

    def test_answers_up_to_the_limit(self):
        board = Board([thread(i) for i in range(1, 6)])
        stats = self.run_board(board, limit=3)
        self.assertEqual((stats["answered"], stats["ids"]), (3, [1, 2, 3]))
        self.assertEqual(board.published[0], (1, REPLY))

    def test_floods_our_own_and_old_threads_are_passed_over(self):
        flood = [thread(10 + i, asker=99, at=NOW - i * 1000) for i in range(3)]
        board = Board(flood + [dict(thread(2), mine=True), thread(3, at=NOW - 200 * 86400 * 1000), thread(4)])
        self.assertEqual(self.run_board(board, limit=5)["ids"], [4])

    def test_one_failure_does_not_stop_the_rest(self):
        board = Board([thread(1), thread(2), thread(3)], fail={2}, no_id={3})
        with self.assertLogs("zhs.qa", "WARNING"):
            stats = self.run_board(board, limit=3)
        self.assertEqual((stats["answered"], stats["failed"], stats["skipped"]), (1, 1, 1))

    def test_a_captcha_or_lost_login_stops_the_job(self):
        with self.assertRaises(CaptchaRequired):
            self.run_board(Board([thread(1), thread(2)], captcha=2), limit=2)
        board = Board([thread(1)])
        board.publish = Mock(side_effect=AuthenticationExpired("过期"))
        with self.assertRaises(AuthenticationExpired):
            self.run_board(board, limit=1)

    def test_answered_threads_are_remembered(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "answered.json")
            self.run_board(Board([thread(1), thread(2)]), limit=1, state_path=path)
            self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8")), [1])
            board = Board([thread(1), thread(2)])
            self.run_board(board, limit=1, state_path=path)
            self.assertEqual(board.published[0][0], 2)

    def test_events_and_pauses(self):
        events, pauses = [], []
        with patch("time.time", return_value=NOW / 1000):
            answer_questions(Board([thread(1), thread(2)]), Ai(), limit=2, interval=5, voice=0,
                             on_event=lambda kind, name, status="": events.append((kind, status)), sleep=pauses.append)
        self.assertEqual(events, [("begin", "running"), ("result", "success"), ("result", "success"), ("done", "done")])
        self.assertEqual(pauses, [5])

    def test_stop_is_checked_before_each_one(self):
        board = Board([thread(1), thread(2)])
        with patch("time.time", return_value=NOW / 1000):
            answer_questions(board, Ai(), limit=2, interval=0, voice=0, should_stop=lambda: bool(board.published))
        self.assertEqual(len(board.published), 1)


class PublishQuestionsTest(unittest.TestCase):
    def test_publishes_each_and_pauses_between(self):
        board, pauses = Board(), []
        stats = publish_questions(board, QUESTIONS, interval=ASK_PACE[0], sleep=pauses.append)
        self.assertEqual((stats["published"], stats["ids"]), (2, [1, 2]))
        self.assertEqual(pauses, [ASK_PACE[0]])

    def test_failures_are_counted_and_skipped(self):
        board = Board(fail={QUESTIONS[0]}, no_id={QUESTIONS[1]})
        with self.assertLogs("zhs.qa", "WARNING"):
            stats = publish_questions(board, QUESTIONS, interval=0)
        self.assertEqual((stats["published"], stats["failed"]), (0, 2))

    def test_a_captcha_stops_it(self):
        board = Board(captcha=QUESTIONS[1])
        with self.assertRaises(CaptchaRequired):
            publish_questions(board, QUESTIONS, interval=0)
        self.assertEqual(board.asked, QUESTIONS[:1])


class CleanQuestionTest(unittest.TestCase):
    def test_greetings_numbers_and_quotes_go(self):
        self.assertEqual(_clean_question(' 1. "老师好，请问为什么天是蓝的?" '), "为什么天是蓝的？")
        self.assertEqual(_clean_question("同学们，想问一下，这个模型最难调的是哪一步？"), "这个模型最难调的是哪一步？")
        self.assertEqual(_clean_question("请问大家  数据和   信息有什么不同？"), "数据和 信息有什么不同？")

    def test_a_word_that_belongs_to_the_question_stays(self):
        self.assertEqual(_clean_question("老师布置的案例为什么都选制造业？"), "老师布置的案例为什么都选制造业？")
        self.assertEqual(_clean_question("想问题的时候先画图有用吗？"), "想问题的时候先画图有用吗？")


class WriteQuestionsTest(unittest.TestCase):
    def test_writes_as_many_as_asked(self):
        ai = Ai(QUESTIONS[0], QUESTIONS[1])
        self.assertEqual(write_questions(ai, [], 2), QUESTIONS)

    def test_a_flawed_or_repeated_one_is_rewritten_with_the_reason(self):
        ai = Ai("请问云计算好吗？", QUESTIONS[0], QUESTIONS[0], QUESTIONS[1])
        with self.assertLogs("zhs.qa", "WARNING"):
            self.assertEqual(write_questions(ai, [], 2), QUESTIONS)
        self.assertIn("请问", ai.prompts[1]["title"])
        self.assertIn("重复", ai.prompts[3]["title"])

    def test_three_bad_tries_drop_that_one(self):
        with self.assertLogs("zhs.qa", "WARNING"):
            self.assertEqual(write_questions(Ai("云计算好吗？"), [], 1), [])

    def test_an_empty_reply_is_asked_again(self):
        ai = Ai(AIResponseError("只有思考"), ASK)
        with self.assertLogs("zhs.qa", "WARNING"):
            self.assertEqual(write_questions(ai, [], 1), [ASK])

    def test_existing_questions_are_listed_to_avoid_and_capped(self):
        reference = ["已有提问%d为什么这样？" % i for i in range(MAX_REFERENCES + 3)]
        ai = Ai(ASK)
        write_questions(ai, reference, 1)
        prompt = ai.prompts[0]["title"]
        self.assertIn(reference[0], prompt)
        self.assertNotIn(reference[-1], prompt)
        with self.assertLogs("zhs.qa", "WARNING"):
            self.assertEqual(write_questions(Ai(reference[0]), reference, 1), [])

    def test_each_question_takes_a_lesson_and_reports_progress(self):
        ai, seen = Ai(QUESTIONS[0], QUESTIONS[1]), []
        write_questions(ai, [], 2, course_name="通信基础", topics=["调制", "复用", "调制"],
                        on_progress=lambda i, n: seen.append((i, n)))
        prompts = [p["title"] for p in ai.prompts]
        self.assertEqual(seen, [(1, 2), (2, 2)])
        self.assertTrue(all("通信基础" in p for p in prompts))
        self.assertEqual({"调制", "复用"}, {next(t for t in ("调制", "复用") if "「%s」" % t in p) for p in prompts})
        ai = Ai(ASK)
        write_questions(ai, [], 1)
        self.assertIn("课程的核心内容", ai.prompts[0]["title"])


class ReplyTest(unittest.TestCase):
    def test_listed_or_stock_answers_are_rewritten(self):
        ai = Ai("首先，样本有偏差。其次，结论会失真。", "1. 样本偏 2. 结论偏", REPLY)
        with self.assertLogs("zhs.qa", "INFO"):
            self.assertEqual(write_reply(ai, ASK, voice=1), REPLY)
        self.assertIn("首先", ai.prompts[1]["context"])

    def test_three_bad_tries_give_up(self):
        with self.assertLogs("zhs.qa", "INFO"), self.assertRaises(ValueError):
            write_reply(Ai("总之很重要。" * 3), ASK, voice=1)

    def test_answers_already_there_are_named_to_steer_clear_of(self):
        ai = Ai(REPLY)
        write_reply(ai, ASK, seen=["别人已经说过的话"], voice=2)
        self.assertIn("别人已经说过的话", ai.prompts[0]["context"])

    def test_flaws(self):
        self.assertIsNone(reply_flaw(REPLY, 100))
        self.assertIsNotNone(reply_flaw("第一行\n第二行", 100))
        self.assertIsNotNone(reply_flaw("综上，" + REPLY, 100))
        self.assertIsNotNone(reply_flaw("短", 100))
        self.assertIsNotNone(reply_flaw(REPLY * 5, 50))


class RulesTest(unittest.TestCase):
    def test_question_flaws_the_board_names(self):
        self.assertIsNone(question_flaw(ASK))
        for text in ("请问大数据分析会怎样误导企业判断？", "物联网安全为什么难做？？", "云计算好吗？",
                     "什么是物联网的感知层？", "人工智能会不会取代程序员？", "5G 是哪一年开始商用的呢？",
                     "大数据（数据集）会怎样影响企业决策？", "大数据怎样影响决策"):
            self.assertIsNotNone(question_flaw(text), text)

    def test_our_own_questions_stay_short_and_plain(self):
        self.assertIsNone(own_question_flaw(ASK))
        self.assertIsNotNone(own_question_flaw("为什么" * 20 + "？"))
        self.assertIsNotNone(own_question_flaw("Edge Computing 和 Cloud 有什么区别？"))
        self.assertIsNotNone(own_question_flaw("在工业互联网场景中为什么要做边缘计算？"))

    def test_threads_worth_answering(self):
        flood = [thread(i, asker=7, at=NOW - i * 60_000) for i in range(3)]
        kept = worth_answering(flood + [thread(5), dict(thread(6), mine=True), thread(8, text="随便")], now=NOW)
        self.assertEqual([q["id"] for q in kept], [5])

    def test_room_is_the_smaller_of_cap_and_daily_limit(self):
        self.assertEqual(qa_room(0, 0, 20, 10), 10)
        self.assertEqual(qa_room(15, 1, 20, 10), 4)
        self.assertEqual(qa_room(25, 0, 20, 10), 0)
        self.assertEqual(qa_room(None, 3, 20, 10), 7)


if __name__ == "__main__":
    unittest.main()
