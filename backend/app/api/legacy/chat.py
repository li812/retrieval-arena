import asyncio
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_services, resolve_key
from app.api.schemas import ChatRequest, FeedbackRequest
from app.api.streaming import SSE_HEADERS, drain, sse
from app.core.container import Services
from app.core.logging import new_run_id

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/bots/{bot_id}/conversations")
async def list_conversations(bot_id: int, svc: Services = Depends(get_services)):
    return await asyncio.to_thread(svc.conversations.list_conversations, bot_id)


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: int, svc: Services = Depends(get_services)):
    conv = await asyncio.to_thread(svc.conversations.get_conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv["messages"] = await asyncio.to_thread(svc.conversations.list_messages, conversation_id)
    return conv


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.conversations.delete_conversation, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": conversation_id}


@router.post("/messages/{message_id}/feedback")
async def message_feedback(message_id: int, body: FeedbackRequest, svc: Services = Depends(get_services)):
    if not await asyncio.to_thread(svc.conversations.set_feedback, message_id, body.value):
        raise HTTPException(status_code=404, detail="Message not found")
    return {"id": message_id, "feedback": body.value}


@router.post("/chat")
async def chat(body: ChatRequest, svc: Services = Depends(get_services)):
    """One chat turn as SSE. Saved bots persist the conversation; a draft `bot` is a stateless preview."""
    conversations = svc.conversations
    if body.bot_id is not None:
        bot = await asyncio.to_thread(svc.bots.get_bot, body.bot_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
    elif body.bot is not None:
        bot = {**body.bot.model_dump(mode="json"), "id": None}
    else:
        raise HTTPException(status_code=400, detail="Provide bot_id or a draft bot")

    key_id = body.key_id if body.key_id is not None else bot.get("key_id")
    api_key = await asyncio.to_thread(resolve_key, svc, body.api_key, key_id if not body.api_key else None)

    conversation_id = None
    if bot["id"] is None:
        history = [
            {"role": m["role"], "content": str(m.get("content", ""))}
            for m in body.history
            if m.get("role") in ("user", "assistant")
        ]
        message = body.message or ""
    else:
        conversation_id = body.conversation_id
        if conversation_id is not None:
            conv = await asyncio.to_thread(conversations.get_conversation, conversation_id)
            if not conv or conv["bot_id"] != bot["id"]:
                raise HTTPException(status_code=404, detail="Conversation not found for this bot")
        if body.regenerate:
            if conversation_id is None:
                raise HTTPException(status_code=400, detail="regenerate needs a conversation_id")
            await asyncio.to_thread(conversations.delete_last_assistant, conversation_id)
            msgs = await asyncio.to_thread(conversations.list_messages, conversation_id)
            if not msgs or msgs[-1]["role"] != "user":
                raise HTTPException(status_code=400, detail="Nothing to regenerate")
            message = msgs[-1]["content"]
            history = [{"role": m["role"], "content": m["content"]} for m in msgs[:-1]]
        else:
            message = body.message or ""
            if conversation_id is None:
                conversation_id = await asyncio.to_thread(conversations.create_conversation, bot["id"], message)
            msgs = await asyncio.to_thread(conversations.list_messages, conversation_id)
            history = [{"role": m["role"], "content": m["content"]} for m in msgs]
            await asyncio.to_thread(conversations.add_message, conversation_id, "user", message)

    if not message.strip():
        raise HTTPException(status_code=400, detail="Empty message")

    async def stream():
        new_run_id()
        started = time.perf_counter()
        logger.info("chat run started", extra={"bot_id": bot["id"], "conversation_id": conversation_id})
        yield sse("conversation", {"conversation_id": conversation_id})
        result: dict = {}
        failed = False
        tools = svc.tool_runner if bot.get("tools") else None
        async for event, data in drain(lambda: svc.chat.run_turn(bot, history, message, api_key, tools), result):
            failed = failed or event == "error"
            yield sse(event, data)
        turn = result.get("value") or {}
        message_id = None
        if conversation_id is not None and not failed and turn.get("answer"):
            message_id = await asyncio.to_thread(
                conversations.add_message, conversation_id, "assistant", turn["answer"], turn["meta"]
            )
        logger.info(
            "chat run finished",
            extra={
                "status": "failed" if failed else "completed",
                "duration_ms": int((time.perf_counter() - started) * 1000),
            },
        )
        yield sse("done", {"conversation_id": conversation_id, "message_id": message_id})

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)
