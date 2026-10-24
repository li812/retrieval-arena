from google import genai
from google.genai import types
from openai import OpenAI

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


class EmbeddingAgent:
    def embed_documents(
        self, texts: list[str], api_key: str, model: str, provider: str = "gemini"
    ) -> list[list[float]]:
        if provider == "nvidia":
            return self._embed_nvidia(texts, api_key, model, task_type="passage")
        return self._embed_gemini_documents(texts, api_key, model)

    def embed_query(
        self, text: str, api_key: str, model: str, provider: str = "gemini",
        timeout: float | None = None,
    ) -> list[float]:
        if provider == "nvidia":
            return self._embed_nvidia([text], api_key, model, task_type="query", timeout=timeout)[0]
        return self._embed_gemini_query(text, api_key, model)

    def _embed_gemini_documents(self, texts: list[str], api_key: str, model: str) -> list[list[float]]:
        client = genai.Client(api_key=api_key)
        all_embeddings: list[list[float]] = []
        for text in texts:
            resp = client.models.embed_content(
                model=model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_DOCUMENT",
                    output_dimensionality=768,
                ),
            )
            all_embeddings.append(resp.embeddings[0].values)
        return all_embeddings

    def _embed_gemini_query(self, text: str, api_key: str, model: str) -> list[float]:
        client = genai.Client(api_key=api_key)
        resp = client.models.embed_content(
            model=model,
            contents=[text],
            config=types.EmbedContentConfig(
                task_type="RETRIEVAL_QUERY",
                output_dimensionality=768,
            ),
        )
        return resp.embeddings[0].values

    def _embed_nvidia(
        self, texts: list[str], api_key: str, model: str, task_type: str,
        timeout: float | None = None,
    ) -> list[list[float]]:
        client = (
            OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL, timeout=timeout, max_retries=0)
            if timeout else OpenAI(api_key=api_key, base_url=NVIDIA_BASE_URL)
        )
        # NVIDIA's retrieval embedders are asymmetric and require input_type
        extra = {"input_type": task_type, "truncate": "END"}
        resp = client.embeddings.create(model=model, input=texts, extra_body=extra)
        return [item.embedding for item in resp.data]
