"""Orchestrates PDF extraction, evaluation, validation, scoring and persistence."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from engine import normalize, rank_suppliers
from llm import evaluate
from sample_data import PROPOSALS
from seed_db import active_criteria, connect, initialize


def extract_pdf(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise ValueError("Uploaded file is not a PDF.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt to enable PDF extraction.") from exc
    try:
        reader = PdfReader(BytesIO(data), strict=False)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDFs are not supported.")
        if len(reader.pages) > 30:
            raise ValueError("PDF exceeds the 30-page limit.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("PDF could not be read.") from exc
    text = re.sub(r"[ \t]+", " ", text)
    if len(text.strip()) < 80:
        raise ValueError("PDF has too little selectable text; scanned PDFs need OCR.")
    return text


def _ground_scorecard(scorecard: dict, text: str) -> None:
    haystack = " ".join(text.split()).casefold()
    for result in scorecard["criteria"]:
        evidence = " ".join(result["evidence"].split()).casefold()
        if result["score"] > 0 and (evidence == "no supporting evidence supplied." or evidence not in haystack):
            result["score"] = 0.0
            scorecard["warnings"].append(
                f"{result['name']} evidence could not be found in the PDF; score set to zero."
            )


def demo_evaluation(name: str, criteria: list[dict]) -> dict:
    profile = next((p for p in PROPOSALS if p["name"] == name), None)
    if profile is None:
        raise ValueError("Demo mode accepts only the bundled sample RFPs.")
    # The excerpts below are literal text from the bundled PDF generation source.
    source_fields = ["solution", "implementation", "price", "security", "support"]
    entries = []
    for index, criterion in enumerate(criteria):
        cid = criterion["criterion_id"]
        if cid not in range(1, 6):
            entries.append({"criterion_id": cid, "score": 0, "max_score": criterion["max_score"],
                            "justification": "No classroom fixture for this added criterion.",
                            "evidence": "No supporting evidence supplied."})
            continue
        source = profile[source_fields[cid - 1]]
        excerpt = source.split("\n")[0]
        entries.append({"criterion_id": cid, "score": profile["scores"][cid - 1],
                        "max_score": criterion["max_score"],
                        "justification": "Classroom fixture score based on this proposal section; use live mode for LLM assessment.",
                        "evidence": excerpt})
    return {"supplier_name": name, "criteria": entries, "risks": [profile["risks"]],
            "overall_summary": profile["summary"]}


def create_run(inputs: list[dict], mode: str, api_key: str = "", model: str = "gpt-5.4-mini",
               path: Path | None = None) -> dict:
    if len(inputs) < 2:
        raise ValueError("Upload or select at least two supplier proposals.")
    names = [item["supplier_name"].strip() for item in inputs]
    if any(not name for name in names) or len({name.casefold() for name in names}) != len(names):
        raise ValueError("Supplier names must be present and unique within a batch.")
    for item in inputs:
        datetime.strptime(item["submission_date"], "%Y-%m-%d")
        rating = float(item["experience_rating"])
        if not 0 <= rating <= 10:
            raise ValueError("Historical experience ratings must be between 0 and 10.")
        if len(item["pdf_bytes"]) > 10 * 1024 * 1024:
            raise ValueError("Each PDF must be 10 MB or smaller.")
    initialize(path)
    criteria = active_criteria(path)
    results = []
    for item in inputs:
        text = extract_pdf(item["pdf_bytes"])
        raw = (demo_evaluation(item["supplier_name"], criteria) if mode == "demo"
               else evaluate(text, item["supplier_name"], criteria, api_key, model))
        scorecard = normalize(raw, item["supplier_name"], criteria)
        _ground_scorecard(scorecard, text)
        results.append({
            "supplier_name": item["supplier_name"],
            "submission_date": item["submission_date"],
            "experience_rating": float(item["experience_rating"]),
            "source_file": item.get("filename", "uploaded.pdf"),
            "scorecard": scorecard,
        })
    ranked = rank_suppliers(results, criteria)
    run = {
        "rfp_run_id": str(uuid.uuid4()),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed_with_warnings" if any(r["scorecard"]["warnings"] for r in ranked) else "completed",
        "mode": mode,
        "model": model if mode == "live" else "classroom fixture",
        "criteria": criteria,
        "suppliers": ranked,
        "formula_notes": {
            "absolute_score": "sum(score / max_score * weight)",
            "benchmark": "maximum validated score per criterion",
            "gap": "supplier score - benchmark",
            "relative_percent": "100 when benchmark is zero; else score / benchmark * 100",
            "ppi": "sum(relative_percent * weight / 100)",
            "tie_break": "PPI descending, submission date ascending, experience descending, name ascending",
        },
    }
    encoded = json.dumps(run, ensure_ascii=False)
    with connect(path) as db:
        db.execute("INSERT INTO rfp_runs VALUES (?, ?, ?, ?)",
                   (run["rfp_run_id"], run["created_at"], run["status"], encoded))
        db.executemany("INSERT INTO supplier_results VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            (run["rfp_run_id"], s["supplier_name"], s["submission_date"],
             s["experience_rating"], s["absolute_score"], s["ppi"],
             s["final_rank"], json.dumps(s, ensure_ascii=False)) for s in ranked
        ])
    return run


def recent_runs(path: Path | None = None) -> list[dict]:
    with connect(path) as db:
        return [dict(row) for row in db.execute(
            "SELECT rfp_run_id, created_at, status FROM rfp_runs ORDER BY created_at DESC LIMIT 20"
        )]


def load_run(run_id: str, path: Path | None = None) -> dict:
    with connect(path) as db:
        row = db.execute("SELECT result_json FROM rfp_runs WHERE rfp_run_id=?", (run_id,)).fetchone()
    if row is None:
        raise ValueError("Run not found.")
    return json.loads(row["result_json"])
