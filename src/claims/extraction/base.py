"""Extraction interface. Two implementations share this contract:
  - InjectedExtractor: maps pre-extracted test-case content into ExtractedDocument (eval).
  - GeminiExtractor:    runs vision OCR/extraction on uploaded bytes (UI).

This abstraction is what lets the eval inject ground-truth content while the UI uses the
real vision pipeline, with no change to the orchestrator or downstream checks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ClaimCategory, DocumentDescriptor, ExtractedDocument


class ExtractionError(Exception):
    pass


class ExtractorBase(ABC):
    @abstractmethod
    def classify_and_extract(
        self, doc: DocumentDescriptor, category: ClaimCategory
    ) -> ExtractedDocument: ...
