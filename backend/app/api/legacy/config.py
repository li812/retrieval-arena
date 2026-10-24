import asyncio

import openai
from fastapi import APIRouter, Depends

from app.api.deps import get_services, resolve_key
from app.api.schemas import ValidateKeyRequest, ValidateKeyResponse
from app.core.container import Services

router = APIRouter()

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


@router.post("/config/tool-support")
async def tool_support(body: dict, svc: Services = Depends(get_services)):
    """Does this model accept OpenAI-style tool definitions? Probed once per (provider, model)."""
    provider, model = body.get("provider", "gemini"), body.get("model", "")
    if provider != "nvidia":
        return {"supported": True, "note": "Gemini models support function calling"}
    cache_key = (provider, model)
    if cache_key in svc.tool_support_cache:
        return svc.tool_support_cache[cache_key]
    api_key = await asyncio.to_thread(resolve_key, svc, body.get("api_key"), body.get("key_id"))

    def probe():
        client = svc.openai_factory(api_key=api_key, base_url=NVIDIA_BASE_URL, timeout=30, max_retries=0)
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "What is the weather in Paris? Use the tool."}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "description": "Get the weather for a city",
                            "parameters": {
                                "type": "object",
                                "properties": {"city": {"type": "string"}},
                                "required": ["city"],
                            },
                        },
                    }
                ],
                max_tokens=256,
            )
            called = bool(resp.choices[0].message.tool_calls)
            return {"supported": called, "note": None if called else "Model accepted tools but did not call one"}
        except openai.APIStatusError as exc:
            return {"supported": False, "note": f"Rejected tool definitions ({exc.status_code})"}

    result = await asyncio.to_thread(probe)
    svc.tool_support_cache[cache_key] = result
    return result


@router.post("/config/validate-key", response_model=ValidateKeyResponse)
async def validate_key(body: ValidateKeyRequest, svc: Services = Depends(get_services)):
    api_key = await asyncio.to_thread(resolve_key, svc, body.api_key, body.key_id)
    return await asyncio.to_thread(svc.model_config.validate_and_list_models, api_key, body.provider.value)
