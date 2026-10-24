import pytest

from app.core.db import Database, run_migrations


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "repo.db")
    run_migrations(database)
    yield database
    database.dispose()
