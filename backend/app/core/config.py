from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    chroma_host: str = "localhost"
    chroma_port: int = 8000
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "playground123"
    default_gen_model: str = "gemini-2.5-flash"
    default_embed_model: str = "gemini-embedding-001"
    arena_db_path: str = "arena.db"
    # stdio MCP servers run arbitrary commands inside the api container — opt in explicitly
    allow_stdio_mcp: bool = False
    # Host headers accepted by the built-in MCP server (DNS-rebinding protection)
    mcp_allowed_hosts: str = "localhost:*,127.0.0.1:*,[::1]:*"

    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"
    # Built React app (frontend/dist); the Docker image sets ARENA_SPA_DIR
    spa_dir: str = Field(
        default=str(REPO_ROOT / "frontend" / "dist"), validation_alias=AliasChoices("arena_spa_dir", "spa_dir")
    )
    # Run `alembic upgrade head` on startup (backs up a pre-Alembic database first)
    auto_migrate: bool = True
    readyz_timeout_s: float = 2.0

    @property
    def mcp_allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.mcp_allowed_hosts.split(",") if h.strip()]


settings = Settings()
