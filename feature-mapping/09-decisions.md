# 09 — Decisions & open questions

## Decisions

| # | Decision | Why | Date |
|---|---|---|---|
| D1 | **One account type, one isolated workspace per user, open signup** | Self-hosters run it for themselves or a group; there are no roles to manage | 2026-10-24 |
| D2 | **SQLite only**, via SQLAlchemy 2 + Alembic | Simplest to self-host; the ORM and repositories keep a future database switch contained | 2026-10-24 |
| D3 | **Keep Chroma for vectors and Neo4j for graphs**, namespaced per workspace | Follows from D2; reuses the working Lab pipeline | 2026-10-24 |
| D4 | **REST and gRPC built together** on one runtime | Both are first-class integration paths; one runtime keeps them identical | 2026-10-24 |
| D5 | **Personas are a reusable layer** attached to bots; published versions snapshot persona content | Reuse across bots without published bots changing silently | 2026-10-24 |
| D6 | **Webhooks = async invoke with callback + event subscriptions**; no inbound channel adapters yet | Covers backend integrations; channel adapters are a large separate scope | 2026-10-24 |
| D7 | **React + Vite + TypeScript** dashboard replacing Alpine | The dashboard outgrows a single Alpine component | 2026-10-24 |
| D8 | **Providers: OpenAI, Anthropic, Gemini, NVIDIA, Ollama** behind one interface | User requirement; removes scattered provider branches | 2026-10-24 |
| D9 | **AES-256-GCM field encryption with the master key in the environment** | The key never sits in the same volume as the data; row-bound AAD stops ciphertext swapping | 2026-10-24 |
| D10 | **Draft / publish with immutable versions** | External products need stable behaviour while bots are edited | 2026-10-24 |
| D11 | **OpenAI-compatible endpoint** alongside the native API | Existing OpenAI SDKs and tools work with no new client code | 2026-10-24 |
| D12 | **In-process job worker on a SQLite queue** (no Redis or Celery) | Follows from D2; fewer moving parts | 2026-10-24 |
| D13 | **stdio MCP stays opt-in and single-tenant only** | On a multi-user install it would let any user run commands on the host | 2026-10-24 |
| D14 | **Conversation content is stored by default, and users choose the retention**: 7, 30, 90 (default), 180 or 365 days, forever, or metadata-only; per workspace with a per-bot override (WS-7) | User choice (was Q1) | 2026-10-25 |
| D15 | **Capacity is configurable and guided**: the app profiles the server (CPU, RAM, disk, cgroup limits, store benchmarks), recommends limits with its reasoning, and offers an infrastructure calculator (OPS-1–6). No fixed load target | User choice (was Q2) | 2026-10-25 |
| D16 | **The caller chooses the conversation mode per request**: new (server returns an id), continue (`conversation_id`), or stateless (inline `history`). Server-side context requires a `conversation_id` (BOT-10) | User choice (was Q4) | 2026-10-25 |
| D17 | **gRPC TLS supports `off`, `app` and `proxy` modes, editable in the UI**; each bot's endpoints are configurable (interfaces on/off, timeouts, limits, CORS, conversation defaults) (GRPC-7, BOT-9) | User choice (was Q5) | 2026-10-25 |
| D18 | **Embeddable widget is in scope as M9** | User choice (was Q6) | 2026-10-25 |
| D19 | **The first account on an install is the instance owner** for the instance settings page only; others see those settings read-only; transfer with `arena instance transfer-owner` | Accepted default (was Q9) | 2026-10-25 |
| D20 | **Ease of use is a requirement**: setup wizard, page tours, contextual help, Simple/Advanced mode, templates, a user guide written alongside each feature | User requirement | 2026-10-25 |
| D21 | **Work is run by four project agents** (`.claude/agents/`): project manager, backend engineer, frontend engineer, QA engineer | User requirement | 2026-10-25 |
| D22 | **Sync SQLAlchemy engine** in M1 (calls run in worker threads, as today); revisit if the async runtime (M4) needs an async session | Matches current threading model; least risk during the move | 2026-10-25 |
| D23 | **All milestones land on the `platform` branch** (one PR into `dev-beta` per milestone) instead of a branch per milestone | Keeps the long refactor on one line of history | 2026-10-25 |
| D24 | **Node 22** for the frontend build stage, the dev container and CI (Node 20 reached end of life in April 2026); `engines.node >=20.19` keeps local Node 20 working | QA finding F7 (M1) | 2026-10-25 |

## Open questions

| # | Question | Default if not decided |
|---|---|---|
| Q3 | Open signup on internet-facing installs: is per-IP rate limiting plus proxy guidance enough? | Keep signup open (D1); revisit if spam appears |
| Q7 | Price table for cost estimates (also used by the calculator): maintained by hand, or user-editable? | Ship a starter table; user-editable per model |
| Q8 | Keep VADER for sentiment, or switch to an LLM or small classifier? | Keep VADER (free, local); the LLM emotion option stays |

## Superseded

| # | Was | Replaced by |
|---|---|---|
| S1 | Single unauthenticated app with plaintext keys in SQLite | D1, D9 |
| S2 | One active key per provider picked in the browser | Credentials per workspace (PROV-7) |
| S3 | Bot edits apply to live traffic immediately | D10 |
