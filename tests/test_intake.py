"""Intake validation: member/policy/amount/currency/deadline gates."""

from datetime import date

from claims.models import CheckStatus, ClaimCategory, ClaimInput, RejectionReason
from claims.pipeline.intake import IntakeValidator


def _claim(policy, **over):
    base = dict(
        member_id="EMP001", policy_id=policy.policy_id, claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 1), claimed_amount=1500,
    )
    base.update(over)
    return ClaimInput(**base)


def test_intake_passes_clean_claim(policy, roster):
    v = IntakeValidator(policy, roster)
    res, member = v.run(_claim(policy), as_of_date=date(2024, 11, 1))
    assert res.status == CheckStatus.PASS
    assert member is not None and member.member_id == "EMP001"


def test_intake_currency_mismatch(policy, roster):
    v = IntakeValidator(policy, roster)
    res, _ = v.run(_claim(policy, currency="USD"), as_of_date=date(2024, 11, 1))
    assert res.status == CheckStatus.FAIL
    assert RejectionReason.INTAKE_INVALID.value in res.reasons
    assert "USD" in res.user_facing_note and "INR" in res.user_facing_note


def test_intake_default_currency_is_inr(policy, roster):
    # currency omitted → defaults to INR → matches the policy
    v = IntakeValidator(policy, roster)
    res, _ = v.run(_claim(policy), as_of_date=date(2024, 11, 1))
    assert res.status == CheckStatus.PASS


def test_intake_unknown_member(policy, roster):
    v = IntakeValidator(policy, roster)
    res, member = v.run(_claim(policy, member_id="EMP999"), as_of_date=date(2024, 11, 1))
    assert res.status == CheckStatus.FAIL
    assert member is None


def test_intake_below_minimum(policy, roster):
    v = IntakeValidator(policy, roster)
    res, _ = v.run(_claim(policy, claimed_amount=100), as_of_date=date(2024, 11, 1))
    assert res.status == CheckStatus.FAIL


def test_intake_past_deadline(policy, roster):
    v = IntakeValidator(policy, roster)
    # 40 days after treatment, deadline is 30
    res, _ = v.run(_claim(policy), as_of_date=date(2024, 12, 11))
    assert res.status == CheckStatus.FAIL
