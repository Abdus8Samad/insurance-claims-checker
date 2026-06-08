"""Run all 12 test cases through the pipeline (deterministic: InjectedExtractor +
KeywordSemanticMapper + frozen as_of_date) and produce an eval report.

Usage:
    python -m eval.run_eval            # prints summary, writes data/eval_report.{md,json}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from claims.config import AppConfig
from claims.extraction.injected import InjectedExtractor
from claims.llm.semantic_mapper import KeywordSemanticMapper
from claims.models import ClaimDecision, Trace
from claims.pipeline.orchestrator import Orchestrator
from claims.policy import PolicyConfig
from claims.roster import MemberRoster

from .cases import REPO_ROOT, build_claim_input, load_cases

POLICY_PATH = REPO_ROOT / "config" / "policy_terms.json"


def build_eval_orchestrator(claim) -> Orchestrator:
    policy = PolicyConfig.load(POLICY_PATH)
    roster = MemberRoster.from_policy_raw(policy.raw)
    # Freeze the clock at treatment date so the submission-deadline check is reproducible.
    cfg = AppConfig(as_of_date=claim.treatment_date)
    return Orchestrator(
        policy=policy, roster=roster,
        extractor=InjectedExtractor(),
        mapper=KeywordSemanticMapper(policy),
        config=cfg,
    )


def _confidence_ok(expected: str, actual: float) -> bool:
    # expected like "above 0.85"
    parts = expected.lower().replace("above", "").strip()
    try:
        return actual > float(parts)
    except ValueError:
        return True


def evaluate_case(case: dict) -> dict:
    claim = build_claim_input(case)
    orch = build_eval_orchestrator(claim)
    decision, trace = orch.process(claim)
    exp = case["expected"]

    checks: list[tuple[str, bool]] = []

    # decision
    exp_decision = exp.get("decision", "__absent__")
    if exp_decision is None:
        checks.append(("decision is null (gate stop)", decision.decision is None))
    elif exp_decision != "__absent__":
        checks.append((f"decision == {exp_decision}",
                       decision.decision is not None and decision.decision.value == exp_decision))

    # approved amount
    if "approved_amount" in exp:
        checks.append((f"approved_amount == {exp['approved_amount']}",
                       decision.approved_amount == exp["approved_amount"]))

    # rejection reasons (subset)
    if "rejection_reasons" in exp:
        produced = set(decision.reasons)
        checks.append((f"reasons ⊇ {exp['rejection_reasons']}",
                       set(exp["rejection_reasons"]).issubset(produced)))

    # confidence
    if "confidence_score" in exp and isinstance(exp["confidence_score"], str):
        checks.append((f"confidence {exp['confidence_score']}",
                       _confidence_ok(exp["confidence_score"], decision.confidence_score)))

    # gate-message specificity heuristics
    if exp.get("decision", "x") is None:
        msg = (decision.user_message or "").lower()
        checks.append(("message is specific/non-empty", len(msg) > 40))

    # degradation expectations (TC011)
    if any("component" in s.lower() and "fail" in s.lower() for s in exp.get("system_must", [])):
        checks.append(("degraded flag set", decision.degraded))
        checks.append(("manual-review note present",
                       any("manual review" in n.lower() for n in decision.notes)))

    passed = all(ok for _, ok in checks)
    return {
        "case_id": case["case_id"],
        "case_name": case["case_name"],
        "passed": passed,
        "checks": checks,
        "decision": decision,
        "trace": trace,
    }


def main() -> int:
    cases = load_cases()
    results = [evaluate_case(c) for c in cases]

    n_pass = sum(1 for r in results if r["passed"])
    print(f"\n{'='*70}\nEVAL: {n_pass}/{len(results)} cases passed\n{'='*70}")
    for r in results:
        flag = "PASS" if r["passed"] else "FAIL"
        d = r["decision"]
        dec = d.decision.value if d.decision else "null"
        print(f"[{flag}] {r['case_id']} {r['case_name']:42s} → {dec:14s} ₹{d.approved_amount:<7} conf={d.confidence_score:.2f}")
        if not r["passed"]:
            for label, ok in r["checks"]:
                if not ok:
                    print(f"        ✗ {label}")

    # write reports
    from .report import write_reports
    write_reports(results, REPO_ROOT / "data")
    print(f"\nReport written to data/eval_report.md")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
