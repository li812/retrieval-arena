from fastapi.testclient import TestClient


def _dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root>SPA</div>")
    (dist / "assets" / "index-abc123.js").write_text("console.log('spa')")
    (dist / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("outside")
    return dist


def test_spa_served_with_deep_link_fallback(make_app, tmp_path):
    app, _ = make_app(spa_dir=str(_dist(tmp_path)))
    with TestClient(app) as client:
        redirect = client.get("/app", follow_redirects=False)
        assert redirect.status_code == 307 and redirect.headers["location"] == "/app/"
        for path in ("/app/", "/app/settings", "/app/bots/42/edit", "/app/no-such-page"):
            r = client.get(path)
            assert r.status_code == 200 and "SPA" in r.text, path
            assert r.headers["content-type"].startswith("text/html")
        asset = client.get("/app/assets/index-abc123.js")
        assert asset.status_code == 200 and "javascript" in asset.headers["content-type"]
        assert client.get("/app/assets/missing.js").status_code == 404
        assert client.get("/app/favicon.svg").text == "<svg/>"
        assert "outside" not in client.get("/app/..%2Fsecret.txt").text
        # Legacy surfaces are untouched
        assert client.get("/").status_code == 200 and "SPA" not in client.get("/").text
        assert client.get("/static/style.css").status_code == 200


def test_missing_build_returns_503_and_api_still_works(make_app, tmp_path):
    app, _ = make_app(spa_dir=str(tmp_path / "not-built"))
    with TestClient(app) as client:
        r = client.get("/app/")
        assert r.status_code == 503 and "frontend not built" in r.text.lower()
        assert client.get("/app/settings").status_code == 503
        assert client.get("/app/assets/x.js").status_code == 503
        assert client.get("/healthz").status_code == 200
        assert client.get("/").status_code == 200
