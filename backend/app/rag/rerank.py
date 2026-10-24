import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

NVIDIA_RERANK_URL = "https://ai.api.nvidia.com/v1/retrieval/{model}/reranking"
_PASSAGE_CHARS = 700


def nvidia_rerank(query: str, passages: list[str], api_key: str, model: str, timeout: float = 30) -> list[float]:
    """Score passages with a hosted NVIDIA reranker; returns one logit per passage, in input order."""
    # Hosted reranker URLs spell dots in the model id as underscores
    url = NVIDIA_RERANK_URL.format(model=model.replace(".", "_"))
    resp = httpx.post(
        url,
        json={"model": model, "query": {"text": query}, "passages": [{"text": p} for p in passages]},
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    scores = [0.0] * len(passages)
    for item in resp.json().get("rankings", []):
        scores[item["index"]] = float(item["logit"])
    return scores


class RerankAgent:
    def __init__(self, extraction_agent):
        self._llm = extraction_agent

    def rerank(self, query: str, passages: list[str], method: str, llm_ctx) -> list[float]:
        """Return a relevance score per passage (input order). `method` is 'llm' or a reranker model id."""
        if method == "llm":
            return self._llm_judge(query, passages, llm_ctx)
        return nvidia_rerank(query, passages, llm_ctx.api_key, method)

    def _llm_judge(self, query: str, passages: list[str], llm_ctx) -> list[float]:
        # Listwise judging: one call scores every candidate, so cost stays flat as the pool grows
        listing = "\n\n".join(f"[{i}] {p[:_PASSAGE_CHARS]}" for i, p in enumerate(passages, start=1))
        prompt = (
            "You are a search relevance judge. Score how well each passage answers the query, "
            "from 0 (irrelevant) to 10 (directly answers it).\n"
            'Return ONLY a JSON object mapping passage number to score, e.g. {"1": 7, "2": 0}.\n\n'
            f"Query: {query}\n\nPassages:\n{listing}"
        )
        raw = self._llm.complete(prompt, llm_ctx.api_key, llm_ctx.gen_model, llm_ctx.provider, max_tokens=1024)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            data = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            data = {}
        if not data:
            logger.warning("[rerank] unparseable judge output: %.200r", raw)
        scores = []
        for i in range(1, len(passages) + 1):
            try:
                scores.append(float(data.get(str(i), 0)))
            except (TypeError, ValueError):
                scores.append(0.0)
        return scores
