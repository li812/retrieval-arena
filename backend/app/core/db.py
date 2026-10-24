"""SQLite engine, sessions and startup migrations.

Sync SQLAlchemy (D22): the legacy code runs DB calls in worker threads, so a sync session per call is enough.
"""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
LEGACY_TABLES = ("api_keys", "collections", "history", "bots", "conversations", "mcp_servers", "messages")


def _set_pragmas(dbapi_conn, _record) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


def make_engine(db_path: str | Path) -> Engine:
    path = Path(db_path)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{path}", connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _set_pragmas)
    return engine


class Database:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.engine = make_engine(db_path)
        self.sessionmaker = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with session_scope(self.sessionmaker) as s:
            yield s

    def dispose(self) -> None:
        self.engine.dispose()


@contextmanager
def session_scope(factory: sessionmaker) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def alembic_config(engine: Engine | None = None, url: str | None = None):
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["engine"] = engine
    cfg.attributes["configure_logger"] = False
    return cfg


def head_revision() -> str | None:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    from alembic.runtime.migration import MigrationContext

    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def backup_sqlite(db_path: Path) -> Path:
    """Online copy with sqlite3's backup API (consistent even with WAL and open connections)."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = db_path.with_name(f"{db_path.name}.pre-alembic-{stamp}.bak")
    src = sqlite3.connect(db_path)
    try:
        dst = sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return target


def run_migrations(db: Database) -> None:
    """Upgrade to head. A database created before Alembic (legacy tables, no version table) is backed up first."""
    from alembic import command

    tables = set(inspect(db.engine).get_table_names())
    if tables & set(LEGACY_TABLES) and "alembic_version" not in tables:
        backup = backup_sqlite(db.path)
        logger.info("backed up pre-Alembic database", extra={"backup": str(backup)})
    before = current_revision(db.engine)
    command.upgrade(alembic_config(engine=db.engine), "head")
    after = current_revision(db.engine)
    if before != after:
        logger.info("database migrated", extra={"from_revision": before, "to_revision": after})
