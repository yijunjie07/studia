# 开发与目录说明

[返回项目首页](../README.md)

## 目录

| 路径 | 用途 |
| --- | --- |
| `StartWork.py` | 版本识别、程序入口与退出处理 |
| `app.py` | 登录、课程选择、学习/导出/AI 的流程编排 |
| `ui.py` | Rich 页面、输入、动态进度、日志面板与结束总结 |
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

## 本地文件

`tiku/`、`ai_results/`、`exports/`、`*.log`、`.venv/` 和密钥配置文件不会提交。整理目录不会清理这些已有文件。

## 验证与实际限制


```bash
python -m unittest discover -s tests -v
```

测试覆盖 AI 服务菜单、选项编号映射、判断/填空、子题、低置信度、漏答、接口失败、未知响应、重复交卷防护和 Markdown / Word 导出，以及 8 行日志、长中文截断、搜索翻页、取消清理、回调异常隔离和真实结果统计。GitHub Actions 配置为在 Python 3.9、3.12 上运行测试。

交卷编码和字段基于平台 2026-10-10 的公开网页代码核对，详见 [接口说明](EXAM_PROTOCOL.md)。本项目当前新增 AI 交卷流程只经过离线模拟验证，未使用真实账号试交卷；平台接口变更或服务商差异可能需要继续适配。不能保证答案正确、获取全部答案或完成全部课程要求。
