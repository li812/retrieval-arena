import sqlite3
import threading
from typing import Optional


class KeyStore:
    def __init__(self, db_path: str = "arena.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    label      TEXT NOT NULL UNIQUE,
                    provider   TEXT NOT NULL,
                    api_key    TEXT NOT NULL,
                    is_active  INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    last_used  TEXT
                );

                CREATE TABLE IF NOT EXISTS collections (
                    name           TEXT PRIMARY KEY,
                    embed_provider TEXT NOT NULL,
                    embed_model    TEXT NOT NULL,
                    embed_dim      INTEGER NOT NULL,
                    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS history (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                    question    TEXT NOT NULL,
                    backend     TEXT NOT NULL,
                    collection  TEXT NOT NULL,
                    payload     TEXT NOT NULL,   -- JSON: settings, answers, chunks, evaluation, timing
                    pinned      INTEGER NOT NULL DEFAULT 0
                );
            """)
            self._conn.commit()

    @staticmethod
    def _public(row: sqlite3.Row) -> dict:
        """Row without the secret: callers outside the server only ever see the last 4 chars."""
        d = dict(row)
        d["key_hint"] = d.pop("api_key")[-4:]
        return d

    def list_keys(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, label, provider, api_key, is_active, created_at, last_used FROM api_keys ORDER BY id"
            ).fetchall()
        return [self._public(r) for r in rows]

    def get_active_key(self, provider: str) -> Optional[dict]:
        """The key last selected in the UI for this provider — used by server-side callers like MCP tools."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, label, provider, api_key FROM api_keys WHERE provider = ? "
                "ORDER BY is_active DESC, last_used DESC, id DESC LIMIT 1",
                (provider,),
            ).fetchone()
        return dict(row) if row else None

    def get_key(self, key_id: int) -> Optional[dict]:
        """Full row including the plaintext key — for server-side use only."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, label, provider, api_key FROM api_keys WHERE id = ?", (key_id,)
            ).fetchone()
        return dict(row) if row else None

    def save_key(self, label: str, provider: str, api_key: str) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO api_keys (label, provider, api_key) VALUES (?, ?, ?)",
                (label, provider, api_key),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT id, label, provider, api_key, is_active, created_at, last_used FROM api_keys WHERE id = ?",
                (cur.lastrowid,),
            ).fetchone()
        return self._public(row)

    def delete_key(self, key_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def set_active(self, key_id: int, provider: str):
        with self._lock:
            self._conn.execute(
                "UPDATE api_keys SET is_active = 0 WHERE provider = ?", (provider,)
            )
            self._conn.execute(
                "UPDATE api_keys SET is_active = 1, last_used = datetime('now') WHERE id = ?",
                (key_id,),
            )
            self._conn.commit()

    def get_collection_dim(self, name: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT name, embed_provider, embed_model, embed_dim FROM collections WHERE name = ?",
                (name,),
            ).fetchone()
        return dict(row) if row else None

    def register_collection(self, name: str, embed_provider: str, embed_model: str, embed_dim: int):
        with self._lock:
            existing = self._conn.execute(
                "SELECT embed_dim, embed_model FROM collections WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                if existing["embed_dim"] != embed_dim:
                    raise ValueError(
                        f"Dimension mismatch: collection '{name}' uses {existing['embed_dim']}-dim "
                        f"({existing['embed_model']}), but {embed_model} produces {embed_dim}-dim."
                    )
                # Same size is not enough: vectors from different models live in different spaces
                if existing["embed_model"] != embed_model:
                    raise ValueError(
                        f"Model mismatch: collection '{name}' was embedded with {existing['embed_model']}; "
                        f"ingesting with {embed_model} would silently corrupt retrieval."
                    )
                return
            self._conn.execute(
                "INSERT INTO collections (name, embed_provider, embed_model, embed_dim) VALUES (?, ?, ?, ?)",
                (name, embed_provider, embed_model, embed_dim),
            )
            self._conn.commit()

    def delete_collection(self, name: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM collections WHERE name = ?", (name,))
            self._conn.commit()

    # --- query history ---

    def add_history(self, question: str, backend: str, collection: str, payload: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO history (question, backend, collection, payload) VALUES (?, ?, ?, ?)",
                (question, backend, collection, payload),
            )
            # Keep the table bounded; pinned entries are never trimmed
            self._conn.execute(
                "DELETE FROM history WHERE pinned = 0 AND id NOT IN "
                "(SELECT id FROM history ORDER BY id DESC LIMIT 500)"
            )
            self._conn.commit()
        return cur.lastrowid

    def list_history(self, search: str = "", limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, created_at, question, backend, collection, payload, pinned FROM history "
                "WHERE question LIKE ? ORDER BY pinned DESC, id DESC LIMIT ?",
                (f"%{search}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def set_history_pinned(self, history_id: int, pinned: bool) -> bool:
        with self._lock:
            cur = self._conn.execute("UPDATE history SET pinned = ? WHERE id = ?", (int(pinned), history_id))
            self._conn.commit()
        return cur.rowcount > 0

    def delete_history(self, history_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM history WHERE id = ?", (history_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self):
        with self._lock:
            self._conn.close()
