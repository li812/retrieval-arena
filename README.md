# Retrieval Arena

A local RAG playground where you ingest documents once and pit **ChromaDB (vector search)** against **Neo4j (knowledge graph)** head-to-head — watching each retrieval strategy animate in real time as your question is answered.

```
┌─────────────────────────────────────────────────┐
│ RETRIEVAL ARENA  [CHROMA ⚡] [GRAPH ◆]  [⚙]    │
├─────────────────┬───────────────────────────────┤
│ Tuning sliders  │  Chunk cards light up          │
│ Ingest panel    │  (Chroma) or graph edges draw  │
│                 │  hop-by-hop (Knowledge Graph)  │
├─────────────────┴───────────────────────────────┤
│  Streaming answer with inline citations         │
└─────────────────────────────────────────────────┘
```

## Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI 0.111+ (Python 3.11) |
| Vector store | ChromaDB (server mode, `HttpClient`) |
| Knowledge graph | Neo4j 5 |
| LLM / Embeddings | Google Gemini via `google-genai` SDK |
| Frontend | Alpine.js 3 — no build step |
| Graph viz | vis-network 9 |
| Orchestration | Docker Compose |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker + Docker Compose v2)
- A **Google Gemini API key** — get one free at [aistudio.google.com](https://aistudio.google.com/app/apikey)

## Quick start

```bash
# 1. Clone
git clone https://github.com/your-org/retrieval-arena
cd retrieval-arena

# 2. Fetch vendored frontend assets (Alpine.js, vis-network, fonts)
bash scripts/fetch_vendor_assets.sh

# 3. (Optional) copy and edit env
cp .env.example .env

# 4. Start everything
docker-compose up --build
```

Open **http://localhost:8000** in your browser.

> **Note:** Neo4j takes 20–30 s to initialise on first boot. The API container waits for both stores to be healthy before starting.

### Ports exposed

| Service | Port | Purpose |
|---|---|---|
| API (FastAPI) | 8000 | Main app |
| ChromaDB | 8001 | Debug / direct queries |
| Neo4j Browser | 7474 | Visual graph explorer |
| Neo4j Bolt | 7687 | Driver access |

## Using the UI

### 1. Configure your API key

Click the **⚙ gear icon** (top-right). Paste your Gemini API key and click **Test Key**. On success the generation-model and embedding-model dropdowns populate from the live Gemini API — pick the models you want (defaults: `gemini-2.5-flash` / `gemini-embedding-001`).

Your key lives only in browser memory for the session — it is never persisted to disk or logged server-side.

### 2. Ingest a document

In the **Ingest** panel (sidebar): enter a collection name, paste text or upload a `.txt`/`.pdf` file, then click **Ingest**. One ingest call populates **both** ChromaDB and Neo4j simultaneously, so you can switch backends per-query without re-ingesting.

### 3. Query

Type a question in the query bar at the bottom and press **Enter** or click **Query**. Toggle between **CHROMA ⚡** and **GRAPH ◆** in the header to switch retrieval mode. The retrieval panel animates in real time:

- **Chroma mode** — chunk cards appear and light up with score bars as `chunk_scored` events stream in
- **Graph mode** — entity nodes and relationship edges draw hop-by-hop as `hop_traversed` events arrive

The answer streams token-by-token from Gemini once retrieval is complete.

## Tuning parameters

All parameters are adjustable in the sidebar before each query (or ingest for chunking params).

### Chunking *(applies at ingest time)*

| Param | Default | Description |
|---|---|---|
| `chunk_size` | 800 | Target characters per chunk |
| `chunk_overlap` | 120 | Overlap between consecutive chunks |
| `chunking_strategy` | `fixed` | `fixed` = sliding window; `sentence_aware` = breaks on sentence/paragraph boundaries |

### Retrieval — Chroma

| Param | Default | Description |
|---|---|---|
| `top_k` | 5 | Chunks returned after MMR re-ranking |
| `similarity_threshold` | 0.0 | Discard chunks below this score (0 = keep all) |
| `mmr_diversity` | 0.5 | MMR λ — 0 = pure relevance, 1 = pure diversity |

### Retrieval — Knowledge Graph

| Param | Default | Description |
|---|---|---|
| `graph_hops` | 1 | BFS depth from seed entities |
| `max_triples_per_chunk` | 8 | Triples extracted per chunk at ingest |
| `triple_limit` | 25 | Max triples returned per query |

### Generation

| Param | Default | Description |
|---|---|---|
| `temperature` | 0.3 | Gemini temperature |
| `max_output_tokens` | 1024 | Maximum tokens in the answer |

**Generation model** and **embedding model** are set once in the ⚙ settings panel and shared across all calls.

## Architecture

```
main.py                  — FastAPI routes, SSE orchestration
app/services/
  chunking.py            — ChunkingService (fixed + sentence_aware strategies)
  embeddings.py          — EmbeddingAgent (all Gemini embed calls, batched)
  generation.py          — GenerationAgent (streaming Gemini generate)
  vector_store.py        — VectorStore (ChromaDB HttpClient wrapper)
  graph_store.py         — GraphStore (Neo4j driver wrapper, BFS traversal)
  extraction.py          — GraphExtractionAgent (triple + entity extraction via Gemini)
  ingestion.py           — IngestionAgent (fan-out to both stores)
  retrieval.py           — RetrievalAgent (Chroma MMR + Graph hop BFS, emits SSE events)
  model_config.py        — ModelConfigAgent (key validation, model listing)
```

**Data flow — Ingest:**
`text` → chunk → embed (Gemini) → Chroma `add()` + Neo4j `MERGE` triples (extracted by Gemini)

**Data flow — Query:**
`question` → embed → Chroma similarity+MMR *or* Neo4j entity-match+BFS → SSE event stream → Gemini streaming answer → SSE token stream

## Resetting data

```bash
# Wipe both stores and restart fresh
docker-compose down -v
docker-compose up
```

## Environment variables

See `.env.example`. The only required customisation is the Neo4j password if you change it from the default `playground123`.
