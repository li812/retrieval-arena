import time

from fastapi.testclient import TestClient


def test_healthz_never_touches_dependencies(make_app):
    app, fakes = make_app()
    fakes.vector_store.healthy = False
    fakes.graph_store.healthy = False
    with TestClient(app) as client:
        r = client.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_readyz_all_ok(make_app):
    app, _ = make_app()
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["checks"]) == {"sqlite", "chroma", "neo4j"}
    for check in body["checks"].values():
        assert check["ok"] is True and check["error"] is None and isinstance(check["latency_ms"], int)


def test_readyz_names_the_failing_dependency(make_app):
    app, fakes = make_app()
    with TestClient(app) as client:
        fakes.graph_store.healthy = False
        r = client.get("/readyz")
        assert r.status_code == 503
        assert r.json()["status"] == "unavailable"
        checks = r.json()["checks"]
        assert checks["neo4j"]["ok"] is False and "neo4j is down" in checks["neo4j"]["error"]
        assert checks["chroma"]["ok"] and checks["sqlite"]["ok"]
        assert client.get("/healthz").status_code == 200

        fakes.graph_store.healthy = True
        fakes.vector_store.healthy = False
        checks = client.get("/readyz").json()["checks"]
        assert not checks["chroma"]["ok"] and checks["neo4j"]["ok"]


def test_readyz_times_out_slow_dependency(make_app):
    app, fakes = make_app(readyz_timeout_s=0.2)
    fakes.vector_store.heartbeat = lambda: time.sleep(2)
    with TestClient(app) as client:
        started = time.perf_counter()
        r = client.get("/readyz")
        assert time.perf_counter() - started < 1.5
    assert r.status_code == 503
    assert "timed out" in r.json()["checks"]["chroma"]["error"]


def test_readyz_fails_when_migrations_not_at_head(make_app):
    app, _ = make_app(auto_migrate=False)
    with TestClient(app) as client:
        r = client.get("/readyz")
    assert r.status_code == 503
    assert "expected 0001_legacy_baseline" in r.json()["checks"]["sqlite"]["error"]
