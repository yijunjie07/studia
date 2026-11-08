"""智慧树问答区（qah5.zhihuishu.com）：取题、回答、提问。

问答区的接口（creditqa gateway）要求每个请求带 secretStr，它由页面脚本里的 yxyz(参数, dynStr)
算出，dynStr 跟着这次登录走。我们不去复刻签名：用无头 Chromium 带上已保存的登录 Cookie
打开问答区，在页面里调用它自己的签名函数再发请求。Python 这边只决定发什么、怎么理解结果。

出错时：被带去登录页抛 AuthenticationExpired，平台要人机验证抛 CaptchaRequired，
接口拒绝抛 ZHSApiError，页面一直没准备好抛 PlatformUnavailable。
"""
from __future__ import annotations

import json
import random
import re
import time
from urllib.parse import urlsplit

from core.log import Logger
from ai.client import AIResponseError
from core.auth import PlatformUnavailable
from zhs.api import AuthenticationExpired, CaptchaRequired, ZHSApiError

logger = Logger(__name__).get_log()

BOARD_PAGE = "https://qah5.zhihuishu.com/qa.html#/web/home/{course}?role=2&recruitId={recruit}"
BOARD_API = "https://creditqa-api.zhihuishu.com/creditqa/gateway/t/v1/web/qa/"
SIGN_IN_HOSTS = ("passport.zhihuishu.com", "login.zhihuishu.com")
READY_SECONDS = 25   # 页面拿到 dynStr 之前签不了名
SIGN_IN_SECONDS = 5  # 刚进站时会经过登录中心换票；一直停在那儿才算没登录
MAX_PAGES = 40

# 页面准备好了吗：签名函数在、Vue 的 baseData 里已经有这次登录的 dynStr。顺便带回自己是谁。
WHO_AM_I = """() => {
  const base = document.querySelector('#app')?.__vue__?.$store?.state?.baseData;
  const ready = typeof window.yxyz === 'function' && !!base && typeof base.dynStr === 'string' && base.dynStr !== '';
  return ready ? JSON.stringify({user: base.userId, role: base.roleId}) : '';
}"""
# 一次接口调用：用页面的签名函数签好，带 Cookie 发出去，原样带回 HTTP 状态和正文。
SIGNED_POST = """async ([url, params]) => {
  const base = document.querySelector('#app')?.__vue__?.$store?.state?.baseData;
  if (typeof window.yxyz !== 'function' || !base || !base.dynStr) return JSON.stringify({gone: true});
  const form = new URLSearchParams();
  form.set('dateFormate', String(Date.now()));
  form.set('secretStr', window.yxyz(params, base.dynStr));
  const response = await fetch(url, {method: 'POST', credentials: 'include', body: form});
  return JSON.stringify({status: response.status, text: await response.text()});
}"""


def browser_cookies(access_token):
    """ZHSApi 把登录 Cookie 存成 JSON 列表（access_token）；换成 Playwright add_cookies 要的样子。"""
    found = []
    for cookie in json.loads(access_token or "[]"):
        domain = cookie.get("domain") or ""
        if not domain.endswith("zhihuishu.com"):
            continue
        item = {"name": cookie["name"], "value": cookie["value"], "domain": domain,
                "path": cookie.get("path") or "/", "secure": cookie.get("secure", True) is not False}
        if cookie.get("expires"):
            item["expires"] = cookie["expires"]
        found.append(item)
    return found


class QaBridge:
    """一门课的问答区。with 进入时开浏览器、进站，退出时关掉；一次任务里所有请求共用这一页。"""

    def __init__(self, access_token, *, course_id, recruit_id, headless=True, timeout=30000):
        self.course_id, self.recruit_id = int(course_id), int(recruit_id)
        self.cookies = browser_cookies(access_token)
        self.headless, self.timeout = headless, timeout
        self.me = {}
        self._playwright = self._browser = self._page = None

    def __enter__(self):
        from playwright.sync_api import sync_playwright  # 只有问答区要浏览器，用到再导入

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            context = self._browser.new_context()
            context.add_cookies(self.cookies)
            self._page = context.new_page()
            self._open()
        except BaseException:
            # 进站失败时 with 不会调 __exit__。不关掉的话，Playwright 留在这个线程上的事件循环
            # 会让之后的 asyncio.run()（终端界面）直接报错。
            self.close()
            raise
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        for step in (getattr(self._browser, "close", None), getattr(self._playwright, "stop", None)):
            if step is None:
                continue
            try:
                step()
            except Exception:
                logger.debug("关闭问答区浏览器时出错", exc_info=True)
        self._browser = self._playwright = self._page = None

    def _open(self):
        """进问答区，等页面能签名。登录后头一回进站常被单点登录绕一圈，所以最多进三次。"""
        from playwright.sync_api import Error as PlaywrightError

        url = BOARD_PAGE.format(course=self.course_id, recruit=self.recruit_id)
        last = ""
        for _ in range(3):
            try:
                self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout)
            except PlaywrightError as exc:
                last = str(exc).splitlines()[0]
                continue
            on_sign_in = 0
            for _ in range(READY_SECONDS):
                if urlsplit(self._page.url).hostname in SIGN_IN_HOSTS:
                    on_sign_in += 1
                    if on_sign_in >= SIGN_IN_SECONDS:
                        raise AuthenticationExpired("智慧树登录已过期，请重新扫码")
                else:
                    on_sign_in = 0
                    try:
                        me = self._page.evaluate(WHO_AM_I)
                    except PlaywrightError:  # 正在跳转，执行环境被换掉了
                        me = ""
                    if me:
                        self.me = json.loads(me)
                        return
                self._page.wait_for_timeout(1000)
            last = "页面一直没拿到签名参数"
        logger.warning("问答区页面没有加载完成：%s", last or "未知原因")
        raise PlatformUnavailable("问答区页面没有加载完成，请稍后重试")

    def _post(self, path, params):
        """签名并调用一个接口，返回平台的 JSON。页面中途刷新、签名参数没了，就重新进站再发一次。"""
        from playwright.sync_api import Error as PlaywrightError

        for attempt in (1, 2):
            try:
                raw = json.loads(self._page.evaluate(SIGNED_POST, [BOARD_API + path, params]))
            except PlaywrightError as exc:
                if attempt == 2 or "context was destroyed" not in str(exc):
                    raise
                raw = {"gone": True}
            if not raw.get("gone"):
                break
            self._open()
        if raw["status"] >= 400:
            raise ZHSApiError(raw["status"], "问答区接口返回 HTTP %d" % raw["status"])
        try:
            return json.loads(raw["text"])
        except ValueError:
            raise ZHSApiError(raw["status"], "问答区接口返回的不是 JSON") from None

    @staticmethod
    def _accepted(result, what):
        """平台的回包：code 1010 是要人机验证，status 200 才算成功。"""
        if str(result.get("code")) == "1010":
            raise CaptchaRequired("问答区要求完成验证，请在页面上验证后重试")
        if str(result.get("status")) != "200":
            raise ZHSApiError(result.get("code") or result.get("status"), result.get("msg") or "%s失败" % what)
        return result.get("rt") or {}

    def questions(self, max_answers=1, limit=10, page_size=50):
        """按推荐顺序翻问答区，收集回答数不超过 max_answers 的提问，最多 limit 条。"""
        found, page = [], 0
        for _ in range(MAX_PAGES):
            result = self._post("getRecommendList", {"courseId": self.course_id, "recruitId": self.recruit_id,
                                                     "pageIndex": page, "pageSize": int(page_size)})
            rows = (result.get("rt") or {}).get("questionInfoList") or []
            for row in rows:
                if row.get("answerNum", 0) <= max_answers:
                    found.append({"id": row.get("questionId"), "content": row.get("content") or "",
                                  "answers": row.get("answerNum", 0), "asker": row.get("questionUserId"),
                                  "at": row.get("createTime"), "mine": row.get("questionUserId") == self.me.get("user")})
            following = (result.get("rt") or {}).get("pageIndex") or page + len(rows)
            if not rows or len(found) >= limit or following <= page:
                break
            page = following
        logger.info("问答区取到 %d 条（回答数≤%d）", min(len(found), limit), max_answers)
        return found[:limit]

    def publish(self, question_id, text):
        """回答一条提问，返回平台给的回答 id。"""
        result = self._post("saveAnswer", {"annexs": [], "qid": int(question_id), "source": self.me.get("role"),
                                           "aContent": text, "courseId": self.course_id, "recruitId": self.recruit_id,
                                           "validate": "", "saveSource": 1})
        return self._accepted(result, "发布回答").get("answerId")

    def ask(self, content, chapter_id=0):
        """在这门课的问答区发一条提问；chapter_id 为 0 是不挂章节的课程提问。返回提问 id。"""
        result = self._post("saveQuestion", {"annexs": [], "content": content, "courseId": self.course_id,
                                             "recruitId": self.recruit_id, "chapterId": int(chapter_id or 0),
                                             "sourceType": self.me.get("role"), "validate": "", "saveSource": 1})
        return self._accepted(result, "发布提问").get("questionId")


def _load_ids(path):
    if not path:
        return set()
    try:
        with open(path, encoding="utf-8") as handle:
            return set(json.load(handle))
    except (OSError, ValueError, TypeError):
        return set()


def _save_ids(path, ids):
    if path:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(sorted(ids), handle)


def answer_questions(qa, ai, *, max_answers=1, limit=10, interval=60, state_path=None,
                     should_stop=lambda: False, on_event=lambda kind, name, status="": None,
                     sleep=time.sleep, voice=None):
    """挑 limit 条值得回答的提问，让 AI 以同学的口吻写好逐条发出去。

    qa 只要有 questions() 和 publish()。answered 记在 state_path 里，同一条不会再答。
    voice 是这个账号固定的说话风格；不给就随机挑一个。单条失败只记一笔，接着答下一条；
    要验证或登录失效会停下整个任务。
    """
    if voice is None:
        voice = random.randrange(len(REPLY_VOICES))
    done = _load_ids(state_path)
    # 多翻一些再挑：刚发的提问里刷帖、水帖占大头，回答它们会跟着被删。
    pool = worth_answering(qa.questions(max_answers=max_answers, limit=limit * 30))
    picked = [item for item in pool if item["id"] not in done][:limit]
    stats = {"answered": 0, "skipped": 0, "failed": 0, "ids": []}
    on_event("begin", "问答区答题", "running")
    for number, item in enumerate(picked, 1):
        if should_stop():
            break
        label = item["content"][:20]
        try:
            reply = write_reply(ai, item["content"], seen=item.get("seen") or (), voice=voice)
            answer_id = qa.publish(item["id"], reply)
        except (CaptchaRequired, AuthenticationExpired):
            raise
        except Exception as exc:
            stats["failed"] += 1
            logger.warning("问答区第 %d 条没答上：%s", number, exc)
            on_event("result", label, "error")
            continue
        if not answer_id:
            stats["skipped"] += 1
            on_event("result", label, "skipped")
            continue
        stats["answered"] += 1
        stats["ids"].append(item["id"])
        done.add(item["id"])
        _save_ids(state_path, done)
        on_event("result", label, "success")
        if interval and number < len(picked):
            sleep(interval)
    on_event("done", "问答区答题", "done")
    return stats


# 回答写得像同学在论坛随手回的，不像教材：答题用的系统提示会写出「1. 2. 3.」分点、
# 「主要体现在以下几个方面」的套话；所有账号用同一套写法，一个帖子下面就全是一个味。
REPLY_RULES = (
    "你是同班同学，在课程问答区回这条提问。只写回复正文：一段话，不分点、不编号、不换行，"
    "不用冒号列清单；不要「首先」「其次」「最后」「综上所述」「总之」「主要体现在」「以下几个方面」"
    "「具有重要意义」这类套话；不要复述提问，不要称呼，不要以「答：」开头；"
    "说人话，像在论坛里随手回的，可以带点口语，可以有自己的看法。"
)
# 每个账号固定一种说话风格：(风格, 最少字数, 最多字数)。
REPLY_VOICES = (
    ("话少，一两句说完，不展开", 20, 50),
    ("爱举身边的例子，语气随和，偶尔用「其实」「比如」", 45, 100),
    ("说话直接，先亮出自己的判断，会说「我觉得」", 35, 80),
    ("比较认真，把一个原因讲透，但不分点", 60, 120),
    ("从自己的经历或见过的事说起，像在聊天", 40, 90),
)
# 每条回答随机换一个角度，同一个人答不同的帖子也不是一个模子。
REPLY_ANGLES = ("举一个生活里或身边的具体例子", "先说自己的看法，再给一个理由", "补充一个别人容易忽略的地方",
                "说说实际可以怎么做", "说一点和常见说法不太一样的看法", "联系课上讲过的内容说一句")
REPLY_CLICHES = ("首先", "其次", "最后", "综上", "总之", "总而言之", "主要体现在", "以下几个", "以下几点",
                 "具有重要意义", "至关重要", "不可或缺", "赋能", "助力", "此外", "与此同时", "值得注意的是",
                 "一方面", "另一方面")
LIST_MARK = re.compile(r"(?:^|[：:；;。，,\s])[（(]?(?:[1-9]|[一二三四五六七八九])[)）.、．]")


def reply_flaw(text, most):
    """像 AI 写的地方：分点编号、套话、太长；没有返回 None。"""
    if "\n" in text or LIST_MARK.search(text):
        return "不要分点编号，写成一段话"
    for cliche in REPLY_CLICHES:
        if cliche in text:
            return "别用「%s」这种套话" % cliche
    if len(text) > most * 1.5 + 20:
        return "太长了，压到 %d 个字以内" % most
    if len(text) < 10:
        return "太短了"
    return None


def write_reply(ai, question, *, seen=(), voice=0, rng=random):
    """以同学的口吻回一条：这个账号的说话风格，加上随机一个角度；seen 是这个帖子下已有的回答，
    让模型换个说法，别和它们一个味。不合格带着原因重写，最多三次。"""
    style, least, most = REPLY_VOICES[voice % len(REPLY_VOICES)]
    context = "%s\n这次的写法：%s；说话风格：%s；%d 到 %d 个字。" % (
        REPLY_RULES, rng.choice(REPLY_ANGLES), style, least, most)
    seen = [str(text).strip()[:80] for text in seen if str(text).strip()][:3]
    if seen:
        context += "\n下面已经有人这样回了，换个角度说，别用他们的说法和用词：\n" + "\n".join("- " + text for text in seen)
    redo = ""
    for _ in range(3):
        answer = ai.answer({"type": "问答题", "title": question, "context": context + redo}).get("answer")
        text = re.sub(r"^\s*(?:答案|回答|答)\s*[:：]\s*", "", " ".join(str(answer or "").split())).strip("\"'“”")
        flaw = reply_flaw(text, most)
        if flaw is None:
            return text
        logger.info("AI 的回答不像同学写的（%s），重写", flaw)
        redo = "\n上一次写的不合格：%s。重写。" % flaw
    raise ValueError("AI 的回答三次都像 AI 写的：%s" % flaw)


# 智慧树问答规则（wiki-wenda.zhihuishu.com「问答规则」）：有效提问每条 5 分、最多 10 条；
# 有效回答每条 2 分、最多 20 条；自己的提问下有 5 个有效回答再 1 分、最多 10 条；
# 合计再乘课程互动分占比。数据次日上午更新。封顶以后再发不加分，只多一分被判刷帖的风险。
QUESTION_CAP, ANSWER_CAP = 10, 20
# 每门课每天最多发这么多：规则说短时间内连发、同一句式连发会被删帖，第三方刷帖整学期禁言。
DAILY_QUESTIONS, DAILY_ANSWERS = 5, 10

# 让模型的「问答题」能力产出提问正文：它只需把问题写成答案，答卷格式不变。
QUESTION_RULES = (
    "要求：像刚学完这一节的学生在问答区发的提问，口语一点、具体一点；只输出提问本身，一句话，"
    "15 到 45 个字，以一个问号结尾，中间不要再出现问号；问原因、比较、影响或者怎么做，让同学能聊起来；"
    "不要堆术语、不要用英文缩写，不要写成「在……场景中，通常采用哪些……」这种论文题；"
    "不要问能直接搜到固定答案的事实（谁、哪一年、什么时候），"
    "不要写成名词解释（什么是、是什么意思、指什么）或是非题（是不是、对不对、有没有、能不能、是否、……吗）；"
    "不要用「请问」开头，不要称呼老师同学，不要「作为大学生」「我们」这类铺垫；"
    "不要带括号、下划线、序号、选项、答案、链接。"
)
QUESTION_PROMPT = ("这门课是「%s」。请围绕课程里「%s」这一节的内容，写一个发到课程问答区的提问，"
                   "这次可以用「%s」这种问法。\n" + QUESTION_RULES)
# 问法轮换：同一个人发的几条不是一个句式（规则：短时间内同一句式连续提问会被删）。
QUESTION_SHAPES = ("为什么……？", "……和……比，差别到底在哪？", "如果……，会怎么样？", "生活里哪些地方用得上……？",
                   "……最难做好的是哪一步？", "要是让你来……，你会怎么做？")
OWN_QUESTION_MOST = 50  # 我们自己发的提问：再长就像论文题了
QUESTION_AVOID = "\n问答区里已经有这些提问，不要重复，也不要换个说法问同一件事：\n%s"
QUESTION_REDO = "\n上一次写的「%s」不合格：%s。请重写。"
MIN_QUESTION, MAX_QUESTION = 8, 200
QA_PACE = (60, 180)        # 两条回答之间随机隔几秒，每次重抽：间隔一样像脚本；网页和终端共用
# 提问隔得更开：同一个人几分钟里连发几条，正是问答区清理刷帖的样子（实测满屏都是这种帖）。
ASK_PACE = (600, 1200)
REFERENCE_ANSWERS = 1      # 参考题目只取回答数为 0–1 的
MAX_REFERENCES = 8         # 塞进提示词的参考题目数量上限
MAX_REFERENCE_CHARS = 70   # 每条参考题目截到这个长度

# 规则和「什么是无效提问」「审核会删哪些帖」两篇里点名会被判无效或删掉的写法。
QUESTION_FLAWS = (
    (r"^请问", "不要用「请问」开头"),
    (r"^\s*(?:\d+|[一二三四五六七八九十]+)\s*[、.．)）]", "不要加序号"),
    (r"[()（）\[\]【】_＿]", "不要带括号或下划线"),
    (r"https?://|www\.|[Qq][Qq]|微信|公众号", "不要带链接或联系方式"),
    (r"(?:^|[^A-Za-z])[A-D][.．、]", "不要写成选择题"),
    (r"(?<!为)什么是|是什么意思|是什么[?？]$|指什么|指的是什么|的含义|的定义|名词解释", "名词解释类提问会被判无效"),
    (r"是不是|对不对|好不好|有没有|能不能|会不会|可不可以|是否|吗[?？]$", "是非题会被判无效"),
    (r"是谁|哪一年|什么时候|何时", "问人物、时间这类固定答案会被判无效"),
)
BURST = (3, 10 * 60 * 1000)   # 同一个人 10 分钟内发 3 条以上，多半是刷帖，迟早被删
OLDEST = 180 * 24 * 3600 * 1000  # 往期学期的提问，回答也算无效


def question_flaw(text):
    """按智慧树问答规则会被判无效或删掉的毛病；没有返回 None。"""
    text = str(text or "").strip()
    if sum(text.count(mark) for mark in "?？") != 1 or text[-1:] not in ("?", "？"):
        return "要以一个问号结尾，中间不能再有问号"
    for pattern, reason in QUESTION_FLAWS:
        if re.search(pattern, text):
            return reason
    if not MIN_QUESTION <= len(text) <= MAX_QUESTION:
        return "要 %d–%d 个字" % (MIN_QUESTION, MAX_QUESTION)
    return None


def own_question_flaw(text):
    """我们自己发的提问再严一点：短、少术语，读起来像学生问的。"""
    if len(text) > OWN_QUESTION_MOST:
        return "太长了，像论文题，缩到 45 个字以内"
    if len(re.findall(r"[A-Za-z][A-Za-z-]+", text)) >= 2:
        return "英文术语太多，换成大白话"
    if re.match(r"在.{2,24}(?:场景|架构|体系|环境|背景|过程|框架)(?:中|下|里)", text):
        return "「在……场景中」开头像论文题，换成学生会问的说法"
    return None


def worth_answering(items, now=None):
    """问答区里值得回答的提问。水帖、刷帖、自问自答和往期的提问会被删，回答它们的也一并作废。"""
    now = now or time.time() * 1000
    times = {}
    for item in items:
        if item.get("asker") is not None and item.get("at"):
            times.setdefault(item["asker"], []).append(item["at"])
    count, window = BURST
    bursty = {asker for asker, stamps in times.items()
              if any(len([t for t in stamps if 0 <= t - start <= window]) >= count for start in stamps)}
    return [item for item in items
            if not item.get("mine") and item.get("asker") not in bursty
            and not (item.get("at") and now - item["at"] > OLDEST)
            and question_flaw(item.get("content")) is None]


def qa_room(valid, posted_today, cap, daily):
    """还能发几条：离封顶还差多少、今天还剩多少，取小的。valid 是平台记的有效数，次日才算上今天发的。"""
    return max(0, min(cap - int(valid or 0) - posted_today, daily - posted_today))


# 模型偶尔还是会在提问前加称呼、客套或序号，发之前去掉。「请问…」「老师好」这类整句客套直接去；
# 「老师」「想问一下」这种词要后面紧跟标点才算称呼，免得「老师布置的作业」被削掉。
_PUNCT = "，,、：:！!。. "
_ALWAYS = re.compile(r"^(?:请问(?:一下|大家|各位|老师)?|(?:各位)?(?:老师|同学)们?(?:您)?好)")
_BEFORE_PUNCT = re.compile(r"^(?:想?请教(?:一下)?|想问(?:一下)?|(?:各位)?(?:老师|同学)们?)(?=[%s])" % re.escape(_PUNCT))


def _clean_question(text):
    """只留问题本身：去掉引号、开头序号、称呼和客套，压掉多余空白；结尾英文问号换成中文的。"""
    quotes = "\"'“”‘’` "
    text = re.sub(r"^\d[.、)）]\s*", "", " ".join(str(text or "").split()).strip(quotes)).strip(quotes)
    for _ in range(4):
        trimmed = _BEFORE_PUNCT.sub("", _ALWAYS.sub("", text.lstrip(_PUNCT))).lstrip(_PUNCT)
        if trimmed == text:
            break
        text = trimmed
    return text[:-1] + "？" if text.endswith("?") else text


def write_questions(ai, reference, count, *, course_name="", topics=(), on_progress=None):
    """让 AI 写 count 条新提问，每条落在课程的一个小节（topics）上，问法轮换。

    reference 是问答区里已有的提问，告诉模型别重复（规则：相似度 98% 以上算无效）。
    每条写出来按问答规则检查，不合格带着原因重写，最多三次；三次都不行就少一条。
    on_progress(第几条, 共几条) 在每条开始前调用。
    """
    known = [str(text).strip()[:MAX_REFERENCE_CHARS] for text in reference or () if str(text).strip()]
    known = known[:MAX_REFERENCES]
    avoid = QUESTION_AVOID % "\n".join("- " + text for text in known) if known else ""
    lessons = list(dict.fromkeys(str(topic) for topic in topics or () if str(topic).strip()))
    random.shuffle(lessons)
    total = max(1, int(count))
    written = []
    for number in range(1, total + 1):
        lesson = lessons[(number - 1) % len(lessons)] if lessons else "课程的核心内容"
        shape = QUESTION_SHAPES[(number - 1) % len(QUESTION_SHAPES)]
        prompt = QUESTION_PROMPT % (course_name or "这门课", lesson, shape) + avoid
        if on_progress is not None:
            on_progress(number, total)
        feedback = ""
        for _ in range(3):
            try:
                reply = ai.answer({"type": "问答题", "title": prompt + feedback}).get("answer")
            except AIResponseError:  # 推理模型偶尔只回了思考、正文是空的：再要一次，其他错误照常抛
                logger.warning("第 %d 条提问 AI 没给出正文，重试", number)
                continue
            text = _clean_question(reply)
            flaw = question_flaw(text)
            if flaw is None and (text in written or text in known):
                flaw = "和已有的提问重复"
            flaw = flaw or own_question_flaw(text)
            if flaw is None:
                written.append(text)
                break
            logger.warning("第 %d 条提问不合格（%s）：%s", number, flaw, text[:40])
            feedback = QUESTION_REDO % (text[:60], flaw)
    return written


def publish_questions(qa, texts, *, interval=60, should_stop=lambda: False,
                      on_event=lambda kind, name, status="": None, sleep=time.sleep):
    """把确认过的提问逐条发出去。qa 只要有 ask()。单条失败接着发下一条；要验证或登录失效就停。"""
    stats = {"published": 0, "failed": 0, "ids": []}
    on_event("begin", "问答区提问", "running")
    for number, text in enumerate(texts, 1):
        if should_stop():
            break
        label = text[:20]
        try:
            question_id = qa.ask(text)
        except (CaptchaRequired, AuthenticationExpired):
            raise
        except Exception as exc:
            question_id = None
            logger.warning("问答区第 %d 条提问没发出去：%s", number, exc)
        if not question_id:
            stats["failed"] += 1
            on_event("result", label, "error")
            continue
        stats["published"] += 1
        stats["ids"].append(question_id)
        on_event("result", label, "success")
        if interval and number < len(texts):
            sleep(interval)
    on_event("done", "问答区提问", "done")
    return stats
