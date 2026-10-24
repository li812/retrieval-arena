import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import ConsoleFormatter, JsonFormatter, install_context_ids, request_id_var, run_id_var


def _record(msg="hello", **extra):
    install_context_ids()
    logger = logging.getLogger("test.logging")
    return logger.makeRecord(logger.name, logging.INFO, __file__, 1, msg, (), None, extra=extra)


def test_json_formatter_fields():
    t1, t2 = request_id_var.set("req-1"), run_id_var.set("run-1")
    try:
        line = JsonFormatter().format(_record(path="/x", status=200))
    finally:
        request_id_var.reset(t1)
        run_id_var.reset(t2)
    entry = json.loads(line)
    assert entry["msg"] == "hello" and entry["level"] == "INFO" and entry["logger"] == "test.logging"
    assert entry["request_id"] == "req-1" and entry["run_id"] == "run-1"
    assert entry["path"] == "/x" and entry["status"] == 200 and entry["ts"].endswith("+00:00")


def test_console_formatter():
    line = ConsoleFormatter().format(_record(status=200))
    assert "INFO test.logging hello" in line and "status=200" in line


def test_request_id_echoed_or_generated(make_app):
    app, _ = make_app()
    with TestClient(app) as client:
        given = client.get("/healthz", headers={"X-Request-ID": "abc-123"})
        generated = client.get("/healthz")
        invalid = client.get("/healthz", headers={"X-Request-ID": "bad id with spaces"})
    assert given.headers["x-request-id"] == "abc-123"
    assert len(generated.headers["x-request-id"]) == 32
    assert invalid.headers["x-request-id"] != "bad id with spaces"


def test_access_line_and_run_ids(make_app, caplog):
    app, _ = make_app()
    caplog.set_level(logging.INFO)
    with TestClient(app) as client:
        key = client.post("/keys", json={"label": "k", "provider": "gemini", "api_key": "fake-0000"}).json()["id"]
        client.post(
            "/ingest",
            data={
                "collection": "c",
                "key_id": str(key),
                "embedding_model": "fake-embed",
                "gen_model": "fake-gen",
                "text": "Apollo 11 landed on the Moon in 1969.",
            },
        )
        q = client.post(
            "/query",
            headers={"X-Request-ID": "req-query"},
            json={
                "question": "Apollo?",
                "collection": "c",
                "key_id": key,
                "gen_model": "fake-gen",
                "embedding_model": "fake-embed",
            },
        )
        assert "event: done" in q.text
        bot = client.post(
            "/bots",
            json={
                "name": "b",
                "collection": "c",
                "gen_model": "fake-gen",
                "embedding_model": "fake-embed",
                "key_id": key,
            },
        ).json()
        c = client.post("/chat", headers={"X-Request-ID": "req-chat"}, json={"bot_id": bot["id"], "message": "hi"})
        assert "event: done" in c.text

    access = [r for r in caplog.records if r.name == "app.access" and r.request_id == "req-query"]
    assert access and access[0].method == "POST" and access[0].path == "/query" and access[0].status == 200
    assert isinstance(access[0].duration_ms, int)
    for request_id, kind in (("req-query", "query"), ("req-chat", "chat")):
        runs = [r for r in caplog.records if r.getMessage().startswith(f"{kind} run") and r.request_id == request_id]
        assert {r.getMessage() for r in runs} == {f"{kind} run started", f"{kind} run finished"}
        assert runs[0].run_id and len({r.run_id for r in runs}) == 1
    ingest_lines = [r for r in caplog.records if r.name == "app.rag.ingestion"]
    assert ingest_lines and all(r.request_id for r in ingest_lines)
