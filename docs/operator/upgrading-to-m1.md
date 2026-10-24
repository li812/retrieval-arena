# Upgrading to the M1 foundation release

This release moves the code to `backend/` and `frontend/`, adds database migrations, health endpoints and
structured logs, and adds the new dashboard at `/app/`. Your existing data is kept. Endpoints, request and response
shapes and the classic UI at `/` are unchanged.

## Before you upgrade

Back up the data volume (optional; the app also makes its own database backup, below):

```bash
docker compose stop api
docker run --rm -v retrieval-arena_arena_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/arena_data-before-m1.tgz -C /data .
```

## Upgrade

```bash
git pull
docker compose up --build -d
docker compose ps            # wait for api: healthy
```

## What happens to `arena.db` on first start

The database stays where it was: `/app/arena_data/arena.db` in the `arena_data` volume. `ARENA_DB_PATH` is now an
absolute path, so the move of the code to `/app/backend` doesn't change where the file is found.

On startup the API runs `alembic upgrade head` (turn this off with `AUTO_MIGRATE=false`):

1. If the database has the old tables but no `alembic_version` table (every install before this release), the API
   first copies it with SQLite's online backup to
   `arena_data/arena.db.pre-alembic-<UTC timestamp>.bak`, for example `arena.db.pre-alembic-20261025T101500Z.bak`.
2. The baseline migration `0001_legacy_baseline` creates only the tables that are missing. Existing tables, columns
   and rows are not changed; it then records the revision in `alembic_version`.
3. Later starts find the database at the latest revision and do nothing (no new backup).

The log shows `backed up pre-Alembic database` with the backup path, then `database migrated`.

Check it worked:

```bash
curl -s localhost:8000/readyz             # sqlite ok means the database is reachable and at the latest revision
docker compose exec api ls -l /app/arena_data
```

## Roll back

The old version doesn't need the `alembic_version` table but doesn't mind it, so rolling back the code alone works:

```bash
git checkout <previous commit>
docker compose up --build -d
```

To restore the database exactly as it was before the upgrade, replace it with the backup while the API is stopped:

```bash
docker compose stop api
docker compose run --rm --no-deps --entrypoint sh api -c '
  cd /app/arena_data &&
  rm -f arena.db-wal arena.db-shm &&
  cp arena.db.pre-alembic-<timestamp>.bak arena.db'
docker compose start api
```

Anything written after the upgrade (new keys, bots, conversations, history) is lost when you restore the backup.
Once you're happy with the upgrade you can delete the `.bak` file.

## Health endpoints

| Endpoint | Use it for | Answers |
|---|---|---|
| `GET /healthz` | Liveness (container health, restarts) | Always 200 `{"status":"ok"}` while the process runs; no dependency calls |
| `GET /readyz` | Readiness (load balancers, monitoring) | 200 when SQLite (and migrations at head), Chroma and Neo4j all answer within `READYZ_TIMEOUT_S` (default 2 s); otherwise 503 |

`/readyz` body:

```json
{
  "status": "unavailable",
  "checks": {
    "sqlite": {"ok": true, "latency_ms": 2, "error": null},
    "chroma": {"ok": true, "latency_ms": 9, "error": null},
    "neo4j": {"ok": false, "latency_ms": 2001, "error": "timed out after 2s"}
  }
}
```

The compose file's `api` healthcheck uses `/healthz`, so a Neo4j outage makes `/readyz` fail without restarting
the API.

## Logs

The API writes one JSON object per line to stdout (`docker compose logs api`):

```json
{"ts": "2026-10-25T10:15:02.114+00:00", "level": "INFO", "logger": "app.access", "msg": "request",
 "request_id": "6f1c…", "run_id": null, "method": "POST", "path": "/query", "status": 200, "duration_ms": 4180}
```

- `request_id`: taken from the caller's `X-Request-ID` header when present (letters, digits, `._:-`, up to 128
  characters), otherwise generated. It's echoed in the `X-Request-ID` response header.
- `run_id`: set for each `/query` and `/chat` stream, on every line the run produces (retrieval, ingestion, tool
  calls), with `query run started` / `chat run finished` lines carrying the status and duration.
- One `app.access` line per request with method, path, status and duration. Uvicorn's own access log is off.

Settings (environment variables, see `.env.example`):

| Variable | Default | |
|---|---|---|
| `LOG_FORMAT` | `json` | `console` gives readable lines for local debugging |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

Logs never contain provider API keys.

## Other changes for operators

- The vendored classic-UI assets (Alpine, vis-network, fonts) are fetched during the image build; you no longer run
  `scripts/fetch_vendor_assets.sh` by hand.
- The root `requirements.txt` is gone; dependencies are in `backend/pyproject.toml`.
- The image contains the built dashboard at `/app/frontend_dist` (`ARENA_SPA_DIR`). If it's missing, `/app/`
  answers 503 "frontend not built" and everything else keeps working.
