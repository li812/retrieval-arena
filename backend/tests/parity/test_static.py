def test_index_serves_alpine_ui(arena, snapshot):
    r = arena.client.get("/")
    snapshot("index", {"status": r.status_code, "content_type": r.headers["content-type"].split(";")[0]})
    assert "x-data" in r.text or "alpine" in r.text.lower()


# Python's mimetypes reads the OS table, so .js is application/javascript on Debian
# images and text/javascript on Ubuntu runners; both are valid (RFC 9239)
_JS_TYPES = {"application/javascript", "text/javascript"}


def _content_type(r) -> str:
    ctype = r.headers["content-type"].split(";")[0]
    return "application/javascript" if ctype in _JS_TYPES else ctype


def test_static_assets(arena, snapshot):
    for asset in ("style.css", "app.js", "chat.js", "index.html"):
        r = arena.client.get(f"/static/{asset}")
        snapshot(asset, {"status": r.status_code, "content_type": _content_type(r)})
        assert r.status_code == 200 and r.content
    snapshot("missing", {"status": arena.client.get("/static/nope.js").status_code})
