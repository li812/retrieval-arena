import openai
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.genai import errors as genai_errors


async def provider_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Surface upstream model-provider failures (bad model, quota, auth) as JSON, not a bare 500."""
    return JSONResponse(status_code=502, content={"detail": f"Model provider error: {exc}"})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(openai.APIError, provider_error_handler)
    app.add_exception_handler(genai_errors.APIError, provider_error_handler)
