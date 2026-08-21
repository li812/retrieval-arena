from google import genai
from google.genai import types


class EmbeddingAgent:
    def embed_documents(self, texts: list[str], api_key: str, model: str) -> list[list[float]]:
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

    def embed_query(self, text: str, api_key: str, model: str) -> list[float]:
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
