import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_services
from app.api.schemas import MCPServerIn
from app.core.container import Services
from app.core.errors import DuplicateNameError

router = APIRouter()


def _public_server(server: dict) -> dict:
    """Header and env values often carry tokens; only their names leave the server."""
    return {
        **server,
        "headers": {k: "••••" for k in server["headers"]},
        "env": {k: "••••" for k in server["env"]},
    }


def _root_cause(exc: BaseException) -> str:
    """anyio wraps failures in ExceptionGroups; surface the innermost message."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return str(exc) or type(exc).__name__


@router.get("/mcp-servers")
async def list_mcp_servers(svc: Services = Depends(get_services)):
    servers = await asyncio.to_thread(svc.mcp_servers.list_mcp_servers)
    return {"servers": [_public_server(s) for s in servers], "allow_stdio": svc.settings.allow_stdio_mcp}


@router.post("/mcp-servers")
async def add_mcp_server(body: MCPServerIn, svc: Services = Depends(get_services)):
    if body.transport == "http" and not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="HTTP servers need an http(s):// URL")
    if body.transport == "stdio":
        if not svc.settings.allow_stdio_mcp:
            raise HTTPException(status_code=403, detail="stdio MCP servers are disabled; set ALLOW_STDIO_MCP=true")
        if not body.command.strip():
            raise HTTPException(status_code=422, detail="stdio servers need a command")
    try:
        server = await asyncio.to_thread(svc.mcp_servers.save_mcp_server, body.model_dump())
    except DuplicateNameError as exc:
        raise HTTPException(status_code=409, detail=f"An MCP server named '{body.name}' already exists") from exc
    return _public_server(server)


@router.post("/mcp-servers/{server_id}/enabled")
async def set_mcp_server_enabled(server_id: int, enabled: bool = True, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.mcp_servers.set_mcp_enabled, server_id, enabled):
        raise HTTPException(status_code=404, detail="MCP server not found")
    return {"id": server_id, "enabled": enabled}


@router.delete("/mcp-servers/{server_id}")
async def delete_mcp_server(server_id: int, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.mcp_servers.delete_mcp_server, server_id):
        raise HTTPException(status_code=404, detail="MCP server not found")
    svc.mcp_clients.invalidate(server_id)
    return {"deleted": server_id}


@router.get("/mcp-servers/{server_id}/tools")
async def list_mcp_server_tools(server_id: int, refresh: bool = False, svc: Services = Depends(get_services)):
    server = await asyncio.to_thread(svc.mcp_servers.get_mcp_server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        tools = await asyncio.to_thread(svc.mcp_clients.list_tools, server, refresh)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach '{server['name']}': {_root_cause(exc)}") from exc
    return {"server": server["name"], "tools": tools}


@router.get("/mcp-tools")
async def list_all_mcp_tools(svc: Services = Depends(get_services)):
    """Every tool on every enabled server, for the Bot Studio picker. Unreachable servers report an error."""
    servers = [s for s in await asyncio.to_thread(svc.mcp_servers.list_mcp_servers) if s["enabled"]]

    async def one(server):
        try:
            return await asyncio.to_thread(svc.mcp_clients.list_tools, server), None
        except Exception as exc:
            return [], {"server": server["name"], "error": _root_cause(exc)}

    results = await asyncio.gather(*(one(s) for s in servers))
    return {
        "tools": [t for tools, _ in results for t in tools],
        "errors": [err for _, err in results if err],
    }
