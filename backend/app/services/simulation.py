"""Simulation service – what-if scenario modelling.

Given an existing supply chain and a hypothetical change (new tariff,
trade deal, embargo, etc.), estimate the impact on each node and provide
proactive recommendations.
"""

from __future__ import annotations

import json
import logging

from ..models.schemas import (
    Recommendation,
    SimulationResult,
    SimulationScenario,
    SupplyChainData,
    SupplierResearch,
    NodeImpact,
)
from .backboard import ask_simulation
from .job_store import research_store

log = logging.getLogger(__name__)


def _build_context_json(chain: SupplyChainData, research: list[SupplierResearch]) -> str:
    """Build a rich JSON context that includes nodes and their sub-components."""
    nodes = []
    research_by_id = {r.node_id: r for r in research}
    for n in chain.nodes:
        node_dict: dict = {
            "id": n.id,
            "name": n.name,
            "material": n.material,
            "supplier": n.supplier,
            "country": n.country,
            "value_usd": n.value,
        }
        res = research_by_id.get(n.id)
        if res:
            node_dict["sub_components"] = [
                {
                    "component": sc.component,
                    "source_company": sc.source_company,
                    "source_country": sc.source_country,
                }
                for sc in res.sub_components
            ]
        nodes.append(node_dict)
    return json.dumps(nodes, indent=2)


async def run_simulation(
    job_id: str,
    chain: SupplyChainData,
    scenario: SimulationScenario,
) -> SimulationResult:
    """Evaluate a single what-if scenario against the supply chain."""

    # Include research context if available
    research = research_store.get(job_id, [])
    context_json = _build_context_json(chain, research)

    prompt = f"""\
Evaluate the following what-if scenario against the supply chain.
Use web_search to look up the latest real-world data relevant to this scenario.

SUPPLY-CHAIN NODES (with sub-component sourcing and USD values):
{context_json}

SCENARIO:
  Description: {scenario.description}
  Affected countries: {', '.join(scenario.affected_countries) if scenario.affected_countries else 'infer from description'}
  Tariff change: {scenario.tariff_change_pct if scenario.tariff_change_pct is not None else 'infer from description'}%
  Trade deal: {scenario.trade_deal or 'N/A'}

IMPORTANT – HOLISTIC COST ANALYSIS RULES:
- Do NOT simply pass through a headline tariff rate as the cost change.
- For each affected node, estimate what fraction of its bill-of-materials (BOM)
  actually comes from the affected region/source.  Multiply the tariff or cost
  change by that fraction to get the direct impact.
- Then adjust for real-world absorption factors:
  • Supplier margin absorption (large suppliers often eat 20-40% of increases)
  • Existing forward contracts and inventory buffers
  • Currency movements triggered by the event
  • Substitution effects and demand elasticity
- Show your reasoning in the impact_description (e.g. "~35% of BOM sourced
  from China × 25% tariff × 0.7 absorption factor ≈ 6.1% net cost increase").
- Severity bands: low (< 3%), medium (3-8%), high (8-15%), critical (> 15%).
- For total_cost_impact_pct, compute a VALUE-WEIGHTED average across all nodes
  (use each node's value_usd as weight), NOT a simple average.

Return a JSON object with exactly this shape:
{{
  "impacts": [
    {{
      "node_id": "<id of the affected node>",
      "impact_description": "<explain: BOM fraction affected, tariff rate, absorption factors, net result>",
      "cost_change_pct": <realistic net percentage cost change after all factors>,
      "severity": "low | medium | high | critical"
    }}
  ],
  "recommendations": [
    {{
      "title": "<short action title>",
      "description": "<1-2 sentence explanation of the step and its expected benefit>",
      "priority": "high | medium | low",
      "type": "mitigate | opportunity"
    }}
  ],
  "total_cost_impact_pct": <single number: value-weighted average cost impact>,
  "summary": "<2-3 sentence executive summary including the calculation methodology used>"
}}

ADDITIONAL RULES:
- Only include nodes that would actually be affected.
- Consider BOTH direct impacts on primary nodes AND indirect impacts through
  their sub-component supply chains.
- Consider second-order effects: scarcity-driven lead time increases, nodes
  that BENEFIT from the event, commodity price ripple effects.
- Provide 3-6 recommendations: a mix of risk mitigation AND opportunities.
- Use web_search to ground your analysis in current real-world trade policies,
  tariff schedules, or recent news about the scenario.
"""

    try:
        data = await ask_simulation(prompt)
    except Exception:
        log.exception("Backboard simulation call failed – falling back to stubs")
        return _fallback_simulation(job_id, chain, scenario)

    impacts: list[NodeImpact] = []
    for i in data.get("impacts", []):
        try:
            impacts.append(
                NodeImpact(
                    node_id=i["node_id"],
                    impact_description=i.get("impact_description", ""),
                    cost_change_pct=float(i.get("cost_change_pct", 0)),
                    severity=i.get("severity", "medium"),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    recommendations: list[Recommendation] = []
    for r in data.get("recommendations", []):
        try:
            recommendations.append(
                Recommendation(
                    title=r.get("title", ""),
                    description=r.get("description", ""),
                    priority=r.get("priority", "medium"),
                    type=r.get("type", "mitigate"),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    total_impact = float(data.get("total_cost_impact_pct", 0))

    summary = data.get(
        "summary",
        f"Scenario '{scenario.description}' would affect "
        f"{len(impacts)} node(s).",
    )

    return SimulationResult(
        job_id=job_id,
        scenario=scenario,
        impacts=impacts,
        recommendations=recommendations,
        total_cost_impact_pct=total_impact,
        summary=summary,
    )


# ── Fallback (used when API is unreachable) ──────────────────────────


def _fallback_simulation(
    job_id: str,
    chain: SupplyChainData,
    scenario: SimulationScenario,
) -> SimulationResult:
    """Simple country-matching fallback."""
    impacts: list[NodeImpact] = []
    affected = {c.lower() for c in scenario.affected_countries}

    for node in chain.nodes:
        if node.country.lower() in affected:
            impacts.append(
                NodeImpact(
                    node_id=node.id,
                    impact_description=(
                        f"{node.material} from {node.country} affected by: "
                        f"{scenario.description}"
                    ),
                    cost_change_pct=scenario.tariff_change_pct or 10.0,
                    severity="high" if (scenario.tariff_change_pct or 10) > 20 else "medium",
                )
            )

    total = sum(i.cost_change_pct for i in impacts) / max(len(chain.nodes), 1)

    return SimulationResult(
        job_id=job_id,
        scenario=scenario,
        impacts=impacts,
        recommendations=[
            Recommendation(
                title="Diversify sourcing",
                description="Consider alternative suppliers in unaffected regions to reduce exposure.",
                priority="high",
                type="mitigate",
            ),
        ],
        total_cost_impact_pct=round(total, 1),
        summary=(
            f"[Fallback] Scenario '{scenario.description}' would affect "
            f"{len(impacts)} node(s). LLM was unavailable."
        ),
    )
