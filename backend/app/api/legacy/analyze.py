import asyncio

from fastapi import APIRouter, Depends

from app.api.deps import get_services, resolve_key
from app.api.schemas import EmotionRequest
from app.core.container import Services
from app.rag.retrieval import LLMContext

router = APIRouter()


@router.post("/analyze/emotion")
async def analyze_emotion(body: EmotionRequest, svc: Services = Depends(get_services)):
    api_key = await asyncio.to_thread(resolve_key, svc, body.api_key, body.key_id)
    llm = LLMContext(api_key, body.gen_model, "", body.provider.value)
    return await asyncio.to_thread(svc.sentiment.emotions, body.text, llm)
