import asyncio
import json

import pytest
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

from tests.parity.harness import json_summary, parse_sse, shape, sse_summary


@pytest.fixture(scope="module")
def self_server(arena, gemini_key, nvidia_key, lab_collection) -> dict:
    """The app's own /mcp/ endpoint, registered as an external MCP server."""
    r = arena.client.post(
        "/mcp-servers", json={"name": "self", "url": f"{arena.base_url}/mcp/", "headers": {"X-Trace": "secret-value"}}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_mcp_server_registry(arena, snapshot, self_server):
    c = arena.client
    snapshot("create", {"status": 200, "body": shape(self_server)})
    assert self_server["headers"] == {"X-Trace": "••••"}

    snapshot("create_duplicate", json_summary(c.post("/mcp-servers", json={"name": "self", "url": "http://x/"})))
    snapshot("create_bad_url", json_summary(c.post("/mcp-servers", json={"name": "bad", "url": "ftp://x"})))
    snapshot(
        "create_stdio_disabled",
        json_summary(c.post("/mcp-servers", json={"name": "local", "transport": "stdio", "command": "echo"})),
    )

    listed = c.get("/mcp-servers")
    snapshot("list", json_summary(listed))
    assert listed.json()["allow_stdio"] is False
    assert all(set(s["headers"].values()) <= {"••••"} for s in listed.json()["servers"])

    tools = c.get(f"/mcp-servers/{self_server['id']}/tools", params={"refresh": "true"})
    snapshot("tools", json_summary(tools))
    assert sorted(t["name"] for t in tools.json()["tools"]) == [
        "ask_bot",
        "graph_query",
        "list_collections",
        "search_collection",
    ]
    snapshot("tools_missing", json_summary(c.get("/mcp-servers/999999/tools")))


def test_mcp_tools_and_toggle(arena, snapshot, self_server):
    c = arena.client
    dead = c.post("/mcp-servers", json={"name": "dead", "url": "http://127.0.0.1:9/mcp/"}).json()
    all_tools = c.get("/mcp-tools")
    snapshot("all_tools_with_unreachable", json_summary(all_tools))
    assert [e["server"] for e in all_tools.json()["errors"]] == ["dead"]
    snapshot("unreachable_tools", json_summary(c.get(f"/mcp-servers/{dead['id']}/tools")))

    snapshot("disable", json_summary(c.post(f"/mcp-servers/{dead['id']}/enabled", params={"enabled": "false"})))
    assert c.get("/mcp-tools").json()["errors"] == []
    snapshot("enable_missing", json_summary(c.post("/mcp-servers/999999/enabled")))

    snapshot("delete", json_summary(c.delete(f"/mcp-servers/{dead['id']}")))
    snapshot("delete_missing", json_summary(c.delete(f"/mcp-servers/{dead['id']}")))


def test_tool_support(arena, snapshot, nvidia_key):
    c = arena.client
    snapshot("gemini", json_summary(c.post("/config/tool-support", json={"provider": "gemini", "model": "m"})))
    nvidia = c.post("/config/tool-support", json={"provider": "nvidia", "model": "fake-tools", "key_id": nvidia_key})
    snapshot("nvidia", json_summary(nvidia))
    assert nvidia.json()["supported"] is True
    snapshot(
        "nvidia_no_key",
        json_summary(c.post("/config/tool-support", json={"provider": "nvidia", "model": "uncached-model"})),
    )


def test_chat_with_mcp_tool_call(arena, snapshot, self_server, nvidia_key):
    c = arena.client
    bot = {
        "name": "tool-bot",
        "collection": "lab",
        "backend": "chroma",
        "provider": "nvidia",
        "gen_model": "fake-gen",
        "embedding_model": "fake-embed",
        "key_id": nvidia_key,
        "tools": [f"{self_server['id']}:list_collections"],
    }
    created = c.post("/bots", json=bot)
    assert created.status_code == 200, created.text
    r = c.post("/chat", json={"bot_id": created.json()["id"], "message": "Which collections exist?"})
    snapshot("chat_tool_call", sse_summary(r))
    events = parse_sse(r.text)
    names = [n for n, _ in events]
    assert names.count("tool_call") == 1 and names.count("tool_result") == 1, names
    result = next(d for n, d in events if n == "tool_result")
    assert "error" not in result and "lab" in result["result"]
    token = next(d for n, d in events if n == "token")["token"]
    assert "<think>" not in token

    conv_id = events[0][1]["conversation_id"]
    meta = c.get(f"/conversations/{conv_id}").json()["messages"][-1]["meta"]
    assert len(meta["tool_calls"]) == 1


async def _builtin_session(base_url: str, calls: list[tuple[str, dict]]):
    async with streamable_http_client(f"{base_url}/mcp/") as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            tools = await session.list_tools()
            results = {}
            for name, args in calls:
                res = await session.call_tool(name, args)
                text = "".join(getattr(item, "text", "") for item in res.content)
                try:
                    payload = json.loads(text)
                except ValueError:
                    payload = text
                results[name] = {"is_error": bool(res.is_error), "body": payload}
            return init, tools, results


def test_builtin_mcp_server(arena, snapshot, gemini_key, lab_collection):
    c = arena.client
    c.post(f"/keys/{gemini_key}/activate", params={"provider": "gemini"})
    bot = c.post(
        "/bots",
        json={
            "name": "mcp-ask-bot",
            "collection": "lab",
            "gen_model": "fake-gen",
            "embedding_model": "fake-embed",
            "key_id": gemini_key,
        },
    ).json()
    calls = [
        ("list_collections", {}),
        ("search_collection", {"collection": "lab", "query": "Apollo landing", "top_k": 2}),
        ("graph_query", {"collection": "lab", "question": "What did Apollo 11 do?", "gen_model": "fake-gen"}),
        ("ask_bot", {"bot": bot["name"], "question": "When did Apollo 11 land?"}),
    ]
    init, tools, results = asyncio.run(_builtin_session(arena.base_url, calls))
    assert init.server_info.name == "retrieval-arena"
    names = sorted(t.name for t in tools.tools)
    assert names == ["ask_bot", "graph_query", "list_collections", "search_collection"]
    snapshot("tools", {t.name: sorted((t.input_schema or {}).get("properties", {})) for t in tools.tools})
    for name, res in results.items():
        assert not res["is_error"], (name, res)
        snapshot(f"call_{name}", {"is_error": res["is_error"], "body": shape(res["body"])})
    assert len(results["search_collection"]["body"]["passages"]) == 2
    assert results["ask_bot"]["body"]["answer"]

    missing = asyncio.run(
        _builtin_session(arena.base_url, [("search_collection", {"collection": "nope", "query": "x"})])
    )
    assert missing[2]["search_collection"]["is_error"]
