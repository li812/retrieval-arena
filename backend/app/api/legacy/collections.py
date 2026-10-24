import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_services
from app.core.container import Services

router = APIRouter()


def _collection_summary(svc: Services, name: str) -> dict:
    chunks = svc.vector_store.get(name)
    sources: dict[str, int] = {}
    for c in chunks:
        src = c["metadata"].get("source") or "(untagged)"
        sources[src] = sources.get(src, 0) + 1
    info = svc.collections.get_collection_dim(name) or {}
    try:
        graph = svc.graph_store.stats(name)
    except Exception:
        graph = {"entities": None, "triples": None}
    return {
        "name": name,
        "chunks": len(chunks),
        "entities": graph["entities"],
        "triples": graph["triples"],
        "sentiment": svc.sentiment.distribution([c["text"] for c in chunks]),
        "sources": [{"name": k, "chunks": v} for k, v in sorted(sources.items())],
        "embed_provider": info.get("embed_provider"),
        "embed_model": info.get("embed_model"),
        "embed_dim": info.get("embed_dim"),
    }


@router.get("/collections")
async def list_collections(svc: Services = Depends(get_services)):
    names = await asyncio.to_thread(svc.vector_store.list_collections)
    return await asyncio.gather(*(asyncio.to_thread(_collection_summary, svc, n) for n in sorted(names)))


@router.delete("/collections/{name}")
async def delete_collection(name: str, svc: Services = Depends(get_services)):
    """Remove a collection everywhere it lives: Chroma vectors, Neo4j subgraph, SQLite registry."""
    if name not in await asyncio.to_thread(svc.vector_store.list_collections):
        raise HTTPException(status_code=404, detail=f"Collection '{name}' not found")
    await asyncio.to_thread(svc.vector_store.delete_collection, name)
    await asyncio.to_thread(svc.graph_store.delete_graph, name)
    await asyncio.to_thread(svc.collections.delete_collection, name)
    svc.retrieval.invalidate_keyword_index(name)
    return {"deleted": name}
