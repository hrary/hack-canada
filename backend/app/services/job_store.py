"""Persistent job store backed by SQLite.

Stores parsed supply chains, analysis results, and simulation results
so they survive server restarts.
"""

from __future__ import annotations

from ..db.database import get_connection
from ..models.schemas import (
    AnalysisResult,
    SimulationResult,
    SupplyChainData,
    SupplierResearch,
)

# ── In-memory research store (used by simulation service) ────────────

research_store: dict[str, list[SupplierResearch]] = {}


def save_research(job_id: str, research: list[SupplierResearch]) -> None:
    research_store[job_id] = research


# ── Supply chain (jobs) ──────────────────────────────────────────────

def save_parsed_chain(job_id: str, chain: SupplyChainData) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO jobs (job_id, chain_json) VALUES (?, ?)",
            (job_id, chain.model_dump_json()),
        )
        conn.commit()
    finally:
        conn.close()


def get_parsed_chain(job_id: str) -> SupplyChainData | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT chain_json FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return SupplyChainData.model_validate_json(row["chain_json"])
    finally:
        conn.close()


# ── Analysis results ─────────────────────────────────────────────────

def save_analysis_result(job_id: str, result: AnalysisResult) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO analysis_results (job_id, result_json) VALUES (?, ?)",
            (job_id, result.model_dump_json()),
        )
        conn.commit()
    finally:
        conn.close()


def get_analysis_result(job_id: str) -> AnalysisResult | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT result_json FROM analysis_results WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return AnalysisResult.model_validate_json(row["result_json"])
    finally:
        conn.close()


# ── Simulation results ───────────────────────────────────────────────

def save_simulation_results(
    job_id: str, results: list[SimulationResult]
) -> None:
    conn = get_connection()
    try:
        conn.executemany(
            "INSERT INTO simulation_results (job_id, result_json) VALUES (?, ?)",
            [(job_id, r.model_dump_json()) for r in results],
        )
        conn.commit()
    finally:
        conn.close()


def get_simulation_results(job_id: str) -> list[SimulationResult]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT result_json FROM simulation_results WHERE job_id = ? ORDER BY id",
            (job_id,),
        ).fetchall()
        return [
            SimulationResult.model_validate_json(row["result_json"])
            for row in rows
        ]
    finally:
        conn.close()


# ── Job listing (for future history UI) ──────────────────────────────

def list_jobs() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT job_id, created_at FROM jobs ORDER BY created_at DESC"
        ).fetchall()
        return [{"job_id": r["job_id"], "created_at": r["created_at"]} for r in rows]
    finally:
        conn.close()
