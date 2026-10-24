"""Retrieval Arena as an MCP server: lets Claude Code, Claude Desktop, Cursor, ... search your collections.

Mounted on the FastAPI app at /mcp/ (streamable HTTP). Tools use the key last selected in the UI for the
collection's provider, so no secret is ever passed as a tool argument.
"""
import asyncio

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from app.schemas import TuningParams
from app.services.retrieval import LLMContext


def build_mcp_server(*, key_store, bot_store, vector_store, embedding, retrieval, chat, embedding_mismatch,
                     allowed_hosts: list[str]) -> tuple[MCPServer, object]:
    mcp = MCPServer(
        name="retrieval-arena",
        instructions=(
            "Search knowledge collections ingested into Retrieval Arena. Call list_collections first, "
            "then search_collection for passages or graph_query for entity relationships. "
            "ask_bot answers with a configured chatbot."
        ),
    )

    def _llm_for(collection: str, gen_model: str | None) -> LLMContext:
        info = key_store.get_collection_dim(collection)
        if not info:
            raise ValueError(f"Unknown collection '{collection}'. Call list_collections to see what exists.")
        key = key_store.get_active_key(info["embed_provider"])
        if not key:
            raise ValueError(f"No saved {info['embed_provider']} API key; save one in the Retrieval Arena UI.")
        if not gen_model:
            # Borrow the generation model of a bot built on this collection, if any
            gen_model = next((b["gen_model"] for b in bot_store.list_bots()
                              if b["collection"] == collection and b["provider"] == info["embed_provider"]), "")
        return LLMContext(key["api_key"], gen_model, info["embed_model"], info["embed_provider"])

    @mcp.tool(description="List the knowledge collections available for search, with chunk counts and sources.")
    async def list_collections() -> list[dict]:
        def run():
            out = []
            for name in sorted(vector_store.list_collections()):
                info = key_store.get_collection_dim(name)
                if not info:
                    continue  # never ingested through the app (empty or foreign)
                chunks = vector_store.get(name)
                out.append({
                    "name": name,
                    "chunks": len(chunks),
                    "sources": sorted({c["metadata"].get("source", "(untagged)") for c in chunks}),
                    "embedding_model": info["embed_model"],
                })
            return out
        return await asyncio.to_thread(run)

    @mcp.tool(description=(
        "Search a collection and return the most relevant passages with scores. "
        "mode: 'hybrid' (default, embeddings + keywords), 'dense' or 'keyword'."
    ))
    async def search_collection(collection: str, query: str, top_k: int = 5, mode: str = "hybrid") -> dict:
        def run():
            llm = _llm_for(collection, None)
            emb = embedding.embed_query(query, llm.api_key, llm.embedding_model, llm.provider)
            mismatch = embedding_mismatch(collection, llm.embedding_model, emb)
            if mismatch:
                raise ValueError(mismatch)
            tuning = TuningParams(top_k=max(1, min(top_k, 20)), search_mode=mode if mode in ("dense", "hybrid", "keyword") else "hybrid", mmr_diversity=0.0)
            passages = []
            for ev in retrieval.retrieve_chroma(query, collection, emb, tuning, llm):
                if ev["event"] == "chunk_scored":
                    d = ev["data"]
                    passages.append({
                        "rank": d["rank"], "id": d["chunk_id"], "source": d.get("source"),
                        "score": round(d["score"], 4), "text": d["text"],
                    })
            return {"collection": collection, "query": query, "passages": passages}
        return await asyncio.to_thread(run)

    @mcp.tool(description=(
        "Query a collection's knowledge graph: finds entities named in the question and returns the "
        "subject—relation→object facts around them, up to `hops` steps away."
    ))
    async def graph_query(collection: str, question: str, hops: int = 1, gen_model: str | None = None) -> dict:
        def run():
            llm = _llm_for(collection, gen_model)
            if not llm.gen_model:
                raise ValueError("graph_query needs a generation model: pass gen_model, or create a bot for this collection.")
            tuning = TuningParams(graph_hops=max(1, min(hops, 3)), entity_match="fuzzy")
            result = {"entities": [], "triples": []}
            for ev in retrieval.retrieve_graph(question, collection, tuning, llm.api_key, llm.gen_model, llm.provider):
                if ev["event"] == "context_assembled":
                    result = {"entities": ev["data"].get("entities", []), "triples": ev["data"].get("triples", [])}
            return {"collection": collection, **result}
        return await asyncio.to_thread(run)

    @mcp.tool(description="Ask a configured Retrieval Arena chatbot a question; returns its answer and sources.")
    async def ask_bot(bot: str, question: str) -> dict:
        def run():
            target = next((b for b in bot_store.list_bots() if b["name"].lower() == bot.lower() or str(b["id"]) == bot), None)
            if not target:
                names = ", ".join(b["name"] for b in bot_store.list_bots()) or "none"
                raise ValueError(f"No bot named '{bot}'. Available: {names}")
            key = key_store.get_key(target["key_id"]) if target.get("key_id") else key_store.get_active_key(target["provider"])
            if not key:
                raise ValueError(f"No saved {target['provider']} key for this bot.")
            gen = chat.run_turn({**target, "tools": []}, [], question, key["api_key"])
            try:
                while True:
                    kind, data = next(gen)
                    if kind == "error":
                        raise ValueError(data["message"])
            except StopIteration as stop:
                turn = stop.value or {}
            meta = turn.get("meta", {})
            return {
                "bot": target["name"],
                "answer": turn.get("answer", ""),
                "sources": [{"cite": c["cite"], "id": c["id"], "text": c["text"]} for c in meta.get("chunks", [])],
                "graph_facts": meta.get("triples", []),
            }
        return await asyncio.to_thread(run)

    app = mcp.streamable_http_app(
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=[f"http://{h}" for h in allowed_hosts],
        ),
    )
    return mcp, app
