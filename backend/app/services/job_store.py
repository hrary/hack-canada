"""In-memory job store.  Replace with Redis / DB for production."""

from ..models.schemas import SupplyChainData

# job_id -> parsed SupplyChainData
jobs: dict[str, SupplyChainData] = {}


def save_parsed_chain(job_id: str, chain: SupplyChainData) -> None:
    jobs[job_id] = chain
