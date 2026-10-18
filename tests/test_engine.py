from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import json
from io import BytesIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from engine import normalize, rank_suppliers
from llm import PROVIDER_KEY_ENV, PROVIDER_MODELS, _post, evaluate
from sample_data import PROPOSALS
from seed_db import active_criteria, initialize
from workflow import create_run, demo_evaluation, extract_pdf, load_run


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
            data = (ROOT / "examples" / "sample_rfps" / filename).read_bytes()
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

    def test_other_provider_request_shapes_and_response_parsing(self):
        result_json = json.dumps({"supplier_name": "X", "criteria": [],
                                  "risks": [], "overall_summary": "ok"})

        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self, *_):
                return json.dumps(self.payload).encode()

        cases = [
            ("Anthropic", "claude-haiku-5-5", {"stop_reason": "end_turn", "content": [
                {"type": "text", "text": result_json}]}, "api.anthropic.com"),
            ("Google Gemini", "gemini-3.8-flash", {"candidates": [{"finishReason": "STOP",
                "content": {"parts": [{"text": result_json}]}}]}, "generativelanguage.googleapis.com"),
            ("Cohere.ai", "command-a-plus-05-2026", {"finish_reason": "COMPLETE",
                "message": {"content": [{"type": "text", "text": result_json}]}}, "api.cohere.com"),
            ("OpenRouter", "openai/gpt-5.4-mini", {"choices": [{"finish_reason": "stop",
                "message": {"content": result_json}}]}, "openrouter.ai"),
        ]
        for provider, model, payload, host in cases:
            with self.subTest(provider=provider):
                with patch("llm.urllib.request.urlopen", return_value=FakeResponse(payload)) as urlopen:
                    result = evaluate("proposal evidence", "X", self.criteria, "fake-key",
                                      provider=provider, model=model)
                self.assertEqual(result["supplier_name"], "X")
                request = urlopen.call_args.args[0]
                self.assertIn(host, request.full_url)
                body = json.loads(request.data)
                self.assertNotIn("fake-key", json.dumps(body))
                if provider == "Anthropic":
                    self.assertEqual(body["model"], model)
                    self.assertEqual(body["output_config"]["format"]["type"], "json_schema")
                elif provider == "Google Gemini":
                    self.assertIn(model, request.full_url)
                    self.assertEqual(body["generationConfig"]["responseFormat"]["text"]["mimeType"],
                                     "application/json")
                elif provider == "Cohere.ai":
                    self.assertEqual(body["model"], model)
                    self.assertEqual(body["response_format"]["type"], "json_object")
                    self.assertEqual(body["response_format"]["schema"]["type"], "object")
                    self.assertEqual(request.get_header("Authorization"), "Bearer fake-key")
                else:
                    self.assertEqual(body["model"], model)
                    self.assertTrue(body["provider"]["require_parameters"])
                    self.assertTrue(body["response_format"]["json_schema"]["strict"])
                    self.assertEqual(request.get_header("Authorization"), "Bearer fake-key")

    def test_new_provider_errors_are_actionable(self):
        self.assertEqual(PROVIDER_KEY_ENV["Cohere.ai"], "COHERE_API_KEY")
        self.assertEqual(PROVIDER_KEY_ENV["OpenRouter"], "OPENROUTER_API_KEY")
        self.assertIn("openai/gpt-5.4-mini", PROVIDER_MODELS["OpenRouter"])
        cases = [
            ("Cohere.ai", {"finish_reason": "MAX_TOKENS", "message": {"content": []}},
             "Cohere response stopped: MAX_TOKENS"),
            ("OpenRouter", {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
             "OpenRouter response stopped: length"),
            ("OpenRouter", {"error": {"message": "Invalid fake-key"}},
             "OpenRouter returned an error: Invalid [redacted]"),
            ("OpenRouter", {"choices": []}, "OpenRouter returned no completion choice"),
            ("Cohere.ai", {"finish_reason": "COMPLETE", "message": {"content": []}},
             "LLM response contained no JSON output"),
        ]
        for provider, payload, expected in cases:
            with self.subTest(provider=provider, expected=expected):
                with patch("llm._post", return_value=payload):
                    with self.assertRaisesRegex(RuntimeError, expected.replace("[", r"\[").replace("]", r"\]")):
                        evaluate("proposal", "X", self.criteria, "fake-key", provider=provider)

    def test_provider_http_error_redacts_key(self):
        error = urllib.error.HTTPError("https://api.cohere.com/v2/chat", 401, "Unauthorized", {},
                                       BytesIO(b'{"message":"bad fake-key"}'))
        with patch("llm.urllib.request.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                _post("https://api.cohere.com/v2/chat", {}, {}, "fake-key")
        self.assertIn("HTTP 401", str(caught.exception))
        self.assertIn("[redacted]", str(caught.exception))
        self.assertNotIn("fake-key", str(caught.exception))

    def test_live_run_passes_selected_provider_without_persisting_key(self):
        inputs = []
        for profile in PROPOSALS[:2]:
            filename = profile["name"].lower().replace(" ", "_") + ".pdf"
            inputs.append({"supplier_name": profile["name"], "submission_date": profile["date"],
                           "experience_rating": profile["experience"], "filename": filename,
                           "pdf_bytes": (ROOT / "examples" / "sample_rfps" / filename).read_bytes()})

        def fixture(_text, name, criteria, _key, provider, model):
            self.assertEqual((provider, model), ("Anthropic", "claude-haiku-5-5"))
            return demo_evaluation(name, criteria)

        with patch("workflow.evaluate", side_effect=fixture) as mocked:
            run = create_run(inputs, "live", api_key="secret-for-test", provider="Anthropic",
                             model="claude-haiku-5-5", path=self.path)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual((run["provider"], run["model"]), ("Anthropic", "claude-haiku-5-5"))
        self.assertNotIn("secret-for-test", json.dumps(load_run(run["rfp_run_id"], self.path)))


if __name__ == "__main__":
    unittest.main()
