"""Orchestrator integration: graceful degradation (TC011) and gate short-circuit."""

from datetime import date

from claims.config import AppConfig
from claims.extraction.injected import InjectedExtractor
from claims.llm.semantic_mapper import KeywordSemanticMapper
from claims.models import (
    CheckStatus,
    ClaimCategory,
    ClaimInput,
    Decision,
    DocumentDescriptor,
    DocumentType,
)
from claims.pipeline.orchestrator import Orchestrator


def _orch(policy, roster, treatment_date):
    return Orchestrator(
        policy=policy, roster=roster, extractor=InjectedExtractor(),
        mapper=KeywordSemanticMapper(policy), config=AppConfig(as_of_date=treatment_date),
    )


def test_tc011_component_failure_degrades_not_crash(policy, roster):
    claim = ClaimInput(
        member_id="EMP006", policy_id=policy.policy_id, claim_category=ClaimCategory.ALTERNATIVE_MEDICINE,
        treatment_date=date(2024, 10, 28), claimed_amount=4000, simulate_component_failure=True,
        documents=[
            DocumentDescriptor(file_id="F021", actual_type=DocumentType.PRESCRIPTION,
                               content={"diagnosis": "Chronic Joint Pain", "treatment": "Panchakarma Therapy"}),
            DocumentDescriptor(file_id="F022", actual_type=DocumentType.HOSPITAL_BILL,
                               content={"total": 4000, "line_items": [
                                   {"description": "Panchakarma Therapy (5 sessions)", "amount": 3000},
                                   {"description": "Consultation", "amount": 1000}]}),
        ],
    )
    decision, trace = _orch(policy, roster, claim.treatment_date).process(claim)

    assert decision.decision == Decision.APPROVED  # not a crash, not auto-reject
    assert decision.degraded is True
    assert decision.approved_amount == 4000
    assert decision.confidence_score < 0.95
    assert any("manual review" in n.lower() for n in decision.notes)
    # the fraud step is recorded as ERROR in the trace (failure is visible)
    assert any(s.component.endswith("FraudCheck") and s.status == CheckStatus.ERROR for s in trace.steps)


def test_gate_failure_short_circuits_before_adjudication(policy, roster):
    claim = ClaimInput(
        member_id="EMP001", policy_id=policy.policy_id, claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 1), claimed_amount=1500,
        documents=[
            DocumentDescriptor(file_id="F001", actual_type=DocumentType.PRESCRIPTION),
            DocumentDescriptor(file_id="F002", actual_type=DocumentType.PRESCRIPTION),
        ],
    )
    decision, trace = _orch(policy, roster, claim.treatment_date).process(claim)
    assert decision.decision is None
    assert decision.status == Decision.NEEDS_RESUBMISSION
    # no adjudication steps ran
    assert not any(s.stage == "adjudication" for s in trace.steps)
