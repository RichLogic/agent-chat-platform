# Agent Chat Platform

全栈 **AI Agent 对话平台**——支持流式响应、自主多步工具调用、MCP 集成、PDF 知识库（RAG）、长期记忆与对话分享回放，体验对标 ChatGPT / Claude，可完全自托管与自由扩展。

---

## 功能清单

| 分类 | 功能 | 说明 |
|------|------|------|
| **对话** | SSE 流式输出 | 基于 Server-Sent Events 逐 token 实时推送 |
| **Agent** | 多步工具调用 | LLM 自主选择并串联最多 5 个工具完成任务 |
| **Agent** | LLM 自动降级 | 主模型失败时自动切换备用模型（Poe ↔ Kimi） |
| **工具** | 联网搜索 | SerpAPI（主）+ Brave Search（备） |
| **工具** | 新闻 | NewsAPI 热点新闻查询 |
| **工具** | 天气 | Open-Meteo 实时天气与 7 天预报 |
| **工具** | 网页抓取 | 抓取 URL 内容并入库到知识库 |
| **RAG** | PDF 知识库 | 上传 PDF → 分块 → 嵌入 (all-MiniLM-L6-v2) → 向量检索 |
| **RAG** | 知识库搜索工具 | LLM 在对话中可主动查询向量知识库 |
| **MCP** | MCP 适配器 | 动态发现并注册任意 MCP 服务器上的工具 |
| **MCP** | 笔记服务 | 内置 MCP 笔记服务器，支持持久化笔记 |
| **记忆** | 长期记忆 | 自动嵌入用户消息 → 跨对话语义检索 |
| **记忆** | 记忆压缩 | 后台由 LLM 将历史记忆压缩为摘要 |
| **分享** | 对话分享 | 生成公开分享链接，无需登录即可查看 |
| **分享** | 回放 | 逐步回放对话过程，包括工具调用细节 |
| **认证** | GitHub OAuth + JWT | 基于 GitHub 登录与 JWT 令牌的安全认证 |
| **评估** | LLM-as-Judge | 内置评估框架，对回答质量自动打分 |

---

## 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                     Frontend (:8300)                         │
│            React 19 · TypeScript · Tailwind CSS              │
│                   Vite · React Router                        │
└────────────────────────┬─────────────────────────────────────┘
                         │  SSE / REST
                         ▼
┌──────────────────────────────────────────────────────────────┐
│                     Backend (:8301)                          │
│              FastAPI · Python 3.14 · Uvicorn                 │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ Chat Service │  │ Memory Svc   │  │ KB / PDF Service    │ │
│  │  (流式对话,  │  │  (嵌入,      │  │  (分块, 嵌入,       │ │
│  │   工具循环)  │  │   压缩)      │  │   向量检索)         │ │
│  └──────┬───────┘  └──────────────┘  └─────────────────────┘ │
│         │                                                    │
│  ┌──────▼───────────────────────────────────────────────┐    │
│  │              Tool Registry (工具注册表)               │    │
│  │  search · news · weather · read_pdf · kb_search      │    │
│  │  search_memory · ingest_webpage · MCP tools (动态)   │    │
│  └──────────────────────────────────────────────────────┘    │
└──────┬───────────────┬──────────────────┬────────────────────┘
       │               │                  │
       ▼               ▼                  ▼
┌────────────┐  ┌─────────────┐   ┌──────────────────┐
│  LLM APIs  │  │  MongoDB    │   │  MCP Servers     │
│ Poe / Kimi │  │ (Atlas      │   │  (Notes :8302)   │
│ (OpenAI    │  │  Local)     │   │                  │
│  兼容接口) │  │ 文档+向量   │   │                  │
└────────────┘  └─────────────┘   └──────────────────┘
```

---

## 快速开始

### Docker Compose 一键启动（推荐）

```bash
# 1. 克隆并配置
git clone https://github.com/RichLogic/agent-chat-platform.git
cd agent-chat-platform
cp .env.example .env        # ← 填入你的 API Key

# 2. 启动所有服务
docker compose up --build

# 3. 打开浏览器
#    前端 → http://localhost:8300
#    后端 → http://localhost:8301/docs  (Swagger 文档)
```

### 本地开发

```bash
# 后端
cd backend
uv sync --dev                 # 安装依赖
uv run uvicorn agent_chat.main:app --reload --port 8301

# 前端（另开终端）
cd frontend
npm install
npm run dev                   # Vite 开发服务器 → http://localhost:8300

# MongoDB（另开终端或后台运行）
docker run -d -p 27017:27017 mongodb/mongodb-atlas-local:8.0
```

---

## 环境变量说明

复制 `.env.example` 为 `.env` 并填入实际值。所有变量使用 `AC_` 前缀（pydantic-settings）。

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `AC_HOST` | | `0.0.0.0` | 服务绑定地址 |
| `AC_PORT` | | `8301` | 服务端口 |
| `AC_CORS_ORIGINS` | | `["http://localhost:8300"]` | 允许的跨域来源（JSON 数组） |
| `AC_MONGO_URI` | **是** | `mongodb://mongodb:27017` | MongoDB 连接串 |
| `AC_MONGO_DB` | | `agent_chat` | 数据库名 |
| `AC_DATA_DIR` | | `data` | 本地文件存储目录 |
| `AC_MAX_UPLOAD_SIZE_MB` | | `50` | 最大上传文件大小（MB） |
| **LLM — 主模型** | | | |
| `AC_LLM_PROVIDER` | **是** | `poe` | 主 LLM 提供方（`poe` 或 `kimi`） |
| `AC_POE_API_KEY` | **是**\* | — | Poe API 密钥 |
| `AC_POE_MODEL` | | `Gemini-3-Flash` | Poe 上的模型名称 |
| `AC_POE_BASE_URL` | | `https://api.poe.com/v1` | Poe API 地址 |
| **LLM — 备用模型** | | | |
| `AC_KIMI_API_KEY` | | — | Kimi API 密钥（填写后启用降级） |
| `AC_KIMI_MODEL` | | `kimi-k2.5` | Kimi 模型名称 |
| `AC_KIMI_BASE_URL` | | `https://kimi-k2.ai/api/v1` | Kimi API 地址 |
| **搜索** | | | |
| `AC_SERPAPI_KEY` | | — | SerpAPI 密钥（启用联网搜索） |
| `AC_BRAVE_SEARCH_KEY` | | — | Brave Search 密钥（搜索降级） |
| `AC_NEWSAPI_KEY` | | — | NewsAPI 密钥（启用新闻工具） |
| **认证** | | | |
| `AC_GITHUB_CLIENT_ID` | **是** | — | GitHub OAuth App Client ID |
| `AC_GITHUB_CLIENT_SECRET` | **是** | — | GitHub OAuth App Client Secret |
| `AC_JWT_SECRET` | **是** | — | JWT 签名密钥 |
| `AC_JWT_EXPIRY_MINUTES` | | `10080` | 令牌过期时间（默认 7 天） |
| **其他** | | | |
| `AC_FRONTEND_URL` | | `http://localhost:8300` | 前端地址（OAuth 回调用） |
| `AC_EMBEDDING_MODEL` | | `all-MiniLM-L6-v2` | sentence-transformers 嵌入模型 |
| `AC_MCP_NOTES_URL` | | — | MCP 笔记服务地址（留空则禁用） |
| `AC_NOTES_ROOT` | | `data/notes` | MCP 笔记存储目录 |
| `AC_LOG_LEVEL` | | `INFO` | 日志级别 |

\* 至少需要配置一个 LLM 提供方的 API 密钥。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19, TypeScript, Tailwind CSS v4, Vite 7, React Router 7 |
| 后端 | Python 3.14, FastAPI, Uvicorn, Pydantic v2, structlog |
| 流式传输 | SSE (sse-starlette) |
| 数据库 | MongoDB (Atlas Local), Motor (异步驱动) |
| 向量嵌入 | sentence-transformers (all-MiniLM-L6-v2)，存储于 MongoDB |
| PDF 解析 | PyMuPDF4LLM |
| LLM 客户端 | OpenAI 兼容 SDK（适配 Poe、Kimi 等） |
| MCP | Model Context Protocol SDK |
| 认证 | GitHub OAuth 2.0, PyJWT |
| 测试 | pytest, pytest-asyncio, mongomock-motor, ruff |
| 构建 | uv (后端), npm (前端), Docker Compose |

---

## 演示

> **截图 / GIF / 视频稍后补充。**

<!-- TODO: 在此添加 2-3 张截图或 GIF / 视频链接 -->

---

## 许可证

MIT
