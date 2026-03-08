"""Parse raw supply-chain text/CSV into the standardised SupplyChainData model."""

from __future__ import annotations

import csv
import io
import json
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
        chain = _parse_csv(content)
        # Sync can't geocode – return as-is; async path preferred
        return chain
    return _sync_parse_freetext(content)


async def parse_supply_chain_text_async(
    content: str,
    fmt: UploadFormat,
) -> SupplyChainData:
    """Async version – preferred when called from async FastAPI routes."""
    if fmt == UploadFormat.csv:
        chain = _parse_csv(content)
        # If any nodes lack coordinates, use LLM to infer them
        missing = [n for n in chain.nodes if n.lat == 0.0 and n.lng == 0.0]
        if missing:
            chain = await _geocode_chain(chain, content)
        return chain
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

Use realistic coordinates. If no specific coordinates are mentioned, infer
the best location from the context: use the centre of the city mentioned,
or the company's known headquarters / factory location, or the centre of
the country as a last resort.
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
                    lat=float(n.get("lat", 0)),
                    lng=float(n.get("lng", 0)),
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
    """Parse CSV content into SupplyChainData.

    Coordinates (lat/lng) are optional — rows without them are still
    accepted and will be geocoded later by the LLM.
    """
    reader = csv.DictReader(io.StringIO(content))
    nodes: list[SupplyNode] = []

    for row in reader:
        # Normalise keys to lowercase
        row = {k.strip().lower(): v.strip() for k, v in row.items()}

        # Try to extract coordinates (optional)
        try:
            lat = float(row.get("lat") or row.get("latitude") or "0")
        except (ValueError, TypeError):
            lat = 0.0
        try:
            lng = float(
                row.get("lng") or row.get("longitude") or row.get("lon") or "0"
            )
        except (ValueError, TypeError):
            lng = 0.0

        try:
            value = float(row.get("value") or row.get("amount") or 0)
        except (ValueError, TypeError):
            value = 0.0

        name = row.get("name", "").strip()
        supplier = row.get("supplier", "").strip()
        material = row.get("material", "").strip()
        country = row.get("country", "").strip()

        # Skip completely empty rows
        if not name and not supplier and not material:
            continue

        nodes.append(
            SupplyNode(
                id=uuid4().hex[:12],
                name=name or supplier or f"Node {len(nodes) + 1}",
                lat=lat,
                lng=lng,
                material=material,
                supplier=supplier,
                country=country,
                value=value,
            )
        )

    return SupplyChainData(nodes=nodes)


async def _geocode_chain(
    chain: SupplyChainData, raw_csv: str = ""
) -> SupplyChainData:
    """Use the LLM to infer coordinates for nodes missing lat/lng."""
    # Build a compact list of nodes that need geocoding
    to_geocode = []
    for n in chain.nodes:
        if n.lat == 0.0 and n.lng == 0.0:
            to_geocode.append({
                "id": n.id,
                "name": n.name,
                "supplier": n.supplier,
                "country": n.country,
                "material": n.material,
            })

    if not to_geocode:
        return chain

    prompt = f"""\
I have supply-chain nodes that are missing geographic coordinates.
For each node, determine the most likely latitude and longitude based on
the supplier name, country, and any other available context.

Use the centre of the city where the company's main factory or HQ is
located. If unsure, use the centre of the named country.

NODES NEEDING COORDINATES:
{json.dumps(to_geocode, indent=2)}

Return a JSON object:
{{
  "locations": [
    {{ "id": "<node id>", "lat": <latitude>, "lng": <longitude> }}
  ]
}}
"""
    try:
        data = await ask_parser(prompt)
        loc_map = {
            loc["id"]: (float(loc["lat"]), float(loc["lng"]))
            for loc in data.get("locations", [])
            if "id" in loc and "lat" in loc and "lng" in loc
        }
        for n in chain.nodes:
            if n.id in loc_map:
                n.lat, n.lng = loc_map[n.id]
    except Exception:
        log.exception("Geocoding via LLM failed – nodes will have 0,0 coords")

    return chain
