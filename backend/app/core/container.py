"""Builds the app's services once per app instance. Tests pass fakes for the providers and stores."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings
from app.core.db import Database


@dataclass
class Services:
    settings: Settings
    db: Database
    # repositories
    provider_keys: Any
    collections: Any
    history: Any
    bots: Any
    conversations: Any
    mcp_servers: Any
    # providers and stores (fakes in tests)
    embedding: Any
    generation: Any
    extraction: Any
    model_config: Any
    vector_store: Any
    graph_store: Any
    openai_factory: Callable[..., Any]
    # pipeline
    chunking: Any
    sentiment: Any
    retrieval: Any
    evaluation: Any
    ingestion: Any
    chat: Any
    mcp_clients: Any
    tool_runner: Any
    mcp: Any
    mcp_app: Any
    tool_support_cache: dict = field(default_factory=dict)

    @classmethod
    def build(cls, settings: Settings, **overrides: Any) -> "Services":
        """Wire today's singletons. Any provider/store can be overridden by keyword (embedding=FakeEmbedding())."""
        import openai

        from app.api.deps import embedding_mismatch
        from app.mcp.client import MCPClientManager, ToolRunner
        from app.mcp.server import build_mcp_server
        from app.providers.embeddings import EmbeddingAgent
        from app.providers.generation import GenerationAgent
        from app.providers.model_config import ModelConfigAgent
        from app.rag.chunking import ChunkingService
        from app.rag.evaluation import EvaluationAgent
        from app.rag.extraction import GraphExtractionAgent
        from app.rag.graph_store import GraphStore
        from app.rag.ingestion import IngestionAgent
        from app.rag.retrieval import RetrievalAgent
        from app.rag.sentiment import SentimentAgent
        from app.rag.vector_store import VectorStore
        from app.repositories.bots import BotRepository
        from app.repositories.collections import CollectionRepository
        from app.repositories.conversations import ConversationRepository
        from app.repositories.history import HistoryRepository
        from app.repositories.mcp_servers import McpServerRepository
        from app.repositories.provider_keys import ProviderKeyRepository
        from app.runtime.chat import ChatAgent

        def pick(name: str, factory: Callable[[], Any]) -> Any:
            return overrides[name] if name in overrides else factory()

        db = overrides.get("db") or Database(settings.arena_db_path)
        sessions = db.sessionmaker
        provider_keys = ProviderKeyRepository(sessions)
        collections = CollectionRepository(sessions)
        history = HistoryRepository(sessions)
        bots = BotRepository(sessions)
        conversations = ConversationRepository(sessions)
        mcp_servers = McpServerRepository(sessions)

        embedding = pick("embedding", EmbeddingAgent)
        generation = pick("generation", GenerationAgent)
        extraction = pick("extraction", GraphExtractionAgent)
        model_config = pick("model_config", ModelConfigAgent)
        vector_store = pick("vector_store", lambda: VectorStore(settings.chroma_host, settings.chroma_port))
        graph_store = pick(
            "graph_store", lambda: GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
        )
        openai_factory = overrides.get("openai_factory", openai.OpenAI)

        def guard(collection: str, model: str, vector: list[float]) -> str | None:
            return embedding_mismatch(collections, collection, model, vector)

        chunking = ChunkingService()
        sentiment = SentimentAgent(extraction)
        retrieval = RetrievalAgent(embedding, vector_store, graph_store, extraction, sentiment)
        evaluation = EvaluationAgent(extraction)
        ingestion = IngestionAgent(chunking, embedding, vector_store, graph_store, extraction, collections)
        chat = ChatAgent(embedding, retrieval, generation, extraction, sentiment, evaluation, guard)
        mcp, mcp_app = build_mcp_server(
            provider_keys=provider_keys,
            collections=collections,
            bots=bots,
            vector_store=vector_store,
            embedding=embedding,
            retrieval=retrieval,
            chat=chat,
            embedding_mismatch=guard,
            allowed_hosts=settings.mcp_allowed_host_list,
        )
        mcp_clients = MCPClientManager(mcp_servers, allow_stdio=settings.allow_stdio_mcp)
        tool_runner = ToolRunner(mcp_clients, generation, openai_factory)

        return cls(
            settings=settings,
            db=db,
            provider_keys=provider_keys,
            collections=collections,
            history=history,
            bots=bots,
            conversations=conversations,
            mcp_servers=mcp_servers,
            embedding=embedding,
            generation=generation,
            extraction=extraction,
            model_config=model_config,
            vector_store=vector_store,
            graph_store=graph_store,
            openai_factory=openai_factory,
            chunking=chunking,
            sentiment=sentiment,
            retrieval=retrieval,
            evaluation=evaluation,
            ingestion=ingestion,
            chat=chat,
            mcp_clients=mcp_clients,
            tool_runner=tool_runner,
            mcp=mcp,
            mcp_app=mcp_app,
        )

    def close(self) -> None:
        try:
            self.graph_store.close()
        finally:
            self.db.dispose()
