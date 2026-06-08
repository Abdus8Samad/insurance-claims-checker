"""Build the eval report (Markdown + JSON) from evaluated cases."""

from __future__ import annotations

import json
from pathlib import Path

from claims.trace import decision_to_dict, trace_to_dict, trace_to_markdown


def write_reports(results: list[dict], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_markdown(results, out_dir / "eval_report.md")
    _write_json(results, out_dir / "eval_report.json")


def _write_markdown(results: list[dict], path: Path) -> None:
    n_pass = sum(1 for r in results if r["passed"])
    lines = [
        "# Eval Report",
        "",
        f"**{n_pass}/{len(results)} cases passed.** "
        "Deterministic run: InjectedExtractor + KeywordSemanticMapper, as_of_date frozen to each "
        "case's treatment date.",
        "",
        "| Case | Name | Expected | Produced | Amount | Conf | Result |",
        "|---|---|---|---|---:|---:|---|",
    ]
    for r in results:
        d = r["decision"]
        produced = d.decision.value if d.decision else "null"
        # infer the expected label from the checks for the summary row
        lines.append(
            f"| {r['case_id']} | {r['case_name']} | — | {produced} | ₹{d.approved_amount:,} | "
            f"{d.confidence_score:.2f} | {'PASS' if r['passed'] else 'FAIL'} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    for r in results:
        lines.append(trace_to_markdown(r["trace"]))
        if not r["passed"]:
            lines.append("")
            lines.append("> **Assertion failures:**")
            for label, ok in r["checks"]:
                if not ok:
                    lines.append(f"> - ✗ {label}")
        lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_json(results: list[dict], path: Path) -> None:
    payload = []
    for r in results:
        payload.append({
            "case_id": r["case_id"],
            "case_name": r["case_name"],
            "passed": r["passed"],
            "checks": [{"label": label, "ok": ok} for label, ok in r["checks"]],
            "decision": decision_to_dict(r["decision"]),
            "trace": trace_to_dict(r["trace"]),
        })
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
