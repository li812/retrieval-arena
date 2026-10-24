import pytest

from app.core.errors import DuplicateNameError
from app.repositories.bots import BotRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.mcp_servers import McpServerRepository

BOT = {
    "name": "Helper",
    "emoji": "◆",
    "description": "",
    "system_prompt": "Be nice",
    "collection": "docs",
    "backend": "chroma",
    "provider": "gemini",
    "gen_model": "gen",
    "embedding_model": "emb",
    "key_id": None,
    "tuning": {"top_k": 3},
    "greeting": "",
    "starters": ["hi"],
    "tools": ["1:search"],
}


def test_bot_roundtrip_and_duplicates(db):
    repo = BotRepository(db.sessionmaker)
    bot = repo.save_bot(BOT)
    assert bot["tuning"] == {"top_k": 3} and bot["starters"] == ["hi"] and bot["tools"] == ["1:search"]
    assert list(bot)[:3] == ["id", "name", "emoji"] and bot["created_at"] and bot["updated_at"]
    with pytest.raises(DuplicateNameError):
        repo.save_bot(BOT)
    other = repo.save_bot({**BOT, "name": "Another"})
    with pytest.raises(DuplicateNameError):
        repo.save_bot({**BOT, "name": "Helper"}, other["id"])
    updated = repo.save_bot({**BOT, "backend": "graph", "tuning": {}}, bot["id"])
    assert updated["backend"] == "graph" and updated["tuning"] == {}
    assert [b["name"] for b in repo.list_bots()] == ["Another", "Helper"]
    assert repo.get_bot(999) is None
    assert repo.delete_bot(bot["id"]) and not repo.delete_bot(bot["id"])


def test_conversation_messages_and_cascade(db):
    bots = BotRepository(db.sessionmaker)
    repo = ConversationRepository(db.sessionmaker)
    bot = bots.save_bot(BOT)
    conv = repo.create_conversation(bot["id"], "x" * 100)
    assert repo.get_conversation(conv)["title"] == "x" * 80
    assert repo.get_conversation(repo.create_conversation(bot["id"], ""))["title"] == "New chat"

    repo.add_message(conv, "user", "hello")
    a1 = repo.add_message(conv, "assistant", "first", {"chunks": [1]})
    convs = {c["id"]: c for c in repo.list_conversations(bot["id"])}
    assert convs[conv]["message_count"] == 2 and len(convs) == 2
    msgs = repo.list_messages(conv)
    assert [m["role"] for m in msgs] == ["user", "assistant"] and msgs[1]["meta"] == {"chunks": [1]}
    assert list(msgs[0]) == ["id", "role", "content", "meta", "feedback", "created_at"]

    assert repo.set_feedback(a1, -1) and repo.list_messages(conv)[1]["feedback"] == -1
    assert not repo.set_feedback(999, 1)
    repo.delete_last_assistant(conv)
    assert [m["role"] for m in repo.list_messages(conv)] == ["user"]

    bots.delete_bot(bot["id"])  # ON DELETE CASCADE through conversations to messages
    assert repo.get_conversation(conv) is None and repo.list_messages(conv) == []
    assert not repo.delete_conversation(conv)


def test_mcp_servers(db):
    repo = McpServerRepository(db.sessionmaker)
    s = repo.save_mcp_server({"name": "tools", "transport": "http", "url": "http://x/", "headers": {"A": "b"}})
    assert s["headers"] == {"A": "b"} and s["args"] == [] and s["env"] == {} and s["enabled"] is True
    with pytest.raises(DuplicateNameError):
        repo.save_mcp_server({"name": "tools", "transport": "http"})
    assert repo.set_mcp_enabled(s["id"], False) and repo.get_mcp_server(s["id"])["enabled"] is False
    assert not repo.set_mcp_enabled(999, True)
    repo.save_mcp_server({"name": "alpha", "transport": "stdio", "command": "x", "args": ["-v"]})
    assert [x["name"] for x in repo.list_mcp_servers()] == ["alpha", "tools"]
    assert repo.delete_mcp_server(s["id"]) and repo.get_mcp_server(s["id"]) is None
