import pytest

from tests.parity.harness import json_summary, parse_sse, sse_summary

QUESTION = "When did Apollo 11 land on the Moon?"


def _query(arena, key_id, collection, backend="chroma", embedding_model="fake-embed", **tuning):
    body = {
        "question": QUESTION,
        "backend": backend,
        "collection": collection,
        "key_id": key_id,
        "gen_model": "fake-gen",
        "embedding_model": embedding_model,
        "provider": "gemini",
        "tuning": tuning,
    }
    return arena.client.post("/query", json=body)


CHROMA_CASES = {
    "dense": {"search_mode": "dense"},
    "hybrid": {"search_mode": "hybrid", "hybrid_alpha": 0.6},
    "keyword": {"search_mode": "keyword"},
    "multi_query": {"query_transform": "multi_query", "multi_query_n": 3},
    "hyde": {"query_transform": "hyde"},
    "step_back": {"query_transform": "step_back", "search_mode": "hybrid"},
    "rerank_llm": {"rerank": "llm", "fetch_k": 6},
    "order_document": {"context_order": "document", "context_window": 1},
    "order_sandwich": {"context_order": "sandwich", "mmr_diversity": 0.0, "max_context_tokens": 60},
    "order_score_threshold": {"context_order": "score", "similarity_threshold": 0.99},
    "source_filter": {"source_filter": "pasted text"},
    "groundedness": {"check_groundedness": True},
}


@pytest.mark.parametrize("case", list(CHROMA_CASES))
def test_query_chroma(arena, snapshot, gemini_key, lab_collection, case):
    r = _query(arena, gemini_key, lab_collection, **CHROMA_CASES[case])
    summary = sse_summary(r)
    snapshot(f"chroma_{case}", summary)
    names = [n for n, _ in parse_sse(r.text)]
    assert names[0] == "embedding_started" and names[-1] == "done", names
    assert "error" not in names


@pytest.mark.parametrize("entity_match", ["contains", "exact", "fuzzy"])
@pytest.mark.parametrize("direction", ["out", "both"])
def test_query_graph(arena, snapshot, gemini_key, lab_collection, entity_match, direction):
    r = _query(
        arena,
        gemini_key,
        lab_collection,
        backend="graph",
        entity_match=entity_match,
        graph_direction=direction,
        graph_hops=2,
    )
    snapshot(f"graph_{entity_match}_{direction}", sse_summary(r))
    events = parse_sse(r.text)
    assert events[-1][0] == "done"
    triples = next(d for n, d in events if n == "context_assembled")["triples"]
    assert triples, "the fake graph should yield triples for 'Apollo 11'"


def test_query_graph_groundedness(arena, snapshot, gemini_key, lab_collection):
    snapshot(
        "graph_groundedness",
        sse_summary(_query(arena, gemini_key, lab_collection, backend="graph", check_groundedness=True)),
    )


def test_query_graph_no_entities(arena, snapshot, gemini_key, lab_collection):
    saved = arena.fakes.extraction.entities
    arena.fakes.extraction.entities = ["Voyager"]
    try:
        r = _query(arena, gemini_key, lab_collection, backend="graph")
    finally:
        arena.fakes.extraction.entities = saved
    snapshot("graph_no_entities", sse_summary(r))


def test_query_compare(arena, snapshot, gemini_key, lab_collection):
    r = _query(arena, gemini_key, lab_collection, backend="compare", search_mode="hybrid")
    snapshot("compare", sse_summary(r))
    names = [n for n, _ in parse_sse(r.text)]
    assert names[0] == "compare_started" and names[-1] == "done"
    assert "chroma_answer_token" in names and "graph_answer_token" in names


def test_query_compare_groundedness(arena, snapshot, gemini_key, lab_collection):
    snapshot(
        "compare_groundedness",
        sse_summary(_query(arena, gemini_key, lab_collection, backend="compare", check_groundedness=True)),
    )


def test_query_dimension_mismatch(arena, snapshot, gemini_key, lab_collection):
    r = _query(arena, gemini_key, lab_collection, embedding_model="fake-embed-small")
    snapshot("dimension_mismatch", sse_summary(r))
    assert "Dimension mismatch" in parse_sse(r.text)[-1][1]["message"]


def test_query_model_mismatch(arena, snapshot, gemini_key, lab_collection):
    r = _query(arena, gemini_key, lab_collection, embedding_model="fake-embed-alt")
    snapshot("model_mismatch", sse_summary(r))
    assert "Model mismatch" in parse_sse(r.text)[-1][1]["message"]


def test_query_compare_mismatch(arena, snapshot, gemini_key, lab_collection):
    snapshot(
        "compare_mismatch",
        sse_summary(_query(arena, gemini_key, lab_collection, backend="compare", embedding_model="fake-embed-alt")),
    )


def test_query_without_key(arena, snapshot, lab_collection):
    r = arena.client.post(
        "/query",
        json={
            "question": QUESTION,
            "collection": lab_collection,
            "gen_model": "fake-gen",
            "embedding_model": "fake-embed",
        },
    )
    snapshot("no_key", json_summary(r))


def test_query_invalid_body(arena, snapshot, gemini_key):
    snapshot("invalid_backend", json_summary(_query(arena, gemini_key, "lab", backend="sql")))
