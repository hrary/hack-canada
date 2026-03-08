"""Analysis router – tariff / risk analysis & alternative sourcing."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..models.schemas import AnalysisResult, JobStatus
from ..services.job_store import get_parsed_chain, get_analysis_result
from ..services.analysis import run_analysis, run_analysis_stream

router = APIRouter()


@router.post("/run/{job_id}", response_model=AnalysisResult)
async def analyse_supply_chain(job_id: str):
    """Run the full (non-streaming) analysis pipeline."""
    chain = get_parsed_chain(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found – upload first.")

    result = await run_analysis(job_id, chain)
    return result


@router.get("/stream/{job_id}")
async def stream_analysis(job_id: str):
    """SSE endpoint – streams analysis phases as they complete.

    Events:
      event: status   – progress indicator  {"phase": "research", "message": "…"}
      event: research – sub-component data   {"job_id", "supplier_research": [...]}
      event: risk     – risks + alternatives  {"job_id", "risks", "alternatives", "summary"}
      event: done     – full AnalysisResult
    """
    chain = get_parsed_chain(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found – upload first.")

    return StreamingResponse(
        run_analysis_stream(job_id, chain),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/result/{job_id}")
async def fetch_analysis_result(job_id: str):
    """Return the persisted analysis result, or a pending stub if not yet run."""
    stored = get_analysis_result(job_id)
    if stored is not None:
        return stored

    chain = get_parsed_chain(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    return AnalysisResult(
        job_id=job_id,
        status=JobStatus.pending,
        supply_chain=chain,
        summary="Analysis not yet started.",
    )
