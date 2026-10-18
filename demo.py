"""Reproducible terminal demonstration and validation/error example."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from engine import normalize
from sample_data import PROPOSALS
from seed_db import active_criteria, initialize
from workflow import create_run


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "demo.db"
        initialize(database)
        inputs = []
        for profile in PROPOSALS[:4]:
            filename = profile["name"].lower().replace(" ", "_") + ".pdf"
            inputs.append({
                "supplier_name": profile["name"], "submission_date": profile["date"],
                "experience_rating": profile["experience"], "filename": filename,
                "pdf_bytes": (Path(__file__).parent / "sample_rfps" / filename).read_bytes(),
            })
        run = create_run(inputs, "demo", path=database)
        print("SUCCESS CASE")
        for supplier in run["suppliers"]:
            print(f"{supplier['final_rank']}. {supplier['supplier_name']}: "
                  f"absolute={supplier['absolute_score']:.2f}, PPI={supplier['ppi']:.2f}")
        bad = {"criteria": [{"criterion_id": 1, "score": 99, "max_score": 10,
                             "justification": "Invalid oversized score", "evidence": "Example"}]}
        normalized = normalize(bad, "Malformed Supplier", active_criteria(database))
        print("\nVALIDATION CASE")
        print(json.dumps({"scores": [c["score"] for c in normalized["criteria"]],
                          "warnings": normalized["warnings"]}, indent=2))


if __name__ == "__main__":
    main()
