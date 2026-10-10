"""All terminal rendering and interaction, including legacy CLI adapters."""
from collections import Counter, deque
from contextlib import contextmanager
from contextvars import ContextVar
import getpass
import logging
import math
import re
import threading
import time

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, ProgressColumn, SpinnerColumn, TimeElapsedColumn
from rich.table import Table, Column
from rich.text import Text

import theme
from reporting import ProgressEvent

_active_ui = ContextVar("active_terminal_ui", default=None)


class Cancelled(Exception):
    """User cancelled configuration; no queued work should begin."""


def safe_text(value):
    # Treat course names, model text and exceptions as literal, untrusted text.
    value = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", str(value))
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return "".join(c for c in value if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))


class CountColumn(ProgressColumn):
    def render(self, task):
        total = "?" if task.total is None else str(int(task.total))
        return Text(f"{int(task.completed)}/{total}", style="muted", no_wrap=True)


class TaskColumn(ProgressColumn):
    def __init__(self):
        super().__init__(table_column=Column(ratio=1, no_wrap=True, overflow="ellipsis"))

    def render(self, task):
        return Text(" ".join(task.description.split()), style="accent", no_wrap=True, overflow="ellipsis")


class UILogHandler(logging.Handler):
    def __init__(self, ui, level):
        super().__init__(level)
        self.ui = ui

    def emit(self, record):
        level = "error" if record.levelno >= logging.ERROR else "warning" if record.levelno >= logging.WARNING else "info"
        # File handlers retain traceback/details; the panel only needs the message.
        self.ui.log(record.getMessage(), level)


class TerminalUI:
    def __init__(self, console=None, input_fn=None, secret_fn=None, dev=False, clock=time.monotonic):
        self.console = console or Console(theme=theme.THEME, highlight=False)
        self.input_fn = input_fn
        self.secret_fn = secret_fn
        self.dev = dev
        self.clock = clock
        self.lines = deque(maxlen=theme.LOG_LINES)
        self.lock = threading.RLock()
        self.live = None
        self.depth = 0
        self.progress = Progress(
            SpinnerColumn(theme.SPINNER, style="accent"), TaskColumn(),
            BarColumn(bar_width=None, style=theme.BAR_STYLE, complete_style=theme.BAR_COMPLETE,
                      finished_style=theme.BAR_FINISHED, table_column=Column(ratio=1)),
            CountColumn(), TimeElapsedColumn(),
            console=self.console, expand=True, auto_refresh=False,
        )
        self.task = self.progress.add_task("准备中", total=None)
        self.counts = Counter()
        self.unit = "项"
        self.started = clock()
        self.finished = False
        self.handler = None
        self.pending_error = ""
        self.cancelled = False
        self.heading = "ICVE AI Assistant"

    @contextmanager
    def session(self):
        self.started = self.clock()
        self.handler = UILogHandler(self, logging.DEBUG if self.dev else logging.INFO)
        root = logging.getLogger()
        previous_level = root.level
        root.setLevel(logging.DEBUG if self.dev else logging.INFO)
        root.addHandler(self.handler)
        token = _active_ui.set(self)
        try:
            yield self
        finally:
            _active_ui.reset(token)
            root.removeHandler(self.handler)
            root.setLevel(previous_level)
            self.handler.close()
            self.handler = None

    def log(self, message, level="info"):
        from MoocMain.log import redact
        with self.lock:
            for line in safe_text(redact(message)).splitlines():
                if line.strip():
                    self.lines.append((line.expandtabs(4), level))
        # Never write outside the dynamic region while a task is running.

    def on_progress(self, event: ProgressEvent):
        with self.lock:
            if event.kind == "begin":
                self.unit = event.unit
                self.progress.reset(self.task, total=event.total, description=safe_text(event.name))
            elif event.kind == "add_total":
                task = self.progress.tasks[0]
                self.progress.update(self.task, total=(task.total or 0) + (event.total or 0))
            elif event.kind == "detail":
                self.progress.update(self.task, description=safe_text(event.name))
            elif event.kind == "result":
                self.counts[event.status] += 1
                self.progress.advance(self.task)
                label = {"success": "成功", "submitted": "已交卷", "preview": "报告已生成",
                         "skipped": "跳过", "needs_review": "待人工处理", "submission_unknown": "交卷结果未知",
                         "submitting": "交卷结果未知", "error": "失败", "cancelled": "中断"}.get(event.status, event.status)
                level = "success" if event.status in ("success", "submitted", "preview") else "warning" if event.status == "skipped" else "error"
                self.log(f"{event.name} · {label}", level)

    def render(self):
        with self.lock:
            rows = list(self.lines)
            # Exactly eight physical rows; no wrapping, even for CJK or long URLs.
            body = Text(no_wrap=True, overflow="ellipsis")
            for index in range(theme.LOG_LINES):
                if index < len(rows):
                    line, level = rows[index]
                    body.append(theme.ICONS.get(level, theme.ICONS["info"]) + " ", style=level)
                    body.append(line, style=level)
                if index < theme.LOG_LINES - 1:
                    body.append("\n")
            panel = Panel(body, title=Text("运行日志 · 最近 8 行", style="muted"),
                          box=theme.BORDER, border_style="border", height=theme.LOG_LINES + 2, padding=(0, 1))
            return Group(self.progress, panel)

    @contextmanager
    def activity(self, name):
        outer = self.depth == 0
        self.depth += 1
        if outer:
            self.progress.reset(self.task, description=safe_text(name), total=None)
            self.live = Live(console=self.console, get_renderable=self.render, transient=True,
                             refresh_per_second=theme.REFRESH_PER_SECOND,
                             auto_refresh=self.console.is_terminal, redirect_stdout=False, redirect_stderr=False)
            self.live.start()
        try:
            yield
        finally:
            self.depth -= 1
            if outer and self.live:
                self.live.stop()
                self.live = None

    def header(self, version):
        self.heading = f"ICVE AI Assistant · {version}"
        self.console.print(Panel(Text.assemble(("ICVE AI Assistant", "title"),
                                              (f"  {version}\n智慧职教 AI 助手", "muted")),
                                 box=theme.BORDER, border_style="border"))
        self.note("按编号选择；q 取消。登录和 AI 配置自动保存，可在「本机设置」修改或清除。")

    def note(self, message, level="muted"):
        if self.live:
            self.log(message, "info" if level == "muted" else level)
        else:
            self.console.print(Text(safe_text(message), style=level))

    def ask(self, prompt, default=None, secret=False):
        if self.live:
            raise RuntimeError("输入必须在动态任务区域之外进行")
        suffix = f" [默认 {default}]" if default is not None else ""
        text = f"{prompt}{suffix} {theme.ICONS['prompt']} "
        if secret:
            value = (self.secret_fn or getpass.getpass)(text)
        else:
            self.console.print(Text(text, style="accent"), end="")
            value = (self.input_fn or input)()
        if not secret and value.strip().lower() == "q":
            raise Cancelled()
        return value.strip() or (str(default) if default is not None else "")

    def table(self, title, columns, rows, help_text=""):
        if self.console.is_terminal:
            self.console.clear()
            self.console.print(Text(self.heading, style="title"))
        table = Table(box=theme.TABLE_BORDER, expand=True, show_edge=False, header_style="muted")
        for i, column in enumerate(columns):
            table.add_column(column, style="accent" if i == 0 else "info",
                             no_wrap=True, overflow="ellipsis", ratio=3 if i == 1 else None)
        for row in rows:
            table.add_row(*(Text(safe_text(value), no_wrap=True, overflow="ellipsis") for value in row))
        self.console.print(Panel(table, title=Text(title, style="title"),
                                 subtitle=Text(help_text, style="muted") if help_text else None,
                                 box=theme.BORDER, border_style="border", padding=(0, 1)))

    def choice(self, title, choices, default=None, help_text=""):
        self.table(title, ["编号", "选项", "说明"],
                   [(str(key), name, description) for key, name, description in choices], help_text)
        values = {str(key): key for key, _, _ in choices}
        while True:
            value = self.ask("选择", default)
            if value in values:
                return values[value]
            self.note("请输入表格中的编号，或 q 取消。", "warning")

    def select(self, title, items, label, details=None, default=None):
        if not items:
            self.note("没有可选择的项目。", "warning")
            return []
        from AIMoocMain.export_questions import parse_index_input
        rows = [(i, label(x), details(x) if details else "") for i, x in enumerate(items, 1)]
        filtered, page = rows, 0
        while True:
            pages = max(1, (len(filtered) + theme.PAGE_SIZE - 1) // theme.PAGE_SIZE)
            self.table(f"{title} · {page + 1}/{pages}", ["编号", "名称", "详情"],
                       filtered[page * theme.PAGE_SIZE:(page + 1) * theme.PAGE_SIZE],
                       "1,3 / 1-3 · all 全部项目 · n/p 翻页 · /关键词搜索 · q 取消")
            self.note("编号始终对应原列表；all 包含全部项目。" +
                      (f" 回车默认 {default}。" if default is not None else " 回车取消。"))
            raw = self.ask("选择编号", default)
            if raw.lower() in ("n", "p"):
                page = min(pages - 1, page + 1) if raw.lower() == "n" else max(0, page - 1)
                continue
            if raw.startswith("/"):
                query = raw[1:].strip().casefold()
                filtered = [row for row in rows if query in (str(row[1]) + " " + str(row[2])).casefold()]
                page = 0
                continue
            if not raw:
                return []
            selected = parse_index_input(raw, len(items))
            if selected:
                self.note(f"已选择 {len(selected)} 项。")
                return [items[index - 1] for index in selected]
            self.note("编号无效，请输入 1、1,3、1-3 或 all。", "warning")

    def courses(self, rows):
        def details(course):
            parts = [str(course.get("courseInfoName") or "")]
            if course.get("studySpeed") is not None:
                parts.append(f"进度 {course['studySpeed']}%")
            return " · ".join(x for x in parts if x)
        return self.select("选择课程", rows, lambda x: x.get("courseName", "未知课程"), details)

    def confirm(self, prompt, default=False):
        while True:
            answer = self.ask(prompt + " [y/n]", "y" if default else "n").lower()
            if answer in ("y", "n"):
                return answer == "y"
            self.note("请输入 y 或 n。", "warning")

    def ai_config(self, current=None):
        from ai.client import AIConfig
        provider = self.choice("AI 服务", [(1, "自定义接口", "兼容 OpenAI Chat Completions"),
                                              (2, "DeepSeek", "填写 Key 并选择模型")],
                               default=2 if current and current.base_url == "https://api.deepseek.com" else 1)
        while True:
            if provider == 1:
                url = self.ask("API Base URL（含 /v1 等服务路径）", current.base_url if current else None)
                model = self.ask("Model ID", current.model if current else None)
            else:
                url = "https://api.deepseek.com"
                default_model = {"deepseek-chat": 1, "deepseek-reasoner": 2}.get(current.model, 3) if current and current.base_url == url else 1
                value = self.choice("DeepSeek 模型", [(1, "deepseek-chat", ""), (2, "deepseek-reasoner", ""),
                                                       (3, "自定义模型", "填写 Model ID")], default=default_model)
                model = {1: "deepseek-chat", 2: "deepseek-reasoner"}.get(value)
                if model is None:
                    model = self.ask("DeepSeek Model ID", current.model if current and current.base_url == url else None)
            reuse_key = current and url.strip().rstrip("/") == current.base_url
            key = self.ask("API Key（隐藏输入，回车保留原 Key）" if reuse_key else "API Key（隐藏输入，将保存到本机）", secret=True)
            if not key and reuse_key:
                key = current.api_key
            try:
                return AIConfig(url, model, key)
            except ValueError as exc:
                self.note(str(exc), "warning")

    def confidence(self, default=0.8):
        if not isinstance(default, (int, float)) or not math.isfinite(default) or not 0 <= default <= 1:
            default = 0.8
        while True:
            try:
                value = float(self.ask("最低置信度（0–1，模型自报值不代表正确率）", str(default)))
                if math.isfinite(value) and 0 <= value <= 1:
                    return value
            except ValueError:
                pass
            self.note("请输入 0 到 1 之间的数字。", "warning")

    def finish(self):
        from MoocMain.log import redact
        if self.finished:
            return
        self.finished = True
        success = sum(self.counts[s] for s in ("success", "submitted", "preview"))
        failures = sum(self.counts[s] for s in ("error", "needs_review", "submission_unknown", "submitting"))
        # Fatal errors before any task result must still be visible in the one-line summary.
        if self.pending_error:
            failures += 1
        elapsed = max(0, int(self.clock() - self.started))
        text = f"成功 {success} · 失败 {failures} · 总用时 {elapsed // 60:02d}:{elapsed % 60:02d}"
        if self.counts["skipped"]:
            text += f" · 跳过 {self.counts['skipped']}"
        if self.counts["needs_review"]:
            text += f" · 待人工 {self.counts['needs_review']}"
        unknown = self.counts["submission_unknown"] + self.counts["submitting"]
        if unknown:
            text += f" · 结果未知 {unknown}（先核对平台）"
        if self.cancelled:
            text += " · 已取消"
        if self.pending_error:
            text += " · " + " ".join(safe_text(redact(self.pending_error)).split())
        style = "error" if failures else "warning" if self.cancelled else "success"
        self.console.print(Text(text, style=style, no_wrap=True, overflow="ellipsis"))

    def home(self, platform_default=0):
        mode = self.choice("1 / 选择功能", [
            (1, "学习管理", "选择课程，处理学习进度"),
            (2, "题目导出", "Markdown / Word，包含平台已有答案"),
            (3, "AI 答题", "生成答案报告，可自动交卷"),
            (4, "本机设置", "修改模型配置、清除 Key、退出登录"),
        ], default=1)
        platform = 0
        if mode == 1:
            platform = self.choice("2 / 选择平台", [
                (0, "常规 MOOC / AI 优课", "ai.icve.com.cn"),
                (1, "资源库", "zyk.icve.com.cn"),
            ], default=platform_default if platform_default in (0, 1) else 0)
        elif mode != 4:
            self.note("平台：常规 MOOC / AI 优课")
        return mode, platform

    def login_hint(self):
        self.note("接下来在浏览器登录，支持扫码或短信；完成后自动返回。")
        self.ask("回车打开浏览器，q 取消")

    def export_settings(self, defaults=None):
        defaults = defaults if isinstance(defaults, dict) else {}
        fmt = self.choice("导出 / 文件格式", [(1, "Markdown", ".md"), (2, "Word", ".docx"),
                                                   (3, "两种都导出", ".md + .docx")],
                          default={"md": 1, "docx": 2, "both": 3}.get(defaults.get("export_format"), 1))
        include = self.confirm("包含我的历史答案", default=defaults.get("include_my_answer") is True)
        saved_categories = defaults.get("category_ids")
        category_default = next((key for key, value in ((0, [1, 2, 3]), (1, [1]), (2, [2]), (3, [3])) if value == saved_categories), 3)
        category = self.choice("导出 / 题目范围", [(0, "全部", "作业、考试、测验"),
                                                        (1, "作业", ""), (2, "考试", ""),
                                                        (3, "章节测验", "")], default=category_default)
        mode = "per_chapter"
        if category in (0, 3):
            selected = self.choice("导出 / 测验组织方式", [(1, "手动选择", "选择具体章节测验"),
                                                              (2, "每章一个文件", "导出全部章节"),
                                                              (3, "合并一个文件", "按课程合并全部章节")],
                                   default={"single": 1, "per_chapter": 2, "merged": 3}.get(defaults.get("quiz_mode"), 2))
            mode = {1: "single", 2: "per_chapter", 3: "merged"}[selected]
        return {"export_format": {1: "md", 2: "docx", 3: "both"}[fmt],
                "include_my_answer": include, "category_ids": [1, 2, 3] if category == 0 else [category],
                "quiz_mode": mode}

    def quizzes(self, catalog):
        return self.select("选择章节测验", catalog, lambda x: x["paper_name"],
                           lambda x: x["course"], default="all")

    def categories(self):
        from AIMoocMain.export_questions import CATEGORY_FALLBACK
        return self.select("AI / 题目范围", [1, 2, 3], lambda x: CATEGORY_FALLBACK[x])

    def papers(self, catalog):
        from AIMoocMain.export_questions import CATEGORY_FALLBACK, paper_display_name
        return self.select("AI / 选择具体任务", catalog, lambda x: paper_display_name(x[1]),
                           lambda x: f"{x[0].get('courseName', '')} · {CATEGORY_FALLBACK[x[2]]}")

    def answer_settings(self, confidence_default=0.8):
        mode = self.choice("AI / 执行方式", [(1, "仅生成答案报告", "不保存到平台，不交卷"),
                                                  (2, "答题并自动交卷", "全部题目通过校验后提交")], default=1)
        return mode == 2, self.confidence(confidence_default)

    def settings_menu(self, path):
        return self.choice("本机设置", [
            (1, "配置 AI 服务", "修改 URL / 模型 / Key；同一 URL 下回车保留 Key"),
            (2, "清除 AI 配置", "删除已保存的 URL、模型和 Key"),
            (3, "退出 MOOC 登录", "下次打开浏览器重新登录，可切换账号"),
            (4, "退出资源库登录", "不影响 MOOC 登录"),
            (0, "返回", "回到功能选择"),
        ], default=0, help_text=f"配置含凭证，请勿分享：{path}")

    def plan(self, name, courses, options=None):
        self.note(f"准备开始：{name} · {len(courses)} 门课程", "accent")
        if options:
            self.note("输出位置：tiku/<课程名>/；答案来自平台，不调用 AI。")

    def ai_plan(self, selected, auto_submit):
        self.note(f"准备开始：{len(selected)} 份任务 · " + ("通过校验后自动交卷" if auto_submit else "只生成本地报告"), "accent")
        self.note("题干和选项会发送给所选 AI 服务。打开试卷可能创建作答记录或开始计时。")
        self.note("报告位置：ai_results/<课程名>/；已提交或状态未知的任务不会重新交卷。")


# Compatibility entry points for standalone scripts. All direct input lives here.
def legacy_input(prompt=""):
    ui = _active_ui.get()
    live = ui.live if ui else None
    if live:
        live.stop()
    try:
        return (ui.input_fn if ui and ui.input_fn else input)(prompt)
    finally:
        if live:
            live.start()


def run_console_tool(operation, name, view=None):
    """Attach the shared renderer to older standalone diagnostic entry points."""
    view = view or TerminalUI()
    with view.session():
        try:
            with view.activity(name):
                view.on_progress(ProgressEvent("begin", name, total=1))
                result = operation()
                view.on_progress(ProgressEvent("result", name, status="error" if result is False else "success"))
                return result
        except (Cancelled, KeyboardInterrupt, EOFError):
            view.cancelled = True
        except Exception as exc:
            from MoocMain.log import Logger
            Logger(__name__).get_log().exception("工具运行失败")
            view.pending_error = str(exc)
        finally:
            view.finish()


def prompt_ai_config(input_fn=None, secret_fn=None, output=None):
    """Keep the former injectable configuration API for library callers/tests."""
    from ai.client import AIConfig
    read = input_fn or input
    secret = secret_fn or getpass.getpass
    emit = output or TerminalUI().note
    emit("AI 服务：1. 自定义 OpenAI 兼容接口  2. DeepSeek")
    while True:
        provider = read("请选择 [1/2]（默认1）: ").strip() or "1"
        if provider in ("1", "2"):
            break
        emit("请输入 1 或 2")
    while True:
        if provider == "1":
            url = read("API Base URL（含服务所需的 /v1 等路径）: ").strip()
            model = read("Model ID: ").strip()
        else:
            url = "https://api.deepseek.com"
            emit("模型：1. deepseek-chat  2. deepseek-reasoner  3. 自定义模型 ID")
            choice = read("请选择 [1/2/3]（默认1）: ").strip() or "1"
            if choice not in ("1", "2", "3"):
                emit("请输入 1、2 或 3")
                continue
            model = {"1": "deepseek-chat", "2": "deepseek-reasoner"}.get(choice)
            if model is None:
                model = read("DeepSeek Model ID: ").strip()
        key = secret("API Key（隐藏输入，仅本次运行使用）: ")
        try:
            return AIConfig(url, model, key)
        except ValueError as exc:
            emit(str(exc))


def display_questions(questions, show_options=True):
    from NewMoocMain.icve_exam_parser import get_question_stats
    ui = TerminalUI()
    stats = get_question_stats(questions)
    ui.note(f"题目总数 {stats['total']} · 总分 {stats['total_score']}")
    for q in questions:
        ui.note(f"{q['number']}. {q['text']}（{q['score']} 分）")
        if q['type'] == '填空题':
            ui.note(f"空格数：{q['blank_count']}")
        elif show_options:
            for opt in q.get('options', []):
                ui.note(f"  {opt['label']}. {opt['text']}")


def parser_help():
    TerminalUI().note("职教云考试解析工具\nquestions = parse_exam_questions(html_content)\ndisplay_questions(questions)")


def oauth_diagnostic(login):
    run_console_tool(lambda: bool(login()), "测试浏览器登录")


def confirm_update():
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    try:
        return messagebox.askyesno("更新可用", "检测到新版本，是否下载？")
    finally:
        root.destroy()


def demo(snapshot=None):
    """Offline UI preview; no platform, browser login or AI requests."""
    from pathlib import Path
    console = Console(theme=theme.THEME, highlight=False, record=bool(snapshot),
                      width=100 if snapshot else None)
    view = TerminalUI(console=console)
    with view.session():
        view.header("界面预览 · 模拟数据")
        view.table("选择课程 · 1/1", ["编号", "名称", "详情"], [
            ("1", "中外音乐与民族技艺实践", "2026 秋季 · 进度 36%"),
            ("2", "大学英语", "2026 秋季 · 进度 82%"),
            ("3", "计算机应用基础", "2026 秋季 · 进度 100%"),
        ], "1,3 / 1-3 · all 全部项目 · n/p 翻页 · /关键词搜索 · q 取消")
        view.note("以下演示 12 份模拟任务；只保留最近 8 行日志。")

        def step(index):
            view.on_progress(ProgressEvent("detail", f"音乐课程 · 模拟任务 {index + 1}"))
            status = "error" if index == 10 else "skipped" if index == 8 else "success"
            view.on_progress(ProgressEvent("result", f"任务 {index + 1:02d}", status=status))

        if snapshot:
            view.on_progress(ProgressEvent("begin", "音乐课程 · 模拟任务", total=12))
            for index in range(9):
                step(index)
            view.log("长行截断演示：" + "课程资源名称与处理详情 " * 12)
            console.print(view.render())
            for index in range(9, 12):
                step(index)
        else:
            with view.activity("模拟运行"):
                view.on_progress(ProgressEvent("begin", "音乐课程 · 模拟任务", total=12))
                for index in range(12):
                    step(index)
                    view.log("处理详情：" + "课程资源名称 " * 20)
                    time.sleep(0.25)
        view.finish()
    if snapshot:
        path = Path(snapshot)
        path.parent.mkdir(parents=True, exist_ok=True)
        console.save_html(str(path))
