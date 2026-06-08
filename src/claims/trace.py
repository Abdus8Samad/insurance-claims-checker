"""Trace rendering helpers — turn a Trace/ClaimDecision into dict, JSON, and Markdown.

The trace is the observability artifact: someone on operations must be able to
reconstruct exactly why a claim got its decision from this alone.
"""

from __future__ import annotations

import json
from typing import Any

from .models import ClaimDecision, Trace


def trace_to_dict(trace: Trace) -> dict[str, Any]:
    return json.loads(trace.model_dump_json())


def decision_to_dict(decision: ClaimDecision) -> dict[str, Any]:
    return json.loads(decision.model_dump_json())


def trace_to_markdown(trace: Trace) -> str:
    d = trace.final_decision
    lines: list[str] = []
    lines.append(f"### Claim `{trace.claim_id}`" + (f" — case {trace.case_id}" if trace.case_id else ""))
    if d:
        dec = d.decision.value if d.decision else "null (NEEDS_RESUBMISSION)"
        lines.append("")
        lines.append(f"- **Decision:** {dec}")
        lines.append(f"- **Approved amount:** ₹{d.approved_amount:,}")
        lines.append(f"- **Confidence:** {d.confidence_score:.2f}")
        if d.reasons:
            lines.append(f"- **Reasons:** {', '.join(d.reasons)}")
        if d.fraud_signals:
            lines.append(f"- **Fraud signals:** {'; '.join(d.fraud_signals)}")
        if d.degraded:
            lines.append(f"- **Degraded:** yes")
        if d.user_message:
            lines.append(f"- **Member message:** {d.user_message}")
        if d.notes:
            lines.append(f"- **Notes:** {' '.join(d.notes)}")

    # line items
    if d and d.line_item_breakdown:
        lines.append("")
        lines.append("| Line item | Amount | Covered | Reason |")
        lines.append("|---|---:|---|---|")
        for li in d.line_item_breakdown:
            cov = "✓" if li.covered else ("✗" if li.covered is False else "—")
            lines.append(f"| {li.description} | ₹{li.amount:,} | {cov} | {li.rejection_reason or ''} |")

    # financial breakdown
    if d and d.financial_breakdown.get("breakdown"):
        lines.append("")
        lines.append("**Financial breakdown:**")
        for step in d.financial_breakdown["breakdown"]:
            lines.append(f"- `{step.get('step')}` → ₹{step.get('amount'):,}  " +
                         json.dumps({k: v for k, v in step.items() if k not in ('step', 'amount')}))

    # trace steps
    lines.append("")
    lines.append("**Trace:**")
    lines.append("")
    lines.append("| Stage | Component | Status | ms | Reasons / Error |")
    lines.append("|---|---|---|---:|---|")
    for s in trace.steps:
        detail = s.error or "; ".join(s.reasons)
        lines.append(f"| {s.stage} | {s.component} | {s.status.value} | {s.duration_ms} | {detail} |")
    return "\n".join(lines)
