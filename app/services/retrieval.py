import json
import re
import time
from dataclasses import dataclass
from typing import Generator

from app.services.hybrid import KeywordIndexCache, rrf_fuse
from app.services.rerank import RerankAgent

_SEQ_SUFFIX = re.compile(r"^(.*)_(\d{4})$")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class LLMContext:
    """Credentials and models for the LLM/embedding calls a retrieval run may need."""
    api_key: str
    gen_model: str
    embedding_model: str
    provider: str


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    span = (hi - lo) or 1.0
    return {k: (v - lo) / span for k, v in values.items()}


def _chunk_position(chunk: dict) -> tuple[str, int] | None:
    """(document prefix, sequence number) from metadata, or parsed from the '<prefix>_0007' id."""
    meta = chunk.get("metadata") or {}
    if "doc" in meta and "seq" in meta:
        return meta["doc"], int(meta["seq"])
    m = _SEQ_SUFFIX.match(chunk["id"])
    return (m.group(1), int(m.group(2))) if m else None


class RetrievalAgent:
    def __init__(self, embedding_agent, vector_store, graph_store, extraction_agent, sentiment_agent=None):
        self._embedding_agent = embedding_agent
        self._sentiment = sentiment_agent
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._extraction_agent = extraction_agent
        self._keyword = KeywordIndexCache(vector_store)
        self._reranker = RerankAgent(extraction_agent)

    def invalidate_keyword_index(self, collection: str) -> None:
        self._keyword.invalidate(collection)

    # ------------------------------------------------------------------
    # Query transforms
    # ------------------------------------------------------------------

    def _transform_query(self, question: str, tuning, llm: LLMContext) -> tuple[list[str], str | None]:
        """Returns (extra query variants, hypothetical passage for HyDE)."""
        complete = lambda prompt: self._extraction_agent.complete(  # noqa: E731
            prompt, llm.api_key, llm.gen_model, llm.provider, max_tokens=1024
        )
        mode = tuning.query_transform
        if mode == "multi_query":
            raw = complete(
                f"Write {tuning.multi_query_n} different search queries that would help find documents "
                "answering the question below. Vary wording and angle. "
                "Return ONLY a JSON array of strings.\n\n"
                f"Question: {question}"
            )
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            try:
                variants = json.loads(match.group(0)) if match else []
            except json.JSONDecodeError:
                variants = []
            return [v for v in variants if isinstance(v, str) and v.strip()][: tuning.multi_query_n], None
        if mode == "step_back":
            broader = complete(
                "Rewrite the question below as a broader, more general 'step-back' question about the "
                "underlying topic. Return ONLY the rewritten question.\n\n"
                f"Question: {question}"
            )
            return ([broader.strip()] if broader.strip() else []), None
        if mode == "hyde":
            passage = complete(
                "Write a short factual passage (3-4 sentences) that would plausibly answer the question "
                "below, as if taken from a reference document. Return ONLY the passage.\n\n"
                f"Question: {question}"
            )
            return [], (passage.strip() or None)
        return [], None

    # ------------------------------------------------------------------
    # Chunk retrieval pipeline
    # ------------------------------------------------------------------

    def retrieve_chroma(
        self,
        question: str,
        collection: str,
        embedding: list[float],
        tuning,
        llm: LLMContext | None = None,
    ) -> Generator[dict, None, None]:
        """transform → dense/keyword search → fuse → rerank → MMR → threshold → expand → pack."""
        stages: list[dict] = []
        clock = time.perf_counter

        def stage(name: str, started: float, detail: str = ""):
            stages.append({"name": name, "ms": int((clock() - started) * 1000), "detail": detail})

        top_k = tuning.top_k
        pool = max(tuning.fetch_k, top_k)
        mode = tuning.search_mode
        where = {"source": tuning.source_filter} if tuning.source_filter else None

        # 1. Query transforms
        variants: list[str] = []
        hyde_passage = None
        if tuning.query_transform != "none" and llm:
            t = clock()
            try:
                variants, hyde_passage = self._transform_query(question, tuning, llm)
            except Exception as exc:
                yield {"event": "pipeline_warning", "data": {"stage": "transform", "message": str(exc)}}
            stage("transform", t, tuning.query_transform)
            yield {
                "event": "query_transformed",
                "data": {"mode": tuning.query_transform, "queries": variants, "hyde": hyde_passage},
            }
        keyword_queries = [question] + variants

        cands: dict[str, dict] = {}
        ranked_lists: list[tuple[float, list[str]]] = []
        dense_w = tuning.hybrid_alpha if mode == "hybrid" else 1.0
        keyword_w = (1 - tuning.hybrid_alpha) if mode == "hybrid" else 1.0

        def remember(c: dict):
            prev = cands.get(c["id"])
            if prev is None:
                cands[c["id"]] = {**c, "scores": {}}
            elif c.get("embedding") is not None and prev.get("embedding") is None:
                prev["embedding"] = c["embedding"]

        # 2a. Dense search (original question, each variant, and the HyDE passage)
        if mode in ("dense", "hybrid"):
            t = clock()
            vectors = [embedding]
            if llm and variants:
                vectors += [
                    self._embedding_agent.embed_query(v, llm.api_key, llm.embedding_model, llm.provider)
                    for v in variants
                ]
            if llm and hyde_passage:
                # A hypothetical answer is a document, so embed it on the passage side
                vectors += self._embedding_agent.embed_documents(
                    [hyde_passage], llm.api_key, llm.embedding_model, provider=llm.provider
                )
            for vec in vectors:
                hits = self._vector_store.query(collection, vec, top_k=pool, fetch_k=pool, where=where)
                for h in hits:
                    remember(h)
                ranked_lists.append((dense_w, [h["id"] for h in hits]))
            stage("dense", t, f"{len(vectors)} vector(s)")

        # 2b. Keyword (BM25) search
        bm25_scores: dict[str, float] = {}
        if mode in ("keyword", "hybrid"):
            t = clock()
            index = self._keyword.get(collection)
            for q in keyword_queries:
                hits = index.search(q, pool, source=tuning.source_filter)
                for chunk, score in hits:
                    remember({**chunk, "embedding": None})
                    bm25_scores[chunk["id"]] = max(score, bm25_scores.get(chunk["id"], 0.0))
                ranked_lists.append((keyword_w, [c["id"] for c, _ in hits]))
            stage("keyword", t, f"{len(keyword_queries)} query(s), {len(index.chunks)} chunks indexed")

        # Every candidate needs an embedding for its dense score and for MMR
        missing = [cid for cid, c in cands.items() if c.get("embedding") is None]
        if missing:
            for c in self._vector_store.get(collection, ids=missing, with_embeddings=True):
                cands[c["id"]]["embedding"] = c["embedding"]
        for c in cands.values():
            c["scores"]["dense"] = _cosine_similarity(embedding, c["embedding"]) if c.get("embedding") is not None else 0.0
            if c["id"] in bm25_scores:
                c["scores"]["bm25"] = bm25_scores[c["id"]]

        # 3. Fusion
        if len(ranked_lists) > 1:
            fused = rrf_fuse(ranked_lists)
            for cid, score in fused.items():
                cands[cid]["scores"]["fused"] = score
            primary = fused
        elif mode == "keyword":
            primary = bm25_scores
        else:
            primary = {cid: c["scores"]["dense"] for cid, c in cands.items()}
        ordered = sorted(cands.values(), key=lambda c: primary.get(c["id"], 0.0), reverse=True)[:pool]

        yield {
            "event": "candidates_found",
            "data": {
                "count": len(ordered),
                "ids": [c["id"] for c in ordered],
                "lists": len(ranked_lists),
                "mode": mode,
            },
        }
        if not ordered:
            yield {"event": "pipeline_trace", "data": {"stages": stages}}
            yield {"event": "context_assembled", "data": {"chunks": []}}
            return

        # 4. Rerank
        relevance = _normalize({c["id"]: primary.get(c["id"], 0.0) for c in ordered})
        if tuning.rerank != "none" and llm:
            t = clock()
            try:
                scores = self._reranker.rerank(question, [c["text"] for c in ordered], tuning.rerank, llm)
                for c, s in zip(ordered, scores):
                    c["scores"]["rerank"] = s
                ordered.sort(key=lambda c: c["scores"]["rerank"], reverse=True)
                relevance = _normalize({c["id"]: c["scores"]["rerank"] for c in ordered})
                stage("rerank", t, tuning.rerank)
                yield {
                    "event": "reranked",
                    "data": {"method": tuning.rerank, "scores": {c["id"]: c["scores"]["rerank"] for c in ordered}},
                }
            except Exception as exc:
                stage("rerank", t, "failed")
                yield {"event": "pipeline_warning", "data": {"stage": "rerank", "message": str(exc)}}

        # 5. MMR diversification over the current relevance order
        t = clock()
        mmr_diversity = tuning.mmr_diversity
        if mmr_diversity > 0 and len(ordered) > 1:
            selected: list[dict] = []
            remaining = list(ordered)
            while remaining and len(selected) < top_k:
                def mmr_score(cand):
                    redundancy = max(
                        (_cosine_similarity(cand["embedding"], s["embedding"]) for s in selected),
                        default=0.0,
                    )
                    return (1 - mmr_diversity) * relevance.get(cand["id"], 0.0) - mmr_diversity * redundancy
                best = max(remaining, key=mmr_score)
                selected.append(best)
                remaining.remove(best)
            picked = selected
        else:
            picked = ordered[:top_k]
        stage("select", t, f"MMR λ={mmr_diversity:.2f}" if mmr_diversity > 0 else "top-k")

        # 6. Similarity threshold on the dense score
        picked = [c for c in picked if c["scores"]["dense"] >= tuning.similarity_threshold]

        # 7. Context expansion with neighbouring chunks
        if tuning.context_window > 0 and picked:
            t = clock()
            self._expand_neighbours(collection, picked, tuning.context_window)
            stage("expand", t, f"±{tuning.context_window}")

        # 8. Packing: order and token budget, then citation numbers
        packed = self._pack(picked, tuning)

        for rank, chunk in enumerate(picked, start=1):
            chunk["rank"] = rank
        try:
            entities = self._graph_store.entities_for_chunks(collection, [c["id"] for c in picked])
        except Exception:
            entities = {}  # graph enrichment is cosmetic; never fail retrieval over it
        for chunk in picked:
            yield {
                "event": "chunk_scored",
                "data": {
                    "chunk_id": chunk["id"],
                    "score": chunk["scores"]["dense"],
                    "scores": chunk["scores"],
                    "text": chunk["text"],
                    "rank": chunk["rank"],
                    "cite": chunk.get("cite"),
                    "source": (chunk.get("metadata") or {}).get("source"),
                    "expanded": chunk.get("context_text", chunk["text"]) != chunk["text"],
                    "dropped": chunk.get("cite") is None,
                    "entities": entities.get(chunk["id"], [])[:8],
                    "sentiment": self._sentiment.score(chunk["text"]) if self._sentiment else None,
                },
            }

        yield {"event": "pipeline_trace", "data": {"stages": stages}}
        yield {
            "event": "context_assembled",
            "data": {
                "chunks": [
                    {
                        "id": c["id"],
                        "text": c["text"],
                        "context_text": c.get("context_text", c["text"]),
                        "score": c["scores"]["dense"],
                        "cite": c["cite"],
                    }
                    for c in packed
                ],
            },
        }

    def _expand_neighbours(self, collection: str, picked: list[dict], window: int) -> None:
        wanted: dict[str, list[str]] = {}
        for c in picked:
            pos = _chunk_position(c)
            if not pos:
                continue
            prefix, seq = pos
            wanted[c["id"]] = [f"{prefix}_{i:04d}" for i in range(seq - window, seq + window + 1) if i >= 0]
        all_ids = sorted({i for ids in wanted.values() for i in ids})
        if not all_ids:
            return
        texts = {c["id"]: c["text"] for c in self._vector_store.get(collection, ids=all_ids)}
        for c in picked:
            ids = wanted.get(c["id"])
            if ids:
                # Overlapping chunks repeat text at their seams; acceptable for a context window
                c["context_text"] = "\n".join(texts[i] for i in ids if i in texts)

    @staticmethod
    def _pack(picked: list[dict], tuning) -> list[dict]:
        """Order chunks for the prompt, enforce the token budget, and assign [n] citation numbers."""
        budget = tuning.max_context_tokens
        kept, used = [], 0
        for c in picked:  # budget is spent in relevance order
            cost = max(1, len(c.get("context_text", c["text"])) // 4)  # ~4 chars per token
            if budget and used + cost > budget and kept:
                continue
            kept.append(c)
            used += cost

        if tuning.context_order == "document":
            kept.sort(key=lambda c: _chunk_position(c) or (c["id"], 0))
        elif tuning.context_order == "sandwich":
            # Best chunks at both ends: models attend least to the middle of long contexts
            front, back = [], []
            for i, c in enumerate(kept):
                (front if i % 2 == 0 else back).append(c)
            kept = front + back[::-1]

        for i, c in enumerate(kept, start=1):
            c["cite"] = i
        return kept

    def retrieve_graph(
        self,
        question: str,
        collection: str,
        tuning,
        api_key: str,
        gen_model: str,
        provider: str = "gemini",
    ) -> Generator[dict, None, None]:
        query_entities = self._extraction_agent.extract_query_entities(
            question, api_key, gen_model, provider=provider
        )

        yield {
            "event": "candidates_found",
            "data": {"count": len(query_entities), "entities": query_entities},
        }

        if not query_entities:
            yield {
                "event": "context_assembled",
                "data": {"triples": [], "entities": []},
            }
            return

        seed_entities = self._graph_store.find_entities(
            collection, query_entities, mode=getattr(tuning, "entity_match", "contains")
        )
        if not seed_entities:
            yield {
                "event": "context_assembled",
                "data": {"triples": [], "entities": []},
            }
            return

        all_triples: list[dict] = []
        seen: set[tuple] = set()
        current_seeds = list(seed_entities)
        all_entities: set[str] = set(seed_entities)

        for hop in range(1, tuning.graph_hops + 1):
            if not current_seeds:
                break

            hop_triples = self._graph_store.traverse(
                collection, current_seeds, hops=1, triple_limit=tuning.triple_limit,
                direction=getattr(tuning, "graph_direction", "both"),
            )

            new_triples = []
            next_seeds: set[str] = set()
            for triple in hop_triples:
                neighbor = triple.pop("neighbor", triple["object"])
                key = (triple["subject"], triple["relation"], triple["object"])
                if key not in seen:
                    seen.add(key)
                    all_triples.append(triple)
                    new_triples.append(triple)
                next_seeds.add(neighbor)

            yield {
                "event": "hop_traversed",
                "data": {"hop": hop, "triples": new_triples},
            }

            all_entities.update(next_seeds)
            current_seeds = list(next_seeds - set(current_seeds))

            if len(all_triples) >= tuning.triple_limit:
                break

        final_triples = all_triples[: tuning.triple_limit]
        yield {
            "event": "context_assembled",
            "data": {
                "triples": final_triples,
                "entities": list(all_entities),
            },
        }
