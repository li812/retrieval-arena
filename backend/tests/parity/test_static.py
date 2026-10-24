def test_index_serves_alpine_ui(arena, snapshot):
    r = arena.client.get("/")
    snapshot("index", {"status": r.status_code, "content_type": r.headers["content-type"].split(";")[0]})
    assert "x-data" in r.text or "alpine" in r.text.lower()


def test_static_assets(arena, snapshot):
    for asset in ("style.css", "app.js", "chat.js", "index.html"):
        r = arena.client.get(f"/static/{asset}")
        snapshot(asset, {"status": r.status_code, "content_type": r.headers["content-type"].split(";")[0]})
        assert r.status_code == 200 and r.content
    snapshot("missing", {"status": arena.client.get("/static/nope.js").status_code})
