"""QA (06-security, "no response contains a stored secret value"): legacy routes in M1.

Stores provider keys and an MCP server with a secret header and env value, then calls every route that reads them
back (and the write routes that echo a record) and asserts no secret value appears in any body or header.
"""

from fastapi.testclient import TestClient

GEMINI_SECRET = "AIzaQAsecretGEMINI0000000000000000000000"
NVIDIA_SECRET = "nvapi-QAsecretNVIDIA0000000000000000000000000000000000000000000000"
HEADER_SECRET = "Bearer ra_QAsecretHEADERtoken000000000"
ENV_SECRET = "sk-QAsecretENVvalue0000000000000000"
SECRETS = (GEMINI_SECRET, NVIDIA_SECRET, HEADER_SECRET, ENV_SECRET)


def _assert_clean(r, where: str) -> None:
    blob = r.text + "\n" + "\n".join(f"{k}: {v}" for k, v in r.headers.items())
    for secret in SECRETS:
        assert secret not in blob, f"{where} leaked a stored secret"
        # A secret's distinctive middle must not leak either (e.g. via a longer-than-intended hint)
        assert secret[6:-6] not in blob, f"{where} leaked part of a stored secret"


def test_no_stored_secret_in_any_response(make_app):
    app, _ = make_app()
    with TestClient(app) as c:
        responses = []
        r = c.post("/keys", json={"label": "qa-gemini", "provider": "gemini", "api_key": GEMINI_SECRET})
        assert r.status_code == 200, r.text
        responses.append(("POST /keys gemini", r))
        gemini_id = r.json()["id"]
        r = c.post("/keys", json={"label": "qa-nvidia", "provider": "nvidia", "api_key": NVIDIA_SECRET})
        assert r.status_code == 200, r.text
        responses.append(("POST /keys nvidia", r))
        nvidia_id = r.json()["id"]

        # Duplicate label: the 409 error must not echo the submitted key either
        responses.append(
            (
                "POST /keys duplicate",
                c.post("/keys", json={"label": "qa-nvidia", "provider": "nvidia", "api_key": NVIDIA_SECRET}),
            )
        )

        r = c.post(
            "/mcp-servers",
            json={
                "name": "qa-secret-server",
                "transport": "http",
                "url": "http://127.0.0.1:9/mcp/",
                "headers": {"Authorization": HEADER_SECRET},
                "env": {"TOKEN": ENV_SECRET},
            },
        )
        assert r.status_code == 200, r.text
        responses.append(("POST /mcp-servers", r))
        server_id = r.json()["id"]

        responses += [
            ("GET /keys", c.get("/keys")),
            (f"POST /keys/{gemini_id}/activate", c.post(f"/keys/{gemini_id}/activate", params={"provider": "gemini"})),
            (
                "POST /config/validate-key gemini",
                c.post("/config/validate-key", json={"key_id": gemini_id, "provider": "gemini"}),
            ),
            (
                "POST /config/validate-key nvidia",
                c.post("/config/validate-key", json={"key_id": nvidia_id, "provider": "nvidia"}),
            ),
            ("GET /mcp-servers", c.get("/mcp-servers")),
            (
                f"POST /mcp-servers/{server_id}/enabled",
                c.post(f"/mcp-servers/{server_id}/enabled", params={"enabled": True}),
            ),
            (f"GET /mcp-servers/{server_id}/tools", c.get(f"/mcp-servers/{server_id}/tools")),
            ("GET /mcp-tools", c.get("/mcp-tools")),
            ("GET /bots", c.get("/bots")),
            ("GET /collections", c.get("/collections")),
            ("GET /history", c.get("/history")),
            ("GET /readyz", c.get("/readyz")),
            ("GET /openapi.json", c.get("/openapi.json")),
            ("DELETE /keys", c.delete(f"/keys/{nvidia_id}")),
        ]
        for where, r in responses:
            _assert_clean(r, where)

        # The hint is exactly the last four characters, never more
        keys = c.get("/keys").json()
        assert [k["key_hint"] for k in keys] == [GEMINI_SECRET[-4:]]
        assert all("api_key" not in k for k in keys)
