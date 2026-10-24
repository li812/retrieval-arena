import json
import logging
import re

logger = logging.getLogger(__name__)


class EvaluationAgent:
    """LLM-as-judge checks on a finished answer."""

    def __init__(self, extraction_agent):
        self._llm = extraction_agent

    def groundedness(self, question: str, context: str, answer: str, llm_ctx) -> dict:
        """Split the answer into claims and check each against the retrieved context.

        Returns {"score": 0..1 | None, "claims": [{"claim", "supported", "sources"}]}.
        """
        if not answer.strip():
            return {"score": None, "claims": []}
        prompt = (
            "You verify whether an answer is supported by the retrieved context.\n"
            "Break the ANSWER into its factual claims about the world. Statements that information is "
            "missing or unavailable are NOT claims; if the answer makes no factual claims, "
            'return {"claims": []}. '
            "For each claim decide if the CONTEXT supports it, and list the context source numbers "
            "([1], [2], ...) that support it.\n"
            'Return ONLY JSON: {"claims": [{"claim": "...", "supported": true, "sources": [1]}]}\n\n'
            f"QUESTION: {question}\n\nCONTEXT:\n{context}\n\nANSWER:\n{answer}"
        )
        raw = self._llm.complete(prompt, llm_ctx.api_key, llm_ctx.gen_model, llm_ctx.provider, max_tokens=2048)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            claims = json.loads(match.group(0)).get("claims", []) if match else []
        except json.JSONDecodeError:
            logger.warning("[eval] unparseable groundedness output: %.200r", raw)
            claims = []
        claims = [
            {
                "claim": str(c.get("claim", "")),
                "supported": bool(c.get("supported")),
                "sources": [s for s in c.get("sources", []) if isinstance(s, int)],
            }
            for c in claims
            if isinstance(c, dict) and c.get("claim")
        ]
        score = (sum(c["supported"] for c in claims) / len(claims)) if claims else None
        return {"score": score, "claims": claims}
