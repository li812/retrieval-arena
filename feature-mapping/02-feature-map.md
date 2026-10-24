# 02 — Feature map

Each feature has an ID, priority (**P0** = required for the platform to work, **P1** = expected, **P2** = valuable later), milestone (see `08-roadmap.md`), dependencies, and acceptance criteria (**AC**).

```
Platform
├── AUTH  Accounts & sessions
├── WS    Workspaces & isolation
├── SEC   Secrets & security controls
├── PROV  Providers & credentials
├── KB    Knowledge bases (collections, ingestion, Lab)
├── PERS  Personas
├── BOT   Bots & versions
├── RT    Bot runtime
├── TOOL  MCP tools (client) & MCP server
├── API   Public REST & OpenAI-compatible API, API keys
├── GRPC  gRPC service
├── HOOK  Webhooks & jobs
├── UI    Dashboard
├── OBS   Usage, logs, audit
├── OPS   Server profile, recommendations, capacity calculator, instance settings
├── UX    Setup wizard, tour guide, contextual help, templates, simple/advanced mode
├── DOC   User guide, operator guide, API reference
└── WIDGET Embeddable chat widget
```

---

## AUTH — Accounts & sessions

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| AUTH-1 | Sign up with email + password (open signup) | P0 | M2 | — | New email creates a user and its workspace; duplicate email → 409; password ≥ 10 chars |
| AUTH-2 | Log in / log out | P0 | M2 | AUTH-1 | Correct credentials set a session cookie; logout revokes the session server-side |
| AUTH-3 | Server-side sessions | P0 | M2 | AUTH-2 | Token stored hashed; httpOnly, SameSite=Lax, Secure when behind HTTPS; idle + absolute expiry |
| AUTH-4 | CSRF protection for dashboard mutations | P0 | M2 | AUTH-3 | State-changing dashboard requests without the CSRF header are rejected with 403 |
| AUTH-5 | Login rate limiting | P0 | M2 | AUTH-2 | More than 10 failed attempts per email or IP in 15 min → 429 |
| AUTH-6 | Change password, revoke all sessions | P1 | M7 | AUTH-3 | Changing the password ends all other sessions |
| AUTH-7 | Delete account (and workspace) | P1 | M7 | WS-1 | Removes SQL rows, Chroma collections, Neo4j graphs; requires password confirmation |
| AUTH-8 | Password reset via email | P2 | — | SMTP config | Out of the initial plan; CLI reset (`arena users reset-password`) covers self-hosters |

## WS — Workspaces & isolation

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| WS-1 | One workspace per user, created at signup | P0 | M2 | AUTH-1 | Every tenant table has `workspace_id`; created atomically with the user |
| WS-2 | Workspace-scoped repositories | P0 | M2 | WS-1 | No query outside `repositories/` touches tenant tables (enforced by a lint/test) |
| WS-3 | Namespaced Chroma collections (`ws{id}__{name}`) and Neo4j graphs (`ws{id}:{name}`) | P0 | M2 | WS-1 | Two users can each own a collection called `docs` with no cross-reads |
| WS-4 | Isolation test suite | P0 | M2 | WS-2, WS-3 | For every resource type: user B gets 404 (not 403) for user A's ids, via dashboard, REST, gRPC, and MCP |
| WS-5 | Legacy import (`arena migrate-legacy`) | P0 | M2 | SEC-2 | Today's `arena.db` imports into a chosen user's workspace; keys encrypted; Chroma/Neo4j renamed; idempotent |
| WS-6 | Workspace settings (name, private-network allowance) | P1 | M7 | WS-1 | — |
| WS-7 | **Retention you choose**: per workspace, overridable per bot. Content retention options: 7, 30, 90 (default), 180 or 365 days, forever, or metadata-only (no message text stored) | P0 | M5 | WS-1 | The retention job deletes content past the chosen window; metadata-only stores no message text; changing the setting applies going forward and offers a one-time purge |

## SEC — Secrets & security controls

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| SEC-1 | Master key from `ARENA_MASTER_KEY`; refuse to start without it | P0 | M2 | — | Missing/invalid key → clear startup error |
| SEC-2 | AES-256-GCM field encryption with row-bound AAD | P0 | M2 | SEC-1 | Round-trip test passes; ciphertext moved to another row fails to decrypt |
| SEC-3 | Key rotation (`ARENA_MASTER_KEY_PREVIOUS`, `arena keys rotate`) | P1 | M2 | SEC-2 | After rotation all values decrypt with the new key only |
| SEC-4 | Secrets never returned; hints only | P0 | M2 | SEC-2 | No API response contains a stored secret (contract test over all routes) |
| SEC-5 | Log scrubbing | P0 | M2 | — | Known secret patterns (`sk-`, `nvapi-`, `AIza`, `ra_`, bearer tokens) never appear in logs |
| SEC-6 | SSRF guard for outbound URLs (MCP, webhooks, callbacks, Ollama) | P0 | M4 | — | Loopback, private, link-local, and metadata targets refused after DNS resolution unless `ALLOW_PRIVATE_TARGETS` |
| SEC-7 | stdio MCP disabled unless `ALLOW_STDIO_MCP` (single-tenant only) | P0 | M4 | — | Creating a stdio server returns 403 when disabled |
| SEC-8 | Security headers, CORS defaults, request size limits | P1 | M5 | — | CSP, X-Content-Type-Options, frame-ancestors set; dashboard not embeddable |
| SEC-9 | Audit log of security-relevant actions | P1 | M8 | WS-1 | Credential, API key, publish, and webhook changes are recorded with actor and time |

## PROV — Providers & credentials

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| PROV-1 | Provider interface (`ChatProvider`, `EmbeddingProvider`, `RerankProvider`) with normalized messages, tool calls, stream events, usage | P0 | M3 | — | All providers pass the same contract test suite |
| PROV-2 | OpenAI (chat, stream, tools, embeddings, model list) | P0 | M3 | PROV-1 | Contract tests pass on recorded fixtures; live smoke with a key |
| PROV-3 | Anthropic (Messages API, stream, `tool_use`, model list; no embeddings) | P0 | M3 | PROV-1 | Same; system prompt and `max_tokens` handled |
| PROV-4 | Ollama (`/api/chat`, `/api/embed`, `/api/tags`; base URL, no key) | P0 | M3 | PROV-1, SEC-6 | Works against a local Ollama when private targets are allowed |
| PROV-5 | Gemini ported to the interface | P0 | M3 | PROV-1 | Parity with today's behaviour |
| PROV-6 | NVIDIA NIM ported (catalog + probes, cache, timeouts) | P0 | M3 | PROV-1 | Parity with today's behaviour |
| PROV-7 | Credentials: CRUD, test connection, encrypted secret, optional base URL | P0 | M3 | SEC-2 | Testing a credential lists usable chat/embedding models |
| PROV-8 | Capability discovery per model (chat, stream, tools, embeddings, dims) | P1 | M3 | PROV-1 | Tool-capable models flagged; embedding dims measured |
| PROV-9 | Usage normalization (input/output tokens per call) | P1 | M3 | PROV-1 | Every run records token usage when the provider reports it |
| PROV-10 | OpenAI-compatible "custom" provider (any base URL) | P2 | — | PROV-2 | Covers vLLM, LM Studio, OpenRouter, etc. |

## KB — Knowledge bases

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| KB-1 | Collections bound to an embedding credential + model | P0 | M3 | PROV-7 | Ingest and query use the collection's embedding model; mismatch impossible |
| KB-2 | Ingestion as a background job with progress | P0 | M6 | HOOK-1 | Upload returns a job id; UI shows chunk/triple progress; failures are retryable |
| KB-3 | Atomic ingestion (no half-written documents) | P1 | M6 | KB-2 | A failed job leaves no partial chunks or triples for that document |
| KB-4 | Document management (list, delete a document) | P1 | M7 | KB-1 | Deleting a document removes its chunks and triples |
| KB-5 | Retrieval Lab ported (dense/BM25/hybrid, transforms, rerank, expansion, packing, trace, compare) | P0 | M7 | KB-1 | Feature parity with today's Lab |
| KB-6 | Groundedness, sentiment, emotion analysis | P1 | M7 | KB-5 | Parity with today |
| KB-7 | More file types (Markdown, HTML, DOCX) and URL import | P2 | — | KB-2 | — |

## PERS — Personas

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| PERS-1 | Persona CRUD: name, avatar, role, tone, style rules, example dialogues | P0 | M4 | WS-1 | Personas listed per workspace; reusable across bots |
| PERS-2 | Guardrails: blocked topics + refusal message, language, max response length | P0 | M4 | PERS-1 | Composer injects them; a blocked-topic test prompt yields the refusal |
| PERS-3 | Prompt composer (persona + bot instructions + knowledge rules + tool rules) | P0 | M4 | PERS-1 | Deterministic output; snapshot tests |
| PERS-4 | Persona preview (chat with persona alone, no knowledge) | P1 | M4 | RT-1 | — |
| PERS-5 | Persona templates (support agent, tutor, analyst, …) | P2 | M7 | PERS-1 | — |

## BOT — Bots & versions

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| BOT-1 | Bot composition: persona, collections + backend + recipe, chat credential + model, tools, memory window, greeting, starters | P0 | M4 | PERS-1, PROV-7, KB-1 | Draft saved and validated (credential/model compatible, collections exist) |
| BOT-2 | Draft / Publish → immutable `bot_version` | P0 | M4 | BOT-1 | Editing a draft never changes what API callers get until Publish |
| BOT-3 | Version history, diff, rollback (re-publish an old version) | P1 | M7 | BOT-2 | — |
| BOT-4 | Bot slug (stable public identifier) | P0 | M4 | BOT-1 | Unique per workspace; used in API paths and `model: "bot:<slug>"` |
| BOT-5 | Playground (draft or published) with live event trace | P0 | M4 | RT-1 | Parity with today's Studio preview |
| BOT-6 | Per-bot CORS allowlist for browser callers | P1 | M5 | API-2 | Requests from other origins rejected |
| BOT-7 | Prompt variables (`{{customer_name}}`) filled per request | P1 | M5 | PERS-3 | Missing required variables → 422 |
| BOT-8 | Feedback (👍/👎 + comment) from dashboard and API | P1 | M5 | API-2 | Emits `feedback.created` |
| BOT-9 | **Endpoint settings per bot** (editable in the bot's *Endpoints* tab): turn each interface on or off (REST JSON, SSE, OpenAI-compatible, gRPC, async/webhook); timeouts; max tokens per request; rate limits that override the key's limits downward; CORS origins; whether callers may send inline history; default conversation mode | P0 | M5 | API-1 | A disabled interface returns `forbidden` with a clear message; changes take effect without republishing |
| BOT-10 | **Conversation modes**, chosen by the caller per request, with a bot default: **new** (no id → server creates one and returns its id), **continue** (pass `conversation_id` → server keeps context), **stateless** (pass inline `history` → nothing stored beyond usage metadata) | P0 | M5 | RT-2 | All three modes produce the same answer for the same context; stateless mode stores no message text |

## RT — Bot runtime

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| RT-1 | `invoke()` → normalized async event stream (see `05-api-contracts.md`) | P0 | M4 | PROV-1 | Same event sequence regardless of interface |
| RT-2 | Memory: conversation window + follow-up rewriting (today's `ChatAgent.rewrite`) | P0 | M4 | RT-1 | Pronoun follow-ups resolve; window size configurable |
| RT-3 | Knowledge retrieval per bot recipe (vector, graph, both) | P0 | M4 | KB-1 | Parity with today's chat retrieval |
| RT-4 | Tool-calling loop for all providers, max rounds, truncation | P0 | M4 | TOOL-1, PROV-1 | Works on OpenAI, Anthropic, Gemini, NVIDIA, Ollama models that support tools |
| RT-5 | Groundedness check per run (optional) | P1 | M4 | RT-1 | `check.groundedness` event emitted |
| RT-6 | Cancellation (client disconnect stops the run) | P1 | M5 | RT-1 | Provider streams closed; run marked `cancelled` |
| RT-7 | Timeouts and per-run budgets (max tokens, max tool calls, wall clock) | P0 | M4 | RT-1 | Exceeding a budget ends the run with a typed error |
| RT-8 | Fallback model on provider error | P2 | — | RT-1 | — |

## TOOL — MCP

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| TOOL-1 | Workspace MCP servers (streamable HTTP; headers encrypted) | P0 | M4 | SEC-2, SEC-6 | Add, test (list tools), enable/disable, delete |
| TOOL-2 | Per-bot tool selection | P0 | M4 | TOOL-1, BOT-1 | Bot only sees selected tools |
| TOOL-3 | Tool-support probe per model | P1 | M4 | PROV-8 | Studio warns when the model can't call tools |
| TOOL-4 | Tool approval in the playground | P2 | M7 | RT-4 | Run pauses until the user approves a call |
| TOOL-5 | Built-in MCP server behind API-key auth (`mcp` scope), workspace-scoped tools | P0 | M5 | API-1 | Unauthenticated → 401; tools only see the key's workspace |
| TOOL-6 | stdio servers (single-tenant installs only) | P2 | M4 | SEC-7 | — |

## API — Public REST, OpenAI-compatible, API keys

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| API-1 | API keys: create (shown once), scopes (bots, permissions), expiry, revoke, rotate | P0 | M5 | WS-1 | Hash-only storage; revoked key → 401 immediately |
| API-2 | `POST /v1/bots/{bot}/messages` (JSON) | P0 | M5 | RT-1, API-1 | Returns final message, sources, usage, run id |
| API-3 | Same endpoint with `stream: true` (SSE) | P0 | M5 | API-2 | Events match the documented schema |
| API-4 | Conversations API (list, get messages, delete) | P0 | M5 | API-1 | Scoped to the key's workspace and bot scopes |
| API-5 | OpenAI-compatible `POST /v1/chat/completions` (`model: "bot:<slug>"`) | P0 | M5 | RT-1 | Official OpenAI SDK works unchanged, streaming and not |
| API-6 | Rate limits (requests/min, tokens/day) per key | P0 | M5 | API-1 | 429 with `Retry-After`; same behaviour on every interface |
| API-7 | Idempotency keys on POST | P1 | M5 | API-2 | Repeated `Idempotency-Key` returns the first result |
| API-8 | OpenAPI docs + per-bot code snippets (curl, Python, JS, OpenAI SDK, grpcurl) | P1 | M5 | API-2 | — |
| API-9 | `GET /v1/models` (OpenAI-compatible list of the key's bots) | P1 | M5 | API-5 | — |

## GRPC — gRPC service

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| GRPC-1 | `arena.v1.BotService` proto, generated stubs committed | P0 | M5 | — | `buf lint` / `protoc` clean |
| GRPC-2 | `Invoke` (unary) | P0 | M5 | RT-1, API-1 | Same answer as REST JSON |
| GRPC-3 | `InvokeStream` (server streaming) | P0 | M5 | GRPC-2 | Same event sequence as SSE |
| GRPC-4 | Conversation RPCs (`GetConversation`, `ListConversations`) | P1 | M5 | API-4 | — |
| GRPC-5 | Auth interceptor (API key in `authorization` metadata), rate limits, error mapping to status codes | P0 | M5 | API-1, API-6 | Status codes documented and tested |
| GRPC-6 | Health + reflection services | P1 | M5 | GRPC-1 | `grpcurl list` works |
| GRPC-7 | **gRPC TLS, configurable from the UI**: mode `off` (localhost only), `app` (upload cert + key, stored encrypted, hot-reloaded), or `proxy` (plaintext behind a TLS proxy, with guidance); bind address and port editable | P0 | M5 | SEC-2, OPS-4 | Switching modes takes effect without a container restart; `grpcurl` works in each mode |

## HOOK — Webhooks & jobs

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| HOOK-1 | SQLite-backed job queue + in-process worker (claim, lease, retry) | P0 | M6 | — | Jobs survive restart; no double execution under 2 workers |
| HOOK-2 | Async invoke: `POST …/messages:async` with `callback_url` → 202 + run id | P0 | M6 | HOOK-1, API-2 | Callback receives the final result, signed |
| HOOK-3 | `GET /v1/runs/{id}` (status, result, events) | P0 | M6 | HOOK-2 | — |
| HOOK-4 | Event subscriptions (workspace- or bot-level, chosen event types, signing secret) | P0 | M6 | HOOK-1 | Matching events delivered within seconds |
| HOOK-5 | Signing: `X-Arena-Signature: t=…,v1=…` (HMAC-SHA256), 5-minute replay window | P0 | M6 | SEC-2 | Reference verifier in docs passes |
| HOOK-6 | Retries with backoff (1m, 5m, 30m, 2h, 12h), dead-letter | P0 | M6 | HOOK-1 | Failing endpoint gets exactly 6 attempts |
| HOOK-7 | Delivery log + manual replay + test ping | P1 | M6 | HOOK-4 | — |

## UI — Dashboard (React + Vite)

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| UI-1 | Shell: routing, auth guard, theme (dark/light/auto), layout, command palette, toasts | P0 | M1 | — | Tokens carried over from today's `style.css` |
| UI-2 | Auth pages (sign up, log in) | P0 | M2 | AUTH-1 | — |
| UI-3 | Credentials page | P0 | M3 | PROV-7 | — |
| UI-4 | Collections + ingest (job progress) + documents | P0 | M7 | KB-2 | — |
| UI-5 | Personas editor | P0 | M4 | PERS-1 | — |
| UI-6 | Bot studio + playground + publish + versions | P0 | M4 | BOT-2 | — |
| UI-7 | Tool servers page | P0 | M4 | TOOL-1 | — |
| UI-8 | API keys page + per-bot "Use this bot" snippets | P0 | M5 | API-1 | Key shown once with copy button |
| UI-9 | Webhooks page (subscriptions, deliveries, replay) | P0 | M6 | HOOK-4 | — |
| UI-10 | Retrieval Lab (Chroma / Graph / Compare) | P0 | M7 | KB-5 | Parity with today |
| UI-11 | Conversations browser, history, export | P1 | M7 | API-4 | — |
| UI-12 | Usage & logs | P1 | M8 | OBS-1 | — |
| UI-13 | Keyboard shortcuts, resizable panels, responsive down to 375 px | P1 | M7 | UI-1 | — |

## OBS — Usage, logs, audit

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| OBS-1 | Usage records per run (tokens, latency, provider, model, bot, key) | P0 | M5 | PROV-9 | Dashboard totals match the records |
| OBS-2 | Request log (metadata by default; content per retention setting) | P1 | M8 | OBS-1 | — |
| OBS-3 | Cost estimates from a per-model price table (editable) | P2 | M8 | OBS-1 | — |
| OBS-4 | Structured JSON logs with run ids; `/healthz`, `/readyz` | P1 | M1 | — | — |
| OBS-5 | Prometheus metrics endpoint | P2 | M8 | — | — |

## OPS — Capacity & instance settings

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| OPS-1 | **Server profile**: the app reads CPU cores, RAM, free disk on the data volume, container limits (cgroup), and runs a short SQLite write benchmark and Chroma/Neo4j latency probe | P0 | M8 | — | Profile shown in Settings → System; re-run on demand; results stored with a timestamp |
| OPS-2 | **Recommended limits** from the profile: max concurrent runs, max concurrent streams, worker count, ingestion concurrency, per-key default rate limits | P0 | M8 | OPS-1 | Each recommendation shows the reasoning (e.g. "4 cores, 8 GB → 24 concurrent streams") and an *Apply* button |
| OPS-3 | **Configurable limits**: instance caps (concurrency, request size, upload size, worker count) and workspace limits within those caps | P0 | M8 | OPS-2 | Limits enforced at runtime; values outside caps rejected |
| OPS-4 | **Instance settings page** (caps, gRPC TLS, private-network allowance, stdio MCP), editable by the instance owner (see `09-decisions.md` Q9) and seeded from env/config | P0 | M5 | AUTH-1 | Env values act as defaults; UI changes persist in SQLite and override them |
| OPS-5 | **Infrastructure calculator**: inputs (bots, requests/day, peak concurrent users, % streaming, avg input/output tokens, tool calls per run, documents and total size, retention); outputs (CPU, RAM, disk for SQLite + Chroma + Neo4j over the retention window, recommended limits, provider token volume and estimated cost from the price table) | P1 | M8 | OPS-1, OBS-3 | Formulas documented; results compared against the measured server profile ("this server fits / is short by X") |
| OPS-6 | Load-test tool (`arena bench`) using a fake provider, to calibrate the calculator on real hardware | P1 | M8 | OPS-1 | Produces requests/s and p95 latency for a given concurrency |

## UX — Ease of use

**Bar:** a new user goes from signup to calling a published bot from curl in **under 10 minutes**, without reading docs first.

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| UX-1 | **Setup wizard** on first login: add a credential → create a collection and upload a file → pick a bot template → test in the playground → publish → copy a snippet. Every step skippable, resumable, and re-openable from Help | P0 | M7 | UI-3, UI-4, UI-6, UI-8 | A first-time tester finishes in under 10 minutes (timed in QA) |
| UX-2 | **Interactive tour guide**: a spotlight overlay that walks through each page's key controls (one tour per page, 4–7 steps each). Starts automatically the first time a page is visited, can be dismissed, and can be replayed from the Help menu; progress is saved per user | P0 | M7 | UI-1 | Tours exist for Home, Credentials, Collections, Personas, Bot Studio, Endpoints, API keys, Webhooks, Lab, System; keyboard accessible |
| UX-3 | **Contextual help**: every non-obvious control has a "?" tooltip in plain language, linking to the matching user-guide section | P0 | M4→M7 | DOC-1 | No Lab or Studio control without a tooltip (lint check in QA) |
| UX-4 | **Empty states with one next action** ("No bots yet → Create your first bot") | P0 | M4→M7 | UI-1 | Every list page has one |
| UX-5 | **Templates**: bot templates (FAQ answerer, support agent, docs assistant, research assistant with tools) and persona templates; each pre-fills sensible settings | P1 | M7 | PERS-5 | Creating a bot from a template needs only a name and a collection |
| UX-6 | **Simple / Advanced mode**: Studio and Lab show only the essentials by default (model, persona, collection, top-k, temperature); Advanced reveals the full retrieval recipe | P0 | M4 | UI-6 | Simple mode fits on one screen without scrolling at 1366×768 |
| UX-7 | **Plain-language errors with a fix**: e.g. "OpenAI rejected the key (401). Check it in Credentials → OpenAI." with a button that goes there | P0 | M3→M7 | — | Provider, auth, limit and validation errors all map to a message + action |
| UX-8 | **In-app Help center** (`/help`): the user guide rendered in the app, searchable, with "Start tour" buttons | P1 | M7 | DOC-1 | Search finds any guide heading |
| UX-9 | **"Use this bot" page** that shows a working curl / Python / JS / gRPC / OpenAI-SDK snippet with the user's real bot slug and a freshly created key inserted | P0 | M5 | API-8 | Copy-paste of the snippet works with no edits |

## DOC — Documentation

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| DOC-1 | **User guide** (`docs/user-guide/`): getting started, core concepts, one page per dashboard area, building a good bot, integrating (REST, streaming, OpenAI SDK, gRPC, webhooks, widget, MCP), conversation modes, retention, limits and the calculator, troubleshooting, FAQ. Written for non-experts, with screenshots | P0 | each M, finished in M8 | — | Every shipped feature has a guide section before its milestone closes |
| DOC-2 | **Operator guide** (`docs/operator-guide/`): install, configuration and env vars, master key backup and rotation, TLS and reverse proxy, backups and restore, upgrades, sizing | P0 | M8 | — | A fresh install following only this guide succeeds |
| DOC-3 | **API reference**: generated OpenAPI + the gRPC proto reference, with examples for every endpoint | P0 | M5 | API-8 | Every public endpoint has a runnable example |

## WIDGET — Embeddable chat widget

| ID | Feature | P | M | Depends | AC |
|---|---|---|---|---|---|
| WIDGET-1 | A `<script>` embed that renders a chat bubble for a bot | P0 | M9 | API-3, BOT-6 | Works on a plain HTML page from an allowed origin |
| WIDGET-2 | Publishable widget keys: origin-locked, invoke-only, low rate limit (safe to expose in a browser) | P0 | M9 | API-1, API-6 | Key fails from any other origin; can't read conversations |
| WIDGET-3 | Theming (colors, position, avatar, greeting, starters from the bot/persona), light/dark | P1 | M9 | WIDGET-1 | Configured in the bot's *Widget* tab with live preview |
| WIDGET-4 | Visitor conversations: anonymous visitor id in local storage → continue mode; optional signed `user` id from the host site (HMAC) | P1 | M9 | BOT-10 | Reloading the page continues the conversation |
| WIDGET-5 | Accessibility (keyboard, screen reader labels), mobile layout | P1 | M9 | WIDGET-1 | — |
