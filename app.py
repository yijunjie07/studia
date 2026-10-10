"""Application orchestration. Menus/rendering are provided by the view (ui.py)."""
from MoocMain.log import Logger

from AIMoocMain.api import AIMoocApi
from AIMoocMain.main import AIMoocHandler
from AIMoocMain.exam_api import ExamAPI, ExamError
from AIMoocMain.export_questions import QuizExportHandler, collect_quiz_catalog, paper_display_name
from ZYKMoocMain.api import ZYKMoocApi
from ZYKMoocMain.main import ZYKMoocHandler
from NewMoocMain.oauth_login import oauth_login
from ai.client import AIClient
from ai.runner import AnswerRunner
from reporting import Reporter
from base.auth import AuthenticationExpired, PlatformUnavailable
from settings import SettingsStore, SettingsError

logger = Logger(__name__).get_log()


class Application:
    def __init__(self, view, store=None):
        self.view = view
        self.progress = Reporter(view.on_progress)
        self.store = store if store is not None else SettingsStore()

    def remember(self, operation):
        try:
            operation()
            return True
        except SettingsError as exc:
            self.view.note(str(exc) + "；本次改动未持久化。", "warning")
            return False

    def login(self):
        self.view.login_hint()
        while True:
            try:
                with self.view.activity("等待浏览器登录"):
                    token = oauth_login(timeout=300)
                if token:
                    return "", "", token
                self.view.note("登录失败或超时。", "warning")
            except Exception as exc:
                logger.exception("OAuth 登录异常")
                self.view.note(f"登录失败：{exc}", "error")
            if not self.view.confirm("重试登录", default=True):
                from ui import Cancelled
                raise Cancelled()

    def client_and_courses(self, api_class, login=None):
        platform = "zyk" if api_class is ZYKMoocApi else "mooc"
        saved = self.store.session(platform) if login is None else None
        if saved:
            try:
                with self.view.activity("恢复已保存的登录状态"):
                    client = api_class(access_token=saved["access_token"])
                    rows = self.read_courses(client)
                self.view.note("已复用本机登录状态。")
                return client, self.view.courses(rows)
            except AuthenticationExpired:
                self.store.clear_session(platform)
                self.view.note("保存的登录已过期，请重新登录；成功后自动保存。", "warning")
        username, password, token = (login or self.login)()
        with self.view.activity("读取课程列表"):
            client = api_class(token=token, username=username, password=password)
            if not client.access_token:
                raise PlatformUnavailable("未获取有效的平台登录状态，请重新登录或稍后重试")
            rows = self.read_courses(client)
        self.remember(lambda: self.store.save_session(platform, client))
        return client, self.view.courses(rows)

    @staticmethod
    def read_courses(client):
        result = client.my_course_list(page_size=9999, strict=True)
        if not isinstance(result, dict) or not isinstance(result.get("rows"), list):
            raise PlatformUnavailable("课程列表读取失败，登录缓存未清除，请稍后重试")
        return result["rows"]

    def ai_configuration(self):
        config = self.store.ai_config()
        if config is not None:
            self.view.note(f"使用已保存的 AI：{config.model} · {config.base_url}（可在本机设置修改）")
            return config
        config = self.view.ai_config()
        if self.remember(lambda: self.store.save_ai(config)):
            self.view.note("AI 配置已保存，下次自动使用。")
        return config

    def study(self, version):
        api_class, handler = (ZYKMoocApi, ZYKMoocHandler) if version == 1 else (AIMoocApi, AIMoocHandler)
        client, selected = self.client_and_courses(api_class)
        if not selected:
            self.view.cancelled = True
            return
        self.view.plan("学习管理", selected)
        with self.view.activity("处理课程"):
            handler(client=client, course_rows=selected, on_progress=self.view.on_progress)

    def export(self):
        client, selected = self.client_and_courses(AIMoocApi)
        if not selected:
            self.view.cancelled = True
            return
        options = self.view.export_settings(self.store.get("export", {}))
        self.remember(lambda: self.store.set("export", options))
        selected_ids = []
        if options["quiz_mode"] == "single" and 3 in options["category_ids"]:
            with self.view.activity("读取章节测验"):
                catalog = collect_quiz_catalog(client, selected, category_id=3)
            quizzes = self.view.quizzes(catalog)
            selected_ids = [item["exam_id"] for item in quizzes]
            if not selected_ids and options["category_ids"] == [3]:
                self.view.cancelled = True
                return
        self.view.plan("题目导出", selected, options)
        with self.view.activity("导出题目"):
            return QuizExportHandler(client=client, course_rows=selected,
                                     selected_exam_ids=selected_ids, output_dir="tiku",
                                     dev_mode=self.view.dev, on_progress=self.view.on_progress, **options)

    def ai(self, version=0, login=None):
        if version != 0:
            self.view.note("AI 答题支持常规 MOOC / AI 优课。", "warning")
            return []
        client, courses = self.client_and_courses(AIMoocApi, login)
        if not courses:
            self.view.cancelled = True
            return []
        api = ExamAPI(client)
        categories = self.view.categories()
        if not categories:
            self.view.cancelled = True
            return []
        catalog = []
        with self.view.activity("读取可选任务"):
            for course in courses:
                for category in categories:
                    for item in api.catalog(course, category):
                        catalog.append((course, item, category))
        selected = self.view.papers(catalog)
        if not selected:
            self.view.cancelled = True
            return []
        config = self.ai_configuration()
        auto_submit, threshold = self.view.answer_settings(self.store.get("confidence", 0.8))
        self.remember(lambda: self.store.set("confidence", threshold))
        self.view.ai_plan(selected, auto_submit)
        runner = AnswerRunner(api, AIClient(config), auto_submit=auto_submit,
                              min_confidence=threshold, on_progress=self.view.on_progress)
        results = []
        with self.view.activity("AI 答题"):
            self.progress.begin("AI 答题", len(selected), "份试卷")
            for course, item, category in selected:
                name = paper_display_name(item)
                try:
                    result = runner.run_paper(course, item, category)
                    results.append(result)
                except ExamError as exc:
                    logger.error("任务停止：%s", exc)
                    self.progress.result(name, "error")
                    break
                status = result["status"]
                if runner.reused and status == "submitted":
                    status = "skipped"
                self.progress.result(name, status)
                if result["status"] in ("submission_unknown", "submitting", "error"):
                    logger.warning("队列停止，请检查报告和平台状态。")
                    break
        return results

    def run(self):
        while True:
            mode, platform = self.view.home(self.store.get("platform", 0))
            if mode != 4:
                break
            self.manage_settings()
        if mode == 1:
            self.remember(lambda: self.store.set("platform", platform))
            return self.study(platform)
        if mode == 2:
            return self.export()
        return self.ai(platform)

    def manage_settings(self):
        while True:
            action = self.view.settings_menu(self.store.path)
            if action == 0:
                return
            if action == 1:
                config = self.view.ai_config(self.store.ai_config())
                if self.remember(lambda: self.store.save_ai(config)):
                    self.view.note("AI 配置已保存。")
            elif action == 2:
                if self.remember(lambda: self.store.set("ai", None)):
                    self.view.note("已清除本机 AI 配置。")
            elif action in (3, 4):
                platform = "mooc" if action == 3 else "zyk"
                if self.remember(lambda: self.store.clear_session(platform)):
                    self.view.note("已退出本机保存的登录，下次使用该平台时重新登录。")
