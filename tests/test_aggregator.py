"""Precedence + confidence tests for the decision aggregator."""

from datetime import date

from claims.models import (
    CheckResult,
    CheckStatus,
    ClaimCategory,
    ClaimInput,
    Decision,
    GateResult,
    GateFailureKind,
    LineItem,
)
from claims.pipeline.aggregator import AggregationInput, aggregate


def _claim(policy, amount=1500, category=ClaimCategory.CONSULTATION):
    return ClaimInput(member_id="EMP001", policy_id=policy.policy_id, claim_category=category,
                      treatment_date=date(2024, 11, 1), claimed_amount=amount)


def _ok_intake():
    return CheckResult(name="intake", status=CheckStatus.PASS)


def _financial(payable):
    return CheckResult(name="financial", status=CheckStatus.PASS, data={"payable": payable, "breakdown": []})


def test_gate_failure_yields_null_decision(policy):
    gate = GateResult(passed=False, failure_kind=GateFailureKind.MISSING_DOC, user_message="missing bill")
    d = aggregate(AggregationInput(claim=_claim(policy), policy=policy, gate=gate,
                                   intake=_ok_intake(), checks={}, line_items=[]), "C1")
    assert d.decision is None
    assert d.status == Decision.NEEDS_RESUBMISSION
    assert d.user_message == "missing bill"


def test_hard_rejection_beats_manual_review(policy):
    # both a per-claim hard rejection AND a fraud flag are present → REJECTED wins.
    checks = {
        "limits": CheckResult(name="limits", status=CheckStatus.FAIL, reasons=["PER_CLAIM_EXCEEDED"],
                              user_facing_note="over limit"),
        "fraud": CheckResult(name="fraud", status=CheckStatus.FLAG, critical=False,
                             data={"manual_review": True, "signals": ["same-day x4"]}),
        "financial": _financial(0),
    }
    d = aggregate(AggregationInput(claim=_claim(policy, 7500), policy=policy, gate=GateResult(passed=True),
                                   intake=_ok_intake(), checks=checks, line_items=[]), "C2")
    assert d.decision == Decision.REJECTED
    assert "PER_CLAIM_EXCEEDED" in d.reasons


def test_fraud_flag_routes_to_manual_review(policy):
    checks = {
        "fraud": CheckResult(name="fraud", status=CheckStatus.FLAG, critical=False,
                             data={"manual_review": True, "signals": ["same-day x4"]}),
        "financial": _financial(4320),
    }
    d = aggregate(AggregationInput(claim=_claim(policy, 4800), policy=policy, gate=GateResult(passed=True),
                                   intake=_ok_intake(), checks=checks, line_items=[]), "C3")
    assert d.decision == Decision.MANUAL_REVIEW
    assert d.fraud_signals == ["same-day x4"]


def test_partial_when_some_items_excluded(policy):
    items = [LineItem(description="Root Canal", amount=8000, covered=True),
             LineItem(description="Whitening", amount=4000, covered=False, rejection_reason="excluded")]
    checks = {
        "coverage": CheckResult(name="coverage", status=CheckStatus.FLAG,
                                data={"excluded_items": [{"description": "Whitening", "amount": 4000,
                                                          "reason": "excluded"}]}),
        "financial": _financial(8000),
    }
    d = aggregate(AggregationInput(claim=_claim(policy, 12000, ClaimCategory.DENTAL), policy=policy,
                                   gate=GateResult(passed=True), intake=_ok_intake(),
                                   checks=checks, line_items=items), "C4")
    assert d.decision == Decision.PARTIAL
    assert d.approved_amount == 8000


def test_clean_approval(policy):
    checks = {
        "coverage": CheckResult(name="coverage", status=CheckStatus.PASS, data={"excluded_items": []}),
        "financial": _financial(1350),
    }
    d = aggregate(AggregationInput(claim=_claim(policy), policy=policy, gate=GateResult(passed=True),
                                   intake=_ok_intake(), checks=checks, line_items=[]), "C5")
    assert d.decision == Decision.APPROVED
    assert d.approved_amount == 1350
    assert d.confidence_score > 0.85


def test_degradation_lowers_confidence_keeps_decision(policy):
    checks = {
        "coverage": CheckResult(name="coverage", status=CheckStatus.PASS, data={"excluded_items": []}),
        "financial": _financial(4000),
    }
    d = aggregate(AggregationInput(claim=_claim(policy, 4000, ClaimCategory.ALTERNATIVE_MEDICINE),
                                   policy=policy, gate=GateResult(passed=True), intake=_ok_intake(),
                                   checks=checks, line_items=[], degraded_components=["fraud"],
                                   critical_degraded=False), "C6")
    assert d.decision == Decision.APPROVED  # non-critical degradation does not force MANUAL_REVIEW
    assert d.degraded is True
    assert d.confidence_score < 0.95
    assert any("manual review" in n.lower() for n in d.notes)


def test_critical_degradation_forces_manual_review(policy):
    checks = {"financial": _financial(1000)}
    d = aggregate(AggregationInput(claim=_claim(policy), policy=policy, gate=GateResult(passed=True),
                                   intake=_ok_intake(), checks=checks, line_items=[],
                                   degraded_components=["limits"], critical_degraded=True), "C7")
    assert d.decision == Decision.MANUAL_REVIEW
