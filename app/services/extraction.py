import json
import logging
import re

from google import genai
from google.genai import types
from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"

logger = logging.getLogger(__name__)


class GraphExtractionAgent:
    def extract_triples(
        self, chunk: str, api_key: str, model: str, max_triples: int, provider: str = "gemini"
    ) -> list[dict]:
        prompt = (
            f"Extract up to {max_triples} subject-relation-object triples from the text below. "
            "Return ONLY a valid JSON array with no extra text, in this format: "
            '[{"subject": "...", "relation": "...", "object": "..."}]\n\n'
            f"Text:\n{chunk}"
        )

        if provider == "nvidia":
            raw = self._generate_nvidia(prompt, api_key, model)
        else:
            raw = self._generate_gemini(prompt, api_key, model)

        try:
            triples = self._parse_json_array(raw)
        except (json.JSONDecodeError, ValueError):
            fix_prompt = (
                "The following text is supposed to be a JSON array of triples but has a syntax error. "
                "Return ONLY the corrected valid JSON array:\n\n" + raw
            )
            try:
                if provider == "nvidia":
                    fix_raw = self._generate_nvidia(fix_prompt, api_key, model)
                else:
                    fix_raw = self._generate_gemini(fix_prompt, api_key, model)
                triples = self._parse_json_array(fix_raw)
            except (json.JSONDecodeError, ValueError):
                logger.warning("[extract] unparseable triples from %s: %.300r", model, raw)
                return []

        return [
            t for t in triples
            if isinstance(t, dict) and "subject" in t and "relation" in t and "object" in t
        ][:max_triples]

    def complete(
        self, prompt: str, api_key: str, model: str, provider: str = "gemini", max_tokens: int = 2048
    ) -> str:
        """Single deterministic completion — shared by query transforms, reranking and evaluation."""
        if provider == "nvidia":
            return self._generate_nvidia(prompt, api_key, model, max_tokens)
        return self._generate_gemini(prompt, api_key, model, max_tokens)

    def _parse_json_array(self, text: str) -> list:
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    def _generate_gemini(self, prompt: str, api_key: str, model: str, max_tokens: int = 512) -> str:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(temperature=0, max_output_tokens=max_tokens)
        resp = client.models.generate_content(model=model, contents=[prompt], config=config)
        return (resp.text or "").strip()

    def _generate_nvidia(self, prompt: str, api_key: str, model: str, max_tokens: int = 2048) -> str:
        # Fail fast: NVIDIA's hosted queue can hold a request for minutes before a 504,
        # and the client's default 600s timeout x 2 retries would hang ingest silently
        client = OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL, timeout=90, max_retries=0)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            # Headroom for reasoning models, which spend tokens thinking before answering
            max_tokens=max_tokens,
        )
        # content is None when a reasoning model exhausts max_tokens before answering
        content = resp.choices[0].message.content or ""
        return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

    def extract_query_entities(
        self, question: str, api_key: str, model: str, provider: str = "gemini"
    ) -> list[str]:
        prompt = (
            "Extract key named entities from this question as a JSON array of strings. "
            "Return ONLY the JSON array with no extra text.\n\n"
            f"Question: {question}"
        )

        if provider == "nvidia":
            raw = self._generate_nvidia(prompt, api_key, model)
        else:
            raw = self._generate_gemini(prompt, api_key, model)

        try:
            entities = self._parse_json_array(raw)
        except (json.JSONDecodeError, ValueError):
            return []
        return [e for e in entities if isinstance(e, str)]
