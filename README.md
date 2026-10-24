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

- **Three retrieval modes** — Chroma (vector + MMR), Graph (Neo4j BFS), Compare (both simultaneously)
- **Live SSE event stream** — chunk cards and graph edges animate in real time during retrieval
- **Dual-answer Compare mode** — identical question, both backends, side-by-side streaming answers
- **Tunable everything** — chunk size, overlap, strategy, top-k, similarity threshold, MMR λ, graph hops, temperature, max tokens
- **Two chunking strategies** — fixed sliding-window and sentence/paragraph-aware
- **PDF + plain text ingestion** — single ingest populates both stores
- **Model selection** — key validation fetches live Gemini model lists; pick any generation or embedding model
- **No build step** — Alpine.js served from disk; plain HTML/CSS/JS frontend

---

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

---

## Quick start

**Prerequisites:** Docker Desktop · Google Gemini API key ([get one free](https://aistudio.google.com/app/apikey))

```bash
# 1. Clone
git clone https://github.com/li812/retrieval-arena.git
cd retrieval-arena

# 2. Fetch vendored frontend assets (Alpine.js, vis-network, fonts)
bash scripts/fetch_vendor_assets.sh

# 3. (Optional) copy and edit env
cp .env.example .env

# 4. Start everything
docker compose up --build
```

Open **http://localhost:8000** — Neo4j takes ~30 s to initialise on first boot.

### Exposed ports

| Service | Port | Purpose |
|---|---|---|
| API (FastAPI) | 8000 | Main app |
| ChromaDB | 8001 | Direct queries / debug |
| Neo4j Browser | 7474 | Visual graph explorer |
| Neo4j Bolt | 7687 | Driver access |

---

## Using the app

### 1. Configure your API key

Click **⚙** (top-right). Paste your Gemini API key and click **Test**. On success the generation-model and embedding-model dropdowns populate from the live API.

> Your key lives only in browser memory — it is never written to disk or logged server-side.

### 2. Ingest a document

Open the **Ingest** panel in the sidebar. Enter a collection name, paste text or upload a `.txt`/`.pdf` file, then click **Ingest**. One call populates both ChromaDB and Neo4j simultaneously, so you can switch backends per-query without re-ingesting.

### 3. Query

Type a question in the bar at the bottom and press **Enter**. Switch between modes with the header buttons:

- **⚡ CHROMA** — chunk cards appear and score bars fill as `chunk_scored` events stream in
- **◆ GRAPH** — entity nodes and relationship edges draw hop-by-hop as `hop_traversed` events arrive
- **⚔ COMPARE** — both panels run simultaneously; two streaming answers appear side-by-side

---

## Architecture

```
main.py                     FastAPI routes, SSE orchestration, Compare multiplexer
app/services/
  chunking.py               ChunkingService — fixed + sentence_aware strategies
  embeddings.py             EmbeddingAgent — Gemini embed calls
  generation.py             GenerationAgent — streaming Gemini generate
  vector_store.py           VectorStore — ChromaDB HttpClient wrapper
  graph_store.py            GraphStore — Neo4j driver, BFS traversal
  extraction.py             GraphExtractionAgent — triple + entity extraction via Gemini
  ingestion.py              IngestionAgent — fan-out to both stores in one call
  retrieval.py              RetrievalAgent — Chroma MMR + Graph hop BFS, emits SSE events
  model_config.py           ModelConfigAgent — key validation, model listing
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

### Generation

| Param | Default | Range | Description |
|---|---|---|---|
| `temperature` | 0.3 | 0–2 | Gemini temperature |
| `max_output_tokens` | 1024 | 1–8192 | Maximum tokens in the answer |

---

## Resetting data

```bash
docker compose down -v   # wipes both ChromaDB and Neo4j volumes
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

The only value you typically need to change is `NEO4J_PASSWORD` (if you override `NEO4J_AUTH` in Docker Compose).

---

## License

MIT
