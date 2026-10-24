import asyncio
import io
import json
import logging
import queue
import time
from contextlib import asynccontextmanager
from threading import Thread
from typing import AsyncGenerator, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)

import pypdf
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.schemas import IngestResult, TuningParams, ValidateKeyRequest, ValidateKeyResponse
from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingAgent
from app.services.extraction import GraphExtractionAgent
from app.services.generation import GenerationAgent
from app.services.graph_store import GraphStore
from app.services.ingestion import IngestionAgent
from app.services.model_config import ModelConfigAgent
from app.services.retrieval import RetrievalAgent
from app.services.vector_store import VectorStore

_chunking = ChunkingService()
_embedding = EmbeddingAgent()
_generation = GenerationAgent()
_vector_store = VectorStore()
_graph_store = GraphStore()
_extraction = GraphExtractionAgent()
_ingestion = IngestionAgent(_chunking, _embedding, _vector_store, _graph_store, _extraction)
_retrieval = RetrievalAgent(_embedding, _vector_store, _graph_store, _extraction)
_model_config = ModelConfigAgent()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _graph_store.close()


app = FastAPI(title="Retrieval Arena", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("app/static/index.html")


@app.post("/ingest", response_model=IngestResult)
async def ingest(
    collection: str = Form(...),
    api_key: str = Form(...),
    embedding_model: str = Form(settings.default_embed_model),
    gen_model: str = Form(settings.default_gen_model),
    tuning: str = Form("{}"),
    text: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
):
    has_files = bool(files and any(f.filename for f in files))
    if not text and not has_files:
        raise HTTPException(status_code=400, detail="Provide either text or at least one file.")

    try:
        tuning_data = json.loads(tuning)
    except json.JSONDecodeError:
        tuning_data = {}
    tuning_params = TuningParams(**tuning_data)

    if has_files:
        total_chunks = 0
        total_triples = 0
        last_result: Optional[IngestResult] = None

        for doc_idx, upload in enumerate(files):
            if not upload.filename:
                continue
            content = await upload.read()
            filename = upload.filename.lower()
            if filename.endswith(".pdf"):
                reader = pypdf.PdfReader(io.BytesIO(content))
                doc_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                doc_text = content.decode("utf-8", errors="replace")

            if not doc_text.strip():
                continue

            prefix = f"{collection}_d{doc_idx:02d}"
            result = await asyncio.to_thread(
                _ingestion.ingest,
                doc_text,
                collection,
                tuning_params,
                api_key,
                embedding_model,
                gen_model,
                prefix,
            )
            total_chunks += result.num_chunks
            total_triples += result.num_triples
            last_result = result

        if last_result is None:
            raise HTTPException(status_code=400, detail="All uploaded files were empty.")

        return IngestResult(
            collection=collection,
            documents=sum(1 for f in files if f.filename),
            num_chunks=total_chunks,
            num_triples=total_triples,
            embedding_model=embedding_model,
        )

    raw_text = text or ""
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Extracted text is empty.")

    result = await asyncio.to_thread(
        _ingestion.ingest,
        raw_text,
        collection,
        tuning_params,
        api_key,
        embedding_model,
        gen_model,
    )
    return result


@app.get("/query")
async def query(
    question: str = Query(...),
    backend: str = Query("chroma"),
    collection: str = Query("default"),
    api_key: str = Query(...),
    gen_model: str = Query(settings.default_gen_model),
    embedding_model: str = Query(settings.default_embed_model),
    top_k: int = Query(5),
    similarity_threshold: float = Query(0.0),
    mmr_diversity: float = Query(0.5),
    graph_hops: int = Query(1),
    max_triples_per_chunk: int = Query(8),
    triple_limit: int = Query(25),
    temperature: float = Query(0.3),
    max_output_tokens: int = Query(1024),
    system_prompt: str = Query(
        "Answer based strictly on the retrieved context. "
        "If the context does not contain the answer, say so rather than guessing. "
        "Cite source chunks by index [1], [2], etc."
    ),
):
    tuning = TuningParams(
        top_k=top_k,
        similarity_threshold=similarity_threshold,
        mmr_diversity=mmr_diversity,
        graph_hops=graph_hops,
        max_triples_per_chunk=max_triples_per_chunk,
        triple_limit=triple_limit,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        system_prompt=system_prompt,
    )

    if backend == "compare":
        stream = _stream_compare(question, collection, api_key, gen_model, embedding_model, tuning)
    else:
        stream = _stream_query(question, backend, collection, api_key, gen_model, embedding_model, tuning)

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_compare(
    question: str,
    collection: str,
    api_key: str,
    gen_model: str,
    embedding_model: str,
    tuning: TuningParams,
) -> AsyncGenerator[str, None]:
    """Run both backends in parallel and prefix every event with 'side' (chroma|graph)."""
    try:
        yield _sse("compare_started", {})

        t0 = time.perf_counter()
        embedding = await asyncio.to_thread(
            _embedding.embed_query, question, api_key, embedding_model
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        yield _sse("embedding_done", {"duration_ms": elapsed_ms})

        # Run both retrievals concurrently
        chroma_task = asyncio.create_task(
            asyncio.to_thread(
                lambda: list(_retrieval.retrieve_chroma(question, collection, embedding, tuning))
            )
        )
        graph_task = asyncio.create_task(
            asyncio.to_thread(
                lambda: list(
                    _retrieval.retrieve_graph(question, collection, tuning, api_key, gen_model)
                )
            )
        )

        chroma_events, graph_events = await asyncio.gather(chroma_task, graph_task)

        chroma_chunks: list[dict] = []
        for ev in chroma_events:
            yield _sse("chroma_" + ev["event"], ev["data"])
            if ev["event"] == "context_assembled":
                chroma_chunks = ev["data"].get("chunks", [])

        graph_triples: list[dict] = []
        for ev in graph_events:
            yield _sse("graph_" + ev["event"], ev["data"])
            if ev["event"] == "context_assembled":
                graph_triples = ev["data"].get("triples", [])

        chroma_context = (
            "\n\n".join(f"[{i + 1}] {c['text']}" for i, c in enumerate(chroma_chunks))
            if chroma_chunks
            else "No relevant context found in the vector store."
        )
        graph_context = (
            "\n".join(
                f"{t['subject']} —[{t['relation']}]→ {t['object']}"
                for t in graph_triples
            )
            if graph_triples
            else "No relevant context found in the knowledge graph."
        )

        # Both generation threads push (side, payload) tuples into one shared queue.
        # This lets us drain a single blocking queue and forward tokens to SSE without polling.
        combined_q: queue.SimpleQueue = queue.SimpleQueue()
        DONE_CHROMA = object()
        DONE_GRAPH = object()

        def _gen_chroma():
            try:
                for token in _generation.stream_answer(
                    question, chroma_context, tuning.system_prompt,
                    api_key, gen_model, tuning.temperature, tuning.max_output_tokens,
                ):
                    combined_q.put(("chroma_token", token))
            except Exception as exc:
                combined_q.put(("chroma_error", str(exc)))
            finally:
                combined_q.put(("sentinel", DONE_CHROMA))

        def _gen_graph():
            try:
                for token in _generation.stream_answer(
                    question, graph_context, tuning.system_prompt,
                    api_key, gen_model, tuning.temperature, tuning.max_output_tokens,
                ):
                    combined_q.put(("graph_token", token))
            except Exception as exc:
                combined_q.put(("graph_error", str(exc)))
            finally:
                combined_q.put(("sentinel", DONE_GRAPH))

        Thread(target=_gen_chroma, daemon=True).start()
        Thread(target=_gen_graph, daemon=True).start()

        done_count = 0
        while done_count < 2:
            kind, payload = await asyncio.to_thread(combined_q.get)
            if kind == "sentinel":
                done_count += 1
            elif kind == "chroma_token":
                yield _sse("chroma_answer_token", {"token": payload})
            elif kind == "graph_token":
                yield _sse("graph_answer_token", {"token": payload})
            elif kind in ("chroma_error", "graph_error"):
                yield _sse(kind, {"message": payload})

        yield _sse("done", {})

    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


async def _stream_query(
    question: str,
    backend: str,
    collection: str,
    api_key: str,
    gen_model: str,
    embedding_model: str,
    tuning: TuningParams,
) -> AsyncGenerator[str, None]:
    try:
        yield _sse("embedding_started", {})

        t0 = time.perf_counter()
        embedding = await asyncio.to_thread(
            _embedding.embed_query, question, api_key, embedding_model
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        yield _sse("embedding_done", {"duration_ms": elapsed_ms})

        if backend == "graph":
            retrieval_events = await asyncio.to_thread(
                lambda: list(
                    _retrieval.retrieve_graph(question, collection, tuning, api_key, gen_model)
                )
            )
        else:
            retrieval_events = await asyncio.to_thread(
                lambda: list(
                    _retrieval.retrieve_chroma(question, collection, embedding, tuning)
                )
            )

        context_chunks: list[dict] = []
        context_triples: list[dict] = []
        for ev in retrieval_events:
            yield _sse(ev["event"], ev["data"])
            if ev["event"] == "context_assembled":
                context_chunks = ev["data"].get("chunks", [])
                context_triples = ev["data"].get("triples", [])

        if backend == "graph":
            if context_triples:
                context = "\n".join(
                    f"{t['subject']} —[{t['relation']}]→ {t['object']}"
                    for t in context_triples
                )
            else:
                context = "No relevant context found in the knowledge graph."
        else:
            if context_chunks:
                context = "\n\n".join(
                    f"[{i + 1}] {c['text']}" for i, c in enumerate(context_chunks)
                )
            else:
                context = "No relevant context found in the vector store."

        token_q: queue.SimpleQueue = queue.SimpleQueue()
        DONE = object()

        def _gen_thread():
            try:
                for token in _generation.stream_answer(
                    question,
                    context,
                    tuning.system_prompt,
                    api_key,
                    gen_model,
                    tuning.temperature,
                    tuning.max_output_tokens,
                ):
                    token_q.put(token)
            except Exception as exc:
                token_q.put(exc)
            finally:
                token_q.put(DONE)

        Thread(target=_gen_thread, daemon=True).start()

        while True:
            item = await asyncio.to_thread(token_q.get)
            if item is DONE:
                break
            if isinstance(item, Exception):
                yield _sse("error", {"message": str(item)})
                return
            yield _sse("answer_token", {"token": item})

        yield _sse("done", {})

    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


@app.post("/config/validate-key", response_model=ValidateKeyResponse)
async def validate_key(body: ValidateKeyRequest):
    return await asyncio.to_thread(_model_config.validate_and_list_models, body.api_key)


@app.get("/config/models", response_model=ValidateKeyResponse)
async def list_models(api_key: str = Query(...)):
    return await asyncio.to_thread(_model_config.validate_and_list_models, api_key)
