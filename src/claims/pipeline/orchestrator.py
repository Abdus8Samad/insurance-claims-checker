"""Orchestrator — runs the staged pipeline, accumulates a trace, and degrades gracefully.

Every component call is wrapped so an exception becomes an ERROR trace step and the
pipeline continues. A failed NON-critical check (e.g. fraud) reduces confidence and adds
an advisory note but leaves the decision intact; a failed CRITICAL check forces
MANUAL_REVIEW. The orchestrator NEVER raises to its caller — it always returns a
(ClaimDecision, Trace).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from ..config import AppConfig
from ..extraction.base import ExtractorBase
from ..llm.semantic_mapper import SemanticMapper
from ..models import (
    CheckResult,
    CheckStatus,
    ClaimDecision,
    ClaimInput,
    Decision,
    ExtractedDocument,
    LineItem,
    Trace,
    TraceStep,
)
from ..policy import PolicyConfig
from ..roster import MemberRoster
from .aggregator import AggregationInput, aggregate
from .checks.base import AdjudicationContext, Check
from .checks.coverage import CoverageCheck
from .checks.exclusions import ExclusionCheck
from .checks.financial import FinancialCheck
from .checks.fraud import FraudCheck
from .checks.limits import LimitCheck
from .checks.pre_auth import PreAuthCheck
from .checks.waiting_period import WaitingPeriodCheck
from .document_verifier import DocumentVerifier
from .intake import IntakeValidator

# Adjudication order. Coverage runs before limits/financial (which need covered amounts).
CHECK_ORDER: list[type[Check]] = [
    WaitingPeriodCheck,
    ExclusionCheck,
    PreAuthCheck,
    CoverageCheck,
    LimitCheck,
    FinancialCheck,
    FraudCheck,
]


class _ForcedFailure(Exception):
    """Raised by the failure injector to exercise the real degradation path (TC011)."""


class Orchestrator:
    def __init__(
        self,
        policy: PolicyConfig,
        roster: MemberRoster,
        extractor: ExtractorBase,
        mapper: SemanticMapper,
        config: Optional[AppConfig] = None,
    ):
        self.policy = policy
        self.roster = roster
        self.extractor = extractor
        self.mapper = mapper
        self.config = config or AppConfig()
        self.intake = IntakeValidator(policy, roster)
        self.gate = DocumentVerifier(policy)

    def process(self, claim: ClaimInput) -> tuple[ClaimDecision, Trace]:
        claim_id = f"CLM_{uuid.uuid4().hex[:10]}"
        trace = Trace(claim_id=claim_id, case_id=claim.case_id, created_at=datetime.now())
        as_of = self.config.as_of_date or claim.treatment_date

        # S1 — intake
        intake_tuple = self._step(
            trace, "intake", "IntakeValidator",
            lambda: self.intake.run(claim, as_of),
        )
        if intake_tuple is None:  # intake itself errored
            intake_result = CheckResult(name="intake", status=CheckStatus.FAIL,
                                        reasons=["INTAKE_INVALID"], user_facing_note="Intake validation failed.")
            member = None
        else:
            intake_result, member = intake_tuple
        if intake_result.status == CheckStatus.FAIL or member is None:
            decision = aggregate(
                AggregationInput(claim=claim, policy=self.policy, gate=None, intake=intake_result,
                                 checks={}, line_items=[]),
                claim_id,
            )
            trace.final_decision = decision
            return decision, trace

        # S2 — extraction / normalization
        extracted: list[ExtractedDocument] = []
        for doc in claim.documents:
            res = self._step(
                trace, "extraction", f"Extractor[{doc.file_id}]",
                lambda d=doc: self.extractor.classify_and_extract(d, claim.claim_category),
                input_summary={"file_id": doc.file_id, "declared_type": doc.actual_type},
            )
            if isinstance(res, ExtractedDocument):
                extracted.append(res)

        # S3 — document verification gate
        gate_result = self._step(
            trace, "document_verification", "DocumentVerifier",
            lambda: self.gate.run(extracted, claim.claim_category),
        )
        if gate_result is not None and not gate_result.passed:
            decision = aggregate(
                AggregationInput(claim=claim, policy=self.policy, gate=gate_result,
                                 intake=intake_result, checks={}, line_items=[], extracted=extracted),
                claim_id,
            )
            trace.final_decision = decision
            return decision, trace

        # S4 — adjudication
        line_items = _derive_line_items(extracted, claim)
        ctx = AdjudicationContext(
            claim=claim, member=member, policy=self.policy, extracted=extracted,
            line_items=line_items, mapper=self.mapper, as_of_date=as_of,
            diagnoses=_collect(extracted, ["diagnosis"]),
            treatments=_collect(extracted, ["treatment"]),
            tests=_collect_tests(extracted),
        )

        checks: dict[str, CheckResult] = {}
        degraded_components: list[str] = []
        critical_degraded = False
        for check_cls in CHECK_ORDER:
            check = check_cls()
            res = self._run_check(trace, check, ctx, claim)
            if res is None:  # the check errored
                degraded_components.append(check.name)
                if check.critical:
                    critical_degraded = True
            else:
                checks[check.name] = res

        # S5 — aggregate
        decision = aggregate(
            AggregationInput(
                claim=claim, policy=self.policy, gate=gate_result, intake=intake_result,
                checks=checks, line_items=line_items, extracted=extracted,
                degraded_components=degraded_components, critical_degraded=critical_degraded,
            ),
            claim_id,
        )
        trace.final_decision = decision
        return decision, trace

    # ── trace-wrapped execution ──
    def _run_check(self, trace: Trace, check: Check, ctx: AdjudicationContext, claim: ClaimInput):
        def call():
            if claim.simulate_component_failure and check.name == "fraud":
                raise _ForcedFailure("Simulated failure of the fraud component (TC011)")
            return check.run(ctx)

        return self._step(trace, "adjudication", check.__class__.__name__, call,
                          input_summary={"check": check.name, "critical": check.critical})

    def _step(self, trace: Trace, stage: str, component: str, fn,
              input_summary: Optional[dict] = None) -> Any:
        started = datetime.now()
        try:
            result = fn()
            ended = datetime.now()
            trace.steps.append(TraceStep(
                stage=stage, component=component, status=_status_of(result),
                started_at=started, ended_at=ended,
                duration_ms=int((ended - started).total_seconds() * 1000),
                input_summary=input_summary or {},
                output_summary=_summarize(result),
                reasons=getattr(result, "reasons", []) if hasattr(result, "reasons") else [],
                confidence_delta=getattr(result, "confidence_delta", 0.0),
            ))
            return result
        except Exception as exc:  # graceful degradation: record and continue
            ended = datetime.now()
            trace.steps.append(TraceStep(
                stage=stage, component=component, status=CheckStatus.ERROR,
                started_at=started, ended_at=ended,
                duration_ms=int((ended - started).total_seconds() * 1000),
                input_summary=input_summary or {},
                error=f"{type(exc).__name__}: {exc}",
            ))
            return None


# ── helpers ──

def _status_of(result: Any) -> CheckStatus:
    if isinstance(result, CheckResult):
        return result.status
    if hasattr(result, "passed"):  # GateResult
        return CheckStatus.PASS if result.passed else CheckStatus.FAIL
    if isinstance(result, tuple) and result and isinstance(result[0], CheckResult):
        return result[0].status
    return CheckStatus.PASS


def _summarize(result: Any) -> dict:
    if isinstance(result, CheckResult):
        return {"status": result.status.value, "data": result.data}
    if hasattr(result, "passed"):
        return {"passed": result.passed, "failure_kind": getattr(result.failure_kind, "value", None),
                "message": result.user_message}
    if isinstance(result, ExtractedDocument):
        return {"doc_type": result.doc_type.value, "quality": result.quality.value,
                "patient_name": result.patient_name}
    if isinstance(result, tuple) and result and isinstance(result[0], CheckResult):
        return {"status": result[0].status.value, "data": result[0].data}
    return {}


def _collect(extracted: list[ExtractedDocument], keys: list[str]) -> list[str]:
    out: list[str] = []
    for d in extracted:
        for k in keys:
            v = (d.content or {}).get(k)
            if isinstance(v, str) and v.strip():
                out.append(v)
            elif isinstance(v, list):
                out.extend(str(x) for x in v)
    return out


def _collect_tests(extracted: list[ExtractedDocument]) -> list[str]:
    out: list[str] = []
    for d in extracted:
        c = d.content or {}
        for k in ("tests_ordered", "investigations"):
            v = c.get(k)
            if isinstance(v, list):
                out.extend(str(x) for x in v)
            elif isinstance(v, str):
                out.append(v)
        tn = c.get("test_name")
        if isinstance(tn, str):
            out.append(tn)
    return out


def _derive_line_items(extracted: list[ExtractedDocument], claim: ClaimInput) -> list[LineItem]:
    items: list[LineItem] = []
    for d in extracted:
        for li in (d.content or {}).get("line_items", []) or []:
            if isinstance(li, dict) and "description" in li:
                items.append(LineItem(description=str(li["description"]), amount=int(li.get("amount", 0))))
    return items
