import json
import sqlite3
import threading
from typing import Optional

_BOT_COLUMNS = (
    "id, name, emoji, description, system_prompt, collection, backend, provider, gen_model, "
    "embedding_model, key_id, tuning, greeting, starters, tools, created_at, updated_at"
)
_JSON_FIELDS = ("tuning", "starters", "tools")


class BotStore:
    """Bot profiles, conversations and messages, in the same SQLite file as the key store."""

    def __init__(self, db_path: str = "arena.db"):
        self._lock = threading.Lock()
        # timeout: the key store holds its own connection to this file, so wait out its brief write locks
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS bots (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT NOT NULL UNIQUE,
                    emoji           TEXT NOT NULL DEFAULT '◆',
                    description     TEXT NOT NULL DEFAULT '',
                    system_prompt   TEXT NOT NULL,
                    collection      TEXT NOT NULL,
                    backend         TEXT NOT NULL,
                    provider        TEXT NOT NULL,
                    gen_model       TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    key_id          INTEGER,
                    tuning          TEXT NOT NULL DEFAULT '{}',
                    greeting        TEXT NOT NULL DEFAULT '',
                    starters        TEXT NOT NULL DEFAULT '[]',
                    tools           TEXT NOT NULL DEFAULT '[]',
                    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    bot_id     INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
                    title      TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS mcp_servers (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    name       TEXT NOT NULL UNIQUE,
                    transport  TEXT NOT NULL,              -- http | stdio
                    url        TEXT NOT NULL DEFAULT '',
                    command    TEXT NOT NULL DEFAULT '',
                    args       TEXT NOT NULL DEFAULT '[]',
                    env        TEXT NOT NULL DEFAULT '{}',
                    headers    TEXT NOT NULL DEFAULT '{}',  -- e.g. Authorization for remote servers
                    enabled    INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    role            TEXT NOT NULL,       -- user | assistant
                    content         TEXT NOT NULL,
                    meta            TEXT NOT NULL DEFAULT '{}',  -- JSON: sources, trace, rewrite, eval
                    feedback        INTEGER NOT NULL DEFAULT 0,  -- -1 / 0 / 1
                    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
                );
            """)
            self._conn.commit()

    @staticmethod
    def _bot_row(row: sqlite3.Row) -> dict:
        d = dict(row)
        for f in _JSON_FIELDS:
            d[f] = json.loads(d[f])
        return d

    # --- bots ---

    def list_bots(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(f"SELECT {_BOT_COLUMNS} FROM bots ORDER BY name").fetchall()
        return [self._bot_row(r) for r in rows]

    def get_bot(self, bot_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(f"SELECT {_BOT_COLUMNS} FROM bots WHERE id = ?", (bot_id,)).fetchone()
        return self._bot_row(row) if row else None

    def save_bot(self, bot: dict, bot_id: Optional[int] = None) -> dict:
        fields = {k: (json.dumps(v) if k in _JSON_FIELDS else v) for k, v in bot.items()}
        cols = list(fields)
        with self._lock:
            if bot_id is None:
                cur = self._conn.execute(
                    f"INSERT INTO bots ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                    [fields[c] for c in cols],
                )
                bot_id = cur.lastrowid
            else:
                self._conn.execute(
                    f"UPDATE bots SET {', '.join(f'{c} = ?' for c in cols)}, updated_at = datetime('now') "
                    "WHERE id = ?",
                    [fields[c] for c in cols] + [bot_id],
                )
            self._conn.commit()
        return self.get_bot(bot_id)

    def delete_bot(self, bot_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM bots WHERE id = ?", (bot_id,))
            self._conn.commit()
        return cur.rowcount > 0

    # --- conversations ---

    def list_conversations(self, bot_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT c.id, c.bot_id, c.title, c.created_at, c.updated_at, "
                "(SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count "
                "FROM conversations c WHERE c.bot_id = ? ORDER BY c.updated_at DESC, c.id DESC",
                (bot_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def create_conversation(self, bot_id: int, title: str) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO conversations (bot_id, title) VALUES (?, ?)", (bot_id, title[:80] or "New chat")
            )
            self._conn.commit()
        return cur.lastrowid

    def get_conversation(self, conversation_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, bot_id, title, created_at, updated_at FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        return dict(row) if row else None

    def delete_conversation(self, conversation_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
            self._conn.commit()
        return cur.rowcount > 0

    # --- messages ---

    def list_messages(self, conversation_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, role, content, meta, feedback, created_at FROM messages "
                "WHERE conversation_id = ? ORDER BY id",
                (conversation_id,),
            ).fetchall()
        return [{**dict(r), "meta": json.loads(r["meta"])} for r in rows]

    def add_message(self, conversation_id: int, role: str, content: str, meta: Optional[dict] = None) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, meta) VALUES (?, ?, ?, ?)",
                (conversation_id, role, content, json.dumps(meta or {})),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?", (conversation_id,)
            )
            self._conn.commit()
        return cur.lastrowid

    def delete_last_assistant(self, conversation_id: int) -> None:
        """Drop the latest assistant reply (for regenerate)."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM messages WHERE id = (SELECT max(id) FROM messages "
                "WHERE conversation_id = ? AND role = 'assistant')",
                (conversation_id,),
            )
            self._conn.commit()

    def set_feedback(self, message_id: int, value: int) -> bool:
        with self._lock:
            cur = self._conn.execute("UPDATE messages SET feedback = ? WHERE id = ?", (value, message_id))
            self._conn.commit()
        return cur.rowcount > 0

    # --- MCP servers ---

    @staticmethod
    def _server_row(row: sqlite3.Row) -> dict:
        d = dict(row)
        for f in ("args", "env", "headers"):
            d[f] = json.loads(d[f])
        d["enabled"] = bool(d["enabled"])
        return d

    def list_mcp_servers(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM mcp_servers ORDER BY name").fetchall()
        return [self._server_row(r) for r in rows]

    def get_mcp_server(self, server_id: int) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
        return self._server_row(row) if row else None

    def save_mcp_server(self, server: dict) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO mcp_servers (name, transport, url, command, args, env, headers, enabled) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (server["name"], server["transport"], server.get("url", ""), server.get("command", ""),
                 json.dumps(server.get("args", [])), json.dumps(server.get("env", {})),
                 json.dumps(server.get("headers", {})), int(server.get("enabled", True))),
            )
            self._conn.commit()
        return self.get_mcp_server(cur.lastrowid)

    def set_mcp_enabled(self, server_id: int, enabled: bool) -> bool:
        with self._lock:
            cur = self._conn.execute("UPDATE mcp_servers SET enabled = ? WHERE id = ?", (int(enabled), server_id))
            self._conn.commit()
        return cur.rowcount > 0

    def delete_mcp_server(self, server_id: int) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def close(self):
        with self._lock:
            self._conn.close()
