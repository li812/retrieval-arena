# 03 — Architecture

## Layers

```
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌────────────┐
 callers →  │ React        │  │ REST /v1     │  │ OpenAI-compat│  │ gRPC :50051 │  │ MCP /mcp/  │
            │ dashboard    │  │ JSON · SSE   │  │ /v1/chat/... │  │ unary·stream│  │ (API key)  │
            └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘  └─────┬──────┘
                   │ session+CSRF    │ API key          │ API key         │ API key        │ API key
            ┌──────▼─────────────────▼──────────────────▼─────────────────▼────────────────▼──────┐
            │  Auth & scoping: resolve caller → workspace, scopes, rate limits                     │
            └──────┬─────────────────────────────────────────────────────────────────────┬────────┘
                   │ dashboard CRUD                                                      │ invoke
            ┌──────▼────────────┐                                        ┌───────────────▼─────────┐
            │ Repositories      │◄──────────────────────────────────────►│ Runtime                 │
            │ (workspace-scoped)│                                        │ composer · memory ·     │
            └──────┬────────────┘                                        │ retrieval · tools ·     │
                   │                                                     │ checks → event stream   │
            ┌──────▼────────────┐   ┌────────────┐   ┌─────────────┐     └──┬──────────┬──────┬────┘
            │ SQLite (WAL)      │   │ Chroma     │   │ Neo4j       │◄───────┘          │      │
            │ SQLAlchemy+Alembic│   │ ws{id}__x  │   │ ws{id}:x    │      ┌────────────▼─┐ ┌──▼─────────┐
            └──────▲────────────┘   └────────────┘   └─────────────┘      │ Providers    │ │ MCP client │
                   │                                                      │ OpenAI·Anth· │ │ (SSRF-     │
            ┌──────┴────────────┐                                         │ Gemini·NVIDIA│ │  guarded)  │
            │ Job worker        │ webhook delivery · async invokes ·      │ ·Ollama      │ └────────────┘
            │ (in-process)      │ ingestion · retention                   └──────────────┘
            └───────────────────┘
```

## Request flows

### Dashboard (session)
Browser → session cookie + `X-CSRF-Token` → router → repository (scoped by the session's workspace) → JSON.

### Synchronous invoke (REST JSON, gRPC `Invoke`, OpenAI non-stream)
1. Authenticate the API key → workspace, scopes; check the bot is in scope; take a rate-limit token.
2. Resolve the bot's **published version** (or the pinned one).
3. `runtime.invoke(...)` → event stream; the adapter collects it into a final response.
4. Persist the conversation turn, the run record, and usage; publish events to the event bus (→ webhook subscriptions).

### Streaming invoke (SSE, gRPC `InvokeStream`, OpenAI stream)
Same, but the adapter forwards each event as it is produced. A client disconnect cancels the run (RT-6).

### Async invoke (webhook callback)
1. `POST …/messages:async` validates the input and the callback URL (SSRF guard), creates a `run` row with status `queued` and a `job`, and returns `202 {run_id}`.
2. The worker claims the job, runs `runtime.invoke`, stores the result, and enqueues a `webhook_delivery` to the callback URL.
3. Delivery is signed and retried with backoff (HOOK-5, HOOK-6).

### Event subscriptions
The runtime and the repositories publish domain events to an in-process bus. A subscriber matches them against the workspace's `webhook_subscriptions` and enqueues deliveries in the same transaction as the triggering write, so no event is lost on a crash.

## The runtime

```
invoke(bot_version, input, conversation, caller, options) → AsyncIterator[Event]
  run.started
  ├─ memory: load last N turns; rewrite follow-up into a standalone query   (rewrite.completed)
  ├─ retrieval: per recipe — vector pipeline / graph / both                 (retrieval.*)
  ├─ compose: persona + bot + context + tool rules → system prompt + messages
  ├─ generate: provider.chat(stream=True, tools=…)                          (message.delta)
  │    └─ tool loop (≤ max rounds): tool.call → MCP client → tool.result → continue
  ├─ checks: sentiment, optional groundedness                               (check.*)
  └─ persist turn + usage                                                   (usage, message.completed)
  run.completed | run.failed | run.cancelled
```

- Pure async: provider SDKs that are sync run in a thread; the event stream is an `asyncio.Queue`.
- Budgets (RT-7): wall clock, max output tokens, max tool calls, per-tool timeout.
- The runtime has no knowledge of HTTP or gRPC; adapters only translate events.

## Providers

`providers/base.py` defines:

```python
class ChatProvider(Protocol):
    async def list_models(self) -> list[ModelInfo]
    async def chat(self, req: ChatRequest) -> ChatResult              # non-streaming
    def stream(self, req: ChatRequest) -> AsyncIterator[ChatChunk]    # text deltas, tool-call deltas, usage
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str], kind: Literal["query","document"]) -> list[list[float]]
class RerankProvider(Protocol):
    async def rerank(self, query: str, passages: list[str]) -> list[float]
```

`ChatRequest` uses one internal message format (roles `system`/`user`/`assistant`/`tool`, tool calls with ids). Each provider module translates to and from its API. `registry.py` builds provider instances from a decrypted credential and caches capability probes.

## Process model & deployment

- One container `api`: uvicorn (HTTP :8000) + `grpc.aio` server (:50051) + job worker, all started in the FastAPI lifespan.
- The React app is built in a multi-stage Docker build and served as static files by the API (`/` → SPA, `/api/*` dashboard, `/v1/*` public, `/mcp/` MCP).
- `chromadb` and `neo4j` containers as today. Ollama optional (host or separate container).
- SQLite file and its WAL live in the `arena_data` volume. Back up with `sqlite3 .backup` or by copying while the app is stopped.
- Horizontal scaling is not a goal with SQLite: one `api` instance per install. The worker uses lease-based claiming so a second worker process would still be safe.

## Repository layout

```
backend/
  app/{core,models,repositories,providers,rag,runtime,mcp,api,grpc,jobs}/
  app/cli.py
  alembic/  alembic.ini
  proto/arena/v1/bots.proto
  tests/{unit,integration,contract,isolation}/
  pyproject.toml
frontend/
  src/{app,routes,features/*,components,lib,styles}/
  package.json  vite.config.ts
docker-compose.yml  Dockerfile  feature-mapping/
```

Today's `app/` moves to `backend/app/` in M1; the Alpine UI keeps working until the React pages replace it, then it's removed.
