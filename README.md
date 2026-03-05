# Agent Chat Platform

A full-stack **AI Agent chat application** with streaming responses, autonomous tool calling, MCP integration, PDF knowledge base (RAG), long-term memory, and conversation sharing — similar in experience to ChatGPT / Claude, but fully self-hosted and extensible.

---

## Features

| Category | Feature | Description |
|----------|---------|-------------|
| **Chat** | SSE Streaming | Real-time token-by-token streaming via Server-Sent Events |
| **Agent** | Multi-step Tool Calling | LLM autonomously selects and chains up to 5 tools per turn |
| **Agent** | LLM Fallback | Primary → fallback provider auto-switch on failure (Poe ↔ Kimi) |
| **Tools** | Web Search | SerpAPI (primary) + Brave Search (fallback) |
| **Tools** | News | NewsAPI integration for latest headlines |
| **Tools** | Weather | Real-time weather queries |
| **Tools** | Webpage Ingestion | Fetch and extract content from URLs into knowledge base |
| **RAG** | PDF Knowledge Base | Upload PDFs → chunk → embed (all-MiniLM-L6-v2) → vector search |
| **RAG** | KB Search Tool | LLM can query the vector knowledge base during conversation |
| **MCP** | MCP Adapter | Dynamically discover and register tools from any MCP server |
| **MCP** | Notes Server | Built-in MCP notes server for persistent note-taking |
| **Memory** | Long-term Memory | Auto-embed user messages → semantic search across conversations |
| **Memory** | Memory Compression | Background LLM-driven compression of memory records |
| **Share** | Conversation Sharing | Generate public share links for conversations |
| **Share** | Replay | Step-by-step replay of conversation including tool calls |
| **Auth** | GitHub OAuth + JWT | Secure authentication with token-based sessions |
| **Eval** | LLM-as-Judge | Built-in evaluation framework for answer quality scoring |

---

## Architecture

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
│  │ (streaming,  │  │ (embed,      │  │ (chunk, embed,      │ │
│  │  tool loop)  │  │  compress)   │  │  vector search)     │ │
│  └──────┬───────┘  └──────────────┘  └─────────────────────┘ │
│         │                                                    │
│  ┌──────▼───────────────────────────────────────────────┐    │
│  │              Tool Registry                           │    │
│  │  search · news · weather · read_pdf · kb_search      │    │
│  │  search_memory · ingest_webpage · MCP tools (dynamic)│    │
│  └──────────────────────────────────────────────────────┘    │
└──────┬───────────────┬──────────────────┬────────────────────┘
       │               │                  │
       ▼               ▼                  ▼
┌────────────┐  ┌─────────────┐   ┌──────────────────┐
│  LLM APIs  │  │  MongoDB    │   │  MCP Servers     │
│ Poe / Kimi │  │ (Atlas      │   │  (Notes :8302)   │
│ (OpenAI-   │  │  Local)     │   │                  │
│  compatible)│  │ docs+vectors│   │                  │
└────────────┘  └─────────────┘   └──────────────────┘
```

---

## Quick Start

### Docker Compose (recommended)

```bash
# 1. Clone and configure
git clone https://github.com/RichLogic/agent-chat-platform.git
cd agent-chat-platform
cp .env.example .env        # ← edit with your API keys

# 2. Launch all services
docker compose up --build

# 3. Open in browser
#    Frontend → http://localhost:8300
#    Backend  → http://localhost:8301/docs  (Swagger UI)
```

### Local Development

```bash
# Backend
cd backend
uv sync --dev                 # install dependencies
uv run uvicorn agent_chat.main:app --reload --port 8301

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # Vite dev server → http://localhost:8300

# MongoDB (separate terminal or background)
docker run -d -p 27017:27017 mongodb/mongodb-atlas-local:8.0
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values. All variables use the `AC_` prefix.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AC_HOST` | | `0.0.0.0` | Server bind address |
| `AC_PORT` | | `8301` | Server port |
| `AC_CORS_ORIGINS` | | `["http://localhost:8300"]` | Allowed CORS origins (JSON array) |
| `AC_MONGO_URI` | **Yes** | `mongodb://mongodb:27017` | MongoDB connection string |
| `AC_MONGO_DB` | | `agent_chat` | Database name |
| `AC_DATA_DIR` | | `data` | Local file storage directory |
| `AC_MAX_UPLOAD_SIZE_MB` | | `50` | Max upload file size in MB |
| **LLM — Primary** | | | |
| `AC_LLM_PROVIDER` | **Yes** | `poe` | Primary LLM provider (`poe` or `kimi`) |
| `AC_POE_API_KEY` | **Yes**\* | — | Poe API key |
| `AC_POE_MODEL` | | `Gemini-3-Flash` | Model name on Poe |
| `AC_POE_BASE_URL` | | `https://api.poe.com/v1` | Poe API base URL |
| **LLM — Fallback** | | | |
| `AC_KIMI_API_KEY` | | — | Kimi API key (enables fallback) |
| `AC_KIMI_MODEL` | | `kimi-k2.5` | Kimi model name |
| `AC_KIMI_BASE_URL` | | `https://kimi-k2.ai/api/v1` | Kimi API base URL |
| **Search** | | | |
| `AC_SERPAPI_KEY` | | — | SerpAPI key (enables web search) |
| `AC_BRAVE_SEARCH_KEY` | | — | Brave Search key (search fallback) |
| `AC_NEWSAPI_KEY` | | — | NewsAPI key (enables news tool) |
| **Auth** | | | |
| `AC_GITHUB_CLIENT_ID` | **Yes** | — | GitHub OAuth App client ID |
| `AC_GITHUB_CLIENT_SECRET` | **Yes** | — | GitHub OAuth App client secret |
| `AC_JWT_SECRET` | **Yes** | — | Secret for signing JWT tokens |
| `AC_JWT_EXPIRY_MINUTES` | | `10080` | Token expiry (default 7 days) |
| **Other** | | | |
| `AC_FRONTEND_URL` | | `http://localhost:8300` | Frontend URL (for OAuth redirect) |
| `AC_EMBEDDING_MODEL` | | `all-MiniLM-L6-v2` | Sentence-transformers model for embeddings |
| `AC_MCP_NOTES_URL` | | — | MCP notes server URL (leave empty to disable) |
| `AC_NOTES_ROOT` | | `data/notes` | Directory for MCP notes storage |
| `AC_LOG_LEVEL` | | `INFO` | Logging level |

\* At least one LLM provider API key is required.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, TypeScript, Tailwind CSS v4, Vite 7, React Router 7 |
| Backend | Python 3.14, FastAPI, Uvicorn, Pydantic v2, structlog |
| Streaming | SSE (sse-starlette) |
| Database | MongoDB (Atlas Local for dev), Motor (async driver) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2), stored in MongoDB |
| PDF Parsing | PyMuPDF4LLM |
| LLM Client | OpenAI-compatible SDK (works with Poe, Kimi, etc.) |
| MCP | Model Context Protocol SDK |
| Auth | GitHub OAuth 2.0, PyJWT |
| Testing | pytest, pytest-asyncio, mongomock-motor, ruff |
| Packaging | uv (backend), npm (frontend), Docker Compose |

---

## Demo

> **Screenshots / GIF / video coming soon** — to be added.

<!-- TODO: Add 2-3 screenshots or a GIF/video link here -->

---

## License

MIT
