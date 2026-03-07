"""Supply-chain upload & parsing router."""

from fastapi import APIRouter, File, UploadFile, HTTPException

from ..models.schemas import (
    TextUploadRequest,
    UploadResponse,
    SupplyChainData,
)
from ..services.parser import parse_supply_chain_text, parse_supply_chain_text_async
from ..services.job_store import jobs, save_parsed_chain

router = APIRouter()


@router.post("/upload/text", response_model=UploadResponse)
async def upload_text(payload: TextUploadRequest):
    """Receive CSV or free-text supply-chain data, parse it, and kick off
    the analysis pipeline."""
    if not payload.content.strip():
        raise HTTPException(status_code=422, detail="Content must not be empty.")

    # Parse into standardised form (async for free-text LLM extraction)
    parsed: SupplyChainData = await parse_supply_chain_text_async(
        payload.content, fmt=payload.format
    )

    resp = UploadResponse(success=True, message=f"Parsed {len(parsed.nodes)} nodes.")
    save_parsed_chain(resp.job_id, parsed)

    # TODO: kick off async analysis pipeline (celery / background task)
    return resp


@router.post("/upload/image", response_model=UploadResponse)
async def upload_image(file: UploadFile = File(...)):
    """Receive an image of a supply-chain document.  OCR / vision model
    processing will happen asynchronously."""
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="File must be an image.")

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:  # 10 MB cap
        raise HTTPException(status_code=413, detail="Image must be under 10 MB.")

    resp = UploadResponse(
        success=True,
        message="Image received. Processing will begin shortly.",
    )

    # TODO: send image bytes to vision model via service layer
    # save_parsed_chain(resp.job_id, ...)

    return resp


@router.get("/job/{job_id}", response_model=SupplyChainData)
async def get_parsed_chain(job_id: str):
    """Return the parsed supply chain for a given job."""
    chain = jobs.get(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return chain
