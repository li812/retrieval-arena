import threading

import chromadb


class VectorStore:
    def __init__(self, host: str, port: int):
        self._host, self._port = host, port
        self._client_obj = None
        self._lock = threading.Lock()

    @property
    def _client(self):
        # Connect on first use: the HttpClient constructor calls the server, and the app must start without Chroma
        with self._lock:
            if self._client_obj is None:
                self._client_obj = chromadb.HttpClient(host=self._host, port=self._port)
            return self._client_obj

    def heartbeat(self) -> int:
        return self._client.heartbeat()

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
        metadatas: list[dict] | None = None,
    ) -> None:
        col = self.get_or_create_collection(collection)
        col.upsert(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)

    def query(
        self,
        collection: str,
        embedding: list[float],
        top_k: int,
        fetch_k: int = None,
        where: dict | None = None,
    ) -> list[dict]:
        col = self.get_or_create_collection(collection)
        n = fetch_k if fetch_k is not None else top_k
        n = min(n, col.count())
        if n <= 0:
            return []
        results = col.query(
            query_embeddings=[embedding],
            n_results=n,
            where=where,
            include=["documents", "distances", "embeddings", "metadatas"],
        )
        docs = results["documents"][0]
        distances = results["distances"][0]
        ids = results["ids"][0]
        embeddings = results["embeddings"][0]
        metadatas = results["metadatas"][0]

        # ChromaDB cosine distance: distance = 1 - cosine_similarity
        # So similarity = 1 - distance
        candidates = []
        for doc_id, doc, dist, emb, meta in zip(ids, docs, distances, embeddings, metadatas, strict=False):
            candidates.append(
                {
                    "id": doc_id,
                    "text": doc,
                    "score": 1.0 - dist,
                    "embedding": emb,
                    "metadata": meta or {},
                }
            )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates

    def get(
        self, collection: str, ids: list[str] | None = None, where: dict | None = None, with_embeddings: bool = False
    ) -> list[dict]:
        """Fetch chunks by id (or all of them) without a similarity search."""
        col = self.get_or_create_collection(collection)
        include = ["documents", "metadatas"] + (["embeddings"] if with_embeddings else [])
        res = col.get(ids=ids, where=where, include=include)
        embs = res.get("embeddings") if with_embeddings else None
        out = []
        for i, doc_id in enumerate(res["ids"]):
            out.append(
                {
                    "id": doc_id,
                    "text": res["documents"][i],
                    "metadata": (res["metadatas"][i] if res.get("metadatas") else None) or {},
                    "embedding": embs[i] if embs is not None else None,
                }
            )
        return out

    def count(self, collection: str) -> int:
        return self.get_or_create_collection(collection).count()

    def delete_collection(self, collection: str) -> None:
        try:
            self._client.delete_collection(collection)
        except Exception:
            pass

    def list_collections(self) -> list[str]:
        return [col.name for col in self._client.list_collections()]
