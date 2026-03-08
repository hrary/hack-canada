"""Backboard client – thin wrapper around the Backboard SDK.

Creates specialised assistants (analysis, simulation, parser) once at
startup and re-uses them across requests.  Each request gets its own
thread so conversations don't bleed into each other.

The *analysis* assistant has a ``web_search`` tool so it can research
specific named suppliers rather than generalising.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from functools import lru_cache
from html import unescape
from urllib.parse import quote_plus

import httpx
from backboard import BackboardClient

from ..config import get_settings

log = logging.getLogger(__name__)

# ── Default model used for all LLM calls ─────────────────────────────
LLM_PROVIDER = "openai"
LLM_MODEL = "gpt-4o"

# ── Web search implementation ────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")


async def _web_search(query: str, max_results: int = 6) -> str:
    """Run *query* through DuckDuckGo HTML and return a plain-text digest.

    No API key required.  Returns up to *max_results* snippet blocks.
    """
    url = "https://html.duckduckgo.com/html/"
    async with httpx.AsyncClient(
        headers={"User-Agent": "Provenance/1.0 (supply-chain research)"},
        follow_redirects=True,
        timeout=15,
    ) as client:
        resp = await client.post(url, data={"q": query})
        resp.raise_for_status()

    html = resp.text
    # Pull out result blocks – each sits inside <a class="result__a"> + <a class="result__snippet">
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
    urls = re.findall(r'class="result__url"[^>]*>(.*?)</a>', html, re.S)

    results: list[str] = []
    for i in range(min(max_results, len(titles))):
        t = unescape(_TAG_RE.sub("", titles[i])).strip()
        s = unescape(_TAG_RE.sub("", snippets[i])).strip() if i < len(snippets) else ""
        u = unescape(_TAG_RE.sub("", urls[i])).strip() if i < len(urls) else ""
        results.append(f"[{i+1}] {t}\n    {u}\n    {s}")

    if not results:
        return "(No results found)"

    return "\n\n".join(results)


# ── Tool definitions given to Backboard assistants ───────────────────

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for information about a specific company, "
            "supplier, or product.  Use this to find out where a named "
            "supplier actually sources their materials / sub-components."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query, e.g. "
                        "'Foxconn iPhone sub-component suppliers' or "
                        "'where does TSMC source silicon wafers'"
                    ),
                }
            },
            "required": ["query"],
        },
    },
}

# Map of tool name → async handler
TOOL_HANDLERS = {
    "web_search": _web_search,
}

# ── System prompts ────────────────────────────────────────────────────

ANALYSIS_RESEARCH_PROMPT = """\
You are a supply-chain intelligence analyst with access to a web_search tool.

When the user gives you a list of supply-chain nodes (each with a named
supplier, material, and country), you MUST:

**Supplier-Specific Sub-Component Research** – For EACH node, use the
web_search tool to research the **specific named supplier company** and find
out where THEY actually source their sub-components or raw materials.
Do NOT generalise about where materials "typically" come from — research the
actual company.  For example, if the user says they get axles from "Joe's
Axles Inc.", search for "Joe's Axles Inc. suppliers" or "Joe's Axles Inc.
sub-component sourcing" to find real information.

Because the nodes represent MANUFACTURED or ASSEMBLED products, each supplier
will have MANY sub-components.  You MUST discover at least 4-5 sub-components
per supplier (and ideally 5-8).  Think about every physical part, chip, board,
casing, chemical, raw material, etc. that goes into the finished product.

Only go one level deep — do NOT research sub-sub-components.

IMPORTANT: Always call web_search at least once per supplier node to ground
your analysis in real data about that specific company.

Always respond with valid JSON matching the schema provided in the user message.
Do NOT include markdown fences or commentary outside the JSON object.
"""

ANALYSIS_RISK_PROMPT = """\
You are a supply-chain risk analyst.  You are given:
1. A list of primary supply-chain nodes.
2. The results of supplier-specific research showing where each supplier
   actually sources their sub-components.

Using this research, perform:

1. **Risk / Weakness Identification** – Evaluate each node (and its discovered
   sub-components) for:
   • Tariff exposure (current & proposed)
   • Geopolitical risk (sanctions, instability)
   • Single-source / concentration risk
   • Logistics fragility (port bottlenecks, distance)
   Rate severity as low / medium / high / critical.

2. **Alternative Sourcing** – For every medium+ risk, suggest at least one
   alternative supplier or country with estimated savings.

Always respond with valid JSON matching the schema provided in the user message.
Do NOT include markdown fences or commentary outside the JSON object.
"""

SIMULATION_SYSTEM_PROMPT = """\
You are a supply-chain scenario modeller with access to a web_search tool.

Given a set of supply chain nodes (with USD values), their sub-component
sourcing data, and a hypothetical event (tariff, trade deal, embargo, natural
disaster, pandemic, regulatory change, etc.), you MUST:

1. **Use web_search** to look up the latest relevant information about the
   scenario (e.g. current tariff rates, trade policies, recent news).  This
   grounds your analysis in real-world data.

2. **Holistic cost-impact analysis** for each affected node:
   a) Determine which sub-components and input materials are directly touched
      by the event.
   b) Estimate what FRACTION of that node's total BOM (bill of materials) cost
      comes from the affected sources.  A 25% tariff on Chinese imports does
      NOT mean the product gets 25% more expensive — if only 40% of the BOM
      is sourced from the affected region, the direct cost pass-through is
      roughly 40% × 25% = 10%.
   c) Factor in real-world dynamics:
      • Supplier margin absorption (large suppliers often eat 20-40% of a
        tariff increase to stay competitive)
      • Currency fluctuations triggered by the event
      • Demand elasticity effects (higher prices → lower volume)
      • Substitution effects (buyers switching to alternative sources)
      • Inventory buffers and existing forward contracts
      • Logistics and compliance overhead
   d) Combine these into a realistic **net cost change percentage** for each
      node.  Be specific about the calculation chain.
   e) Rate severity as low (< 3%), medium (3-8%), high (8-15%), critical (> 15%).

3. **Second-order / cascading effects** — Consider knock-on impacts:
   • If a key sub-component gets scarce, what happens to the parent node's
     lead times and reliability?
   • Are there nodes that BENEFIT from the event (e.g. competitors in
     unaffected regions becoming more attractive)?
   • Currency or commodity price movements that affect the whole chain.

4. **Recommend proactive steps** — provide 3-6 actionable recommendations:
   • Mitigation steps to reduce negative impacts.
   • Opportunities the company could seize because of the event.
   Each recommendation should have a title, description, priority
   (high/medium/low), and type ("mitigate" or "opportunity").

5. **Total cost impact** — compute a WEIGHTED-AVERAGE cost impact across
   the entire supply chain, where each node's weight is its value_usd
   relative to the total.  NOT a simple average or a pass-through of the
   headline tariff number.

Always respond with valid JSON matching the schema provided in the user message.
Do NOT include markdown fences or commentary outside the JSON object.
"""

PARSER_SYSTEM_PROMPT = """\
You are a supply-chain data extractor.  The user will give you unstructured
text (an article, email, report, etc.) that describes a company's supply chain.
Extract every supply-chain node you can find.

For each node output:
  name, lat, lng, material, supplier, country, hs_code

Use realistic latitude/longitude for the location described.  If unsure of
exact coords, use the centroid of the city, state, or country mentioned.

For hs_code: infer the most likely 4-6 digit Harmonized System (HS) code for
the material or product described.  Use the standard international HS
classification (e.g. "7214.10" for steel bars, "8542.31" for processors,
"5201.00" for raw cotton).  If you are unsure, provide your best guess —
a 4-digit heading is acceptable.

Always respond with valid JSON matching the schema provided in the user message.
Do NOT include markdown fences or commentary outside the JSON object.
"""


# ── Singleton assistants (created lazily) ────────────────────────────

_client: BackboardClient | None = None
_assistant_ids: dict[str, str] = {}

# Which roles get tool access
_ROLE_TOOLS: dict[str, list[dict]] = {
    "analysis_research": [WEB_SEARCH_TOOL],
    "simulation": [WEB_SEARCH_TOOL],
}


def _get_client() -> BackboardClient:
    """Return a singleton BackboardClient, creating it on first call."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.blackboard_api_key:
            raise RuntimeError(
                "BLACKBOARD_API_KEY is not set.  "
                "Add it to backend/.env and restart the server."
            )
        _client = BackboardClient(api_key=settings.blackboard_api_key)
    return _client


async def _ensure_assistant(role: str, system_prompt: str) -> str:
    """Return the assistant_id for *role*, creating it if needed."""
    if role in _assistant_ids:
        return _assistant_ids[role]

    client = _get_client()
    tools = _ROLE_TOOLS.get(role)
    kwargs: dict = dict(
        name=f"Provenance – {role}",
        system_prompt=system_prompt,
    )
    if tools:
        kwargs["tools"] = tools

    assistant = await client.create_assistant(**kwargs)
    _assistant_ids[role] = assistant.assistant_id
    log.info("Created Backboard assistant %s → %s", role, assistant.assistant_id)
    return assistant.assistant_id


# ── Public helpers ────────────────────────────────────────────────────


async def ask_analysis_research(user_message: str) -> dict:
    """Phase 1 – supplier-specific sub-component research."""
    return await _ask("analysis_research", ANALYSIS_RESEARCH_PROMPT, user_message)


async def ask_analysis_risk(user_message: str) -> dict:
    """Phase 2 – risk scoring & alternative sourcing using research data."""
    return await _ask("analysis_risk", ANALYSIS_RISK_PROMPT, user_message)


async def ask_simulation(user_message: str) -> dict:
    """Send *user_message* to the simulation assistant and return parsed JSON."""
    return await _ask("simulation", SIMULATION_SYSTEM_PROMPT, user_message)


async def ask_parser(user_message: str) -> dict:
    """Send *user_message* to the parser assistant and return parsed JSON."""
    return await _ask("parser", PARSER_SYSTEM_PROMPT, user_message)


async def _ask(role: str, system_prompt: str, user_message: str) -> dict:
    """Core helper: ensure assistant, create thread, send message, parse JSON.

    If the assistant has tools, this handles the REQUIRES_ACTION loop —
    executing tool calls locally and submitting results back until the
    assistant produces a final text response.
    """
    client = _get_client()
    assistant_id = await _ensure_assistant(role, system_prompt)

    # Each call gets its own thread (no cross-contamination)
    thread = await client.create_thread(assistant_id)

    response = await client.add_message(
        thread_id=thread.thread_id,
        content=user_message,
        llm_provider=LLM_PROVIDER,
        model_name=LLM_MODEL,
        stream=False,
    )

    # ── Tool-call loop (max 25 rounds; tool calls within a round run in parallel) ────
    MAX_TOOL_ROUNDS = 25
    for _round in range(MAX_TOOL_ROUNDS):
        if not (
            getattr(response, "status", None) == "REQUIRES_ACTION"
            and getattr(response, "tool_calls", None)
        ):
            break

        # Execute all tool calls in this round concurrently
        async def _exec_tool(tc, round_num=_round):  # noqa: E306
            fn_name = tc.function.name
            args = tc.function.parsed_arguments or {}
            handler = TOOL_HANDLERS.get(fn_name)
            if handler:
                log.info("Tool call [round %d]: %s(%s)", round_num + 1, fn_name, args)
                try:
                    result = await handler(**args)
                except Exception as exc:
                    log.warning("Tool %s failed: %s", fn_name, exc)
                    result = f"(Error: {exc})"
            else:
                result = f"(Unknown tool: {fn_name})"
            return {"tool_call_id": tc.id, "output": str(result)}

        tool_outputs = await asyncio.gather(
            *[_exec_tool(tc) for tc in response.tool_calls]
        )

        response = await client.submit_tool_outputs(
            thread_id=thread.thread_id,
            run_id=response.run_id,
            tool_outputs=list(tool_outputs),
        )

    # If the model still wants to call tools after MAX_TOOL_ROUNDS,
    # submit "limit reached" outputs so it completes on the SAME thread
    # (preserving all conversation context).
    WIND_DOWN_ROUNDS = 5
    for _ in range(WIND_DOWN_ROUNDS):
        if not (
            getattr(response, "status", None) == "REQUIRES_ACTION"
            and getattr(response, "tool_calls", None)
        ):
            break
        log.warning(
            "Tool-call loop exhausted for role=%s; winding down (%d pending tool calls).",
            role, len(response.tool_calls),
        )
        wind_outputs = [
            {
                "tool_call_id": tc.id,
                "output": (
                    "(SEARCH LIMIT REACHED — do NOT request any more tool calls. "
                    "Return your complete JSON response now with all the data "
                    "you have collected so far.)"
                ),
            }
            for tc in response.tool_calls
        ]
        response = await client.submit_tool_outputs(
            thread_id=thread.thread_id,
            run_id=response.run_id,
            tool_outputs=wind_outputs,
        )

    raw = (getattr(response, "content", None) or "").strip()

    # Strip markdown code fences if the model wraps anyway
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract a JSON object embedded in prose text
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Last resort: ask the same assistant to fix its output
        log.warning("Non-JSON response for role=%s, requesting JSON fix", role)
        try:
            fix_thread = await client.create_thread(assistant_id)
            fix_response = await client.add_message(
                thread_id=fix_thread.thread_id,
                content=(
                    "Your previous response was not valid JSON. "
                    "Please re-read the instructions and return ONLY "
                    "the JSON object requested, with no other text.\n\n"
                    f"Your previous response was:\n{raw[:2000]}"
                ),
                llm_provider=LLM_PROVIDER,
                model_name=LLM_MODEL,
                stream=False,
            )
            fix_raw = fix_response.content.strip()
            if fix_raw.startswith("```"):
                fix_raw = fix_raw.split("\n", 1)[1] if "\n" in fix_raw else fix_raw[3:]
                if fix_raw.endswith("```"):
                    fix_raw = fix_raw[:-3]
                fix_raw = fix_raw.strip()
            return json.loads(fix_raw)
        except Exception:
            log.error("Backboard returned non-JSON for role=%s: %s", role, raw[:500])
            raise ValueError(f"LLM returned invalid JSON for {role}")
