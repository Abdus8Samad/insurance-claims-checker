"""Fraud / anomaly signal check (deterministic, NON-critical).

Counts same-day and monthly claims against policy thresholds and flags high-value
claims. Emits FLAG (never auto-rejects) so the aggregator can route to MANUAL_REVIEW
with the specific triggering signals attached. Being non-critical, this is the
component skipped under graceful-degradation (TC011).
"""

from __future__ import annotations

from ...models import CheckResult, CheckStatus
from .base import AdjudicationContext, Check


class FraudCheck(Check):
    name = "fraud"
    critical = False

    def run(self, ctx: AdjudicationContext) -> CheckResult:
        f = ctx.policy.fraud
        history = ctx.claim.claims_history
        td = ctx.claim.treatment_date

        same_day = sum(1 for h in history if h.date == td) + 1  # + current claim
        monthly = sum(1 for h in history if h.date.year == td.year and h.date.month == td.month) + 1
        claimed = ctx.claim.claimed_amount

        signals: list[str] = []
        score = 0.0

        if same_day > f["same_day_claims_limit"]:
            signals.append(
                f"Same-day claims: {same_day} claims on {td.isoformat()} exceeds the limit of "
                f"{f['same_day_claims_limit']}"
            )
            score = max(score, 0.85)
        if monthly > f["monthly_claims_limit"]:
            signals.append(
                f"Monthly claims: {monthly} claims this month exceeds the limit of {f['monthly_claims_limit']}"
            )
            score = max(score, 0.85)
        if claimed > f["high_value_claim_threshold"]:
            signals.append(f"High-value claim: ₹{claimed:,} exceeds ₹{f['high_value_claim_threshold']:,}")
            score = max(score, 0.6)

        high_value_auto = claimed > f["auto_manual_review_above"]
        score_trigger = score >= f["fraud_score_manual_review_threshold"]
        manual_review = bool(signals) and (score_trigger or high_value_auto or same_day > f["same_day_claims_limit"] or monthly > f["monthly_claims_limit"])
        if high_value_auto:
            manual_review = True

        data = {
            "same_day_count": same_day,
            "monthly_count": monthly,
            "fraud_score": round(score, 2),
            "signals": signals,
            "manual_review": manual_review,
        }
        status = CheckStatus.FLAG if manual_review else CheckStatus.PASS
        return CheckResult(
            name=self.name, status=status, critical=False, reasons=signals, data=data,
            user_facing_note=(
                "This claim was routed to manual review due to unusual activity. " + " ".join(signals)
                if manual_review else None
            ),
        )
