# 开发与目录说明

[返回项目首页](../README.md)

## 目录

| 路径 | 用途 |
| --- | --- |
| `StartWork.py` | 终端入口、登录与课程选择 |
| `AIMoocMain/` | 当前 MOOC 平台接口、学习管理、题目导出与交卷协议 |
| `ai/` | AI 服务配置、题型处理、答题与交卷流程 |
| `ZYKMoocMain/` | 资源库平台接口与学习管理 |
| `base/` | 共用 API 客户端与工具 |
| `NewMoocMain/` | 当前仍在使用的 OAuth 登录，以及兼容代码 |
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

## 本地文件

`tiku/`、`ai_results/`、`exports/`、`*.log`、`.venv/` 和密钥配置文件不会提交。整理目录不会清理这些已有文件。

## 验证与实际限制


```bash
python -m unittest discover -s tests -v
```

测试覆盖 AI 服务菜单、选项编号映射、判断/填空、子题、低置信度、漏答、接口失败、未知响应、重复交卷防护和 Markdown / Word 导出。GitHub Actions 在 Python 3.9、3.12 上运行测试。

交卷编码和字段基于平台 2026-10-10 的公开网页代码核对，详见 [接口说明](EXAM_PROTOCOL.md)。本项目当前新增 AI 交卷流程只经过离线模拟验证，未使用真实账号试交卷；平台接口变更或服务商差异可能需要继续适配。不能保证答案正确、获取全部答案或完成全部课程要求。
