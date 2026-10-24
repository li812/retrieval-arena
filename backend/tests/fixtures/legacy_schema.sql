-- Verbatim DDL from the pre-M1 stores (app/services/key_store.py and app/services/bot_store.py).
-- Used to build "legacy" databases for the adoption tests. Do not edit.

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
