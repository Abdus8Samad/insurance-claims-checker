"""GeminiExtractor — real vision OCR/extraction for UI uploads.

Sends document bytes (image or PDF) to Gemini with a constrained JSON schema. On any
LLM failure it raises ExtractionError; the orchestrator records the failure and the
pipeline degrades (it does not crash). Maps the model's response into ExtractedDocument.
"""

from __future__ import annotations

from ..llm.gemini_client import GeminiClient, LLMError
from ..llm.prompts import EXTRACTION_PROMPT, VisionExtraction
from ..models import (
    ClaimCategory,
    DocumentDescriptor,
    DocumentType,
    ExtractedDocument,
    Quality,
)
from .base import ExtractionError, ExtractorBase

_QUALITY_PENALTY = {Quality.GOOD: 0.0, Quality.LOW: 0.15, Quality.PARTIAL: 0.25, Quality.UNREADABLE: 0.6}


class GeminiExtractor(ExtractorBase):
    def __init__(self, client: GeminiClient):
        self.client = client

    def classify_and_extract(
        self, doc: DocumentDescriptor, category: ClaimCategory
    ) -> ExtractedDocument:
        if not doc.raw_bytes or not doc.mime_type:
            raise ExtractionError(f"Document {doc.file_id} has no bytes/mime to extract from")

        try:
            data = self.client.generate_structured(
                prompt=EXTRACTION_PROMPT,
                response_schema=VisionExtraction,
                parts=[(doc.raw_bytes, doc.mime_type)],
            )
        except LLMError as exc:
            raise ExtractionError(f"Vision extraction failed for {doc.file_id}: {exc}") from exc

        quality = _coerce_quality(data.get("quality"))
        warnings = data.get("warnings", []) or []
        # Confidence reflects both self-reported quality and number of warnings.
        extraction_confidence = max(0.3, 1.0 - _QUALITY_PENALTY.get(quality, 0.2) - 0.05 * len(warnings))

        content = {
            "patient_name": data.get("patient_name"),
            "doctor_name": data.get("doctor_name"),
            "doctor_registration": data.get("doctor_registration"),
            "hospital_name": data.get("hospital_name"),
            "date": data.get("date"),
            "diagnosis": data.get("diagnosis"),
            "treatment": data.get("treatment"),
            "medicines": data.get("medicines", []),
            "tests_ordered": data.get("tests_ordered", []),
            "line_items": [
                {"description": li.get("description", ""), "amount": int(round(li.get("amount", 0) or 0))}
                for li in data.get("line_items", []) or []
            ],
            "total": data.get("total"),
        }
        content = {k: v for k, v in content.items() if v not in (None, [], "")}

        return ExtractedDocument(
            file_id=doc.file_id,
            doc_type=_coerce_doc_type(data.get("doc_type"), doc.actual_type),
            quality=quality,
            patient_name=data.get("patient_name"),
            content=content,
            extraction_confidence=round(extraction_confidence, 3),
            warnings=warnings,
        )


def _coerce_quality(value) -> Quality:
    try:
        return Quality(str(value).upper())
    except (ValueError, AttributeError):
        return Quality.LOW


def _coerce_doc_type(value, fallback) -> DocumentType:
    try:
        return DocumentType(str(value).upper())
    except (ValueError, AttributeError):
        return fallback or DocumentType.UNKNOWN
