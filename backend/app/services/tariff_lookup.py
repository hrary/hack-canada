"""Deterministic tariff lookup engine.

Queries the local SQLite tariff database — no LLM involved.
Provides:
  - lookup_tariff()       — single HS-code + country → TariffInfo
  - enrich_chain()        — batch-enrich every node in a SupplyChainData
  - material_to_hs_code() — keyword fallback when no HS code is provided
  - calculate_net_tariff() — net tariff % across a full supply chain
"""

from __future__ import annotations

import logging
import re

from ..db.database import get_connection
from ..models.schemas import SupplyChainData, TariffInfo

log = logging.getLogger(__name__)

# ── Country name → ISO 3166-1 alpha-2 ───────────────────────────────
# Covers the most common trading partners; case-insensitive lookup.

_COUNTRY_MAP: dict[str, str] = {
    "afghanistan": "AF", "albania": "AL", "algeria": "DZ", "argentina": "AR",
    "australia": "AU", "austria": "AT", "bangladesh": "BD", "belgium": "BE",
    "bolivia": "BO", "brazil": "BR", "cambodia": "KH", "cameroon": "CM",
    "canada": "CA", "chile": "CL", "china": "CN", "colombia": "CO",
    "congo": "CD", "costa rica": "CR", "croatia": "HR", "cuba": "CU",
    "czech republic": "CZ", "czechia": "CZ", "denmark": "DK",
    "dominican republic": "DO", "ecuador": "EC", "egypt": "EG",
    "el salvador": "SV", "ethiopia": "ET", "finland": "FI", "france": "FR",
    "germany": "DE", "ghana": "GH", "greece": "GR", "guatemala": "GT",
    "honduras": "HN", "hong kong": "HK", "hungary": "HU", "india": "IN",
    "indonesia": "ID", "iran": "IR", "iraq": "IQ", "ireland": "IE",
    "israel": "IL", "italy": "IT", "ivory coast": "CI", "jamaica": "JM",
    "japan": "JP", "jordan": "JO", "kazakhstan": "KZ", "kenya": "KE",
    "south korea": "KR", "korea": "KR", "kuwait": "KW", "laos": "LA",
    "latvia": "LV", "lebanon": "LB", "libya": "LY", "lithuania": "LT",
    "malaysia": "MY", "mexico": "MX", "mongolia": "MN", "morocco": "MA",
    "mozambique": "MZ", "myanmar": "MM", "nepal": "NP", "netherlands": "NL",
    "new zealand": "NZ", "nicaragua": "NI", "nigeria": "NG", "norway": "NO",
    "oman": "OM", "pakistan": "PK", "panama": "PA", "papua new guinea": "PG",
    "paraguay": "PY", "peru": "PE", "philippines": "PH", "poland": "PL",
    "portugal": "PT", "qatar": "QA", "romania": "RO", "russia": "RU",
    "saudi arabia": "SA", "senegal": "SN", "serbia": "RS", "singapore": "SG",
    "slovakia": "SK", "slovenia": "SI", "south africa": "ZA", "spain": "ES",
    "sri lanka": "LK", "sweden": "SE", "switzerland": "CH", "taiwan": "TW",
    "tanzania": "TZ", "thailand": "TH", "trinidad and tobago": "TT",
    "tunisia": "TN", "turkey": "TR", "turkiye": "TR", "uganda": "UG",
    "ukraine": "UA", "united arab emirates": "AE", "uae": "AE",
    "united kingdom": "GB", "uk": "GB", "united states": "US", "usa": "US",
    "us": "US", "uruguay": "UY", "uzbekistan": "UZ", "venezuela": "VE",
    "vietnam": "VN", "zambia": "ZM", "zimbabwe": "ZW",
}

CUSMA_COUNTRIES = {"US", "MX"}


def _normalise_country(country: str) -> str:
    """Best-effort conversion of a country name/code to ISO alpha-2."""
    cleaned = country.strip()
    if len(cleaned) == 2:
        return cleaned.upper()
    return _COUNTRY_MAP.get(cleaned.lower(), cleaned.upper()[:2])


# ── Keyword → HS code fallback ───────────────────────────────────────
# When neither the CSV nor the LLM provides an HS code, we try to infer
# one from the material description using simple keyword matching.

_MATERIAL_KEYWORDS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"semiconductor|chip|processor|cpu|gpu|soc|asic|fpga", re.I), "8542.31"),
    (re.compile(r"integrated circuit|\bic\b|microcontroller|mcu\b", re.I), "8542.31"),
    (re.compile(r"memory|dram|nand|flash|sram", re.I), "8542.32"),
    (re.compile(r"led\b|light.emitting.diode", re.I), "8541.41"),
    (re.compile(r"solar\s*(cell|panel|module)", re.I), "8541.40"),
    (re.compile(r"diode", re.I), "8541.10"),
    (re.compile(r"capacitor", re.I), "8532.24"),
    (re.compile(r"resistor", re.I), "8533.21"),
    (re.compile(r"printed.circuit|pcb", re.I), "8534.00"),
    (re.compile(r"lithium.ion|li.ion|battery\s*cell|battery\s*pack", re.I), "8507.60"),
    (re.compile(r"lithium\s*(oxide|hydroxide|carbonate)", re.I), "2825.20"),
    (re.compile(r"lithium", re.I), "2825.20"),
    (re.compile(r"battery", re.I), "8506.50"),
    (re.compile(r"smartphone|mobile\s*phone|cellphone", re.I), "8517.12"),
    (re.compile(r"router|switch|network", re.I), "8517.62"),
    (re.compile(r"laptop|notebook\s*computer|portable\s*computer", re.I), "8471.30"),
    (re.compile(r"computer|server|workstation", re.I), "8471.49"),
    (re.compile(r"monitor|display\s*panel", re.I), "8528.52"),
    (re.compile(r"power\s*supply|inverter|converter", re.I), "8504.40"),
    (re.compile(r"electric\s*motor", re.I), "8501.40"),
    (re.compile(r"electric\s*vehicle|ev\b|bev\b", re.I), "8703.60"),
    (re.compile(r"hybrid\s*vehicle", re.I), "8703.40"),
    (re.compile(r"car|automobile|sedan|suv", re.I), "8703.23"),
    (re.compile(r"truck|lorry", re.I), "8704.21"),
    (re.compile(r"engine|motor\s*(gasoline|petrol)", re.I), "8407.34"),
    (re.compile(r"diesel\s*engine", re.I), "8408.20"),
    (re.compile(r"turbine\s*(jet|turbo)", re.I), "8411.12"),
    (re.compile(r"gas\s*turbine", re.I), "8411.82"),
    (re.compile(r"brake|braking", re.I), "8708.30"),
    (re.compile(r"gearbox|transmission", re.I), "8708.40"),
    (re.compile(r"axle|drive.?shaft", re.I), "8708.50"),
    (re.compile(r"bumper", re.I), "8708.10"),
    (re.compile(r"seat\s*belt", re.I), "8708.21"),
    (re.compile(r"radiator", re.I), "8708.91"),
    (re.compile(r"steering", re.I), "8708.94"),
    (re.compile(r"auto\s*part|vehicle\s*part|car\s*part", re.I), "8708.99"),
    (re.compile(r"tyre|tire", re.I), "4011.10"),
    (re.compile(r"bearing|ball.bearing", re.I), "8482.10"),
    (re.compile(r"stainless\s*steel", re.I), "7219.34"),
    (re.compile(r"steel\s*(alloy|bar|rod|beam|coil|plate|sheet|pipe|tube|rebar|wire)", re.I), "7214.10"),
    (re.compile(r"steel", re.I), "7207.11"),
    (re.compile(r"iron\s*(ore|concentrate)", re.I), "2601.11"),
    (re.compile(r"iron|pig\s*iron", re.I), "7201.10"),
    (re.compile(r"copper\s*(ore|concentrate)", re.I), "2603.00"),
    (re.compile(r"copper\s*(wire|cable)", re.I), "7408.11"),
    (re.compile(r"copper\s*(cathode|refined)", re.I), "7403.11"),
    (re.compile(r"copper", re.I), "7403.11"),
    (re.compile(r"alumin(i?)um\s*(foil|sheet|plate)", re.I), "7606.11"),
    (re.compile(r"alumin(i?)um\s*(bar|rod|profile|extrusion)", re.I), "7604.10"),
    (re.compile(r"alumin(i?)um", re.I), "7601.10"),
    (re.compile(r"nickel\s*ore", re.I), "2604.00"),
    (re.compile(r"zinc", re.I), "7901.11"),
    (re.compile(r"tin\b", re.I), "8001.10"),
    (re.compile(r"titanium", re.I), "8108.20"),
    (re.compile(r"tungsten", re.I), "8101.10"),
    (re.compile(r"magnesium", re.I), "8104.11"),
    (re.compile(r"rare\s*earth", re.I), "2846.90"),
    (re.compile(r"uranium", re.I), "2612.10"),
    (re.compile(r"crude\s*(oil|petroleum)", re.I), "2709.00"),
    (re.compile(r"natural\s*gas|lng\b", re.I), "2711.11"),
    (re.compile(r"coal\b", re.I), "2701.12"),
    (re.compile(r"gasoline|petrol\b", re.I), "2710.12"),
    (re.compile(r"diesel\s*fuel", re.I), "2710.19"),
    (re.compile(r"cotton\s*yarn", re.I), "5205.11"),
    (re.compile(r"raw\s*cotton|cotton\s*fibre", re.I), "5201.00"),
    (re.compile(r"cotton\s*fabric|cotton\s*textile", re.I), "5208.12"),
    (re.compile(r"denim", re.I), "5209.42"),
    (re.compile(r"polyester\s*(yarn|fibre|fabric)", re.I), "5402.33"),
    (re.compile(r"nylon|polyamide", re.I), "3908.10"),
    (re.compile(r"textile|fabric|cloth", re.I), "5407.61"),
    (re.compile(r"t-shirt|tee.shirt", re.I), "6109.10"),
    (re.compile(r"jersey|pullover|sweater", re.I), "6110.20"),
    (re.compile(r"trouser|pant|jeans", re.I), "6203.42"),
    (re.compile(r"dress\b", re.I), "6104.43"),
    (re.compile(r"shoe|footwear|sneaker|boot", re.I), "6404.11"),
    (re.compile(r"rubber\b", re.I), "4001.22"),
    (re.compile(r"plastic\s*(bottle|container|packaging)", re.I), "3923.30"),
    (re.compile(r"polyethylene|pe\b|hdpe|ldpe", re.I), "3901.10"),
    (re.compile(r"polypropylene|pp\b", re.I), "3902.10"),
    (re.compile(r"pvc|poly.?vinyl", re.I), "3904.10"),
    (re.compile(r"pet\b|polyester\s*resin", re.I), "3907.61"),
    (re.compile(r"plastic", re.I), "3926.90"),
    (re.compile(r"plywood", re.I), "4412.31"),
    (re.compile(r"lumber|timber|wood", re.I), "4407.11"),
    (re.compile(r"paper|cardboard|carton", re.I), "4819.10"),
    (re.compile(r"glass\s*(fibre|fiber)", re.I), "7019.39"),
    (re.compile(r"glass\b", re.I), "7005.10"),
    (re.compile(r"cement\b", re.I), "2523.29"),
    (re.compile(r"fertiliz", re.I), "3105.20"),
    (re.compile(r"ammonia", re.I), "2814.10"),
    (re.compile(r"silicon\s*wafer|silicon\b", re.I), "2804.61"),
    (re.compile(r"optical\s*fibre|optical\s*fiber", re.I), "9001.10"),
    (re.compile(r"medical\s*device|surgical", re.I), "9018.90"),
    (re.compile(r"x-ray|x.ray", re.I), "9022.14"),
    (re.compile(r"sensor|instrument|gauge", re.I), "9031.80"),
    (re.compile(r"furniture|chair|desk|table|cabinet", re.I), "9403.20"),
    (re.compile(r"mattress", re.I), "9404.21"),
    (re.compile(r"toy\b|game\b", re.I), "9503.00"),
    (re.compile(r"aircraft|airplane|aeroplane", re.I), "8802.40"),
    (re.compile(r"ship|vessel|boat", re.I), "8901.90"),
    (re.compile(r"robot|robotic\s*arm|industrial\s*robot", re.I), "8479.89"),
    (re.compile(r"precision\s*part|machined\s*part|cnc\s*part", re.I), "8479.89"),
]


def material_to_hs_code(material: str) -> str | None:
    """Best-effort HS code from a material description (keyword matching)."""
    if not material:
        return None
    for pattern, code in _MATERIAL_KEYWORDS:
        if pattern.search(material):
            return code
    return None


# ── Core lookup ──────────────────────────────────────────────────────


def lookup_tariff(hs_code: str, country: str) -> TariffInfo | None:
    """Look up tariff for a given HS code and origin country.

    Tries an exact match first, then falls back to the 4-digit heading.
    Returns None only if the HS code is completely unknown.
    """
    if not hs_code:
        return None

    cc = _normalise_country(country)
    conn = get_connection()
    try:
        row = _find_hs_row(conn, hs_code)
        if row is None:
            return None

        mfn = row["mfn_rate"]
        cusma_rate = row["cusma_rate"]
        cusma_eligible = bool(row["cusma_eligible"])
        description = row["description"]
        matched_code = row["hs_code"]

        override_row = conn.execute(
            "SELECT tariff_rate, notes FROM country_tariffs "
            "WHERE hs_code = ? AND country_code = ?",
            (matched_code, cc),
        ).fetchone()

        country_override = override_row is not None
        notes = override_row["notes"] if override_row else ""

        if cc in CUSMA_COUNTRIES and cusma_eligible:
            applied = cusma_rate
        elif country_override:
            applied = override_row["tariff_rate"]
        else:
            applied = mfn

        return TariffInfo(
            hs_code=matched_code,
            description=description,
            mfn_rate=mfn,
            applied_rate=applied,
            cusma_eligible=cusma_eligible,
            cusma_rate=cusma_rate,
            country_override=country_override,
            notes=notes,
        )
    finally:
        conn.close()


def _find_hs_row(conn, hs_code: str):
    """Try exact match, then 4-digit heading prefix."""
    row = conn.execute(
        "SELECT * FROM hs_codes WHERE hs_code = ?", (hs_code,)
    ).fetchone()
    if row:
        return row

    prefix = hs_code.replace(".", "")[:4]
    if len(prefix) >= 4:
        row = conn.execute(
            "SELECT * FROM hs_codes WHERE hs_code LIKE ? ORDER BY hs_code LIMIT 1",
            (f"{prefix[:2]}{prefix[2:4]}%",),
        ).fetchone()
    return row


# ── Batch enrichment ─────────────────────────────────────────────────


def enrich_chain(chain: SupplyChainData) -> SupplyChainData:
    """Attach deterministic tariff data to every node in the chain."""
    for node in chain.nodes:
        hs = node.hs_code or material_to_hs_code(node.material)
        if not hs:
            continue

        info = lookup_tariff(hs, node.country)
        if info is None:
            if not node.hs_code and hs:
                node.hs_code = hs
            continue

        cc = _normalise_country(node.country)
        node.hs_code = info.hs_code
        node.tariff_rate = info.applied_rate
        node.cusma_eligible = info.cusma_eligible and cc in CUSMA_COUNTRIES
        node.cusma_rate = info.cusma_rate if node.cusma_eligible else None
        node.tariff_cost_delta = info.applied_rate

    return chain


# ── FTA / preferential tariff groupings ──────────────────────────────
# Based on the 2026 Canada Customs Tariff schedule.
# When a country belongs to an FTA, most manufactured goods enter
# Canada duty-free.  Agricultural TRQ items are the main exception.

# Chapters where FTA preferential rates are nearly always Free (0%).
# Chapters 25-97 cover minerals, chemicals, plastics, metals,
# machinery, electronics, vehicles, instruments, etc.
_FTA_FREE_CHAPTERS = set(range(25, 98))

# Key FTA country groups and their tariff treatment codes
_FTA_GROUPS: dict[str, set[str]] = {
    "CUSMA":  {"US", "MX"},
    "CPTPP":  {"JP", "AU", "NZ", "SG", "VN", "MY", "PE", "CL", "BN", "MX"},
    "CETA":   {  # EU-27
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR",
        "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL",
        "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    },
    "CUKTCA": {"GB"},
    "CKFTA":  {"KR"},
    "CIFTA":  {"IL"},
    "CCRFTA": {"CR"},
    "CCOFTA": {"CO"},
    "CPAFTA": {"PA"},
    "CHFTA":  {"HN"},
    "EFTA":   {"CH", "LI", "NO", "IS"},
}

# GPT (General Preferential Tariff) — developing countries get reduced rates.
# In the 2026 schedule, GPT rate is typically 0% or a small fraction of MFN.
# We conservatively estimate GPT = max(MFN * 0.5, 0) for non-free items.
_GPT_COUNTRIES: set[str] = {
    "IN", "BD", "PK", "LK", "PH", "ID", "TH", "EG", "NG", "GH",
    "KE", "TZ", "UG", "SN", "CM", "CI", "MZ", "TN", "MA", "DZ",
    "JO", "ZA", "BO", "EC", "PY", "UY", "GT", "SV", "NI", "DO",
    "JM", "TT", "GY", "KH", "MM", "LA", "MN", "UZ", "KZ", "UA",
    "GE", "MD",
}

# LDCT (Least Developed Country Tariff) — always Free
_LDCT_COUNTRIES: set[str] = {
    "BD", "KH", "MM", "LA", "NP", "AF", "ET", "MZ", "TZ", "UG",
    "RW", "MG", "MW", "ZM", "SN", "ML", "NE", "BF", "TD", "CD",
    "SO", "SD", "SS", "ER", "DJ", "HT", "SL", "LR", "GW", "GM",
    "TG", "BJ", "CF", "BI", "LS", "SB", "VU", "TL", "KI", "TV",
    "ST", "MR", "YE",
}


def _get_preferential_rate(mfn_rate: float, hs_code: str, country_code: str) -> float:
    """Determine the best preferential tariff rate for a country.

    Returns the applied rate (percentage points).  Falls back to MFN
    if no preferential treatment applies.
    """
    if mfn_rate == 0:
        return 0.0

    # Chapter from the first 2 digits of HS code
    try:
        chapter = int(hs_code.replace(".", "")[:2])
    except (ValueError, IndexError):
        return mfn_rate

    # LDCT countries → always Free
    if country_code in _LDCT_COUNTRIES:
        return 0.0

    # FTA partners → Free for manufactured goods (chapters 25-97)
    if chapter in _FTA_FREE_CHAPTERS:
        for _group_name, members in _FTA_GROUPS.items():
            if country_code in members:
                return 0.0

    # GPT countries → typically ~50% of MFN for non-free items
    if country_code in _GPT_COUNTRIES:
        return round(mfn_rate * 0.65, 2)  # conservative estimate

    return mfn_rate


def calculate_net_tariff(chain: SupplyChainData) -> dict:
    """Calculate the net tariff cost percentage across a full supply chain.

    Returns a dict with:
        - nodes: per-node breakdown
        - total_goods_value: sum of all node values
        - total_tariff_cost: sum of tariff costs
        - net_tariff_pct: weighted-average tariff rate
        - summary: human-readable summary
    """
    conn = get_connection()
    node_results: list[dict] = []
    total_value = 0.0
    total_tariff_cost = 0.0

    try:
        for node in chain.nodes:
            hs = node.hs_code or material_to_hs_code(node.material)
            value = node.value if node.value and node.value > 0 else 0.0
            total_value += value

            if not hs:
                node_results.append({
                    "node_id": node.id,
                    "name": node.name,
                    "country": node.country,
                    "material": node.material,
                    "hs_code": None,
                    "value": value,
                    "mfn_rate": None,
                    "applied_rate": None,
                    "tariff_cost": 0.0,
                    "rate_type": "unknown",
                    "notes": "No HS code could be determined",
                })
                continue

            cc = _normalise_country(node.country)
            row = _find_hs_row(conn, hs)

            if row is None:
                node_results.append({
                    "node_id": node.id,
                    "name": node.name,
                    "country": node.country,
                    "material": node.material,
                    "hs_code": hs,
                    "value": value,
                    "mfn_rate": None,
                    "applied_rate": None,
                    "tariff_cost": 0.0,
                    "rate_type": "not_found",
                    "notes": f"HS code {hs} not in database",
                })
                continue

            mfn = row["mfn_rate"]
            cusma_rate = row["cusma_rate"]
            cusma_eligible = bool(row["cusma_eligible"])
            matched_code = row["hs_code"]
            description = row["description"]

            # Check for country-specific override first (e.g. Chinese surtax)
            override_row = conn.execute(
                "SELECT tariff_rate, notes FROM country_tariffs "
                "WHERE hs_code = ? AND country_code = ?",
                (matched_code, cc),
            ).fetchone()

            if override_row:
                applied = override_row["tariff_rate"]
                rate_type = "country_override"
                notes = override_row["notes"]
            elif cc in CUSMA_COUNTRIES and cusma_eligible:
                applied = cusma_rate
                rate_type = "cusma"
                notes = f"CUSMA preferential rate ({cc})"
            else:
                # Try FTA/GPT preferential rates
                pref_rate = _get_preferential_rate(mfn, matched_code, cc)
                if pref_rate < mfn:
                    applied = pref_rate
                    # Determine which FTA
                    if cc in _LDCT_COUNTRIES:
                        rate_type = "ldct"
                        notes = "Least Developed Country Tariff (Free)"
                    elif cc in _GPT_COUNTRIES:
                        rate_type = "gpt"
                        notes = "General Preferential Tariff (~65% of MFN)"
                    else:
                        fta_name = "FTA"
                        for gname, members in _FTA_GROUPS.items():
                            if cc in members:
                                fta_name = gname
                                break
                        rate_type = fta_name.lower()
                        notes = f"{fta_name} preferential rate (Free)"
                else:
                    applied = mfn
                    rate_type = "mfn"
                    notes = "Most Favoured Nation rate"

            tariff_cost = value * applied / 100.0
            total_tariff_cost += tariff_cost

            node_results.append({
                "node_id": node.id,
                "name": node.name,
                "country": node.country,
                "material": node.material,
                "hs_code": matched_code,
                "description": description,
                "value": value,
                "mfn_rate": mfn,
                "applied_rate": applied,
                "tariff_cost": round(tariff_cost, 2),
                "rate_type": rate_type,
                "notes": notes,
            })
    finally:
        conn.close()

    if total_value > 0:
        net_pct = round(total_tariff_cost / total_value * 100, 2)
    else:
        # No dollar values available — use equal-weighted average of applied rates
        known_rates = [n["applied_rate"] for n in node_results if n.get("applied_rate") is not None]
        net_pct = round(sum(known_rates) / len(known_rates), 2) if known_rates else 0.0

    # Build summary
    fta_nodes = sum(1 for n in node_results if n.get("rate_type") not in ("mfn", "unknown", "not_found", "country_override"))
    override_nodes = sum(1 for n in node_results if n.get("rate_type") == "country_override")
    mfn_nodes = sum(1 for n in node_results if n.get("rate_type") == "mfn")

    summary_parts = [
        f"Net tariff impact: {net_pct}% on ${total_value:,.0f} total goods value",
        f"(${total_tariff_cost:,.0f} in tariff costs).",
    ]
    if fta_nodes:
        summary_parts.append(f"{fta_nodes} node(s) benefit from preferential/FTA rates.")
    if override_nodes:
        summary_parts.append(f"{override_nodes} node(s) subject to country-specific surtaxes.")
    if mfn_nodes:
        summary_parts.append(f"{mfn_nodes} node(s) at standard MFN rates.")

    return {
        "nodes": node_results,
        "total_goods_value": round(total_value, 2),
        "total_tariff_cost": round(total_tariff_cost, 2),
        "net_tariff_pct": net_pct,
        "summary": " ".join(summary_parts),
    }
