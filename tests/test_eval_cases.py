"""Regression gate: all 12 spec cases produce their expected outcomes."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.cases import build_claim_input, load_cases  # noqa: E402
from eval.run_eval import evaluate_case  # noqa: E402

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["case_id"] for c in CASES])
def test_case_matches_expected(case):
    result = evaluate_case(case)
    failed = [label for label, ok in result["checks"] if not ok]
    assert result["passed"], f"{case['case_id']} failed checks: {failed}"


def test_all_twelve_present():
    assert len(CASES) == 12
