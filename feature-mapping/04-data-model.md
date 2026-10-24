# 04 — Data model (SQLite via SQLAlchemy 2 + Alembic)

Conventions:
- **IDs:** prefixed ULIDs stored as text (`usr_…`, `ws_…`, `bot_…`). They're sortable and don't reveal how many rows exist.
- **Timestamps:** UTC ISO-8601.
- **Tenant tables** carry `workspace_id` (FK, indexed). Every tenant query filters on it, through `repositories/` only.
- 🔒 = encrypted column (AES-256-GCM, `v1:<key_id>:<nonce>:<ct>`, AAD = `table|row_id|workspace_id`).
- # = stored as a hash only.
- **SQLite pragmas:** `journal_mode=WAL`, `busy_timeout=5000`, `foreign_keys=ON`.

## Identity

| Table | Columns |
|---|---|
| `users` | id, email (unique, lower-cased), password_hash (argon2id), created_at, last_login_at, disabled |
| `sessions` | id, user_id, token_hash #, csrf_token_hash #, created_at, last_seen_at, expires_at, ip, user_agent |
| `workspaces` | id, owner_user_id (unique for now), name, settings (JSON: retention `{mode: "days"\|"forever"\|"metadata_only", days}`, allow_private_targets, limits within instance caps), created_at |
| `instance_settings` | key, value (JSON), value_secret 🔒 (for the gRPC TLS private key), updated_at, updated_by. Seeded from env/config; UI edits override |
| `system_profiles` | id, measured_at, cpu_cores, cpu_limit, ram_bytes, ram_limit, disk_free_bytes, sqlite_writes_per_s, chroma_p50_ms, neo4j_p50_ms, recommendations (JSON) |
| `login_attempts` | id, email, ip, at, success (for AUTH-5) |

## Providers & knowledge

| Table | Columns |
|---|---|
| `credentials` | id, workspace_id, name, provider (`openai`/`anthropic`/`gemini`/`nvidia`/`ollama`), secret 🔒 (nullable for Ollama), secret_hint, base_url, created_at, last_tested_at, status |
| `model_capabilities` | credential_id, model, kind (`chat`/`embedding`/`rerank`), supports_tools, supports_stream, embed_dim, probed_at |
| `collections` | id, workspace_id, name (unique per workspace), chroma_name (`ws{n}__{name}`), graph_name (`ws{n}:{name}`), embed_credential_id, embed_model, embed_dim, created_at |
| `documents` | id, collection_id, workspace_id, source_name, chunk_prefix, chunk_count, triple_count, status (`pending`/`ready`/`failed`), error, created_at |

## Personas, bots, versions

| Table | Columns |
|---|---|
| `personas` | id, workspace_id, name, avatar, role, tone, style_rules (JSON list), example_dialogues (JSON list of {user, assistant}), blocked_topics (JSON list), refusal_message, language, max_response_words, created_at, updated_at |
| `bots` | id, workspace_id, slug (unique per workspace), name, description, **draft** (JSON: persona_id, instructions, collection_ids, backend, recipe, chat_credential_id, chat_model, tool_refs, memory_turns, greeting, starters, variables_schema, cors_origins), **endpoint_config** (JSON, not versioned: enabled interfaces, timeouts, max tokens, rate limits, allow_stateless, default conversation mode, retention override), **widget_config** (JSON: theme, position, allowed origins), published_version_id (nullable), created_at, updated_at |
| `bot_versions` | id, bot_id, workspace_id, number (1, 2, …), snapshot (JSON: the draft **plus the persona's content at publish time**), published_at, published_by, note |

The snapshot embeds persona content rather than referencing it, so editing a persona never silently changes a published bot. Republishing picks up persona edits.

## Conversations & runs

| Table | Columns |
|---|---|
| `conversations` | id, workspace_id, bot_id, external_user (caller's `user` field, nullable), source (`dashboard`/`api`/`grpc`/`openai`/`webhook`), api_key_id (nullable), title, created_at, updated_at |
| `messages` | id, conversation_id, workspace_id, role, content, meta (JSON: sources, triples, tool_calls, rewrite, checks), feedback (-1/0/1), feedback_comment, created_at |
| `runs` | id, workspace_id, bot_id, bot_version_id, conversation_id, api_key_id, interface, status (`queued`/`running`/`completed`/`failed`/`cancelled`), input, result (JSON), error, callback_url, started_at, finished_at, idempotency_key (unique per key) |
| `run_events` | run_id, seq, type, data (JSON), at (kept for async runs and debugging; pruned by retention) |
| `usage_records` | id, workspace_id, run_id, bot_id, api_key_id, provider, model, input_tokens, output_tokens, latency_ms, at |

## Tools

| Table | Columns |
|---|---|
| `tool_servers` | id, workspace_id, name, transport (`http`/`stdio`), url, headers 🔒 (JSON), command, args (JSON), env 🔒 (JSON), enabled, created_at, last_tested_at |
| `tool_cache` | server_id, tools (JSON), fetched_at |

## Delivery

| Table | Columns |
|---|---|
| `api_keys` | id, workspace_id, name, kind (`secret` / `publishable` for the widget, origin-locked), allowed_origins (JSON, publishable only), prefix (first 8 chars, for display and lookup), key_hash # (SHA-256), scopes (JSON: permissions + bot_ids or `*`), rate_limit_rpm, token_limit_daily, expires_at, last_used_at, revoked_at, created_at |
| `rate_counters` | api_key_id, window, count, tokens (in-memory primary; flushed for daily limits) |
| `webhook_subscriptions` | id, workspace_id, bot_id (nullable = all bots), url, event_types (JSON), secret 🔒, enabled, created_at |
| `webhook_deliveries` | id, workspace_id, subscription_id (nullable for run callbacks), run_id (nullable), event_type, payload (JSON), attempt, status (`pending`/`delivered`/`failed`/`dead`), next_attempt_at, last_status_code, last_error, created_at |
| `jobs` | id, workspace_id, kind (`ingest`/`invoke`/`deliver`/`retention`), payload (JSON), status, attempts, max_attempts, run_after, locked_by, locked_until, error, created_at |

## Audit & history

| Table | Columns |
|---|---|
| `audit_log` | id, workspace_id, user_id or api_key_id, action, target_type, target_id, detail (JSON, never secrets), ip, at |
| `lab_history` | id, workspace_id, question, backend, collection_id, payload (JSON), pinned, created_at (today's `history`) |

## Scoping rules

1. Repositories take a `Scope(workspace_id, actor)` in their constructor. There are no unscoped tenant reads.
2. Cross-references are validated in the same workspace. A bot can only reference that workspace's personas, collections, credentials and tool servers.
3. Lookups by id return **404** when the row belongs to another workspace, so ids can't be probed.
4. External names derive from the workspace: `collections.chroma_name` and `graph_name` are computed on creation and never taken from user input directly.
5. Deleting a workspace cascades in SQL and also deletes its Chroma collections and Neo4j graph nodes.

## Legacy import mapping (`arena migrate-legacy`)

| Legacy | New |
|---|---|
| `api_keys` (plaintext) | `credentials` (encrypted, hint kept) |
| `collections` registry + Chroma collection `x` | `collections` + Chroma renamed to `ws{n}__x` via `collection.modify(name=…)` |
| Neo4j `graph = 'x'` | `graph = 'ws{n}:x'` |
| `bots` | `bots` (draft) + `personas` (one generated from each system prompt) + published `bot_versions` v1 |
| `conversations`, `messages` | same tables, `source = 'dashboard'` |
| `mcp_servers` | `tool_servers` (headers and env encrypted) |
| `history` | `lab_history` |
