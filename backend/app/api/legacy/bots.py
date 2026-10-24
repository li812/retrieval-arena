import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_services
from app.api.schemas import BotIn
from app.core.container import Services
from app.core.errors import DuplicateNameError

router = APIRouter()


@router.get("/bots")
async def list_bots(svc: Services = Depends(get_services)):
    return await asyncio.to_thread(svc.bots.list_bots)


@router.post("/bots")
async def create_bot(bot: BotIn, svc: Services = Depends(get_services)):
    try:
        return await asyncio.to_thread(svc.bots.save_bot, bot.model_dump(mode="json"))
    except DuplicateNameError as exc:
        raise HTTPException(status_code=409, detail=f"A bot named '{bot.name}' already exists") from exc


@router.put("/bots/{bot_id}")
async def update_bot(bot_id: int, bot: BotIn, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.bots.get_bot, bot_id):
        raise HTTPException(status_code=404, detail="Bot not found")
    try:
        return await asyncio.to_thread(svc.bots.save_bot, bot.model_dump(mode="json"), bot_id)
    except DuplicateNameError as exc:
        raise HTTPException(status_code=409, detail=f"A bot named '{bot.name}' already exists") from exc


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: int, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.bots.delete_bot, bot_id):
        raise HTTPException(status_code=404, detail="Bot not found")
    return {"deleted": bot_id}
