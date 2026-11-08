# 开发说明

[返回首页](../README.md)

## 目录

| 路径 | 内容 |
| --- | --- |
| `StartWork.py` | 入口：默认终端版，`--web` 本机网页版，`--serve` 服务器模式 |
| `web/` | 网页版：`server.py` 接口、任务队列和事件推送；`hosting.py` 服务器模式（多用户、加密存储、管理接口）；`accounts.py` 账号和邀请码（SQLite）；`static/` 前端，原生 JS/CSS，没有构建步骤 |
| `mooc/` | 智慧职教 MOOC / AI 优课：接口、学习、交卷协议、题目导出、浏览器登录（`oauth_login.py`） |
| `zhs/` | 智慧树：扫码登录、接口加密、学习、答题、答案记忆、滑块验证、问答区（`qa.py`） |
| `ai/` | AI 接口、题目整理、MOOC 答题流程（`runner.py`）、MOOC 答案记忆 |
| `core/` | 公共代码：日志（`log.py`）、本机设置（`settings.py`）、请求客户端、进度事件、任务开放时间和成绩字段 |
| `terminal/` | 终端版界面：流程编排（`app.py`）、页面和键盘控件 |
| `tools/` | 排查用的小脚本 |
| `tests/` | 离线测试，不连平台、不调 AI |
| `docs/EXAM_PROTOCOL.md` | MOOC 交卷接口的字段和编码 |

所有命令都在仓库根目录执行。

## 测试

```bash
uv run python -m unittest discover -s tests
```

CI 在 Python 3.9 和 3.12 上跑测试，再构建 Docker 镜像做一次首次设置的冒烟测试；main 更新后发布镜像到 `ghcr.io/yijunjie07/studia`。

只改前端时不用起后端：在 `web/static` 下运行 `python3 -m http.server 8790`，打开 `http://127.0.0.1:8790/?mock`，接口由 `mock.js` 返回假数据。

## 约定

- **登录只走平台已有的入口**：智慧职教用 `mooc/oauth_login.py`，智慧树用 `zhs/login.py` 扫码。新功能从 `store.session(平台)` 取登录，不要另开浏览器抓 Cookie。
- **平台写入不自动重发**：交卷、学习记录、发帖的结果不确定时，停下来让人去平台核对，不重试。
- **401/403 不等于掉线**：删登录前先用 `signed_in()` 问一次平台。
- **业务代码不直接 print / input**：用 logging 写日志，用 `on_progress(ProgressEvent)` 报进度，界面自己订阅。
- **网页只转发自己认识的日志**：`web/server.py` 的 `_EventLogHandler.PREFIXES` 按日志器名过滤（`zhs.`、`mooc.`、`core.log`、`ai.`），新加的平台目录要加进去，任务日志才会出现在网页上。
- 版本号写在 `pyproject.toml`，改了要同步 `uv.lock`。

## 小工具

```bash
uv run python -m tools.list_structure 课程名关键词   # 导出 MOOC 课程目录到 exports/structure/
uv run python -m tools.ui_demo                       # 不登录预览终端界面
uv run python tools/zhs_captcha_probe.py             # 扫码后逐个接口记录智慧树验证码在哪里出现
```
