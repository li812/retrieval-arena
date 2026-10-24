"""Shared fixtures. Tests never reach real providers, Chroma or Neo4j: see tests/fakes/."""

import pytest

from tests.fakes.providers import FakeEmbedding, FakeExtraction, FakeGeneration, FakeModelConfig
from tests.fakes.stores import InMemoryGraphStore, InMemoryVectorStore


@pytest.fixture
def fake_embedding() -> FakeEmbedding:
    return FakeEmbedding()


@pytest.fixture
def fake_generation() -> FakeGeneration:
    return FakeGeneration()


@pytest.fixture
def fake_extraction() -> FakeExtraction:
    return FakeExtraction()


@pytest.fixture
def fake_model_config() -> FakeModelConfig:
    return FakeModelConfig()


@pytest.fixture
def vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


@pytest.fixture
def graph_store() -> InMemoryGraphStore:
    return InMemoryGraphStore()


@pytest.fixture
def make_app(tmp_path):
    """Build the real app around fakes and a temp database. Returns (app, fakes)."""
    from app.core.config import Settings
    from app.core.container import Services
    from app.main import create_app
    from tests.parity.harness import Fakes

    def build(**settings_overrides):
        fakes = Fakes()
        values = {
            "arena_db_path": str(tmp_path / "arena.db"),
            "spa_dir": str(tmp_path / "no-spa"),
            "log_format": "json",
            **settings_overrides,
        }
        settings = Settings(_env_file=None, **values)
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
        return create_app(settings=settings, services=services), fakes

    return build
