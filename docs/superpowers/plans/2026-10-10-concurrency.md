# Configurable Concurrency Implementation Plan

> **For agentic workers:** Use test-driven-development for each task. Independent AI and study implementation domains may run in parallel under dispatching-parallel-agents; integration and review follow.

**Goal:** AI 答题与自动学习各自支持 1–8 路并发，默认 1，在设置中修改并持久化；仅本地修改，不推送。

**Architecture:** AI 同卷题目生成并行，试卷队列串行，主流程校验、人工补答、写报告与交卷。学习课程串行、当前课程内资源有界并行，隔离工作线程客户端和状态；主流程汇总。1 路保持现有顺序路径。

**Tech Stack:** Python >=3.9、标准库 concurrent.futures/threading、requests、unittest；不增加依赖。

**Spec:** 用户 2026-10-10 指令与 `docs/research/2026-10-10-concurrency.md`。用户已经要求实施：上限 8、默认 1、设置内调整、不推送。

## Global Constraints

- AI 与学习分开保存 `concurrency: {ai: 1, study: 1}`；只接受整数 1–8，拒绝 bool/浮点/字符串及越界。缺失字段回退 1。
- 旧配置无迁移写入；非法持久配置回退对应默认值，设置保存严格验证，不破坏其他设置。
- 只使用合成题、假传输及临时目录验证，不调用真实平台或模型，不读写真实用户设置。
- 提交只由协调者执行一次，提交未知不重发；低置信度/无效答案仍人工处理或禁止提交。
- 新配置只在下一次操作开始读取，运行中保持快照。
- 不推送、不开 PR；保留本地变更供用户检查。

## Review Focus

- 乱序结果与材料子题仍关联正确题号，不串答案、不丢答案。
- 补答/取消/超时/鉴权失败时停止新派发，晚到结果不能触发交卷。
- 429 和重试不得突破并发上限；请求/session 生命周期有明确归属。
- 学习共享状态不污染，失败响应不计成功，同资源不重复调度。
- 设置持久化/取消/非法值/默认兼容，界面进度单调且准确。

### Task 1: Settings and application integration

Files: `settings.py`, `ui.py`, `app.py`, `tests/test_concurrency_settings.py`, `base/concurrency.py`.

Interfaces: `validate_workers(value) -> int` in base/concurrency.py (ValueError on invalid); `SettingsStore.concurrency() -> {ai:int, study:int}`; `save_concurrency(ai, study)`; `TerminalUI.concurrency_settings(current) -> dict`; `max_workers=1` keyword for AnswerRunner/AIMoocHandler/ZYKMoocHandler.

- [x] RED: default/restart persistence, independent values, 1/8 boundaries, invalid inputs, Esc cancels both fields, settings action and propagation to execution.
- [x] GREEN: implement validation, atomic settings save, settings menu entry and numeric prompts; pass snapshot to each handler.
- [x] Verify: `.venv/bin/python -m unittest tests.test_concurrency_settings tests.test_settings tests.test_course_flow -q`.

### Task 2: AI question concurrency

Files: `ai/runner.py`, `ai/client.py`, optional `ai/concurrency.py`, `tests/test_ai_concurrency.py`.

Consumes `validate_workers`; adds keyword `max_workers=1` to AnswerRunner. Thread-owned AI sessions with fixed config after connection check. Each question generates independently; coordinator preserves report/submission order and manual interaction. Bounded dispatch, no eager submission of all questions. Cancel remaining work before returning/cleanup. Existing single-worker retry behavior remains compatible.

- [x] RED: real overlap at 2/8, max in-flight bound, ordering/subquestions, manual pause/abort, failure stop, single submission, retry bound, timeout.
- [x] GREEN: implement limited AI generation workers and coordinator integration.
- [x] Verify AI tests including existing manual/retry/progress scenarios.

### Task 3: Study resource concurrency

Files: `AIMoocMain/main.py`, `ZYKMoocMain/main.py`, `base/api_client.py`, `base/util.py`, optional `base/study.py`, `tests/test_study_concurrency.py`.

Consumes `validate_workers`; adds keyword `max_workers=1` to both handlers. Courses remain sequential; resources within a course execute with isolated worker state and cloned authenticated sessions (no repeated login). Main thread aggregates outcomes. Bound pending work, deduplicate resources, add timeouts and validate MOOC write business result; never automatically retry a study write.

- [x] RED: resource overlap and 1/8 bounds on both platforms, course isolation, duplicates, business failure, partial failure, request timeout and worker cleanup.
- [x] GREEN: implement bounded resources and HTTP/session safeguards.
- [x] Verify study tests and existing observation/auth tests.

### Task 4: Integration, documentation, review

- [x] Update README/USAGE/DEVELOPMENT with settings, default/max and execution boundaries.
- [x] Run `.venv/bin/python -m unittest discover -s tests -q` and `git -c core.whitespace=cr-at-eol diff --check`.
- [x] Request independent code review, address material findings, rerun affected tests/full suite after changes.
- [x] Report local files, checks and remaining live-platform limits; do not push.

## Execution notes

Local branch `codex/concurrency-settings`; work remains in the current checkout with the existing research note. No worktree needed for this local-only change. Baseline tests and final verification results recorded below as work completes.

Baseline: 248 tests passed. Settings/application checks: 60 passed. AI added 12 concurrency checks; study added 20; settings added 9. Integrated suite reported 289 passed before independent review.

Ruling: AI uses bounded batch windows rather than continuous replenishment, so manual input never overlaps fresh dispatch. The maximum is honored but a slow question can hold the batch. Study clones authenticated sessions on the coordinator before dispatch, keeping directory reads separate from copying session state. Existing CRLF files retain their line endings; whitespace verification explicitly permits CR at EOL without changing Git configuration.

Final review: one P2 found and fixed — a final 429/503 now extends the shared cooldown before retry exhaustion is raised. Regression covers the next HTTP request waiting until virtual time 403 instead of 103. Reviewer independently re-ran 13 AI concurrency tests and found no remaining blocking issue. Final full suite: 290 tests passed. No commit, push, PR, real platform write or real model request was performed.
