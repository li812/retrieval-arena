import time
from typing import Callable, Generator, Optional

from app.schemas import TuningParams
from app.services.retrieval import LLMContext

_HISTORY_TURNS = 10  # prior messages sent to the model and to the rewriter


class ChatAgent:
    """One conversational turn: rewrite → retrieve → generate → check. Yields (event, data) tuples."""

    def __init__(self, embedding, retrieval, generation, extraction, sentiment, evaluation,
                 embedding_guard: Callable[[str, str, list[float]], Optional[str]]):
        self._embedding = embedding
        self._retrieval = retrieval
        self._generation = generation
        self._extraction = extraction
        self._sentiment = sentiment
        self._evaluation = evaluation
        self._guard = embedding_guard

    def rewrite(self, history: list[dict], message: str, llm: LLMContext) -> str:
        """Turn a follow-up ("when did he land?") into a standalone search query using the chat so far."""
        transcript = "\n".join(f"{m['role'].upper()}: {m['content'][:600]}" for m in history[-6:])
        prompt = (
            "Rewrite the user's latest message as a standalone search query that can be understood "
            "without the conversation. Resolve pronouns and references using the conversation. "
            "If it is already standalone, return it unchanged. Return ONLY the query.\n\n"
            f"Conversation:\n{transcript}\n\nLatest message: {message}"
        )
        rewritten = self._extraction.complete(prompt, llm.api_key, llm.gen_model, llm.provider, max_tokens=256)
        return rewritten.strip().strip('"') or message

    def run_turn(self, bot: dict, history: list[dict], message: str, api_key: str,
                 tools=None) -> Generator[tuple[str, dict], None, dict]:
        tuning = TuningParams(**bot["tuning"]) if isinstance(bot["tuning"], dict) else bot["tuning"]
        llm = LLMContext(api_key, bot["gen_model"], bot["embedding_model"], bot["provider"])
        history = history[-_HISTORY_TURNS:]
        started = time.perf_counter()

        # 1. Standalone query for retrieval
        query = message
        if history:
            try:
                query = self.rewrite(history, message, llm)
            except Exception as exc:
                yield "warning", {"stage": "rewrite", "message": str(exc)}
            yield "rewritten", {"query": query, "changed": query != message}

        # 2. Retrieval
        chunks: list[dict] = []
        triples: list[dict] = []
        trace: dict = {}
        embedding = self._embedding.embed_query(query, api_key, bot["embedding_model"], bot["provider"])
        mismatch = self._guard(bot["collection"], bot["embedding_model"], embedding)
        if mismatch:
            yield "error", {"message": mismatch}
            return {}

        if bot["backend"] in ("chroma", "both"):
            for ev in self._retrieval.retrieve_chroma(query, bot["collection"], embedding, tuning, llm):
                yield ev["event"], ev["data"]
                if ev["event"] == "context_assembled":
                    chunks = ev["data"]["chunks"]
                elif ev["event"] == "pipeline_trace":
                    trace = ev["data"]
        if bot["backend"] in ("graph", "both"):
            for ev in self._retrieval.retrieve_graph(query, bot["collection"], tuning, api_key, bot["gen_model"], bot["provider"]):
                name = "graph_" + ev["event"] if bot["backend"] == "both" else ev["event"]
                yield name, ev["data"]
                if ev["event"] == "context_assembled":
                    triples = ev["data"].get("triples", [])

        context = self._build_context(chunks, triples)

        # 3. Generation (tool-calling when the bot has MCP tools)
        user_content = f"## Retrieved context\n{context}\n\n## User message\n{message}"
        answer_parts: list[str] = []
        tool_calls: list[dict] = []
        if tools:
            for kind, data in tools.run(bot, history, user_content, llm, tuning):
                if kind == "token":
                    answer_parts.append(data["token"])
                elif kind == "tool_result":
                    tool_calls.append(data)
                yield kind, data
        else:
            for token in self._generation.stream_chat(
                bot["system_prompt"], history, user_content, api_key, bot["gen_model"],
                tuning.temperature, tuning.max_output_tokens, bot["provider"],
            ):
                answer_parts.append(token)
                yield "token", {"token": token}
        answer = "".join(answer_parts)

        # 4. Checks
        sentiment = self._sentiment.score(answer)
        yield "sentiment", sentiment
        evaluation = None
        if tuning.check_groundedness:
            yield "evaluation_started", {}
            try:
                evaluation = self._evaluation.groundedness(message, context, answer, llm)
            except Exception as exc:
                evaluation = {"score": None, "claims": [], "error": str(exc)}
            yield "evaluation", evaluation

        return {
            "answer": answer,
            "meta": {
                "query": query if query != message else None,
                "chunks": [{k: c[k] for k in ("id", "text", "score", "cite")} for c in chunks],
                "triples": triples,
                "trace": trace,
                "sentiment": sentiment,
                "evaluation": evaluation,
                "tool_calls": tool_calls,
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        }

    @staticmethod
    def _build_context(chunks: list[dict], triples: list[dict]) -> str:
        parts = []
        if chunks:
            parts.append("\n\n".join(f"[{c['cite']}] {c['context_text']}" for c in chunks))
        if triples:
            offset = len(chunks)
            parts.append("Knowledge graph facts:\n" + "\n".join(
                f"[{offset + i}] {t['subject']} —[{t['relation']}]→ {t['object']}"
                for i, t in enumerate(triples, start=1)
            ))
        return "\n\n".join(parts) or "No relevant context was found in the knowledge base."
