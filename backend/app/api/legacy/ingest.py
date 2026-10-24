import asyncio
import io
import json

import pypdf
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.deps import get_services, resolve_key
from app.api.schemas import IngestResult, TuningParams
from app.core.config import settings
from app.core.container import Services

router = APIRouter()


@router.post("/ingest", response_model=IngestResult)
async def ingest(
    collection: str = Form(...),
    api_key: str | None = Form(None),
    key_id: int | None = Form(None),
    embedding_model: str = Form(settings.default_embed_model),
    gen_model: str = Form(settings.default_gen_model),
    tuning: str = Form("{}"),
    provider: str = Form("gemini"),
    text: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),  # noqa: B008
    svc: Services = Depends(get_services),
):
    has_files = bool(files and any(f.filename for f in files))
    if not text and not has_files:
        raise HTTPException(status_code=400, detail="Provide either text or at least one file.")

    try:
        tuning_data = json.loads(tuning)
    except json.JSONDecodeError:
        tuning_data = {}
    tuning_params = TuningParams(**tuning_data)
    api_key = await asyncio.to_thread(resolve_key, svc, api_key, key_id)

    if has_files:
        total_chunks = 0
        total_triples = 0
        last_result: IngestResult | None = None

        for doc_idx, upload in enumerate(files):
            if not upload.filename:
                continue
            content = await upload.read()
            filename = upload.filename.lower()
            if filename.endswith(".pdf"):
                reader = pypdf.PdfReader(io.BytesIO(content))
                doc_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            else:
                doc_text = content.decode("utf-8", errors="replace")

            if not doc_text.strip():
                continue

            prefix = f"{collection}_d{doc_idx:02d}"
            try:
                result = await asyncio.to_thread(
                    svc.ingestion.ingest,
                    doc_text,
                    collection,
                    tuning_params,
                    api_key,
                    embedding_model,
                    gen_model,
                    prefix,
                    provider,
                    upload.filename,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            total_chunks += result.num_chunks
            total_triples += result.num_triples
            last_result = result

        if last_result is None:
            raise HTTPException(status_code=400, detail="All uploaded files were empty.")

        return IngestResult(
            collection=collection,
            documents=sum(1 for f in files if f.filename),
            num_chunks=total_chunks,
            num_triples=total_triples,
            embedding_model=embedding_model,
        )

    raw_text = text or ""
    if not raw_text.strip():
        raise HTTPException(status_code=400, detail="Extracted text is empty.")

    try:
        result = await asyncio.to_thread(
            svc.ingestion.ingest,
            raw_text,
            collection,
            tuning_params,
            api_key,
            embedding_model,
            gen_model,
            "",
            provider,
            "pasted text",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result
