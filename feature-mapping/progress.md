# Progress

The project manager agent maintains this file. Status: ⬜ todo · 🔄 in progress · ✅ done · ⛔ blocked.

| Milestone | Status | Branch / PR | QA |
|---|---|---|---|
| M1 Foundation | 🔄 | `platform` | — |
| M2 Accounts, workspaces, secrets | ⬜ | — | — |
| M3 Providers | ⬜ | — | — |
| M4 Personas, bots v2, runtime | ⬜ | — | — |
| M5 Delivery: REST + gRPC | ⬜ | — | — |
| M6 Webhooks & jobs | ⬜ | — | — |
| M7 Dashboard completion | ⬜ | — | — |
| M8 Observability, capacity & hardening | ⬜ | — | — |
| M9 Embeddable widget | ⬜ | — | — |

---

## M1 — Foundation 🔄

**Goal:** new structure, today's behaviour unchanged. **Features:** UI-1, OBS-4, plus the M1 platform work in `08-roadmap.md` (layout, DB, tests, CI, Docker) and DOC-1 for what ships. **Branch:** `platform` (the roadmap says branch off `dev-beta`; this milestone runs on `platform` as instructed).

**Ground rules for M1**
- Parity first: no endpoint path, request shape, response shape or SSE event sequence changes. The Alpine UI stays at `/` and `/static/*`; the new SPA is served at `/app/`. `/mcp/` stays where it is.
- No workspace scoping, auth, encryption or provider refactor yet (M2/M3). Legacy tables keep their current names and columns.
- The live `arena.db` in the `arena_data` volume must survive the upgrade with no data loss.
- Proposed (not yet in `09-decisions.md`): M1 uses a **sync** SQLAlchemy engine/session (the legacy code runs DB calls in threads). Revisit async when the runtime is rewritten in M4.

Format: `ID · owner · features · depends on — task`. Owners: **BE** backend-engineer (owns `backend/`, `Dockerfile`, `docker-compose.yml`, `.github/`, `scripts/`, `docs/`, root files, removal of `app/`), **FE** frontend-engineer (owns `frontend/` only), **QA** qa-engineer.

### Backend

- [x] **B1** · BE · M1-infra · — — Scaffold `backend/`: `pyproject.toml` (runtime deps from `requirements.txt` + `sqlalchemy>=2.0`, `alembic`; `[dev]` extra: `pytest`, `pytest-asyncio`, `httpx`, `ruff`), ruff config (line length 120; rules E, F, I, UP, B; `ruff format`), empty packages `backend/app/{core,models,repositories,providers,rag,runtime,mcp,api,grpc,jobs}/__init__.py`, `backend/tests/{unit,integration,contract,isolation,parity,fixtures,fakes}/`, `backend/tests/conftest.py`.
- [x] **B2** · BE · M1-exit · B1 — **Characterization tests against today's `app/` before moving anything.** Fakes in `backend/tests/fakes/providers.py` (deterministic hash `FakeEmbedding` with configurable dim, `FakeGeneration` with scripted token streams incl. one scripted tool call through the NVIDIA/OpenAI tool loop, `FakeExtraction` with fixed triples/entities, fake `ModelConfigAgent`) and `backend/tests/fakes/stores.py` (`InMemoryVectorStore`, `InMemoryGraphStore`), injected by monkeypatching the module singletons in `app/main.py:46-58`. Parity tests in `backend/tests/parity/` cover every endpoint in the parity list below and record status codes, JSON key shapes and SSE event-type sequences to `backend/tests/parity/snapshots/*.json`. Commit the snapshots.
- [x] **B3** · BE · M1-infra · B2 — Move code with `git mv` (keep history), fixing imports only: `config.py`→`core/config.py`; `schemas.py`→`api/schemas.py`; `chunking, vector_store, graph_store, hybrid, retrieval, rerank, evaluation, sentiment, ingestion, extraction`→`rag/`; `embeddings, generation, model_config`→`providers/` (unchanged; refactor is M3); `chat.py`→`runtime/chat.py`; `mcp_client.py`→`mcp/client.py`; `mcp_server.py`→`mcp/server.py`; `app/static/`→`backend/app/static/` (Alpine UI, unchanged).
- [x] **B4** · BE · M1-infra · B3 — App factory: `backend/app/main.py` exposes `create_app(settings=None, services=None) -> FastAPI` and module-level `app = create_app()`. `core/container.py` holds a `Services` dataclass that builds today's singletons and accepts overrides (fakes in tests). Split `main.py` routes into `api/legacy/{keys,ingest,query,collections,history,analyze,bots,chat,mcp_servers,config}.py` at the **same paths**; helpers `_sse`, `_drain` → `api/streaming.py`, `_resolve_key`, `_embedding_mismatch` → `api/deps.py`; provider error handler → `api/errors.py`. Alpine at `/` + `/static`, MCP at `/mcp`. Resolve file paths from `Path(__file__)`, never the CWD.
- [x] **B5** · BE · M1-infra · B4 — Settings in `core/config.py`: move to pydantic-settings v2 `model_config` (drop `class Config`); add `log_level`, `log_format` (`json`|`console`), `spa_dir`, `auto_migrate` (default true), `readyz_timeout_s` (default 2). Update `.env.example`.
- [x] **B6** · BE · M1-infra · B5 — `core/db.py`: sync SQLAlchemy 2 engine (`sqlite+pysqlite`), `connect` event sets `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`; `sessionmaker` + `session_scope()`; engine disposed in lifespan. Unit test asserts all three pragmas on a new connection.
- [x] **B7** · BE · M1-infra · B6 — Models: `models/base.py` (`DeclarativeBase`, naming convention) and `models/legacy.py` mapping the 7 existing tables **exactly** as `key_store.py`/`bot_store.py` create them (names, types, NOT NULL, `server_default=text("(datetime('now'))")`, UNIQUE on `api_keys.label`, `bots.name`, `mcp_servers.name`, FKs `conversations.bot_id`→`bots` and `messages.conversation_id`→`conversations` with ON DELETE CASCADE). Classes: `ProviderKey` (table `api_keys`; named to avoid clashing with M2's delivery API keys), `CollectionRecord`, `HistoryEntry`, `Bot`, `Conversation`, `Message`, `McpServer`.
- [x] **B8** · BE · M1-infra · B7 — Alembic: `backend/alembic.ini`, `backend/alembic/env.py` (URL from settings, `render_as_batch=True`, `target_metadata = Base.metadata`), revision `0001_legacy_baseline` that creates each table **only if** `sa.inspect(bind).has_table()` is false, so `upgrade head` works on fresh and live DBs. `core/db.py:run_migrations()` runs from the lifespan when `auto_migrate`; if the DB has legacy tables but no `alembic_version`, it first makes an online `sqlite3` backup to `arena.db.pre-alembic-<UTC timestamp>.bak`. Tests: (a) fresh DB → 7 tables + `alembic_version`; (b) DB built from verbatim legacy DDL (`tests/fixtures/legacy_schema.sql`, copied from today's stores) seeded with rows in every table → upgrade → identical rows, backup file present; (c) `alembic check` reports no drift for both; (d) running upgrade twice is a no-op.
- [x] **B9** · BE · M1-infra · B4, B8 — Repositories replacing the stores: `repositories/{provider_keys,collections,history,bots,conversations,mcp_servers}.py` (`conversations.py` also covers messages, feedback, `delete_last_assistant`) with the **same method names and returned dict shapes** as `KeyStore`/`BotStore` (JSON decoding of `tuning`, `starters`, `tools`, `args`, `env`, `headers`; int→bool as today). Constructors take a `sessionmaker`; no workspace scope yet (M2). Duplicate names raise `core/errors.py:DuplicateNameError`, mapped to the same 409 messages as `main.py:677/687/826`. `rag/ingestion.py` uses `CollectionRepository`. Unit tests in `tests/unit/repositories/`. Delete `key_store.py`, `bot_store.py`; no `sqlite3` import left in app code except the backup helper.
- [x] **B10** · BE · OBS-4 · B4, B8 — Logging and health. `core/logging.py`: stdlib logging with JSON formatter (`ts, level, logger, msg, request_id, run_id` + extras) and a console formatter, chosen by `log_format`. `api/middleware.py`: request-id middleware (accept/echo `X-Request-ID`, contextvar) and one access line per request (`method, path, status, duration_ms`); a `run_id` is generated per `/query` and `/chat` stream and bound to its log lines. `api/health.py`: `GET /healthz` → 200 `{"status":"ok"}` with no dependency calls; `GET /readyz` → checks `sqlite` (`SELECT 1` and alembic revision == head), `chroma` (heartbeat), `neo4j` (`verify_connectivity`), each with `readyz_timeout_s`; 200 if all ok, else 503; body `{"status", "checks": {name: {"ok", "latency_ms", "error"}}}`. Tests with fake deps up and down.
- [x] **B11** · BE · UI-1 · B4 — Serve the SPA from `settings.spa_dir` at `/app/`: `/app/assets/*` as static files, `/app/{path:path}` falls back to `index.html` (deep links work on reload), `/app` → 307 `/app/`. If the build is missing, `/app/` returns 503 with a "frontend not built" message and the API still starts. Legacy `/`, `/static`, `/mcp` untouched. Tests with a temp dist dir and with none.
- [x] **B12** · BE · M1-infra · B11, F1 — Docker. Multi-stage `Dockerfile`: stage `web` (`node:20-alpine`, `npm ci && npm run build` in `frontend/`), stage `api` (`python:3.11-slim`, wget, `pip install ./backend`, vendor fetch into `backend/app/static/vendor`, copy `backend/`, copy `--from=web` dist to `/app/frontend_dist`), `WORKDIR /app/backend`, CMD runs uvicorn `app.main:app`. `docker-compose.yml`: bind mounts and `develop.watch` re-pointed at `backend/app`; `ARENA_DB_PATH=/app/arena_data/arena.db` (**absolute; the `arena_data` mount at `/app/arena_data` must not move**); `ARENA_SPA_DIR=/app/frontend_dist`; api healthcheck on `/healthz`. Update `scripts/fetch_vendor_assets.sh` (`VENDOR` path), `.gitignore` (`backend/app/static/vendor/`, `frontend/node_modules/`, `frontend/dist/`), add `.dockerignore`.
- [x] **B13** · BE · M1-infra · B1, F1 — CI: `.github/workflows/ci.yml` on push and PR to `main`, `dev-beta`, `platform`. Job `backend` (Python 3.11, `pip install -e backend[dev]`, `ruff check`, `ruff format --check`, `alembic upgrade head` on a temp DB, `pytest`; no Chroma/Neo4j needed). Job `frontend` (Node 20, `npm ci`, `npm run lint`, `npm run typecheck`, `npm test -- --run`, `npm run build`). Job `docker` (`docker build .`, needs both).
- [x] **B14** · BE · M1-exit · B9–B12 — Re-point the parity suite from the monkeypatched legacy app to `create_app(services=fakes)` and make it pass against the B2 snapshots **without editing the snapshots** (any snapshot change must be listed and justified in the report). Then delete the old `app/` directory and root `requirements.txt`, and update `README.md` (run instructions, backend path, `/app/` shell, `/healthz` `/readyz`, test and lint commands).
- [x] **B15** · BE · DOC-1 · B14, F6 — Docs: `docs/user-guide/getting-started.md` (run with compose; classic UI at `/`, new shell at `/app/`, theme and command palette) and `docs/operator/upgrading-to-m1.md` (what happens to `arena.db` on first start, the `.bak` file and how to roll back, health endpoints, log format and level).

### Frontend

- [x] **F1** · FE · UI-1 · — — Scaffold `frontend/`: Vite + React 18 + TypeScript (strict), `base: '/app/'`; React Router (`createBrowserRouter`, `basename: '/app'`); ESLint (typescript-eslint, react-hooks) + Prettier; Vitest + Testing Library + jsdom; scripts `dev`, `build`, `lint`, `typecheck`, `test`; folders `src/{app,routes,features,components,lib,styles}/`; dev proxy to `http://localhost:8000` for `/keys /ingest /query /collections /history /analyze /bots /conversations /messages /chat /mcp-servers /mcp-tools /config /mcp /healthz /readyz /static`; commit `package-lock.json`.
- [x] **F2** · FE · UI-1 · F1 — Theme: copy every custom property from `app/static/style.css` `:root` and `:root[data-theme="light"]` into `src/styles/tokens.css` with **identical names and values**; base styles (body, focus ring, scrollbars, selection) in `src/styles/base.css`; Inter and JetBrains Mono via `@fontsource/*` (no CDN). `src/lib/theme.ts` + `ThemeProvider`: modes `auto | light | dark`, stored in localStorage key `arena.theme` (same key as the Alpine UI, so the preference is shared), sets `document.documentElement.dataset.theme`, follows `prefers-color-scheme` live in auto; inline pre-paint script in `index.html` so there's no flash. Unit tests for mode resolution and persistence.
- [x] **F3** · FE · UI-1, UX-4 · F2 — Layout and routing: `src/app/AppShell.tsx` (sidebar nav, top bar, content outlet); routes `src/routes/{Home,Bots,Collections,Lab,Settings,NotFound}.tsx`. Non-Home pages are placeholders, each with an empty state and one next action (e.g. "The Lab is in the classic UI for now → Open classic UI" linking to `/`). `RequireAuth` guard component that passes through in M1 (wired to the session in M2).
- [x] **F4** · FE · UI-1 · F1 — API layer: `src/lib/api/client.ts` typed fetch wrapper (base from `import.meta.env.VITE_API_BASE`, default `''`, so M2's `/api` prefix is a one-line change; non-2xx → `ApiError{status, detail}`; sends `X-Request-ID`); `src/lib/api/types.ts` hand-written types for the legacy responses used; `src/lib/api/sse.ts` POST-SSE reader for the later `/query` and `/chat` ports; TanStack Query `QueryClientProvider` in `src/app/providers.tsx` (retry 1, staleTime 30 s, Devtools in dev only); hooks `useReadiness()` (`/readyz`), `useCollections()` (`/collections`), `useBots()` (`/bots`) in `src/features/{system,collections,bots}/api.ts`. Tests with mocked fetch.
- [x] **F5** · FE · UI-1, UX-3 · F3, F4, B10 — Home page: per-check readiness (SQLite, Chroma, Neo4j) from `/readyz`, collection and bot counts, with loading, error and empty states; a "?" tooltip on each status explaining it.
- [x] **F6** · FE · UI-1 · F3 — Command palette (`src/components/CommandPalette.tsx`, Ctrl/Cmd+K: go to each route, cycle theme, open classic UI; arrow/Enter/Esc, focus trap, screen-reader labels) and toasts (`src/components/toast/`), with API errors surfaced through a global `QueryCache` `onError`. Tests for keyboard flow.

### QA

- [x] **Q1** · QA · M1-exit · B2 — Review the B2 parity list and snapshots against the checklist below before the move starts. Report missing endpoints or modes.
- [x] **Q2** · QA · all · B14, B15, F5, F6 — Run the exit checklist below on a clean clone, plus the live-data adoption test, and report each item as met / not met / met with caveat with evidence (commands and output, screenshots).

### Parity list (B2/B14 must cover all of it)

- Keys: `GET/POST /keys`, `DELETE /keys/{id}`, `POST /keys/{id}/activate`, `POST /config/validate-key`.
- Ingest: `POST /ingest` with a `.txt` and a `.pdf`, chunking strategies, into a vector-only and a graph-enabled collection.
- Query (`POST /query`, SSE): `backend` = `chroma`, `graph`, `compare`; `search_mode` dense / hybrid / keyword; `query_transform` none / multi_query / hyde / step_back; `rerank` none / llm; `context_order` score / document / sandwich; graph `entity_match` contains / exact / fuzzy and `graph_direction` out / both; the embedding dimension and model mismatch errors.
- Collections: `GET /collections`, `DELETE /collections/{name}`.
- History: `GET /history` (with `q`), `POST /history`, `POST /history/{id}/pin`, `DELETE /history/{id}`. Analyze: `POST /analyze/emotion`.
- Bots and chat: `GET/POST /bots`, `PUT/DELETE /bots/{id}` incl. duplicate-name 409; `GET /bots/{id}/conversations`; `GET/DELETE /conversations/{id}`; `POST /messages/{id}/feedback`; `POST /chat` (SSE) for a new conversation, a follow-up (rewrite), preview mode with client-held history, and a turn with one MCP tool call.
- MCP: `GET/POST /mcp-servers` incl. 409, `POST /mcp-servers/{id}/enabled`, `DELETE /mcp-servers/{id}`, `GET /mcp-servers/{id}/tools`, `GET /mcp-tools`, `POST /config/tool-support`; built-in `/mcp/` (initialize, list 4 tools, call each), using a uvicorn instance on a random port (the app's own `/mcp/` can be the registered server).
- `GET /` serves the Alpine `index.html`; `/static/*` assets load.

### Exit checklist (QA)

- [x] `pytest` passes in `backend/`, including every item in the parity list, with no network access to providers, Chroma or Neo4j.
- [x] Parity snapshots unchanged between B2 (legacy app) and B14 (new app), or each change justified.
- [x] `alembic upgrade head` works on a fresh database; `alembic check` shows no drift.
- [x] Adoption: a copy of the live `arena.db` (taken from the `arena_data` volume with `sqlite3 .backup`) upgrades with identical row counts in all 7 tables, a `.pre-alembic-*.bak` file is created, and a second start is a no-op.
- [x] SQLite pragmas on the app's connections: `journal_mode=wal`, `busy_timeout=5000`, `foreign_keys=1`. Deleting a bot cascades to its conversations and messages.
- [x] No `key_store.py` / `bot_store.py`; no `sqlite3` use in app code outside the backup helper; old `app/` and root `requirements.txt` are gone.
- [x] `ruff check` and `ruff format --check` are clean; frontend `lint`, `typecheck`, `test`, `build` pass.
- [ ] GitHub Actions run is green on `platform` (link the run). _QA: not yet verifiable — pending push._
- [x] `docker compose up --build` from a clean clone: api becomes healthy; `/healthz` 200; `/readyz` 200 with all three checks ok; stopping `neo4j` makes `/readyz` 503 naming neo4j while `/healthz` stays 200.
- [x] Logs are JSON lines with `request_id`; a `/chat` and a `/query` request log a `run_id`; `X-Request-ID` is echoed.
- [x] With the existing `arena_data` volume, the classic UI at `/` shows the same keys, collections, bots, conversations, history and MCP servers as before the upgrade, and these flows work by hand: ingest, query in each backend including Compare, chat with a bot, history pin/delete.
- [x] SPA at `/app/`: loads from the Docker image; deep link `/app/settings` survives reload; unknown route shows 404 page; `/app` redirects to `/app/`.
- [x] Theme: auto / light / dark work, auto follows the OS live, no flash on load, and the choice is shared with the classic UI (same `arena.theme` key). Tokens match `style.css`.
- [x] Command palette is fully keyboard-operable; API errors show a toast; Home shows readiness and counts; every placeholder page has an empty state with one action; status indicators have tooltips.
- [x] Docs from B15 exist and match what was shipped.

### Risks and notes

- **Data loss on adoption.** Mitigated by create-if-not-exists baseline, the automatic `.bak`, the B8 tests and the QA live-copy test. Do not drop or rename legacy columns in M1.
- **DB path moves with the code.** Today `ARENA_DB_PATH` is relative to `/app`; after the move the CWD is `/app/backend`. B12 makes it absolute; QA confirms the existing volume is picked up and no new empty `arena.db` appears.
- **Name clash for M2.** The legacy `api_keys` table holds provider keys; M2's `api_keys` holds delivery keys. M2's `migrate-legacy` must rename or move the legacy table first. Logged here for M2 planning.
- **Fakes vs reality.** Parity tests run on fakes; the manual classic-UI check in Q2 covers real Gemini/NVIDIA calls where a key is available.
- **UI-1 auth guard** is a pass-through stub in M1; real wiring is in M2 (UI-2 / AUTH-*). Layout, theme, palette, toasts and routing are fully in scope now.
