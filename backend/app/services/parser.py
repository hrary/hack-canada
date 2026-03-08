"""Parse raw supply-chain text/CSV into the standardised SupplyChainData model."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from uuid import uuid4

from ..models.schemas import SupplyChainData, SupplyNode, UploadFormat
from .backboard import ask_parser

log = logging.getLogger(__name__)

# Maximum seconds to wait for a single LLM parse / geocode call
_LLM_TIMEOUT = 90


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
    if fmt == UploadFormat.csv or _looks_like_csv(content):
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
      "country": "<country>",
      "value": <estimated monetary value in USD, or 0 if unknown>
    }}
  ]
}}

Use realistic coordinates. If no specific coordinates are mentioned, infer
the best location from the context: use the centre of the city mentioned,
or the company's known headquarters / factory location, or the centre of
the country as a last resort.
"""
    try:
        data = await asyncio.wait_for(ask_parser(prompt), timeout=_LLM_TIMEOUT)
    except asyncio.TimeoutError:
        log.error("Backboard parser timed out after %ss", _LLM_TIMEOUT)
        return SupplyChainData(nodes=[])
    except Exception:
        log.exception("Backboard parser call failed – returning empty chain")
        return SupplyChainData(nodes=[])

    nodes: list[SupplyNode] = []
    for n in data.get("nodes", []):
        try:
            value = float(n.get("value", 0) or 0)
        except (ValueError, TypeError):
            value = 0.0
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
                    value=value,
                )
            )
        except (KeyError, ValueError, TypeError):
            continue

    return SupplyChainData(nodes=nodes)


def _sync_parse_freetext(content: str) -> SupplyChainData:
    """Synchronous wrapper for the async parser (used as fallback)."""
    import asyncio
    return asyncio.run(_parse_freetext(content))


# ── CSV helpers ───────────────────────────────────────────────────────

_COORD_HEADERS = {'lat', 'lng', 'lon', 'latitude', 'longitude'}
_CSV_KEYWORDS = {'name', 'supplier', 'material', 'country', 'value', 'amount'}


def _looks_like_csv(content: str) -> bool:
    """Heuristic: does *content* look like comma-separated tabular data?"""
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return False
    first = lines[0].strip().lower()
    if ',' not in first:
        return False
    headers = {h.strip() for h in first.split(',')}
    return len(headers & (_CSV_KEYWORDS | _COORD_HEADERS)) >= 2


def _fix_csv_columns(content: str) -> str:
    """If the header has lat/lng columns but data rows have fewer columns,
    drop those columns from the header so DictReader aligns correctly."""
    lines = content.strip().split('\n')
    if len(lines) < 2:
        return content

    raw_headers = [h.strip() for h in lines[0].split(',')]
    norm_headers = [h.lower() for h in raw_headers]

    coord_cols = [i for i, h in enumerate(norm_headers) if h in _COORD_HEADERS]
    if not coord_cols:
        return content  # no coord columns, nothing to fix

    # Count data columns in the first non-empty data row
    first_data = None
    for line in lines[1:]:
        if line.strip():
            first_data = line
            break
    if first_data is None:
        return content

    data_col_count = len(first_data.split(','))
    header_col_count = len(raw_headers)

    if data_col_count >= header_col_count:
        return content  # columns already match, no fix needed

    # Check if removing coord columns makes it match
    kept = [h for i, h in enumerate(raw_headers) if i not in coord_cols]
    if len(kept) == data_col_count:
        new_header = ','.join(kept)
        return new_header + '\n' + '\n'.join(lines[1:])

    return content  # can't auto-fix, return as-is

def _parse_csv(content: str) -> SupplyChainData:
    """Parse CSV content into SupplyChainData.

    Coordinates (lat/lng) are optional — rows without them are still
    accepted and will be geocoded later by the LLM.

    Handles the common case where the header includes lat/lng columns
    but data rows omit those values (fewer columns than the header).
    """
    content = _fix_csv_columns(content)
    reader = csv.DictReader(io.StringIO(content))
    nodes: list[SupplyNode] = []

    for row in reader:
        # Normalise keys to lowercase; handle None from short/long rows
        row = {
            k.strip().lower(): (v.strip() if v else '')
            for k, v in row.items()
            if k is not None
        }

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
        data = await asyncio.wait_for(
            ask_parser(prompt), timeout=_LLM_TIMEOUT
        )
        loc_map = {
            loc["id"]: (float(loc["lat"]), float(loc["lng"]))
            for loc in data.get("locations", [])
            if "id" in loc and "lat" in loc and "lng" in loc
        }
        for n in chain.nodes:
            if n.id in loc_map:
                n.lat, n.lng = loc_map[n.id]
    except asyncio.TimeoutError:
        log.error("Geocoding LLM call timed out after %ss", _LLM_TIMEOUT)
    except Exception:
        log.exception("Geocoding via LLM failed – nodes will have 0,0 coords")

    return chain
