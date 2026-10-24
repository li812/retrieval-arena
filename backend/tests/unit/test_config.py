from app.core.config import REPO_ROOT, Settings


def test_defaults(monkeypatch):
    for var in ("ARENA_SPA_DIR", "SPA_DIR", "LOG_FORMAT", "AUTO_MIGRATE"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.log_level == "INFO" and s.log_format == "json" and s.auto_migrate is True
    assert s.readyz_timeout_s == 2.0
    assert s.spa_dir == str(REPO_ROOT / "frontend" / "dist")


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("ARENA_SPA_DIR", "/app/frontend_dist")
    monkeypatch.setenv("ARENA_DB_PATH", "/app/arena_data/arena.db")
    monkeypatch.setenv("LOG_FORMAT", "console")
    monkeypatch.setenv("AUTO_MIGRATE", "false")
    monkeypatch.setenv("MCP_ALLOWED_HOSTS", "a:*, b:1 ,")
    s = Settings(_env_file=None)
    assert s.spa_dir == "/app/frontend_dist" and s.arena_db_path == "/app/arena_data/arena.db"
    assert s.log_format == "console" and s.auto_migrate is False
    assert s.mcp_allowed_host_list == ["a:*", "b:1"]
