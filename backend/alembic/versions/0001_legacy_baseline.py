"""Legacy baseline: the seven tables created by the pre-M1 key and bot stores.

Each table is created with the legacy DDL only if it doesn't exist, so `upgrade head` adopts an existing arena.db
unchanged and builds the same schema on a fresh one.

Revision ID: 0001_legacy_baseline
Revises:
Create Date: 2026-10-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_legacy_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Creation order respects the foreign keys (bots -> conversations -> messages).
TABLES: dict[str, str] = {
    "api_keys": """
        CREATE TABLE api_keys (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            label      TEXT NOT NULL UNIQUE,
            provider   TEXT NOT NULL,
            api_key    TEXT NOT NULL,
            is_active  INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_used  TEXT
        )
    """,
    "collections": """
        CREATE TABLE collections (
            name           TEXT PRIMARY KEY,
            embed_provider TEXT NOT NULL,
            embed_model    TEXT NOT NULL,
            embed_dim      INTEGER NOT NULL,
            created_at     TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "history": """
        CREATE TABLE history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            question    TEXT NOT NULL,
            backend     TEXT NOT NULL,
            collection  TEXT NOT NULL,
            payload     TEXT NOT NULL,
            pinned      INTEGER NOT NULL DEFAULT 0
        )
    """,
    "bots": """
        CREATE TABLE bots (
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
        )
    """,
    "conversations": """
        CREATE TABLE conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_id     INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            title      TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "mcp_servers": """
        CREATE TABLE mcp_servers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL UNIQUE,
            transport  TEXT NOT NULL,
            url        TEXT NOT NULL DEFAULT '',
            command    TEXT NOT NULL DEFAULT '',
            args       TEXT NOT NULL DEFAULT '[]',
            env        TEXT NOT NULL DEFAULT '{}',
            headers    TEXT NOT NULL DEFAULT '{}',
            enabled    INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
    "messages": """
        CREATE TABLE messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role            TEXT NOT NULL,
            content         TEXT NOT NULL,
            meta            TEXT NOT NULL DEFAULT '{}',
            feedback        INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """,
}


def upgrade() -> None:
    bind = op.get_bind()
    for name, ddl in TABLES.items():
        if not sa.inspect(bind).has_table(name):
            op.execute(ddl)


def downgrade() -> None:
    for name in reversed(TABLES):
        op.drop_table(name)
