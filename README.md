# Retrieval Arena

A local RAG (Retrieval-Augmented Generation) playground that lets you ingest documents once and benchmark two fundamentally different retrieval strategies in real time — **ChromaDB vector search** vs **Neo4j knowledge graph** — with a live-animating UI and streaming answers.

The defining feature is **Compare mode**: run both backends simultaneously on the same question and watch chunk cards and graph edges populate side-by-side as results stream in.

```
┌─────────────────────────────────────────────────────────────────┐
│  RETRIEVAL ARENA   [⚡ CHROMA]  [◆ GRAPH]  [⚔ COMPARE]   [⚙]  │
├──────────────────┬──────────────────┬───────────────────────────┤
│                  │  ⚡ CHROMA       │  ◆ GRAPH                  │
│  Tuning sliders  │  Chunk cards     │  Entity nodes draw        │
│  Ingest panel    │  light up with   │  hop-by-hop as graph      │
│                  │  score bars      │  edges arrive             │
├──────────────────┴──────────────────┴───────────────────────────┤
│  ⚡ CHROMA answer (streaming)  │  ◆ GRAPH answer (streaming)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Why this project exists

Most RAG tutorials show one retrieval strategy. Real systems face a genuine choice: vector similarity is fast and general; knowledge graphs capture structured relationships that dense search misses. **Retrieval Arena** makes that trade-off visible and interactive.

---

## Features

- **Four modes** — Chroma (vector + MMR), Graph (Neo4j BFS), Compare (both simultaneously), Chat (bots built on your collections)
- **Retrieval Lab** — dense / BM25 keyword / hybrid (RRF) search, multi-query · HyDE · step-back query transforms, LLM-judge reranking, neighbour-chunk expansion, context ordering and token budgets, source filters, with a per-stage pipeline trace
- **Answer checks** — LLM groundedness verdict per claim, VADER sentiment on chunks and answers, optional LLM emotion breakdown
- **Bot Studio** — save a prompt + collection + retrieval recipe + model as a chatbot, test it in a live preview, chat with memory (follow-ups are rewritten into standalone queries), rate replies
- **MCP both ways** — the app is an MCP server (`/mcp/`) for Claude Code / Desktop / Cursor, and bots can call tools on external MCP servers
- **Workspace** — query history with restore / re-run / pin, Markdown & JSON export, collections manager, light/dark themes, resizable panels, ⌘K command palette and keyboard shortcuts
- **Live SSE event stream** — chunk cards and graph edges animate in real time during retrieval
- **Dual-answer Compare mode** — identical question, both backends, side-by-side streaming answers
- **Tunable everything** — chunk size, overlap, strategy, top-k, similarity threshold, MMR λ, graph hops, temperature, max tokens
- **Two chunking strategies** — fixed sliding-window and sentence/paragraph-aware
- **PDF + plain text ingestion** — single ingest populates both stores
- **Two providers** — Gemini and NVIDIA NIM; key validation discovers the models your key can actually use (NVIDIA models are probed live)
- **Two UIs during the move** — the classic Alpine.js UI at `/`, and the new React dashboard shell at `/app/` (themes, command palette, live readiness)
- **Ops basics** — `/healthz` and `/readyz` endpoints, JSON logs with request and run ids, automatic database migrations with a backup

---

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.111+ (Python 3.11) |
| Vector store | ChromaDB (server mode, `HttpClient`) |
| Knowledge graph | Neo4j 5 |
| LLM / Embeddings | Google Gemini (`google-genai`) · NVIDIA NIM (OpenAI-compatible API) |
| App data | SQLite via SQLAlchemy 2 + Alembic (saved keys, bots, conversations, history, MCP servers) |
| Agent protocol | MCP Python SDK 2.x (streamable HTTP server + client) |
| Frontend | React 18 + Vite + TypeScript at `/app/`; classic Alpine.js 3 UI at `/` |
| Graph viz | vis-network 9 |
| Orchestration | Docker Compose |

---

## Quick start

**Prerequisites:** Docker Desktop · a Google Gemini API key ([get one free](https://aistudio.google.com/app/apikey)) or an NVIDIA NIM key ([build.nvidia.com](https://build.nvidia.com))

```bash
# 1. Clone
git clone https://github.com/li812/retrieval-arena.git
cd retrieval-arena

# 2. (Optional) copy and edit env
cp .env.example .env

# 3. Build and start everything (only Docker is needed on the host)
docker compose up --build
```

The image is a multi-stage build: a Node stage builds the React app, and the API container serves it.
Neo4j takes ~30 s to initialise on first boot.

| URL | What |
|---|---|
| http://localhost:8000/ | Classic UI (Lab, Compare, Chat, Bot Studio) |
| http://localhost:8000/app/ | New dashboard shell (theme, command palette with ⌘/Ctrl K, system readiness) |
| http://localhost:8000/healthz | Liveness: `{"status":"ok"}` whenever the process is up |
| http://localhost:8000/readyz | Readiness: SQLite (and migrations), Chroma and Neo4j; 503 naming the failing check |
| http://localhost:8000/mcp/ | Built-in MCP server |

Upgrading an existing install? Read [docs/operator/upgrading-to-m1.md](docs/operator/upgrading-to-m1.md): the first
start migrates `arena.db` and keeps a backup next to it. A user guide is in
[docs/user-guide/getting-started.md](docs/user-guide/getting-started.md).

### Frontend development with hot reload

```bash
docker compose --profile dev up --build
```

This adds a `web` service (Node 22 in a container, `node_modules` in a Docker volume) running the Vite dev server on
**http://localhost:5173/app/**. Edits under `frontend/` reload instantly; API calls are proxied to the `api`
container (`VITE_PROXY_TARGET=http://api:8000`). Backend code under `backend/app` is bind-mounted into `api`:
run `docker compose restart api` after Python changes.

### Exposed ports

| Service | Port | Purpose |
|---|---|---|
| API (FastAPI) | 8000 | Main app, classic UI, `/app/` shell |
| Vite dev server (`dev` profile only) | 5173 | React app with hot reload |
| ChromaDB | 8001 | Direct queries / debug |
| Neo4j Browser | 7474 | Visual graph explorer |
| Neo4j Bolt | 7687 | Driver access |

---

## Using the app

### 1. Configure your API key

Click **⚙** (top-right), pick a provider, paste your key and click **Test**. On success the model dropdowns fill with the models your key can use. Give the key a label and **Save** it to reuse it after reloads.

> Saved keys are stored in plain text in the `arena_data` volume (`arena.db`). After saving, the browser only holds the key's id — requests reference it and the server looks the secret up, so keys never appear in URLs or access logs. The app has **no authentication**: keep port 8000 on localhost.

### 2. Ingest a document

Open the **Ingest** panel in the sidebar. Enter a collection name, paste text or upload a `.txt`/`.pdf` file, then click **Ingest**. One call populates both ChromaDB and Neo4j simultaneously, so you can switch backends per-query without re-ingesting.

### 3. Query

Type a question in the bar at the bottom and press **Enter**. Switch between modes with the header buttons:

- **⚡ CHROMA** — chunk cards appear and score bars fill as `chunk_scored` events stream in
- **◆ GRAPH** — entity nodes and relationship edges draw hop-by-hop as `hop_traversed` events arrive
- **⚔ COMPARE** — both panels run simultaneously; two streaming answers appear side-by-side
- **● CHAT** — talk to a bot (see below)

Press **?** for keyboard shortcuts and **⌘/Ctrl K** for the command palette. Every result lands in **History** (↺) and can be exported as Markdown or JSON.

### 4. Build a chatbot

Switch to **Chat** and click **+ New**: the current Lab settings become a bot draft. In **Bot Studio** set the name, system prompt, collection, knowledge source (vectors, graph or both), model, greeting and starter questions, and try it in the live preview before saving. Conversations are saved per bot; each follow-up is rewritten into a standalone search query before retrieval.

### 5. MCP

**Use the arena from Claude Code** (or any MCP client) — tools `list_collections`, `search_collection`, `graph_query`, `ask_bot`:

```bash
claude mcp add --transport http retrieval-arena http://localhost:8000/mcp/
```

Tools run with the key last selected in the UI for the collection's provider. The trailing slash in `/mcp/` matters.

**Give bots tools** — in ⚙ → *MCP servers*, add a streamable-HTTP server (optionally with an `Authorization` header), click **Test** to list its tools, then tick tools per bot in Bot Studio. The studio checks whether the bot's model supports tool calling; small models often answer without calling tools, so prefer a larger model for tool-using bots. stdio servers are disabled unless `ALLOW_STDIO_MCP=true`, because they execute commands inside the API container.

---

## Architecture

```
backend/
  app/main.py               create_app(): routers, middleware, /static, /app/ SPA, /mcp/
  app/core/                 settings, SQLite engine + migrations, logging, service container
  app/models/               SQLAlchemy models (legacy tables mapped exactly)
  app/repositories/         all database access (keys, collections, history, bots, conversations, MCP servers)
  app/api/legacy/           today's endpoints, same paths and shapes as before
  app/api/health.py         /healthz, /readyz
  app/rag/                  chunking, stores, hybrid search, retrieval, rerank, evaluation, sentiment, ingestion
  app/providers/            Gemini / NVIDIA embedding, generation, model discovery
  app/runtime/chat.py       one chat turn: rewrite → retrieve → generate (+ tools) → checks
  app/mcp/                  MCP client (bot tools) and server (/mcp/)
  app/static/               classic Alpine UI
  alembic/                  migrations (0001 = legacy baseline)
  tests/                    unit, integration, parity (fakes; no network)
frontend/                   React + Vite + TypeScript dashboard (served at /app/)
```

### Data flow — Ingest

```
text/PDF
  → ChunkingService (fixed or sentence_aware)
  → EmbeddingAgent (Gemini)          → VectorStore.upsert()
  → GraphExtractionAgent (Gemini)    → GraphStore.merge_triples()
```

### Data flow — Query (single backend)

```
question
  → EmbeddingAgent (query embedding)
  → [Chroma] VectorStore.query() → MMR re-rank → threshold filter
  → [Graph]  GraphExtractionAgent.extract_entities() → GraphStore.traverse() (BFS)
  → SSE event stream (candidates_found, chunk_scored / hop_traversed, context_assembled)
  → GenerationAgent.stream_answer() (Gemini streaming)
  → SSE token stream → answer
```

### Data flow — Compare mode

```
question
  → single embedding call (shared)
  → asyncio.gather([Chroma retrieval, Graph retrieval])   ← run in parallel
  → SSE: chroma_* events + graph_* events interleaved
  → two generation threads → combined queue → SSE token stream
  → two answers stream simultaneously
```

---

## Tuning parameters

### Chunking *(applied at ingest time)*

| Param | Default | Range | Description |
|---|---|---|---|
| `chunk_size` | 800 | 100–4000 | Target characters per chunk |
| `chunk_overlap` | 120 | 0–1000 | Overlap between consecutive chunks |
| `chunking_strategy` | `fixed` | fixed / sentence_aware | Sliding window vs sentence/paragraph boundary splitting |

### Retrieval — Chroma

| Param | Default | Range | Description |
|---|---|---|---|
| `top_k` | 5 | 1–20 | Chunks returned after MMR re-ranking |
| `similarity_threshold` | 0.0 | 0–1 | Discard chunks below this cosine similarity |
| `mmr_diversity` | 0.5 | 0–1 | MMR λ — 0 = pure relevance, 1 = pure diversity |

### Retrieval — Knowledge Graph

| Param | Default | Range | Description |
|---|---|---|---|
| `graph_hops` | 1 | 1–3 | BFS depth from seed entities |
| `max_triples_per_chunk` | 8 | 1–30 | Triples extracted per chunk at ingest |
| `triple_limit` | 25 | 1–100 | Max triples returned per query |

### Retrieval Lab *(Chroma / Compare / bots)*

| Param | Default | Description |
|---|---|---|
| `search_mode` | `dense` | `dense` (embeddings), `keyword` (BM25) or `hybrid` (both, Reciprocal Rank Fusion) |
| `hybrid_alpha` | 0.5 | Weight of the dense list in hybrid fusion |
| `fetch_k` | 20 | Candidate pool before reranking / MMR / top-k |
| `query_transform` | `none` | `multi_query`, `hyde` or `step_back` (one extra LLM call) |
| `rerank` | `none` | `llm` = generation model scores the pool; NVIDIA rerank models appear when your key can use one |
| `context_window` | 0 | Neighbouring chunks (±n) added around each hit |
| `context_order` | `score` | `document` order or `sandwich` (strongest chunks at both ends) |
| `max_context_tokens` | 0 | Context budget (~4 chars/token); 0 = unlimited |
| `source_filter` | — | Only search chunks from one ingested file |
| `entity_match` / `graph_direction` | `contains` / `both` | Graph seed matching and traversal direction |
| `contextual_headers` | off | Ingest-time: an LLM line situating each chunk in its document is prepended before embedding |

### Generation

| Param | Default | Range | Description |
|---|---|---|---|
| `temperature` | 0.3 | 0–2 | Sampling temperature |
| `max_output_tokens` | 1024 | 1–8192 | Maximum tokens in the answer |
| `check_groundedness` | off | — | After answering, an LLM judge checks each claim against the context |

---

## Tests and lint

Everything runs in containers. Backend (from the repo root):

```bash
docker build -f backend/Dockerfile.dev -t arena-backend-dev backend      # once, and when dependencies change
docker run --rm -v "$PWD":/work -w /work/backend arena-backend-dev python -m pytest -q
docker run --rm -v "$PWD":/work -w /work/backend arena-backend-dev sh -c 'ruff check . && ruff format --check .'
```

Frontend:

```bash
docker run --rm -v "$PWD/frontend":/web -v arena_fe_node_modules:/web/node_modules -w /web node:22-alpine \
  sh -c 'npm ci && npm run lint && npm run typecheck && npm test -- --run && npm run build'
```

CI (`.github/workflows/ci.yml`) runs the same steps plus `alembic upgrade head` / `alembic check` and a Docker build.
See [backend/README.md](backend/README.md) for the test layout and parity snapshots.

---

## Resetting data

```bash
docker compose down -v   # wipes ChromaDB, Neo4j and the app database (keys, bots, history)
docker compose up
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `CHROMA_HOST` | `localhost` | ChromaDB host |
| `CHROMA_PORT` | `8000` | ChromaDB port |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `playground123` | Neo4j password |
| `DEFAULT_GEN_MODEL` | `gemini-2.5-flash` | Default generation model |
| `DEFAULT_EMBED_MODEL` | `gemini-embedding-001` | Default embedding model |
| `ARENA_DB_PATH` | `arena.db` (Docker: `/app/arena_data/arena.db`) | SQLite file for keys, bots, conversations, history |
| `AUTO_MIGRATE` | `true` | Run database migrations on startup (backs up a pre-migration database first) |
| `ARENA_SPA_DIR` | `frontend/dist` (Docker: `/app/frontend_dist`) | Built React app served at `/app/` |
| `LOG_FORMAT` | `json` | `json` lines or `console` |
| `LOG_LEVEL` | `INFO` | Root log level |
| `READYZ_TIMEOUT_S` | `2` | Per-check timeout for `/readyz` |
| `ALLOW_STDIO_MCP` | `false` | Allow stdio MCP servers (they run commands in the container) |
| `MCP_ALLOWED_HOSTS` | `localhost:*,127.0.0.1:*,[::1]:*` | Host headers accepted by the built-in MCP server |

The only value you typically need to change is `NEO4J_PASSWORD` (if you override `NEO4J_AUTH` in Docker Compose).

---

## License

MIT
