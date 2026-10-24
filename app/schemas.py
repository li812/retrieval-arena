from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChunkingStrategy(str, Enum):
    fixed = "fixed"
    sentence_aware = "sentence_aware"


class Backend(str, Enum):
    chroma = "chroma"
    graph = "graph"
    compare = "compare"


class Provider(str, Enum):
    gemini = "gemini"
    nvidia = "nvidia"


class TuningParams(BaseModel):
    chunk_size: int = Field(800, ge=100, le=4000)
    chunk_overlap: int = Field(120, ge=0, le=1000)
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.fixed
    top_k: int = Field(5, ge=1, le=20)
    similarity_threshold: float = Field(0.0, ge=0.0, le=1.0)
    mmr_diversity: float = Field(0.5, ge=0.0, le=1.0)
    graph_hops: int = Field(1, ge=1, le=3)
    max_triples_per_chunk: int = Field(8, ge=1, le=30)
    triple_limit: int = Field(25, ge=1, le=100)
    # --- Retrieval Lab ---
    search_mode: Literal["dense", "hybrid", "keyword"] = "dense"
    hybrid_alpha: float = Field(0.5, ge=0.0, le=1.0)  # weight of dense vs keyword in RRF
    fetch_k: int = Field(20, ge=1, le=100)  # candidate pool before rerank / MMR / top-k
    query_transform: Literal["none", "multi_query", "hyde", "step_back"] = "none"
    multi_query_n: int = Field(3, ge=1, le=5)
    rerank: str = "none"  # "none" | "llm" | an NVIDIA reranker model id
    context_window: int = Field(0, ge=0, le=3)  # neighbouring chunks added on each side
    source_filter: Optional[str] = None
    context_order: Literal["score", "document", "sandwich"] = "score"
    max_context_tokens: int = Field(0, ge=0, le=32000)  # 0 = unlimited
    check_groundedness: bool = False
    entity_match: Literal["contains", "exact", "fuzzy"] = "contains"
    graph_direction: Literal["out", "both"] = "both"
    contextual_headers: bool = False
    temperature: float = Field(0.3, ge=0.0, le=2.0)
    max_output_tokens: int = Field(1024, ge=1, le=8192)
    system_prompt: str = Field(
        "Answer based strictly on the retrieved context. "
        "If the context does not contain the answer, say so rather than guessing. "
        "Cite source chunks by index [1], [2], etc."
    )


class IngestResult(BaseModel):
    collection: str
    documents: int
    num_chunks: int
    num_triples: int
    embedding_model: str


class ModelInfo(BaseModel):
    name: str
    display_name: str


class ValidateKeyRequest(BaseModel):
    api_key: Optional[str] = None
    key_id: Optional[int] = None
    provider: Provider = Provider.gemini


class ValidateKeyResponse(BaseModel):
    valid: bool
    error: Optional[str] = None
    gen_models: list[ModelInfo] = []
    embed_models: list[ModelInfo] = []
    embed_model_dims: dict[str, int] = {}
    rerank_models: list[ModelInfo] = []


class SaveKeyRequest(BaseModel):
    label: str
    provider: Provider
    api_key: str


class SavedKeyInfo(BaseModel):
    id: int
    label: str
    provider: str
    key_hint: str
    is_active: bool
    created_at: str
    last_used: Optional[str] = None


class EmotionRequest(BaseModel):
    text: str
    api_key: Optional[str] = None
    key_id: Optional[int] = None
    provider: Provider = Provider.gemini
    gen_model: str


class HistoryEntry(BaseModel):
    question: str
    backend: str
    collection: str
    payload: dict


class QueryRequest(BaseModel):
    """POST body for /query — keeps the key (or its id) out of URLs and access logs."""
    question: str
    backend: Backend = Backend.chroma
    collection: str = "default"
    api_key: Optional[str] = None
    key_id: Optional[int] = None
    gen_model: str
    embedding_model: str
    provider: Provider = Provider.gemini
    tuning: TuningParams = TuningParams()


class BotIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    emoji: str = Field("◆", max_length=8)
    description: str = Field("", max_length=300)
    system_prompt: str = Field(
        "You are a helpful assistant. Answer from the retrieved context. "
        "If the context does not contain the answer, say so. Cite sources as [1], [2]."
    )
    collection: str = "default"
    backend: Literal["chroma", "graph", "both"] = "chroma"
    provider: Provider = Provider.gemini
    gen_model: str
    embedding_model: str
    key_id: Optional[int] = None
    tuning: TuningParams = TuningParams()
    greeting: str = Field("", max_length=500)
    starters: list[str] = Field(default_factory=list, max_length=6)
    tools: list[str] = Field(default_factory=list)  # "<server_id>:<tool_name>" MCP tools this bot may call


class ChatRequest(BaseModel):
    bot_id: Optional[int] = None
    bot: Optional[BotIn] = None  # unsaved draft, for Bot Studio's live preview (not persisted)
    conversation_id: Optional[int] = None
    message: Optional[str] = None
    regenerate: bool = False
    history: list[dict] = Field(default_factory=list)  # preview mode only: prior turns held by the client
    api_key: Optional[str] = None
    key_id: Optional[int] = None


class FeedbackRequest(BaseModel):
    value: Literal[-1, 0, 1]


class MCPServerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    transport: Literal["http", "stdio"] = "http"
    url: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True
