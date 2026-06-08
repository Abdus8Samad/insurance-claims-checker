"""Streamlit render helpers for decisions and traces."""

from __future__ import annotations

import streamlit as st

from claims.models import ClaimDecision, Decision, Trace

_COLOR = {
    Decision.APPROVED: "green",
    Decision.PARTIAL: "orange",
    Decision.REJECTED: "red",
    Decision.MANUAL_REVIEW: "violet",
    Decision.NEEDS_RESUBMISSION: "blue",
}
_STATUS_EMOJI = {"PASS": "✅", "FAIL": "❌", "FLAG": "⚠️", "SKIPPED": "⏭️", "ERROR": "🔥"}


def render_decision(d: ClaimDecision) -> None:
    status = d.decision or Decision.NEEDS_RESUBMISSION
    color = _COLOR.get(status, "gray")
    label = d.decision.value if d.decision else "NEEDS RESUBMISSION (no decision)"
    st.markdown(f"## :{color}[{label}]")

    if d.degraded:
        st.warning("⚠️ Degraded run — one or more components failed and were skipped. "
                   "Manual review recommended; confidence reduced.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Approved amount", f"₹{d.approved_amount:,}")
    c2.metric("Confidence", f"{d.confidence_score:.2f}")
    c3.metric("Reasons", ", ".join(d.reasons) or "—")

    if d.user_message:
        st.info(d.user_message)

    if d.fraud_signals:
        with st.expander("Fraud / anomaly signals", expanded=True):
            for s in d.fraud_signals:
                st.write(f"- {s}")

    if d.line_item_breakdown:
        st.subheader("Line items")
        rows = [
            {
                "Item": li.description,
                "Amount": f"₹{li.amount:,}",
                "Covered": "✓" if li.covered else ("✗" if li.covered is False else "—"),
                "Reason": li.rejection_reason or "",
            }
            for li in d.line_item_breakdown
        ]
        st.dataframe(rows, width='stretch', hide_index=True)

    breakdown = d.financial_breakdown.get("breakdown") if d.financial_breakdown else None
    if breakdown:
        st.subheader("Financial breakdown")
        for step in breakdown:
            extra = {k: v for k, v in step.items() if k not in ("step", "amount")}
            st.write(f"**{step['step']}** → ₹{step.get('amount', 0):,}  ", extra)

    if d.notes:
        with st.expander("Notes"):
            for n in d.notes:
                st.write(f"- {n}")


def render_trace(trace: Trace) -> None:
    st.subheader("Decision trace")
    st.caption(f"Claim {trace.claim_id} · {len(trace.steps)} steps")
    for s in trace.steps:
        emoji = _STATUS_EMOJI.get(s.status.value, "•")
        header = f"{emoji} [{s.stage}] {s.component} — {s.status.value} ({s.duration_ms} ms)"
        with st.expander(header, expanded=s.status.value in ("FAIL", "ERROR", "FLAG")):
            if s.error:
                st.error(s.error)
            if s.reasons:
                st.write("**Reasons:**", "; ".join(s.reasons))
            if s.confidence_delta:
                st.write(f"**Confidence delta:** {s.confidence_delta:+.2f}")
            if s.input_summary:
                st.write("**Input:**", s.input_summary)
            if s.output_summary:
                st.write("**Output:**", s.output_summary)
