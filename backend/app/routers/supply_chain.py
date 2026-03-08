"""Supply-chain upload & parsing router."""

from fastapi import APIRouter, HTTPException

from ..models.schemas import (
    TextUploadRequest,
    UploadResponse,
    SupplyChainData,
)
from ..services.parser import parse_supply_chain_text_async
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


@router.get("/job/{job_id}", response_model=SupplyChainData)
async def get_parsed_chain(job_id: str):
    """Return the parsed supply chain for a given job."""
    chain = jobs.get(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return chain
