import re
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def test_sqlite3_only_in_backup_helper():
    users = sorted(
        str(p.relative_to(APP))
        for p in APP.rglob("*.py")
        if re.search(r"^\s*(import sqlite3|from sqlite3)", p.read_text(), re.MULTILINE)
    )
    assert users == ["core/db.py"]


def test_legacy_stores_are_gone():
    assert not list(APP.rglob("key_store.py")) and not list(APP.rglob("bot_store.py"))
