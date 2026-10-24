# syntax=docker/dockerfile:1

# --- web: build the React app (frontend/) -------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- api: FastAPI backend serving the API, the classic UI (/) and the built SPA (/app/) ----------
FROM python:3.11-slim AS api

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    ARENA_SPA_DIR=/app/frontend_dist \
    ARENA_DB_PATH=/app/arena_data/arena.db

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, so code changes don't reinstall them
COPY backend/pyproject.toml /tmp/pyproject.toml
RUN python - <<'PY'
import subprocess, sys, tomllib
deps = tomllib.load(open("/tmp/pyproject.toml", "rb"))["project"]["dependencies"]
subprocess.check_call([sys.executable, "-m", "pip", "install", *deps])
PY

# Vendored assets for the classic UI (Alpine, vis-network, fonts) into backend/app/static/vendor
COPY scripts/ scripts/
RUN bash scripts/fetch_vendor_assets.sh

COPY backend/ backend/
RUN pip install --no-deps ./backend

COPY --from=web /web/dist /app/frontend_dist

WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1:8000/healthz || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
