from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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

    class Config:
        env_file = ".env"


settings = Settings()
