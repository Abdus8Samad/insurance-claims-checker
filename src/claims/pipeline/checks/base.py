"""Base types for adjudication checks.

Every check is a small object with a `run(ctx) -> CheckResult`. Checks NEVER raise for
business outcomes (a rejection is a normal `CheckResult(status=FAIL)`); they may raise
only on genuine internal errors, which the orchestrator catches and records as ERROR.
Checks never short-circuit each other — the aggregator resolves precedence at the end.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from ...llm.semantic_mapper import SemanticMapper
from ...models import CheckResult, ClaimInput, LineItem
from ...policy import PolicyConfig
from ...roster import Member


@dataclass
class AdjudicationContext:
    claim: ClaimInput
    member: Member
    policy: PolicyConfig
    extracted: list  # list[ExtractedDocument]
    line_items: list[LineItem]
    mapper: SemanticMapper
    as_of_date: date
    diagnoses: list[str] = field(default_factory=list)
    treatments: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)


class Check(ABC):
    name: str = "check"
    critical: bool = True

    @abstractmethod
    def run(self, ctx: AdjudicationContext) -> CheckResult: ...


def covered_base(ctx: AdjudicationContext) -> int:
    """Sum of covered line items (post-exclusion, pre-discount).

    Falls back to the claimed amount when the bill has no itemized lines. Line items
    not yet classified (covered is None) count as covered.
    """
    if not ctx.line_items:
        return ctx.claim.claimed_amount
    return sum(li.amount for li in ctx.line_items if li.covered is not False)
