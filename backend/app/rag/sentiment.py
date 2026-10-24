import json
import re

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

EMOTIONS = ("joy", "trust", "fear", "surprise", "sadness", "disgust", "anger", "anticipation")


class SentimentAgent:
    """Local VADER sentiment (instant, no API) plus an optional LLM emotion breakdown."""

    def __init__(self, extraction_agent):
        self._vader = SentimentIntensityAnalyzer()
        self._llm = extraction_agent

    def score(self, text: str) -> dict:
        """{'compound': -1..1, 'label': 'positive'|'neutral'|'negative'} using VADER's standard cut-offs."""
        compound = self._vader.polarity_scores(text or "")["compound"]
        label = "positive" if compound >= 0.05 else "negative" if compound <= -0.05 else "neutral"
        return {"compound": round(compound, 3), "label": label}

    def distribution(self, texts: list[str]) -> dict:
        counts = {"positive": 0, "neutral": 0, "negative": 0}
        for t in texts:
            counts[self.score(t)["label"]] += 1
        return counts

    def emotions(self, text: str, llm_ctx) -> dict:
        """LLM-rated intensity (0..1) for Plutchik's eight basic emotions, plus a one-line tone summary."""
        prompt = (
            "Rate the intensity of each emotion expressed in the text from 0 to 1, and describe its tone "
            "in a few words. Return ONLY JSON like "
            '{"emotions": {"joy": 0.1, "trust": 0.0, "fear": 0.0, "surprise": 0.0, "sadness": 0.0, '
            '"disgust": 0.0, "anger": 0.0, "anticipation": 0.0}, "tone": "..."}\n\n'
            f"Text:\n{text[:6000]}"
        )
        raw = self._llm.complete(prompt, llm_ctx.api_key, llm_ctx.gen_model, llm_ctx.provider, max_tokens=512)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        try:
            data = json.loads(match.group(0)) if match else {}
        except json.JSONDecodeError:
            data = {}
        raw_emotions = data.get("emotions") or {}
        emotions = {}
        for e in EMOTIONS:
            try:
                emotions[e] = max(0.0, min(1.0, float(raw_emotions.get(e, 0))))
            except (TypeError, ValueError):
                emotions[e] = 0.0
        return {"emotions": emotions, "tone": str(data.get("tone", ""))[:120]}
