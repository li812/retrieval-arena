import pytest

from app.core.errors import DuplicateNameError
from app.repositories.provider_keys import ProviderKeyRepository


def test_save_list_never_expose_secret(db):
    repo = ProviderKeyRepository(db.sessionmaker)
    saved = repo.save_key("main", "gemini", "secret-value-9876")
    assert saved["key_hint"] == "9876" and "api_key" not in saved
    assert saved["is_active"] == 0 and saved["last_used"] is None and saved["created_at"]
    assert list(saved) == ["id", "label", "provider", "is_active", "created_at", "last_used", "key_hint"]
    assert [k["label"] for k in repo.list_keys()] == ["main"]
    assert all("api_key" not in k for k in repo.list_keys())
    assert repo.get_key(saved["id"])["api_key"] == "secret-value-9876"
    assert repo.get_key(999) is None


def test_duplicate_label(db):
    repo = ProviderKeyRepository(db.sessionmaker)
    repo.save_key("main", "gemini", "a")
    with pytest.raises(DuplicateNameError, match="UNIQUE constraint failed: api_keys.label"):
        repo.save_key("main", "nvidia", "b")


def test_active_key_per_provider(db):
    repo = ProviderKeyRepository(db.sessionmaker)
    a = repo.save_key("a", "gemini", "aaaa")
    b = repo.save_key("b", "gemini", "bbbb")
    n = repo.save_key("n", "nvidia", "nnnn")
    assert repo.get_active_key("gemini")["id"] == b["id"]  # none active: newest wins
    repo.set_active(a["id"], "gemini")
    repo.set_active(n["id"], "nvidia")
    keys = {k["label"]: k for k in repo.list_keys()}
    assert keys["a"]["is_active"] == 1 and keys["b"]["is_active"] == 0 and keys["a"]["last_used"]
    assert repo.get_active_key("gemini")["api_key"] == "aaaa"
    repo.set_active(b["id"], "gemini")
    assert repo.get_active_key("gemini")["id"] == b["id"]
    assert repo.get_active_key("nvidia")["id"] == n["id"]
    assert repo.get_active_key("openai") is None


def test_delete(db):
    repo = ProviderKeyRepository(db.sessionmaker)
    k = repo.save_key("a", "gemini", "aaaa")
    assert repo.delete_key(k["id"]) is True
    assert repo.delete_key(k["id"]) is False
