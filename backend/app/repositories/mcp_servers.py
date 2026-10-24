import json

from sqlalchemy import delete, select, update

from app.models import McpServer
from app.repositories.base import Repository

_COLUMNS = tuple(McpServer.__table__.columns)
_JSON_FIELDS = ("args", "env", "headers")


def _server(row) -> dict:
    d = dict(row._mapping)
    for f in _JSON_FIELDS:
        d[f] = json.loads(d[f])
    d["enabled"] = bool(d["enabled"])
    return d


class McpServerRepository(Repository):
    """External MCP servers that bots may call tools on."""

    def list_mcp_servers(self) -> list[dict]:
        with self._session() as s:
            return [_server(r) for r in s.execute(select(*_COLUMNS).order_by(McpServer.name))]

    def get_mcp_server(self, server_id: int) -> dict | None:
        with self._session() as s:
            row = s.execute(select(*_COLUMNS).where(McpServer.id == server_id)).first()
        return _server(row) if row else None

    def save_mcp_server(self, server: dict) -> dict:
        def insert(s):
            row = McpServer(
                name=server["name"],
                transport=server["transport"],
                url=server.get("url", ""),
                command=server.get("command", ""),
                args=json.dumps(server.get("args", [])),
                env=json.dumps(server.get("env", {})),
                headers=json.dumps(server.get("headers", {})),
                enabled=int(server.get("enabled", True)),
            )
            s.add(row)
            s.flush()
            return row.id

        return self.get_mcp_server(self._unique(insert))

    def set_mcp_enabled(self, server_id: int, enabled: bool) -> bool:
        with self._session() as s:
            stmt = update(McpServer).where(McpServer.id == server_id).values(enabled=int(enabled))
            return s.execute(stmt).rowcount > 0

    def delete_mcp_server(self, server_id: int) -> bool:
        with self._session() as s:
            return s.execute(delete(McpServer).where(McpServer.id == server_id)).rowcount > 0
