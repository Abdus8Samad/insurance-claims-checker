"""JSON-file audit log (no database).

One file per claim: data/audit/{claim_id}.json containing the submitted claim, the
decision, and the full trace. Write-once per unique claim_id avoids read-modify-write
races. Also serves same-day / monthly claim counts for live fraud detection.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from ..models import ClaimDecision, ClaimInput, Trace


class AuditWriteError(IOError):
    pass


class JsonAuditStore:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def append(self, claim: ClaimInput, decision: ClaimDecision, trace: Trace) -> Path:
        record = {
            "claim_id": decision.claim_id,
            "written_at": datetime.now().isoformat(),
            "member_id": claim.member_id,
            "claim_category": claim.claim_category.value,
            "treatment_date": claim.treatment_date.isoformat(),
            "claimed_amount": claim.claimed_amount,
            "decision": json.loads(decision.model_dump_json()),
            "claim": json.loads(claim.model_dump_json()),
            "trace": json.loads(trace.model_dump_json()),
        }
        path = self.base_dir / f"{decision.claim_id}.json"
        try:
            path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
        except OSError as exc:  # non-fatal: decision is already made
            raise AuditWriteError(str(exc)) from exc
        return path

    def list_claims(self, member_id: Optional[str] = None) -> list[dict]:
        out = []
        for f in sorted(self.base_dir.glob("*.json")):
            try:
                rec = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if member_id is None or rec.get("member_id") == member_id:
                out.append(rec)
        return out

    def same_day_count(self, member_id: str, day: date) -> int:
        return sum(
            1 for r in self.list_claims(member_id)
            if r.get("treatment_date") == day.isoformat()
        )

    def monthly_count(self, member_id: str, year: int, month: int) -> int:
        count = 0
        for r in self.list_claims(member_id):
            td = r.get("treatment_date", "")
            if td[:7] == f"{year:04d}-{month:02d}":
                count += 1
        return count
