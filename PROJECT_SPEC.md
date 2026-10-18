# Project specification and acceptance checks

## Goal

Rank suppliers responding to one RFP with traceable criterion scores, proposal evidence and fixed business rules. The app should run locally and be deployable to Streamlit Community Cloud.

## Functional scope

| Area | Acceptance check |
| --- | --- |
| Criteria | SQLite contains criterion ID, name, description, weight, maximum and active flag. UI shows and edits them. Active weights total 100%. |
| Input | At least two PDF proposals, a unique supplier name, ISO submission date and experience rating from 0 to 10. |
| Extraction | Read selectable text from every PDF; reject unreadable, encrypted, oversized or scanned files with a clear error. |
| Evaluation | One structured JSON scorecard per supplier based only on its PDF and the current active criteria. |
| Provider selection | Sidebar selects OpenAI, Anthropic or Google Gemini, a model, and a provider API key. The selected provider and model appear in the run JSON; the key never does. |
| Validation | Fill missing criteria, reject/normalize malformed scores, clip out-of-range values, flag unmatched evidence and show warnings. |
| Scoring | Calculate absolute weighted score, best peer score, gap, relative percentage and PPI in Python. |
| Ranking | Sort by PPI descending, date ascending, experience descending, name ascending; assign 1..N. |
| Storage | `rfp_runs` and `supplier_results` hold the complete result under one run ID. |
| Output | Leaderboard, scorecard evidence, warnings, tie-break explanation and full JSON export. |
| Samples | Ten fictional PDF proposals for the same request, three pages each, with varied strengths and deliberate gaps. |

## Data contract

The model result has `supplier_name`, `criteria[]`, `risks[]` and `overall_summary`. Each criterion has `criterion_id`, `score`, `max_score`, `justification` and `evidence`. The app adds database `name` and `weight`, peer `benchmark`, `gap` and `relative_percent`, plus supplier metadata, `absolute_score`, `ppi`, `final_rank` and warnings. See `example_run.json` for a full example.

## Edge cases to preserve

- A missing criterion scores zero and produces a warning.
- Nonnumeric, NaN or infinity scores become zero; finite negative/over-maximum values are clipped.
- Unknown criteria are ignored; duplicate IDs keep the first entry and warn.
- If a benchmark is zero, all suppliers receive 100% relative performance for that criterion.
- Comparison uses unrounded PPI so display rounding cannot change rank.
- A refused/failed LLM request stops the batch and writes no partial run.
- Editing weights affects later runs, not stored run JSON.

## Files to hand in

`app.py`, supporting modules, `seed_db.py`, `requirements.txt`, ten PDFs under `sample_rfps/`, this specification, `AGENTS.md`, `README.md`, `DEPLOYMENT.md`, `example_run.json` and `DEMO_OUTPUT.md`. The final public URL and screenshots must be added after deployment to a GitHub repository and Streamlit Community Cloud account.
