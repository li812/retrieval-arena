# 00 — Overview

## Vision

Retrieval Arena grows from a single-user RAG lab into a **self-hostable bot platform**. People sign up, build knowledge bases, design **personas**, compose them into **bots** with retrieval recipes and **MCP tools**, publish them, and use them inside their own products through **REST**, **gRPC**, an **OpenAI-compatible endpoint**, **async webhooks**, and **event subscriptions**. The Retrieval Lab stays as the workbench for tuning how a bot retrieves.

## Who it is for

- **Builders** who host the platform on their own infrastructure and create bots for their products.
- **Developers** who integrate a published bot into an app, backend, or workflow using an API key.

There is one account type. Each user has their own isolated workspace. Signup is open.

## Glossary

| Term | Meaning |
|---|---|
| **User** | A person with an account (email + password). Owns exactly one workspace. |
| **Workspace** | The isolation boundary. Every credential, collection, persona, bot, conversation, API key, MCP server, and webhook belongs to one workspace. |
| **Credential** | A provider connection: provider (`openai`, `anthropic`, `gemini`, `nvidia`, `ollama`), an encrypted secret, an optional base URL. Used for chat and/or embeddings. |
| **Collection** | A knowledge base: documents chunked into Chroma (vectors) and Neo4j (graph). Bound to one embedding credential + model. |
| **Persona** | A reusable personality layer: name, avatar, role, tone, style rules, example dialogues, blocked topics, refusal message, language, length limits. Attachable to many bots. |
| **Bot** | Persona + knowledge (collections, backend, retrieval recipe) + model (credential + model) + tools (MCP tool refs) + memory and delivery settings. Edited as a **draft**. |
| **Bot version** | An immutable snapshot created by **Publish**. API traffic uses the latest published version unless a request pins one. |
| **Tool server** | An MCP server the workspace connects to (streamable HTTP; stdio only on single-tenant installs). Its tools can be enabled per bot. |
| **API key** | A secret (`ra_…`) that lets an external caller use bots. Scoped to bots/permissions, rate-limited, shown once. |
| **Conversation** | A thread of messages between an end user and a bot. External callers may pass their own `user` identifier. |
| **Run** | One invocation of a bot (one user turn → one assistant reply, including retrieval and tool calls). Has an id, status, and event log. |
| **Event** | A normalized record emitted during a run (`message.delta`, `tool.call`, …) or about platform activity (`conversation.created`, …). Streamed to callers and delivered to webhook subscriptions. |
| **Retrieval recipe** | The tuning parameters for retrieval and generation (search mode, rerank, transforms, top-k, temperature, …) — today's `TuningParams`. |

## In scope

- Accounts, sessions, per-user workspaces, open signup
- Encrypted secrets in SQLite (credentials, MCP headers/env, webhook secrets)
- Providers: OpenAI, Anthropic, Gemini, NVIDIA NIM, Ollama (chat, streaming, tool calling, embeddings where offered)
- Collections and ingestion (text, PDF), vector + graph retrieval, the Retrieval Lab
- Personas, bots, draft/publish versions, bot playground
- Bot runtime with RAG + MCP tool calling + memory + groundedness checks
- Delivery: REST (JSON + SSE), OpenAI-compatible chat completions, gRPC (unary + server streaming), async invoke with signed callback, event subscriptions
- Built-in MCP server (authenticated) exposing collections and bots
- API keys with scopes, expiry, and rate limits
- React + Vite dashboard
- Usage, request logs, audit log
- User-chosen conversation retention; per-bot endpoint settings; caller-chosen conversation modes
- Server profiling, recommended limits, configurable capacity, infrastructure calculator
- Embeddable chat widget

## Out of scope (for this plan)

- Inbound channel adapters (Slack, Telegram, WhatsApp, email)
- Teams, shared workspaces, roles, SSO
- Billing
- Databases other than SQLite (the data layer keeps a switch contained)
- Fine-tuning, voice, image generation

## Guiding principles

1. **One runtime, many interfaces.** Every interface adapts the same event stream, so behaviour is identical everywhere.
2. **Isolation by construction.** Data access goes through workspace-scoped repositories; no query is written without a `workspace_id`.
3. **Secrets never leave the server.** Encrypted at rest, never returned by any API, scrubbed from logs.
4. **Discover, don't hardcode.** Models and capabilities come from the provider at runtime.
5. **Every milestone ships.** Each milestone ends with working, tested software.
6. **Easy first, powerful second.** Simple mode, a setup wizard, page tours, plain-language help and errors come first; the full Lab sits behind *Advanced*. Signup → a working API call in under 10 minutes (UX group).
7. **Documented as it's built.** A feature isn't done until its user-guide section exists.
