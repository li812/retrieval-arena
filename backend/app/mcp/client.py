"""MCP client side: connect to external MCP servers and let bots call their tools.

Connections are opened per operation (list or call) rather than held open: simple, robust to server
restarts, and cheap at chat-turn volumes. Tool schemas are cached per server.
"""

import asyncio
import json
import logging
import re
import threading
import time
from contextlib import asynccontextmanager

from google import genai
from google.genai import types as gtypes
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from openai import OpenAI

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
_TOOL_CACHE_TTL_S = 300
_CALL_TIMEOUT_S = 60
_MAX_TOOL_ROUNDS = 5
_MAX_RESULT_CHARS = 12000


def _run(coro):
    """Run a coroutine from sync code; callers are worker threads with no event loop of their own."""
    return asyncio.run(coro)


def _fn_name(tool: str, server: str | None = None) -> str:
    # Function names must be [a-zA-Z0-9_-]{1,64} for both OpenAI-style and Gemini tool calling
    raw = f"{server}__{tool}" if server else tool
    return re.sub(r"[^a-zA-Z0-9_-]", "_", raw)[:64]


class MCPClientManager:
    def __init__(self, mcp_servers, allow_stdio: bool):
        self._store = mcp_servers
        self.allow_stdio = allow_stdio
        self._cache: dict[int, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _session(self, server: dict):
        if server["transport"] == "stdio":
            if not self.allow_stdio:
                raise PermissionError("stdio MCP servers are disabled (set ALLOW_STDIO_MCP=true to enable)")
            params = StdioServerParameters(
                command=server["command"], args=server.get("args") or [], env=server.get("env") or None
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=_CALL_TIMEOUT_S) as session:
                    await session.initialize()
                    yield session
        else:
            http = create_mcp_http_client(headers=server.get("headers") or None)
            async with http:
                async with streamable_http_client(server["url"], http_client=http) as (read, write):
                    async with ClientSession(read, write, read_timeout_seconds=_CALL_TIMEOUT_S) as session:
                        await session.initialize()
                        yield session

    async def _list_tools_async(self, server: dict) -> list[dict]:
        async with self._session(server) as session:
            result = await session.list_tools()
        return [
            {
                "ref": f"{server['id']}:{t.name}",
                "server_id": server["id"],
                "server": server["name"],
                "name": t.name,
                "description": (t.description or "")[:1024],
                "input_schema": t.input_schema or {"type": "object", "properties": {}},
            }
            for t in result.tools
        ]

    def list_tools(self, server: dict, refresh: bool = False) -> list[dict]:
        with self._lock:
            cached = self._cache.get(server["id"])
        if cached and not refresh and time.monotonic() - cached[0] < _TOOL_CACHE_TTL_S:
            return cached[1]
        tools = _run(asyncio.wait_for(self._list_tools_async(server), _CALL_TIMEOUT_S))
        with self._lock:
            self._cache[server["id"]] = (time.monotonic(), tools)
        return tools

    def invalidate(self, server_id: int) -> None:
        with self._lock:
            self._cache.pop(server_id, None)

    def call_tool(self, server: dict, name: str, arguments: dict) -> tuple[str, bool]:
        """Returns (text result, is_error)."""

        async def go():
            async with self._session(server) as session:
                return await session.call_tool(name, arguments or {})

        result = _run(asyncio.wait_for(go(), _CALL_TIMEOUT_S))
        parts = []
        for item in getattr(result, "content", None) or []:
            text = getattr(item, "text", None)
            parts.append(text if text is not None else f"[{getattr(item, 'type', 'content')}]")
        if not parts and getattr(result, "structured_content", None) is not None:
            parts.append(json.dumps(result.structured_content))
        text = "\n".join(parts)
        if len(text) > _MAX_RESULT_CHARS:
            text = text[:_MAX_RESULT_CHARS] + f"\n… [truncated {len(text) - _MAX_RESULT_CHARS} chars]"
        return text, bool(getattr(result, "is_error", False))

    # ------------------------------------------------------------------
    # Tools for a bot
    # ------------------------------------------------------------------

    def tools_for_bot(self, bot: dict) -> list[dict]:
        """Resolve the bot's '<server_id>:<tool>' refs into tool specs; unreachable servers are skipped."""
        wanted: dict[int, set[str]] = {}
        for ref in bot.get("tools") or []:
            sid, _, name = ref.partition(":")
            if sid.isdigit() and name:
                wanted.setdefault(int(sid), set()).add(name)
        specs = []
        for sid, names in wanted.items():
            server = self._store.get_mcp_server(sid)
            if not server or not server["enabled"]:
                continue
            try:
                tools = self.list_tools(server)
            except Exception as exc:
                logger.warning("[mcp] cannot list tools for %s: %s", server["name"], exc)
                continue
            specs += [{**t, "server_obj": server} for t in tools if t["name"] in names]
        # Models see plain tool names; prefix with the server only where two servers clash
        counts: dict[str, int] = {}
        for spec in specs:
            counts[spec["name"]] = counts.get(spec["name"], 0) + 1
        for spec in specs:
            spec["fn"] = _fn_name(spec["name"], spec["server"] if counts[spec["name"]] > 1 else None)
        return specs


class ToolRunner:
    """Tool-calling generation loop for ChatAgent: model ⇄ MCP tools, at most _MAX_TOOL_ROUNDS rounds."""

    def __init__(self, manager: MCPClientManager, generation, openai_factory=OpenAI):
        self._mgr = manager
        self._generation = generation
        self._openai = openai_factory

    def run(self, bot, history, user_content, llm, tuning):
        specs = self._mgr.tools_for_bot(bot)
        if not specs:
            # Tools configured but none reachable: answer without them
            if bot.get("tools"):
                yield "warning", {"stage": "tools", "message": "No configured MCP tools are reachable"}
            for token in self._generation.stream_chat(
                bot["system_prompt"],
                history,
                user_content,
                llm.api_key,
                llm.gen_model,
                tuning.temperature,
                tuning.max_output_tokens,
                llm.provider,
            ):
                yield "token", {"token": token}
            return
        by_fn = {s["fn"]: s for s in specs}
        system = bot["system_prompt"] + (
            "\n\nYou have tools: " + ", ".join(s["fn"] for s in specs) + ". When the retrieved context does "
            "not fully answer the user, CALL the relevant tools yourself before answering — never tell the "
            "user to call a tool. Cite retrieved context as [n]."
        )
        if llm.provider == "nvidia":
            yield from self._run_openai(system, history, user_content, llm, tuning, specs, by_fn)
        else:
            yield from self._run_gemini(system, history, user_content, llm, tuning, specs, by_fn)

    def _execute(self, spec: dict, args: dict, call_id: str):
        yield "tool_call", {"id": call_id, "name": spec["name"], "server": spec["server"], "arguments": args}
        try:
            text, is_error = self._mgr.call_tool(spec["server_obj"], spec["name"], args)
            payload = {"id": call_id, "name": spec["name"], "result": text}
            if is_error:
                payload["error"] = text
        except Exception as exc:
            text, payload = f"Tool error: {exc}", {"id": call_id, "name": spec["name"], "error": str(exc)}
        yield "tool_result", payload
        return text

    def _run_openai(self, system, history, user_content, llm, tuning, specs, by_fn):
        client = self._openai(api_key=llm.api_key, base_url=NVIDIA_BASE_URL, timeout=90, max_retries=0)
        tools = [
            {
                "type": "function",
                "function": {
                    "name": s["fn"],
                    "description": s["description"] or s["name"],
                    "parameters": s["input_schema"],
                },
            }
            for s in specs
        ]
        messages = [{"role": "system", "content": system}]
        messages += [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({"role": "user", "content": user_content})

        for round_no in range(_MAX_TOOL_ROUNDS + 1):
            kwargs = {"tools": tools, "tool_choice": "auto"} if round_no < _MAX_TOOL_ROUNDS else {}
            resp = client.chat.completions.create(
                model=llm.gen_model,
                messages=messages,
                temperature=tuning.temperature,
                max_tokens=tuning.max_output_tokens,
                **kwargs,
            )
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            if not calls:
                content = re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.DOTALL).strip()
                yield "token", {"token": content}
                return
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.function.name, "arguments": c.function.arguments},
                        }
                        for c in calls
                    ],
                }
            )
            for c in calls:
                spec = by_fn.get(c.function.name)
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                if spec is None:
                    text = f"Unknown tool {c.function.name}"
                else:
                    text = yield from self._execute(spec, args, c.id)
                messages.append({"role": "tool", "tool_call_id": c.id, "content": text})

    def _run_gemini(self, system, history, user_content, llm, tuning, specs, by_fn):
        client = genai.Client(api_key=llm.api_key)
        tool = gtypes.Tool(
            function_declarations=[
                gtypes.FunctionDeclaration(
                    name=s["fn"], description=s["description"] or s["name"], parameters_json_schema=s["input_schema"]
                )
                for s in specs
            ]
        )
        contents = [
            gtypes.Content(role="model" if m["role"] == "assistant" else "user", parts=[gtypes.Part(text=m["content"])])
            for m in history
        ]
        contents.append(gtypes.Content(role="user", parts=[gtypes.Part(text=user_content)]))

        for round_no in range(_MAX_TOOL_ROUNDS + 1):
            config = gtypes.GenerateContentConfig(
                system_instruction=system,
                temperature=tuning.temperature,
                max_output_tokens=tuning.max_output_tokens,
                tools=[tool] if round_no < _MAX_TOOL_ROUNDS else None,
                automatic_function_calling=gtypes.AutomaticFunctionCallingConfig(disable=True),
            )
            resp = client.models.generate_content(model=llm.gen_model, contents=contents, config=config)
            calls = resp.function_calls or []
            if not calls:
                yield "token", {"token": resp.text or ""}
                return
            contents.append(resp.candidates[0].content)
            responses = []
            for i, c in enumerate(calls):
                spec = by_fn.get(c.name)
                call_id = c.id or f"{c.name}-{round_no}-{i}"
                if spec is None:
                    text = f"Unknown tool {c.name}"
                else:
                    text = yield from self._execute(spec, dict(c.args or {}), call_id)
                responses.append(gtypes.Part.from_function_response(name=c.name, response={"result": text}))
            contents.append(gtypes.Content(role="user", parts=responses))
