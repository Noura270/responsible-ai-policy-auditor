import streamlit as st
import plotly.express as px
import pandas as pd
from db import get_dashboard_data

MIN_ROWS_FOR_CHART = 4  # الحد الأدنى لعرض chart بدل رقم خام

DECISION_COLORS = {
    "Violation": "#E5484D",
    "Needs Review": "#F2994A",
    "Compliant": "#30A46C",
    "Partially Compliant": "#3E63DD",
}
RISK_COLORS = {
    "Low": "#30A46C",
    "Medium": "#F2C94C",
    "High": "#F2994A",
    "Critical": "#E5484D",
}
STATUS_COLORS = {
    "Compliant": "#30A46C",
    "Evidence Required": "#F2C94C",
    "Non-Compliant": "#E5484D",
}


def render_dashboard():
    st.header("Governance Dashboard")

    evaluations, findings, policy_violations = get_dashboard_data()

    if evaluations.empty:
        st.info("No evaluations yet — run an assessment first.")
        return

    # ---------- KPI Row ----------
    total_evals = len(evaluations)
    high_critical = evaluations[evaluations["risk_level"].isin(["High", "Critical"])].shape[0]

    total_assessments = len(policy_violations)
    gap_statuses = ["Evidence Required", "Non-Compliant"]
    gap_count = policy_violations[policy_violations["status"].isin(gap_statuses)].shape[0]
    gap_rate = round((gap_count / total_assessments) * 100, 1) if total_assessments else 0

    confirmed_noncompliant = policy_violations[
        policy_violations["status"] == "Non-Compliant"
    ].shape[0]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Evaluations", total_evals)
    col2.metric("High/Critical Risk", high_critical)
    col3.metric("Compliance Gap Rate", f"{gap_rate}%")
    col4.metric("Confirmed Non-Compliant", confirmed_noncompliant)

    st.caption(f"Based on {total_evals} evaluations, {total_assessments} policy assessments.")
    st.divider()

    # ---------- Decision Distribution ----------
    _render_categorical_chart(
        df=evaluations,
        column="decision",
        title="Decision Distribution",
        chart_type="donut",
        color_map=DECISION_COLORS,
    )

    # ---------- Risk Level Distribution ----------
    _render_categorical_chart(
        df=evaluations,
        column="risk_level",
        title="Risk Level Distribution",
        chart_type="bar",
        category_order=["Low", "Medium", "High", "Critical"],
        color_map=RISK_COLORS,
    )

    # ---------- Findings by Risk Category ----------
    _render_categorical_chart(
        df=findings,
        column="category",
        title="Findings by Risk Category",
        chart_type="hbar",
    )

    # ---------- Compliance Status across Frameworks ----------
    if len(policy_violations) >= MIN_ROWS_FOR_CHART and "source" in policy_violations.columns:
        grouped = policy_violations.groupby(["source", "status"]).size().reset_index(name="count")
        fig = px.bar(
            grouped, x="source", y="count", color="status",
            title="Compliance Status across Frameworks", barmode="stack",
            color_discrete_map=STATUS_COLORS,
            category_orders={"status": ["Compliant", "Evidence Required", "Non-Compliant"]},
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"Based on {len(policy_violations)} policy assessments.")
    else:
        st.subheader("Compliance Status across Frameworks")
        st.write(f"Not enough data yet ({len(policy_violations)} policy assessments recorded).")


def _render_categorical_chart(df, column, title, chart_type="bar", category_order=None, color_map=None):
    st.subheader(title)
    if column not in df.columns or df.empty:
        st.write("Not enough data yet.")
        return

    counts = df[column].value_counts().reset_index()
    counts.columns = [column, "count"]

    if len(df) < MIN_ROWS_FOR_CHART:
        st.write(f"Not enough data yet ({len(df)} records). Raw counts:")
        st.table(counts)
        return

    max_count = counts["count"].max()

    if chart_type == "donut":
        fig = px.pie(
            counts, names=column, values="count", hole=0.5,
            color=column, color_discrete_map=color_map,
        )
    elif chart_type == "hbar":
        fig = px.bar(counts, x="count", y=column, orientation="h")
        fig.update_yaxes(categoryorder="total ascending")
        if max_count <= 10:
            fig.update_xaxes(dtick=1)
    else:
        fig = px.bar(
            counts, x=column, y="count",
            color=column if color_map else None,
            color_discrete_map=color_map,
            category_orders={column: category_order} if category_order else None,
        )
        fig.update_layout(showlegend=False)
        if max_count <= 10:
            fig.update_yaxes(dtick=1)

    fig.update_layout(title=title)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"Based on {len(df)} records.")