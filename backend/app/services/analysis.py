"""Analysis service – two-phase supplier research + risk analysis.

Phase 1 (research): Web-search each named supplier to discover actual
    sub-component sourcing.  Emits an SSE event so the frontend can display
    discovered nodes/edges on the globe immediately.

Phase 2 (risk): Using research findings, score risks and propose alternatives.
    Emits a second SSE event to update the globe with severity colours.
"""

from __future__ import annotations

import asyncio
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
from .job_store import save_research, save_analysis_result

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


async def _await_with_keepalive(
    coro,
    timeout: float,
) -> tuple[bool, object]:
    """Run *coro* with a hard timeout, returning (ok, result).

    Returns (True, result) on success, (False, None) on timeout.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return True, result
    except asyncio.TimeoutError:
        return False, None


async def run_analysis_stream(
    job_id: str, chain: SupplyChainData
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted events as each analysis phase completes.

    Events emitted:
      event: status   – progress indicator
      event: research – sub-component data
      event: risk     – risks + alternatives
      event: done     – full AnalysisResult
    """
    RESEARCH_TIMEOUT = 150  # seconds
    RISK_TIMEOUT = 90       # seconds

    nodes_json = _nodes_to_json(chain)

    # ── Phase 1: Supplier-specific research ───────────────────────────
    yield _sse("status", {"phase": "research", "message": "Researching suppliers…"})

    # Build ID lookup for remapping LLM output
    valid_ids, name_to_id = _build_id_lookup(chain)

    research: list[SupplierResearch] = []
    try:
        ok, research_data = await _await_with_keepalive(
            _run_research_phase(nodes_json),
            timeout=RESEARCH_TIMEOUT,
        )
        if not ok:
            log.warning("Research phase timed out after %ds for job %s", RESEARCH_TIMEOUT, job_id)
        else:
            log.info("Research raw keys: %s", list(research_data.keys()) if isinstance(research_data, dict) else type(research_data))
            research = _parse_research(research_data)
            log.info("Parsed %d research entries, sub-component counts: %s",
                     len(research),
                     [(r.supplier, len(r.sub_components)) for r in research])
            research = _remap_research(research, valid_ids, name_to_id)
            log.info("After remap: %d research entries, sub-component counts: %s",
                     len(research),
                     [(r.supplier, len(r.sub_components)) for r in research])
    except Exception:
        log.exception("Research phase failed")

    # Retry ONCE if research came back empty (LLM sometimes returns wrong format)
    if not research:
        log.warning("Research empty after first attempt for job %s – retrying", job_id)
        try:
            ok2, research_data2 = await _await_with_keepalive(
                _run_research_phase(nodes_json),
                timeout=RESEARCH_TIMEOUT,
            )
            if ok2 and research_data2:
                log.info("Retry raw keys: %s", list(research_data2.keys()) if isinstance(research_data2, dict) else type(research_data2))
                research = _parse_research(research_data2)
                research = _remap_research(research, valid_ids, name_to_id)
                log.info("Retry produced %d research entries", len(research))
        except Exception:
            log.exception("Research retry also failed")

    yield _sse("research", {
        "job_id": job_id,
        "supplier_research": [r.model_dump() for r in research],
    })

    # Persist research for later use by simulation
    save_research(job_id, research)

    # ── Phase 2: Risk scoring + alternatives ──────────────────────────
    yield _sse("status", {"phase": "risk", "message": "Scoring risks…"})

    risks: list[RiskFactor] = []
    alternatives: list[Alternative] = []
    summary = ""
    try:
        ok, risk_data = await _await_with_keepalive(
            _run_risk_phase(nodes_json, research),
            timeout=RISK_TIMEOUT,
        )
        if not ok:
            log.warning("Risk phase timed out after %ds for job %s", RISK_TIMEOUT, job_id)
        else:
            risks = _parse_risks(risk_data)
            alternatives = _parse_alternatives(risk_data)
            # Remap LLM-generated node_ids to authoritative chain IDs
            risks = _remap_risks(risks, valid_ids, name_to_id, research)
            alternatives = _remap_alternatives(alternatives, valid_ids, name_to_id)
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
        # Parse the last 'done' event
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

CRITICAL HONESTY RULE:
- The "findings" field MUST only contain facts that came from web_search results.
- Do NOT fabricate or guess information about a company.
- If web_search returns no useful results for a specific supplier, you MUST set
  "findings" to exactly the string "NO_DATA" and leave "sub_components" as an
  empty array for that supplier.  This is far better than making things up.

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


# ── Node-ID remapping ────────────────────────────────────────────────


def _build_id_lookup(chain: SupplyChainData) -> tuple[set[str], dict[str, str]]:
    """Return (valid_ids, name_to_id) for fuzzy node-ID remapping."""
    valid = {n.id for n in chain.nodes}
    by_name: dict[str, str] = {}
    for n in chain.nodes:
        by_name[n.name.strip().lower()] = n.id
        if n.supplier:
            by_name[n.supplier.strip().lower()] = n.id
    return valid, by_name


def _remap_research(
    research: list[SupplierResearch],
    valid_ids: set[str],
    name_to_id: dict[str, str],
) -> list[SupplierResearch]:
    """Re-map node_ids returned by the LLM to authoritative chain IDs."""
    out: list[SupplierResearch] = []
    for r in research:
        nid = r.node_id
        if nid not in valid_ids:
            # Try matching by supplier name
            mapped = name_to_id.get(r.supplier.strip().lower())
            if mapped:
                nid = mapped
                log.info("Remapped research node_id %s → %s (supplier=%s)", r.node_id, nid, r.supplier)
            else:
                log.warning("Dropping research entry with unmatchable node_id=%s supplier=%s", r.node_id, r.supplier)
                continue
        out.append(SupplierResearch(
            node_id=nid,
            supplier=r.supplier,
            findings=r.findings,
            sub_components=r.sub_components,
        ))
    return out


def _remap_risks(
    risks: list[RiskFactor],
    valid_ids: set[str],
    name_to_id: dict[str, str],
    research: list[SupplierResearch],
) -> list[RiskFactor]:
    """Re-map risk node_ids to authoritative chain IDs."""
    # Also build a lookup from research supplier name → remapped node_id
    supplier_to_id = {r.supplier.strip().lower(): r.node_id for r in research}
    out: list[RiskFactor] = []
    for r in risks:
        nid = r.node_id
        if nid not in valid_ids:
            # Try the research mapping first (LLM may have used same wrong ID)
            mapped = None
            for res in research:
                if res.node_id == nid or r.node_id == res.node_id:
                    mapped = res.node_id
                    break
            if not mapped:
                mapped = name_to_id.get(r.node_id.strip().lower())
            if mapped and mapped in valid_ids:
                nid = mapped
                log.info("Remapped risk node_id %s → %s", r.node_id, nid)
            else:
                log.warning("Dropping risk with unmatchable node_id=%s", r.node_id)
                continue
        out.append(RiskFactor(
            node_id=nid,
            category=r.category,
            description=r.description,
            severity=r.severity,
            estimated_cost_impact=r.estimated_cost_impact,
        ))
    return out


def _remap_alternatives(
    alternatives: list[Alternative],
    valid_ids: set[str],
    name_to_id: dict[str, str],
) -> list[Alternative]:
    """Re-map alternative original_node_ids to authoritative chain IDs."""
    out: list[Alternative] = []
    for a in alternatives:
        nid = a.original_node_id
        if nid not in valid_ids:
            mapped = name_to_id.get(nid.strip().lower())
            if mapped:
                nid = mapped
            else:
                log.warning("Dropping alternative with unmatchable original_node_id=%s", a.original_node_id)
                continue
        out.append(Alternative(
            original_node_id=nid,
            suggested_supplier=a.suggested_supplier,
            suggested_country=a.suggested_country,
            lat=a.lat,
            lng=a.lng,
            reason=a.reason,
            estimated_savings=a.estimated_savings,
        ))
    return out


# ── Parsers ──────────────────────────────────────────────────────────


def _get(d: dict, *keys, default=None):
    """Get first matching key from dict (handles snake_case/camelCase variants)."""
    for k in keys:
        if k in d:
            return d[k]
    return default


def _parse_research(data: dict) -> list[SupplierResearch]:
    out: list[SupplierResearch] = []
    # Handle both snake_case and camelCase keys from LLM
    items = (
        data.get("supplier_research")
        or data.get("supplierResearch")
        or data.get("research")
        or []
    )
    # If the LLM returned the array directly (not wrapped in an object)
    if isinstance(data, list):
        items = data
    if not items:
        log.warning("_parse_research: no items found. Keys in data: %s", list(data.keys()) if isinstance(data, dict) else type(data))
    for item in items:
        if not isinstance(item, dict):
            continue
        subs = []
        sub_list = _get(item, "sub_components", "subComponents", "sub_component_sources", default=[])
        if not isinstance(sub_list, list):
            sub_list = []
        for sc in sub_list:
            if not isinstance(sc, dict):
                continue
            try:
                lat = float(_get(sc, "lat", "latitude", default=0) or 0)
            except (ValueError, TypeError):
                lat = 0.0
            try:
                lng = float(_get(sc, "lng", "longitude", default=0) or 0)
            except (ValueError, TypeError):
                lng = 0.0
            subs.append(SubComponent(
                component=str(_get(sc, "component", "name", "material", default="")),
                source_company=str(_get(sc, "source_company", "sourceCompany", "company", "supplier", default="")),
                source_country=str(_get(sc, "source_country", "sourceCountry", "country", default="")),
                lat=lat,
                lng=lng,
            ))
        nid = _get(item, "node_id", "nodeId", "id", default="")
        if not nid:
            log.warning("_parse_research: skipping item with no node_id: %s", item.get("supplier", "?"))
            continue
        out.append(SupplierResearch(
            node_id=str(nid),
            supplier=str(_get(item, "supplier", "name", default="")),
            findings=str(_get(item, "findings", "summary", "description", default="")),
            sub_components=subs,
        ))
    log.info("_parse_research: parsed %d entries with %d total subs",
             len(out), sum(len(r.sub_components) for r in out))
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
