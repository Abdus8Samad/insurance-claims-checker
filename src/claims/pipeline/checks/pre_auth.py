"""Pre-authorization check (fully deterministic).

For categories that list high-value tests requiring pre-auth (e.g. DIAGNOSTIC: MRI/CT/
PET), if such a test appears above the pre-auth threshold and no pre-auth reference is
present in the documents, the claim is rejected with PRE_AUTH_MISSING.
"""

from __future__ import annotations

from ...models import CheckResult, CheckStatus, RejectionReason
from .base import AdjudicationContext, Check


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


class PreAuthCheck(Check):
    name = "pre_auth"
    critical = True

    def run(self, ctx: AdjudicationContext) -> CheckResult:
        category = ctx.claim.claim_category
        high_value_tests = ctx.policy.high_value_tests_requiring_pre_auth(category)
        threshold = ctx.policy.pre_auth_threshold(category)

        if not high_value_tests:
            return CheckResult(name=self.name, status=CheckStatus.PASS,
                               data={"applicable": False})

        # Names to scan: ordered tests + billed line-item descriptions.
        names = list(ctx.tests) + [li.description for li in ctx.line_items]
        matched_test = None
        for n in names:
            for hv in high_value_tests:
                if _norm(hv) in _norm(n):
                    matched_test = hv
                    break
            if matched_test:
                break

        if not matched_test:
            return CheckResult(name=self.name, status=CheckStatus.PASS,
                               data={"applicable": True, "high_value_test_found": False})

        over_threshold = threshold is None or ctx.claim.claimed_amount > threshold
        has_pre_auth = self._pre_auth_reference_present(ctx)
        data = {
            "applicable": True,
            "high_value_test_found": matched_test,
            "threshold": threshold,
            "claimed_amount": ctx.claim.claimed_amount,
            "over_threshold": over_threshold,
            "pre_auth_reference_present": has_pre_auth,
        }

        if over_threshold and not has_pre_auth:
            return CheckResult(
                name=self.name, status=CheckStatus.FAIL, critical=True,
                reasons=[RejectionReason.PRE_AUTH_MISSING.value], data=data,
                user_facing_note=(
                    f"{matched_test} above ₹{threshold:,} requires pre-authorization before the "
                    f"procedure, which was not obtained for this claim. To resubmit: obtain pre-authorization "
                    f"from the insurer for the {matched_test}, then submit the claim with the pre-authorization "
                    f"reference number attached."
                ),
            )
        return CheckResult(name=self.name, status=CheckStatus.PASS, data=data)

    @staticmethod
    def _pre_auth_reference_present(ctx: AdjudicationContext) -> bool:
        for doc in ctx.extracted:
            content = getattr(doc, "content", {}) or {}
            keys = " ".join(str(k).lower() for k in content.keys())
            if "pre_auth" in keys or "preauth" in keys or "pre-auth" in keys:
                return True
            for v in content.values():
                if isinstance(v, str) and ("pre-auth" in v.lower() or "pre auth" in v.lower()):
                    return True
        return False
