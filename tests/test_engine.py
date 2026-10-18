from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import normalize, rank_suppliers
from llm import evaluate
from sample_data import PROPOSALS
from seed_db import active_criteria, initialize
from workflow import create_run, extract_pdf, load_run


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        initialize(self.path)
        self.criteria = active_criteria(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_normalization_clips_and_fills_missing_scores(self):
        raw = {"criteria": [{"criterion_id": 1, "score": 99, "max_score": 99,
                             "justification": "Claim", "evidence": "Claim"}]}
        result = normalize(raw, "X", self.criteria)
        self.assertEqual([c["score"] for c in result["criteria"]], [10, 0, 0, 0, 0])
        self.assertTrue(any("clipped" in warning for warning in result["warnings"]))
        self.assertEqual(len(result["criteria"]), 5)

    def test_tie_break_order_and_zero_benchmark(self):
        suppliers = []
        for name, day, experience in [("Zulu", "2026-10-02", 9),
                                       ("Beta", "2026-10-01", 7),
                                       ("Alpha", "2026-10-01", 7),
                                       ("Omega", "2026-10-01", 8)]:
            scorecard = normalize({"criteria": []}, name, self.criteria)
            suppliers.append({"supplier_name": name, "submission_date": day,
                              "experience_rating": experience, "scorecard": scorecard})
        ranked = rank_suppliers(suppliers, self.criteria)
        self.assertEqual([s["supplier_name"] for s in ranked],
                         ["Omega", "Alpha", "Beta", "Zulu"])
        self.assertTrue(all(s["ppi"] == 100 for s in ranked))
        self.assertTrue(all(c["relative_percent"] == 100 for c in ranked[0]["scorecard"]["criteria"]))

    def test_all_sample_pdfs_and_saved_batch(self):
        inputs = []
        for profile in PROPOSALS:
            filename = profile["name"].lower().replace(" ", "_") + ".pdf"
            data = (Path(__file__).resolve().parents[1] / "sample_rfps" / filename).read_bytes()
            text = extract_pdf(data)
            self.assertIn(profile["name"], text)
            self.assertIn("Page 3 of 3", text)
            inputs.append({"supplier_name": profile["name"], "submission_date": profile["date"],
                           "experience_rating": profile["experience"], "filename": filename,
                           "pdf_bytes": data})
        run = create_run(inputs, "demo", path=self.path)
        self.assertEqual(len(run["suppliers"]), 10)
        self.assertEqual([s["final_rank"] for s in run["suppliers"]], list(range(1, 11)))
        self.assertEqual(load_run(run["rfp_run_id"], self.path)["rfp_run_id"], run["rfp_run_id"])
        self.assertFalse(any(s["scorecard"]["warnings"] for s in run["suppliers"]))

    def test_llm_request_uses_dynamic_criteria_and_strict_schema(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, *_):
                return json.dumps({"status": "completed", "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": json.dumps({"supplier_name": "X", "criteria": [],
                                                                  "risks": [], "overall_summary": "ok"})}
                ]}]}).encode()

        with patch("llm.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            result = evaluate("proposal evidence", "X", self.criteria, "fake-key")
        self.assertEqual(result["supplier_name"], "X")
        request = urlopen.call_args.args[0]
        body = json.loads(request.data)
        self.assertTrue(body["text"]["format"]["strict"])
        self.assertEqual(len(json.loads(body["input"][1]["content"].split("Active criteria: ")[1].split("\n\n")[0])), 5)
        self.assertNotIn("fake-key", json.dumps(body))


if __name__ == "__main__":
    unittest.main()
