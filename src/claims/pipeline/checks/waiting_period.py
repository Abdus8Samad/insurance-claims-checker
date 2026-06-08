"""Waiting-period eligibility check.

LLM/mapper maps the diagnosis to a policy condition key; the date math (eligible_date =
join_date + waiting_days, compared against treatment_date) is fully deterministic.
"""

from __future__ import annotations

from datetime import timedelta

from ...models import CheckResult, CheckStatus, RejectionReason
from .base import AdjudicationContext, Check


class WaitingPeriodCheck(Check):
    name = "waiting_period"
    critical = True

    def run(self, ctx: AdjudicationContext) -> CheckResult:
        mapping = ctx.mapper.map_waiting_condition(ctx.diagnoses + ctx.treatments)
        confidence_delta = 0.0 if mapping.confidence >= 0.8 else -0.10

        if not mapping.matched:
            return CheckResult(
                name=self.name, status=CheckStatus.PASS, critical=True,
                data={"mapped_condition": None, "method": mapping.method},
                confidence_delta=confidence_delta,
            )

        waiting_days = ctx.policy.specific_waiting_days(mapping.matched)
        if waiting_days is None:
            return CheckResult(name=self.name, status=CheckStatus.PASS,
                               data={"mapped_condition": mapping.matched, "waiting_days": None})

        if ctx.member.join_date is None:
            return CheckResult(
                name=self.name, status=CheckStatus.FLAG, critical=True,
                reasons=["Member join date unknown; cannot verify waiting period"],
                data={"mapped_condition": mapping.matched, "waiting_days": waiting_days},
                confidence_delta=-0.15,
            )

        eligible_date = ctx.member.join_date + timedelta(days=waiting_days)
        in_waiting = ctx.claim.treatment_date < eligible_date
        data = {
            "mapped_condition": mapping.matched,
            "waiting_days": waiting_days,
            "join_date": ctx.member.join_date.isoformat(),
            "treatment_date": ctx.claim.treatment_date.isoformat(),
            "eligible_from": eligible_date.isoformat(),
            "method": mapping.method,
        }
        if in_waiting:
            return CheckResult(
                name=self.name, status=CheckStatus.FAIL, critical=True,
                reasons=[RejectionReason.WAITING_PERIOD.value],
                data=data, confidence_delta=confidence_delta,
                user_facing_note=(
                    f"This claim is for {mapping.matched.replace('_', ' ')}, which has a "
                    f"{waiting_days}-day waiting period from your policy start ({ctx.member.join_date.isoformat()}). "
                    f"You will be eligible for {mapping.matched.replace('_', ' ')}-related claims from "
                    f"{eligible_date.isoformat()}."
                ),
            )
        return CheckResult(name=self.name, status=CheckStatus.PASS, data=data,
                           confidence_delta=confidence_delta)
