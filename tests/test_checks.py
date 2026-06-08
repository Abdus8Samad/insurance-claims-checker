"""Unit tests for individual adjudication checks."""

from datetime import date

from claims.models import CheckStatus, ClaimCategory, LineItem, RejectionReason
from claims.pipeline.checks.coverage import CoverageCheck
from claims.pipeline.checks.exclusions import ExclusionCheck
from claims.pipeline.checks.financial import FinancialCheck
from claims.pipeline.checks.fraud import FraudCheck
from claims.pipeline.checks.limits import LimitCheck
from claims.pipeline.checks.pre_auth import PreAuthCheck
from claims.pipeline.checks.waiting_period import WaitingPeriodCheck
from claims.roster import Member

from conftest import make_ctx
from claims.models import ClaimHistoryEntry


# ── waiting period (TC005) ──
def test_waiting_period_diabetes_rejects_and_states_eligible_date(policy, mapper):
    member = Member(member_id="EMP005", name="Vikram Joshi", join_date=date(2024, 9, 1))
    ctx = make_ctx(policy, mapper, member=member, treatment_date=date(2024, 10, 15),
                   diagnoses=["Type 2 Diabetes Mellitus"])
    res = WaitingPeriodCheck().run(ctx)
    assert res.status == CheckStatus.FAIL
    assert RejectionReason.WAITING_PERIOD.value in res.reasons
    assert res.data["eligible_from"] == "2024-11-30"  # 2024-09-01 + 90 days
    assert "2024-11-30" in res.user_facing_note


def test_waiting_period_passes_for_unrelated_diagnosis(policy, mapper):
    ctx = make_ctx(policy, mapper, diagnoses=["Viral Fever"])
    assert WaitingPeriodCheck().run(ctx).status == CheckStatus.PASS


# ── exclusions (TC012) ──
def test_exclusion_obesity_bariatric(policy, mapper):
    ctx = make_ctx(policy, mapper, diagnoses=["Morbid Obesity — BMI 37"],
                   treatments=["Bariatric Consultation and Customised Diet Plan"])
    res = ExclusionCheck().run(ctx)
    assert res.status == CheckStatus.FAIL
    assert RejectionReason.EXCLUDED_CONDITION.value in res.reasons


def test_exclusion_passes_for_covered_condition(policy, mapper):
    ctx = make_ctx(policy, mapper, diagnoses=["Viral Fever"])
    assert ExclusionCheck().run(ctx).status == CheckStatus.PASS


# ── pre-auth (TC007) ──
def test_pre_auth_missing_for_mri(policy, mapper):
    ctx = make_ctx(policy, mapper, category=ClaimCategory.DIAGNOSTIC, claimed_amount=15000,
                   tests=["MRI Lumbar Spine"],
                   line_items=[LineItem(description="MRI Lumbar Spine", amount=15000)])
    res = PreAuthCheck().run(ctx)
    assert res.status == CheckStatus.FAIL
    assert RejectionReason.PRE_AUTH_MISSING.value in res.reasons
    assert "pre-auth" in res.user_facing_note.lower()


def test_pre_auth_not_applicable_for_consultation(policy, mapper):
    ctx = make_ctx(policy, mapper, category=ClaimCategory.CONSULTATION)
    assert PreAuthCheck().run(ctx).status == CheckStatus.PASS


# ── coverage / line items (TC006) ──
def test_coverage_dental_partial(policy, mapper):
    items = [
        LineItem(description="Root Canal Treatment", amount=8000),
        LineItem(description="Teeth Whitening", amount=4000),
    ]
    ctx = make_ctx(policy, mapper, category=ClaimCategory.DENTAL, claimed_amount=12000, line_items=items)
    res = CoverageCheck().run(ctx)
    assert items[0].covered is True
    assert items[1].covered is False
    assert len(res.data["excluded_items"]) == 1
    assert res.data["excluded_items"][0]["description"] == "Teeth Whitening"


# ── limits (TC008 reject vs TC006 dental allowed) ──
def test_limit_consultation_rejects_over_per_claim(policy, mapper):
    items = [LineItem(description="Consultation Fee", amount=2000),
             LineItem(description="Medicines", amount=5500)]
    ctx = make_ctx(policy, mapper, category=ClaimCategory.CONSULTATION, claimed_amount=7500, line_items=items)
    # mark all covered (coverage runs first in the pipeline)
    for li in items:
        li.covered = True
    res = LimitCheck().run(ctx)
    assert res.status == CheckStatus.FAIL
    assert RejectionReason.PER_CLAIM_EXCEEDED.value in res.reasons
    assert "5,000" in res.user_facing_note and "7,500" in res.user_facing_note


def test_limit_dental_8000_allowed(policy, mapper):
    items = [LineItem(description="Root Canal Treatment", amount=8000, covered=True)]
    ctx = make_ctx(policy, mapper, category=ClaimCategory.DENTAL, claimed_amount=8000, line_items=items)
    assert LimitCheck().run(ctx).status == CheckStatus.PASS


# ── financial (TC004, TC010 + order proof) ──
def test_financial_consultation_copay_only(policy, mapper):
    ctx = make_ctx(policy, mapper, category=ClaimCategory.CONSULTATION, claimed_amount=1500)
    res = FinancialCheck().run(ctx)
    assert res.data["payable"] == 1350  # 1500 - 10%


def test_financial_network_discount_before_copay(policy, mapper):
    ctx = make_ctx(policy, mapper, category=ClaimCategory.CONSULTATION, claimed_amount=4500,
                   hospital_name="Apollo Hospitals")
    res = FinancialCheck().run(ctx)
    assert res.data["payable"] == 3240  # 4500 ×0.8 = 3600 ×0.9 = 3240
    steps = {s["step"]: s for s in res.data["breakdown"]}
    assert steps["network_discount"]["amount"] == 3600  # discount applied first


def test_financial_order_is_observable_with_cap(policy, mapper):
    # Prove discount-before-copay even though percentages commute: a category whose
    # discount makes the amount cross no cap still records the discount step first.
    ctx = make_ctx(policy, mapper, category=ClaimCategory.CONSULTATION, claimed_amount=4500,
                   hospital_name="Apollo Hospitals")
    steps = [s["step"] for s in FinancialCheck().run(ctx).data["breakdown"]]
    assert steps.index("network_discount") < steps.index("copay")


# ── fraud (TC009) ──
def test_fraud_same_day_routes_to_manual_review(policy, mapper):
    history = [
        ClaimHistoryEntry(claim_id="CLM_0081", date=date(2024, 10, 30), amount=1200),
        ClaimHistoryEntry(claim_id="CLM_0082", date=date(2024, 10, 30), amount=1800),
        ClaimHistoryEntry(claim_id="CLM_0083", date=date(2024, 10, 30), amount=2100),
    ]
    ctx = make_ctx(policy, mapper, category=ClaimCategory.CONSULTATION, claimed_amount=4800,
                   treatment_date=date(2024, 10, 30), claims_history=history)
    res = FraudCheck().run(ctx)
    assert res.status == CheckStatus.FLAG
    assert res.data["same_day_count"] == 4
    assert res.data["manual_review"] is True
    assert res.critical is False  # non-critical → skippable on degradation
