# 开发与目录说明

[返回项目首页](../README.md)

## 目录

| 路径 | 用途 |
| --- | --- |
| `StartWork.py` | 版本识别、程序入口与退出处理 |
| `app.py` | 登录、课程选择、学习/导出/AI 的流程编排 |
| `course_flow.py` | 课程工作区导航、返回状态、执行摘要和连续操作 |
| `ui.py` | Rich 页面、输入、动态进度、日志面板与结束总结 |
| `checklist.py` | prompt_toolkit 多选列表：方向键、空格、All、确认和刷新 |
| `theme.py` | 颜色、图标、边框、刷新频率和面板尺寸 |
| `reporting.py` | 业务进度事件与回调适配，不依赖 Rich |
| `settings.py` | 仓库外的用户配置、原子写入、平台令牌与 AI 配置持久化 |
| `base/auth.py` | 有超时且禁止重定向的只读认证检查；区分 401 与网络/服务异常 |
| `AIMoocMain/` | 当前 MOOC 平台接口、学习管理、题目导出与交卷协议 |
| `ai/` | AI 服务配置、题型处理、答题与交卷流程 |
| `ZYKMoocMain/` | 资源库平台接口与学习管理 |
| `base/` | 共用 API 客户端与工具 |
| `NewMoocMain/` | 当前仍在使用的 OAuth 登录，以及兼容代码 |
| `NewMoocMain/oauth_pages.py` | 浏览器登录回调的成功、等待、失败与 404 页面；纯内联资源，不接收令牌 |
| `MoocMain/` | 共用日志模块，以及保留的旧平台代码 |
| `tools/` | 开发、排查用的辅助脚本 |
| `tests/` | 离线自动化测试 |
| `assets/` | 应用图标 |
| `docs/` | 当前使用指南、开发说明与接口说明 |
| `docs/legacy/` | 上游旧教程及截图，仅供历史参考 |
| `.github/` | 测试、打包、发布工作流与脚本 |
| `StartWorkLite.spec` | Windows PyInstaller 打包配置，从仓库根目录调用 |

`MoocMain/`、`NewMoocMain/` 仍被当前入口引用，不能仅凭名称删除。运行命令均从仓库根目录执行。

## 辅助工具

```bash
python -m tools.list_structure "课程名称关键词"
```

工具会打开浏览器登录，读取匹配课程的资源目录，并保存到 `exports/structure/`。该目录已加入忽略规则。

离线预览选择页与运行区域：

```bash
python -m tools.ui_demo
python -m tools.ui_demo exports/ui-preview.html
```

第二条命令生成可用浏览器查看的静态 HTML 样例，保留运行中画面便于检查布局；正常运行会清除动态区域。

## 界面与业务边界

业务模块使用标准 logging 记录消息，通过可选 `on_progress(ProgressEvent)` 报告开始、总数增长、当前任务和结果。AI runner 另支持 `on_log`（旧 `output` 参数仍兼容）。回调错误被隔离，不影响请求与交卷。界面订阅日志和事件，不通过匹配日志文字推断成功。

新增终端显示与输入放在 `ui.py`，样式放在 `theme.py`；业务模块不直接调用 `print` / `input`。`TerminalUI.session()` 管理日志订阅，`activity()` 管理可清除的动态区域。主流程在动态区域之外提问；旧脚本输入适配器会暂停动态显示再读取输入。文件日志独立保留。

`Application` 可注入 `SettingsStore`，测试使用临时目录或 Mock，不能触碰真实用户配置。平台客户端接收关键字参数 `access_token` 时只验证账号，不再兑换 SSO 令牌；主流程使用严格模式读取课程。只有明确的认证过期会触发重新登录，恢复逻辑只覆盖执行任务前的只读操作，不重试答题或提交。

AI 配置与连接健康状态独立保存；健康记录绑定 endpoint、模型和 Key 的指纹，配置变化后失效。`verify_ai()` 发送固定的合成题验证连接和答案格式，必须先于读取平台试卷。单题生成中，`AITransientServiceError`（网络、408/429、5xx）和 `AIResponseError`（响应格式异常）允许最多 2 次重试，间隔 1、2 秒，每次请求前检查时限。重试耗尽、答案无效或低置信度时，runner 调用 `manual_answer(question, reason)`；返回有效答案后标记来源为 manual，返回 None 则保存 paused 并停止队列。未注入交互回调时保留原有 ai_error / needs_review 行为。鉴权错误不交给人工补题；低置信度不靠重复生成抬高。平台读取、计时、交卷不由此重放，错误信息不包含 Key 或服务商原始响应。

补答前写入 pending_manual 检查点，输入时 UI 暂停 Rich Live，平台计时继续。人工答案先校验并落盘，再检查时限决定能否继续。`ai/answer_cache.py` 按题目身份、题干、选项、题型和父题材料指纹匹配已存答案；旧报告仅允许题干、选项和编码记录全部一致的独立题复用。尚未处理的旧答案放在 resume_answers，防止在更早的题目暂停时丢失后续缓存。交卷前仍复查平台记录，结果未知的提交不自动重发。

任务列表的列宽由全部行统一计算，按终端字符宽度处理中文，表头固定在滚动区域上方。成绩与次数的单位放在表头，`?` 表示未知、`--` 表示暂无成绩，真实零值必须保留。`task_metrics.py` 只读取平台目录中的成绩和剩余次数，不根据历史记录推算。

`Application.run()` 进入 `CourseWorkspace`：复用当前客户端和课程，按课程导航，执行结束后留在结果页。`Back` 表示返回上层，`Cancelled` 表示退出；二者不可混用。交互终端中的多选调用 `checklist.choose_many()`：返回原列表索引、光标和动作，状态持久化交由 `TerminalUI` 与工作区处理；刷新后按任务稳定标识恢复勾选。无 TTY 或注入行输入时沿用编号模式。摘要中的自动交卷只属于当次操作。导出器的 `selected_papers` 是精确 `(course, item, category)` 列表；传入空列表必须不导出，不能退回全量目录。`None` 保留旧调用方式。

OAuth 回调使用 `ThreadingHTTPServer` 和有限的连接读取超时：浏览器预连接可能不发送 HTTP 请求，不能让它占住唯一处理线程或阻塞关闭。登录方法统一在 `finally` 清理服务器，包括 Ctrl+C；不再由回调额外启动关闭定时器。回归测试覆盖“已收到令牌但仍有空连接”这一退出阻塞场景。

进度行使用 ASCII spinner 与单列宽的进度条字符，避免 macOS 终端字体把 Braille / 粗线字符显示成双列宽后，Rich 回退行数不足、每次刷新留下残影。相关显示选项集中在 `theme.py`。

## 本地文件

`tiku/`、`ai_results/`、`exports/`、`*.log`、`.venv/` 和密钥配置文件不会提交。整理目录不会清理这些已有文件。

## 验证与实际限制


```bash
python -m unittest discover -s tests -v
```

测试覆盖 AI 服务菜单、选项编号映射、判断/填空、子题、低置信度、漏答、接口失败、未知响应、重复交卷防护和 Markdown / Word 导出，以及 8 行日志、长中文截断、搜索翻页、取消清理、回调异常隔离和真实结果统计。GitHub Actions 配置为在 Python 3.9、3.12 上运行测试。

交卷编码和字段基于平台 2026-10-10 的公开网页代码核对，详见 [接口说明](EXAM_PROTOCOL.md)。2026-10-10 经用户授权，对一份 34 题的真实测验完成 AI 答题、交卷、记录确认和成绩回读：平台返回 92.5 分，剩余次数从 9999 减为 9998。该验证只覆盖这一份测验；平台接口变更或服务商差异可能需要继续适配。不能保证答案正确、获取全部答案或完成全部课程要求。
