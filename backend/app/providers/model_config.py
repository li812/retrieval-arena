import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

import openai
from google import genai
from openai import OpenAI

from app.api.schemas import ModelInfo, ValidateKeyResponse
from app.providers.embeddings import EmbeddingAgent
from app.rag.rerank import nvidia_rerank

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
_PROBE_TIMEOUT_S = 15
_VALIDATION_CACHE_TTL_S = 600

# Catalog entries that aren't plain text-chat models (embedders, rerankers,
# safety classifiers, vision/speech/parsing models, ...)
_NVIDIA_NON_CHAT_MARKERS = (
    "embed",
    "rerank",
    "retriever",
    "reward",
    "guard",
    "safety",
    "parse",
    "vlm",
    "vision",
    "-vl",
    "omni",
    "clip",
    "ocr",
    "detector",
    "deplot",
    "kosmos",
    "fuyu",
    "neva",
    "vila",
    "paligemma",
    "riva",
    "cosmos",
)


class ModelConfigAgent:
    def __init__(self):
        # sha256(api_key) -> (monotonic timestamp, response); avoids re-probing every model on each page load
        self._nvidia_cache: dict[str, tuple[float, ValidateKeyResponse]] = {}

    def validate_and_list_models(self, api_key: str, provider: str = "gemini") -> ValidateKeyResponse:
        if provider == "nvidia":
            return self._validate_nvidia(api_key)
        return self._validate_gemini(api_key)

    def _validate_gemini(self, api_key: str) -> ValidateKeyResponse:
        try:
            client = genai.Client(api_key=api_key)
            models = list(client.models.list())

            gen_models: list[ModelInfo] = []
            embed_models: list[ModelInfo] = []

            for model in models:
                actions = getattr(model, "supported_actions", []) or []
                info = ModelInfo(
                    name=model.name,
                    display_name=getattr(model, "display_name", model.name),
                )
                if "generateContent" in actions:
                    gen_models.append(info)
                if "embedContent" in actions:
                    embed_models.append(info)

            return ValidateKeyResponse(
                valid=True,
                gen_models=gen_models,
                embed_models=embed_models,
            )
        except Exception as e:
            return ValidateKeyResponse(valid=False, error=str(e))

    def _validate_nvidia(self, api_key: str) -> ValidateKeyResponse:
        cache_key = hashlib.sha256(api_key.encode()).hexdigest()
        cached = self._nvidia_cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < _VALIDATION_CACHE_TTL_S:
            return cached[1]

        try:
            client = OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL)
            ids = sorted(m.id for m in client.models.list())
        except Exception as e:
            return ValidateKeyResponse(valid=False, error=str(e))

        embed_candidates = [i for i in ids if "embed" in i]
        rerank_candidates = [i for i in ids if "rerank" in i]
        chat_candidates = [i for i in ids if not any(k in i for k in _NVIDIA_NON_CHAT_MARKERS)]

        # The catalog is public, so it says nothing about the key or what the
        # account may call. Probe every candidate with a minimal request: this
        # authenticates the key, drops models the account can't reach (404) or
        # that are retired (410), and measures each embedder's real dimension.
        with ThreadPoolExecutor(max_workers=16) as pool:
            embed_results = list(pool.map(lambda m: self._probe_nvidia_embed(api_key, m), embed_candidates))
            chat_results = list(pool.map(lambda m: self._probe_nvidia_chat(api_key, m), chat_candidates))
            rerank_results = list(pool.map(lambda m: self._probe_nvidia_rerank(api_key, m), rerank_candidates))

        for _, err in embed_results + chat_results:
            if isinstance(err, (openai.AuthenticationError, openai.PermissionDeniedError)):
                return ValidateKeyResponse(valid=False, error=str(err))

        embed_dims = {m: dim for m, (dim, _) in zip(embed_candidates, embed_results, strict=False) if dim}
        gen_ids = [m for m, (ok, _) in zip(chat_candidates, chat_results, strict=False) if ok]

        missing = [kind for kind, found in (("embedding", embed_dims), ("generation", gen_ids)) if not found]
        if missing:
            return ValidateKeyResponse(
                valid=False,
                error=f"Key accepted, but no {' or '.join(missing)} model is usable with this account",
            )

        result = ValidateKeyResponse(
            valid=True,
            gen_models=[ModelInfo(name=i, display_name=i) for i in gen_ids],
            embed_models=[ModelInfo(name=m, display_name=f"{m} ({d}-dim)") for m, d in embed_dims.items()],
            embed_model_dims=embed_dims,
            rerank_models=[
                ModelInfo(name=m, display_name=m)
                for m, ok in zip(rerank_candidates, rerank_results, strict=False)
                if ok
            ],
        )
        self._nvidia_cache[cache_key] = (time.monotonic(), result)
        return result

    @staticmethod
    def _probe_nvidia_embed(api_key: str, model: str) -> tuple[int | None, Exception | None]:
        try:
            vec = EmbeddingAgent().embed_query("test", api_key, model, provider="nvidia", timeout=_PROBE_TIMEOUT_S)
            return len(vec), None
        except Exception as e:
            return None, e

    @staticmethod
    def _probe_nvidia_rerank(api_key: str, model: str) -> bool:
        try:
            nvidia_rerank("test", ["test"], api_key, model, timeout=_PROBE_TIMEOUT_S)
            return True
        except Exception:
            return False

    @staticmethod
    def _probe_nvidia_chat(api_key: str, model: str) -> tuple[bool, Exception | None]:
        try:
            client = OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL, timeout=_PROBE_TIMEOUT_S, max_retries=0)
            client.chat.completions.create(model=model, messages=[{"role": "user", "content": "hi"}], max_tokens=1)
            return True, None
        except Exception as e:
            return False, e
