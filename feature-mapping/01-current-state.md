# 01 — Current state (dev-beta @ 8e2db1b)

## What exists

A single FastAPI process (`app/main.py`, ~1,100 lines) serving an Alpine.js UI, backed by ChromaDB, Neo4j, and one SQLite file. No authentication.

### Backend modules (`app/services/`) and where each goes

| Module | Today | Becomes |
|---|---|---|
| `chunking.py` | Fixed and sentence-aware chunking | `rag/chunking.py` (unchanged) |
| `embeddings.py` | Gemini + NVIDIA embeddings, branching on provider | `providers/*` embedding implementations |
| `extraction.py` | Triple and entity extraction; `complete()` helper; Gemini + NVIDIA branches | `rag/extraction.py` using `ChatProvider.complete` |
| `generation.py` | `stream_answer`, `stream_chat`; Gemini + NVIDIA branches | Folded into `providers/*` chat implementations |
| `model_config.py` | Key validation; NVIDIA catalog probing with a 10-minute cache | `providers/registry.py` discovery + capability probes |
| `vector_store.py` | Chroma client (query, get, count, delete) | `rag/vector_store.py` with workspace-namespaced collections |
| `graph_store.py` | Neo4j merge, traverse, entity match, stats, delete | `rag/graph_store.py` with workspace-namespaced graphs |
| `hybrid.py` | BM25 index cache + weighted RRF | `rag/hybrid.py` (unchanged) |
| `retrieval.py` | Multi-stage chunk pipeline + graph retrieval; `LLMContext` | `rag/retrieval.py`; `LLMContext` replaced by provider handles |
| `rerank.py` | LLM-judge listwise rerank; NVIDIA hosted rerank | `rag/rerank.py` + `RerankProvider` |
| `evaluation.py` | Groundedness judge | `rag/evaluation.py` |
| `sentiment.py` | VADER + LLM emotions | `rag/sentiment.py` |
| `ingestion.py` | Synchronous chunk → embed → upsert → extract triples | `rag/ingestion.py`, run as a background job |
| `chat.py` | `ChatAgent.run_turn`: rewrite → retrieve → generate → check | Core of `runtime/runtime.py` |
| `mcp_client.py` | `MCPClientManager` (connect per call, tool cache) + `ToolRunner` (NVIDIA + Gemini tool loops) | `mcp/client.py` + `runtime/tools.py` (all five providers) |
| `mcp_server.py` | Unauthenticated MCP server at `/mcp/` (4 tools) | `mcp/server.py` behind API-key auth, workspace-scoped |
| `key_store.py` | SQLite: **plaintext** API keys, collection registry, query history | Replaced by SQLAlchemy models + encrypted credentials |
| `bot_store.py` | SQLite: bots, conversations, messages, MCP servers (headers/env **plaintext**) | Replaced by SQLAlchemy models |

### Frontend (`app/static/`)

`index.html` (~1,400 lines), `app.js`, `chat.js`, `style.css` — a single Alpine component covering the Lab (Chroma/Graph/Compare), Chat, Bot Studio, Settings, History, Collections, the command palette, themes, and resizable panels. Design tokens in `style.css` (dark "observatory" + light theme) carry over to React.

### Data stores

| Store | Holds | Isolation today |
|---|---|---|
| SQLite `arena.db` | `api_keys`, `collections`, `history`, `bots`, `conversations`, `messages`, `mcp_servers` | None |
| ChromaDB | One collection per knowledge base, chunk metadata `source/doc/seq` | None (global names) |
| Neo4j | `Entity` nodes and `RELATES` edges with a `graph` property per collection | None |

### HTTP surface (all unauthenticated)

Keys (`/keys`), ingest, query (`POST /query`, SSE), collections, history, analyze, bots, conversations, messages feedback, `/chat` (SSE), MCP server management, tool-support probe, `/config/validate-key`, and the MCP endpoint `/mcp/`.

## Gaps against the target

| Area | Gap |
|---|---|
| Identity | No users, sessions, or workspaces. Anyone who reaches port 8000 controls everything. |
| Secrets | Provider keys and MCP headers stored in plaintext. `/keys` masks them, but the file does not. |
| Providers | Only Gemini and NVIDIA; provider logic is spread across six modules as `if provider == "nvidia"` branches. No OpenAI, Anthropic, or Ollama. |
| Credentials | One active key per provider, chosen in the browser. Collections don't record which credential embedded them. |
| Bots | No personas, no versions; edits apply to live traffic immediately. |
| Delivery | No public API, no API keys, no gRPC, no webhooks, no OpenAI-compatible endpoint. The MCP server is open to anyone. |
| Jobs | Ingestion blocks the request; no queue, no retries. |
| Tenancy in stores | Chroma and Neo4j names are global; collisions across users would leak data. |
| Network safety | User-supplied MCP URLs are fetched without SSRF protection. |
| Observability | No usage tracking, request logs, or audit log. |
| Tests | No automated test suite. |
| Frontend | One large Alpine file; hard to grow into a multi-page dashboard. |

## Known issues to carry forward

- Small models (e.g. `nemotron-3.5-bolt-e4b`) often skip tool calls and sometimes mark refusals as grounded; larger models behave.
- VADER sentiment mislabels some neutral factual text.
- No hosted NVIDIA reranker is available on the test account (retired or not entitled); LLM-judge reranking is the fallback.
- NVIDIA's free tier queues requests for minutes and returns 503/504; probes and calls need timeouts without retries.
- Gemini tool calling and stdio MCP servers are implemented but untested.
- Ingestion is not atomic: chunks are written before triple extraction finishes.
