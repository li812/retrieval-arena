import pytest
from sqlalchemy import text

from app.core.db import Database, session_scope
from app.models import Bot


def test_pragmas_on_every_new_connection(tmp_path):
    db = Database(tmp_path / "pragmas.db")
    for _ in range(2):  # a second pooled/new connection gets them too
        with db.engine.connect() as conn:
            assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
            assert conn.execute(text("PRAGMA busy_timeout")).scalar() == 5000
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        db.engine.dispose()


def test_creates_parent_directory(tmp_path):
    db = Database(tmp_path / "nested" / "dir" / "arena.db")
    with db.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert (tmp_path / "nested" / "dir" / "arena.db").exists()


def test_session_scope_rolls_back_on_error(tmp_path):
    db = Database(tmp_path / "rollback.db")
    Bot.metadata.create_all(db.engine)
    with pytest.raises(RuntimeError):
        with session_scope(db.sessionmaker) as s:
            s.add(
                Bot(
                    name="b",
                    system_prompt="p",
                    collection="c",
                    backend="chroma",
                    provider="gemini",
                    gen_model="g",
                    embedding_model="e",
                )
            )
            s.flush()
            raise RuntimeError("boom")
    with db.session() as s:
        assert s.query(Bot).count() == 0
