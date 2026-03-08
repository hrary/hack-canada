"""Analysis service – two-phase supplier research + risk analysis.

Phase 1 (research): Web-search each named supplier to discover actual
    sub-component sourcing.  Emits an SSE event so the frontend can display
    discovered nodes/edges on the globe immediately.

Phase 2 (risk): Using research findings, score risks and propose alternatives.
    Emits a second SSE event to update the globe with severity colours.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

from ..models.schemas import (
    AnalysisResult,
    JobStatus,
    RiskFactor,
    RiskSeverity,
    Alternative,
    SupplyChainData,
    SupplierResearch,
    SubComponent,
)
from .backboard import ask_analysis_research, ask_analysis_risk
from .job_store import save_analysis_result

log = logging.getLogger(__name__)


def _nodes_to_json(chain: SupplyChainData) -> str:
    """Serialise nodes to a compact JSON string for the LLM prompt."""
    return json.dumps(
        [
            {
                "id": n.id,
                "name": n.name,
                "lat": n.lat,
                "lng": n.lng,
                "material": n.material,
                "supplier": n.supplier,
                "country": n.country,
                "hs_code": n.hs_code,
                "tariff_rate_pct": n.tariff_rate,
                "cusma_eligible": n.cusma_eligible,
            }
            for n in chain.nodes
        ],
        indent=2,
    )


# ── Streaming (SSE) analysis ─────────────────────────────────────────


async def run_analysis_stream(
    job_id: str, chain: SupplyChainData
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events as each analysis phase completes.

    Events emitted:
      event: phase\n data: {"phase": "research", ...}\n\n
      event: phase\n data: {"phase": "risk", ...}\n\n
      event: done\n  data: {full AnalysisResult}\n\n
    """
    nodes_json = _nodes_to_json(chain)

    # ── Phase 1: Supplier-specific research ───────────────────────────
    yield _sse("status", {"phase": "research", "message": "Researching suppliers…"})

    research: list[SupplierResearch] = []
    try:
        research_data = await _run_research_phase(nodes_json)
        research = _parse_research(research_data)
    except Exception:
        log.exception("Research phase failed")

    yield _sse("research", {
        "job_id": job_id,
        "supplier_research": [r.model_dump() for r in research],
    })

    # ── Phase 2: Risk scoring + alternatives ──────────────────────────
    yield _sse("status", {"phase": "risk", "message": "Scoring risks…"})

    risks: list[RiskFactor] = []
    alternatives: list[Alternative] = []
    summary = ""
    try:
        risk_data = await _run_risk_phase(nodes_json, research)
        risks = _parse_risks(risk_data)
        alternatives = _parse_alternatives(risk_data)
        summary = risk_data.get("summary", "")
    except Exception:
        log.exception("Risk phase failed")

    if not summary:
        summary = (
            f"Analysed {len(chain.nodes)} nodes. "
            f"Found {len(risks)} risk(s) and {len(alternatives)} alternative(s)."
        )

    result = AnalysisResult(
        job_id=job_id,
        status=JobStatus.complete,
        supply_chain=chain,
        risks=risks,
        alternatives=alternatives,
        supplier_research=research,
        summary=summary,
    )

    save_analysis_result(job_id, result)

    yield _sse("risk", {
        "job_id": job_id,
        "risks": [r.model_dump() for r in risks],
        "alternatives": [a.model_dump() for a in alternatives],
        "summary": summary,
    })

    yield _sse("done", result.model_dump())


# ── Non-streaming convenience (kept for backward compat) ─────────────


async def run_analysis(job_id: str, chain: SupplyChainData) -> AnalysisResult:
    """Execute the full analysis pipeline and return final AnalysisResult."""
    last: dict = {}
    async for event in run_analysis_stream(job_id, chain):
        for line in event.strip().split("\n"):
            if line.startswith("data: "):
                last = json.loads(line[6:])
    if last:
        return AnalysisResult(**last)
    result = _fallback_analysis(job_id, chain)
    save_analysis_result(job_id, result)
    return result


# ── Phase runners ────────────────────────────────────────────────────


async def _run_research_phase(nodes_json: str) -> dict:
    prompt = f"""\
Research the following supply-chain nodes.  Each node has a NAMED SUPPLIER.

NODES:
{nodes_json}

INSTRUCTIONS:
For EACH node, use the web_search tool to research the **specific named
supplier** and discover where THEY source their sub-components or raw materials.
Do NOT generalise — look up the actual company.

Because these are MANUFACTURED or ASSEMBLED products, each supplier will have
many sub-components.  You MUST find at least 4 sub-components per supplier node,
and ideally 5-8.  Think about what goes INTO the finished product:
  • Semiconductor chips, PCBs, connectors, casings, displays, batteries,
    motors, gears, wiring, sensors, software IPs, rare-earth magnets, etc.
  • For each sub-component identify WHO supplies it and WHERE.

Only go one level deep — do NOT research sub-sub-components.
Use web_search for EVERY supplier node to ground your answers in real data.

Return a JSON object:
{{
  "supplier_research": [
    {{
      "node_id": "<id>",
      "supplier": "<supplier name>",
      "findings": "<1-2 sentence summary of their sourcing>",
      "sub_components": [
        {{
          "component": "<sub-component or raw material>",
          "source_company": "<who supplies it to them>",
          "source_country": "<country>",
          "lat": <latitude of source>,
          "lng": <longitude of source>
        }}
      ]
    }}
  ]
}}

Include realistic lat/lng for each sub-component source (use city coords where
the supplier's factory or HQ is located, not just the capital).
"""
    return await ask_analysis_research(prompt)


async def _run_risk_phase(
    nodes_json: str, research: list[SupplierResearch]
) -> dict:
    research_json = json.dumps(
        [r.model_dump() for r in research], indent=2
    )
    prompt = f"""\
Assess risks for the following supply chain using the research data below.

PRIMARY NODES (with deterministic tariff data from CBSA database):
{nodes_json}

SUPPLIER RESEARCH (sub-component sources discovered):
{research_json}

IMPORTANT — TARIFF DATA RULES:
Each node already has deterministic tariff data looked up from the Canadian
customs tariff schedule (CBSA).  The fields tariff_rate_pct and cusma_eligible
are AUTHORITATIVE — do NOT estimate or override them.
- For tariff-category risks, use the provided tariff_rate_pct as the
  estimated_cost_impact.
- A node with tariff_rate_pct > 0 should get a tariff risk; severity should
  scale with the rate (>25% = critical, >10% = high, >5% = medium, else low).
- If cusma_eligible is true and the country is US or Mexico, tariff risk is
  low or absent — note CUSMA eligibility in the description.
- Focus your analytical effort on geopolitical, logistics, and single-source
  risks where the LLM adds real value.

Return a JSON object:
{{
  "risks": [
    {{
      "node_id": "<id of affected node>",
      "category": "tariff | geopolitical | logistics | single_source",
      "description": "<one-sentence explanation grounded in research>",
      "severity": "low | medium | high | critical",
      "estimated_cost_impact": <number or null>
    }}
  ],
  "alternatives": [
    {{
      "original_node_id": "<id of node being replaced>",
      "suggested_supplier": "<real company name>",
      "suggested_country": "<country>",
      "lat": <latitude>,
      "lng": <longitude>,
      "reason": "<why better, referencing research>",
      "estimated_savings": <percentage or null>
    }}
  ],
  "summary": "<2-3 sentence executive summary>"
}}
"""
    return await ask_analysis_risk(prompt)


# ── Parsers ──────────────────────────────────────────────────────────


def _parse_research(data: dict) -> list[SupplierResearch]:
    out: list[SupplierResearch] = []
    for item in data.get("supplier_research", []):
        subs = []
        for sc in item.get("sub_components", []):
            try:
                subs.append(SubComponent(
                    component=sc.get("component", ""),
                    source_company=sc.get("source_company", ""),
                    source_country=sc.get("source_country", ""),
                    lat=float(sc.get("lat", 0)),
                    lng=float(sc.get("lng", 0)),
                ))
            except (ValueError, TypeError):
                continue
        try:
            out.append(SupplierResearch(
                node_id=item["node_id"],
                supplier=item.get("supplier", ""),
                findings=item.get("findings", ""),
                sub_components=subs,
            ))
        except KeyError:
            continue
    return out


def _parse_risks(data: dict) -> list[RiskFactor]:
    risks: list[RiskFactor] = []
    for r in data.get("risks", []):
        try:
            risks.append(RiskFactor(
                node_id=r["node_id"],
                category=r.get("category", "tariff"),
                description=r.get("description", ""),
                severity=RiskSeverity(r.get("severity", "medium")),
                estimated_cost_impact=r.get("estimated_cost_impact"),
            ))
        except (KeyError, ValueError):
            continue
    return risks


def _parse_alternatives(data: dict) -> list[Alternative]:
    alts: list[Alternative] = []
    for a in data.get("alternatives", []):
        try:
            alts.append(Alternative(
                original_node_id=a["original_node_id"],
                suggested_supplier=a.get("suggested_supplier", ""),
                suggested_country=a.get("suggested_country", ""),
                lat=float(a.get("lat", 0)),
                lng=float(a.get("lng", 0)),
                reason=a.get("reason", ""),
                estimated_savings=a.get("estimated_savings"),
            ))
        except (KeyError, ValueError, TypeError):
            continue
    return alts


# ── SSE formatter ────────────────────────────────────────────────────


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


# ── Fallback ─────────────────────────────────────────────────────────


def _fallback_analysis(job_id: str, chain: SupplyChainData) -> AnalysisResult:
    risks: list[RiskFactor] = []
    for node in chain.nodes:
        rate = node.tariff_rate or 0
        if rate > 25:
            sev = RiskSeverity.critical
        elif rate > 10:
            sev = RiskSeverity.high
        elif rate > 5:
            sev = RiskSeverity.medium
        elif rate > 0:
            sev = RiskSeverity.low
        else:
            sev = RiskSeverity.low

        desc = (
            f"{node.material} from {node.country} — "
            f"HS {node.hs_code}, {rate}% duty"
            if node.hs_code
            else f"Potential tariff exposure on {node.material} from {node.country}."
        )
        if node.cusma_eligible:
            desc += " (CUSMA eligible)"

        risks.append(RiskFactor(
            node_id=node.id,
            category="tariff",
            description=desc,
            severity=sev,
            estimated_cost_impact=rate if rate > 0 else None,
        ))

    return AnalysisResult(
        job_id=job_id,
        status=JobStatus.complete,
        supply_chain=chain,
        risks=risks,
        alternatives=[],
        summary=(
            f"[Fallback] Analysed {len(chain.nodes)} nodes using CBSA tariff data. "
            f"Found {len(risks)} risk(s). LLM was unavailable."
        ),
    )
