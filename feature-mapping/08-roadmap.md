# 08 — Roadmap

Every milestone runs on its own branch off `dev-beta` and ends in one PR. Feature IDs refer to `02-feature-map.md`.

**Definition of done for every milestone:**
- The exit criteria are met.
- QA has signed off.
- The user-guide section for each shipped feature exists (DOC-1).
- New UI has tooltips and empty states (UX-3, UX-4).
- `progress.md` is updated.

```
M1 Foundation ──► M2 Accounts·Workspaces·Secrets ──► M3 Providers ──► M4 Personas·Bots·Runtime ──► M5 REST+gRPC
                                                                                                    │
                    M9 Widget ◄── M8 Capacity·Hardening ◄── M7 Dashboard completion ◄── M6 Webhooks·Jobs
```

## M1 — Foundation
**Goal:** a new structure with today's behaviour unchanged.
- **Backend:**
  - Move `app/` to `backend/app/` in the package layout from `03-architecture.md`.
  - App factory and settings.
  - SQLAlchemy 2 models for today's tables, and an Alembic baseline.
  - SQLite pragmas (WAL, `busy_timeout`, foreign keys).
  - Repository layer.
  - Structured logging, `/healthz` and `/readyz` (OBS-4).
- **Tests:** pytest with fake providers; ruff; GitHub Actions running lint and tests.
- **Frontend:** React + Vite + TypeScript shell (UI-1) with routing, the theme tokens ported from `style.css`, an API client and TanStack Query. The Alpine UI is still served for now.
- **Docker:** a multi-stage build where the API serves the built SPA.

**Exit criteria:**
- Parity tests cover today's ingest, query (all modes), chat, history and MCP endpoints.
- `alembic upgrade head` works on a fresh database.
- `docker compose up --build` gives a working app.

## M2 — Accounts, workspaces, secrets
**Features:** AUTH-1–5, WS-1–5, SEC-1–5, UI-2.
- Users, sessions, CSRF and login rate limiting.
- A workspace created at signup.
- Every dashboard route scoped to the workspace; Chroma and Neo4j names namespaced.
- `core/crypto.py`, `arena keys generate|rotate`, the canary value.
- `arena migrate-legacy` imports today's `arena.db`.
- The Alpine UI is put behind login temporarily, until the React pages replace it.

**Exit criteria:**
- The isolation suite passes.
- A grep of the SQLite file finds no plaintext provider key.
- The legacy import is idempotent and the imported bots still answer.

## M3 — Providers
**Features:** PROV-1–9, KB-1, UI-3.
- Provider interface and registry.
- OpenAI, Anthropic and Ollama, with Gemini and NVIDIA ported.
- Credentials with encrypted secrets.
- Capability discovery.
- Collections bound to an embedding credential and model.
- Usage normalization.

**Exit criteria:**
- The shared contract suite passes for all five providers on recorded fixtures.
- Live smoke tests pass for each provider the owner has a key for.
- The provider branches in `embeddings.py`, `extraction.py`, `generation.py` and `model_config.py` are gone.

## M4 — Personas, bots v2, runtime
**Features:** PERS-1–4, BOT-1, BOT-2, BOT-4, BOT-5, RT-1–5, RT-7, TOOL-1–3, SEC-6, SEC-7, UI-5–7.
- Persona model and editor.
- Prompt composer.
- Bot drafts and immutable published versions.
- A unified async runtime with normalized events.
- Tool calling for all five providers.
- Per-workspace tool servers with the SSRF guard.
- React Studio and playground, with Simple/Advanced mode (UX-6).

**Exit criteria:**
- The same bot gives equivalent event sequences on at least three providers.
- Draft edits don't affect the published version.
- A blocked-topic prompt returns the persona's refusal.
- The SSRF tests pass.

## M5 — Delivery: REST + gRPC
**Features:** API-1–9, GRPC-1–7, TOOL-5, BOT-6–10, RT-6, SEC-8, OBS-1, UI-8, WS-7, OPS-4.
- Per-bot endpoint settings, the three conversation modes, user-chosen retention, and the instance settings page (gRPC TLS).
- API keys with scopes, rate limits and expiry.
- `/v1/bots/{bot}/messages` (JSON and SSE).
- Conversations API.
- OpenAI-compatible `/v1/chat/completions` and `/v1/models`.
- gRPC `BotService` with auth interceptor, health and reflection.
- The built-in MCP server behind API keys.
- Per-bot CORS, idempotency, usage records.
- A "Use this bot" page with working snippets (UX-9) and the API reference (DOC-3).

**Exit criteria:** a parity test sends one request through REST JSON, REST SSE, gRPC unary, gRPC stream and the OpenAI SDK, and gets:
- the same final content from a deterministic fake provider
- the same event types
- identical rejections for a bad key, a missing scope and a rate limit

## M6 — Webhooks & jobs
**Features:** HOOK-1–7, KB-2, KB-3, UI-9.
- SQLite job queue with lease-based claiming and an in-process worker.
- Async invoke with signed callbacks.
- Event subscriptions.
- Retries, dead-letter, delivery log, replay and test ping.
- Ingestion moved onto jobs and made atomic.

**Exit criteria:**
- Killing the container mid-queue loses no deliveries after restart.
- Signatures verify with the documented Python and Node verifiers.
- A failing endpoint gets exactly six attempts.

## M7 — Dashboard completion
**Features:** UI-4, UI-10, UI-11, UI-13, KB-4–6, BOT-3, PERS-5, AUTH-6, AUTH-7, WS-6, TOOL-4.
- React pages for collections and documents with job progress, the Lab port (Chroma, Graph and Compare with all the Lab controls), conversations and history browsers, version history and rollback, persona templates, account and workspace settings, keyboard shortcuts and responsive layout.
- Setup wizard (UX-1), page tours (UX-2), templates (UX-5), in-app Help center (UX-8).
- The Alpine UI is removed.

**Exit criteria:**
- A first-time user finishes the setup wizard in under 10 minutes.
- A Playwright smoke test passes: sign up → add credential → create collection and ingest → create persona → create bot → publish → create API key → call the bot with curl → see the conversation in the dashboard.
- Lab feature parity is checked against `01-current-state.md`.

## M8 — Observability, capacity & hardening
**Features:** OBS-2, OBS-3, OBS-5, SEC-9, UI-12, OPS-1, OPS-2, OPS-3, OPS-5, OPS-6.
- Server profile (CPU, RAM, disk, cgroup limits, SQLite/Chroma/Neo4j benchmarks) with recommended limits and an *Apply* button.
- Configurable instance caps and workspace limits.
- Infrastructure calculator, calibrated by `arena bench`.
- Usage and cost dashboards, request log with retention, audit log, metrics.
- Full `/security-review` and fixes.
- A load test on the reference hardware with `arena bench`, used to calibrate the recommendations and the calculator. There's no fixed target (D15); the measured numbers go in the docs.
- Operator guide (DOC-2), and the user guide completed and reviewed end to end (DOC-1).

**Exit criteria:**
- No high-severity findings remain open.
- On the reference machine, the recommended limits are within 20% of the measured `arena bench` results.
- The docs are complete.

## M9 — Embeddable widget
**Features:** WIDGET-1–5.
- A `<script>` embed served by the app, with publishable origin-locked keys.
- Theming and live preview in the bot's *Widget* tab.
- Visitor conversations, using continue mode.

**Exit criteria:**
- The widget works on a test page from an allowed origin and fails from any other origin.
- An accessibility check passes.

## Rough effort (one developer with an AI assistant)

| M1 | M2 | M3 | M4 | M5 | M6 | M7 | M8 | M9 |
|---|---|---|---|---|---|---|---|---|
| 1–1.5 wk | 1.5 wk | 1.5 wk | 2 wk | 2–2.5 wk | 1 wk | 2–3 wk | 1.5 wk | 1 wk |

These are estimates for planning order, not commitments.
