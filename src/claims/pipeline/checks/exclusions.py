"""Whole-claim exclusion check (operates on diagnosis/treatment, not line items).

A globally-excluded *condition* rejects the entire claim with EXCLUDED_CONDITION.
Line-item-level exclusions (e.g. one cosmetic dental procedure) are handled by the
coverage check, which can yield PARTIAL.
"""

from __future__ import annotations

from ...models import CheckResult, CheckStatus, RejectionReason
from .base import AdjudicationContext, Check


class ExclusionCheck(Check):
    name = "exclusions"
    critical = True

    def run(self, ctx: AdjudicationContext) -> CheckResult:
        mapping = ctx.mapper.map_exclusion(ctx.diagnoses + ctx.treatments, ctx.claim.claim_category)
        confidence_delta = 0.0 if mapping.confidence >= 0.8 else -0.10

        if mapping.matched:
            return CheckResult(
                name=self.name, status=CheckStatus.FAIL, critical=True,
                reasons=[RejectionReason.EXCLUDED_CONDITION.value],
                data={"matched_exclusion": mapping.matched, "method": mapping.method},
                confidence_delta=confidence_delta,
                user_facing_note=(
                    f"This claim relates to '{mapping.matched}', which is explicitly excluded "
                    f"under your policy and cannot be reimbursed."
                ),
            )
        return CheckResult(name=self.name, status=CheckStatus.PASS,
                           data={"matched_exclusion": None}, confidence_delta=confidence_delta)
