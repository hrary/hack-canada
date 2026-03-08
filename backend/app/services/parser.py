"""Parse raw supply-chain text/CSV into the standardised SupplyChainData model."""

from __future__ import annotations

import csv
import io
import logging
from uuid import uuid4

from ..models.schemas import SupplyChainData, SupplyNode, UploadFormat
from .backboard import ask_parser

log = logging.getLogger(__name__)

# ── Country → capital-city coordinates (fallback when CSV lacks lat/lng) ──

_COUNTRY_COORDS: dict[str, tuple[float, float]] = {
    "china": (39.9042, 116.4074),
    "united states": (38.9072, -77.0369),
    "usa": (38.9072, -77.0369),
    "us": (38.9072, -77.0369),
    "germany": (52.5200, 13.4050),
    "japan": (35.6762, 139.6503),
    "south korea": (37.5665, 126.9780),
    "korea": (37.5665, 126.9780),
    "taiwan": (25.0330, 121.5654),
    "india": (28.6139, 77.2090),
    "mexico": (19.4326, -99.1332),
    "canada": (45.4215, -75.6972),
    "united kingdom": (51.5074, -0.1278),
    "uk": (51.5074, -0.1278),
    "france": (48.8566, 2.3522),
    "italy": (41.9028, 12.4964),
    "brazil": (-15.7975, -47.8919),
    "australia": (-35.2809, 149.1300),
    "vietnam": (21.0285, 105.8542),
    "thailand": (13.7563, 100.5018),
    "malaysia": (3.1390, 101.6869),
    "indonesia": (-6.2088, 106.8456),
    "philippines": (14.5995, 120.9842),
    "singapore": (1.3521, 103.8198),
    "netherlands": (52.3676, 4.9041),
    "switzerland": (46.9480, 7.4474),
    "sweden": (59.3293, 18.0686),
    "spain": (40.4168, -3.7038),
    "poland": (52.2297, 21.0122),
    "turkey": (39.9334, 32.8597),
    "saudi arabia": (24.7136, 46.6753),
    "south africa": (-25.7479, 28.2293),
    "chile": (-33.4489, -70.6693),
    "argentina": (-34.6037, -58.3816),
    "colombia": (4.7110, -74.0721),
    "israel": (31.7683, 35.2137),
    "belgium": (50.8503, 4.3517),
    "austria": (48.2082, 16.3738),
    "czech republic": (50.0755, 14.4378),
    "ireland": (53.3498, -6.2603),
    "finland": (60.1699, 24.9384),
    "norway": (59.9139, 10.7522),
    "denmark": (55.6761, 12.5683),
    "portugal": (38.7223, -9.1393),
    "russia": (55.7558, 37.6173),
    "egypt": (30.0444, 31.2357),
    "bangladesh": (23.8103, 90.4125),
    "pakistan": (33.6844, 73.0479),
    "new zealand": (-41.2865, 174.7762),
    "hungary": (47.4979, 19.0402),
    "romania": (44.4268, 26.1025),
    "greece": (37.9838, 23.7275),
    "uae": (24.4539, 54.3773),
    "united arab emirates": (24.4539, 54.3773),
    "nigeria": (9.0765, 7.3986),
    "kenya": (-1.2921, 36.8219),
    "peru": (-12.0464, -77.0428),
    "costa rica": (9.9281, -84.0907),
}


def _geocode_country(country: str) -> tuple[float, float] | None:
    """Return (lat, lng) for a country name, or None if unknown."""
    return _COUNTRY_COORDS.get(country.strip().lower())


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
        result = _parse_csv(content)
        if result.nodes:
            return result
        # CSV produced 0 nodes (likely missing lat/lng columns).
        # Fall back to the LLM parser which can infer coordinates.
        log.warning("CSV parsing produced 0 nodes — falling back to LLM parser")
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
      "hs_code": "<4-6 digit HS code, e.g. 7214.10>"
    }}
  ]
}}

Use realistic coordinates.  If only a country is mentioned, use the capital's coords.
For hs_code, infer the best-fit Harmonized System code for the material described.
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
                    hs_code=n.get("hs_code", ""),
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

        # Try explicit lat/lng first, then geocode from country
        lat: float | None = None
        lng: float | None = None
        try:
            lat = float(row.get("lat") or row.get("latitude") or "")
            lng = float(
                row.get("lng") or row.get("longitude") or row.get("lon") or ""
            )
        except (ValueError, TypeError):
            # No valid coordinates — try geocoding from country
            country = row.get("country", "")
            coords = _geocode_country(country) if country else None
            if coords:
                lat, lng = coords
            else:
                continue  # skip rows without any location info

        try:
            value = float(row.get("value") or row.get("amount") or 0)
        except (ValueError, TypeError):
            value = 0.0

        nodes.append(
            SupplyNode(
                id=uuid4().hex[:12],
                name=row.get("name", row.get("part", row.get("component", f"Node {len(nodes) + 1}"))),
                lat=lat,
                lng=lng,
                material=row.get("material", row.get("description", row.get("part", ""))),
                supplier=row.get("supplier", row.get("manufacturer", row.get("vendor", ""))),
                country=row.get("country", ""),
                value=value,
                hs_code=row.get("hs_code", row.get("hscode", row.get("hs code", ""))),
            )
        )

    log.info("CSV parser: %d nodes parsed from %d data rows",
             len(nodes), reader.line_num - 1 if reader.line_num else 0)
    return SupplyChainData(nodes=nodes)
