# 07 — Providers

## Capability matrix

| | OpenAI | Anthropic | Gemini | NVIDIA NIM | Ollama |
|---|---|---|---|---|---|
| Auth | API key | API key (`x-api-key`) | API key | API key (`nvapi-`) | None (base URL) |
| Base URL | `api.openai.com/v1` (overridable) | `api.anthropic.com` | Google default | `integrate.api.nvidia.com/v1` | `http://host:11434` (configurable) |
| Chat API | Chat Completions | Messages | `generate_content` | OpenAI-compatible Chat Completions | `/api/chat` |
| Streaming | ✓ | ✓ (typed SSE events) | ✓ | ✓ | ✓ (NDJSON) |
| Tool calling | ✓ `tools` / `tool_calls` | ✓ `tool_use` / `tool_result` blocks | ✓ function declarations | ✓ on many models (probe) | ✓ on supporting models (probe) |
| Embeddings | ✓ (`text-embedding-3-*`, dims configurable) | ✗ (no embedding API) | ✓ | ✓ (needs `input_type`) | ✓ `/api/embed` |
| Rerank | ✗ (use the LLM judge) | ✗ (use the LLM judge) | ✗ (use the LLM judge) | ✓ hosted rerankers when entitled | ✗ (use the LLM judge) |
| Model listing | `models.list` | `models.list` | `models.list` | catalog + per-model probe (catalog is public) | `/api/tags` |
| SDK | `openai` | `anthropic` | `google-genai` | `openai` | `httpx` (native API) |

## Mapping to the internal format

Internal messages: `system | user | assistant(text, tool_calls[]) | tool(tool_call_id, content)`.

| Concern | OpenAI / NVIDIA | Anthropic | Gemini | Ollama |
|---|---|---|---|---|
| System prompt | `system` message | top-level `system` | `system_instruction` | `system` message |
| Assistant tool call | `tool_calls[{id, function{name, arguments(json str)}}]` | content block `tool_use{id, name, input(obj)}` | `function_call{name, args}` (id may be absent → synthesize) | `tool_calls[{function{name, arguments(obj)}}]` (no id → synthesize) |
| Tool result | `role: tool, tool_call_id` | `user` message with `tool_result{tool_use_id}` blocks | `function_response{name, response}` part | `role: tool` |
| Required params | — | `max_tokens` always | — | — |
| Stream deltas | `choices[].delta.content` / `tool_calls` | `content_block_delta` (`text_delta`, `input_json_delta`) | chunk `.text`, `function_calls` | `message.content` per line |
| Usage | `usage` (final chunk with `stream_options.include_usage`) | `message_start` + `message_delta.usage` | `usage_metadata` | `prompt_eval_count`, `eval_count` |
| Reasoning text | strip `<think>…</think>` if present | thinking blocks hidden unless enabled | — | strip `<think>…</think>` |

## Discovery and probing

- **Model lists** come from the provider; nothing is hardcoded. Today's approach of hardcoding NVIDIA model names failed when models were retired, which is why.
- **NVIDIA**: the catalog is public and doesn't show what a key can use, so each candidate gets a minimal request with a 15 s timeout and no retries (today's `model_config.py`). Results are cached for 10 minutes per credential and stored in `model_capabilities`.
- **Tool support** is probed only when a bot first enables tools on a model, and the result is cached. Today's `/config/tool-support` does this for NVIDIA.
- **Embedding dimensions** are measured with one embed call when a collection is created, and stored on the collection.
- **Ollama**: `/api/tags` for models. `/api/show` gives capabilities such as tool support and the embedding model family where the server reports them.

## Timeouts and retries

Retrying a call that might have partly succeeded can double the cost, so the defaults are conservative and live in the provider registry:
- **Connect:** 10 s.
- **Read:** 90 s for chat, 30 s for embeddings, 15 s for probes.
- **Retries:** none for streaming calls. One retry on 429 or 5xx for non-streaming calls, honouring `Retry-After`.
- **NVIDIA:** queue waits of minutes followed by a 504 are expected on the free tier. Calls surface as `provider_error` with the upstream message.

## Embeddings per collection

A collection is bound to one embedding credential and one embedding model, recorded at creation. Ingest and query both use that binding, so model mismatches can't happen. That replaces today's dimension-and-model guard. A bot's chat credential can be any provider, including Anthropic, regardless of how its collections were embedded.

## Adding a provider later

1. Implement `ChatProvider`, and `EmbeddingProvider` or `RerankProvider` where the provider offers them, in `providers/<name>.py`.
2. Register it in `registry.py` with its credential schema (secret required? base URL?).
3. Add recorded fixtures and run the shared contract suite.
4. Add its row to this matrix.

`PROV-10` (any OpenAI-compatible base URL) covers vLLM, LM Studio, OpenRouter, Together and others without new code.
