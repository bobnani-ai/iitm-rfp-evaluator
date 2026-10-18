"""Create the SQLite schema and seed the classroom evaluation criteria."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_DB = Path(__file__).resolve().parent / "rfp_evaluation.db"
CRITERIA = [
    (1, "Technical Capability", "Architecture, integrations, scalability, technical fit", 30.0, 10.0, 1),
    (2, "Implementation Plan", "Timeline, milestones, staffing, risk plan", 20.0, 10.0, 1),
    (3, "Commercial Value", "Pricing clarity, total cost, assumptions", 20.0, 10.0, 1),
    (4, "Security & Compliance", "Controls, certifications, privacy, auditability", 20.0, 10.0, 1),
    (5, "Support & Experience", "Support model, similar projects, references", 10.0, 10.0, 1),
]


def db_path() -> Path:
    return Path(os.environ.get("RFP_DB_PATH", DEFAULT_DB)).expanduser().resolve()


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path | None = None) -> None:
    with connect(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS evaluation_criteria (
                criterion_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                weight REAL NOT NULL CHECK (weight >= 0 AND weight <= 100),
                max_score REAL NOT NULL CHECK (max_score > 0),
                is_active INTEGER NOT NULL CHECK (is_active IN (0, 1))
            );
            CREATE TABLE IF NOT EXISTS rfp_runs (
                rfp_run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS supplier_results (
                rfp_run_id TEXT NOT NULL REFERENCES rfp_runs(rfp_run_id),
                supplier_name TEXT NOT NULL,
                submission_date TEXT NOT NULL,
                experience_rating REAL NOT NULL,
                absolute_score REAL NOT NULL,
                ppi REAL NOT NULL,
                final_rank INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                PRIMARY KEY (rfp_run_id, supplier_name)
            );
        """)
        db.executemany("""
            INSERT OR IGNORE INTO evaluation_criteria
            (criterion_id, name, description, weight, max_score, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, CRITERIA)


def active_criteria(path: Path | None = None) -> list[dict]:
    with connect(path) as db:
        rows = db.execute("""
            SELECT criterion_id, name, description, weight, max_score
            FROM evaluation_criteria WHERE is_active=1 ORDER BY criterion_id
        """).fetchall()
    criteria = [dict(row) for row in rows]
    if not criteria:
        raise ValueError("Activate at least one evaluation criterion.")
    if abs(sum(row["weight"] for row in criteria) - 100.0) > 0.001:
        raise ValueError("Active criterion weights must total 100%.")
    return criteria


if __name__ == "__main__":
    initialize()
    print(f"Initialized {db_path()}")
