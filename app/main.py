import asyncio
import io
import json
import logging
import queue
import sqlite3
import time
from contextlib import asynccontextmanager
from threading import Thread
from typing import AsyncGenerator, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)

import openai
import pypdf
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from google.genai import errors as genai_errors
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.schemas import (
    BotIn, ChatRequest, EmotionRequest, FeedbackRequest, HistoryEntry, MCPServerIn, IngestResult, QueryRequest, SaveKeyRequest, SavedKeyInfo, TuningParams,
    ValidateKeyRequest, ValidateKeyResponse,
)
from app.services.bot_store import BotStore
from app.services.chat import ChatAgent
from app.services.chunking import ChunkingService
from app.services.embeddings import EmbeddingAgent
from app.services.evaluation import EvaluationAgent
from app.services.extraction import GraphExtractionAgent
from app.services.generation import GenerationAgent
from app.services.graph_store import GraphStore
from app.services.ingestion import IngestionAgent
from app.services.key_store import KeyStore
from app.services.mcp_client import MCPClientManager, ToolRunner
from app.services.mcp_server import build_mcp_server
from app.services.model_config import ModelConfigAgent
from app.services.retrieval import LLMContext, RetrievalAgent
from app.services.sentiment import SentimentAgent
from app.services.vector_store import VectorStore

_chunking = ChunkingService()
_embedding = EmbeddingAgent()
_generation = GenerationAgent()
_vector_store = VectorStore()
_graph_store = GraphStore()
_extraction = GraphExtractionAgent()
_key_store = KeyStore(settings.arena_db_path)
_ingestion = IngestionAgent(_chunking, _embedding, _vector_store, _graph_store, _extraction, _key_store)
_sentiment = SentimentAgent(_extraction)
_retrieval = RetrievalAgent(_embedding, _vector_store, _graph_store, _extraction, _sentiment)
_model_config = ModelConfigAgent()
_evaluation = EvaluationAgent(_extraction)
_bot_store = BotStore(settings.arena_db_path)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _embedding_mismatch(collection: str, embedding_model: str, embedding: list[float]) -> Optional[str]:
    """Guard: the query must be embedded by the same model (and so the same space) as the collection."""
    col_info = _key_store.get_collection_dim(collection)
    if not col_info:
        return None
    if col_info["embed_dim"] != len(embedding):
        return (
            f"Dimension mismatch: collection '{collection}' uses {col_info['embed_dim']}-dim "
            f"({col_info['embed_model']}), but {embedding_model} produces {len(embedding)}-dim."
        )
    if col_info["embed_model"] != embedding_model:
        return (
            f"Model mismatch: collection '{collection}' was embedded with {col_info['embed_model']}; "
            f"select that embedding model to query it."
        )
    return None


async def _drain(gen_factory, result: dict) -> AsyncGenerator[tuple[str, dict], None]:
    """Run a blocking (event, data) generator in a worker thread and relay its items as they arrive.

    The generator's return value is stored in result["value"].
    """
    q: queue.SimpleQueue = queue.SimpleQueue()
    end = object()

    def worker():
        try:
            gen = gen_factory()
            while True:
                try:
                    q.put(next(gen))
                except StopIteration as stop:
                    result["value"] = stop.value or {}
                    break
        except Exception as exc:
            q.put(("error", {"message": str(exc)}))
        finally:
            q.put(end)

    Thread(target=worker, daemon=True).start()
    while True:
        item = await asyncio.to_thread(q.get)
        if item is end:
            break
        yield item


def _safe_groundedness(question: str, context: str, answer: str, llm: LLMContext) -> dict:
    try:
        return _evaluation.groundedness(question, context, answer, llm)
    except Exception as exc:
        return {"score": None, "claims": [], "error": str(exc)}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The mounted MCP app's session manager needs a running task group for the app's lifetime
    async with _mcp.session_manager.run():
        yield
    _graph_store.close()
    _key_store.close()
    _bot_store.close()


app = FastAPI(title="Retrieval Arena", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.exception_handler(openai.APIError)
@app.exception_handler(genai_errors.APIError)
async def provider_error_handler(request: Request, exc: Exception):
    """Surface upstream model-provider failures (bad model, quota, auth) as JSON, not a bare 500."""
    return JSONResponse(status_code=502, content={"detail": f"Model provider error: {exc}"})


def _resolve_key(api_key: Optional[str], key_id: Optional[int]) -> str:
    """Prefer a saved key looked up server-side, so the secret never has to leave the server."""
    if key_id is not None:
        row = _key_store.get_key(key_id)
        if not row:
            raise HTTPException(status_code=404, detail=f"Saved key {key_id} not found")
        return row["api_key"]
    if api_key:
        return api_key
    raise HTTPException(status_code=400, detail="Provide api_key or key_id")


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse("app/static/index.html")


# ---------------------------------------------------------------------------
# Key management
# ---------------------------------------------------------------------------

@app.get("/keys", response_model=list[SavedKeyInfo])
async def list_keys():
    rows = await asyncio.to_thread(_key_store.list_keys)
    return [SavedKeyInfo(**{**r, "is_active": bool(r["is_active"])}) for r in rows]


@app.post("/keys", response_model=SavedKeyInfo)
async def save_key(body: SaveKeyRequest):
    try:
        row = await asyncio.to_thread(
            _key_store.save_key, body.label, body.provider.value, body.api_key
        )
        return SavedKeyInfo(**{**row, "is_active": bool(row["is_active"])})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/keys/{key_id}")
async def delete_key(key_id: int):
    deleted = await asyncio.to_thread(_key_store.delete_key, key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"deleted": True}


@app.post("/keys/{key_id}/activate")
async def activate_key(key_id: int, provider: str = Query(...)):
    await asyncio.to_thread(_key_store.set_active, key_id, provider)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

@app.post("/ingest", response_model=IngestResult)
async def ingest(
    collection: str = Form(...),
    api_key: Optional[str] = Form(None),
    key_id: Optional[int] = Form(None),
    embedding_model: str = Form(settings.default_embed_model),
    gen_model: str = Form(settings.default_gen_model),
    tuning: str = Form("{}"),
    provider: str = Form("gemini"),
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
    api_key = await asyncio.to_thread(_resolve_key, api_key, key_id)

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
            try:
                result = await asyncio.to_thread(
                    _ingestion.ingest,
                    doc_text,
                    collection,
                    tuning_params,
                    api_key,
                    embedding_model,
                    gen_model,
                    prefix,
                    provider,
                    upload.filename,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
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

    try:
        result = await asyncio.to_thread(
            _ingestion.ingest,
            raw_text,
            collection,
            tuning_params,
            api_key,
            embedding_model,
            gen_model,
            "",
            provider,
            "pasted text",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

@app.post("/query")
async def query(body: QueryRequest):
    api_key = await asyncio.to_thread(_resolve_key, body.api_key, body.key_id)
    question, backend, collection = body.question, body.backend.value, body.collection
    gen_model, embedding_model, provider = body.gen_model, body.embedding_model, body.provider.value
    tuning = body.tuning

    if backend == "compare":
        stream = _stream_compare(question, collection, api_key, gen_model, embedding_model, provider, tuning)
    else:
        stream = _stream_query(question, backend, collection, api_key, gen_model, embedding_model, provider, tuning)

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
    provider: str,
    tuning: TuningParams,
) -> AsyncGenerator[str, None]:
    """Run both backends in parallel and prefix every event with 'side' (chroma|graph)."""
    try:
        yield _sse("compare_started", {})

        t0 = time.perf_counter()
        embedding = await asyncio.to_thread(
            _embedding.embed_query, question, api_key, embedding_model, provider
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        yield _sse("embedding_done", {"duration_ms": elapsed_ms})

        mismatch = await asyncio.to_thread(_embedding_mismatch, collection, embedding_model, embedding)
        if mismatch:
            yield _sse("error", {"message": mismatch})
            return

        llm = LLMContext(api_key, gen_model, embedding_model, provider)

        # Run both retrievals concurrently
        chroma_task = asyncio.create_task(
            asyncio.to_thread(
                lambda: list(_retrieval.retrieve_chroma(question, collection, embedding, tuning, llm))
            )
        )
        graph_task = asyncio.create_task(
            asyncio.to_thread(
                lambda: list(
                    _retrieval.retrieve_graph(question, collection, tuning, api_key, gen_model, provider)
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
            "\n\n".join(f"[{c['cite']}] {c['context_text']}" for c in chroma_chunks)
            if chroma_chunks
            else "No relevant context found in the vector store."
        )
        graph_context = (
            "\n".join(
                f"[{i}] {t['subject']} —[{t['relation']}]→ {t['object']}"
                for i, t in enumerate(graph_triples, start=1)
            )
            if graph_triples
            else "No relevant context found in the knowledge graph."
        )

        combined_q: queue.SimpleQueue = queue.SimpleQueue()
        DONE_CHROMA = object()
        DONE_GRAPH = object()

        def _gen_chroma():
            try:
                for token in _generation.stream_answer(
                    question, chroma_context, tuning.system_prompt,
                    api_key, gen_model, tuning.temperature, tuning.max_output_tokens, provider,
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
                    api_key, gen_model, tuning.temperature, tuning.max_output_tokens, provider,
                ):
                    combined_q.put(("graph_token", token))
            except Exception as exc:
                combined_q.put(("graph_error", str(exc)))
            finally:
                combined_q.put(("sentinel", DONE_GRAPH))

        Thread(target=_gen_chroma, daemon=True).start()
        Thread(target=_gen_graph, daemon=True).start()

        answers = {"chroma": [], "graph": []}
        done_count = 0
        while done_count < 2:
            kind, payload = await asyncio.to_thread(combined_q.get)
            if kind == "sentinel":
                done_count += 1
            elif kind == "chroma_token":
                answers["chroma"].append(payload)
                yield _sse("chroma_answer_token", {"token": payload})
            elif kind == "graph_token":
                answers["graph"].append(payload)
                yield _sse("graph_answer_token", {"token": payload})
            elif kind in ("chroma_error", "graph_error"):
                yield _sse(kind, {"message": payload})

        yield _sse("chroma_answer_sentiment", _sentiment.score("".join(answers["chroma"])))
        yield _sse("graph_answer_sentiment", _sentiment.score("".join(answers["graph"])))

        if tuning.check_groundedness:
            yield _sse("evaluation_started", {})
            chroma_eval, graph_eval = await asyncio.gather(
                asyncio.to_thread(_safe_groundedness, question, chroma_context, "".join(answers["chroma"]), llm),
                asyncio.to_thread(_safe_groundedness, question, graph_context, "".join(answers["graph"]), llm),
            )
            yield _sse("chroma_evaluation", chroma_eval)
            yield _sse("graph_evaluation", graph_eval)

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
    provider: str,
    tuning: TuningParams,
) -> AsyncGenerator[str, None]:
    try:
        yield _sse("embedding_started", {})

        t0 = time.perf_counter()
        embedding = await asyncio.to_thread(
            _embedding.embed_query, question, api_key, embedding_model, provider
        )
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        yield _sse("embedding_done", {"duration_ms": elapsed_ms})

        mismatch = await asyncio.to_thread(_embedding_mismatch, collection, embedding_model, embedding)
        if mismatch:
            yield _sse("error", {"message": mismatch})
            return

        if backend == "graph":
            retrieval_events = await asyncio.to_thread(
                lambda: list(
                    _retrieval.retrieve_graph(question, collection, tuning, api_key, gen_model, provider)
                )
            )
        else:
            llm = LLMContext(api_key, gen_model, embedding_model, provider)
            retrieval_events = await asyncio.to_thread(
                lambda: list(
                    _retrieval.retrieve_chroma(question, collection, embedding, tuning, llm)
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
                    f"[{i}] {t['subject']} —[{t['relation']}]→ {t['object']}"
                    for i, t in enumerate(context_triples, start=1)
                )
            else:
                context = "No relevant context found in the knowledge graph."
        else:
            if context_chunks:
                context = "\n\n".join(f"[{c['cite']}] {c['context_text']}" for c in context_chunks)
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
                    provider,
                ):
                    token_q.put(token)
            except Exception as exc:
                token_q.put(exc)
            finally:
                token_q.put(DONE)

        Thread(target=_gen_thread, daemon=True).start()

        answer_parts: list[str] = []
        while True:
            item = await asyncio.to_thread(token_q.get)
            if item is DONE:
                break
            if isinstance(item, Exception):
                yield _sse("error", {"message": str(item)})
                return
            answer_parts.append(item)
            yield _sse("answer_token", {"token": item})

        yield _sse("answer_sentiment", _sentiment.score("".join(answer_parts)))

        if tuning.check_groundedness:
            yield _sse("evaluation_started", {})
            llm_eval = LLMContext(api_key, gen_model, embedding_model, provider)
            result = await asyncio.to_thread(
                _safe_groundedness, question, context, "".join(answer_parts), llm_eval
            )
            yield _sse("evaluation", result)

        yield _sse("done", {})

    except Exception as exc:
        yield _sse("error", {"message": str(exc)})


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

def _collection_summary(name: str) -> dict:
    chunks = _vector_store.get(name)
    sources: dict[str, int] = {}
    for c in chunks:
        src = c["metadata"].get("source") or "(untagged)"
        sources[src] = sources.get(src, 0) + 1
    info = _key_store.get_collection_dim(name) or {}
    try:
        graph = _graph_store.stats(name)
    except Exception:
        graph = {"entities": None, "triples": None}
    return {
        "name": name,
        "chunks": len(chunks),
        "entities": graph["entities"],
        "triples": graph["triples"],
        "sentiment": _sentiment.distribution([c["text"] for c in chunks]),
        "sources": [{"name": k, "chunks": v} for k, v in sorted(sources.items())],
        "embed_provider": info.get("embed_provider"),
        "embed_model": info.get("embed_model"),
        "embed_dim": info.get("embed_dim"),
    }


@app.get("/collections")
async def list_collections():
    names = await asyncio.to_thread(_vector_store.list_collections)
    return await asyncio.gather(*(asyncio.to_thread(_collection_summary, n) for n in sorted(names)))


@app.delete("/collections/{name}")
async def delete_collection(name: str):
    """Remove a collection everywhere it lives: Chroma vectors, Neo4j subgraph, SQLite registry."""
    if name not in await asyncio.to_thread(_vector_store.list_collections):
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    await asyncio.to_thread(_vector_store.delete_collection, name)
    await asyncio.to_thread(_graph_store.delete_graph, name)
    await asyncio.to_thread(_key_store.delete_collection, name)
    _retrieval.invalidate_keyword_index(name)
    return {"deleted": name}


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

@app.get("/history")
async def list_history(q: str = "", limit: int = Query(100, ge=1, le=500)):
    rows = await asyncio.to_thread(_key_store.list_history, q, limit)
    return [{**r, "payload": json.loads(r["payload"]), "pinned": bool(r["pinned"])} for r in rows]


@app.post("/history")
async def add_history(entry: HistoryEntry):
    history_id = await asyncio.to_thread(
        _key_store.add_history, entry.question, entry.backend, entry.collection, json.dumps(entry.payload)
    )
    return {"id": history_id}


@app.post("/history/{history_id}/pin")
async def pin_history(history_id: int, pinned: bool = True):
    if not await asyncio.to_thread(_key_store.set_history_pinned, history_id, pinned):
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"id": history_id, "pinned": pinned}


@app.delete("/history/{history_id}")
async def delete_history(history_id: int):
    if not await asyncio.to_thread(_key_store.delete_history, history_id):
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"deleted": history_id}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

@app.post("/analyze/emotion")
async def analyze_emotion(body: EmotionRequest):
    api_key = await asyncio.to_thread(_resolve_key, body.api_key, body.key_id)
    llm = LLMContext(api_key, body.gen_model, "", body.provider.value)
    return await asyncio.to_thread(_sentiment.emotions, body.text, llm)


# ---------------------------------------------------------------------------
# Bots & chat
# ---------------------------------------------------------------------------

_chat = ChatAgent(_embedding, _retrieval, _generation, _extraction, _sentiment, _evaluation, _embedding_mismatch)

_mcp, _mcp_app = build_mcp_server(
    key_store=_key_store, bot_store=_bot_store, vector_store=_vector_store, embedding=_embedding,
    retrieval=_retrieval, chat=_chat, embedding_mismatch=_embedding_mismatch,
    allowed_hosts=[h.strip() for h in settings.mcp_allowed_hosts.split(",") if h.strip()],
)
# Streamable HTTP endpoint for MCP clients: http://localhost:8000/mcp/ (note the trailing slash)
app.mount("/mcp", _mcp_app)

_mcp_clients = MCPClientManager(_bot_store, allow_stdio=settings.allow_stdio_mcp)
_tool_runner = ToolRunner(_mcp_clients, _generation)
_tool_support_cache: dict[tuple[str, str], dict] = {}


@app.get("/bots")
async def list_bots():
    return await asyncio.to_thread(_bot_store.list_bots)


@app.post("/bots")
async def create_bot(bot: BotIn):
    try:
        return await asyncio.to_thread(_bot_store.save_bot, bot.model_dump(mode="json"))
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"A bot named '{bot.name}' already exists")


@app.put("/bots/{bot_id}")
async def update_bot(bot_id: int, bot: BotIn):
    if not await asyncio.to_thread(_bot_store.get_bot, bot_id):
        raise HTTPException(status_code=404, detail="Bot not found")
    try:
        return await asyncio.to_thread(_bot_store.save_bot, bot.model_dump(mode="json"), bot_id)
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"A bot named '{bot.name}' already exists")


@app.delete("/bots/{bot_id}")
async def delete_bot(bot_id: int):
    if not await asyncio.to_thread(_bot_store.delete_bot, bot_id):
        raise HTTPException(status_code=404, detail="Bot not found")
    return {"deleted": bot_id}


@app.get("/bots/{bot_id}/conversations")
async def list_conversations(bot_id: int):
    return await asyncio.to_thread(_bot_store.list_conversations, bot_id)


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int):
    conv = await asyncio.to_thread(_bot_store.get_conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv["messages"] = await asyncio.to_thread(_bot_store.list_messages, conversation_id)
    return conv


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    if not await asyncio.to_thread(_bot_store.delete_conversation, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": conversation_id}


@app.post("/messages/{message_id}/feedback")
async def message_feedback(message_id: int, body: FeedbackRequest):
    if not await asyncio.to_thread(_bot_store.set_feedback, message_id, body.value):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"id": message_id, "feedback": body.value}


@app.post("/chat")
async def chat(body: ChatRequest):
    """One chat turn as SSE. Saved bots persist the conversation; a draft `bot` is a stateless preview."""
    if body.bot_id is not None:
        bot = await asyncio.to_thread(_bot_store.get_bot, body.bot_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
    elif body.bot is not None:
        bot = {**body.bot.model_dump(mode="json"), "id": None}
    else:
        raise HTTPException(status_code=400, detail="Provide bot_id or a draft bot")

    key_id = body.key_id if body.key_id is not None else bot.get("key_id")
    api_key = await asyncio.to_thread(_resolve_key, body.api_key, key_id if not body.api_key else None)

    conversation_id = None
    if bot["id"] is None:
        history = [
            {"role": m["role"], "content": str(m.get("content", ""))}
            for m in body.history if m.get("role") in ("user", "assistant")
        ]
        message = body.message or ""
    else:
        conversation_id = body.conversation_id
        if conversation_id is not None:
            conv = await asyncio.to_thread(_bot_store.get_conversation, conversation_id)
            if not conv or conv["bot_id"] != bot["id"]:
                raise HTTPException(status_code=404, detail="Conversation not found for this bot")
        if body.regenerate:
            if conversation_id is None:
                raise HTTPException(status_code=400, detail="regenerate needs a conversation_id")
            await asyncio.to_thread(_bot_store.delete_last_assistant, conversation_id)
            msgs = await asyncio.to_thread(_bot_store.list_messages, conversation_id)
            if not msgs or msgs[-1]["role"] != "user":
                raise HTTPException(status_code=400, detail="Nothing to regenerate")
            message = msgs[-1]["content"]
            history = [{"role": m["role"], "content": m["content"]} for m in msgs[:-1]]
        else:
            message = body.message or ""
            if conversation_id is None:
                conversation_id = await asyncio.to_thread(_bot_store.create_conversation, bot["id"], message)
            msgs = await asyncio.to_thread(_bot_store.list_messages, conversation_id)
            history = [{"role": m["role"], "content": m["content"]} for m in msgs]
            await asyncio.to_thread(_bot_store.add_message, conversation_id, "user", message)

    if not message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    async def stream():
        yield _sse("conversation", {"conversation_id": conversation_id})
        result: dict = {}
        failed = False
        tools = _tool_runner if bot.get("tools") else None
        async for event, data in _drain(lambda: _chat.run_turn(bot, history, message, api_key, tools), result):
            failed = failed or event == "error"
            yield _sse(event, data)
        turn = result.get("value") or {}
        message_id = None
        if conversation_id is not None and not failed and turn.get("answer"):
            message_id = await asyncio.to_thread(
                _bot_store.add_message, conversation_id, "assistant", turn["answer"], turn["meta"]
            )
        yield _sse("done", {"conversation_id": conversation_id, "message_id": message_id})

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# MCP servers (client side)
# ---------------------------------------------------------------------------

def _public_server(server: dict) -> dict:
    """Header and env values often carry tokens; only their names leave the server."""
    return {
        **server,
        "headers": {k: "••••" for k in server["headers"]},
        "env": {k: "••••" for k in server["env"]},
    }


@app.get("/mcp-servers")
async def list_mcp_servers():
    servers = await asyncio.to_thread(_bot_store.list_mcp_servers)
    return {"servers": [_public_server(s) for s in servers], "allow_stdio": settings.allow_stdio_mcp}


@app.post("/mcp-servers")
async def add_mcp_server(body: MCPServerIn):
    if body.transport == "http" and not body.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail="HTTP servers need an http(s):// URL")
    if body.transport == "stdio":
        if not settings.allow_stdio_mcp:
            raise HTTPException(status_code=403, detail="stdio MCP servers are disabled; set ALLOW_STDIO_MCP=true")
        if not body.command.strip():
            raise HTTPException(status_code=422, detail="stdio servers need a command")
    try:
        server = await asyncio.to_thread(_bot_store.save_mcp_server, body.model_dump())
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"An MCP server named '{body.name}' already exists")
    return _public_server(server)


@app.post("/mcp-servers/{server_id}/enabled")
async def set_mcp_server_enabled(server_id: int, enabled: bool = True):
    if not await asyncio.to_thread(_bot_store.set_mcp_enabled, server_id, enabled):
        raise HTTPException(status_code=404, detail="MCP server not found")
    return {"id": server_id, "enabled": enabled}


@app.delete("/mcp-servers/{server_id}")
async def delete_mcp_server(server_id: int):
    if not await asyncio.to_thread(_bot_store.delete_mcp_server, server_id):
        raise HTTPException(status_code=404, detail="MCP server not found")
    _mcp_clients.invalidate(server_id)
    return {"deleted": server_id}


@app.get("/mcp-servers/{server_id}/tools")
async def list_mcp_server_tools(server_id: int, refresh: bool = False):
    server = await asyncio.to_thread(_bot_store.get_mcp_server, server_id)
    if not server:
        raise HTTPException(status_code=404, detail="MCP server not found")
    try:
        tools = await asyncio.to_thread(_mcp_clients.list_tools, server, refresh)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach '{server['name']}': {_root_cause(exc)}")
    return {"server": server["name"], "tools": tools}


@app.get("/mcp-tools")
async def list_all_mcp_tools():
    """Every tool on every enabled server, for the Bot Studio picker. Unreachable servers report an error."""
    servers = [s for s in await asyncio.to_thread(_bot_store.list_mcp_servers) if s["enabled"]]

    async def one(server):
        try:
            return await asyncio.to_thread(_mcp_clients.list_tools, server), None
        except Exception as exc:
            return [], {"server": server["name"], "error": _root_cause(exc)}

    results = await asyncio.gather(*(one(s) for s in servers))
    return {
        "tools": [t for tools, _ in results for t in tools],
        "errors": [err for _, err in results if err],
    }


def _root_cause(exc: BaseException) -> str:
    """anyio wraps failures in ExceptionGroups; surface the innermost message."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return str(exc) or type(exc).__name__


@app.post("/config/tool-support")
async def tool_support(body: dict):
    """Does this model accept OpenAI-style tool definitions? Probed once per (provider, model)."""
    provider, model = body.get("provider", "gemini"), body.get("model", "")
    if provider != "nvidia":
        return {"supported": True, "note": "Gemini models support function calling"}
    cache_key = (provider, model)
    if cache_key in _tool_support_cache:
        return _tool_support_cache[cache_key]
    api_key = await asyncio.to_thread(_resolve_key, body.get("api_key"), body.get("key_id"))

    def probe():
        client = openai.OpenAI(api_key=api_key, base_url="https://integrate.api.nvidia.com/v1", timeout=30, max_retries=0)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "What is the weather in Paris? Use the tool."}],
                tools=[{"type": "function", "function": {
                    "name": "get_weather", "description": "Get the weather for a city",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
                }}],
                max_tokens=256,
            )
            called = bool(resp.choices[0].message.tool_calls)
            return {"supported": called, "note": None if called else "Model accepted tools but did not call one"}
        except openai.APIStatusError as exc:
            return {"supported": False, "note": f"Rejected tool definitions ({exc.status_code})"}

    result = await asyncio.to_thread(probe)
    _tool_support_cache[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Config / model validation
# ---------------------------------------------------------------------------

@app.post("/config/validate-key", response_model=ValidateKeyResponse)
async def validate_key(body: ValidateKeyRequest):
    api_key = await asyncio.to_thread(_resolve_key, body.api_key, body.key_id)
    return await asyncio.to_thread(
        _model_config.validate_and_list_models, api_key, body.provider.value
    )
