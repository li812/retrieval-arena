import pytest

from tests.parity.harness import json_summary, parse_sse, sse_summary


def _bot(key_id: int, name: str, **extra) -> dict:
    bot = {
        "name": name,
        "emoji": "🚀",
        "description": "Parity bot",
        "collection": "lab",
        "backend": "chroma",
        "provider": "gemini",
        "gen_model": "fake-gen",
        "embedding_model": "fake-embed",
        "key_id": key_id,
        "greeting": "Hi!",
        "starters": ["When did Apollo 11 land?"],
        "tuning": {"top_k": 3},
    }
    bot.update(extra)
    return bot


def test_bot_crud(arena, snapshot, gemini_key):
    c = arena.client
    created = c.post("/bots", json=_bot(gemini_key, "crud-bot"))
    snapshot("create", json_summary(created))
    bot = created.json()
    assert bot["tuning"]["top_k"] == 3 and bot["starters"] == ["When did Apollo 11 land?"] and bot["tools"] == []

    snapshot("create_duplicate", json_summary(c.post("/bots", json=_bot(gemini_key, "crud-bot"))))
    snapshot("create_invalid", json_summary(c.post("/bots", json={"name": ""})))

    listed = c.get("/bots")
    snapshot("list", json_summary(listed))
    names = [b["name"] for b in listed.json()]
    assert names == sorted(names)

    updated = c.put(f"/bots/{bot['id']}", json=_bot(gemini_key, "crud-bot-renamed", backend="graph"))
    snapshot("update", json_summary(updated))
    assert updated.json()["backend"] == "graph"
    other = c.post("/bots", json=_bot(gemini_key, "crud-bot-other")).json()
    snapshot("update_duplicate", json_summary(c.put(f"/bots/{other['id']}", json=_bot(gemini_key, "crud-bot-renamed"))))
    snapshot("update_missing", json_summary(c.put("/bots/999999", json=_bot(gemini_key, "nobody"))))

    snapshot("delete", json_summary(c.delete(f"/bots/{bot['id']}")))
    snapshot("delete_missing", json_summary(c.delete(f"/bots/{bot['id']}")))
    c.delete(f"/bots/{other['id']}")


@pytest.fixture(scope="module")
def chat_bot(arena, gemini_key, lab_collection) -> dict:
    r = arena.client.post("/bots", json=_bot(gemini_key, "chat-bot", tuning={"top_k": 3, "check_groundedness": True}))
    assert r.status_code == 200, r.text
    return r.json()


def test_chat_new_followup_regenerate(arena, snapshot, chat_bot):
    c = arena.client
    first = c.post("/chat", json={"bot_id": chat_bot["id"], "message": "When did Apollo 11 land?"})
    snapshot("new_conversation", sse_summary(first))
    events = parse_sse(first.text)
    conv_id = events[0][1]["conversation_id"]
    assert events[0][0] == "conversation" and conv_id is not None
    assert events[-1][0] == "done" and events[-1][1]["message_id"] is not None

    follow = c.post("/chat", json={"bot_id": chat_bot["id"], "conversation_id": conv_id, "message": "Who flew it?"})
    snapshot("follow_up", sse_summary(follow))
    assert any(n == "rewritten" for n, _ in parse_sse(follow.text))

    regen = c.post("/chat", json={"bot_id": chat_bot["id"], "conversation_id": conv_id, "regenerate": True})
    snapshot("regenerate", sse_summary(regen))

    convs = c.get(f"/bots/{chat_bot['id']}/conversations")
    snapshot("list_conversations", json_summary(convs))
    assert convs.json()[0]["id"] == conv_id and convs.json()[0]["message_count"] == 4

    conv = c.get(f"/conversations/{conv_id}")
    snapshot("get_conversation", json_summary(conv))
    messages = conv.json()["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]

    fb = c.post(f"/messages/{messages[1]['id']}/feedback", json={"value": 1})
    snapshot("feedback", json_summary(fb))
    assert c.get(f"/conversations/{conv_id}").json()["messages"][1]["feedback"] == 1
    snapshot("feedback_invalid", json_summary(c.post(f"/messages/{messages[1]['id']}/feedback", json={"value": 5})))
    snapshot("feedback_missing", json_summary(c.post("/messages/999999/feedback", json={"value": -1})))

    snapshot("delete_conversation", json_summary(c.delete(f"/conversations/{conv_id}")))
    snapshot("get_conversation_missing", json_summary(c.get(f"/conversations/{conv_id}")))
    snapshot("delete_conversation_missing", json_summary(c.delete(f"/conversations/{conv_id}")))


def test_chat_preview_mode(arena, snapshot, gemini_key, lab_collection):
    draft = _bot(gemini_key, "draft-bot", backend="both")
    history = [
        {"role": "user", "content": "Tell me about Apollo 11"},
        {"role": "assistant", "content": "Sure."},
        {"role": "system", "content": "dropped"},
    ]
    r = arena.client.post("/chat", json={"bot": draft, "message": "When did it land?", "history": history})
    snapshot("preview", sse_summary(r))
    events = parse_sse(r.text)
    assert events[0][1]["conversation_id"] is None and events[-1][1] == {"conversation_id": None, "message_id": None}


def test_chat_graph_backend(arena, snapshot, gemini_key, lab_collection):
    bot = arena.client.post("/bots", json=_bot(gemini_key, "graph-bot", backend="graph")).json()
    snapshot("graph_backend", sse_summary(arena.client.post("/chat", json={"bot_id": bot["id"], "message": "Apollo?"})))


def test_chat_both_backend(arena, snapshot, gemini_key, lab_collection):
    """QA (Q1): a bot with backend="both" retrieves from Chroma and the graph in one turn."""
    bot = arena.client.post("/bots", json=_bot(gemini_key, "both-bot", backend="both")).json()
    r = arena.client.post("/chat", json={"bot_id": bot["id"], "message": "When did Apollo 11 land?"})
    snapshot("both_backend", sse_summary(r))
    names = [n for n, _ in parse_sse(r.text)]
    assert names[-1] == "done" and "error" not in names, names


def test_chat_errors(arena, snapshot, chat_bot, gemini_key):
    c = arena.client
    snapshot("no_bot", json_summary(c.post("/chat", json={"message": "hi"})))
    snapshot("unknown_bot", json_summary(c.post("/chat", json={"bot_id": 999999, "message": "hi"})))
    snapshot("empty_message", json_summary(c.post("/chat", json={"bot_id": chat_bot["id"], "message": "  "})))
    snapshot(
        "regenerate_without_conversation",
        json_summary(c.post("/chat", json={"bot_id": chat_bot["id"], "regenerate": True})),
    )
    snapshot(
        "foreign_conversation",
        json_summary(c.post("/chat", json={"bot_id": chat_bot["id"], "conversation_id": 999999, "message": "hi"})),
    )
    mismatch = c.post("/bots", json=_bot(gemini_key, "mismatch-bot", embedding_model="fake-embed-small")).json()
    snapshot("embedding_mismatch", sse_summary(c.post("/chat", json={"bot_id": mismatch["id"], "message": "hi"})))


def test_delete_bot_cascades(arena, snapshot, gemini_key, lab_collection):
    c = arena.client
    bot = c.post("/bots", json=_bot(gemini_key, "cascade-bot")).json()
    events = parse_sse(c.post("/chat", json={"bot_id": bot["id"], "message": "Apollo?"}).text)
    conv_id = events[0][1]["conversation_id"]
    assert c.get(f"/conversations/{conv_id}").status_code == 200
    assert c.delete(f"/bots/{bot['id']}").status_code == 200
    snapshot("conversation_after_bot_delete", json_summary(c.get(f"/conversations/{conv_id}")))
    snapshot("conversations_of_deleted_bot", json_summary(c.get(f"/bots/{bot['id']}/conversations")))
