"""Pydantic models shared across the API."""

from __future__ import annotations

from enum import Enum
from uuid import UUID, uuid4
from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────

class UploadFormat(str, Enum):
    csv = "csv"
    text = "text"


class JobStatus(str, Enum):
    pending = "pending"
    parsing = "parsing"
    analysing = "analysing"
    finding_alternatives = "finding_alternatives"
    complete = "complete"
    error = "error"


class RiskSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


# ── Supply-chain primitives ───────────────────────────────────────────

class GeoPoint(BaseModel):
    lat: float
    lng: float


class SupplyNode(BaseModel):
    """A single node in the supply chain (supplier / material source)."""
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str
    lat: float
    lng: float
    material: str = ""
    supplier: str = ""
    country: str = ""
    hs_code: str = ""
    tariff_rate: float | None = None
    cusma_eligible: bool = False
    cusma_rate: float | None = None
    tariff_cost_delta: float | None = None
    value: float = 0.0  # estimated monetary value (USD) of this supply link


class SupplyChainData(BaseModel):
    """Standardised representation of an uploaded supply chain."""
    headquarters: GeoPoint | None = None
    nodes: list[SupplyNode] = []


# ── Tariff lookup result ──────────────────────────────────────────────

class TariffInfo(BaseModel):
    """Result of a deterministic tariff database lookup."""
    hs_code: str
    description: str
    mfn_rate: float
    applied_rate: float
    cusma_eligible: bool
    cusma_rate: float
    country_override: bool = False
    notes: str = ""


# ── Upload payloads ───────────────────────────────────────────────────

class TextUploadRequest(BaseModel):
    format: UploadFormat
    content: str
    file_name: str | None = Field(None, alias="fileName")


class UploadResponse(BaseModel):
    success: bool
    message: str
    job_id: str = Field(default_factory=lambda: uuid4().hex)


# ── Analysis models ───────────────────────────────────────────────────

class RiskFactor(BaseModel):
    """One identified weakness / risk in the supply chain."""
    node_id: str
    category: str          # e.g. "tariff", "geopolitical", "logistics"
    description: str
    severity: RiskSeverity
    estimated_cost_impact: float | None = None  # % increase, if known


class Alternative(BaseModel):
    """A suggested replacement for a risky supply-chain node."""
    original_node_id: str
    suggested_supplier: str
    suggested_country: str
    lat: float
    lng: float
    reason: str
    estimated_savings: float | None = None  # % savings


class AnalysisResult(BaseModel):
    """Full analysis payload returned to the frontend."""
    job_id: str
    status: JobStatus = JobStatus.complete
    supply_chain: SupplyChainData
    risks: list[RiskFactor] = []
    alternatives: list[Alternative] = []
    supplier_research: list["SupplierResearch"] = []
    summary: str = ""


# ── Supplier research (sub-component discovery) ──────────────────────

class SubComponent(BaseModel):
    """A sub-component discovered during supplier research."""
    component: str
    source_company: str = ""
    source_country: str = ""
    lat: float = 0.0
    lng: float = 0.0


class SupplierResearch(BaseModel):
    """Research findings for a single supplier node."""
    node_id: str
    supplier: str
    findings: str = ""
    sub_components: list[SubComponent] = []


# ── Simulation models ────────────────────────────────────────────────

class SimulationScenario(BaseModel):
    """A what-if scenario the user wants to test."""
    description: str                     # e.g. "25% tariff on Chinese goods"
    affected_countries: list[str] = []
    tariff_change_pct: float | None = None
    trade_deal: str | None = None


class SimulationRequest(BaseModel):
    job_id: str       # references an existing analysis job
    scenarios: list[SimulationScenario]


class NodeImpact(BaseModel):
    node_id: str
    impact_description: str
    cost_change_pct: float
    severity: str = "medium"  # low | medium | high | critical


class Recommendation(BaseModel):
    """A proactive step to mitigate risk or seize opportunity."""
    title: str
    description: str
    priority: str = "medium"   # high | medium | low
    type: str = "mitigate"     # mitigate | opportunity


class SimulationResult(BaseModel):
    job_id: str
    scenario: SimulationScenario
    impacts: list[NodeImpact] = []
    recommendations: list[Recommendation] = []
    total_cost_impact_pct: float = 0.0
    summary: str = ""
