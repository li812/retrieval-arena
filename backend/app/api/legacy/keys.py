import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_services
from app.api.schemas import SavedKeyInfo, SaveKeyRequest
from app.core.container import Services

router = APIRouter()


@router.get("/keys", response_model=list[SavedKeyInfo])
async def list_keys(svc: Services = Depends(get_services)):
    rows = await asyncio.to_thread(svc.provider_keys.list_keys)
    return [SavedKeyInfo(**{**r, "is_active": bool(r["is_active"])}) for r in rows]


@router.post("/keys", response_model=SavedKeyInfo)
async def save_key(body: SaveKeyRequest, svc: Services = Depends(get_services)):
    try:
        row = await asyncio.to_thread(svc.provider_keys.save_key, body.label, body.provider.value, body.api_key)
        return SavedKeyInfo(**{**row, "is_active": bool(row["is_active"])})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/keys/{key_id}")
async def delete_key(key_id: int, svc: Services = Depends(get_services)):
    deleted = await asyncio.to_thread(svc.provider_keys.delete_key, key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"deleted": True}


@router.post("/keys/{key_id}/activate")
async def activate_key(key_id: int, provider: str = Query(...), svc: Services = Depends(get_services)):
    await asyncio.to_thread(svc.provider_keys.set_active, key_id, provider)
    return {"ok": True}
