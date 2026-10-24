from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ChunkingStrategy(str, Enum):
    fixed = "fixed"
    sentence_aware = "sentence_aware"


class Backend(str, Enum):
    chroma = "chroma"
    graph = "graph"
    compare = "compare"


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
    api_key: str


class ValidateKeyResponse(BaseModel):
    valid: bool
    error: Optional[str] = None
    gen_models: list[ModelInfo] = []
    embed_models: list[ModelInfo] = []
