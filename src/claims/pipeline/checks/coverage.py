"""Line-item coverage / itemization check.

Classifies each billed line item as covered or excluded (LLM/mapper) and records the
per-line reason. The financial check sums only covered items; a mix of covered and
excluded items drives a PARTIAL decision in the aggregator.
"""

from __future__ import annotations

from ...models import CheckResult, CheckStatus
from .base import AdjudicationContext, Check


class CoverageCheck(Check):
    name = "coverage"
    critical = True

    def run(self, ctx: AdjudicationContext) -> CheckResult:
        if not ctx.line_items:
            return CheckResult(name=self.name, status=CheckStatus.PASS,
                               data={"line_items": 0, "note": "no itemized lines; using claimed amount"})

        excluded, covered = [], []
        min_conf = 1.0
        for li in ctx.line_items:
            cls = ctx.mapper.classify_line_item(li.description, ctx.claim.claim_category)
            li.covered = cls.covered
            li.mapped_to = cls.matched
            li.map_confidence = cls.confidence
            li.rejection_reason = None if cls.covered else cls.reason
            min_conf = min(min_conf, cls.confidence)
            (covered if cls.covered else excluded).append(li)

        confidence_delta = 0.0 if min_conf >= 0.8 else -0.10
        status = CheckStatus.FLAG if excluded else CheckStatus.PASS
        return CheckResult(
            name=self.name, status=status, critical=True,
            reasons=[f"Excluded: {li.description} — {li.rejection_reason}" for li in excluded],
            data={
                "covered_items": [{"description": li.description, "amount": li.amount} for li in covered],
                "excluded_items": [
                    {"description": li.description, "amount": li.amount, "reason": li.rejection_reason}
                    for li in excluded
                ],
                "min_map_confidence": min_conf,
            },
            confidence_delta=confidence_delta,
        )
