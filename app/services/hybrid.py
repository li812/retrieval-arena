import math
import re
import threading
from collections import Counter

# Small English stopword list: enough to keep BM25 from matching on glue words
_STOPWORDS = frozenset("""
a an and are as at be but by for from has have he her his how i if in into is it its
me my no not of on or our she so than that the their them then there these they this
to was we were what when where which who whom why will with you your about can do does
did tell
""".split())

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class BM25Index:
    """Okapi BM25 over a fixed set of chunks."""

    def __init__(self, chunks: list[dict], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self._tfs = [Counter(tokenize(c["text"])) for c in chunks]
        self._lens = [sum(tf.values()) for tf in self._tfs]
        self._avg_len = (sum(self._lens) / len(self._lens)) if self._lens else 0.0
        df: Counter = Counter()
        for tf in self._tfs:
            df.update(tf.keys())
        n = len(chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, limit: int, source: str | None = None) -> list[tuple[dict, float]]:
        terms = tokenize(query)
        scored = []
        for chunk, tf, length in zip(self.chunks, self._tfs, self._lens):
            if source and chunk["metadata"].get("source") != source:
                continue
            score = 0.0
            for t in terms:
                f = tf.get(t)
                if not f:
                    continue
                norm = self.k1 * (1 - self.b + self.b * length / (self._avg_len or 1))
                score += self._idf[t] * f * (self.k1 + 1) / (f + norm)
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]


class KeywordIndexCache:
    """One BM25 index per collection, rebuilt whenever the collection's chunk count changes."""

    def __init__(self, vector_store):
        self._vector_store = vector_store
        self._cache: dict[str, tuple[int, BM25Index]] = {}
        self._lock = threading.Lock()

    def get(self, collection: str) -> BM25Index:
        count = self._vector_store.count(collection)
        with self._lock:
            cached = self._cache.get(collection)
            if cached and cached[0] == count:
                return cached[1]
        index = BM25Index(self._vector_store.get(collection))
        with self._lock:
            self._cache[collection] = (count, index)
        return index

    def invalidate(self, collection: str) -> None:
        with self._lock:
            self._cache.pop(collection, None)


def rrf_fuse(ranked_lists: list[tuple[float, list[str]]], k: int = 60) -> dict[str, float]:
    """Weighted Reciprocal Rank Fusion: sum of weight / (k + rank) over every list an id appears in."""
    fused: dict[str, float] = {}
    for weight, ids in ranked_lists:
        for rank, doc_id in enumerate(ids, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + weight / (k + rank)
    return fused
