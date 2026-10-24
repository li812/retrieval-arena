import pytest

from app.repositories import history as history_module
from app.repositories.collections import CollectionRepository
from app.repositories.history import HistoryRepository


def test_register_and_guard(db):
    repo = CollectionRepository(db.sessionmaker)
    assert repo.get_collection_dim("docs") is None
    repo.register_collection("docs", "gemini", "emb-a", 768)
    repo.register_collection("docs", "gemini", "emb-a", 768)  # same model: no-op
    assert repo.get_collection_dim("docs") == {
        "name": "docs",
        "embed_provider": "gemini",
        "embed_model": "emb-a",
        "embed_dim": 768,
    }
    with pytest.raises(ValueError, match="Dimension mismatch"):
        repo.register_collection("docs", "gemini", "emb-b", 1024)
    with pytest.raises(ValueError, match="Model mismatch"):
        repo.register_collection("docs", "gemini", "emb-b", 768)
    repo.delete_collection("docs")
    assert repo.get_collection_dim("docs") is None


def test_history_search_pin_delete(db):
    repo = HistoryRepository(db.sessionmaker)
    a = repo.add_history("apollo landing", "chroma", "docs", '{"x": 1}')
    b = repo.add_history("mars rover", "graph", "docs", "{}")
    assert [h["id"] for h in repo.list_history()] == [b, a]
    assert [h["question"] for h in repo.list_history("apollo")] == ["apollo landing"]
    assert repo.set_history_pinned(a, True)
    rows = repo.list_history()
    assert rows[0]["id"] == a and rows[0]["pinned"] == 1
    assert list(rows[0]) == ["id", "created_at", "question", "backend", "collection", "payload", "pinned"]
    assert repo.list_history(limit=1)[0]["id"] == a
    assert not repo.set_history_pinned(999, True)
    assert repo.delete_history(b) and not repo.delete_history(b)


def test_history_trims_unpinned_only(db, monkeypatch):
    monkeypatch.setattr(history_module, "_MAX_UNPINNED", 3)
    repo = HistoryRepository(db.sessionmaker)
    pinned = repo.add_history("keep me", "chroma", "docs", "{}")
    repo.set_history_pinned(pinned, True)
    ids = [repo.add_history(f"q{i}", "chroma", "docs", "{}") for i in range(5)]
    remaining = {h["id"] for h in repo.list_history(limit=500)}
    assert remaining == {pinned, *ids[-3:]}
