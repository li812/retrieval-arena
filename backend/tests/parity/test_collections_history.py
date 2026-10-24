from tests.parity.harness import json_summary


def test_collections_list_and_delete(arena, snapshot, gemini_key, lab_collection):
    c = arena.client
    r = c.post(
        "/ingest",
        data={
            "collection": "to-delete",
            "key_id": str(gemini_key),
            "embedding_model": "fake-embed",
            "gen_model": "fake-gen",
            "text": "Temporary text about Mars rovers.",
        },
    )
    assert r.status_code == 200

    listed = c.get("/collections")
    snapshot("list", json_summary(listed))
    names = [col["name"] for col in listed.json()]
    assert names == sorted(names) and {"lab", "to-delete"} <= set(names)
    lab = next(col for col in listed.json() if col["name"] == "lab")
    assert lab["embed_model"] == "fake-embed" and lab["chunks"] > 0 and lab["triples"] > 0

    snapshot("delete", json_summary(c.delete("/collections/to-delete")))
    assert "to-delete" not in [col["name"] for col in c.get("/collections").json()]
    assert arena.fakes.graph_store.stats("to-delete")["triples"] == 0
    snapshot("delete_missing", json_summary(c.delete("/collections/to-delete")))


def test_history(arena, snapshot):
    c = arena.client
    payload = {"settings": {"top_k": 5}, "answers": {"chroma": "x"}, "timing": {"total_ms": 12}}
    created = c.post(
        "/history", json={"question": "history apollo", "backend": "chroma", "collection": "lab", "payload": payload}
    )
    snapshot("create", json_summary(created))
    hid = created.json()["id"]
    c.post("/history", json={"question": "history other", "backend": "graph", "collection": "lab", "payload": {}})
    snapshot("create_invalid", json_summary(c.post("/history", json={"question": "q"})))

    listed = c.get("/history")
    snapshot("list", json_summary(listed))
    entry = next(e for e in listed.json() if e["id"] == hid)
    assert entry["payload"] == payload and entry["pinned"] is False

    searched = c.get("/history", params={"q": "apollo"})
    snapshot("search", json_summary(searched))
    assert [e["question"] for e in searched.json()] == ["history apollo"]
    snapshot("limit_invalid", json_summary(c.get("/history", params={"limit": 0})))

    snapshot("pin", json_summary(c.post(f"/history/{hid}/pin")))
    assert c.get("/history").json()[0]["id"] == hid
    snapshot("unpin", json_summary(c.post(f"/history/{hid}/pin", params={"pinned": "false"})))
    snapshot("pin_missing", json_summary(c.post("/history/999999/pin")))

    snapshot("delete", json_summary(c.delete(f"/history/{hid}")))
    snapshot("delete_missing", json_summary(c.delete(f"/history/{hid}")))


def test_analyze_emotion(arena, snapshot, gemini_key):
    r = arena.client.post(
        "/analyze/emotion", json={"text": "What a wonderful launch!", "key_id": gemini_key, "gen_model": "fake-gen"}
    )
    snapshot("emotion", json_summary(r))
    assert r.json()["tone"] == "upbeat" and set(r.json()["emotions"]) >= {"joy", "anger"}
    snapshot(
        "emotion_no_key",
        json_summary(arena.client.post("/analyze/emotion", json={"text": "x", "gen_model": "fake-gen"})),
    )
