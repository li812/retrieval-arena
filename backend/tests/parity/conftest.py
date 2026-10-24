from dataclasses import dataclass

import httpx
import pytest

from tests.parity.harness import Fakes, LiveServer, Snapshots, build_app


@dataclass
class Arena:
    base_url: str
    client: httpx.Client
    fakes: Fakes

    def save_key(self, label: str, provider: str = "gemini") -> int:
        r = self.client.post("/keys", json={"label": label, "provider": provider, "api_key": f"fake-{label}-0000"})
        assert r.status_code == 200, r.text
        return r.json()["id"]


@pytest.fixture(scope="session")
def arena(tmp_path_factory):
    fakes = Fakes()
    db_path = tmp_path_factory.mktemp("parity") / "arena.db"
    app = build_app(fakes, db_path)
    with LiveServer(app) as server, httpx.Client(base_url=server.base_url, timeout=60) as client:
        yield Arena(server.base_url, client, fakes)


@pytest.fixture(scope="session")
def _snapshots():
    snaps = Snapshots()
    yield snaps
    snaps.flush()


@pytest.fixture
def snapshot(_snapshots, request):
    module = request.module.__name__.rsplit(".", 1)[-1].removeprefix("test_")

    test = request.node.originalname.removeprefix("test_")

    def check(name: str, value):
        _snapshots.check(module, f"{test}.{name}", value)

    return check


@pytest.fixture(scope="session")
def gemini_key(arena) -> int:
    return arena.save_key("parity-gemini")


@pytest.fixture(scope="session")
def nvidia_key(arena) -> int:
    return arena.save_key("parity-nvidia", provider="nvidia")


LAB_TEXT = (
    "Apollo 11 was the American spaceflight that first landed humans on the Moon. "
    "Commander Neil Armstrong and pilot Buzz Aldrin landed the lunar module Eagle on July 20, 1969.\n\n"
    "Armstrong became the first person to step onto the lunar surface six hours later. "
    "Aldrin joined him nineteen minutes after that.\n\n"
    "Michael Collins flew the command module Columbia alone in lunar orbit. "
    "The astronauts returned to Earth and splashed down in the Pacific Ocean on July 24.\n\n"
    "The Saturn V rocket launched the mission from Kennedy Space Center in Florida. "
    "Mission control in Houston monitored the flight around the clock."
)


@pytest.fixture(scope="session")
def lab_collection(arena, gemini_key) -> str:
    """A collection with chunks in Chroma and triples in the graph, used by the query and chat tests."""
    tuning = '{"chunk_size": 200, "chunk_overlap": 20, "chunking_strategy": "sentence_aware"}'
    r = arena.client.post(
        "/ingest",
        data={
            "collection": "lab",
            "key_id": str(gemini_key),
            "embedding_model": "fake-embed",
            "gen_model": "fake-gen",
            "tuning": tuning,
            "text": LAB_TEXT,
        },
    )
    assert r.status_code == 200, r.text
    return "lab"
