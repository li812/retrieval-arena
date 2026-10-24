import json

from tests.fixtures.pdf import make_pdf
from tests.parity.harness import json_summary

TXT = (
    "The Hubble Space Telescope was launched in 1990. It orbits Earth above the atmosphere.\n\n"
    "Hubble observations helped determine the rate of expansion of the universe."
)


def _form(key_id: int, collection: str, **extra) -> dict:
    data = {"collection": collection, "key_id": str(key_id), "embedding_model": "fake-embed", "gen_model": "fake-gen"}
    data.update(extra)
    return data


def test_ingest_txt_and_pdf_files(arena, snapshot, gemini_key):
    pdf = make_pdf(["The James Webb Space Telescope launched in 2021.", "It observes in the infrared."])
    files = [
        ("files", ("hubble.txt", TXT.encode(), "text/plain")),
        ("files", ("webb.pdf", pdf, "application/pdf")),
    ]
    tuning = json.dumps({"chunk_size": 100, "chunk_overlap": 10, "chunking_strategy": "fixed"})
    r = arena.client.post("/ingest", data=_form(gemini_key, "ingest-files", tuning=tuning), files=files)
    snapshot("files_fixed", json_summary(r))
    body = r.json()
    assert body["documents"] == 2 and body["num_chunks"] > 2 and body["num_triples"] > 0

    sources = {c["metadata"]["source"] for c in arena.fakes.vector_store.get("ingest-files")}
    assert sources == {"hubble.txt", "webb.pdf"}
    texts = " ".join(c["text"] for c in arena.fakes.vector_store.get("ingest-files"))
    assert "Webb" in texts


def test_ingest_text_sentence_aware_with_graph(arena, snapshot, gemini_key):
    tuning = json.dumps(
        {
            "chunking_strategy": "sentence_aware",
            "chunk_size": 120,
            "chunk_overlap": 30,
            "max_triples_per_chunk": 2,
            "contextual_headers": True,
        }
    )
    r = arena.client.post("/ingest", data=_form(gemini_key, "ingest-text", tuning=tuning, text=TXT))
    snapshot("text_sentence_aware", json_summary(r))
    assert r.json()["documents"] == 1
    assert arena.fakes.graph_store.stats("ingest-text")["triples"] > 0
    assert all(c["text"].startswith("[Context:") for c in arena.fakes.vector_store.get("ingest-text"))


def test_ingest_vector_only(arena, snapshot, gemini_key):
    """Extraction that yields no triples leaves the collection vector-only (nothing in the graph)."""
    saved = arena.fakes.extraction.triples
    arena.fakes.extraction.triples = []
    try:
        r = arena.client.post("/ingest", data=_form(gemini_key, "ingest-vector-only", text=TXT))
    finally:
        arena.fakes.extraction.triples = saved
    snapshot("vector_only", json_summary(r))
    assert r.json()["num_triples"] == 0
    assert arena.fakes.graph_store.stats("ingest-vector-only")["triples"] == 0


def test_ingest_errors(arena, snapshot, gemini_key):
    c = arena.client
    snapshot("nothing_to_ingest", json_summary(c.post("/ingest", data=_form(gemini_key, "ingest-err"))))
    snapshot("no_key", json_summary(c.post("/ingest", data={"collection": "ingest-err", "text": "hello"})))
    snapshot(
        "empty_files",
        json_summary(
            c.post(
                "/ingest", data=_form(gemini_key, "ingest-err"), files=[("files", ("empty.txt", b"   ", "text/plain"))]
            )
        ),
    )
    snapshot("blank_text", json_summary(c.post("/ingest", data=_form(gemini_key, "ingest-err", text="   "))))

    assert c.post("/ingest", data=_form(gemini_key, "ingest-dims", text=TXT)).status_code == 200
    snapshot(
        "dimension_mismatch",
        json_summary(
            c.post("/ingest", data=_form(gemini_key, "ingest-dims", text=TXT, embedding_model="fake-embed-small"))
        ),
    )
    snapshot(
        "model_mismatch",
        json_summary(
            c.post("/ingest", data=_form(gemini_key, "ingest-dims", text=TXT, embedding_model="fake-embed-alt"))
        ),
    )
