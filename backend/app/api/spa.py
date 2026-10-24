"""Serves the built React app at /app/. The Alpine UI keeps / and /static until its pages are replaced."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from starlette.staticfiles import StaticFiles

NOT_BUILT = (
    "Frontend not built: run `npm ci && npm run build` in frontend/ (or build the Docker image). "
    "The API and the classic UI at / keep working."
)


class _Assets(StaticFiles):
    """Hashed build assets; a missing build answers 503 instead of crashing the mount."""

    async def __call__(self, scope, receive, send):
        if not Path(self.directory).is_dir():
            await PlainTextResponse(NOT_BUILT, status_code=503)(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def mount_spa(app: FastAPI, spa_dir: str | Path) -> None:
    root = Path(spa_dir).resolve()

    @app.get("/app", include_in_schema=False)
    async def spa_redirect():
        return RedirectResponse("/app/", status_code=307)

    app.mount("/app/assets", _Assets(directory=root / "assets", check_dir=False), name="spa-assets")

    @app.get("/app/{path:path}", include_in_schema=False)
    async def spa(path: str):
        index = root / "index.html"
        if not index.is_file():
            return PlainTextResponse(NOT_BUILT, status_code=503)
        candidate = (root / path).resolve()
        # Top-level build files (favicon, manifest) are served as-is; every other path is a client-side route
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
