"""Interactive AI workflow; course and paper scope are selected explicitly."""
import math

from AIMoocMain.api import AIMoocApi
from AIMoocMain.exam_api import ExamAPI, ExamError
from AIMoocMain.export_questions import CATEGORY_FALLBACK, paper_display_name, parse_index_input
from ai.client import AIClient, prompt_config
from ai.runner import AnswerRunner


def select_items(items, label):
    for index, item in enumerate(items, 1):
        print("  %s. %s" % (index, label(item)))
    if not items:
        return []
    while True:
        raw = input("选择编号（1,3 / 1-3 / all；直接回车取消）: ").strip()
        if not raw:
            return []
        indexes = parse_index_input(raw, len(items))
        if indexes:
            return [items[i - 1] for i in indexes]
        print("请输入列表内的编号")


def run_ai_menu(version, login):
    if version != 0:
        print("AI 答题目前支持常规 MOOC / AI 优课，请选择平台 0")
        return
    config = prompt_config()
    print("题干与选项会发送给你选择的 AI 服务；平台登录凭证不会发送。")
    username, password, token = login()
    client = AIMoocApi(token=token, username=username, password=password)
    api = ExamAPI(client)
    result = client.my_course_list(page_size=9999)
    courses = result.get("rows", []) if isinstance(result, dict) else []
    print("\n选择要处理的课程（直接选择目标课程，无需排除其他课程）")
    selected_courses = select_items(courses, lambda x: x.get("courseName", "未知课程"))
    if not selected_courses:
        return
    print("\n范围：1. 作业  2. 考试  3. 测验")
    categories = select_items([1, 2, 3], lambda x: CATEGORY_FALLBACK[x])
    if not categories:
        return
    catalog = []
    for course in selected_courses:
        for category in categories:
            for item in api.catalog(course, category):
                catalog.append((course, item, category))
    print("\n选择具体任务（已交卷任务在执行时自动跳过）")
    selected = select_items(catalog, lambda x: "%s / %s / %s" % (x[0].get("courseName", ""), CATEGORY_FALLBACK[x[2]], paper_display_name(x[1])))
    if not selected:
        print("未选择任务")
        return
    while True:
        mode = input("执行方式：1. 仅生成本地答案报告  2. AI 答题并自动交卷（默认1）: ").strip() or "1"
        if mode in ("1", "2"):
            break
    while True:
        try:
            threshold = float(input("最低 AI 置信度 [0-1]（默认0.8；自报置信度不保证正确）: ").strip() or "0.8")
            if math.isfinite(threshold) and 0 <= threshold <= 1:
                break
        except ValueError:
            pass
        print("请输入 0 到 1 之间的数字")
    print("将处理 %s 份任务；%s。打开试卷可能创建作答记录或开始计时。" % (len(selected), "全部题目通过校验后自动交卷" if mode == "2" else "只保存本地报告"))
    runner = AnswerRunner(api, AIClient(config), auto_submit=mode == "2", min_confidence=threshold)
    results = []
    for course, item, category in selected:
        try:
            results.append(runner.run_paper(course, item, category))
        except ExamError as exc:
            print("任务停止：%s" % exc)
            break
        if results[-1]["status"] in ("submission_unknown", "submitting", "error"):
            print("遇到错误或未确认的交卷结果，已停止队列，请检查报告和平台状态。")
            break
    print("\n本次结果：")
    for result in results:
        print("  %s：%s" % (result["paper"], result["status"]))
    return results
