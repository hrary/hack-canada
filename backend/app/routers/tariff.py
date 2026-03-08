"""Tariff calculation router."""

from fastapi import APIRouter, HTTPException

from ..services.tariff_lookup import calculate_net_tariff
from ..services.job_store import get_parsed_chain

router = APIRouter()


@router.get("/net-cost/{job_id}")
async def get_net_tariff_cost(job_id: str):
    """Calculate the net tariff cost percentage for a job's supply chain."""
    chain = get_parsed_chain(job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return calculate_net_tariff(chain)
