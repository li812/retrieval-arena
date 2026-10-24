"""Deterministic stand-ins for the model providers. No network, no keys.

They duck-type the legacy agents (EmbeddingAgent, GenerationAgent, GraphExtractionAgent, ModelConfigAgent) and the
OpenAI client used by the MCP tool loop and the tool-support probe.
"""

import hashlib
import json
import math
import re
from types import SimpleNamespace

DEFAULT_DIM = 32
TOKENS = ["Apollo 11 ", "landed on ", "the Moon ", "in 1969 [1]."]


def _hash_embed(text: str, dim: int) -> list[float]:
    """Bag-of-words hashing: texts sharing words get similar vectors, so retrieval order is meaningful."""
    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) % 2 else -1.0
    if not any(vec):
        vec[0] = 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


class FakeEmbedding:
    """Per-model dimensions so the dimension and model mismatch guards can be exercised."""

    def __init__(self, dim: int = DEFAULT_DIM, model_dims: dict[str, int] | None = None):
        self.dim = dim
        self.model_dims = model_dims or {"fake-embed-small": 16}
        self.calls: list[tuple[str, int]] = []

    def _dim(self, model: str) -> int:
        return self.model_dims.get(model, self.dim)

    def embed_documents(self, texts, api_key, model, provider="gemini"):
        self.calls.append(("documents", len(texts)))
        return [_hash_embed(t, self._dim(model)) for t in texts]

    def embed_query(self, text, api_key, model, provider="gemini", timeout=None):
        self.calls.append(("query", 1))
        return _hash_embed(text, self._dim(model))


class FakeGeneration:
    """Scripted token streams for one-shot answers and multi-turn chat."""

    def __init__(self, tokens: list[str] | None = None):
        self.tokens = list(tokens or TOKENS)

    def stream_answer(
        self, question, context, system_prompt, api_key, model, temperature, max_output_tokens, provider="gemini"
    ):
        yield from self.tokens

    def stream_chat(
        self, system_prompt, history, user_content, api_key, model, temperature, max_output_tokens, provider="gemini"
    ):
        yield from self.tokens


TRIPLES = [
    {"subject": "Apollo 11", "relation": "landed on", "object": "Moon"},
    {"subject": "Neil Armstrong", "relation": "commanded", "object": "Apollo 11"},
    {"subject": "Moon", "relation": "orbits", "object": "Earth"},
]


class FakeExtraction:
    """Fixed triples and entities; `complete` answers each known prompt with well-formed output."""

    def __init__(self, triples: list[dict] | None = None, entities: list[str] | None = None):
        self.triples = triples or TRIPLES
        self.entities = entities or ["Apollo 11"]

    def extract_triples(self, chunk, api_key, model, max_triples, provider="gemini"):
        return [dict(t) for t in self.triples][:max_triples]

    def extract_query_entities(self, question, api_key, model, provider="gemini"):
        return list(self.entities)

    def complete(self, prompt, api_key, model, provider="gemini", max_tokens=2048):
        if "different search queries" in prompt:
            return json.dumps(["apollo moon landing", "first crewed lunar landing", "1969 mission"])
        if "step-back" in prompt:
            return "What is the history of lunar exploration?"
        if "hypothetical" in prompt or "plausibly answer" in prompt:
            return "Apollo 11 was the first crewed mission to land on the Moon, in July 1969."
        if "search relevance judge" in prompt:
            n = len(re.findall(r"^\[\d+\]", prompt, re.MULTILINE))
            return json.dumps({str(i): 10 - (i % 10) for i in range(1, n + 1)})
        if "verify whether an answer is supported" in prompt:
            return json.dumps(
                {"claims": [{"claim": "Apollo 11 landed on the Moon", "supported": True, "sources": [1]}]}
            )
        if "intensity of each emotion" in prompt:
            return json.dumps({"emotions": {"joy": 0.6, "trust": 0.4}, "tone": "upbeat"})
        if "standalone search query" in prompt:
            return "When did Apollo 11 land on the Moon?"
        if "situates this chunk" in prompt:
            return "This chunk is about the Apollo program."
        return "ok"


class FakeModelConfig:
    def validate_and_list_models(self, api_key, provider="gemini"):
        if api_key == "bad-key":
            return {
                "valid": False,
                "error": "API key not valid",
                "gen_models": [],
                "embed_models": [],
                "embed_model_dims": {},
                "rerank_models": [],
            }
        return {
            "valid": True,
            "error": None,
            "gen_models": [{"name": "fake-gen", "display_name": "Fake Gen"}],
            "embed_models": [{"name": "fake-embed", "display_name": "Fake Embed"}],
            "embed_model_dims": {"fake-embed": DEFAULT_DIM} if provider == "nvidia" else {},
            "rerank_models": [],
        }


class FakeOpenAI:
    """Stands in for `openai.OpenAI`: the first tool-enabled call requests one tool, the next one answers.

    Covers ToolRunner._run_openai (NVIDIA tool loop) and the /config/tool-support probe.
    """

    tool_arguments: dict[str, dict] = {}

    def __init__(self, *args, **kwargs):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, tools=None, **kwargs):
        already_called = any(m.get("role") == "tool" for m in messages if isinstance(m, dict))
        if tools and not already_called:
            name = tools[0]["function"]["name"]
            args = self.tool_arguments.get(name, {})
            call = SimpleNamespace(
                id="call_1", type="function", function=SimpleNamespace(name=name, arguments=json.dumps(args))
            )
            message = SimpleNamespace(content=None, tool_calls=[call])
        else:
            tool_text = next((m["content"] for m in messages if isinstance(m, dict) and m.get("role") == "tool"), "")
            message = SimpleNamespace(
                content=f"<think>plan</think>Used a tool ({len(tool_text)} chars).", tool_calls=None
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])
