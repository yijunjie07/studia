# ICVE AI Assistant · 智慧职教 AI 助手

智慧职教常规 MOOC / AI 优课的课程管理、题目导出和 AI 答题工具。

当前维护者：[yijunjie07](https://github.com/yijunjie07) · [使用指南](docs/USAGE.md) · [开发与目录说明](docs/DEVELOPMENT.md) · [接口说明](docs/EXAM_PROTOCOL.md)

## 功能

| 课程内操作 | 功能 |
| --- | --- |
| 1. 继续学习 | 处理当前课程的学习进度 |
| 2. 导出题目 | 选择作业、测验、考试，导出 Markdown / Word；可按课程合并所选内容 |
| 3. AI 答题 | 自定义 OpenAI 兼容服务 / DeepSeek；生成本地报告或当次选择自动交卷 |
| 课程列表的 s 设置 | 添加、编辑、切换模型，或退出已保存的平台登录 |

AI 答题及题目导出支持 `ai.icve.com.cn`，资源库当前支持学习管理。含音频、图片、附件的题目仍需人工处理；不能保证答案正确或完成全部课程要求。

## 安装与启动

推荐使用 **uv**，macOS、Windows、Linux 都使用下面这套命令。uv 会管理 Python 和项目依赖，无需手动创建或激活虚拟环境。

### 1. 首次安装

先安装 [Git](https://git-scm.com/downloads) 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，安装后重新打开终端（Windows 使用 PowerShell）。在想存放项目的目录执行：

```bash
git clone https://github.com/yijunjie07/icve-ai-assistant.git
cd icve-ai-assistant
uv sync --locked --python 3.12
uv run StartWork.py
```

首次安装会下载所需的 Python 3.12 和依赖（已有可用版本时复用）。启动后，在浏览器完成平台登录，再回到终端操作。

### 2. 以后启动

在项目目录（包含 `StartWork.py` 的文件夹）打开终端，执行：

```bash
uv run StartWork.py
```

### 3. 更新项目

先退出正在运行的程序，再在项目目录执行：

```bash
git pull --ff-only
uv sync --locked
uv run StartWork.py
```

## 使用

每次启动默认进入 MOOC / AI 优课，自动恢复有效登录，直接显示课程。输入 `2` 进入第 2 门课程，再选择继续学习、导出题目或 AI 答题。任务列表用方向键移动、空格勾选、回车确认，顶部 `All` 可全选或取消全选。`t` 切换平台，`s` 打开设置。

选择页支持 `n/p` 翻页、`/关键词` 搜索，搜索后的 `all` 只选匹配项。`Esc` 返回上一步，`q` 退出；回车仅采用明确显示的默认值。导出和 AI 先选任务，再看执行摘要，回车开始或 `s` 修改设置。AI 默认答题并自动交卷，置信度默认为 **0.8**；全部题目通过校验才交卷，也可切换为仅生成本地答案。已交卷任务可再次选择作答，是否开放由平台决定；上一轮报告会保留。运行时显示进度和最近 8 行日志，结束后保留结果、文件位置和失败原因，可回到当前课程继续操作。无需登录可执行 `uv run python -m tools.ui_demo` 预览界面。

AI 已内置项目提供的**默认供应商**，固定显示在模型列表顶部。新用户无需填写 Key，使用项目共享额度；可用性以供应商和剩余额度为准。已有模型的用户升级后保留当前选择，可随时切换到默认供应商。

要用自己的服务，选择 **＋ 添加模型**，分别填写供应商名称、接口地址、模型名称和 API Key，按 Tab 切换字段，选择 **保存并测试**。模型列表用 ↑↓ 选择、回车启用，按 `e` 编辑自定义模型；可保存多份配置，列表和答题摘要显示供应商名称与模型；旧配置未命名时显示“自定义供应商”。答题摘要按 `m` 直接切换模型，已选任务不变；课程列表的 **s 设置 → 模型配置** 也能打开同一列表。默认供应商不可修改或删除，界面不显示其接口地址。当前仅支持 **OpenAI 兼容的 Chat Completions API**；供应商名称是自定义标签，不会切换接口协议。

配置保存在仓库外的用户目录（macOS / Linux 为 `~/.config/icve-ai-assistant/settings.json`），包含访问令牌和 Key。这是未加密的本地 JSON；macOS / Linux 新建目录权限为 `700`，文件权限为 `600`。不要分享该文件。导出选项和置信度也会保存；每次进入 AI 答题默认答题并自动交卷，可在执行摘要中修改。

## 文件在哪里

| 内容 | 本地位置 |
| --- | --- |
| 导出的题目与平台答案 | `tiku/<课程名>/` |
| AI 答案与执行报告 | `ai_results/<课程名>/` |
| 课程结构导出 | `exports/structure/` |

导出功能不调用 AI。“我的答案”来自当前账号的已有作答记录。具体操作、自动交卷条件及异常恢复方式见 [使用指南](docs/USAGE.md)。这些本地结果、日志和密钥文件已由 Git 忽略。

## 来源与致谢

基于 [11273/mooc-work-answer](https://github.com/11273/mooc-work-answer) 继续开发，由 **yijunjie07** 维护。感谢原作者及贡献者，以及 **tooplick** 的[题目导出贡献](https://github.com/11273/mooc-work-answer/pull/198)。

本仓库重建过提交历史，保留原作者署名；旧教程见 [docs/legacy](docs/legacy/)。

上游未发现明确的许可证，使用或再分发前请确认授权。
