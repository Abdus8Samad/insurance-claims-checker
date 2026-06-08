"""Load test_cases.json and build ClaimInput objects for the eval harness."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from claims.models import (
    ClaimCategory,
    ClaimHistoryEntry,
    ClaimInput,
    DocumentDescriptor,
    DocumentType,
    Quality,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_CASES_PATH = REPO_ROOT / "test_cases.json"


def load_cases(path: str | Path = TEST_CASES_PATH) -> list[dict[str, Any]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["test_cases"]


def build_claim_input(case: dict[str, Any]) -> ClaimInput:
    inp = case["input"]
    docs = []
    for d in inp.get("documents", []):
        docs.append(DocumentDescriptor(
            file_id=d["file_id"],
            file_name=d.get("file_name"),
            actual_type=DocumentType(d["actual_type"]) if d.get("actual_type") else None,
            quality=Quality(d["quality"]) if d.get("quality") else None,
            patient_name_on_doc=d.get("patient_name_on_doc"),
            content=d.get("content"),
        ))
    history = [
        ClaimHistoryEntry(claim_id=h["claim_id"], date=date.fromisoformat(h["date"]),
                          amount=h.get("amount", 0), provider=h.get("provider"))
        for h in inp.get("claims_history", [])
    ]
    return ClaimInput(
        case_id=case["case_id"],
        member_id=inp["member_id"],
        policy_id=inp["policy_id"],
        claim_category=ClaimCategory(inp["claim_category"]),
        treatment_date=date.fromisoformat(inp["treatment_date"]),
        claimed_amount=inp["claimed_amount"],
        currency=inp.get("currency", "INR"),
        hospital_name=inp.get("hospital_name"),
        ytd_claims_amount=inp.get("ytd_claims_amount", 0),
        claims_history=history,
        simulate_component_failure=inp.get("simulate_component_failure", False),
        documents=docs,
    )
