"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from claims.llm.semantic_mapper import KeywordSemanticMapper
from claims.models import ClaimCategory, ClaimInput, ExtractedDocument, LineItem
from claims.pipeline.checks.base import AdjudicationContext
from claims.policy import PolicyConfig
from claims.roster import Member, MemberRoster

REPO_ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = REPO_ROOT / "config" / "policy_terms.json"


@pytest.fixture(scope="session")
def policy() -> PolicyConfig:
    return PolicyConfig.load(POLICY_PATH)


@pytest.fixture(scope="session")
def roster(policy) -> MemberRoster:
    return MemberRoster.from_policy_raw(policy.raw)


@pytest.fixture
def mapper(policy) -> KeywordSemanticMapper:
    return KeywordSemanticMapper(policy)


def make_ctx(
    policy: PolicyConfig,
    mapper,
    *,
    category=ClaimCategory.CONSULTATION,
    claimed_amount=1500,
    treatment_date=date(2024, 11, 1),
    member=None,
    line_items=None,
    diagnoses=None,
    treatments=None,
    tests=None,
    hospital_name=None,
    ytd=0,
    claims_history=None,
    extracted=None,
) -> AdjudicationContext:
    member = member or Member(member_id="EMP001", name="Rajesh Kumar", join_date=date(2024, 4, 1))
    claim = ClaimInput(
        member_id=member.member_id, policy_id=policy.policy_id, claim_category=category,
        treatment_date=treatment_date, claimed_amount=claimed_amount,
        hospital_name=hospital_name, ytd_claims_amount=ytd,
        claims_history=claims_history or [],
    )
    return AdjudicationContext(
        claim=claim, member=member, policy=policy,
        extracted=extracted or [],
        line_items=line_items or [],
        mapper=mapper, as_of_date=treatment_date,
        diagnoses=diagnoses or [], treatments=treatments or [], tests=tests or [],
    )
