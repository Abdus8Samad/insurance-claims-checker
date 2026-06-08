"""Structured-output schemas and prompts for Gemini vision extraction & semantic mapping."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ExtractedLineItem(BaseModel):
    description: str = ""
    amount: float = 0


class VisionExtraction(BaseModel):
    """Schema Gemini must fill from a medical document image/PDF."""

    doc_type: str = Field(description="One of: PRESCRIPTION, HOSPITAL_BILL, PHARMACY_BILL, "
                                      "LAB_REPORT, DIAGNOSTIC_REPORT, DISCHARGE_SUMMARY, DENTAL_REPORT, UNKNOWN")
    quality: str = Field(description="One of: GOOD, LOW, PARTIAL, UNREADABLE")
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    hospital_name: Optional[str] = None
    date: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    medicines: list[str] = Field(default_factory=list)
    tests_ordered: list[str] = Field(default_factory=list)
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    total: Optional[float] = None
    warnings: list[str] = Field(description="e.g. 'registration number obscured by stamp'",
                                default_factory=list)


EXTRACTION_PROMPT = """You are a meticulous medical-document extraction agent for an Indian health
insurance claims system. Extract the fields defined by the schema from the attached document(s).

Rules:
- Indian documents are messy: handwritten prescriptions, rubber stamps over text, phone photos,
  regional languages mixed with English. Extract English fields; if a field is obscured or illegible,
  leave it null and add a short note to `warnings` — do NOT guess.
- Classify `doc_type` from the layout (a doctor's Rx with medicines = PRESCRIPTION; an itemized
  invoice with amounts = HOSPITAL_BILL or PHARMACY_BILL; a test report with results = LAB_REPORT).
- Set `quality`: GOOD (clearly readable), LOW (readable with effort), PARTIAL (some sections cut off),
  UNREADABLE (cannot reliably read the key fields).
- Expand medical shorthand where unambiguous (T2DM = Type 2 Diabetes Mellitus, HTN = Hypertension).
- For bills, extract every line item with its amount, and the total.
Return ONLY the JSON object."""


class ConditionMapping(BaseModel):
    condition_key: Optional[str] = Field(description="A policy waiting-period key or null")
    confidence: float = 0.0


class ExclusionMapping(BaseModel):
    matched_exclusion: Optional[str] = Field(description="The exact policy exclusion phrase, or null")
    confidence: float = 0.0


class LineItemMapping(BaseModel):
    covered: bool
    matched: Optional[str] = None
    confidence: float = 0.0
    reason: Optional[str] = None
