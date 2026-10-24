import asyncio
import time
from collections.abc import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import get_services
from app.core.container import Services
from app.core.db import current_revision, head_revision

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    """Liveness: the process is up and serving. Never touches a dependency."""
    return {"status": "ok"}


def _check_sqlite(svc: Services) -> None:
    with svc.db.engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    current, head = current_revision(svc.db.engine), head_revision()
    if current != head:
        raise RuntimeError(f"database at revision {current}, expected {head}")


async def _run_check(fn: Callable[[], object], timeout: float) -> dict:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(asyncio.to_thread(fn), timeout)
        ok, error = True, None
    except TimeoutError:
        ok, error = False, f"timed out after {timeout:g}s"
    except Exception as exc:
        ok, error = False, str(exc) or type(exc).__name__
    return {"ok": ok, "latency_ms": int((time.perf_counter() - started) * 1000), "error": error}


@router.get("/readyz")
async def readyz(svc: Services = Depends(get_services)):
    """Readiness: SQLite (and migrations at head), Chroma and Neo4j all answer within readyz_timeout_s."""
    timeout = svc.settings.readyz_timeout_s
    checks = {
        "sqlite": lambda: _check_sqlite(svc),
        "chroma": svc.vector_store.heartbeat,
        "neo4j": svc.graph_store.verify_connectivity,
    }
    results = await asyncio.gather(*(_run_check(fn, timeout) for fn in checks.values()))
    body = {"checks": dict(zip(checks, results, strict=True))}
    ready = all(r["ok"] for r in results)
    body = {"status": "ok" if ready else "unavailable", **body}
    return JSONResponse(body, status_code=200 if ready else 503)
