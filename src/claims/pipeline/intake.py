"""Intake validation — the first gate. Member exists, policy matches, amount and
submission window are valid. Hard failures here produce an INTAKE_INVALID rejection
(handled by the orchestrator) rather than proceeding to adjudication.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from ..models import CheckResult, CheckStatus, ClaimInput, RejectionReason
from ..policy import PolicyConfig
from ..roster import Member, MemberRoster


class IntakeValidator:
    name = "intake"

    def __init__(self, policy: PolicyConfig, roster: MemberRoster):
        self.policy = policy
        self.roster = roster

    def run(self, claim: ClaimInput, as_of_date: date) -> tuple[CheckResult, Optional[Member]]:
        reasons: list[str] = []
        data: dict = {}

        member = self.roster.get(claim.member_id) if self.roster.exists(claim.member_id) else None
        if member is None:
            reasons.append(f"Member {claim.member_id} not found in roster")

        if claim.policy_id != self.policy.policy_id:
            reasons.append(
                f"Policy mismatch: claim cites {claim.policy_id}, policy is {self.policy.policy_id}"
            )

        if claim.claimed_amount < self.policy.minimum_claim_amount:
            reasons.append(
                f"Claimed amount ₹{claim.claimed_amount:,} is below the minimum of "
                f"₹{self.policy.minimum_claim_amount:,}"
            )

        if claim.currency != self.policy.currency:
            reasons.append(
                f"Claim currency {claim.currency} does not match the policy currency "
                f"{self.policy.currency}. This policy only reimburses claims in {self.policy.currency}."
            )

        deadline = claim.treatment_date + timedelta(days=self.policy.submission_deadline_days)
        data["submission_deadline"] = deadline.isoformat()
        data["as_of_date"] = as_of_date.isoformat()
        if as_of_date > deadline:
            reasons.append(
                f"Claim submitted on {as_of_date.isoformat()} is past the "
                f"{self.policy.submission_deadline_days}-day deadline ({deadline.isoformat()})"
            )

        if reasons:
            return (
                CheckResult(name=self.name, status=CheckStatus.FAIL, critical=True,
                            reasons=[RejectionReason.INTAKE_INVALID.value], data={**data, "errors": reasons},
                            user_facing_note="; ".join(reasons)),
                member,
            )
        return CheckResult(name=self.name, status=CheckStatus.PASS, data=data), member
