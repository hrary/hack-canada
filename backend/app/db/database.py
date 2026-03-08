"""SQLite tariff database — schema creation and connection management."""

from __future__ import annotations

import sqlite3
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "tariffs.db"

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


def get_connection() -> sqlite3.Connection:
    """Return a new connection to the tariff database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables (if missing) and seed initial data."""
    from .seed import seed_tariffs

    conn = get_connection()
    try:
        conn.execute(_CREATE_HS_CODES)
        conn.execute(_CREATE_COUNTRY_TARIFFS)
        conn.commit()
        seed_tariffs(conn)
        log.info("Tariff DB initialised at %s", DB_PATH)
    finally:
        conn.close()
