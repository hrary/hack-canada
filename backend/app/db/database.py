"""SQLite database — schema creation and connection management.

Houses both the tariff reference tables and the persistent job store.
"""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "tariffs.db"

# ── Tariff reference tables ───────────────────────────────────────────

_CREATE_HS_CODES = """\
CREATE TABLE IF NOT EXISTS hs_codes (
    hs_code        TEXT PRIMARY KEY,
    description    TEXT NOT NULL,
    mfn_rate       REAL NOT NULL DEFAULT 0,
    cusma_rate     REAL NOT NULL DEFAULT 0,
    cusma_eligible INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_COUNTRY_TARIFFS = """\
CREATE TABLE IF NOT EXISTS country_tariffs (
    hs_code      TEXT NOT NULL,
    country_code TEXT NOT NULL,
    tariff_rate  REAL NOT NULL,
    notes        TEXT DEFAULT '',
    PRIMARY KEY (hs_code, country_code),
    FOREIGN KEY (hs_code) REFERENCES hs_codes(hs_code)
);
"""

# ── Persistent job store tables ───────────────────────────────────────

_CREATE_JOBS = """\
CREATE TABLE IF NOT EXISTS jobs (
    job_id      TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    chain_json  TEXT NOT NULL
);
"""

_CREATE_ANALYSIS_RESULTS = """\
CREATE TABLE IF NOT EXISTS analysis_results (
    job_id      TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    result_json TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
"""

_CREATE_SIMULATION_RESULTS = """\
CREATE TABLE IF NOT EXISTS simulation_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    result_json TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES jobs(job_id)
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a new connection to the database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables (if missing) and seed tariff reference data."""
    from .seed import seed_tariffs

    conn = get_connection()
    try:
        conn.execute(_CREATE_HS_CODES)
        conn.execute(_CREATE_COUNTRY_TARIFFS)
        conn.execute(_CREATE_JOBS)
        conn.execute(_CREATE_ANALYSIS_RESULTS)
        conn.execute(_CREATE_SIMULATION_RESULTS)
        conn.commit()
        seed_tariffs(conn)
        log.info("DB initialised at %s", DB_PATH)
    finally:
        conn.close()
