"""Audit store: write-once per claim, history reads, fraud counts."""

from datetime import date

from claims.audit.store import JsonAuditStore
from claims.models import (
    ClaimCategory,
    ClaimDecision,
    ClaimInput,
    Decision,
    Trace,
)
from datetime import datetime


def _claim(policy, member="EMP001", td=date(2024, 11, 1)):
    return ClaimInput(member_id=member, policy_id=policy.policy_id,
                      claim_category=ClaimCategory.CONSULTATION, treatment_date=td, claimed_amount=1500)


def _decision(claim_id):
    return ClaimDecision(claim_id=claim_id, decision=Decision.APPROVED, status=Decision.APPROVED,
                         approved_amount=1350, confidence_score=0.95)


def test_append_and_list(tmp_path, policy):
    store = JsonAuditStore(tmp_path)
    claim = _claim(policy)
    dec = _decision("CLM_a")
    trace = Trace(claim_id="CLM_a", created_at=datetime.now())
    path = store.append(claim, dec, trace)
    assert path.exists()
    records = store.list_claims("EMP001")
    assert len(records) == 1
    assert records[0]["decision"]["status"] == "APPROVED"


def test_same_day_and_monthly_counts(tmp_path, policy):
    store = JsonAuditStore(tmp_path)
    for i, td in enumerate([date(2024, 11, 1), date(2024, 11, 1), date(2024, 11, 20)]):
        store.append(_claim(policy, td=td), _decision(f"CLM_{i}"),
                     Trace(claim_id=f"CLM_{i}", created_at=datetime.now()))
    assert store.same_day_count("EMP001", date(2024, 11, 1)) == 2
    assert store.monthly_count("EMP001", 2024, 11) == 3
    assert store.same_day_count("EMP001", date(2024, 11, 2)) == 0
