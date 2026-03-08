"""In-memory job store.  Replace with Redis / DB for production."""

from ..models.schemas import AnalysisResult, SupplyChainData, SupplierResearch

# job_id -> parsed SupplyChainData
jobs: dict[str, SupplyChainData] = {}

# job_id -> supplier research results (populated after analysis phase 1)
research_store: dict[str, list[SupplierResearch]] = {}

# job_id -> completed analysis result
analysis_results: dict[str, AnalysisResult] = {}


def save_parsed_chain(job_id: str, chain: SupplyChainData) -> None:
    jobs[job_id] = chain


def save_research(job_id: str, research: list[SupplierResearch]) -> None:
    research_store[job_id] = research


def save_analysis_result(job_id: str, result: AnalysisResult) -> None:
    analysis_results[job_id] = result
