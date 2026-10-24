import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_services
from app.api.schemas import HistoryEntry
from app.core.container import Services

router = APIRouter()


@router.get("/history")
async def list_history(q: str = "", limit: int = Query(100, ge=1, le=500), svc: Services = Depends(get_services)):
    rows = await asyncio.to_thread(svc.history.list_history, q, limit)
    return [{**r, "payload": json.loads(r["payload"]), "pinned": bool(r["pinned"])} for r in rows]


@router.post("/history")
async def add_history(entry: HistoryEntry, svc: Services = Depends(get_services)):
    history_id = await asyncio.to_thread(
        svc.history.add_history, entry.question, entry.backend, entry.collection, json.dumps(entry.payload)
    )
    return {"id": history_id}


@router.post("/history/{history_id}/pin")
async def pin_history(history_id: int, pinned: bool = True, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.history.set_history_pinned, history_id, pinned):
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"id": history_id, "pinned": pinned}


@router.delete("/history/{history_id}")
async def delete_history(history_id: int, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.history.delete_history, history_id):
        raise HTTPException(status_code=404, detail="History entry not found")
    return {"deleted": history_id}
