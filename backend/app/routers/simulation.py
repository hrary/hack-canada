"""Simulation router – what-if scenario modelling."""

from fastapi import APIRouter, HTTPException

from ..models.schemas import SimulationRequest, SimulationResult
from ..services.job_store import jobs
from ..services.simulation import run_simulation

router = APIRouter()


@router.post("/run", response_model=list[SimulationResult])
async def simulate(request: SimulationRequest):
    """Run one or more what-if scenarios against an existing supply chain
    analysis.  Examples:
    - "What if the US applies a 25 % tariff on Chinese imports?"
    - "What if a new EU-Mercosur trade deal is signed?"
    """
    chain = jobs.get(request.job_id)
    if chain is None:
        raise HTTPException(status_code=404, detail="Job not found – upload first.")

    results: list[SimulationResult] = []
    for scenario in request.scenarios:
        result = await run_simulation(request.job_id, chain, scenario)
        results.append(result)

    return results
