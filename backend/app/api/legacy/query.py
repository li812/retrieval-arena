import asyncio
import logging
import queue
import time
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import embedding_mismatch, get_services, resolve_key
from app.api.schemas import QueryRequest, TuningParams
from app.api.streaming import SSE_HEADERS, sse, start_thread
from app.core.container import Services
from app.core.logging import new_run_id
from app.rag.retrieval import LLMContext

logger = logging.getLogger(__name__)
router = APIRouter()


def _safe_groundedness(svc: Services, question: str, context: str, answer: str, llm: LLMContext) -> dict:
    try:
        return svc.evaluation.groundedness(question, context, answer, llm)
    except Exception as exc:
        return {"score": None, "claims": [], "error": str(exc)}


def _chunk_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant context found in the vector store."
    return "\n\n".join(f"[{c['cite']}] {c['context_text']}" for c in chunks)


def _triple_context(triples: list[dict]) -> str:
    if not triples:
        return "No relevant context found in the knowledge graph."
    return "\n".join(f"[{i}] {t['subject']} —[{t['relation']}]→ {t['object']}" for i, t in enumerate(triples, start=1))


@router.post("/query")
async def query(body: QueryRequest, svc: Services = Depends(get_services)):
    api_key = await asyncio.to_thread(resolve_key, svc, body.api_key, body.key_id)
    question, backend, collection = body.question, body.backend.value, body.collection
    gen_model, embedding_model, provider = body.gen_model, body.embedding_model, body.provider.value
    tuning = body.tuning

    if backend == "compare":
        stream = _stream_compare(svc, question, collection, api_key, gen_model, embedding_model, provider, tuning)
    else:
        stream = _stream_query(
            svc, question, backend, collection, api_key, gen_model, embedding_model, provider, tuning
        )
    return StreamingResponse(_logged(stream, backend, collection), media_type="text/event-stream", headers=SSE_HEADERS)


async def _logged(stream: AsyncGenerator[str, None], backend: str, collection: str) -> AsyncGenerator[str, None]:
    new_run_id()
    started = time.perf_counter()
    logger.info("query run started", extra={"backend": backend, "collection": collection})
    failed = False
    async for chunk in stream:
        failed = failed or chunk.startswith("event: error")
        yield chunk
    logger.info(
        "query run finished",
        extra={
            "status": "failed" if failed else "completed",
            "duration_ms": int((time.perf_counter() - started) * 1000),
        },
    )


async def _stream_compare(
    svc: Services,
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
        yield sse("compare_started", {})

        t0 = time.perf_counter()
        embedding = await asyncio.to_thread(svc.embedding.embed_query, question, api_key, embedding_model, provider)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        yield sse("embedding_done", {"duration_ms": elapsed_ms})

        mismatch = await asyncio.to_thread(embedding_mismatch, svc.collections, collection, embedding_model, embedding)
        if mismatch:
            yield sse("error", {"message": mismatch})
            return

        llm = LLMContext(api_key, gen_model, embedding_model, provider)

        # Run both retrievals concurrently
        chroma_task = asyncio.create_task(
            asyncio.to_thread(lambda: list(svc.retrieval.retrieve_chroma(question, collection, embedding, tuning, llm)))
        )
        graph_task = asyncio.create_task(
            asyncio.to_thread(
                lambda: list(svc.retrieval.retrieve_graph(question, collection, tuning, api_key, gen_model, provider))
            )
        )

        chroma_events, graph_events = await asyncio.gather(chroma_task, graph_task)

        chroma_chunks: list[dict] = []
        for ev in chroma_events:
            yield sse("chroma_" + ev["event"], ev["data"])
            if ev["event"] == "context_assembled":
                chroma_chunks = ev["data"].get("chunks", [])

        graph_triples: list[dict] = []
        for ev in graph_events:
            yield sse("graph_" + ev["event"], ev["data"])
            if ev["event"] == "context_assembled":
                graph_triples = ev["data"].get("triples", [])

        chroma_context = _chunk_context(chroma_chunks)
        graph_context = _triple_context(graph_triples)

        combined_q: queue.SimpleQueue = queue.SimpleQueue()
        done_chroma = object()
        done_graph = object()

        def _generate(side: str, context: str, done: object):
            try:
                for token in svc.generation.stream_answer(
                    question,
                    context,
                    tuning.system_prompt,
                    api_key,
                    gen_model,
                    tuning.temperature,
                    tuning.max_output_tokens,
                    provider,
                ):
                    combined_q.put((f"{side}_token", token))
            except Exception as exc:
                combined_q.put((f"{side}_error", str(exc)))
            finally:
                combined_q.put(("sentinel", done))

        start_thread(lambda: _generate("chroma", chroma_context, done_chroma))
        start_thread(lambda: _generate("graph", graph_context, done_graph))

        answers: dict[str, list[str]] = {"chroma": [], "graph": []}
        done_count = 0
        while done_count < 2:
            kind, payload = await asyncio.to_thread(combined_q.get)
            if kind == "sentinel":
                done_count += 1
            elif kind == "chroma_token":
                answers["chroma"].append(payload)
                yield sse("chroma_answer_token", {"token": payload})
            elif kind == "graph_token":
                answers["graph"].append(payload)
                yield sse("graph_answer_token", {"token": payload})
            elif kind in ("chroma_error", "graph_error"):
                yield sse(kind, {"message": payload})

        yield sse("chroma_answer_sentiment", svc.sentiment.score("".join(answers["chroma"])))
        yield sse("graph_answer_sentiment", svc.sentiment.score("".join(answers["graph"])))

        if tuning.check_groundedness:
            yield sse("evaluation_started", {})
            chroma_eval, graph_eval = await asyncio.gather(
                asyncio.to_thread(_safe_groundedness, svc, question, chroma_context, "".join(answers["chroma"]), llm),
                asyncio.to_thread(_safe_groundedness, svc, question, graph_context, "".join(answers["graph"]), llm),
            )
            yield sse("chroma_evaluation", chroma_eval)
            yield sse("graph_evaluation", graph_eval)

        yield sse("done", {})

    except Exception as exc:
        logger.exception("compare query failed")
        yield sse("error", {"message": str(exc)})


async def _stream_query(
    svc: Services,
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
        yield sse("embedding_started", {})

        t0 = time.perf_counter()
        embedding = await asyncio.to_thread(svc.embedding.embed_query, question, api_key, embedding_model, provider)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        yield sse("embedding_done", {"duration_ms": elapsed_ms})

        mismatch = await asyncio.to_thread(embedding_mismatch, svc.collections, collection, embedding_model, embedding)
        if mismatch:
            yield sse("error", {"message": mismatch})
            return

        if backend == "graph":
            retrieval_events = await asyncio.to_thread(
                lambda: list(svc.retrieval.retrieve_graph(question, collection, tuning, api_key, gen_model, provider))
            )
        else:
            llm = LLMContext(api_key, gen_model, embedding_model, provider)
            retrieval_events = await asyncio.to_thread(
                lambda: list(svc.retrieval.retrieve_chroma(question, collection, embedding, tuning, llm))
            )

        context_chunks: list[dict] = []
        context_triples: list[dict] = []
        for ev in retrieval_events:
            yield sse(ev["event"], ev["data"])
            if ev["event"] == "context_assembled":
                context_chunks = ev["data"].get("chunks", [])
                context_triples = ev["data"].get("triples", [])

        context = _triple_context(context_triples) if backend == "graph" else _chunk_context(context_chunks)

        token_q: queue.SimpleQueue = queue.SimpleQueue()
        done = object()

        def _gen_thread():
            try:
                for token in svc.generation.stream_answer(
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
                token_q.put(done)

        start_thread(_gen_thread)

        answer_parts: list[str] = []
        while True:
            item = await asyncio.to_thread(token_q.get)
            if item is done:
                break
            if isinstance(item, Exception):
                yield sse("error", {"message": str(item)})
                return
            answer_parts.append(item)
            yield sse("answer_token", {"token": item})

        yield sse("answer_sentiment", svc.sentiment.score("".join(answer_parts)))

        if tuning.check_groundedness:
            yield sse("evaluation_started", {})
            llm_eval = LLMContext(api_key, gen_model, embedding_model, provider)
            result = await asyncio.to_thread(
                _safe_groundedness, svc, question, context, "".join(answer_parts), llm_eval
            )
            yield sse("evaluation", result)

        yield sse("done", {})

    except Exception as exc:
        logger.exception("query failed")
        yield sse("error", {"message": str(exc)})
