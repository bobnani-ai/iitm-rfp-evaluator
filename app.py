"""Streamlit entrypoint for the Agentic RFP Evaluation mini project."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import streamlit as st

from llm import PROVIDER_KEY_ENV, PROVIDER_MODELS
from sample_data import PROPOSALS, REQUEST
from seed_db import active_criteria, connect, initialize
from workflow import create_run, load_run, recent_runs

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="RFP Supplier Ranking", page_icon="📋", layout="wide")
initialize()


def api_key(provider: str, entered: str) -> str:
    if entered.strip():
        return entered.strip()
    variable = PROVIDER_KEY_ENV[provider]
    key = os.environ.get(variable, "")
    if key:
        return key
    try:
        return str(st.secrets.get(variable, ""))
    except (FileNotFoundError, KeyError):
        return ""


def show_run(run: dict, key: str) -> None:
    st.subheader("Leaderboard")
    st.caption(f"Run {run['rfp_run_id']} · {run['status']} · {run['mode']} mode · "
               f"{run.get('provider', 'OpenAI')} / {run['model']}")
    st.dataframe([{
        "Rank": s["final_rank"], "Supplier": s["supplier_name"],
        "Absolute score / 100": round(s["absolute_score"], 2),
        "PPI / 100": round(s["ppi"], 2),
        "Submission date": s["submission_date"],
        "Experience / 10": s["experience_rating"],
    } for s in run["suppliers"]], hide_index=True, width="stretch")
    st.caption("PPI decides rank; ties use earlier date, higher experience, then supplier name.")
    selected = st.selectbox("Detailed scorecard", [s["supplier_name"] for s in run["suppliers"]],
                            key=f"{key}_supplier")
    supplier = next(s for s in run["suppliers"] if s["supplier_name"] == selected)
    st.dataframe([{
        "Criterion": c["name"], "Score": c["score"], "Maximum": c["max_score"],
        "Weight %": c["weight"], "Peer best": c["benchmark"], "Gap": c["gap"],
        "Relative %": round(c["relative_percent"], 2),
        "Evidence": c["evidence"], "Justification": c["justification"],
    } for c in supplier["scorecard"]["criteria"]], hide_index=True, width="stretch")
    st.write("**Summary:**", supplier["scorecard"]["overall_summary"])
    st.write("**Risks:**", "; ".join(supplier["scorecard"]["risks"]) or "None listed")
    st.write("**Tie-break:**", supplier["tie_break_explanation"])
    if supplier["scorecard"]["warnings"]:
        st.warning("Validation warnings: " + " | ".join(supplier["scorecard"]["warnings"]))
    st.download_button("Download complete run JSON", json.dumps(run, indent=2, ensure_ascii=False),
                       file_name=f"rfp_run_{run['rfp_run_id']}.json", mime="application/json",
                       key=f"{key}_download")


with st.sidebar:
    st.header("LLM settings")
    provider = st.selectbox("Provider", list(PROVIDER_MODELS))
    model_choice = st.selectbox("Model", [*PROVIDER_MODELS[provider], "Custom model ID"],
                                key=f"model_choice_{provider}")
    model = (st.text_input("Custom model ID", key=f"custom_model_{provider}").strip()
             if model_choice == "Custom model ID" else model_choice)
    entered_key = st.text_input(f"{provider} API key", type="password",
                                key=f"api_key_{provider}", placeholder="Paste API key")
    selected_api_key = api_key(provider, entered_key)
    if selected_api_key:
        st.caption("API key available for live evaluation.")
    else:
        st.caption(f"Enter a key or configure {PROVIDER_KEY_ENV[provider]} as an environment variable or Streamlit secret.")
    st.caption("The key is used for API calls and is not saved in SQLite or run JSON.")

st.title("Agentic RFP Evaluation and Supplier Ranking")
st.write(REQUEST)
st.info("Classroom demonstration. Proposals and fixture scores are fictional. Live mode uses an LLM; all arithmetic and ranking use Python.")
criteria_tab, evaluate_tab, history_tab = st.tabs(["Criteria", "Evaluate", "Saved runs"])

with criteria_tab:
    st.subheader("SQLite evaluation criteria")
    with connect() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM evaluation_criteria ORDER BY criterion_id")]
    edited = st.data_editor(rows, hide_index=True, width="stretch",
                            disabled=["criterion_id"], num_rows="fixed",
                            column_config={"is_active": st.column_config.CheckboxColumn("Active")})
    st.caption("Active weights must sum to 100%. Changes affect new runs; stored runs retain their original criteria snapshot.")
    if st.button("Save criteria"):
        try:
            active = [r for r in edited if r["is_active"]]
            if not active or abs(sum(float(r["weight"]) for r in active) - 100) > 0.001:
                raise ValueError("Active weights must total 100%.")
            if any(float(r["max_score"]) <= 0 or not 0 <= float(r["weight"]) <= 100 for r in edited):
                raise ValueError("Use positive maximum scores and weights from 0 to 100.")
            with connect() as db:
                db.executemany("""UPDATE evaluation_criteria SET name=?, description=?, weight=?,
                    max_score=?, is_active=? WHERE criterion_id=?""", [
                    (r["name"], r["description"], float(r["weight"]), float(r["max_score"]),
                     int(bool(r["is_active"])), r["criterion_id"]) for r in edited
                ])
            st.success("Criteria saved to SQLite.")
        except Exception as exc:
            st.error(f"Could not save criteria: {exc}")
    try:
        current = active_criteria()
        st.write(f"Active weight total: **{sum(row['weight'] for row in current):g}%**")
    except ValueError as exc:
        st.error(str(exc))

with evaluate_tab:
    mode = st.radio("Evaluation mode", ["Demo: bundled proposals", "Live: uploaded PDFs + selected LLM"],
                    horizontal=True)
    inputs = []
    if mode.startswith("Demo"):
        names = st.multiselect("Select sample RFPs", [p["name"] for p in PROPOSALS],
                               default=[p["name"] for p in PROPOSALS[:4]])
        for profile in PROPOSALS:
            if profile["name"] in names:
                filename = profile["name"].lower().replace(" ", "_") + ".pdf"
                inputs.append({"supplier_name": profile["name"], "submission_date": profile["date"],
                               "experience_rating": profile["experience"], "filename": filename,
                               "pdf_bytes": (ROOT / "sample_rfps" / filename).read_bytes()})
        st.caption("Fixture scores are preassigned for reproducibility. PDFs are still parsed and evidence is checked.")
    else:
        if not selected_api_key:
            st.warning(f"Enter a {provider} API key in the sidebar or configure {PROVIDER_KEY_ENV[provider]}.")
        uploads = st.file_uploader("Upload supplier RFP PDFs", type="pdf", accept_multiple_files=True)
        for index, uploaded in enumerate(uploads or []):
            with st.expander(f"Supplier metadata: {uploaded.name}", expanded=True):
                name = st.text_input("Supplier name", value=Path(uploaded.name).stem.replace("_", " ").title(),
                                     key=f"name_{index}_{uploaded.name}")
                submitted = st.date_input("Submission date", value=date.today(),
                                          key=f"date_{index}_{uploaded.name}")
                experience = st.number_input("Historical experience / 10", 0.0, 10.0, 5.0, 0.1,
                                              key=f"exp_{index}_{uploaded.name}")
                inputs.append({"supplier_name": name.strip(), "submission_date": submitted.isoformat(),
                               "experience_rating": experience, "filename": uploaded.name,
                               "pdf_bytes": uploaded.getvalue()})
    if st.button("Evaluate batch", type="primary",
                 disabled=len(inputs) < 2 or (not mode.startswith("Demo") and (not selected_api_key or not model))):
        try:
            with st.spinner("Reading proposals and evaluating suppliers..."):
                run = create_run(inputs, "demo" if mode.startswith("Demo") else "live",
                                 api_key=selected_api_key if not mode.startswith("Demo") else "",
                                 provider=provider, model=model)
            st.session_state["current_run_id"] = run["rfp_run_id"]
            st.success("Run completed and saved to SQLite.")
        except Exception as exc:
            st.error(f"Evaluation stopped: {exc}")
    if st.session_state.get("current_run_id"):
        try:
            show_run(load_run(st.session_state["current_run_id"]), "current")
        except ValueError:
            st.session_state.pop("current_run_id", None)

with history_tab:
    runs = recent_runs()
    if not runs:
        st.write("No saved runs yet.")
    else:
        selected_id = st.selectbox("Open a saved run", [r["rfp_run_id"] for r in runs])
        show_run(load_run(selected_id), "history")
