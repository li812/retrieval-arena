from typing import Generator


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class RetrievalAgent:
    def __init__(self, embedding_agent, vector_store, graph_store, extraction_agent):
        self._embedding_agent = embedding_agent
        self._vector_store = vector_store
        self._graph_store = graph_store
        self._extraction_agent = extraction_agent

    def retrieve_chroma(
        self,
        question: str,
        collection: str,
        embedding: list[float],
        tuning,
    ) -> Generator[dict, None, None]:
        top_k = tuning.top_k
        fetch_k = top_k * 4
        mmr_diversity = tuning.mmr_diversity
        threshold = tuning.similarity_threshold

        candidates = self._vector_store.query(
            collection, embedding, top_k=top_k, fetch_k=fetch_k
        )

        yield {
            "event": "candidates_found",
            "data": {"count": len(candidates), "ids": [c["id"] for c in candidates]},
        }

        if not candidates:
            yield {"event": "context_assembled", "data": {"chunks": []}}
            return

        # MMR re-ranking
        if mmr_diversity > 0 and len(candidates) > 1:
            selected: list[dict] = []
            remaining = list(candidates)

            while remaining and len(selected) < top_k:
                best = None
                best_score = float("-inf")
                for cand in remaining:
                    sim_to_query = cand["score"]
                    if selected:
                        max_sim_to_selected = max(
                            _cosine_similarity(cand["embedding"], s["embedding"])
                            for s in selected
                        )
                    else:
                        max_sim_to_selected = 0.0
                    mmr_score = (
                        (1 - mmr_diversity) * sim_to_query
                        - mmr_diversity * max_sim_to_selected
                    )
                    if mmr_score > best_score:
                        best_score = mmr_score
                        best = cand
                if best is not None:
                    selected.append(best)
                    remaining.remove(best)

            reranked = selected
        else:
            reranked = candidates[:top_k]

        # Apply similarity threshold
        filtered = [c for c in reranked if c["score"] >= threshold]

        final_chunks = []
        for rank, chunk in enumerate(filtered, start=1):
            yield {
                "event": "chunk_scored",
                "data": {
                    "chunk_id": chunk["id"],
                    "score": chunk["score"],
                    "text": chunk["text"],
                    "rank": rank,
                },
            }
            final_chunks.append({"id": chunk["id"], "text": chunk["text"], "score": chunk["score"]})

        yield {
            "event": "context_assembled",
            "data": {"chunks": final_chunks},
        }

    def retrieve_graph(
        self,
        question: str,
        collection: str,
        tuning,
        api_key: str,
        gen_model: str,
    ) -> Generator[dict, None, None]:
        query_entities = self._extraction_agent.extract_query_entities(
            question, api_key, gen_model
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

        seed_entities = self._graph_store.find_entities(collection, query_entities)
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
                collection, current_seeds, hops=1, triple_limit=tuning.triple_limit
            )

            new_triples = []
            next_seeds: set[str] = set()
            for triple in hop_triples:
                key = (triple["subject"], triple["relation"], triple["object"])
                if key not in seen:
                    seen.add(key)
                    all_triples.append(triple)
                    new_triples.append(triple)
                next_seeds.add(triple["object"])

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
