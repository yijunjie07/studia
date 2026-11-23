"""Hosted Studia: several people share one server, each with their own isolated data."""
from __future__ import annotations

import argparse
import base64
import collections
import datetime
import getpass
import hmac
import html
import json
import logging
import os
import re
import secrets
import signal
import smtplib
import ssl
import threading
import time
from dataclasses import asdict, replace
from email.message import EmailMessage
from email.utils import formataddr
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from Crypto.Cipher import AES

from core.log import Logger
from mooc.oauth_login import SSO_AUTH_URL, SSO_SOURCE
from zhs.memory import DatabaseAnswerMemory
from ai.memory import MoocDatabaseAnswerMemory
from ai.client import AIClient, AIConfig, AIError
from ai.defaults import DEFAULT_PROVIDER_NAME, default_config
from core.settings import ANSWER_PACES, SettingsError, SettingsStore
from web.accounts import EMAIL, AccountError, Accounts, Sessions, Throttle
from web.server import MAX_JOBS, MAX_PENDING, NOT_HANDLED, PEERS_MARKER, HttpError, Reply, Studia, _EventLogHandler, drain, \
    keep_passports, key_hint, make_handler

COOKIE = "studia_session"
OAUTH_TTL = 600
KEY_ENV = "STUDIA_SECRET_KEY"
logger = Logger(__name__).get_log()  # into the daily log file the admin exports


def load_key(value):
    """32-byte AES key from the base64url text printed by --gen-key."""
    try:
        key = base64.urlsafe_b64decode((value or "").strip() + "==")
    except (ValueError, TypeError):
        key = b""
    if len(key) != 32:
        raise ValueError("%s 无效：请用 python StartWork.py --serve --gen-key 生成" % KEY_ENV)
    return key


class EncryptedSettingsStore(SettingsStore):
    """A user's settings (platform tokens, API keys) sealed with AES-256-GCM.

    The user id is the associated data, so a file copied into another user's
    directory fails authentication instead of handing over that account.
    """

    def __init__(self, directory, key, owner, *, default_model=None, site_health=None):
        super().__init__(directory)
        self.key, self.owner = key, owner.encode()
        self.default_model = default_model
        self.site_health = site_health
        self.plain_path = self.path
        self.path = self.directory / "settings.enc"

    def ai_profiles(self):
        # Resolve on every use, including jobs leaving the queue without a browser request.
        if self.default_model is not None:
            self.ensure_default_model(self.default_model())
        return super().ai_profiles()

    def ai_health(self, config):
        # The admin's test of the site default counts for everyone until the user tests it themselves.
        return super().ai_health(config) or (self.site_health(config) if self.site_health else {})

    def _read(self):
        if not self.path.exists():
            if not self.plain_path.exists():
                return {}
            return self._migrate()
        try:
            sealed = json.loads(self.path.read_text(encoding="utf-8"))
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=base64.b64decode(sealed["nonce"]))
            cipher.update(self.owner)
            plain = cipher.decrypt_and_verify(base64.b64decode(sealed["data"]), base64.b64decode(sealed["tag"]))
            data = json.loads(plain)
        except (OSError, ValueError, KeyError, TypeError):
            raise SettingsError("无法解密用户配置：密钥不对或文件已损坏（原文件未覆盖）") from None
        if not isinstance(data, dict):
            raise SettingsError("用户配置格式不正确（原文件未覆盖）")
        return data

    def _migrate(self):
        data = json.loads(self.plain_path.read_text(encoding="utf-8"))
        self._write(data)
        self.plain_path.unlink()
        return data

    def _write(self, data):
        data["version"] = 1
        cipher = AES.new(self.key, AES.MODE_GCM)
        cipher.update(self.owner)
        body, tag = cipher.encrypt_and_digest(json.dumps(data, ensure_ascii=False).encode("utf-8"))
        sealed = {"v": 1, "nonce": base64.b64encode(cipher.nonce).decode(), "tag": base64.b64encode(tag).decode(),
                  "data": base64.b64encode(body).decode()}
        temporary = self.directory / (".settings-%s.tmp" % secrets.token_hex(4))
        try:
            self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(sealed, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except OSError:
            raise SettingsError("无法保存用户配置，请检查数据目录权限") from None
        finally:
            if temporary.exists():
                temporary.unlink()


SMTP_PORTS = {"ssl": 465, "starttls": 587, "none": 25}
CODE_TTL = 10 * 60
# Who may sign up: open (a sign-up page at all), invite (with an unused invite code), email (with a code mailed
# to the address, which the account then keeps). The defaults are how the site worked before they could change.
REGISTRATION = {"open": True, "invite": True, "email": False}
# How fast the pages animate for everyone, as a multiple of the stylesheet's tempo (1.0); the admin nudges it in 0.1 steps.
UI_SPEED = (0.5, 2.0)


def smtp_open(config):
    """Connect and sign in to the site's mail server. Raises OSError or smtplib.SMTPException."""
    context = ssl.create_default_context()  # smtplib alone would not check the certificate on Python 3.9
    if config["security"] == "ssl":
        server = smtplib.SMTP_SSL(config["host"], config["port"], timeout=15, context=context)
    else:
        server = smtplib.SMTP(config["host"], config["port"], timeout=15)
    try:
        if config["security"] == "starttls":
            server.starttls(context=context)
        if config["username"]:
            server.login(config["username"], config["password"])
    except BaseException:
        server.close()
        raise
    return server


def mail_error(exc):
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "账号或密码（授权码）不正确"
    if isinstance(exc, smtplib.SMTPResponseException):
        return "%d %s" % (exc.smtp_code, exc.smtp_error.decode("utf-8", "replace") if isinstance(exc.smtp_error, bytes) else exc.smtp_error)
    return str(exc) or exc.__class__.__name__


MAIL_FONT = "font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;"
MAIL_MONO = "font-family:'SF Mono',Menlo,Consolas,'Courier New',monospace;"


def mail_page(preview, heading, intro, main, note):
    """Studia's mail look: the brand, one heading, one action, a quiet footnote. Tables and inline styles
    only: mail clients drop <style> blocks and most layout CSS. Arguments are HTML; escape what users typed."""
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f0;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{preview}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#f4f4f0;"><tr><td align="center" style="padding:36px 14px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;background:#ffffff;border:1px solid #e4e4df;border-radius:12px;">
<tr><td style="padding:28px 32px 0;">
  <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
    <td style="padding-right:10px;"><table role="presentation" cellpadding="0" cellspacing="2" border="0">
      <tr><td width="9" height="9" style="background:#212429;border-radius:2px;"></td><td width="9" height="9" style="background:#212429;border-radius:2px;"></td></tr>
      <tr><td width="9" height="9" style="background:#2d5fa6;border-radius:2px;"></td><td width="9" height="9" style="background:#d03b2e;border-radius:2px;"></td></tr></table></td>
    <td style="{MAIL_FONT}font-size:16px;font-weight:700;color:#212429;">Studia</td></tr></table></td></tr>
<tr><td style="padding:26px 32px 0;{MAIL_FONT}">
  <h1 style="margin:0;font-size:21px;line-height:1.4;font-weight:700;color:#212429;">{heading}</h1>
  <p style="margin:10px 0 0;font-size:14px;line-height:1.8;color:#55585c;">{intro}</p></td></tr>
<tr><td style="padding:24px 32px 28px;{MAIL_FONT}">{main}</td></tr>
<tr><td style="padding:18px 32px 26px;border-top:1px solid #eeeeea;{MAIL_FONT}font-size:12px;line-height:1.8;color:#8d9094;">{note}</td></tr>
</table>
<p style="margin:18px 0 0;{MAIL_FONT}font-size:12px;line-height:1.6;color:#a3a5a8;">这封邮件由 Studia 自动发送，请不要直接回复。</p>
</td></tr></table></body></html>"""


class Hub:
    """Accounts plus one Studia app per user, each rooted in data/users/<id>/."""

    def __init__(self, data_dir, public_url, *, key, trust_proxy=False):
        self.key = key
        self.data = Path(data_dir).expanduser()
        (self.data / "users").mkdir(mode=0o700, parents=True, exist_ok=True)
        self.data.chmod(0o700)  # mkdir(parents=True) leaves the root at the umask default
        self.accounts = Accounts(self.data)
        self.sessions = Sessions(self.accounts)
        self.site_store = EncryptedSettingsStore(self.data / "site", key, "site")
        # Answers the platform has judged, shared by every user: one user's graded paper
        # spares everyone else the AI call (and the wrong answer) next time.
        self.memory = DatabaseAnswerMemory(self.accounts.path)
        # MOOC answers are only shared within the same course offering and paper (ai.memory).
        self.mooc_memory = MoocDatabaseAnswerMemory(self.accounts.path)
        for legacy in sorted((self.data / "users").glob("*/zhs-answers.json")):
            try:
                count = self.memory.merge_file(legacy)
            except (OSError, ValueError, TypeError) as exc:
                logger.warning("合并 %s 失败，保留原文件：%s", legacy, exc)
                continue
            legacy.replace(legacy.with_name("zhs-answers.json.merged"))
            logger.info("已把 %s 的 %d 题并入共享答案记忆", legacy.parent.name, count)
        # Until an administrator exists, whoever reaches the site first could claim it; the
        # first-run page therefore also asks for this code, printed only in the server log.
        self.setup_code = None if self.accounts.has_admin() else "-".join(
            secrets.token_hex(2).upper() for _ in range(3))
        self.throttle = Throttle()
        # Mail costs the site's sender reputation: at most 5 an hour per person, per account and per address.
        self.mail_throttle = Throttle(limit=5, window=3600)
        # ponytail: binding codes live in memory, so a restart asks for a new one; a table if that ever matters.
        self.email_codes = {}
        self.signup_codes = {}  # address (lowercase) -> the code mailed for signing up with it
        self.public_url = public_url.rstrip("/")
        self.trust_proxy = trust_proxy
        # The program writes its daily log files to the working directory (/data in Docker).
        self.log_dir = Path.cwd()
        self.lock = threading.RLock()
        self.apps = {}
        self.pending_oauth = {}

    def app(self, uid):
        with self.lock:
            app = self.apps.get(uid)
            if app is None:
                directory = self.data / "users" / uid
                directory.mkdir(mode=0o700, parents=True, exist_ok=True)
                store = EncryptedSettingsStore(directory, self.key, uid, default_model=self.default_model,
                                               site_health=self.default_model_health)
                store.ensure_default_model(self.default_model())
                app = Studia(store, reports_dir=directory / "ai_results", memory=self.memory, mooc_memory=self.mooc_memory,
                             oauth_url=lambda pid, here=False, uid=uid: self.oauth_url(uid, pid, here),
                             job_limit=lambda uid=uid: self.job_limit(uid),
                             zhs_parallel=lambda: bool(self.accounts.setting("zhs_parallel_study", False)),
                             answer_pace=self.answer_pace,
                             peers=lambda course_id, recruit_id, uid=uid: self.peer_questions(uid, course_id, recruit_id))
                app.owner = (self.accounts.user(uid) or {}).get("username", uid)
                self.apps[uid] = app
            return app

    def peer_questions(self, uid, course_id, recruit_id):
        """Questions the other people on this site asked in the same Zhihuishu class, oldest first, each with how many
        of us have answered it ("ours"). Read from everyone's post records (Studia._record_post); the questions are
        public on the board anyway. Only records that name the class count: a question from another class is not on
        this person's board."""
        asked, ours, replies = [], collections.Counter(), collections.defaultdict(list)
        for path in sorted((self.data / "users").glob("*/zhs-qa-posts.json")):
            sharing = (path.parent / PEERS_MARKER).exists()  # only those who turned 站内互答 on offer their questions
            try:
                posts = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for post in posts if isinstance(posts, list) else []:
                if not isinstance(post, dict) or str(post.get("course")) != str(course_id) \
                        or str(post.get("recruit")) != str(recruit_id):
                    continue
                if post.get("kind") == "answer" and post.get("qid"):
                    ours[str(post["qid"])] += 1
                    replies[str(post["qid"])].append(post.get("text") or "")  # so the next one says it differently
                elif post.get("kind") == "ask" and post.get("id") and path.parent.name != uid and sharing:
                    asked.append({"id": post["id"], "text": post.get("question") or "", "at": post.get("at") or 0})
        return [dict(q, ours=ours[str(q["id"])], replies=replies[str(q["id"])][-3:]) for q in sorted(asked, key=lambda q: q["at"])]

    def resume(self):
        """After a restart, start again each person's jobs it interrupted (see Studia.resume)."""
        for path in sorted((self.data / "users").glob("*/jobs.json")):
            user = self.accounts.user(path.parent.name)
            if user and not user.get("disabled"):
                threading.Thread(target=self.app(user["id"]).resume, daemon=True,
                                 name="studia-resume-%s" % user["id"]).start()

    def audit(self, action, *, actor="", target="", ip="", ok=True):
        """Append-only record of sign-ins and admin actions; never passwords or tokens."""
        line = json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "action": action, "ok": ok,
                           "actor": actor, "target": target, "ip": ip}, ensure_ascii=False)
        path = self.data / "audit.log"
        with self.lock:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    # ------------------------------------------------------------ MOOC browser login

    def oauth_url(self, uid, pid, here=False):
        # here: the Studia page itself goes to the SSO (no tab of its own), so the callback has to bring it back.
        nonce = secrets.token_urlsafe(24)
        now = time.time()
        with self.lock:
            self.pending_oauth = {k: v for k, v in self.pending_oauth.items() if v[2] > now}
            self.pending_oauth[nonce] = (uid, pid, now + OAUTH_TTL, here)
        redirect = "%s/oauth/callback/%s" % (self.public_url, nonce)
        return SSO_AUTH_URL + "?" + urlencode({"mode": "simple", "source": SSO_SOURCE, "redirect": redirect})

    def oauth_callback(self, nonce, token, session_uid):
        # The SSO accepts any redirect, so only a fresh single-use nonce we issued
        # (and, when a Studia session is present, the same user) may bind a token.
        with self.lock:
            entry = self.pending_oauth.pop(nonce, None)
        home = self.public_url + "/"
        if entry is None or entry[2] < time.time():
            return False, "这个登录链接已失效，请回到 Studia 重新点击登录。", home
        uid, pid, _, here = entry
        back = "%s#/login/%s" % (home, pid)  # the login page picks the result up from there
        if session_uid is not None and session_uid != uid:
            return False, "当前浏览器登录的 Studia 账号和发起登录的账号不一致，请换回原账号重试。", home
        if not token:
            return False, "没有收到职教云的登录结果，请重试。", back
        threading.Thread(target=self.app(uid).finish_browser_login, args=(pid, token), daemon=True).start()
        if not here:  # a tab of its own: the Studia tab that opened it carries on, this one is not a second Studia
            return True, "职教云登录成功，正在读取课程。可以关闭这个页面，回到 Studia。", None
        return True, "职教云登录成功，正在返回 Studia…", back

    # ------------------------------------------------------------ admin helpers

    def default_model(self):
        saved = self.site_store.get("default_model")
        return AIConfig(**saved) if saved is not None else default_config()

    def default_model_health(self, config=None):
        config = config or self.default_model()
        health = self.site_store.get("default_model_health")
        if config is None or not isinstance(health, dict) or health.get("config") != SettingsStore.ai_fingerprint(config):
            return {}
        return health

    def _record_default_health(self, config, status, message=""):
        self.site_store.set("default_model_health", {
            "config": SettingsStore.ai_fingerprint(config), "status": status, "message": message,
            "checked_at": datetime.datetime.now().isoformat(timespec="seconds")})

    def _check_default(self, config):
        """Test a candidate default; returns it with the detected request format. Raises AIError."""
        client = AIClient(replace(config))
        try:
            client.check_connection()
        finally:
            client.session.close()
        return client.config

    def save_default_model(self, body):
        if body is None:  # back to the built-in default (or none, without STUDIA_DEFAULT_API_KEY)
            with self.lock:
                self.site_store.set("default_model", None)
                self.site_store.set("default_model_health", None)
            return
        fields = ("provider_name", "base_url", "model", "api_key")
        if not isinstance(body, dict) or any(k in body and not isinstance(body[k], str) for k in fields):
            raise HttpError(400, "默认模型配置格式不正确")
        previous = self.default_model()
        api_key = body.get("api_key", "").strip()
        if not api_key and previous is not None:
            # A blank key keeps the saved one, but never sends it to a different host.
            if urlsplit(body.get("base_url", "").strip()).hostname != urlsplit(previous.base_url).hostname:
                raise HttpError(400, "更换服务地址时请重新填写 API Key")
            api_key = previous.api_key
        try:
            config = AIConfig(base_url=body.get("base_url", ""), model=body.get("model", ""), api_key=api_key,
                              provider_name=body.get("provider_name", "").strip() or DEFAULT_PROVIDER_NAME)
        except ValueError as exc:
            raise HttpError(400, str(exc)) from None
        # Test before anyone depends on it, outside the hub lock: a slow provider must not stall other users.
        try:
            config = self._check_default(config)
        except AIError as exc:
            raise HttpError(400, "连接测试失败，没有保存：%s" % exc) from None
        with self.lock:
            # Users pick it up when they next list models or start AI work.
            self.site_store.set("default_model", asdict(config))
            self._record_default_health(config, "ok")

    def test_default_model(self):
        config = self.default_model()
        if config is None:
            raise HttpError(400, "还没有默认模型")
        try:
            detected = self._check_default(config)
        except AIError as exc:
            self._record_default_health(config, "error", str(exc))
            return {"health": "error", "message": str(exc)}
        with self.lock:
            if detected != config and self.site_store.get("default_model") is not None:
                self.site_store.set("default_model", asdict(detected))
            self._record_default_health(detected, "ok")
        return {"health": "ok", "message": "连接正常"}

    def registration(self):
        saved = self.accounts.setting("registration", {})
        return {k: saved[k] if isinstance(saved, dict) and isinstance(saved.get(k), bool) else v for k, v in REGISTRATION.items()}

    def save_registration(self, body):
        if not isinstance(body, dict) or any(k not in REGISTRATION or not isinstance(v, bool) for k, v in body.items()):
            raise HttpError(400, "注册设置格式不正确")
        rules = dict(self.registration(), **body)
        if rules["open"] and rules["email"] and self.smtp() is None:
            raise HttpError(400, "先配置邮件服务，才能要求注册时验证邮箱")
        self.accounts.set_setting("registration", rules)

    def site_settings(self):
        config, smtp = self.default_model(), self.smtp()
        health = self.default_model_health(config)
        return {"max_jobs": self.default_job_limit(),
                "registration": self.registration(),
                "zhs_parallel_study": bool(self.accounts.setting("zhs_parallel_study", False)),
                "answer_pace": self.answer_pace(),
                "ui_speed": self.ui_speed(),
                "smtp": smtp and dict({k: v for k, v in smtp.items() if k != "password"},
                                      password_hint="已保存" if smtp["password"] else ""),  # not even part of it
                "builtin_available": default_config() is not None,
                "default_model": config and dict(
                    provider_name=config.provider_name, base_url=config.base_url, model=config.model,
                    key_hint=key_hint(config.api_key), health=health.get("status", ""),
                    health_message=health.get("message", ""), checked_at=health.get("checked_at", ""),
                    source="site" if self.site_store.get("default_model") is not None else "builtin")}

    def ui_speed(self):
        speed = self.accounts.setting("ui_speed", 1.0)
        return speed if isinstance(speed, (int, float)) and UI_SPEED[0] <= speed <= UI_SPEED[1] else 1.0

    def answer_pace(self):
        """Zhihuishu answer pace for everyone on the site; only an admin changes it (stored like zhs_parallel_study)."""
        pace = self.accounts.setting("answer_pace", "steady")
        return pace if pace in ANSWER_PACES else "steady"

    def smtp(self):
        return self.site_store.get("smtp")

    def save_smtp(self, body):
        if body is None:
            rules = self.registration()
            if rules["open"] and rules["email"]:
                raise HttpError(400, "注册要求验证邮箱，先关掉它再清除邮件服务")
            self.site_store.set("smtp", None)
            return
        fields = ("host", "security", "username", "password", "sender", "sender_name")
        if not isinstance(body, dict) or any(k in body and not isinstance(body[k], str) for k in fields):
            raise HttpError(400, "邮件服务配置格式不正确")
        config = {k: body.get(k, "").strip() for k in fields}
        if not config["host"]:
            raise HttpError(400, "请填写 SMTP 服务器")
        if config["security"] not in SMTP_PORTS:
            raise HttpError(400, "加密方式只能是 SSL、STARTTLS 或不加密")
        try:
            config["port"] = int(body.get("port") or SMTP_PORTS[config["security"]])
        except (TypeError, ValueError):
            config["port"] = 0
        if not 0 < config["port"] < 65536:
            raise HttpError(400, "端口不正确")
        config["sender"] = config["sender"] or config["username"]
        if not EMAIL.fullmatch(config["sender"]):
            raise HttpError(400, "请填写正确的发件地址")
        previous = self.smtp()
        if not config["password"] and previous:
            # A blank password keeps the saved one, but never sends it to a different server.
            if config["host"].lower() != previous["host"].lower():
                raise HttpError(400, "更换服务器时请重新填写密码")
            config["password"] = previous["password"]
        try:  # sign in before anyone depends on it, outside the hub lock
            smtp_open(config).quit()
        except (OSError, smtplib.SMTPException) as exc:
            raise HttpError(400, "连接测试失败，没有保存：%s" % mail_error(exc)) from None
        self.site_store.set("smtp", config)

    def mail(self, to, subject, text, page=None):
        config = self.smtp()
        if config is None:
            raise HttpError(400, "管理员还没有配置邮件服务")
        message = EmailMessage()
        message["From"] = formataddr((config["sender_name"] or "Studia", config["sender"]))
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text)  # what a client that shows no HTML reads
        if page:
            message.add_alternative(page, subtype="html")
        try:
            server = smtp_open(config)
            try:
                server.send_message(message)
            finally:
                server.close()
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning("发送邮件失败：%s", mail_error(exc))
            raise HttpError(400, "邮件发送失败：%s" % mail_error(exc)) from None

    def send_email_code(self, uid, email):
        email = str(email or "").strip()
        if len(email) > 254 or not EMAIL.fullmatch(email):
            raise HttpError(400, "邮箱格式不正确")
        if self.accounts.email_taken(email, uid):
            raise HttpError(400, "这个邮箱已经绑定了其他账号")
        with self.lock:
            pending = self.email_codes.get(uid)
            wait = pending and 60 - (time.time() - pending["sent"])
            if wait and wait > 0:
                raise HttpError(429, "验证码刚发过，请 %d 秒后再试" % wait)
            if self.mail_throttle.blocked("code:" + uid):
                raise HttpError(429, "验证码发送太频繁，请过一会儿再试")
            self.mail_throttle.fail("code:" + uid)
            code = "%06d" % secrets.randbelow(10 ** 6)
            self.email_codes[uid] = {"email": email, "code": code, "sent": time.time(), "tries": 0}
        try:
            self.mail_code(email, code, "完成邮箱绑定", "你的账号不会有任何变化")
        except HttpError:
            self.email_codes.pop(uid, None)  # nothing arrived: let them try again at once
            raise

    def mail_code(self, email, code, purpose, otherwise):
        self.mail(email, "Studia 邮箱验证码：%s" % code,
                  "你的验证码是 %s，10 分钟内有效。\n\n如果不是你本人操作，请忽略这封邮件。" % code,
                  mail_page("验证码 %s，10 分钟内有效" % code, "你的邮箱验证码",
                            "在 Studia 里填写下面的验证码，%s。验证码 10 分钟内有效。" % purpose,
                            '<div style="padding:20px 0 20px 10px;border-radius:10px;background:#f4f4f0;text-align:center;%s'
                            'font-size:34px;line-height:1;font-weight:700;letter-spacing:10px;color:#212429;">%s</div>' % (MAIL_MONO, code),
                            "如果不是你本人操作，请忽略这封邮件，%s。" % otherwise))

    def send_signup_code(self, email, ip):
        """Mail a code proving the address someone signs up with. Codes are kept by address: there is no account yet."""
        email = str(email or "").strip()
        if len(email) > 254 or not EMAIL.fullmatch(email):
            raise HttpError(400, "邮箱格式不正确")
        if self.accounts.email_taken(email, ""):
            raise HttpError(400, "这个邮箱已经注册过了")
        key = email.lower()
        with self.lock:
            now = time.time()
            for other in [k for k, v in self.signup_codes.items() if now - v["sent"] > CODE_TTL]:
                del self.signup_codes[other]  # strangers' addresses must not pile up in memory
            pending = self.signup_codes.get(key)
            wait = pending and 60 - (now - pending["sent"])
            if wait and wait > 0:
                raise HttpError(429, "验证码刚发过，请 %d 秒后再试" % wait)
            keys = ("signup-ip:" + ip, "signup:" + key)
            if self.mail_throttle.blocked(*keys):
                raise HttpError(429, "验证码发送太频繁，请过一会儿再试")
            self.mail_throttle.fail(*keys)
            code = "%06d" % secrets.randbelow(10 ** 6)
            self.signup_codes[key] = {"email": email, "code": code, "sent": now, "tries": 0}
        try:
            self.mail_code(email, code, "完成注册", "不会有账号用到这个邮箱")
        except HttpError:
            self.signup_codes.pop(key, None)
            raise

    def signup_email(self, email, code):
        """The address a sign-up proved with its mailed code. The code stays until the account exists, so a
        taken username does not cost a new one."""
        key = str(email or "").strip().lower()
        with self.lock:
            pending = self.signup_codes.get(key)
            if not pending or time.time() - pending["sent"] > CODE_TTL:
                raise HttpError(400, "验证码已过期，请重新发送" if pending else "请先给邮箱发送验证码")
            pending["tries"] += 1
            if pending["tries"] > 5:
                self.signup_codes.pop(key, None)
                raise HttpError(400, "错误次数太多，请重新发送验证码")
            if not hmac.compare_digest(str(code or "").strip().encode(), pending["code"].encode()):
                raise HttpError(400, "验证码不正确")
            return pending["email"]

    def bind_email(self, uid, code):
        with self.lock:
            pending = self.email_codes.get(uid)
            if not pending or time.time() - pending["sent"] > CODE_TTL:
                raise HttpError(400, "验证码已过期，请重新发送")
            pending["tries"] += 1
            if pending["tries"] > 5:
                self.email_codes.pop(uid, None)
                raise HttpError(400, "错误次数太多，请重新发送验证码")
            if not hmac.compare_digest(str(code or "").strip().encode(), pending["code"].encode()):
                raise HttpError(400, "验证码不正确")
            self.email_codes.pop(uid, None)
        try:
            self.accounts.set_email(uid, pending["email"])
        except AccountError as exc:
            raise HttpError(400, str(exc)) from None

    def send_reset(self, user):
        """Mail a one-time link that sets a new password (修改密码 and 忘记密码 alike)."""
        token = self.accounts.create_reset(user["id"])
        link, name = "%s/#/reset/%s" % (self.public_url, token), html.escape(user["username"])
        self.mail(user["email"], "设置 Studia 新密码",
                  "%s，你好：\n\n打开下面的链接设置新密码。链接 30 分钟内有效，只能用一次：\n%s\n\n"
                  "如果不是你本人操作，请忽略这封邮件，密码不会改变。" % (user["username"], link),
                  mail_page("点链接设置新密码，30 分钟内有效", "设置新密码",
                            "%s，你好。点下面的按钮为你的 Studia 账号设置新密码，链接 30 分钟内有效，只能使用一次。" % name,
                            '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr><td style="border-radius:8px;background:#212429;">'
                            '<a href="%s" style="display:inline-block;padding:13px 30px;%sfont-size:15px;font-weight:600;color:#ffffff;'
                            'text-decoration:none;border-radius:8px;">设置新密码</a></td></tr></table>'
                            '<p style="margin:20px 0 0;font-size:12px;line-height:1.7;color:#8d9094;">按钮打不开的话，把这个链接复制到浏览器：<br>'
                            '<a href="%s" style="color:#2d5fa6;word-break:break-all;">%s</a></p>' % (html.escape(link), MAIL_FONT, html.escape(link), html.escape(link)),
                            "设置后，已登录的其他设备会退出。如果不是你本人操作，请忽略这封邮件，你的密码不会改变。"))

    def default_job_limit(self):
        return self.accounts.setting("max_jobs", MAX_JOBS)

    def job_limit(self, uid):
        """Jobs this person may run at once: their own limit if an admin set one, else the site default."""
        user = self.accounts.user(uid)
        return (user or {}).get("max_jobs") or self.default_job_limit()

    def overview(self):
        users = self.accounts.users()
        for user in users:
            app = self.apps.get(user["id"])
            user["jobs"] = app._running() if app else []
            user["job_limit"] = user["max_jobs"] or self.default_job_limit()
        return users

    def all_jobs(self):
        """Every user (not administrator: theirs are under 我的) who has jobs, with their limit and jobs in run order."""
        people = []
        for user in self.accounts.users():
            if user["role"] == "admin":
                continue
            app = self.apps.get(user["id"])
            jobs = app._running() if app else []
            if jobs:
                people.append({"id": user["id"], "username": user["username"],
                               "limit": user["max_jobs"] or self.default_job_limit(), "jobs": jobs})
        return people

    def disable(self, uid):
        self.accounts.set_disabled(uid, True)
        self.sessions.drop_user(uid)
        app = self.apps.get(uid)
        if app:
            app.stop_job()


def _page(title, message, ok, back):
    # WeChat and other in-app browsers have no tabs to close: send them back to Studia on their own.
    # back is None for a login opened in a tab of its own, which is simply closed.
    color = "#237a3e" if ok else "#c8285a"
    back = html.escape(back, quote=True) if back else ""
    refresh = "<meta http-equiv=refresh content='1;url=%s'>" % back if ok and back else ""
    link = ("<a href=\"%s\" style=\"display:block;margin-top:18px;padding:12px;border-radius:8px;background:#141413;"
            "color:#fff;text-align:center;text-decoration:none\">返回 Studia</a>" % back) if back else ""
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>%s"
            "<title>%s</title><body style=\"margin:0;display:grid;place-items:center;min-height:100vh;"
            "font-family:-apple-system,'PingFang SC',sans-serif;background:#f4f5f7\"><div style=\"max-width:420px;"
            "padding:28px;border-radius:12px;background:#fff;box-shadow:0 8px 30px rgba(0,0,0,.08)\">"
            "<h1 style=\"margin:0 0 10px;font-size:20px;color:%s\">%s</h1><p style=\"margin:0;line-height:1.6;"
            "color:#3c3e41\">%s</p>%s</div>") % (
        refresh, html.escape(title), color, html.escape(title), html.escape(message), link)


class HostedAccess:
    """Cookie sessions with CSRF headers, invite-only sign-up and an admin role."""

    mode = "hosted"

    def __init__(self, hub, port):
        self.hub = hub
        url = urlsplit(hub.public_url)
        self.secure = url.scheme == "https"
        self.hosts = {url.netloc, f"127.0.0.1:{port}", f"localhost:{port}"}

    def host_ok(self, host):
        return host in self.hosts

    def headers(self):
        headers = {"X-Frame-Options": "DENY", "Permissions-Policy": "camera=(), microphone=(), geolocation=()"}
        if self.secure:
            headers["Strict-Transport-Security"] = "max-age=31536000"
        return headers

    def _ip(self, request):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if self.hub.trust_proxy and forwarded:
            return forwarded.split(",")[-1].strip()
        return request.client_address[0]

    def _token(self, request):
        cookie = SimpleCookie()
        try:
            cookie.load(request.headers.get("Cookie", ""))
        except Exception:
            return ""
        return cookie[COOKIE].value if COOKIE in cookie else ""

    def _cookie(self, value, max_age):
        return {"Set-Cookie": "%s=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=%d%s"
                              % (COOKIE, value, max_age, "; Secure" if self.secure else "")}

    def _signed_in(self, uid):
        token = self.hub.sessions.create(uid)
        return Reply({"user": self.hub.accounts.user(uid)}, headers=self._cookie(token, self.hub.sessions.ttl))

    # ------------------------------------------------------------ no session needed

    def public(self, request, method, path, query, body):
        hub = self.hub
        if method == "GET" and path == "/api/mode":
            return {"mode": self.mode, "setup": not hub.accounts.has_admin(), "register": hub.registration(), "speed": hub.ui_speed()}
        if method == "POST" and path == "/api/auth/setup":
            ip = self._ip(request)
            key = "ip:" + ip
            if hub.accounts.has_admin():
                raise HttpError(409, "管理员已经设置过了，请直接登录")
            if hub.throttle.blocked(key):
                raise HttpError(429, "尝试次数太多，请稍后再试")
            code = str(body.get("code", "")).strip().upper()
            if not hub.setup_code or not hmac.compare_digest(code.encode(), hub.setup_code.encode()):
                hub.throttle.fail(key)
                hub.audit("setup", ip=ip, ok=False)
                raise HttpError(403, "设置码不正确，请在服务器日志里查看")
            try:
                uid = hub.accounts.setup_admin(str(body.get("username", "")).strip(), str(body.get("password", "")))
            except AccountError as exc:
                raise HttpError(400, str(exc))
            hub.setup_code = None
            hub.audit("setup", actor=hub.accounts.user(uid)["username"], ip=ip)
            return self._signed_in(uid)
        if method == "POST" and path == "/api/auth/login":
            username = str(body.get("username", "")).strip()
            keys = ("ip:" + self._ip(request), "user:" + username.lower())
            ip = self._ip(request)
            wait = hub.throttle.blocked(*keys)
            if wait:
                hub.audit("login", actor=username, ip=ip, ok=False)
                raise HttpError(429, "尝试次数太多，请 %d 分钟后再试" % max(1, wait // 60))
            try:
                user = hub.accounts.authenticate(username, str(body.get("password", "")))
            except AccountError as exc:
                hub.audit("login", actor=username, ip=ip, ok=False)
                raise HttpError(403, str(exc))
            if user is None:
                hub.throttle.fail(*keys)
                hub.audit("login", actor=username, ip=ip, ok=False)
                raise HttpError(401, "用户名或密码不正确")
            hub.throttle.clear(*keys)
            hub.audit("login", actor=user["username"], ip=ip)
            return self._signed_in(user["id"])
        if method == "POST" and path == "/api/auth/register/code":
            rules = hub.registration()
            if not (rules["open"] and rules["email"]):
                raise HttpError(403, "现在注册不需要验证邮箱" if rules["open"] else "现在不开放注册")
            hub.send_signup_code(body.get("email"), self._ip(request))
            return {}
        if method == "POST" and path == "/api/auth/register":
            rules, key, ip = hub.registration(), "ip:" + self._ip(request), self._ip(request)
            if not rules["open"]:
                raise HttpError(403, "现在不开放注册")
            if hub.throttle.blocked(key):
                raise HttpError(429, "尝试次数太多，请稍后再试")
            username = str(body.get("username", "")).strip()
            try:
                email = hub.signup_email(body.get("email"), body.get("code")) if rules["email"] else None
                uid = hub.accounts.register(str(body.get("invite", "")), username, str(body.get("password", "")),
                                            invite=rules["invite"], email=email)
            except (AccountError, HttpError) as exc:
                hub.throttle.fail(key)
                hub.audit("register", actor=username, ip=ip, ok=False)
                raise exc if isinstance(exc, HttpError) else HttpError(400, str(exc))
            if email:
                hub.signup_codes.pop(email.lower(), None)
            hub.audit("register", actor=hub.accounts.user(uid)["username"], ip=ip)
            return self._signed_in(uid)
        if method == "POST" and path == "/api/auth/forgot":
            ip, login = self._ip(request), str(body.get("login", "")).strip()
            if hub.smtp() is None:
                raise HttpError(400, "管理员还没有配置邮件服务，请联系管理员重置密码")
            user = hub.accounts.find(login) if login else None
            keys = ("ip:" + ip,) + (("reset:" + user["id"],) if user else ())
            if hub.mail_throttle.blocked(*keys):
                raise HttpError(429, "发送太频繁，请过一会儿再试")
            hub.mail_throttle.fail(*keys)
            sent = bool(user and user["email"] and not user["disabled"])
            if sent:
                hub.send_reset(user)
            hub.audit("forgot", actor=login[:64], ip=ip, ok=sent)
            return {}  # the same answer whether or not the account exists
        if method == "POST" and path == "/api/auth/reset":
            ip = self._ip(request)
            if hub.throttle.blocked("ip:" + ip):
                raise HttpError(429, "尝试次数太多，请稍后再试")
            try:
                uid = hub.accounts.reset_password(str(body.get("token", "")), str(body.get("password", "")))
            except AccountError as exc:
                hub.throttle.fail("ip:" + ip)
                raise HttpError(400, str(exc))
            hub.sessions.drop_user(uid)  # every other device signs in again
            user = hub.accounts.user(uid)
            hub.audit("reset", actor=user["username"], ip=ip)
            if user["disabled"]:
                raise HttpError(403, "这个账号已被停用，请联系管理员")
            return self._signed_in(uid)
        match = re.fullmatch(r"/oauth/callback/([\w-]+)", path)
        if method == "GET" and match:
            session = hub.sessions.get(self._token(request))
            ok, message, back = hub.oauth_callback(match[1], (query.get("token") or [""])[0].strip(),
                                             session["uid"] if session else None)
            return Reply(_page("登录成功" if ok else "登录没有完成", message, ok, back), status=200 if ok else 400,
                         content_type="text/html; charset=utf-8",
                         headers={"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})
        return NOT_HANDLED

    # ------------------------------------------------------------ session required

    def authorize(self, request, method, query):
        token = self._token(request)
        session = self.hub.sessions.get(token)
        if session is None:
            raise HttpError(401, "请先登录 Studia")
        user = self.hub.accounts.user(session["uid"])
        if user is None or user["disabled"]:
            self.hub.sessions.drop(token)
            raise HttpError(401, "账号已停用或不存在")
        if method == "POST" and not hmac.compare_digest(request.headers.get("X-Studia-CSRF", ""), session["csrf"]):
            raise HttpError(403, "请求校验失败，请刷新页面后重试")
        self.hub.accounts.touch(user["id"])
        return {"app": self.hub.app(user["id"]), "user": user, "session": session, "token": token}

    def private(self, request, method, path, query, body, ctx):
        hub, user = self.hub, ctx["user"]
        if method == "GET" and path == "/api/auth/me":
            return {"user": user, "csrf": ctx["session"]["csrf"], "mail": hub.smtp() is not None}
        if method == "POST" and path == "/api/auth/logout":
            hub.sessions.drop(ctx["token"])
            return Reply({}, headers=self._cookie("", 0))
        if method == "POST" and path == "/api/auth/password":
            # The password changes only through a link mailed to the bound address.
            if not user["email"]:
                raise HttpError(400, "请先绑定邮箱")
            if hub.mail_throttle.blocked("reset:" + user["id"]):
                raise HttpError(429, "邮件发送太频繁，请过一会儿再试")
            hub.mail_throttle.fail("reset:" + user["id"])
            hub.send_reset(user)
            hub.audit("password_link", actor=user["username"], ip=self._ip(request))
            return {"email": user["email"]}
        if method == "POST" and path == "/api/auth/username":
            try:
                hub.accounts.set_username(user["id"], str(body.get("username", "")).strip())
            except AccountError as exc:
                raise HttpError(400, str(exc))
            fresh = hub.accounts.user(user["id"])
            if user["id"] in hub.apps:
                hub.apps[user["id"]].owner = fresh["username"]  # runtime log lines name the account
            hub.audit("username", actor=fresh["username"], target=user["username"], ip=self._ip(request))
            return {"user": fresh}
        if method == "POST" and path == "/api/auth/email/code":
            hub.send_email_code(user["id"], body.get("email"))
            return {}
        if method == "POST" and path == "/api/auth/email":
            hub.bind_email(user["id"], body.get("code"))
            fresh = hub.accounts.user(user["id"])
            hub.audit("email", actor=user["username"], ip=self._ip(request))
            return {"user": fresh}
        if not path.startswith("/api/admin/"):
            return NOT_HANDLED
        if user["role"] != "admin":
            raise HttpError(403, "只有管理员可以访问")
        try:
            result = self._admin(method, path, body, user, query)
        except AccountError as exc:
            raise HttpError(400, str(exc))
        if method == "POST":
            target = path.split("/")[4] if path.count("/") >= 4 else ""
            name = (hub.accounts.user(target) or {}).get("username", target)
            hub.audit("admin:" + path.rsplit("/", 1)[-1], actor=user["username"], target=name, ip=self._ip(request))
        return result

    def _admin(self, method, path, body, me, query=None):
        hub = self.hub
        if method == "GET" and path == "/api/admin/logs":
            arg = lambda name: (query or {}).get(name, [""])[0]
            kind = "audit" if arg("kind") == "audit" else "app"
            try:
                start, end = float(arg("from")), float(arg("to"))
            except ValueError:
                raise HttpError(400, "请选择导出的时间段") from None
            if not 0 < start < end or end - start > 92 * 86400:
                raise HttpError(400, "时间段无效，最长 92 天")
            hub.audit("admin:export_logs", actor=me["username"], target=kind)
            name = "studia-%s-%s.log" % (kind, time.strftime("%Y%m%d-%H%M", time.localtime(start)))
            return Reply(export_logs(hub.data if kind == "audit" else hub.log_dir, kind, start, end).encode("utf-8"),
                         content_type="text/plain; charset=utf-8",
                         headers={"Content-Disposition": 'attachment; filename="%s"' % name})
        if method == "GET" and path == "/api/admin/users":
            return {"users": hub.overview()}
        if method == "GET" and path == "/api/admin/invites":
            return {"invites": hub.accounts.invites(), "registration": hub.registration()}
        if method == "GET" and path == "/api/admin/memory":
            return dict(hub.memory.stats(), mooc=hub.mooc_memory.stats())
        if method == "GET" and path == "/api/admin/jobs":
            return {"people": hub.all_jobs()}
        if method == "GET" and path == "/api/admin/settings":
            return hub.site_settings()
        if method == "POST" and path == "/api/admin/default-model/test":
            return hub.test_default_model()
        if method == "POST" and path == "/api/admin/settings":
            limit = _job_limit(body["max_jobs"]) if "max_jobs" in body else None
            if "answer_pace" in body and body["answer_pace"] not in ANSWER_PACES:
                raise HttpError(400, "答题节奏只能是稳妥或快速")
            speed = body.get("ui_speed")
            if "ui_speed" in body and (isinstance(speed, bool) or not isinstance(speed, (int, float)) or not UI_SPEED[0] <= speed <= UI_SPEED[1]):
                raise HttpError(400, "动画速度要在 %.1f× 到 %.1f× 之间" % UI_SPEED)
            if "default_model" in body:
                hub.save_default_model(body["default_model"])
            if "smtp" in body:
                hub.save_smtp(body["smtp"])
            if "registration" in body:
                hub.save_registration(body["registration"])
            if limit is not None:
                hub.accounts.set_setting("max_jobs", limit)
            if "zhs_parallel_study" in body:
                hub.accounts.set_setting("zhs_parallel_study", body.get("zhs_parallel_study") is True)
            if "answer_pace" in body:
                hub.accounts.set_setting("answer_pace", body["answer_pace"])
            if "ui_speed" in body:
                hub.accounts.set_setting("ui_speed", round(float(speed), 1))
            return hub.site_settings()
        match = re.fullmatch(r"/api/admin/users/(\w+)/jobs/(\w+)/(stop|pause|continue|move)", path)
        if method == "POST" and match:
            app = hub.apps.get(match[1])
            if app is None or match[2] not in app.jobs:
                raise HttpError(404, "任务已经结束")
            return app.stop_job(match[2]) if match[3] == "stop" else app.act_job(match[3], match[2], body, who="管理员")
        if method == "POST" and path == "/api/admin/invites":
            days = min(max(int(body.get("days") or 7), 1), 30)
            return {"code": hub.accounts.create_invite(me["id"], ttl=days * 86400)}
        match = re.fullmatch(r"/api/admin/invites/([\w-]+)/revoke", path)
        if method == "POST" and match:
            hub.accounts.revoke_invite(match[1])
            return {}
        match = re.fullmatch(r"/api/admin/users/(\w+)/(disable|enable|password|stop|limit)", path)
        if method == "POST" and match:
            uid, action = match[1], match[2]
            if hub.accounts.user(uid) is None:
                raise HttpError(404, "用户不存在")
            if action == "disable":
                if uid == me["id"]:
                    raise HttpError(400, "不能停用自己")
                hub.disable(uid)
            elif action == "enable":
                hub.accounts.set_disabled(uid, False)
            elif action == "password":
                hub.accounts.set_password(uid, str(body.get("password", "")))
                hub.sessions.drop_user(uid)
            elif action == "limit":
                # Empty returns the user to the site default.
                limit = body.get("max_jobs")
                hub.accounts.set_job_limit(uid, None if limit in (None, "") else _job_limit(limit))
            else:
                app = hub.apps.get(uid)
                if app:
                    app.stop_job()
            return {}
        raise HttpError(404, "not found")


LOG_TIME = re.compile(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
EXPORT_LIMIT = 20 * 1024 * 1024


def export_logs(directory, kind, start, end):
    """Log lines written between two epoch times. A line without its own time (a traceback)
    goes with the line before it. Runtime logs are one file per day; audit is one file."""
    if kind == "audit":
        files = [Path(directory) / "audit.log"]
    else:
        # From the day before: older servers kept writing into the file of the day they started.
        day = datetime.date.fromtimestamp(start) - datetime.timedelta(days=1)
        last = datetime.date.fromtimestamp(end)
        files = []
        while day <= last:
            files.append(Path(directory) / ("icve-ai-assistant-log_%s.log" % day.isoformat()))
            day += datetime.timedelta(days=1)
    lines, size, keep = [], 0, False
    for path in files:
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if kind == "audit":
                    try:
                        stamp = json.loads(line)["time"]
                    except (ValueError, KeyError, TypeError):
                        continue
                else:
                    match = LOG_TIME.match(line)
                    stamp = match[1] if match else None
                if stamp:
                    keep = start <= time.mktime(time.strptime(stamp, "%Y-%m-%d %H:%M:%S")) <= end
                if keep:
                    lines.append(line)
                    size += len(line)
                    if size > EXPORT_LIMIT:
                        lines.append("……超过 20MB，后面的省略了，请缩短时间段\n")
                        return "".join(lines)
    return "".join(lines) or "这段时间没有日志。\n"


def _job_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        raise HttpError(400, "请填写 1 到 %d 之间的整数" % MAX_PENDING) from None
    if not 1 <= limit <= MAX_PENDING:
        raise HttpError(400, "请填写 1 到 %d 之间的整数" % MAX_PENDING)
    return limit


def serve_hosted(hub, host, port):
    logging.getLogger().addHandler(_EventLogHandler())
    server = ThreadingHTTPServer((host, port), None)
    server.daemon_threads = True
    server.RequestHandlerClass = make_handler(HostedAccess(hub, server.server_address[1]))
    print("Studia 服务器模式已启动：监听 %s:%d，对外地址 %s" % (host, server.server_address[1], hub.public_url))
    print("数据目录：%s；按 Ctrl+C 退出。" % hub.data)
    threading.Thread(target=hub.resume, daemon=True, name="studia-resume").start()
    # Everyone with an account, not only those who opened the site since the restart: their saved logins count too.
    threading.Thread(target=keep_passports, daemon=True, name="studia-keepalive",
                     args=(lambda: [hub.app(user["id"]) for user in hub.accounts.users() if not user["disabled"]],)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for app in list(hub.apps.values()):
            app.shutdown()
        drain()
        server.server_close()


def _interrupt(*_):
    raise KeyboardInterrupt


def _key_file(path):
    """The key text from a file, generated on first start so a fresh deployment needs no setup."""
    if not path.exists():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=") + "\n")
        print("已生成主密钥：%s 。请把它另外备份一份；丢了它，用户保存的平台登录和 API Key 就解不开了。" % path)
    return path.read_text().strip()


def main(argv):
    env = os.environ.get
    parser = argparse.ArgumentParser(prog="StartWork.py --serve", description="Studia 服务器模式（多用户）。"
                                     "每个选项也可以用括号里的环境变量设置，Docker 部署时就是这样用的。")
    parser.add_argument("--host", default=env("STUDIA_HOST", "127.0.0.1"),
                        help="监听地址，放在反向代理后面时保持 127.0.0.1（STUDIA_HOST）")
    parser.add_argument("--port", type=int, default=int(env("STUDIA_PORT", "8080")), help="（STUDIA_PORT）")
    parser.add_argument("--data", default=env("STUDIA_DATA", "~/.studia-hosted"),
                        help="数据目录：数据库和每个用户的子目录（STUDIA_DATA）")
    parser.add_argument("--public-url", default=env("STUDIA_PUBLIC_URL"),
                        help="浏览器访问用的地址，例如 https://studia.example.com（STUDIA_PUBLIC_URL）")
    parser.add_argument("--trust-proxy", action="store_true", default=env("STUDIA_TRUST_PROXY", "") in ("1", "true", "yes"),
                        help="信任反向代理传来的 X-Forwarded-For（STUDIA_TRUST_PROXY=1）")
    parser.add_argument("--key-file", default=env("STUDIA_KEY_FILE"),
                        help="没有设置 %s 时，从这个文件读主密钥，文件不存在就生成；默认是数据目录下的 secret.key（STUDIA_KEY_FILE）" % KEY_ENV)
    parser.add_argument("--create-admin", metavar="USERNAME", help="创建管理员账号后退出")
    parser.add_argument("--gen-key", action="store_true", help="生成加密用户数据的主密钥后退出")
    args = parser.parse_args(argv)
    if args.gen_key:
        print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("="))
        print("把它设成环境变量 %s 后再启动；丢失这个密钥，用户保存的平台登录和 API Key 将无法解密。" % KEY_ENV)
        return 0
    try:
        key = load_key(os.environ.get(KEY_ENV) or _key_file(Path(args.key_file or Path(args.data).expanduser() / "secret.key")))
    except ValueError as exc:
        if not args.create_admin:
            print("缺少或无效的加密密钥：%s" % exc)
            return 1
        key = None
    hub = Hub(args.data, args.public_url or "http://127.0.0.1:%d" % args.port, key=key,
              trust_proxy=args.trust_proxy)
    if args.create_admin:
        password = getpass.getpass("设置 %s 的密码：" % args.create_admin)
        if password != getpass.getpass("再输入一次："):
            print("两次输入的密码不一致。")
            return 1
        try:
            hub.accounts.create_user(args.create_admin, password, role="admin")
        except AccountError as exc:
            print(exc)
            return 1
        print("管理员 %s 已创建。" % args.create_admin)
        return 0
    if hub.setup_code:
        print("=" * 48)
        print("还没有管理员。打开 %s ，用下面的设置码创建管理员账号：" % hub.public_url)
        print("    设置码：%s" % hub.setup_code)
        print("（每次启动都会换一个，创建完管理员后失效）")
        print("=" * 48, flush=True)
    # `docker stop` sends SIGTERM: shut down like Ctrl+C so running jobs get their stop signal.
    signal.signal(signal.SIGTERM, _interrupt)
    serve_hosted(hub, args.host, args.port)
    return 0
