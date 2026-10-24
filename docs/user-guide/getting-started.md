# Getting started

Retrieval Arena runs entirely in Docker. You don't need Python or Node on your computer.

## Start it

```bash
git clone https://github.com/li812/retrieval-arena.git
cd retrieval-arena
cp .env.example .env        # optional: change the Neo4j password, log format, ...
docker compose up --build
```

The first build takes a few minutes: it builds the React dashboard in a Node stage and the API image, and Neo4j
needs about 30 seconds to start. When `docker compose ps` shows `api` as **healthy**, open the app.

## Two interfaces, one app

| Address | What you get |
|---|---|
| http://localhost:8000/ | **Classic UI.** Everything that exists today: ingest, the Retrieval Lab (Chroma, Graph, Compare), chat, Bot Studio, history, MCP servers |
| http://localhost:8000/app/ | **New dashboard.** The shell the classic pages are moving into. For now it shows system status and counts, and links to the classic UI for the rest |

Both use the same data: keys, collections, bots, conversations and history you created before are still there.

### Home

The Home page shows whether the app is ready: one status per dependency (SQLite, Chroma, Neo4j), plus how many
collections and bots you have. Hover the **?** next to a status to see what it means. A red status names the
service that isn't answering; the rest of the app keeps working for anything that doesn't need it.

### Other pages

Bots, Collections, Lab and Settings are placeholders in this release. Each one tells you what will live there and
links to the classic UI, where the feature works today.

### Theme

Choose **Auto** (follows your operating system, and switches live when the OS does), **Light** or **Dark**. The
choice is remembered in your browser and shared with the classic UI, so both always look the same.

### Command palette

Press **Ctrl K** (Windows, Linux) or **⌘ K** (macOS) anywhere in the dashboard.

- Type to filter, **↑ ↓** to move, **Enter** to run, **Esc** to close.
- Commands: go to any page, cycle or pick the theme, open the classic UI.

### Errors

If a request to the server fails, a notification appears in the corner with the server's message. Nothing is lost:
retry once the service is back.

## Working on the frontend (hot reload)

```bash
docker compose --profile dev up --build
```

Open **http://localhost:5173/app/**. A `web` container runs the Vite dev server with your `frontend/` folder
mounted, so edits show up immediately. Its `node_modules` live in a Docker volume, not on your computer. API calls
go to the `api` container. `http://localhost:8000/app/` keeps serving the build baked into the image until you run
`docker compose up --build` again.

## Health checks

- `GET /healthz` answers `{"status": "ok"}` whenever the API process is running. Docker uses it for the
  container's health status.
- `GET /readyz` checks SQLite, Chroma and Neo4j and answers 200 when all are reachable, or 503 with the failing
  check named, for example `{"status": "unavailable", "checks": {"neo4j": {"ok": false, ...}}}`.

## Stopping and resetting

```bash
docker compose down        # stop; your data stays in Docker volumes
docker compose down -v     # stop and delete ALL data: keys, bots, history, Chroma and Neo4j
```
