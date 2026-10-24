# 05 — API contracts

Three surfaces:
- **Dashboard API:** under `/api/*`, authenticated by session cookie + CSRF header, for the React app only.
- **Public API:** under `/v1/*`, authenticated by API key.
- **gRPC:** on port 50051, authenticated by API key.

All public errors use one shape:

```json
{ "error": { "type": "rate_limited", "message": "Rate limit exceeded", "retry_after": 12, "request_id": "req_…" } }
```

| `type` | HTTP | gRPC |
|---|---|---|
| `invalid_request` | 400 / 422 | INVALID_ARGUMENT |
| `unauthenticated` | 401 | UNAUTHENTICATED |
| `forbidden` (key lacks scope) | 403 | PERMISSION_DENIED |
| `not_found` | 404 | NOT_FOUND |
| `conflict` | 409 | ALREADY_EXISTS |
| `rate_limited` | 429 | RESOURCE_EXHAUSTED |
| `provider_error` | 502 | UNAVAILABLE |
| `timeout` | 504 | DEADLINE_EXCEEDED |
| `internal` | 500 | INTERNAL |

## Authentication

`Authorization: Bearer ra_<key>`. For gRPC, the same value goes in the `authorization` metadata. The key determines the workspace and its scopes:

```json
{ "permissions": ["invoke", "conversations:read", "mcp"], "bots": ["support-bot"] }   // or "bots": "*"
```

## REST: invoke a bot

### `POST /v1/bots/{bot}/messages`

`{bot}` is a slug or an id.

```json
{
  "input": "Where is my order?",
  "conversation_id": "cnv_…",          // optional: continue mode (server keeps the context)
  "history": [                          // optional: stateless mode (you keep the context); not with conversation_id
    { "role": "user", "content": "Hi" }, { "role": "assistant", "content": "Hello!" }
  ],
  "user": "customer-8812",             // optional external end-user id (analytics; widget visitor id)
  "stream": false,
  "variables": { "customer_name": "Ana" },
  "metadata": { "ticket": "T-91" },    // echoed back and into webhooks
  "version": 3                          // optional: pin a published version
}
```

Headers: `Idempotency-Key` (optional).

**Conversation modes** (BOT-10). The caller picks a mode per request. Server-side context needs a `conversation_id`; without one, the caller either starts fresh or supplies the context itself.

| Mode | Send | Server stores | Response |
|---|---|---|---|
| **new** (default) | neither `conversation_id` nor `history` | the conversation and its messages (subject to retention) | a new `conversation_id` to continue with |
| **continue** | `conversation_id` | appends to that conversation; loads the last N turns as context | same `conversation_id` |
| **stateless** | `history` (optional, may be empty) | usage metadata only, no message text | `conversation_id: null` |

- Sending both `conversation_id` and `history` → `invalid_request`.
- A bot's endpoint settings can turn stateless mode off, or make `new` behave as stateless (no storage) by default.
- `"store": false` on a `new` request is shorthand for stateless with no history.

**Endpoint settings** (BOT-9) are applied before the request runs:
- an interface that is turned off → `forbidden` ("gRPC is disabled for this bot")
- the bot's timeout and max-token caps apply
- the bot's rate limit applies when it's stricter than the key's

**Response (`stream: false`)**

```json
{
  "run_id": "run_…",
  "conversation_id": "cnv_…",
  "bot": { "id": "bot_…", "slug": "support-bot", "version": 3 },
  "message": { "id": "msg_…", "role": "assistant", "content": "Your order shipped on …" },
  "sources": [ { "cite": 1, "collection": "orders-faq", "document": "faq.pdf", "chunk_id": "…", "text": "…", "score": 0.71 } ],
  "tool_calls": [ { "id": "call_…", "name": "lookup_order", "arguments": {"id": "8812"}, "result": "…", "status": "done" } ],
  "checks": { "groundedness": { "score": 1.0, "claims": [ … ] }, "sentiment": { "label": "neutral", "compound": 0.0 } },
  "usage": { "input_tokens": 812, "output_tokens": 96, "latency_ms": 2140 },
  "metadata": { "ticket": "T-91" }
}
```

**Response (`stream: true`)**: `text/event-stream`, one SSE event per runtime event (see *Event schema*):

```
event: run.started
data: {"run_id":"run_…","conversation_id":"cnv_…","bot":{…}}

event: message.delta
data: {"text":"Your order "}

event: run.completed
data: { …same body as the non-streaming response… }
```

### `POST /v1/bots/{bot}/messages:async`

Same body plus `"callback_url": "https://…"` (must pass the SSRF guard). Returns **202**:

```json
{ "run_id": "run_…", "status": "queued", "conversation_id": "cnv_…" }
```

When the run finishes, the callback receives a signed `run.completed` or `run.failed` delivery (see *Webhooks*).

### Runs and conversations

| Method | Path | Notes |
|---|---|---|
| GET | `/v1/runs/{run_id}` | Status, result when done, error when failed |
| GET | `/v1/runs/{run_id}/events` | Stored events (async runs) |
| GET | `/v1/bots/{bot}/conversations?user=&limit=&after=` | Cursor pagination |
| GET | `/v1/bots/{bot}/conversations/{id}/messages` | |
| DELETE | `/v1/bots/{bot}/conversations/{id}` | |
| POST | `/v1/messages/{message_id}/feedback` | `{ "value": 1 \| -1, "comment": "…" }` → emits `feedback.created` |

## OpenAI-compatible

### `POST /v1/chat/completions`

```json
{ "model": "bot:support-bot", "messages": [ {"role":"user","content":"Where is my order?"} ], "stream": true, "user": "customer-8812" }
```

- **Messages:** only the **last user message** is the input. Earlier messages are used as conversation memory when no `conversation_id` is given. To keep server-side memory instead, pass `extra_body: {"conversation_id": "cnv_…"}`.
- **Response:** follows the OpenAI shape (`chat.completion` or `chat.completion.chunk`). `sources` and `run_id` are added under an `arena` field, which OpenAI SDKs ignore.
- **Ignored parameters:** `temperature` and `max_tokens` from the request are ignored, because the published bot version decides them. This is documented.
- **Model list:** `GET /v1/models` lists the bots the key can use, as `bot:<slug>`.

## gRPC (`proto/arena/v1/bots.proto`)

```proto
syntax = "proto3";
package arena.v1;
import "google/protobuf/struct.proto";

service BotService {
  rpc Invoke(InvokeRequest) returns (InvokeResponse);
  rpc InvokeStream(InvokeRequest) returns (stream InvokeEvent);
  rpc GetConversation(GetConversationRequest) returns (Conversation);
  rpc ListConversations(ListConversationsRequest) returns (ListConversationsResponse);
}

message InvokeRequest {
  string bot = 1;                       // slug or id
  string input = 2;
  string conversation_id = 3;
  string user = 4;
  map<string, string> variables = 5;
  google.protobuf.Struct metadata = 6;
  optional int32 version = 7;
  string idempotency_key = 8;
  repeated HistoryMessage history = 9;  // stateless mode
  optional bool store = 10;
}

message HistoryMessage { string role = 1; string content = 2; }

message Source { int32 cite = 1; string collection = 2; string document = 3; string chunk_id = 4; string text = 5; float score = 6; }
message ToolCall { string id = 1; string name = 2; google.protobuf.Struct arguments = 3; string result = 4; string status = 5; string error = 6; }
message Usage { int32 input_tokens = 1; int32 output_tokens = 2; int32 latency_ms = 3; }

message InvokeResponse {
  string run_id = 1; string conversation_id = 2; string message_id = 3; string content = 4;
  repeated Source sources = 5; repeated ToolCall tool_calls = 6; Usage usage = 7;
  google.protobuf.Struct checks = 8; google.protobuf.Struct metadata = 9; int32 bot_version = 10;
}

message InvokeEvent {
  string type = 1;                      // same names as the SSE event types
  int64 seq = 2;
  oneof payload {
    string text_delta = 10;             // message.delta
    ToolCall tool = 11;                 // tool.call / tool.result
    Source source = 12;                 // retrieval.source
    InvokeResponse completed = 13;      // run.completed
    google.protobuf.Struct data = 14;   // everything else
  }
}
// Conversation messages omitted here; mirrors the REST conversation shapes.
```

Server: `grpc.aio` on `:50051` with standard health and reflection services. The auth interceptor reuses the REST key resolver and rate limiter.

**TLS** (GRPC-7) is set on the instance settings page. It's seeded from `ARENA_GRPC_TLS_MODE`, `ARENA_GRPC_BIND` and `ARENA_GRPC_PORT`:

| Mode | Behaviour |
|---|---|
| `off` | Plaintext, bound to `127.0.0.1` only |
| `app` | The app terminates TLS with an uploaded cert and key; the key is stored encrypted; certs are hot-reloaded when replaced |
| `proxy` | Plaintext on the configured bind address, for a TLS-terminating proxy (Caddy, nginx, Envoy); the UI shows sample proxy config |

## Event schema

Every event is `{ "type": "...", "seq": n, "run_id": "...", "at": "...", "data": {...} }`.

| Type | When | `data` |
|---|---|---|
| `run.started` | run begins | run_id, conversation_id, bot {id, slug, version} |
| `rewrite.completed` | follow-up rewritten | query, changed |
| `retrieval.started` / `retrieval.completed` | per backend | backend, counts, trace stages |
| `retrieval.source` | each selected chunk or fact | Source |
| `tool.call` | model requests a tool | id, name, server, arguments |
| `tool.result` | tool returns | id, name, result (truncated) or error |
| `message.delta` | generated text | text |
| `check.completed` | sentiment / groundedness | kind, result |
| `usage` | after each provider call | provider, model, input_tokens, output_tokens |
| `run.completed` | success | the full invoke response |
| `run.failed` | failure | error {type, message} |
| `run.cancelled` | client disconnected | — |

**Subscription-only events** (not part of a run stream): `conversation.created`, `message.completed`, `tool.called`, `run.failed`, `feedback.created`, `bot.published`.

## Webhooks

**Delivery request:**

```
POST <url>
Content-Type: application/json
User-Agent: RetrievalArena-Webhooks/1
X-Arena-Event: message.completed
X-Arena-Delivery: dlv_…
X-Arena-Signature: t=1761321600,v1=5d1c…e9

{ "id": "evt_…", "type": "message.completed", "created_at": "…", "workspace_id": "ws_…", "data": { … } }
```

**Signature:**
- **Algorithm:** `v1 = hex(HMAC_SHA256(secret, f"{t}.{raw_body}"))`, where `secret` is the subscription's signing secret, or the workspace's callback secret for async runs.
- **Verifying:** receivers recompute the value, compare in constant time, and reject when `|now - t| > 300s`.
- **Reference code:** the docs include verifiers in Python and Node.

**Retries:**
- **Success:** any 2xx counts as delivered.
- **Retry:** any other response, or no response within 10 s, triggers a retry at +1m, +5m, +30m, +2h and +12h.
- **Dead letter:** after the last attempt the delivery is marked `dead`.
- **Replay:** delivery IDs are stable across retries, so receivers can deduplicate.

## Dashboard API (outline)

`/api/system/{profile,recommendations,calculator}` · `/api/instance-settings` · `/api/bots/{id}/endpoints` · `/api/bots/{id}/widget` · `/api/auth/{signup,login,logout,me}` · `/api/credentials` (+ `/{id}/test`) · `/api/collections` (+ documents, ingest → job) · `/api/jobs/{id}` · `/api/personas` · `/api/bots` (+ `/{id}/publish`, `/{id}/versions`, `/{id}/playground` SSE) · `/api/tool-servers` (+ `/{id}/tools`) · `/api/api-keys` · `/api/webhooks` (+ deliveries, replay, ping) · `/api/conversations` · `/api/lab/query` (SSE) · `/api/lab/history` · `/api/usage` · `/api/audit`.

The dashboard API is internal. It's versioned with the frontend, and the public stability promise doesn't cover it.
