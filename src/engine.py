"""Validation, transparent scoring, benchmarking and stable supplier ranking."""

from __future__ import annotations

import json
import math
from datetime import date


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def normalize(raw: object, supplier_name: str, criteria: list[dict]) -> dict:
    """Fail closed for absent scores; clip finite out-of-range scores with warnings."""
    warnings: list[str] = []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
            warnings.append("Model response was not valid JSON; all scores defaulted to zero.")
    if not isinstance(raw, dict):
        raw = {}
        warnings.append("Model response was not a JSON object; all scores defaulted to zero.")
    entries = raw.get("criteria", [])
    if not isinstance(entries, list):
        entries = []
        warnings.append("Criteria field was malformed; all scores defaulted to zero.")
    by_id: dict[int, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            warnings.append("Discarded a malformed criterion result.")
            continue
        try:
            cid = int(entry.get("criterion_id"))
        except (TypeError, ValueError):
            warnings.append("Discarded a criterion result with invalid ID.")
            continue
        if cid in by_id:
            warnings.append(f"Duplicate criterion {cid}; first result retained.")
            continue
        by_id[cid] = entry
    known = {row["criterion_id"] for row in criteria}
    for cid in by_id.keys() - known:
        warnings.append(f"Ignored inactive or unknown criterion {cid}.")
    output = []
    for criterion in criteria:
        cid = criterion["criterion_id"]
        entry = by_id.get(cid)
        maximum = float(criterion["max_score"])
        if entry is None:
            warnings.append(f"Missing {criterion['name']} score; set to zero.")
            entry = {}
        score = _number(entry.get("score"))
        if score is None:
            warnings.append(f"Invalid {criterion['name']} score; set to zero.")
            score = 0.0
        elif score < 0 or score > maximum:
            warnings.append(f"{criterion['name']} score clipped to 0–{maximum:g}.")
            score = min(max(score, 0.0), maximum)
        if _number(entry.get("max_score")) not in (None, maximum):
            warnings.append(f"Model maximum for {criterion['name']} ignored; database maximum used.")
        justification = entry.get("justification")
        evidence = entry.get("evidence")
        if not isinstance(justification, str) or not justification.strip():
            justification = "No justification supplied."
            warnings.append(f"Missing {criterion['name']} justification.")
        if not isinstance(evidence, str) or not evidence.strip():
            evidence = "No supporting evidence supplied."
            warnings.append(f"Missing {criterion['name']} evidence.")
        output.append({
            "criterion_id": cid, "name": criterion["name"], "score": score,
            "max_score": maximum, "weight": float(criterion["weight"]),
            "justification": justification.strip(), "evidence": evidence.strip(),
        })
    risks = raw.get("risks", [])
    if not isinstance(risks, list):
        risks = []
        warnings.append("Malformed risks field ignored.")
    return {
        "supplier_name": supplier_name,
        "criteria": output,
        "risks": [str(item) for item in risks if isinstance(item, str)],
        "overall_summary": str(raw.get("overall_summary") or "No summary supplied."),
        "warnings": warnings,
    }


def rank_suppliers(suppliers: list[dict], criteria: list[dict]) -> list[dict]:
    if not suppliers:
        raise ValueError("At least one supplier is required.")
    benchmarks = {
        c["criterion_id"]: max(s["scorecard"]["criteria"][i]["score"] for s in suppliers)
        for i, c in enumerate(criteria)
    }
    for supplier in suppliers:
        absolute = 0.0
        ppi = 0.0
        for result in supplier["scorecard"]["criteria"]:
            benchmark = benchmarks[result["criterion_id"]]
            score = result["score"]
            relative = 100.0 if benchmark == 0 else score / benchmark * 100.0
            result["benchmark"] = benchmark
            result["gap"] = score - benchmark
            result["relative_percent"] = relative
            absolute += score / result["max_score"] * result["weight"]
            ppi += relative * result["weight"] / 100.0
        supplier["absolute_score"] = absolute
        supplier["ppi"] = ppi
    ranked = sorted(suppliers, key=lambda s: (
        -s["ppi"], date.fromisoformat(s["submission_date"]),
        -float(s["experience_rating"]), s["supplier_name"].casefold(),
    ))
    for index, supplier in enumerate(ranked, 1):
        supplier["final_rank"] = index
        supplier["tie_break_explanation"] = (
            "Sorted by higher PPI, earlier submission date, higher historical experience "
            "rating, then supplier name ascending."
        )
    return ranked
