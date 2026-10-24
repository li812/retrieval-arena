# Retrieval Arena backend

FastAPI app (`app/`), SQLAlchemy 2 models and Alembic migrations (`alembic/`), tests (`tests/`).
See the main [README](../README.md) for running the whole stack.

## Tests and lint, with nothing installed on the host

Build the dev image once (and again when `pyproject.toml` changes), then run from the repo root:

```bash
docker build -f backend/Dockerfile.dev -t arena-backend-dev backend

docker run --rm -v "$PWD":/work -w /work/backend arena-backend-dev python -m pytest -q
docker run --rm -v "$PWD":/work -w /work/backend arena-backend-dev ruff check .
docker run --rm -v "$PWD":/work -w /work/backend arena-backend-dev ruff format --check .
docker run --rm -v "$PWD":/work -w /work/backend arena-backend-dev \
  sh -c 'alembic -x db_path=/tmp/check.db upgrade head && alembic -x db_path=/tmp/check.db check'
```

With a local Python 3.11+: `pip install -e "backend[dev]"`, then the same commands from `backend/`.

Tests never call real providers, Chroma or Neo4j: `tests/fakes/` holds deterministic fakes.

## Test layout

| Folder | What |
|---|---|
| `tests/unit` | DB pragmas, migrations (fresh and legacy adoption), repositories, settings |
| `tests/integration` | App-level: `/healthz`, `/readyz`, logging and request ids, SPA serving |
| `tests/parity` | Every legacy endpoint against a live server with fakes; compared to `tests/parity/snapshots/` |
| `tests/contract`, `tests/isolation` | Provider contract tests (M3) and workspace isolation tests (M2) |

## Parity snapshots

`tests/parity/snapshots/*.json` record status codes, JSON key shapes and SSE event sequences of the pre-M1 app.
They must not change without a reason. To re-record deliberately: `UPDATE_SNAPSHOTS=1 python -m pytest tests/parity`,
then review the diff.

## Migrations

`alembic upgrade head` runs automatically on startup (`AUTO_MIGRATE=true`). A database created before Alembic is
backed up first to `arena.db.pre-alembic-<UTC timestamp>.bak`. New schema changes:
`alembic revision --autogenerate -m "..."` from `backend/`, review the file, never edit a shipped migration.
