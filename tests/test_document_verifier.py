"""Gate tests — TC001 (wrong doc), TC002 (unreadable), TC003 (patient mismatch)."""

from claims.models import ClaimCategory, DocumentType, ExtractedDocument, GateFailureKind, Quality
from claims.pipeline.document_verifier import DocumentVerifier, normalize_name


def _doc(file_id, dtype, quality=Quality.GOOD, patient=None):
    return ExtractedDocument(file_id=file_id, doc_type=dtype, quality=quality, patient_name=patient)


def test_tc001_missing_required_doc_type(policy):
    gate = DocumentVerifier(policy)
    res = gate.run(
        [_doc("F001", DocumentType.PRESCRIPTION), _doc("F002", DocumentType.PRESCRIPTION)],
        ClaimCategory.CONSULTATION,
    )
    assert not res.passed
    assert res.failure_kind == GateFailureKind.MISSING_DOC
    # message names both the uploaded type and the required/missing type
    assert "PRESCRIPTION" in res.user_message
    assert "HOSPITAL_BILL" in res.user_message


def test_tc002_unreadable_required_doc(policy):
    gate = DocumentVerifier(policy)
    res = gate.run(
        [
            _doc("prescription.jpg", DocumentType.PRESCRIPTION, Quality.GOOD, "Sneha Reddy"),
            _doc("blurry_bill.jpg", DocumentType.PHARMACY_BILL, Quality.UNREADABLE, "Sneha Reddy"),
        ],
        ClaimCategory.PHARMACY,
    )
    assert not res.passed
    assert res.failure_kind == GateFailureKind.UNREADABLE
    assert "blurry_bill.jpg" in res.user_message
    # must not be a rejection — names the specific doc to re-upload
    assert "re-upload" in res.user_message.lower()


def test_tc003_patient_mismatch(policy):
    gate = DocumentVerifier(policy)
    res = gate.run(
        [
            _doc("prescription_rajesh.jpg", DocumentType.PRESCRIPTION, patient="Rajesh Kumar"),
            _doc("bill_arjun.jpg", DocumentType.HOSPITAL_BILL, patient="Arjun Mehta"),
        ],
        ClaimCategory.CONSULTATION,
    )
    assert not res.passed
    assert res.failure_kind == GateFailureKind.PATIENT_MISMATCH
    assert "Rajesh Kumar" in res.user_message and "Arjun Mehta" in res.user_message


def test_gate_passes_clean_consultation(policy):
    gate = DocumentVerifier(policy)
    res = gate.run(
        [
            _doc("F007", DocumentType.PRESCRIPTION, patient="Rajesh Kumar"),
            _doc("F008", DocumentType.HOSPITAL_BILL, patient="RAJESH KUMAR "),  # same person, noisy
        ],
        ClaimCategory.CONSULTATION,
    )
    assert res.passed


def test_name_normalization():
    assert normalize_name("Dr. Rajesh Kumar") == "rajesh kumar"
    assert normalize_name("RAJESH  KUMAR.") == "rajesh kumar"
