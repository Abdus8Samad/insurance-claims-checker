"""Financial calculation (deterministic, order-sensitive).

Order is mandated by the policy and the test cases:
    covered_base  →  network discount (if network hospital)  →  co-pay  →  annual cap

Network discount is applied BEFORE co-pay (TC010: 4500 → ×0.8 = 3600 → ×0.9 = 3240).
All money is integer rupees; intermediate results round half-up to the nearest rupee.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ...models import CheckResult, CheckStatus
from .base import AdjudicationContext, Check, covered_base


def _round(x: Decimal) -> int:
    return int(x.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class FinancialCheck(Check):
    name = "financial"
    critical = True

    def run(self, ctx: AdjudicationContext) -> CheckResult:
        category = ctx.claim.claim_category
        base = covered_base(ctx)
        steps: list[dict] = [{"step": "covered_base", "amount": base}]

        # 1) network discount
        hospital = ctx.claim.hospital_name or self._hospital_from_docs(ctx)
        is_network = ctx.policy.is_network_hospital(hospital)
        disc_pct = ctx.policy.network_discount_percent(category) if is_network else 0
        after_discount = base
        if disc_pct:
            after_discount = _round(Decimal(base) * (Decimal(100 - disc_pct) / Decimal(100)))
        steps.append({
            "step": "network_discount", "hospital": hospital, "is_network": is_network,
            "discount_percent": disc_pct, "amount": after_discount,
        })

        # 2) co-pay
        copay_pct = ctx.policy.copay_percent(category)
        after_copay = after_discount
        copay_deducted = 0
        if copay_pct:
            after_copay = _round(Decimal(after_discount) * (Decimal(100 - copay_pct) / Decimal(100)))
            copay_deducted = after_discount - after_copay
        steps.append({
            "step": "copay", "copay_percent": copay_pct,
            "copay_deducted": copay_deducted, "amount": after_copay,
        })

        # 3) annual OPD remaining cap (soft cap)
        annual_remaining = ctx.policy.annual_opd_limit - ctx.claim.ytd_claims_amount
        payable = after_copay
        annual_capped = False
        if payable > annual_remaining:
            payable = max(0, annual_remaining)
            annual_capped = True
        steps.append({
            "step": "annual_cap", "annual_opd_limit": ctx.policy.annual_opd_limit,
            "ytd_claims_amount": ctx.claim.ytd_claims_amount,
            "annual_remaining": annual_remaining, "capped": annual_capped, "amount": payable,
        })

        return CheckResult(
            name=self.name, status=CheckStatus.PASS, critical=True,
            data={"payable": payable, "covered_base": base, "breakdown": steps},
        )

    @staticmethod
    def _hospital_from_docs(ctx: AdjudicationContext) -> str | None:
        for doc in ctx.extracted:
            content = getattr(doc, "content", {}) or {}
            name = content.get("hospital_name")
            if name:
                return name
        return None
