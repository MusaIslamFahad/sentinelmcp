"""
SentinelMCP dashboard.

Run with: streamlit run dashboard/app.py

Reads directly from the SQLite DB — no separate API needed for the dashboard
itself, keeping the free-tier footprint minimal.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd

from storage.db import init_db, get_all_runs, get_run_results
from agents.reporter import ReporterAgent

st.set_page_config(page_title="SentinelMCP", layout="wide")
init_db()

st.title("🛡️ SentinelMCP — Agent Reliability Dashboard")
st.caption("Automated red-teaming results for AI agents under test")

runs = get_all_runs()

if not runs:
    st.info("No runs yet. Run `python main.py --target my-agent` to generate results.")
    st.stop()

run_options = {f"{r['target_name']} — {r['started_at'][:19]} ({r['run_id'][:8]})": r["run_id"] for r in runs}
selected_label = st.selectbox("Select a run", list(run_options.keys()))
run_id = run_options[selected_label]

results = get_run_results(run_id)
scorecard = ReporterAgent().build_scorecard(results)

errored = scorecard.get("errored_tests", [])
col1, col2, col3, col4 = st.columns(4)
col1.metric("Tests scored", scorecard["total_tests"])
col2.metric("Attacks succeeded", scorecard.get("attacks_succeeded", 0))
col3.metric("Attack success rate", f"{scorecard['overall_success_rate']*100:.1f}%")
col4.metric("Not tested (errors)", len(errored), delta=None if not errored else "re-run these", delta_color="inverse")

if errored:
    with st.expander(f"⚠️ {len(errored)} test case(s) failed to execute — excluded from the success rate above"):
        for e in errored:
            st.write(f"**[{e['category']}]** {e['test_case_id']}: {e['error']}")

st.subheader("Results by attack category")
if scorecard["by_category"]:
    df_cat = pd.DataFrame([
        {"category": cat, "success_rate": stats["success_rate"], "total": stats["total"], "succeeded": stats["succeeded"]}
        for cat, stats in scorecard["by_category"].items()
    ]).sort_values("success_rate", ascending=False)
    st.bar_chart(df_cat.set_index("category")["success_rate"])
    st.dataframe(df_cat, use_container_width=True)

st.subheader("High severity failures")
if scorecard["high_severity_failures"]:
    for f in scorecard["high_severity_failures"]:
        with st.expander(f"[{f['category']}] {f['test_case_id']} — severity {f['severity']}"):
            st.write("**Judge reasoning:**", f["judge_reasoning"])
            st.write("**Prompt:**", f["prompt"])
            st.write("**Target response:**", f["target_response"])
            if f.get("tool_called"):
                st.warning(f"Tool actually invoked: `{f['tool_called']}`")
else:
    st.success("No high-severity failures in this run.")

st.subheader("All results")
df_all = pd.DataFrame(results)
st.dataframe(df_all, use_container_width=True)

st.subheader("Trend across runs")
trend_rows = []
for r in runs:
    r_results = get_run_results(r["run_id"])
    if r_results:
        r_scorecard = ReporterAgent().build_scorecard(r_results)
        trend_rows.append({
            "run": f"{r['started_at'][:16]}",
            "attack_success_rate": r_scorecard["overall_success_rate"],
        })
if len(trend_rows) > 1:
    df_trend = pd.DataFrame(trend_rows).sort_values("run")
    st.line_chart(df_trend.set_index("run")["attack_success_rate"])
else:
    st.caption("Run the suite a few more times to see a trend over runs.")
