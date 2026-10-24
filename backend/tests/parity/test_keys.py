from tests.parity.harness import json_summary


def test_keys_lifecycle(arena, snapshot):
    c = arena.client
    created = c.post("/keys", json={"label": "keys-a", "provider": "gemini", "api_key": "AIza-fake-key-abcd"})
    snapshot("create", json_summary(created))
    body = created.json()
    assert body["key_hint"] == "abcd" and body["is_active"] is False
    assert "api_key" not in body

    snapshot(
        "create_duplicate",
        json_summary(c.post("/keys", json={"label": "keys-a", "provider": "gemini", "api_key": "other"})),
    )
    snapshot(
        "create_bad_provider",
        json_summary(c.post("/keys", json={"label": "keys-b", "provider": "acme", "api_key": "x"})),
    )

    listed = c.get("/keys")
    snapshot("list", json_summary(listed))
    assert any(k["id"] == body["id"] for k in listed.json())
    assert all("api_key" not in k for k in listed.json())

    snapshot("activate", json_summary(c.post(f"/keys/{body['id']}/activate", params={"provider": "gemini"})))
    snapshot("activate_missing_provider", json_summary(c.post(f"/keys/{body['id']}/activate")))
    assert next(k for k in c.get("/keys").json() if k["id"] == body["id"])["is_active"] is True

    snapshot("delete", json_summary(c.delete(f"/keys/{body['id']}")))
    snapshot("delete_missing", json_summary(c.delete(f"/keys/{body['id']}")))


def test_validate_key(arena, snapshot, gemini_key, nvidia_key):
    c = arena.client
    snapshot("by_id_gemini", json_summary(c.post("/config/validate-key", json={"key_id": gemini_key})))
    snapshot(
        "by_id_nvidia", json_summary(c.post("/config/validate-key", json={"key_id": nvidia_key, "provider": "nvidia"}))
    )
    invalid = c.post("/config/validate-key", json={"api_key": "bad-key"})
    snapshot("invalid", json_summary(invalid))
    assert invalid.json()["valid"] is False
    snapshot("no_key", json_summary(c.post("/config/validate-key", json={})))
    snapshot("unknown_key_id", json_summary(c.post("/config/validate-key", json={"key_id": 99999})))
