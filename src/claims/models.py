"""Shared data models for the claims pipeline.

Every component speaks in terms of these models. Money is stored as integer rupees
(the test cases use clean integers); percentage math rounds half-up to the nearest
rupee. Floats are never used for money.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

Money = int  # integer rupees


# ─── Enums ────────────────────────────────────────────────────────────────────


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    PHARMACY_BILL = "PHARMACY_BILL"
    LAB_REPORT = "LAB_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DENTAL_REPORT = "DENTAL_REPORT"
    UNKNOWN = "UNKNOWN"


class Quality(str, Enum):
    GOOD = "GOOD"
    LOW = "LOW"
    PARTIAL = "PARTIAL"
    UNREADABLE = "UNREADABLE"


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class Decision(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NEEDS_RESUBMISSION = "NEEDS_RESUBMISSION"  # gate failure — decision field stays null


class CheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    FLAG = "FLAG"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class GateFailureKind(str, Enum):
    MISSING_DOC = "MISSING_DOC"
    WRONG_DOC = "WRONG_DOC"
    UNREADABLE = "UNREADABLE"
    PATIENT_MISMATCH = "PATIENT_MISMATCH"


# Canonical rejection reason codes (used in ClaimDecision.reasons).
class RejectionReason(str, Enum):
    EXCLUDED_CONDITION = "EXCLUDED_CONDITION"
    WAITING_PERIOD = "WAITING_PERIOD"
    PRE_AUTH_MISSING = "PRE_AUTH_MISSING"
    PER_CLAIM_EXCEEDED = "PER_CLAIM_EXCEEDED"
    INTAKE_INVALID = "INTAKE_INVALID"
    NOT_COVERED = "NOT_COVERED"


# ─── Input models ─────────────────────────────────────────────────────────────


class LineItem(BaseModel):
    """A single billed line item. Coverage fields are filled by the coverage check."""

    description: str
    amount: Money = 0
    covered: Optional[bool] = None
    rejection_reason: Optional[str] = None
    mapped_to: Optional[str] = None
    map_confidence: Optional[float] = None


class DocumentDescriptor(BaseModel):
    """A document as submitted. In the UI, raw_bytes is set and the rest is extracted.
    In eval, actual_type / quality / patient_name_on_doc / content are injected."""

    file_id: str
    file_name: Optional[str] = None
    actual_type: Optional[DocumentType] = None
    quality: Optional[Quality] = None
    patient_name_on_doc: Optional[str] = None
    content: Optional[dict[str, Any]] = None
    raw_bytes: Optional[bytes] = Field(default=None, exclude=True, repr=False)
    mime_type: Optional[str] = None


class ClaimHistoryEntry(BaseModel):
    claim_id: str
    date: date
    amount: Money = 0
    provider: Optional[str] = None


class ClaimInput(BaseModel):
    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: date
    claimed_amount: Money
    currency: str = "INR"
    hospital_name: Optional[str] = None
    ytd_claims_amount: Money = 0
    claims_history: list[ClaimHistoryEntry] = Field(default_factory=list)
    simulate_component_failure: bool = False
    documents: list[DocumentDescriptor] = Field(default_factory=list)
    # Optional case label, carried into the trace for eval reporting.
    case_id: Optional[str] = None


# ─── Extraction output ────────────────────────────────────────────────────────


class ExtractedDocument(BaseModel):
    file_id: str
    doc_type: DocumentType
    quality: Quality = Quality.GOOD
    patient_name: Optional[str] = None
    content: dict[str, Any] = Field(default_factory=dict)
    field_confidences: dict[str, float] = Field(default_factory=dict)
    extraction_confidence: float = 1.0
    warnings: list[str] = Field(default_factory=list)


# ─── Check / gate output ──────────────────────────────────────────────────────


class CheckResult(BaseModel):
    name: str
    status: CheckStatus
    critical: bool = True
    reasons: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    confidence_delta: float = 0.0
    user_facing_note: Optional[str] = None


class GateResult(BaseModel):
    passed: bool
    failure_kind: Optional[GateFailureKind] = None
    user_message: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)


# ─── Decision + trace ─────────────────────────────────────────────────────────


class ClaimDecision(BaseModel):
    claim_id: str
    decision: Optional[Decision] = None  # null only for gate failures (NEEDS_RESUBMISSION)
    status: Decision  # always set; mirrors decision or NEEDS_RESUBMISSION
    approved_amount: Money = 0
    reasons: list[str] = Field(default_factory=list)
    line_item_breakdown: list[LineItem] = Field(default_factory=list)
    financial_breakdown: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    fraud_signals: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    degraded: bool = False
    user_message: Optional[str] = None  # the actionable member-facing message


class TraceStep(BaseModel):
    stage: str
    component: str
    status: CheckStatus
    started_at: datetime
    ended_at: datetime
    duration_ms: int = 0
    input_summary: dict[str, Any] = Field(default_factory=dict)
    output_summary: dict[str, Any] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    confidence_delta: float = 0.0
    error: Optional[str] = None


class Trace(BaseModel):
    claim_id: str
    case_id: Optional[str] = None
    created_at: datetime
    steps: list[TraceStep] = Field(default_factory=list)
    final_decision: Optional[ClaimDecision] = None
