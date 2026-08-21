import json

from google import genai
from google.genai import types


class GraphExtractionAgent:
    def extract_triples(
        self, chunk: str, api_key: str, model: str, max_triples: int
    ) -> list[dict]:
        client = genai.Client(api_key=api_key)
        prompt = (
            f"Extract up to {max_triples} subject-relation-object triples from the text below. "
            "Return ONLY a valid JSON array with no extra text, in this format: "
            '[{"subject": "...", "relation": "...", "object": "..."}]\n\n'
            f"Text:\n{chunk}"
        )
        config = types.GenerateContentConfig(temperature=0, max_output_tokens=512)

        resp = client.models.generate_content(model=model, contents=[prompt], config=config)
        raw = resp.text.strip()

        try:
            triples = self._parse_json_array(raw)
        except (json.JSONDecodeError, ValueError):
            # Retry once: ask Gemini to fix the malformed JSON
            fix_prompt = (
                "The following text is supposed to be a JSON array of triples but has a syntax error. "
                "Return ONLY the corrected valid JSON array:\n\n" + raw
            )
            fix_resp = client.models.generate_content(
                model=model, contents=[fix_prompt], config=config
            )
            triples = self._parse_json_array(fix_resp.text.strip())

        return [
            t for t in triples
            if isinstance(t, dict) and "subject" in t and "relation" in t and "object" in t
        ][:max_triples]

    def _parse_json_array(self, text: str) -> list:
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())

    def extract_query_entities(self, question: str, api_key: str, model: str) -> list[str]:
        client = genai.Client(api_key=api_key)
        prompt = (
            "Extract key named entities from this question as a JSON array of strings. "
            "Return ONLY the JSON array with no extra text.\n\n"
            f"Question: {question}"
        )
        resp = client.models.generate_content(
            model=model,
            contents=[prompt],
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=512),
        )
        raw = resp.text.strip()
        try:
            entities = self._parse_json_array(raw)
        except (json.JSONDecodeError, ValueError):
            return []
        return [e for e in entities if isinstance(e, str)]
