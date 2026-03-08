"""Analysis router – tariff / risk analysis & alternative sourcing."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..models.schemas import AnalysisResult, JobStatus, NewsArticle
from ..services.job_store import jobs, analysis_results
from ..services.analysis import run_analysis, run_analysis_stream, run_news_scan

router = APIRouter()


@router.post("/run/{job_id}", response_model=AnalysisResult)
async def analyse_supply_chain(job_id: str):
    """Run the full (non-streaming) analysis pipeline."""
    chain = jobs.get(job_id)
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
    chain = jobs.get(job_id)
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
async def get_analysis_result(job_id: str):
    """Poll / fetch the final analysis result for a job."""
    chain = jobs.get(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    cached = analysis_results.get(job_id)
    if cached is not None:
        return cached

    return AnalysisResult(
        job_id=job_id,
        status=JobStatus.pending,
        supply_chain=chain,
        summary="Analysis not yet started.",
    )


@router.post("/news/{job_id}")
async def scan_news(job_id: str):
    """Scan for geopolitical / tariff news affecting the supply chain."""
    chain = jobs.get(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found – upload first.")

    articles = await run_news_scan(chain)
    return {"job_id": job_id, "news_articles": [a.model_dump() for a in articles]}
