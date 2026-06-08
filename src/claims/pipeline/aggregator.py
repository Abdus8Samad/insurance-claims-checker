"""Decision aggregation — applies precedence and computes confidence.

A pure function over collected results. Precedence (highest first):
    Tier 0  gate failure          → decision=null, NEEDS_RESUBMISSION
    Tier 1  hard rejections        → REJECTED  (intake / exclusion / waiting / pre-auth / per-claim)
    Tier 2  manual review          → MANUAL_REVIEW (fraud / high-value / critical degradation)
    Tier 3  partial                → PARTIAL  (some line items excluded, some covered)
    Tier 4  approved               → APPROVED

Hard rejection beats manual review: a categorically-ineligible claim is not worth a
reviewer's time, and the fraud signal is still recorded in the trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..models import (
    CheckResult,
    CheckStatus,
    ClaimDecision,
    ClaimInput,
    Decision,
    GateResult,
    LineItem,
)
from ..policy import PolicyConfig

BASE_CONFIDENCE = 0.95
CONFIDENCE_FLOOR = 0.30
PENALTY_DOC_QUALITY = 0.08
PENALTY_NONCRITICAL_DEGRADED = 0.20
PENALTY_CRITICAL_DEGRADED = 0.35

HARD_REJECTION_CHECKS = ("intake", "exclusions", "waiting_period", "pre_auth", "limits")


@dataclass
class AggregationInput:
    claim: ClaimInput
    policy: PolicyConfig
    gate: Optional[GateResult]
    intake: CheckResult
    checks: dict[str, CheckResult]
    line_items: list[LineItem]
    extracted: list = field(default_factory=list)
    degraded_components: list[str] = field(default_factory=list)
    critical_degraded: bool = False


def aggregate(inp: AggregationInput, claim_id: str) -> ClaimDecision:
    # ── Tier 0: gate failure ──
    if inp.gate is not None and not inp.gate.passed:
        return ClaimDecision(
            claim_id=claim_id, decision=None, status=Decision.NEEDS_RESUBMISSION,
            approved_amount=0, reasons=[inp.gate.failure_kind.value] if inp.gate.failure_kind else [],
            confidence_score=1.0, user_message=inp.gate.user_message,
            notes=["Stopped at document verification; no claim decision was made."],
        )

    financial = inp.checks.get("financial")
    payable = int(financial.data.get("payable", 0)) if financial else 0
    breakdown = financial.data.get("breakdown", []) if financial else []
    confidence = _confidence(inp)

    # ── Tier 1: hard rejections ──
    hard_reasons: list[str] = []
    hard_notes: list[str] = []
    if inp.intake.status == CheckStatus.FAIL:
        hard_reasons += inp.intake.reasons
        if inp.intake.user_facing_note:
            hard_notes.append(inp.intake.user_facing_note)
    for name in HARD_REJECTION_CHECKS:
        if name == "intake":
            continue
        r = inp.checks.get(name)
        if r and r.status == CheckStatus.FAIL:
            hard_reasons += r.reasons
            if r.user_facing_note:
                hard_notes.append(r.user_facing_note)

    if hard_reasons:
        return ClaimDecision(
            claim_id=claim_id, decision=Decision.REJECTED, status=Decision.REJECTED,
            approved_amount=0, reasons=_dedupe(hard_reasons),
            line_item_breakdown=inp.line_items, financial_breakdown={"breakdown": breakdown},
            confidence_score=confidence, notes=hard_notes,
            user_message=" ".join(hard_notes) if hard_notes else None,
            degraded=bool(inp.degraded_components),
        )

    # ── Tier 2: manual review ──
    fraud = inp.checks.get("fraud")
    fraud_signals = fraud.data.get("signals", []) if fraud else []
    manual_triggers: list[str] = []
    if fraud and fraud.status == CheckStatus.FLAG and fraud.data.get("manual_review"):
        manual_triggers += fraud_signals
    if inp.claim.claimed_amount > inp.policy.fraud["auto_manual_review_above"]:
        manual_triggers.append(
            f"High-value claim ₹{inp.claim.claimed_amount:,} exceeds auto-review threshold "
            f"₹{inp.policy.fraud['auto_manual_review_above']:,}"
        )
    if inp.critical_degraded:
        manual_triggers.append("A critical component failed; a safe automated decision was not possible")
    if confidence < CONFIDENCE_FLOOR:
        manual_triggers.append(f"Confidence {confidence:.2f} below floor {CONFIDENCE_FLOOR}")

    notes = _degradation_notes(inp)
    if manual_triggers:
        return ClaimDecision(
            claim_id=claim_id, decision=Decision.MANUAL_REVIEW, status=Decision.MANUAL_REVIEW,
            approved_amount=payable, reasons=["MANUAL_REVIEW"],
            line_item_breakdown=inp.line_items, financial_breakdown={"breakdown": breakdown},
            confidence_score=confidence, fraud_signals=fraud_signals,
            notes=notes + manual_triggers,
            user_message="This claim has been routed to manual review. " + " ".join(manual_triggers),
            degraded=bool(inp.degraded_components),
        )

    # ── Tier 3 / 4: partial vs approved ──
    coverage = inp.checks.get("coverage")
    excluded_items = coverage.data.get("excluded_items", []) if coverage else []
    has_excluded = bool(excluded_items)
    has_covered = payable > 0

    if has_excluded and has_covered:
        decision = Decision.PARTIAL
    elif has_excluded and not has_covered:
        return ClaimDecision(
            claim_id=claim_id, decision=Decision.REJECTED, status=Decision.REJECTED,
            approved_amount=0, reasons=["NOT_COVERED"],
            line_item_breakdown=inp.line_items, financial_breakdown={"breakdown": breakdown},
            confidence_score=confidence, notes=notes + ["All billed items were excluded/uncovered."],
            degraded=bool(inp.degraded_components),
        )
    else:
        decision = Decision.APPROVED

    msg_bits = []
    if decision == Decision.PARTIAL:
        msg_bits.append(
            "Some billed items were approved and others were excluded. "
            + "; ".join(f"{e['description']} excluded ({e['reason']})" for e in excluded_items)
        )
    msg_bits += notes
    return ClaimDecision(
        claim_id=claim_id, decision=decision, status=decision,
        approved_amount=payable, reasons=[decision.value],
        line_item_breakdown=inp.line_items, financial_breakdown={"breakdown": breakdown},
        confidence_score=confidence, fraud_signals=fraud_signals, notes=notes,
        user_message=" ".join(msg_bits) if msg_bits else None,
        degraded=bool(inp.degraded_components),
    )


def _confidence(inp: AggregationInput) -> float:
    conf = BASE_CONFIDENCE
    for r in inp.checks.values():
        conf += r.confidence_delta  # deltas are <= 0
    for d in inp.extracted:
        q = getattr(d, "quality", None)
        if q is not None and getattr(q, "value", q) in ("LOW", "PARTIAL"):
            conf -= PENALTY_DOC_QUALITY
        ec = getattr(d, "extraction_confidence", 1.0)
        if ec < 1.0:
            conf -= round((1.0 - ec) * 0.2, 3)
    for comp in inp.degraded_components:
        conf -= PENALTY_CRITICAL_DEGRADED if inp.critical_degraded else PENALTY_NONCRITICAL_DEGRADED
    return max(CONFIDENCE_FLOOR, min(1.0, round(conf, 3)))


def _degradation_notes(inp: AggregationInput) -> list[str]:
    if not inp.degraded_components:
        return []
    return [
        f"Manual review recommended: processing was incomplete — the following component(s) "
        f"failed and were skipped: {', '.join(inp.degraded_components)}. The decision was made "
        f"from the remaining checks and confidence was reduced accordingly."
    ]


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
