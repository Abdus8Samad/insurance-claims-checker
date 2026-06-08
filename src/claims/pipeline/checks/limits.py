"""Per-claim limit check (deterministic, hard rejection).

The binding ceiling for a category is max(category sub_limit, global per_claim_limit) —
the single rule that reconciles the test ground truth (consultation binds on the ₹5,000
per-claim limit; dental binds on its ₹10,000 sub-limit). If the covered amount exceeds
the ceiling, the claim is rejected with PER_CLAIM_EXCEEDED.
"""

from __future__ import annotations

from ...models import CheckResult, CheckStatus, RejectionReason
from .base import AdjudicationContext, Check, covered_base


class LimitCheck(Check):
    name = "limits"
    critical = True

    def run(self, ctx: AdjudicationContext) -> CheckResult:
        category = ctx.claim.claim_category
        ceiling = ctx.policy.effective_claim_ceiling(category)
        source = ctx.policy.ceiling_source(category)
        base = covered_base(ctx)
        binding_limit = (
            ctx.policy.per_claim_limit if source == "per_claim_limit" else ctx.policy.sub_limit(category)
        )

        data = {
            "covered_amount": base,
            "claimed_amount": ctx.claim.claimed_amount,
            "effective_ceiling": ceiling,
            "binding_limit": source,
            "binding_limit_value": binding_limit,
        }

        if base > ceiling:
            if source == "per_claim_limit":
                note = (
                    f"The claimed amount of ₹{ctx.claim.claimed_amount:,} exceeds the per-claim limit "
                    f"of ₹{ctx.policy.per_claim_limit:,} for this policy. The claim cannot be approved as submitted."
                )
            else:
                note = (
                    f"The covered amount of ₹{base:,} exceeds the {category.value} sub-limit of "
                    f"₹{binding_limit:,}. The claim cannot be approved as submitted."
                )
            return CheckResult(
                name=self.name, status=CheckStatus.FAIL, critical=True,
                reasons=[RejectionReason.PER_CLAIM_EXCEEDED.value], data=data,
                user_facing_note=note,
            )
        return CheckResult(name=self.name, status=CheckStatus.PASS, data=data)
