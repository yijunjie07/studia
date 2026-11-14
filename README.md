<h1 align="center">Studia</h1>

<p align="center"><strong>智慧职教与智慧树的课程自动化与 AI 答题工具</strong></p>
<p align="center">Course automation and AI assistance for ICVE and Zhihuishu</p>

<p align="center">
  <a href="#部署"><img src="https://img.shields.io/static/v1?label=Python&amp;message=3.12&amp;color=3776AB&amp;style=for-the-badge&amp;logo=python&amp;logoColor=white" alt="Python: 3.12"></a>
  <a href="#能做什么"><img src="https://img.shields.io/static/v1?label=JavaScript&amp;message=Web%20UI&amp;color=F7DF1E&amp;style=for-the-badge&amp;logo=javascript&amp;logoColor=white" alt="JavaScript: Web UI"></a>
  <a href="#docker推荐"><img src="https://img.shields.io/static/v1?label=Docker&amp;message=AMD64%20/%20ARM64&amp;color=2496ED&amp;style=for-the-badge&amp;logo=docker&amp;logoColor=white" alt="Docker: AMD64 / ARM64"></a>
</p>

<p align="center">
  <a href="docs/DEVELOPMENT.md">开发说明</a> · <a href="docs/EXAM_PROTOCOL.md">接口说明</a> · <a href="https://github.com/yijunjie07/studia/issues">问题反馈</a>
</p>

<p align="center">
  <strong><a href="#能做什么">功能介绍</a> · <a href="#部署">部署安装</a> · <a href="#ai-模型">AI 模型</a> · <a href="#注意">使用须知</a></strong>
</p>

---

提供终端版和网页版，也可部署成多人服务，各账号的数据分别保存。

## 能做什么

| 平台 | 自动学习 | AI 答题 | 其他 |
| --- | --- | --- | --- |
| MOOC / AI 优课（`ai.icve.com.cn`） | 学完全部资源，参与主题讨论、提交课程评价 | 作业、考试、测验 | 导出题目（终端版） |
| 智慧树（`zhihuishu.com`） | 共享课播视频（弹题自动答）、智慧课程完成知识点资源 | 共享课作业和考试、智慧课程作业和考试 | 每日复习、问答区自动回答和提问 |

- AI 答不出、题型不支持时，整份卷子不交，记下是哪题、什么原因。
- 平台公布过的标准答案会记下来，同一门课的其他卷子、其他人再遇到直接用。不同课程之间不共享。
- 服务器模式有账号、邀请码和管理后台，可以给任务排队、调顺序、导出日志。平台登录和 API Key 加密存放。

## 部署

### Docker（推荐）

```bash
mkdir studia && cd studia
curl -fsSLO https://raw.githubusercontent.com/yijunjie07/studia/main/docker-compose.yml
STUDIA_PUBLIC_URL=http://服务器IP:8080 docker compose up -d
docker compose logs studia   # 找到「设置码」
```

1. 浏览器打开 `STUDIA_PUBLIC_URL`，第一次进入要创建管理员：填日志里的设置码、用户名和密码。设置码每次启动都会换，管理员建好后作废。
2. 用管理员登录后，从左下角头像进「管理后台 → 用户」，生成邀请码发给别人注册。

`STUDIA_PUBLIC_URL` 必须和浏览器地址栏完全一致，包括协议、域名或 IP、端口，否则网页会拒绝访问，MOOC 登录也跳不回来。这些变量可以写在同目录的 `.env` 里：

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `STUDIA_PUBLIC_URL` | `http://localhost:8080` | 浏览器访问的地址 |
| `STUDIA_TRUST_PROXY` | `0` | 放在 Nginx、Caddy 等反向代理后面时设为 `1` |
| `STUDIA_SECRET_KEY` | 空 | 主密钥，不填就在数据卷里生成 `secret.key` |
| `TZ` | `Asia/Shanghai` | 日志时区 |

**更新**：`docker compose pull && docker compose up -d`。数据和登录都会保留；正在跑的学习任务重启后会接着学，AI 答题不会自动重跑。镜像跟着 main 自动构建（`ghcr.io/yijunjie07/studia`，支持 amd64 和 arm64），想固定版本就把 `latest` 换成提交的 SHA。

**数据**：都在 Docker 卷 `studia-data` 里。`studia.db` 存账号和共享的答案记忆，`users/` 下是每个人的登录、模型和答题报告，`secret.key` 是主密钥。备份时先 `docker compose stop`，再备份这个卷。

- **主密钥丢了，加密的数据就解不开**，所有人都要重新登录平台、重填 API Key。把 `secret.key` 另外存一份，或者用 `python StartWork.py --serve --gen-key` 生成一个写进 `.env`。
- 智慧树不接受境外网络访问，服务器要放在国内，或者让 `zhihuishu.com` 走国内线路。
- 国内拉 `ghcr.io` 可能很慢，可以给 Docker 配镜像加速。
- 开放到公网时，前面加一层 HTTPS 反向代理，`STUDIA_PUBLIC_URL` 改成 `https://你的域名`，再设 `STUDIA_TRUST_PROXY=1`。

### 不用 Docker

```bash
python StartWork.py --serve --data ~/.studia-hosted --port 8080 --public-url http://127.0.0.1:8080
```

设置码同样打印在终端里。全部选项见 `python StartWork.py --serve --help`。

### 只在自己电脑上用

装好 [Git](https://git-scm.com/downloads) 和 [uv](https://docs.astral.sh/uv/getting-started/installation/)，然后：

```bash
git clone https://github.com/yijunjie07/studia.git
cd studia
uv sync --locked --python 3.12
uv run playwright install --only-shell chromium   # 智慧树验证码和问答区要用
uv run StartWork.py --web
```

浏览器会自动打开网页版，只有本机能访问。去掉 `--web` 进入终端版。更新：`git pull --ff-only && uv sync --locked`。

本机模式的配置在 `~/.config/icve-ai-assistant/settings.json`（Windows 在 `%LOCALAPPDATA%\icve-ai-assistant\`），里面的登录令牌和 Key **没有加密**，不要分享。

## AI 模型

内置一个默认供应商，不填 Key 就能用，用的是项目的共享额度。想用自己的服务，在设置里添加模型，填接口地址（如 `https://服务商地址/v1`）、模型名和 API Key。支持 OpenAI 兼容的 Chat Completions 和 Responses 接口，会自动识别。

智慧树智慧课程作业里有图片题，要用能看图的模型。发给 AI 的是题目和选项（智慧树验证码会发截图），不带平台登录信息。

## 注意

- 不保证答案正确，也不保证满足课程的全部要求。
- 打开试卷可能会在平台上开始计时。
- 交卷结果不确定时不会自动重交，请到平台核对。

## 来源

部分早期代码源自 [11273/mooc-work-answer](https://github.com/11273/mooc-work-answer)（含 tooplick 的题目导出贡献）；上游未声明许可证，再分发前请确认授权。

## 友情链接

- [LINUX DO](https://linux.do) - 真诚、友善、团结、专业，共建你我引以为荣之社区
