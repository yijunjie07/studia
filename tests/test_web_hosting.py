import http.client
import json
import logging
import os
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

import web.accounts
import web.hosting
from web.accounts import AccountError, Accounts, Sessions, Throttle
from core.settings import SettingsError
from web.hosting import COOKIE, EncryptedSettingsStore, HostedAccess, Hub, _key_file, export_logs, load_key, main
from web.server import JOBS, Studia, _EventLogHandler, make_handler


class HostedServerTest(unittest.TestCase):
    def setUp(self):
        fast = patch.object(web.accounts, "ITERATIONS", 1000)
        fast.start()
        self.addCleanup(fast.stop)
        shared = patch.dict(os.environ, {"STUDIA_DEFAULT_API_KEY": "test-shared-key"})
        shared.start()
        self.addCleanup(shared.stop)
        # The admin's default model is tested before it is saved: answer as a provider would.
        self.detected, self.connect_error = "chat_completions", None
        def check(client):
            if self.connect_error:
                raise web.hosting.AIError(self.connect_error)
            client.config.api_format = self.detected
        connection = patch("web.hosting.AIClient.check_connection", check)
        connection.start()
        self.addCleanup(connection.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), None)
        self.port = self.server.server_address[1]
        self.hub = Hub(directory.name, "http://127.0.0.1:%d" % self.port, key=os.urandom(32))
        self.server.RequestHandlerClass = make_handler(HostedAccess(self.hub, self.port))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.admin_id = self.hub.accounts.create_user("admin", "admin-password", role="admin")

    def request(self, method, path, body=None, cookie=None, csrf=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        headers = {"Host": host or "127.0.0.1:%d" % self.port}
        if cookie:
            headers["Cookie"] = "%s=%s" % (COOKIE, cookie)
        if csrf:
            headers["X-Studia-CSRF"] = csrf
        data = json.dumps(body) if body is not None else None
        if data:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        set_cookie = response.getheader("Set-Cookie") or ""
        token = set_cookie.split(";")[0].split("=", 1)[1] if set_cookie.startswith(COOKIE + "=") else None
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = raw.decode()
        return response.status, payload, token, set_cookie

    def test_first_visit_sets_up_the_admin_with_the_logged_code(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = Hub(directory, "http://127.0.0.1:%d" % self.port, key=os.urandom(32))
            self.server.RequestHandlerClass = make_handler(HostedAccess(hub, self.port))
            self.assertTrue(self.request("GET", "/api/mode")[1]["setup"])
            form = {"username": "owner", "password": "owner-password"}
            self.assertEqual(self.request("POST", "/api/auth/setup", dict(form, code="0000-0000-0000"))[0], 403)
            status, payload, token, _ = self.request("POST", "/api/auth/setup", dict(form, code=hub.setup_code.lower()))
            self.assertEqual((status, payload["user"]["role"]), (200, "admin"))
            self.assertTrue(token)
            self.assertFalse(self.request("GET", "/api/mode")[1]["setup"])
            self.assertEqual(self.request("POST", "/api/auth/setup", dict(form, code="x"))[0], 409)

    def login(self, username, password):
        status, _, token, _ = self.request("POST", "/api/auth/login", {"username": username, "password": password})
        self.assertEqual(status, 200)
        csrf = self.request("GET", "/api/auth/me", cookie=token)[1]["csrf"]
        return token, csrf

    # ------------------------------------------------------------ email, username, password links

    def mail_ready(self):
        """Pretend the admin set up a mail server; every message lands in the returned list."""
        sent = []
        server = Mock(send_message=sent.append)
        opened = patch("web.hosting.smtp_open", return_value=server)
        opened.start()
        self.addCleanup(opened.stop)
        self.hub.site_store.set("smtp", {"host": "smtp.example.com", "port": 465, "security": "ssl", "username": "bot@example.com",
                                         "password": "smtp-secret", "sender": "bot@example.com", "sender_name": "Studia"})
        return sent

    def test_admin_sets_up_mail_only_after_it_signs_in(self):
        token, csrf = self.login("admin", "admin-password")
        post = lambda body: self.request("POST", "/api/admin/settings", body, cookie=token, csrf=csrf)
        self.assertFalse(self.request("GET", "/api/auth/me", cookie=token)[1]["mail"])
        config = {"host": "smtp.qq.com", "security": "ssl", "username": "me@qq.com", "password": "auth-code"}
        with patch("web.hosting.smtp_open", side_effect=web.hosting.smtplib.SMTPAuthenticationError(535, b"bad")):
            status, reply, _, _ = post({"smtp": config})
        self.assertEqual(status, 400)
        self.assertIn("账号或密码", reply["error"])
        self.assertIsNone(self.hub.smtp())
        with patch("web.hosting.smtp_open") as opened:
            saved = post({"smtp": config})[1]["smtp"]
            self.assertEqual(opened.call_args[0][0]["port"], 465)  # the default port of the chosen security
            self.assertEqual((saved["sender"], saved["password_hint"]), ("me@qq.com", "已保存"))
            self.assertNotIn("password", saved)
            self.assertNotIn(b"auth-code", (self.hub.data / "site" / "settings.enc").read_bytes())
            self.assertEqual(post({"smtp": dict(config, password="", sender_name="课程助手")})[0], 200)
            self.assertEqual(self.hub.smtp()["password"], "auth-code")  # blank keeps it on the same server
            self.assertEqual(post({"smtp": dict(config, host="smtp.evil.example", password="")})[0], 400)
            self.assertEqual(post({"smtp": dict(config, security="tls")})[0], 400)
        self.assertTrue(self.request("GET", "/api/auth/me", cookie=token)[1]["mail"])
        self.assertIsNone(post({"smtp": None})[1]["smtp"])

    def test_email_is_bound_with_the_code_mailed_to_it(self):
        alice = self.hub.accounts.create_user("alice", "alice-password")
        self.hub.accounts.create_user("bob", "bob-password")
        token, csrf = self.login("alice", "alice-password")
        post = lambda path, body=None: self.request("POST", path, body or {}, cookie=token, csrf=csrf)
        self.assertIn("没有配置邮件服务", post("/api/auth/email/code", {"email": "a@example.com"})[1]["error"])
        sent = self.mail_ready()
        self.assertEqual(post("/api/auth/password")[1]["error"], "请先绑定邮箱")
        self.assertEqual(post("/api/auth/email/code", {"email": "not-an-email"})[0], 400)
        self.assertEqual(post("/api/auth/email/code", {"email": "Alice@Example.com"})[0], 200)
        self.assertEqual(post("/api/auth/email/code", {"email": "Alice@Example.com"})[0], 429)  # one a minute
        self.assertEqual(sent[0]["To"], "Alice@Example.com")
        code = re.search(r"\d{6}", sent[0].get_body(("plain",)).get_content())[0]
        self.assertIn(">%s</div>" % code, sent[0].get_body(("html",)).get_content())  # the designed mail shows it too
        self.assertEqual(post("/api/auth/email", {"code": "000000" if code != "000000" else "111111"})[1]["error"], "验证码不正确")
        self.assertEqual(post("/api/auth/email", {"code": code})[1]["user"]["email"], "Alice@Example.com")
        self.assertEqual(post("/api/auth/email", {"code": code})[0], 400)  # used up
        bob_token, bob_csrf = self.login("bob", "bob-password")
        status, reply, _, _ = self.request("POST", "/api/auth/email/code", {"email": "alice@example.com"}, cookie=bob_token, csrf=bob_csrf)
        self.assertIn("已经绑定了其他账号", reply["error"])
        self.assertEqual(len(sent), 1)
        self.assertEqual(self.hub.accounts.user(alice)["email"], "Alice@Example.com")

    def test_password_changes_only_through_the_newest_mailed_link(self):
        alice = self.hub.accounts.create_user("alice", "alice-password")
        self.hub.accounts.set_email(alice, "alice@example.com")
        token, csrf = self.login("alice", "alice-password")
        sent = self.mail_ready()
        link = lambda: re.search(r"/#/reset/([\w-]+)", sent[-1].get_body(("plain",)).get_content())[1]
        self.assertEqual(self.request("POST", "/api/auth/password", {}, cookie=token, csrf=csrf)[1], {"email": "alice@example.com"})
        old = link()
        page = sent[-1].get_body(("html",)).get_content()
        self.assertIn('href="%s/#/reset/%s"' % (self.hub.public_url, old), page)
        self.assertIn("alice，你好", page)
        self.request("POST", "/api/auth/password", {}, cookie=token, csrf=csrf)
        reset = lambda t, password="brand-new-pass": self.request("POST", "/api/auth/reset", {"token": t, "password": password})
        self.assertEqual(reset(old)[0], 400)  # superseded by the newer mail
        self.assertEqual(reset(link(), "short")[0], 400)  # a too-short password does not use up the link
        status, payload, cookie, _ = reset(link())
        self.assertEqual((status, payload["user"]["username"]), (200, "alice"))
        self.assertTrue(cookie)
        self.assertEqual(self.request("GET", "/api/auth/me", cookie=token)[0], 401)  # other devices are signed out
        self.assertEqual(reset(link())[0], 400)  # single use
        self.login("alice", "brand-new-pass")

    def test_forgot_password_answers_the_same_for_unknown_accounts(self):
        alice = self.hub.accounts.create_user("alice", "alice-password")
        self.hub.accounts.set_email(alice, "alice@example.com")
        self.hub.accounts.create_user("nomail", "nomail-password")
        forgot = lambda login: self.request("POST", "/api/auth/forgot", {"login": login})
        self.assertEqual(forgot("alice")[0], 400)  # no mail server: ask the admin
        sent = self.mail_ready()
        self.assertEqual([forgot(x)[:2] for x in ("ghost", "nomail")], [(200, {}), (200, {})])
        self.assertEqual(sent, [])
        self.assertEqual(forgot("ALICE@example.com")[0], 200)
        self.assertEqual([m["To"] for m in sent], ["alice@example.com"])
        self.hub.accounts.set_disabled(alice, True)
        self.assertEqual(forgot("alice")[0], 200)
        self.assertEqual(len(sent), 1)  # a disabled account gets no link
        self.assertEqual([forgot("alice")[0] for _ in range(2)], [200, 429])  # five an hour from one address

    def test_username_can_change_but_stays_unique(self):
        alice = self.hub.accounts.create_user("alice", "alice-password")
        token, csrf = self.login("alice", "alice-password")
        rename = lambda name: self.request("POST", "/api/auth/username", {"username": name}, cookie=token, csrf=csrf)
        self.assertEqual(rename("ADMIN")[1]["error"], "用户名已被使用")
        self.assertEqual(rename("a")[0], 400)
        self.assertEqual(rename("小爱")[1]["user"]["username"], "小爱")
        self.assertEqual(self.hub.app(alice).owner, "小爱")  # runtime log lines follow the new name
        self.login("小爱", "alice-password")
        self.assertEqual(self.request("POST", "/api/auth/login", {"username": "alice", "password": "alice-password"})[0], 401)

    def test_everything_but_login_needs_a_session(self):
        self.assertEqual(self.request("GET", "/api/mode")[1], {"mode": "hosted", "setup": False})
        self.assertEqual(self.request("GET", "/api/state")[0], 401)
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/api/mode", host="evil.example")[0], 403)

    def test_admin_sets_job_limits_and_sees_everyones_jobs(self):
        token, csrf = self.login("admin", "admin-password")
        alice = self.hub.accounts.create_user("alice", "alice-password")
        post = lambda path, body: self.request("POST", path, body, cookie=token, csrf=csrf)
        settings = self.request("GET", "/api/admin/settings", cookie=token)[1]
        self.assertEqual((settings["max_jobs"], settings["zhs_parallel_study"]), (4, False))
        self.assertEqual(post("/api/admin/settings", {"max_jobs": 2})[1], dict(settings, max_jobs=2))
        self.assertFalse(self.hub.app(alice).zhs_parallel())
        self.assertTrue(post("/api/admin/settings", {"zhs_parallel_study": True})[1]["zhs_parallel_study"])
        self.assertTrue(self.hub.app(alice).zhs_parallel())
        post("/api/admin/settings", {"zhs_parallel_study": False})
        # The Zhihuishu answer pace is the admin's call for the whole site; people only see it.
        self.assertEqual(settings["answer_pace"], "steady")
        alice_token, alice_csrf = self.login("alice", "alice-password")
        self.assertEqual(post("/api/admin/settings", {"answer_pace": "turbo"})[0], 400)
        self.assertEqual(post("/api/admin/settings", {"answer_pace": "fast"})[1]["answer_pace"], "fast")
        mine = self.request("GET", "/api/settings", cookie=alice_token)[1]
        self.assertEqual((mine["pace"], mine["pace_locked"]), ("fast", True))
        status, reply, _, _ = self.request("POST", "/api/settings/pace", {"pace": "steady"}, cookie=alice_token, csrf=alice_csrf)
        self.assertEqual((status, self.hub.app(alice).answer_pace()), (403, "fast"))
        post("/api/admin/settings", {"answer_pace": "steady"})
        self.assertEqual(self.hub.app(alice).answer_pace(), "steady")
        self.assertEqual(self.hub.job_limit(alice), 2)
        self.assertEqual(post("/api/admin/users/%s/limit" % alice, {"max_jobs": 6})[0], 200)
        self.assertEqual(self.hub.job_limit(alice), 6)
        self.assertEqual(post("/api/admin/users/%s/limit" % alice, {"max_jobs": ""})[0], 200)
        self.assertEqual(self.hub.job_limit(alice), 2)
        self.assertEqual(post("/api/admin/settings", {"max_jobs": 0})[0], 400)
        app = self.hub.app(alice)
        app.jobs = {"j1": {"id": "j1", "kind": "study", "title": "自动学习", "course": "c", "course_name": "课",
                           "platform": "zhs", "state": "queued", "summary": "", "started": 1, "ended": None,
                           "lines": [], "cancel": threading.Event()}}
        admin_app = self.hub.app(self.request("GET", "/api/auth/me", cookie=token)[1]["user"]["id"])
        admin_app.jobs = {"mine": dict(app.jobs["j1"], id="mine", cancel=threading.Event())}   # under 我的, not 全站
        people = self.request("GET", "/api/admin/jobs", cookie=token)[1]["people"]
        admin_app.jobs = {}
        self.assertEqual([(u["username"], u["limit"], [j["state"] for j in u["jobs"]]) for u in people], [("alice", 2, ["queued"])])
        self.assertEqual(post("/api/admin/users/%s/jobs/j1/pause" % alice, {})[0], 200)
        self.assertEqual(app.jobs["j1"]["state"], "paused")
        alice_token, alice_csrf = self.login("alice", "alice-password")   # people order their own jobs too
        self.assertEqual(self.request("POST", "/api/jobs/continue", {"id": "j1"}, cookie=alice_token, csrf=alice_csrf)[0], 200)
        self.assertNotEqual(app.jobs["j1"]["state"], "paused")
        self.assertEqual(post("/api/admin/users/%s/jobs/j1/stop" % alice, {})[0], 200)
        self.assertTrue(app.jobs["j1"]["cancel"].is_set())
        status, text, _, _ = self.request("GET", "/api/admin/logs?kind=audit&from=%d&to=%d" % (time.time() - 3600, time.time() + 60), cookie=token)
        self.assertEqual(status, 200)
        self.assertIn("admin:limit", text)   # the limit changes above were recorded
        self.assertEqual(self.request("GET", "/api/admin/logs?kind=app&from=x&to=1", cookie=token)[0], 400)
        # A user cannot reach any of it.
        user_token, user_csrf = self.login("alice", "alice-password")
        self.assertEqual(self.request("POST", "/api/admin/settings", {"max_jobs": 20},
                                      cookie=user_token, csrf=user_csrf)[0], 403)

    def test_admin_default_model_is_live_private_and_survives_restart(self):
        from ai.client import AIConfig
        from ai.defaults import DEFAULT_PROFILE_ID, default_config
        token, csrf = self.login("admin", "admin-password")
        alice = self.hub.accounts.create_user("alice", "alice-password")
        bob = self.hub.accounts.create_user("bob", "bob-password")
        app = self.hub.app(alice)
        other = self.hub.app(bob)
        custom = AIConfig("https://private.example/v1", "personal", "personal-secret")
        profile_id = other.store.save_ai_profile(custom)
        other.store.activate_ai_profile(profile_id)
        old = app.store.ai_config()
        app.store.save_ai_health(old, "ok")
        initial = self.request("GET", "/api/admin/settings", cookie=token)[1]["default_model"]
        self.assertEqual(initial["model"], default_config().model)
        self.assertNotIn("api_key", initial)
        form = {"provider_name": "站点服务", "base_url": "https://site.example/v1",
                "model": "site-model", "api_key": "sk-site-private-12345678", "api_format": "responses"}
        self.detected = "responses"
        status, result, _, _ = self.request("POST", "/api/admin/settings", {"default_model": form}, cookie=token, csrf=csrf)
        self.assertEqual(status, 200)
        self.assertEqual(result["default_model"]["key_hint"], "sk-…5678")
        self.assertNotIn(form["api_key"], json.dumps(result))
        # No intervening HTTP request: queued jobs resolve the new default themselves.
        self.assertEqual(app.store.ai_config(), AIConfig(**form))
        # The admin's test counts for every user: nobody sees an untested default.
        self.assertEqual(app.store.ai_health(app.store.ai_config())["status"], "ok")
        self.assertEqual(result["default_model"]["health"], "ok")
        self.assertEqual(result["default_model"]["source"], "site")
        self.assertEqual(other.store.ai_config(), custom)
        self.assertEqual(other.store.ai_profiles()[0].id, DEFAULT_PROFILE_ID)
        self.assertEqual(other.store.ai_profiles()[0].config, AIConfig(**form))
        self.assertFalse(other.store.ai_profiles()[0].active)
        late = self.hub.accounts.create_user("late", "late-password")
        self.assertEqual(self.hub.app(late).store.ai_config(), AIConfig(**form))
        restarted = Hub(self.hub.data, self.hub.public_url, key=self.hub.key)
        self.assertEqual(restarted.app(alice).store.ai_config(), AIConfig(**form))
        self.assertEqual(restarted.app(bob).store.ai_config(), custom)
        public = self.request("GET", "/api/settings", cookie=token)[1]
        self.assertNotIn(form["api_key"], json.dumps(public))
        self.assertFalse(public["models"][0]["deletable"])
        for path in self.hub.data.rglob("*"):
            if path.is_file():
                self.assertNotIn(form["api_key"].encode(), path.read_bytes(), str(path))
        self.assertEqual(self.hub.site_store.path.stat().st_mode & 0o777, 0o600)
        self.assertIn("admin:settings", (self.hub.data / "audit.log").read_text())
        # Blank keys retain the server-side value, not the masked hint from GET.
        form.update(model="replacement", api_key="  ")
        self.assertEqual(self.request("POST", "/api/admin/settings", {"default_model": form}, cookie=token, csrf=csrf)[0], 200)
        self.assertEqual(app.store.ai_config().api_key, "sk-site-private-12345678")
        self.assertEqual(app.store.ai_config().model, "replacement")
        self.assertEqual(old.model, default_config().model)  # clients already running keep their snapshot
        form.update(api_format="auto", api_key="")
        self.assertEqual(self.request("POST", "/api/admin/settings", {"default_model": form}, cookie=token, csrf=csrf)[0], 200)
        def detect(client):
            client.config.api_format = "responses"
        with patch("web.server.AIClient.check_connection", detect):
            self.assertEqual(app.test_model(DEFAULT_PROFILE_ID)["health"], "ok")
        self.assertEqual(app.store.ai_config().api_format, "responses")
        self.assertEqual(app.store.ai_health(app.store.ai_config())["status"], "ok")

    def test_default_model_is_tested_before_it_is_saved(self):
        token, csrf = self.login("admin", "admin-password")
        alice = self.hub.accounts.create_user("alice", "alice-password")
        app = self.hub.app(alice)
        before = self.hub.default_model()
        form = {"base_url": "https://broken.example/v1", "model": "m", "api_key": "sk-broken-key"}
        self.connect_error = "401 Unauthorized"
        status, result, _, _ = self.request("POST", "/api/admin/settings", {"default_model": form}, cookie=token, csrf=csrf)
        self.assertEqual(status, 400)
        self.assertIn("401 Unauthorized", json.dumps(result, ensure_ascii=False))
        self.assertEqual(self.hub.default_model(), before)
        self.assertEqual(app.store.ai_config(), before)
        # Testing the live default records the outcome for the site, and users see it.
        status, result, _, _ = self.request("POST", "/api/admin/default-model/test", {}, cookie=token, csrf=csrf)
        self.assertEqual((status, result["health"]), (200, "error"))
        self.assertEqual(app.store.ai_health(app.store.ai_config())["status"], "error")
        self.connect_error = None
        self.assertEqual(self.request("POST", "/api/admin/default-model/test", {}, cookie=token, csrf=csrf)[1]["health"], "ok")
        self.assertEqual(app.store.ai_health(app.store.ai_config())["status"], "ok")
        # A saved site default can be withdrawn back to the built-in one.
        self.assertEqual(self.request("POST", "/api/admin/settings", {"default_model": dict(form, base_url="https://ok.example/v1")},
                                      cookie=token, csrf=csrf)[0], 200)
        settings = self.request("GET", "/api/admin/settings", cookie=token)[1]
        self.assertEqual((settings["default_model"]["source"], settings["builtin_available"]), ("site", True))
        self.assertEqual(app.store.ai_config().base_url, "https://ok.example/v1")
        status, settings, _, _ = self.request("POST", "/api/admin/settings", {"default_model": None}, cookie=token, csrf=csrf)
        self.assertEqual((status, settings["default_model"]["source"]), (200, "builtin"))
        self.assertEqual(app.store.ai_config(), before)

    def test_blank_key_is_not_sent_to_a_new_host(self):
        token, csrf = self.login("admin", "admin-password")
        path = "/api/admin/settings"
        before = self.hub.default_model()
        form = {"base_url": "https://other.example/v1", "model": "m", "api_key": ""}
        status, result, _, _ = self.request("POST", path, {"default_model": form}, cookie=token, csrf=csrf)
        self.assertEqual(status, 400)
        self.assertIn("API Key", result["error"] if isinstance(result, dict) else result)
        self.assertEqual(self.hub.default_model(), before)
        # Same host, different path and model: the saved key is kept.
        form.update(base_url="https://mochif.com/v2", model="other")
        self.assertEqual(self.request("POST", path, {"default_model": form}, cookie=token, csrf=csrf)[0], 200)
        self.assertEqual(self.hub.default_model().api_key, "test-shared-key")

    def test_without_shared_key_there_is_no_builtin_until_admin_sets_one(self):
        from ai.defaults import DEFAULT_PROFILE_ID
        token, csrf = self.login("admin", "admin-password")
        alice = self.hub.accounts.create_user("alice", "alice-password")
        with patch.dict(os.environ, {"STUDIA_DEFAULT_API_KEY": ""}):
            self.assertIsNone(self.hub.app(alice).store.ai_config())
            self.assertEqual(self.hub.app(alice).store.ai_profiles(), [])
            self.assertIsNone(self.request("GET", "/api/admin/settings", cookie=token)[1]["default_model"])
            form = {"base_url": "https://site.example/v1", "model": "m", "api_key": ""}
            self.assertEqual(self.request("POST", "/api/admin/settings", {"default_model": form}, cookie=token, csrf=csrf)[0], 400)
            form["api_key"] = "sk-site-key"
            self.assertEqual(self.request("POST", "/api/admin/settings", {"default_model": form}, cookie=token, csrf=csrf)[0], 200)
            profile = self.hub.app(alice).store.ai_profiles()[0]
            self.assertEqual((profile.id, profile.config.api_key, profile.active), (DEFAULT_PROFILE_ID, "sk-site-key", True))

    def test_default_model_permissions_and_validation(self):
        from ai.defaults import DEFAULT_PROFILE_ID
        token, csrf = self.login("admin", "admin-password")
        self.hub.accounts.create_user("alice", "alice-password")
        user, user_csrf = self.login("alice", "alice-password")
        path = "/api/admin/settings"
        form = {"base_url": "https://site.example/v1", "model": "test", "api_key": "private-key"}
        self.assertEqual(self.request("GET", path)[0], 401)
        self.assertEqual(self.request("GET", path, cookie=user)[0], 403)
        self.assertEqual(self.request("POST", path, {"default_model": form}, cookie=user, csrf=user_csrf)[0], 403)
        self.assertEqual(self.request("POST", path, {"default_model": form}, cookie=token)[0], 403)
        before = self.hub.default_model()
        for invalid in ([], "x", {}, dict(form, model=" "), dict(form, model=12), dict(form, api_key=None),
                        dict(form, base_url="http://example.com/v1"), dict(form, base_url="https://example.com/v1?key=secret")):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.request("POST", path, {"default_model": invalid, "max_jobs": 2}, cookie=token, csrf=csrf)[0], 400)
                self.assertEqual(self.hub.default_model(), before)
                self.assertEqual(self.hub.default_job_limit(), 4)
        for suffix, body in (("", form), ("/delete", {})):
            self.assertEqual(self.request("POST", "/api/settings/models/" + DEFAULT_PROFILE_ID + suffix,
                                          body, cookie=user, csrf=user_csrf)[0], 400)
        # Reading a failed save never creates a site secret or replaces the built-in fallback.
        self.assertFalse(self.hub.site_store.path.exists())

    def test_login_cookie_csrf_and_logout(self):
        status, _, token, header = self.request("POST", "/api/auth/login", {"username": "ADMIN", "password": "admin-password"})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", header)
        self.assertIn("SameSite=Lax", header)
        me = self.request("GET", "/api/auth/me", cookie=token)[1]
        self.assertEqual(me["user"]["role"], "admin")
        self.assertEqual(self.request("POST", "/api/auth/logout", {}, cookie=token)[0], 403)
        self.assertEqual(self.request("POST", "/api/auth/logout", {}, cookie=token, csrf=me["csrf"])[0], 200)
        self.assertEqual(self.request("GET", "/api/state", cookie=token)[0], 401)

    def test_repeated_failures_lock_the_login(self):
        for _ in range(5):
            self.assertEqual(self.request("POST", "/api/auth/login", {"username": "admin", "password": "nope"})[0], 401)
        self.assertEqual(self.request("POST", "/api/auth/login", {"username": "admin", "password": "admin-password"})[0], 429)

    def test_invite_registration_is_single_use(self):
        token, csrf = self.login("admin", "admin-password")
        code = self.request("POST", "/api/admin/invites", {"days": 3}, cookie=token, csrf=csrf)[1]["code"]
        status, payload, new_token, _ = self.request("POST", "/api/auth/register",
                                                     {"invite": code.lower(), "username": "alice", "password": "alice-password"})
        self.assertEqual((status, payload["user"]["role"]), (200, "user"))
        self.assertTrue(new_token)
        again = self.request("POST", "/api/auth/register", {"invite": code, "username": "bob", "password": "bob-password"})
        self.assertEqual(again[0], 400)
        invites = self.request("GET", "/api/admin/invites", cookie=token)[1]["invites"]
        self.assertEqual(invites[0]["state"], "used")

    def test_last_seen_counts_cookie_visits_not_only_password_logins(self):
        token, csrf = self.login("admin", "admin-password")
        code = self.request("POST", "/api/admin/invites", {"days": 3}, cookie=token, csrf=csrf)[1]["code"]
        alice = self.request("POST", "/api/auth/register",
                             {"invite": code, "username": "alice", "password": "alice-password"})[2]
        self.request("GET", "/api/auth/me", cookie=alice)
        seen = {u["username"]: u["last_login"] for u in self.request("GET", "/api/admin/users", cookie=token)[1]["users"]}
        self.assertIsNotNone(seen["alice"])

    def test_users_cannot_see_each_others_data(self):
        self.hub.accounts.create_user("alice", "alice-password")
        self.hub.accounts.create_user("bob", "bob-password")
        alice, alice_csrf = self.login("alice", "alice-password")
        bob, _ = self.login("bob", "bob-password")
        status = self.request("POST", "/api/settings/models", {"provider_name": "Alice 私有", "base_url": "https://a.example/v1",
                                                               "model": "m", "api_key": "sk-alice-secret-0001"},
                              cookie=alice, csrf=alice_csrf)[0]
        self.assertEqual(status, 200)
        alice_models = [m["provider"] for m in self.request("GET", "/api/settings", cookie=alice)[1]["models"]]
        bob_models = [m["provider"] for m in self.request("GET", "/api/settings", cookie=bob)[1]["models"]]
        self.assertIn("Alice 私有", alice_models)
        self.assertNotIn("Alice 私有", bob_models)
        uids = {u["username"]: u["id"] for u in self.hub.accounts.users()}
        self.assertNotEqual(self.hub.app(uids["alice"]).store.directory, self.hub.app(uids["bob"]).store.directory)
        self.assertEqual(self.request("GET", "/api/admin/users", cookie=bob)[0], 403)

    def test_user_settings_are_encrypted_on_disk(self):
        self.hub.accounts.create_user("alice", "alice-password")
        alice, csrf = self.login("alice", "alice-password")
        self.request("POST", "/api/settings/models", {"provider_name": "私有", "base_url": "https://a.example/v1",
                                                      "model": "m", "api_key": "sk-alice-secret-0001"}, cookie=alice, csrf=csrf)
        files = list((self.hub.data / "users").rglob("settings*"))
        self.assertEqual([f.name for f in files], ["settings.enc"])
        self.assertNotIn("sk-alice-secret", files[0].read_text())
        self.assertEqual(oct(files[0].stat().st_mode & 0o777), "0o600")

    def test_audit_log_records_sign_ins_and_admin_actions_without_secrets(self):
        self.request("POST", "/api/auth/login", {"username": "admin", "password": "not-it"})
        token, csrf = self.login("admin", "admin-password")
        self.request("POST", "/api/admin/invites", {"days": 1}, cookie=token, csrf=csrf)
        lines = [json.loads(l) for l in (self.hub.data / "audit.log").read_text().splitlines()]
        self.assertEqual([(l["action"], l["ok"]) for l in lines], [("login", False), ("login", True), ("admin:invites", True)])
        self.assertNotIn("not-it", (self.hub.data / "audit.log").read_text())
        self.assertEqual(oct((self.hub.data / "audit.log").stat().st_mode & 0o777), "0o600")
        status, _, _, _ = self.request("GET", "/api/mode")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/mode", headers={"Host": "127.0.0.1:%d" % self.port})
        self.assertEqual(conn.getresponse().getheader("X-Frame-Options"), "DENY")
        conn.close()

    def test_disabled_user_is_signed_out_immediately(self):
        uid = self.hub.accounts.create_user("alice", "alice-password")
        alice, _ = self.login("alice", "alice-password")
        token, csrf = self.login("admin", "admin-password")
        self.assertEqual(self.request("POST", "/api/admin/users/%s/disable" % uid, {}, cookie=token, csrf=csrf)[0], 200)
        self.assertEqual(self.request("GET", "/api/state", cookie=alice)[0], 401)
        self.assertEqual(self.request("POST", "/api/auth/login", {"username": "alice", "password": "alice-password"})[0], 403)
        self.assertEqual(self.request("POST", "/api/admin/users/%s/disable" % self.admin_id, {}, cookie=token, csrf=csrf)[0], 400)

    def test_oauth_callback_nonce_is_single_use_and_bound_to_its_user(self):
        url = self.hub.oauth_url(self.admin_id, "mooc", here=True)
        self.assertIn("redirect=http%3A%2F%2F127.0.0.1", url)
        nonce = url.rsplit("%2F", 1)[1]
        with patch.object(Studia, "finish_browser_login") as finish:
            status, page, _, _ = self.request("GET", "/oauth/callback/%s?token=abc" % nonce)
            self.assertEqual(status, 200)
            self.assertNotIn("abc", page)
            self.assertIn("url=http://127.0.0.1", page)  # back to Studia by itself: WeChat has no tab to close
            self.assertIn("#/login/mooc", page)
            for _ in range(50):
                if finish.called:
                    break
                time.sleep(0.01)
            finish.assert_called_once_with("mooc", "abc")
            self.assertEqual(self.request("GET", "/oauth/callback/%s?token=abc" % nonce)[0], 400)
        other = self.hub.accounts.create_user("alice", "alice-password")
        alice, _ = self.login("alice", "alice-password")
        nonce = self.hub.oauth_url(other, "mooc").rsplit("%2F", 1)[1]
        admin, _ = self.login("admin", "admin-password")
        self.assertEqual(self.request("GET", "/oauth/callback/%s?token=abc" % nonce, cookie=admin)[0], 400)

    def test_oauth_callback_in_a_tab_of_its_own_leaves_studia_to_the_tab_that_opened_it(self):
        nonce = self.hub.oauth_url(self.admin_id, "mooc").rsplit("%2F", 1)[1]
        with patch.object(Studia, "finish_browser_login"):
            status, page, _, _ = self.request("GET", "/oauth/callback/%s?token=abc" % nonce)
        self.assertEqual(status, 200)
        self.assertNotIn("http-equiv=refresh", page)  # it would turn the SSO tab into a second Studia
        self.assertNotIn("返回 Studia", page)
        self.assertIn("可以关闭这个页面", page)

    def test_login_start_records_whether_the_page_goes_to_the_sso_itself(self):
        token, csrf = self.login("admin", "admin-password")
        for body, here in (({"here": True}, True), ({}, False)):
            status, started, _, _ = self.request("POST", "/api/platforms/mooc/login", body, cookie=token, csrf=csrf)
            self.assertEqual(status, 200)
            nonce = started["open"].rsplit("%2F", 1)[1]
            self.assertIs(self.hub.pending_oauth[nonce][3], here)


class IsolationUnitTest(unittest.TestCase):
    def test_log_lines_go_only_to_the_job_thread_owner(self):
        alice, bob = Studia.__new__(Studia), Studia.__new__(Studia)
        for app in (alice, bob):
            app.lines = []
            app.publish = app.lines.append
        handler = _EventLogHandler()
        record = logging.LogRecord("zhs.main", logging.INFO, __file__, 1, "进度", None, None)
        JOBS["a1"] = alice
        try:
            for name in ("studia-job-a1", "studia-job-a1/study_3", "MainThread", "studia-job-b2"):
                record.threadName = name
                handler.emit(record)
        finally:
            JOBS.pop("a1", None)
        self.assertEqual([line["job"] for line in alice.lines], ["a1", "a1"])
        self.assertEqual(bob.lines, [])

    def test_jobs_beyond_the_personal_limit_wait_their_turn(self):
        app = Studia.__new__(Studia)
        app.lock, app.history, app.last, app.events, app.jobs = threading.RLock(), [], {}, [], {}
        app.store, app.closing = None, False
        app.publish = app.events.append
        app.job_limit = lambda: 1
        gate = threading.Event()

        def job(jid, started):
            app.jobs[jid] = {"id": jid, "kind": "study", "title": jid, "course": jid, "course_name": jid, "platform": "zhs",
                             "state": "queued", "summary": "", "started": started, "ended": None, "lines": [],
                             "cancel": threading.Event()}
            with app.lock:
                app._take_turn(app.jobs[jid])
            return app.jobs[jid]

        first, second = job("a", 1), job("b", 2)
        self.assertEqual((first["state"], second["state"]), ("running", "queued"))
        runners = [threading.Thread(target=app._run_job, args=(first, lambda: gate.wait(5) and "完成", None)),
                   threading.Thread(target=app._run_job, args=(second, lambda: "完成", None))]
        for runner in runners:
            runner.start()
        time.sleep(1.3)
        self.assertEqual(second["state"], "queued")
        gate.set()
        for runner in runners:
            runner.join(5)
        self.assertEqual([(e["id"], e["state"]) for e in app.events], [("a", "done"), ("b", "running"), ("b", "done")])

    def test_throttle_window(self):
        throttle = Throttle(limit=2, window=60)
        throttle.fail("k")
        self.assertEqual(throttle.blocked("k"), 0)
        throttle.fail("k")
        self.assertGreater(throttle.blocked("k"), 0)
        throttle.clear("k")
        self.assertEqual(throttle.blocked("k"), 0)

    def test_an_older_database_gains_unique_emails(self):
        with tempfile.TemporaryDirectory() as directory:
            old = web.accounts.sqlite3.connect(os.path.join(directory, "studia.db"))
            old.executescript("CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, "
                              "password TEXT NOT NULL, role TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, created REAL, last_login REAL);"
                              "INSERT INTO users (id, username, password, role) VALUES ('u1', 'old', 'x', 'user'), ('u2', 'other', 'x', 'user');")
            old.close()
            accounts = Accounts(directory)
            self.assertIsNone(accounts.user("u1")["email"])
            accounts.set_email("u1", "Old@Example.com")
            self.assertEqual(accounts.find("old@example.com")["id"], "u1")
            with self.assertRaisesRegex(AccountError, "其他账号"):
                accounts.set_email("u2", "old@example.com")

    def test_accounts_file_is_private(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(web.accounts, "ITERATIONS", 1000):
            accounts = Accounts(directory)
            accounts.create_user("alice", "alice-password")
            self.assertEqual(oct(accounts.path.stat().st_mode & 0o777), "0o600")
            self.assertNotIn(b"alice-password", accounts.path.read_bytes())

    def test_sessions_survive_a_restart_and_json_accounts_migrate(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(web.accounts, "ITERATIONS", 1000):
            legacy = {"users": {"u1": {"username": "alice", "password": web.accounts.hash_password("alice-password"),
                                       "role": "admin", "disabled": False, "created": 1, "last_login": None}},
                      "invites": {"AAAA-BBBB-CCCC": {"created": 1, "created_by": "u1", "expires": 9e9, "used_by": None}}}
            Path(directory, "accounts.json").write_text(json.dumps(legacy))
            accounts = Accounts(directory)
            self.assertEqual(accounts.authenticate("ALICE", "alice-password")["id"], "u1")
            self.assertEqual([i["state"] for i in accounts.invites()], ["open"])
            self.assertTrue(Path(directory, "accounts.json.migrated").exists())
            token = Sessions(accounts).create("u1")
            restarted = Accounts(directory)
            self.assertEqual(Sessions(restarted).get(token)["uid"], "u1")
            with self.assertRaises(AccountError):
                restarted.setup_admin("mallory", "mallory-password")

    def test_encrypted_store_round_trip_and_tamper_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            key = os.urandom(32)
            alice = EncryptedSettingsStore(Path(directory) / "alice", key, "alice")
            alice.set("session_zhs", {"access_token": "secret-cookie"})
            self.assertEqual(alice.session("zhs")["access_token"], "secret-cookie")
            sealed = alice.path.read_text()
            self.assertNotIn("secret-cookie", sealed)
            with self.assertRaises(SettingsError):
                EncryptedSettingsStore(Path(directory) / "alice", os.urandom(32), "alice").session("zhs")
            bob = EncryptedSettingsStore(Path(directory) / "bob", key, "bob")
            bob.path.parent.mkdir()
            bob.path.write_text(sealed)
            with self.assertRaises(SettingsError):
                bob.session("zhs")

    def test_plain_settings_are_migrated_and_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "settings.json").write_text(json.dumps({"version": 1, "concurrency": {"ai": 3, "study": 2}}))
            store = EncryptedSettingsStore(directory, os.urandom(32), "u")
            self.assertEqual(store.concurrency(), {"ai": 3, "study": 2})
            self.assertFalse(Path(directory, "settings.json").exists())
            self.assertTrue(store.path.exists())

    def test_server_refuses_to_start_without_a_valid_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"STUDIA_SECRET_KEY": "short"}):
            self.assertEqual(main(["--data", directory]), 1)
        self.assertEqual(len(load_key("A" * 43)), 32)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keys" / "secret.key"
            first = _key_file(path)
            self.assertEqual((len(load_key(first)), _key_file(path)), (32, first))
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")
        with self.assertRaises(ValueError):
            load_key("")

    def test_answer_memory_is_shared_and_old_user_files_are_merged(self):
        from zhs.answer import prepare
        from zhs.memory import AnswerMemory
        question = prepare({"id": 1, "content": "1+1=?", "questionType": 1,
                            "optionVos": [{"id": 1, "content": "1"}, {"id": 2, "content": "2"}]})
        with tempfile.TemporaryDirectory() as directory:
            legacy = AnswerMemory(Path(directory) / "users" / "u1" / "zhs-answers.json")
            legacy.remember_correct(question, ["2"])
            legacy.save()
            hub = Hub(directory, "http://127.0.0.1:1", key=os.urandom(32))
            self.assertIs(hub.app("u1").memory, hub.app("u2").memory)
            self.assertEqual(hub.app("u2").memory.lookup(question)["correct"], ["2"])
            self.assertFalse(legacy.path.exists())
            self.assertTrue(legacy.path.with_name("zhs-answers.json.merged").exists())

    def test_data_root_is_private(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = Hub(Path(directory) / "data", "http://127.0.0.1:1", key=os.urandom(32))
            self.assertEqual(oct(hub.data.stat().st_mode & 0o777), "0o700")


if __name__ == "__main__":
    unittest.main()


class LogExportTest(unittest.TestCase):
    def test_only_lines_inside_the_window_and_their_tracebacks(self):
        with tempfile.TemporaryDirectory() as directory:
            day = Path(directory) / "icve-ai-assistant-log_2026-11-01.log"
            day.write_text("[2026-11-01 08:00:00,001][1][a.py][line: 1][INFO] :: early\n"
                           "[2026-11-01 09:30:00,001][1][a.py][line: 1][ERROR] :: boom\n"
                           "Traceback (most recent call last):\n"
                           "[2026-11-01 11:00:00,001][1][a.py][line: 1][INFO] :: late\n", encoding="utf-8")
            at = lambda text: time.mktime(time.strptime(text, "%Y-%m-%d %H:%M"))
            text = export_logs(directory, "app", at("2026-11-01 09:00"), at("2026-11-01 10:00"))
            self.assertEqual(text.splitlines(), ["[2026-11-01 09:30:00,001][1][a.py][line: 1][ERROR] :: boom",
                                                 "Traceback (most recent call last):"])
            Path(directory, "audit.log").write_text(
                json.dumps({"time": "2026-11-01 09:15:00", "action": "login"}) + "\n", encoding="utf-8")
            self.assertIn('"login"', export_logs(directory, "audit", at("2026-11-01 09:00"), at("2026-11-01 10:00")))
            self.assertEqual(export_logs(directory, "app", at("2026-11-02 09:00"), at("2026-11-02 10:00")),
                             "这段时间没有日志。\n")


class DailyLogFileTest(unittest.TestCase):
    def test_a_long_running_server_writes_each_day_to_its_own_file(self):
        from core.log import DailyFileHandler
        with tempfile.TemporaryDirectory() as directory:
            cwd = os.getcwd()
            os.chdir(directory)
            try:
                handler = DailyFileHandler()
                handler.setFormatter(logging.Formatter("%(message)s"))
                today = time.time()
                for when, text in ((today, "today"), (today + 86400, "tomorrow")):
                    record = logging.LogRecord("zhs.api", logging.WARNING, __file__, 1, text, None, None)
                    record.created = when
                    handler.handle(record)
                handler.close()
                day = lambda t: time.strftime("%Y-%m-%d", time.localtime(t))
                self.assertEqual(Path("icve-ai-assistant-log_%s.log" % day(today)).read_text().strip(), "today")
                self.assertEqual(Path("icve-ai-assistant-log_%s.log" % day(today + 86400)).read_text().strip(), "tomorrow")
            finally:
                os.chdir(cwd)

    def test_export_finds_lines_an_older_server_left_in_the_previous_days_file(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "icve-ai-assistant-log_2026-11-01.log").write_text(
                "[2026-11-02 00:01:53,616][1][api.py][line: 1][WARNING] :: 智慧树接口失败：POST x\n", encoding="utf-8")
            at = lambda text: time.mktime(time.strptime(text, "%Y-%m-%d %H:%M"))
            self.assertIn("智慧树接口失败", export_logs(directory, "app", at("2026-11-02 00:00"), at("2026-11-02 09:00")))


class LogOwnerTest(unittest.TestCase):
    def test_runtime_log_lines_name_the_user_and_job(self):
        import core.log
        from web.server import JOBS
        with tempfile.TemporaryDirectory() as directory:
            cwd = os.getcwd()
            os.chdir(directory)
            log = logging.getLogger("zhs.owner-test")
            log.setLevel(logging.INFO)
            handler = core.log.DailyFileHandler()
            handler.setFormatter(logging.Formatter("[%(levelname)s]%(who)s :: %(message)s"))
            log.addHandler(handler)
            JOBS["ab12cd34"] = Mock(owner="alice")
            try:
                for name in ("studia-job-ab12cd34/study_0", "MainThread"):
                    worker = threading.Thread(target=log.warning, args=("被拦",), name=name)
                    worker.start()
                    worker.join()
            finally:
                log.removeHandler(handler)
                handler.close()
                JOBS.pop("ab12cd34", None)
                os.chdir(cwd)
            lines = next(Path(directory).glob("*.log")).read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, ["[WARNING][alice/ab12cd34] :: 被拦", "[WARNING] :: 被拦"])
