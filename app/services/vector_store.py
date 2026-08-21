import chromadb
from app.config import settings


class VectorStore:
    def __init__(self):
        self._client = chromadb.HttpClient(
            host=settings.chroma_host, port=settings.chroma_port
        )

    def get_or_create_collection(self, collection: str) -> chromadb.Collection:
        return self._client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        collection: str,
        chunks: list[str],
        embeddings: list[list[float]],
        ids: list[str],
    ) -> None:
        col = self.get_or_create_collection(collection)
        col.add(documents=chunks, embeddings=embeddings, ids=ids)

    def query(
        self,
        collection: str,
        embedding: list[float],
        top_k: int,
        fetch_k: int = None,
    ) -> list[dict]:
        col = self.get_or_create_collection(collection)
        n = fetch_k if fetch_k is not None else top_k
        results = col.query(
            query_embeddings=[embedding],
            n_results=n,
            include=["documents", "distances", "embeddings"],
        )
        docs = results["documents"][0]
        distances = results["distances"][0]
        ids = results["ids"][0]
        embeddings = results["embeddings"][0]

        # ChromaDB cosine distance: distance = 1 - cosine_similarity
        # So similarity = 1 - distance
        candidates = []
        for doc_id, doc, dist, emb in zip(ids, docs, distances, embeddings):
            candidates.append({
                "id": doc_id,
                "text": doc,
                "score": 1.0 - dist,
                "embedding": emb,
            })

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def list_collections(self) -> list[str]:
        return [col.name for col in self._client.list_collections()]
