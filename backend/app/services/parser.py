"""Parse raw supply-chain text/CSV into the standardised SupplyChainData model."""

from __future__ import annotations

import csv
import io
import logging
from uuid import uuid4

from ..models.schemas import SupplyChainData, SupplyNode, UploadFormat
from .backboard import ask_parser

log = logging.getLogger(__name__)


def parse_supply_chain_text(
    content: str,
    fmt: UploadFormat,
) -> SupplyChainData:
    """Synchronous variant — for CSV returns immediately, for free-text
    spins up a temporary event loop to call the async LLM extractor."""
    if fmt == UploadFormat.csv:
        return _parse_csv(content)
    return _sync_parse_freetext(content)


async def parse_supply_chain_text_async(
    content: str,
    fmt: UploadFormat,
) -> SupplyChainData:
    """Async version – preferred when called from async FastAPI routes."""
    if fmt == UploadFormat.csv:
        return _parse_csv(content)
    return await _parse_freetext(content)


async def _parse_freetext(content: str) -> SupplyChainData:
    """Use Backboard LLM to extract supply-chain nodes from prose."""
    prompt = f"""\
Extract every supply-chain node from the following text.

TEXT:
\"\"\"
{content}
\"\"\"

Return a JSON object with this shape:
{{
  "nodes": [
    {{
      "name": "<node name or company>",
      "lat": <latitude>,
      "lng": <longitude>,
      "material": "<material or component>",
      "supplier": "<supplier company name>",
      "country": "<country>"
    }}
  ]
}}

Use realistic coordinates.  If only a country is mentioned, use the capital's coords.
"""
    try:
        data = await ask_parser(prompt)
    except Exception:
        log.exception("Backboard parser call failed – returning empty chain")
        return SupplyChainData(nodes=[])

    nodes: list[SupplyNode] = []
    for n in data.get("nodes", []):
        try:
            nodes.append(
                SupplyNode(
                    id=uuid4().hex[:12],
                    name=n.get("name", f"Node {len(nodes) + 1}"),
                    lat=float(n["lat"]),
                    lng=float(n["lng"]),
                    material=n.get("material", ""),
                    supplier=n.get("supplier", ""),
                    country=n.get("country", ""),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    return SupplyChainData(nodes=nodes)


def _sync_parse_freetext(content: str) -> SupplyChainData:
    """Synchronous wrapper for the async parser (used as fallback)."""
    import asyncio
    return asyncio.run(_parse_freetext(content))


def _parse_csv(content: str) -> SupplyChainData:
    reader = csv.DictReader(io.StringIO(content))
    nodes: list[SupplyNode] = []

    for row in reader:
        # Normalise keys to lowercase
        row = {k.strip().lower(): v.strip() for k, v in row.items()}
        try:
            lat = float(row.get("lat") or row.get("latitude") or "")
            lng = float(
                row.get("lng") or row.get("longitude") or row.get("lon") or ""
            )
        except (ValueError, TypeError):
            continue  # skip rows without valid coordinates

        try:
            value = float(row.get("value") or row.get("amount") or 0)
        except (ValueError, TypeError):
            value = 0.0

        nodes.append(
            SupplyNode(
                id=uuid4().hex[:12],
                name=row.get("name", f"Node {len(nodes) + 1}"),
                lat=lat,
                lng=lng,
                material=row.get("material", ""),
                supplier=row.get("supplier", ""),
                country=row.get("country", ""),
                value=value,
            )
        )

    return SupplyChainData(nodes=nodes)
