"""Runs the app with fake providers and in-memory stores behind a real uvicorn server on a random port.

A real server (not TestClient) is used because the MCP client code under test opens its own HTTP connections, and
the app's own `/mcp/` endpoint is registered as an MCP server in the tool-call tests.
"""

import json
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from tests.fakes.providers import FakeEmbedding, FakeExtraction, FakeGeneration, FakeModelConfig, FakeOpenAI
from tests.fakes.stores import InMemoryGraphStore, InMemoryVectorStore

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


@dataclass
class Fakes:
    embedding: FakeEmbedding = field(default_factory=FakeEmbedding)
    generation: FakeGeneration = field(default_factory=FakeGeneration)
    extraction: FakeExtraction = field(default_factory=FakeExtraction)
    model_config: FakeModelConfig = field(default_factory=FakeModelConfig)
    vector_store: InMemoryVectorStore = field(default_factory=InMemoryVectorStore)
    graph_store: InMemoryGraphStore = field(default_factory=InMemoryGraphStore)
    openai_factory: type = FakeOpenAI


def build_app(fakes: Fakes, db_path: Path):
    from app.core.config import Settings
    from app.core.container import Services
    from app.main import create_app

    settings = Settings(
        arena_db_path=str(db_path),
        spa_dir=str(db_path.parent / "no-spa"),
        log_format="console",
        _env_file=None,
    )
    services = Services.build(
        settings,
        embedding=fakes.embedding,
        generation=fakes.generation,
        extraction=fakes.extraction,
        model_config=fakes.model_config,
        vector_store=fakes.vector_store,
        graph_store=fakes.graph_store,
        openai_factory=fakes.openai_factory,
    )
    return create_app(settings=settings, services=services)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    def __init__(self, app):
        self.port = _free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning", lifespan="on")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.monotonic() + 30
        while not self.server.started:
            if time.monotonic() > deadline or not self.thread.is_alive():
                raise RuntimeError("parity server did not start")
            time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=10)


# ---------------------------------------------------------------------------
# Shapes and snapshots
# ---------------------------------------------------------------------------


def shape(value: Any) -> Any:
    """Structure without values: dict keys are kept, scalars become type names, list items are de-duplicated."""
    if isinstance(value, dict):
        return {k: shape(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        out: list = []
        for item in value:
            s = shape(item)
            if s not in out:
                out.append(s)
        return sorted(out, key=lambda s: json.dumps(s, sort_keys=True))
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "null"
    return type(value).__name__


def parse_sse(text: str) -> list[tuple[str, Any]]:
    events = []
    for block in text.split("\n\n"):
        name, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if name:
            events.append((name, data))
    return events


def _collapse(names: list[str]) -> list[str]:
    out: list[str] = []
    for n in names:
        if not out or out[-1].removesuffix("+") != n:
            out.append(n)
        elif not out[-1].endswith("+"):
            out[-1] = n + "+"
    return out


def sse_summary(response: httpx.Response) -> dict:
    """Status, content type, the event-type sequence (repeats collapsed to `name+`) and each event's data shape.

    Compare mode interleaves the two sides from two threads, so its sequence is split per side.
    """
    events = parse_sse(response.text)
    names = [n for n, _ in events]
    data_shapes: dict[str, list] = {}
    for n, d in events:
        s = shape(d)
        bucket = data_shapes.setdefault(n, [])
        if s not in bucket:
            bucket.append(s)
    if any(n == "compare_started" for n in names):
        sequence: Any = {
            "chroma": _collapse([n for n in names if n.startswith("chroma_")]),
            "graph": _collapse([n for n in names if n.startswith("graph_")]),
            "other": _collapse([n for n in names if not n.startswith(("chroma_", "graph_"))]),
        }
    else:
        sequence = _collapse(names)
    return {
        "status": response.status_code,
        "content_type": response.headers.get("content-type", "").split(";")[0],
        "events": sequence,
        "data": {k: sorted(v, key=lambda s: json.dumps(s, sort_keys=True)) for k, v in sorted(data_shapes.items())},
    }


def json_summary(response: httpx.Response) -> dict:
    try:
        body = shape(response.json())
    except ValueError:
        body = "<non-json>"
    return {"status": response.status_code, "body": body}


class Snapshots:
    """One JSON file per test module. Set UPDATE_SNAPSHOTS=1 to (re)record; otherwise a missing entry fails."""

    def __init__(self):
        self.update = os.environ.get("UPDATE_SNAPSHOTS") == "1"
        self._files: dict[str, dict] = {}
        self._dirty: set[str] = set()

    def _load(self, module: str) -> dict:
        if module not in self._files:
            path = SNAPSHOT_DIR / f"{module}.json"
            self._files[module] = json.loads(path.read_text()) if path.exists() else {}
        return self._files[module]

    def check(self, module: str, name: str, value: Any) -> None:
        data = self._load(module)
        value = json.loads(json.dumps(value))
        if self.update:
            if data.get(name) != value:
                data[name] = value
                self._dirty.add(module)
            return
        assert name in data, f"no snapshot '{name}' in {module}.json (run with UPDATE_SNAPSHOTS=1 to record)"
        assert value == data[name], f"snapshot '{name}' differs:\nexpected {data[name]}\nactual   {value}"

    def flush(self) -> None:
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        for module in self._dirty:
            path = SNAPSHOT_DIR / f"{module}.json"
            path.write_text(json.dumps(dict(sorted(self._files[module].items())), indent=1, sort_keys=True) + "\n")
