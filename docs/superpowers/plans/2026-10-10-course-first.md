# Course-first Interaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将一次性功能向导改为可连续操作的课程工作区。

**Architecture:** `course_flow.py` 负责课程工作区导航，复用 `Application` 的认证与执行能力；`ui.py` 保持所有终端显示和输入；导出器接收精确选择的课程/任务列表，文件组织独立于选择。

**Tech Stack:** Python 3.9+、Rich、unittest；不新增依赖。

**Spec:** `docs/superpowers/specs/2026-10-10-course-first-design.md`

## Global Constraints

- 保留当前未提交的登录、进度显示及对应测试改动；在当前目录实施，便于直接运行验收。
- 不改变平台协议或提交校验；自动交卷不持久化；所有测试离线。
- b 返回、q 退出；无默认值时回车停留；搜索全选只含匹配项。

## Review Focus

- 空课程/空筛选仍能返回或切换平台，不意外执行全部。
- 返回摘要后保留选择；新的一轮 AI 操作不能沿用自动交卷。
- 退出登录/切换账号必须使内存客户端失效。
- 精确导出不能扩大到未选任务；批量课程有相同试卷 ID 时按课程隔离。
- 结果页与下一轮统计隔离，错误不导致自动重放。

### Task 1: 统一输入和选择

**Files:** `ui.py`, `tests/test_course_flow.py`

**Interfaces:** `Back` 表示返回；`TerminalUI.select(..., multiple=True, actions=None, filters=None, state=None, selected=None)` 支持单选/多选、辅助命令、过滤和保留状态。`library(rows, platform, state)` 返回课程列表或辅助命令。

- [x] 新增搜索全选、空回车、单选、返回、筛选与保留选择测试，先验证失败。
- [x] 实现选择控件及课程列表、课程菜单。
- [x] 运行 `python -m unittest discover -s tests -p 'test_course_flow.py' -v`，预期通过。

### Task 2: 精确导出和执行摘要

**Files:** `AIMoocMain/export_questions.py`, `ui.py`, `tests/test_course_flow.py`, `tests/test_export.py`

**Interfaces:** `QuizExportHandler(..., selected_papers=None)` 接收 `(course, item, category)` 元组列表；摘要编辑只在用户选择设置时展开。

- [x] 新增精确选择、空选择、跨课程隔离和所选内容合并测试，验证失败。
- [x] 实现导出精确列表及独立文件组织；保留旧调用兼容。
- [x] 实现导出/AI 摘要、设置编辑、结果页；验证默认回车不展开配置，自动交卷不沿用。
- [x] 运行导出与交互测试，预期通过。

### Task 3: 课程工作区循环

**Files:** `course_flow.py`, `app.py`, `StartWork.py`, `tests/test_course_flow.py`

**Interfaces:** `CourseWorkspace(application).run()` 管理课程、任务、摘要和结果导航；`Application.client_and_courses(..., choose=False)` 仅认证和读取；`Application.execute_ai(...)` 复用既有队列。

- [x] 用真实 UI 和临时配置、假的外部客户端跑课程优先、连续操作、返回保留、账号失效、异常退出测试，先验证失败。
- [x] 实现工作区循环，提取共用 AI 执行能力，记录每次任务结果与文件路径。
- [x] 运行全套 `python -m unittest discover -s tests -v`，预期零失败。

### Task 4: 文档和界面验收

**Files:** `README.md`, `docs/USAGE.md`, `docs/DEVELOPMENT.md`, `ui.py`

- [x] 更新使用说明及离线演示，使入口、快捷键、结果流程与实现一致。
- [x] 跑离线演示、完整测试及 `git diff --check`；复核实际渲染和窄终端。
- [x] 进行独立代码审阅，修复实质问题，再报告验证结果。

## Execution record

- Baseline: 71 tests passed before implementation.
- 在本会话内连续实施；用户已经认可方案并跳过进一步提问。

- Task 1 complete: selection tests failed on old global-all/empty-enter behavior, then passed with filtered-all, Back, retained choices and single-course entry.
- Task 2 complete: exact/empty/mixed-category exports and per-course merged output verified offline; saved-summary options and explicit auto-submit verified.
- Task 3 complete: startup, repeated operations, logout invalidation, batch selection, empty lists and actual selected-file export covered with scripted real UI and temporary settings.
- Independent read-only review found two important result lifecycle issues. Both fixed with RED→GREEN regression tests: fatal error after a completed operation, and stale reports from unprocessed AI queue items.
- Additional UI checks fixed previous-field navigation in AI configuration, same-name course term details and clipped shortcuts at 52 columns.
- Task 4 complete: README, usage, developer docs and offline preview updated. Final verification: 98 unittest tests passed; compileall and git diff --check passed. 52/80-column output inspected; local HTML browser preview was unavailable due to browser URL policy, so terminal rendering was used for layout verification.
- No real platform/AI requests, no user settings changes, no commits or pushes. Existing local changes remain intact.
