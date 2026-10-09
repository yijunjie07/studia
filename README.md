# ICVE AI Assistant · 智慧职教 AI 助手

智慧职教常规 MOOC / AI 优课的课程管理、题目导出和 AI 答题工具。

当前维护者：[yijunjie07](https://github.com/yijunjie07) · [使用指南](docs/USAGE.md) · [开发与目录说明](docs/DEVELOPMENT.md) · [接口说明](docs/EXAM_PROTOCOL.md)

## 功能

| 启动菜单 | 功能 |
| --- | --- |
| 1. 学习管理 | 登录后读取课程，按编号选择单门、多门或全部，再处理学习进度 |
| 2. 导出题目 | 作业、测验、考试导出为 Markdown / Word；包含平台返回的答案，可选自己的历史答案 |
| 3. AI 答题 | 自定义 OpenAI 兼容服务 / DeepSeek；选择课程与具体任务，生成本地报告或自动交卷 |

AI 答题及题目导出支持 `ai.icve.com.cn`，资源库当前支持学习管理。含音频、图片、附件的题目仍需人工处理；不能保证答案正确或完成全部课程要求。

## 安装与启动

建议 Python 3.10–3.12，最低 Python 3.9。

```bash
git clone https://github.com/yijunjie07/icve-ai-assistant.git
cd icve-ai-assistant
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python StartWork.py
```

Windows 激活命令为 `.venv\Scripts\activate`。使用 uv 时执行 `uv sync --locked`、`uv run StartWork.py`。Mac 自带 Python 3.9 的 LibreSSL 兼容依赖已包含在安装配置中。

浏览器完成登录后回到终端，按编号选择课程：`2` 选择第 2 门，`1,3` 选择两门，`1-3` 选择连续三门，`all` 选择全部，直接回车取消。更新代码后需要退出旧程序再启动。

AI 服务在运行时配置：自定义接口填写 URL、Key、Model；DeepSeek 填写 Key 并选择模型。Key 隐藏输入，仅保存在本次进程内存中。

## 文件在哪里

| 内容 | 本地位置 |
| --- | --- |
| 导出的题目与平台答案 | `tiku/<课程名>/` |
| AI 答案与执行报告 | `ai_results/<课程名>/` |
| 课程结构导出 | `exports/structure/` |

导出功能不调用 AI。“我的答案”来自当前账号的已有作答记录。具体操作、自动交卷条件及异常恢复方式见 [使用指南](docs/USAGE.md)。这些本地结果、日志和密钥文件已由 Git 忽略。

## 来源与致谢

本仓库由 **yijunjie07** 维护，是基于以下项目与贡献继续开发的版本：

- 基础代码：[11273/mooc-work-answer](https://github.com/11273/mooc-work-answer)，感谢原项目作者及历任贡献者。整理时的上游基线为 `aa87320f6cda73a8ed363dd1e4e3cb6fe4b9c61b`。
- 题目导出：感谢 **tooplick** 的 [PR #198](https://github.com/11273/mooc-work-answer/pull/198)，采用版本为 `a276abd0627f44bc433a4b8d8bc74dc1e44c09ac`。
- 本仓库后续开发：可配置 AI 答题、交卷验证、课程选择及相关测试。新版 AI 模块独立实现，不依赖上游历史版本中缺失的 `AIExamHandler`。

本仓库重新建立了提交历史；GitHub 的贡献者统计只反映新历史，不代表全部源码均由当前维护者原创。保留源码中的原作者署名，旧教程归档在 [docs/legacy](docs/legacy/)。

所采用的上游版本未发现明确的许可证文件。本仓库不对上游代码重新声明许可，使用或再分发前请确认相应授权。
