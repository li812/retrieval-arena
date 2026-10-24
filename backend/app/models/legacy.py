"""The seven tables created by the pre-M1 key and bot stores, mapped exactly as they exist in `arena.db`.

Names, types, defaults and constraints match the legacy DDL (see tests/fixtures/legacy_schema.sql), so the Alembic
baseline adopts an existing database without changes. SQLite reports primary-key columns declared without NOT NULL
as nullable, hence `nullable=True` on them. Don't rename or drop columns here; M2 migrates them.
"""

from sqlalchemy import ForeignKey, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import LegacyBase

NOW = text("(datetime('now'))")


class ProviderKey(LegacyBase):
    """A model-provider API key (legacy `api_keys`; M2's delivery keys get their own table)."""

    __tablename__ = "api_keys"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=True)
    label: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    last_used: Mapped[str | None] = mapped_column(Text)


class CollectionRecord(LegacyBase):
    __tablename__ = "collections"

    name: Mapped[str] = mapped_column(Text, primary_key=True, nullable=True)
    embed_provider: Mapped[str] = mapped_column(Text, nullable=False)
    embed_model: Mapped[str] = mapped_column(Text, nullable=False)
    embed_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)


class HistoryEntry(LegacyBase):
    __tablename__ = "history"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    backend: Mapped[str] = mapped_column(Text, nullable=False)
    collection: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    pinned: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class Bot(LegacyBase):
    __tablename__ = "bots"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    emoji: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'◆'"))
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    collection: Mapped[str] = mapped_column(Text, nullable=False)
    backend: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    gen_model: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[int | None] = mapped_column(Integer)
    tuning: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    greeting: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    starters: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    tools: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)


class Conversation(LegacyBase):
    __tablename__ = "conversations"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=True)
    bot_id: Mapped[int] = mapped_column(Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)


class McpServer(LegacyBase):
    __tablename__ = "mcp_servers"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    transport: Mapped[str] = mapped_column(Text, nullable=False)  # http | stdio
    url: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    command: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    args: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    env: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    headers: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)


class Message(LegacyBase):
    __tablename__ = "messages"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'{}'"))  # JSON
    feedback: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))  # -1 / 0 / 1
    created_at: Mapped[str] = mapped_column(Text, nullable=False, server_default=NOW)
