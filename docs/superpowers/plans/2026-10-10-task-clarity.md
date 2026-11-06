# Version, Study Progress and Attachment Task Clarity

> **For agentic workers:** Apply test-driven-development; independent protocol research and study progress work may proceed in parallel. Preserve the existing uncommitted concurrency implementation.

**Goal:** 更新本地版本到 4.1.0，学习逐资源展示真实处理进度，明确标记并禁用暂不支持的附件作业。

**Architecture:** 课程计数与资源计数分开；统一资源事件由协调者发送。任务能力从平台公开前端验证的目录字段判断；列表保留不可处理项但禁选，全选排除；业务入口再防护，禁止为识别类型打开试卷。

**Tech Stack:** Python 3.9+、Rich、prompt_toolkit、unittest；不增加依赖。

**Spec:** 用户 2026-10-10 两张截图及三项要求；沿用“不推送”。

## Constraints and review focus

- pyproject 和 uv.lock 项目版本同步；源码更新走手动 Git 更新，不自动覆盖本地代码，不发布标签。
- 资源数含去重后的叶资源；进度表示已处理，成功、跳过、失败分开显示；中断不能虚报完成。
- 附件任务字段必须来自平台一手证据；普通题干含附件不等于附件作业，不能按标题猜测。
- 禁选对方向键/空格/All、编号/all、保留选择及刷新均有效；不可选项仍可见原因。
- 防护覆盖 AI 执行、runner 和导出入口；不能调用 attachment paper 或消耗 AI 额度。
- 保留其他本地变更，所有验证离线，不读凭证、不提交平台答案、不推送。

## Tasks

- [x] 同步版本元数据，核对启动来源及使用说明。
- [x] RED/GREEN: Reporter.resources + 学习顺序/并发资源统计和取消测试；UI 独立资源条、百分比与重置测试。
- [x] 核对公开前端附件类型字段，新增 task_capabilities.py 与分类回归测试。
- [x] RED/GREEN: checklist.disabled、UI禁选和业务防护，普通/附件混合列表回归。
- [x] 更新文档、运行全部 unittest 和 CRLF-aware whitespace check；独立审查并修复有效发现。
- [x] 本地保留，不提交、不推送。

## Verification results

- 全量 `.venv/bin/python -m unittest discover -s tests -q`：318 tests，OK。
- `git -c core.whitespace=cr-at-eol diff --check`：通过；两个学习 handler 保留 CRLF。
- 源码入口 `APP_VERSION` 和 uv.lock 自身项目版本一致为 4.1.0；源码发布标记保持 False。
- 52、80、120 列离线渲染检查：资源分数、百分比和独立换行结果统计可读；原生键盘选择验证全选排除附件。
- 独立审查发现并修复 Ctrl+C 虚增资源完成数；两个平台、并发 1/2/8 均有回归覆盖。复核 28 项相关测试通过，无新增实质问题。
- 未读取真实凭证、未向平台或模型提交请求；未提交、未推送。
