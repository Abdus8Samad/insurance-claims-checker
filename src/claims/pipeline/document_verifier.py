"""Document Verification gate — runs BEFORE adjudication and short-circuits on failure.

Three ordered checks (each dependent on the previous):
    1. type completeness  — are all required document types present?
    2. readability        — is any required document unreadable?
    3. patient consistency — do all documents name the same patient?

A gate failure is NOT a rejection: it returns decision=null with a specific, actionable
message naming exactly what is wrong and what to provide instead.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..models import (
    ClaimCategory,
    ExtractedDocument,
    GateFailureKind,
    GateResult,
    Quality,
)
from ..policy import PolicyConfig

_HONORIFICS = {"dr", "mr", "mrs", "ms", "miss", "shri", "smt", "md", "prof"}


def normalize_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z\s]", " ", name).lower()
    tokens = [t for t in name.split() if t and t not in _HONORIFICS]
    return " ".join(tokens)


def _same_person(a: str, b: str) -> bool:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return True  # missing name on one side: don't trip the mismatch check
    if na == nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= 0.88  # tolerate minor OCR noise


class DocumentVerifier:
    name = "document_verification"

    def __init__(self, policy: PolicyConfig):
        self.policy = policy

    def run(self, extracted: list[ExtractedDocument], category: ClaimCategory) -> GateResult:
        reqs = self.policy.document_requirements(category)
        required = [t for t in reqs.get("required", [])]
        present_types = [d.doc_type.value for d in extracted]

        # 1) Type completeness
        type_counts: dict[str, int] = {}
        for t in present_types:
            type_counts[t] = type_counts.get(t, 0) + 1
        missing = [t for t in required if t not in present_types]
        if missing:
            uploaded_desc = ", ".join(f"{n}× {t}" for t, n in type_counts.items()) or "no documents"
            msg = (
                f"This {category.value} claim requires the following document type(s): "
                f"{', '.join(required)}. You uploaded: {uploaded_desc}. "
                f"Missing required document(s): {', '.join(missing)}. "
                f"Please upload the missing {', '.join(missing)} and resubmit."
            )
            return GateResult(
                passed=False, failure_kind=GateFailureKind.MISSING_DOC, user_message=msg,
                details={"required": required, "uploaded_types": type_counts, "missing": missing},
            )

        # 2) Readability (required docs)
        for d in extracted:
            if d.doc_type.value in required and d.quality == Quality.UNREADABLE:
                fname = next((e for e in [d.file_id] if e), "the document")
                # prefer a human file name if available via content; fall back to file_id
                msg = (
                    f"The document you uploaded as your {d.doc_type.value} (file '{d.file_id}') could not "
                    f"be read — it appears blurry or unreadable. Please re-upload a clearer photo or scan of "
                    f"your {d.doc_type.value}. The rest of your submission looks fine; only this document needs "
                    f"to be replaced."
                )
                return GateResult(
                    passed=False, failure_kind=GateFailureKind.UNREADABLE, user_message=msg,
                    details={"unreadable_file": d.file_id, "doc_type": d.doc_type.value},
                )

        # 3) Patient-name consistency (across all docs)
        named = [(d.file_id, d.patient_name) for d in extracted if d.patient_name]
        for i in range(len(named)):
            for j in range(i + 1, len(named)):
                (fa, na), (fb, nb) = named[i], named[j]
                if not _same_person(na, nb):
                    msg = (
                        f"The documents appear to belong to different patients: '{na}' on file '{fa}' and "
                        f"'{nb}' on file '{fb}'. All documents in a single claim must be for the same patient. "
                        f"Please check you have uploaded the correct documents and resubmit."
                    )
                    return GateResult(
                        passed=False, failure_kind=GateFailureKind.PATIENT_MISMATCH, user_message=msg,
                        details={"names": {fa: na, fb: nb}},
                    )

        return GateResult(passed=True, details={"required": required, "uploaded_types": type_counts})
