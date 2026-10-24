"""App factory. `app` is what uvicorn serves; tests call create_app(settings, services) with fakes."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import health
from app.api.errors import register_error_handlers
from app.api.legacy import analyze, bots, chat, collections, config, history, ingest, keys, mcp_servers, query
from app.api.middleware import RequestContextMiddleware
from app.api.spa import mount_spa
from app.core.config import Settings
from app.core.config import settings as default_settings
from app.core.container import Services
from app.core.db import run_migrations
from app.core.logging import configure_logging

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None, services: Services | None = None) -> FastAPI:
    settings = settings or default_settings
    services = services or Services.build(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(settings.log_level, settings.log_format)
        if settings.auto_migrate:
            run_migrations(services.db)
        logger.info("api started", extra={"db_path": str(services.db.path)})
        # The mounted MCP app's session manager needs a running task group for the app's lifetime
        async with services.mcp.session_manager.run():
            yield
        services.close()

    app = FastAPI(title="Retrieval Arena", lifespan=lifespan)
    app.state.services = services
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health.router)
    for module in (keys, ingest, query, collections, history, analyze, bots, chat, mcp_servers, config):
        app.include_router(module.router)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    mount_spa(app, settings.spa_dir)
    # Streamable HTTP endpoint for MCP clients: http://localhost:8000/mcp/ (note the trailing slash)
    app.mount("/mcp", services.mcp_app)
    return app


app = create_app()
