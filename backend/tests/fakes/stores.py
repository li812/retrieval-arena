"""In-memory stand-ins for Chroma (VectorStore) and Neo4j (GraphStore) with the same method surface."""

import math
import threading


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _matches(meta: dict, where: dict | None) -> bool:
    return not where or all(meta.get(k) == v for k, v in where.items())


class InMemoryVectorStore:
    def __init__(self):
        self._cols: dict[str, dict[str, dict]] = {}
        self._lock = threading.Lock()
        self.healthy = True

    def heartbeat(self) -> int:
        if not self.healthy:
            raise ConnectionError("chroma is down")
        return 1

    def get_or_create_collection(self, collection: str) -> dict[str, dict]:
        with self._lock:
            return self._cols.setdefault(collection, {})

    def add_chunks(self, collection, chunks, embeddings, ids, metadatas=None):
        col = self.get_or_create_collection(collection)
        metadatas = metadatas or [{} for _ in ids]
        with self._lock:
            for doc_id, text, emb, meta in zip(ids, chunks, embeddings, metadatas, strict=True):
                col[doc_id] = {"id": doc_id, "text": text, "embedding": list(emb), "metadata": dict(meta or {})}

    def query(self, collection, embedding, top_k, fetch_k=None, where=None):
        col = self.get_or_create_collection(collection)
        n = min(fetch_k if fetch_k is not None else top_k, len(col))
        if n <= 0:
            return []
        if col and len(next(iter(col.values()))["embedding"]) != len(embedding):
            raise ValueError("Collection expecting embedding with a different dimension")
        hits = [
            {**c, "score": _cosine(embedding, c["embedding"]), "metadata": dict(c["metadata"])}
            for c in col.values()
            if _matches(c["metadata"], where)
        ]
        hits.sort(key=lambda h: (-h["score"], h["id"]))
        return hits[:n]

    def get(self, collection, ids=None, where=None, with_embeddings=False):
        col = self.get_or_create_collection(collection)
        rows = [col[i] for i in ids if i in col] if ids is not None else list(col.values())
        return [
            {
                "id": c["id"],
                "text": c["text"],
                "metadata": dict(c["metadata"]),
                "embedding": list(c["embedding"]) if with_embeddings else None,
            }
            for c in rows
            if _matches(c["metadata"], where)
        ]

    def count(self, collection):
        return len(self.get_or_create_collection(collection))

    def delete_collection(self, collection):
        with self._lock:
            self._cols.pop(collection, None)

    def list_collections(self):
        with self._lock:
            return list(self._cols)


class InMemoryGraphStore:
    _MATCHERS = {
        "exact": lambda name, q: name.lower() == q.lower(),
        "contains": lambda name, q: q.lower() in name.lower(),
        "fuzzy": lambda name, q: q.lower() in name.lower() or name.lower() in q.lower(),
    }

    def __init__(self):
        # (graph, subject, relation, object, chunk_id)
        self._edges: list[tuple[str, str, str, str, str]] = []
        self._lock = threading.Lock()
        self.healthy = True
        self.closed = False

    def verify_connectivity(self) -> None:
        if not self.healthy:
            raise ConnectionError("neo4j is down")

    def merge_triples(self, graph, chunk_id, triples):
        with self._lock:
            for t in triples:
                edge = (graph, t["subject"], t["relation"], t["object"], chunk_id)
                if edge not in self._edges:
                    self._edges.append(edge)

    def _entities(self, graph):
        names: dict[str, None] = {}
        for g, s, _, o, _ in self._edges:
            if g == graph:
                names[s] = None
                names[o] = None
        return list(names)

    def find_entities(self, graph, names, mode="contains"):
        match = self._MATCHERS.get(mode, self._MATCHERS["contains"])
        with self._lock:
            entities = self._entities(graph)
        found = [e for n in names for e in entities if match(e, n)]
        return list(dict.fromkeys(found))

    def traverse(self, graph, seed_entities, hops, triple_limit, direction="out"):
        out: list[dict] = []
        seen: set[tuple] = set()
        seeds = list(seed_entities)
        with self._lock:
            edges = [e for e in self._edges if e[0] == graph]
        for _ in range(hops):
            nxt: set[str] = set()
            for _, s, r, o, _ in edges:
                if s in seeds:
                    neighbor = o
                elif direction == "both" and o in seeds:
                    neighbor = s
                else:
                    continue
                key = (s, r, o)
                if key not in seen:
                    seen.add(key)
                    out.append({"subject": s, "relation": r, "object": o, "neighbor": neighbor})
                nxt.add(neighbor)
            seeds = list(nxt - set(seed_entities))
            if len(out) >= triple_limit or not seeds:
                break
        return out[:triple_limit]

    def entities_for_chunks(self, graph, chunk_ids):
        result: dict[str, list[str]] = {}
        with self._lock:
            for g, s, _, o, cid in self._edges:
                if g == graph and cid in chunk_ids:
                    names = result.setdefault(cid, [])
                    for n in (s, o):
                        if n not in names:
                            names.append(n)
        return result

    def stats(self, graph):
        with self._lock:
            return {"entities": len(self._entities(graph)), "triples": sum(1 for e in self._edges if e[0] == graph)}

    def delete_graph(self, graph):
        with self._lock:
            self._edges = [e for e in self._edges if e[0] != graph]

    def close(self):
        self.closed = True
