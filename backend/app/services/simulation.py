"""Simulation service – what-if scenario modelling.

Given an existing supply chain and a hypothetical change (new tariff,
trade deal, embargo, etc.), estimate the impact on each node.
"""

from __future__ import annotations

import json
import logging

from ..models.schemas import (
    SimulationResult,
    SimulationScenario,
    SupplyChainData,
    NodeImpact,
)
from .backboard import ask_simulation

log = logging.getLogger(__name__)


def _nodes_to_json(chain: SupplyChainData) -> str:
    return json.dumps(
        [
            {
                "id": n.id,
                "name": n.name,
                "material": n.material,
                "supplier": n.supplier,
                "country": n.country,
            }
            for n in chain.nodes
        ],
        indent=2,
    )


async def run_simulation(
    job_id: str,
    chain: SupplyChainData,
    scenario: SimulationScenario,
) -> SimulationResult:
    """Evaluate a single what-if scenario against the supply chain."""

    nodes_json = _nodes_to_json(chain)

    prompt = f"""\
Evaluate the following what-if scenario against the supply chain.

SUPPLY-CHAIN NODES:
{nodes_json}

SCENARIO:
  Description: {scenario.description}
  Affected countries: {', '.join(scenario.affected_countries) if scenario.affected_countries else 'infer from description'}
  Tariff change: {scenario.tariff_change_pct if scenario.tariff_change_pct is not None else 'infer from description'}%
  Trade deal: {scenario.trade_deal or 'N/A'}

Return a JSON object with exactly this shape:
{{
  "impacts": [
    {{
      "node_id": "<id of the affected node>",
      "impact_description": "<one-sentence explanation of the impact>",
      "cost_change_pct": <estimated percentage cost change, positive = more expensive>
    }}
  ],
  "summary": "<2-3 sentence summary of overall impact>"
}}

Only include nodes that would actually be affected.  Be specific about
mechanisms (tariff pass-through, supply disruption, shipping delays, etc.).
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
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    summary = data.get(
        "summary",
        f"Scenario '{scenario.description}' would affect "
        f"{len(impacts)} node(s).",
    )

    return SimulationResult(
        job_id=job_id,
        scenario=scenario,
        impacts=impacts,
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
                )
            )

    return SimulationResult(
        job_id=job_id,
        scenario=scenario,
        impacts=impacts,
        summary=(
            f"[Fallback] Scenario '{scenario.description}' would affect "
            f"{len(impacts)} node(s). LLM was unavailable."
        ),
    )
