"""Rebuild the example completed-run JSON from four bundled proposals."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from sample_data import PROPOSALS
from workflow import create_run


def main() -> None:
    root = Path(__file__).resolve().parent
    inputs = []
    for profile in PROPOSALS[:4]:
        filename = profile["name"].lower().replace(" ", "_") + ".pdf"
        inputs.append({
            "supplier_name": profile["name"], "submission_date": profile["date"],
            "experience_rating": profile["experience"], "filename": filename,
            "pdf_bytes": (root / "sample_rfps" / filename).read_bytes(),
        })
    with tempfile.TemporaryDirectory() as directory:
        run = create_run(inputs, "demo", path=Path(directory) / "example.db")
    output = root / "example_run.json"
    output.write_bytes((json.dumps(run, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(output)


if __name__ == "__main__":
    main()
