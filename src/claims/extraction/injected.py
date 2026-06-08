"""InjectedExtractor — normalizes pre-extracted test-case data into ExtractedDocument.

Used by the eval harness. TC001–003 carry only metadata (actual_type / quality /
patient_name_on_doc) and no `content`; TC004+ carry full `content`. Both map cleanly
into the same ExtractedDocument shape. extraction_confidence is 1.0 because the content
is ground truth, not inferred.
"""

from __future__ import annotations

from ..models import (
    ClaimCategory,
    DocumentDescriptor,
    DocumentType,
    ExtractedDocument,
    Quality,
)
from .base import ExtractorBase


class InjectedExtractor(ExtractorBase):
    def classify_and_extract(
        self, doc: DocumentDescriptor, category: ClaimCategory
    ) -> ExtractedDocument:
        content = doc.content or {}
        patient = doc.patient_name_on_doc or content.get("patient_name")
        return ExtractedDocument(
            file_id=doc.file_id,
            doc_type=doc.actual_type or DocumentType.UNKNOWN,
            quality=doc.quality or Quality.GOOD,
            patient_name=patient,
            content=content,
            extraction_confidence=1.0,
        )
