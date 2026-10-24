"""Alembic environment. The app passes its engine via `config.attributes["engine"]`; the CLI builds one from settings
(or `-x db_path=...`), always with the app's SQLite pragmas."""

from logging.config import fileConfig

from alembic import context

from app.core.db import make_engine
from app.models import ALL_METADATA

config = context.config
target_metadata = ALL_METADATA

if config.config_file_name and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)


# SQLite reflection drops ON DELETE from inline `REFERENCES ... ON DELETE CASCADE`, so autogenerate would report the
# two legacy foreign keys as changed. They're checked directly (PRAGMA foreign_key_list) in tests/unit/test_migrations.
_LEGACY_FK_TABLES = {"conversations", "messages"}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "foreign_key_constraint" and obj.table.name in _LEGACY_FK_TABLES:
        return False
    return True


def _engine():
    engine = config.attributes.get("engine")
    if engine is not None:
        return engine
    db_path = context.get_x_argument(as_dictionary=True).get("db_path")
    if not db_path:
        from app.core.config import settings

        db_path = settings.arena_db_path
    return make_engine(db_path)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url") or "sqlite:///arena.db",
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with _engine().connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
