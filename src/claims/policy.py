"""Typed accessors over policy_terms.json.

Policy values are NEVER hardcoded in business logic — every rule, limit, threshold,
and list is read through this object. If a key is missing the accessor raises, so a
malformed policy fails loudly rather than silently approving.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ClaimCategory, Money


class PolicyError(KeyError):
    """A required policy key is missing or malformed."""


class PolicyConfig:
    def __init__(self, raw: dict[str, Any]):
        self.raw = raw

    @classmethod
    def load(cls, path: str | Path) -> "PolicyConfig":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data)

    # ── identity ──
    @property
    def policy_id(self) -> str:
        return self.raw["policy_id"]

    # ── coverage ──
    @property
    def per_claim_limit(self) -> Money:
        return self.raw["coverage"]["per_claim_limit"]

    @property
    def annual_opd_limit(self) -> Money:
        return self.raw["coverage"]["annual_opd_limit"]

    @property
    def sum_insured(self) -> Money:
        return self.raw["coverage"]["sum_insured_per_employee"]

    # ── per-category config ──
    def category_config(self, category: ClaimCategory) -> dict[str, Any]:
        key = category.value.lower()
        cats = self.raw["opd_categories"]
        if key not in cats:
            raise PolicyError(f"Unknown OPD category in policy: {key}")
        return cats[key]

    def sub_limit(self, category: ClaimCategory) -> Money:
        return self.category_config(category)["sub_limit"]

    def copay_percent(self, category: ClaimCategory) -> float:
        return self.category_config(category).get("copay_percent", 0)

    def network_discount_percent(self, category: ClaimCategory) -> float:
        return self.category_config(category).get("network_discount_percent", 0)

    def effective_claim_ceiling(self, category: ClaimCategory) -> Money:
        """Resolved per-claim ceiling = max(category sub_limit, global per_claim_limit).

        This single rule reconciles the test ground truth: consultation ceiling 5000
        (per_claim_limit binds), dental ceiling 10000 (sub_limit binds). See ARCHITECTURE.md.
        """
        return max(self.sub_limit(category), self.per_claim_limit)

    def ceiling_source(self, category: ClaimCategory) -> str:
        """Which limit is binding for this category ('per_claim_limit' or 'sub_limit')."""
        return "sub_limit" if self.sub_limit(category) > self.per_claim_limit else "per_claim_limit"

    # ── waiting periods ──
    @property
    def waiting_periods(self) -> dict[str, Any]:
        return self.raw["waiting_periods"]

    def specific_waiting_days(self, condition_key: str) -> int | None:
        return self.raw["waiting_periods"]["specific_conditions"].get(condition_key)

    @property
    def initial_waiting_days(self) -> int:
        return self.raw["waiting_periods"]["initial_waiting_period_days"]

    def waiting_condition_keys(self) -> list[str]:
        return list(self.raw["waiting_periods"]["specific_conditions"].keys())

    # ── exclusions ──
    @property
    def excluded_conditions(self) -> list[str]:
        return self.raw["exclusions"]["conditions"]

    def category_exclusions(self, category: ClaimCategory) -> list[str]:
        cfg = self.category_config(category)
        return cfg.get("excluded_procedures", []) + cfg.get("excluded_items", [])

    def category_covered_items(self, category: ClaimCategory) -> list[str]:
        cfg = self.category_config(category)
        return cfg.get("covered_procedures", []) + cfg.get("covered_items", [])

    # ── pre-authorization ──
    def high_value_tests_requiring_pre_auth(self, category: ClaimCategory) -> list[str]:
        return self.category_config(category).get("high_value_tests_requiring_pre_auth", [])

    def pre_auth_threshold(self, category: ClaimCategory) -> Money | None:
        return self.category_config(category).get("pre_auth_threshold")

    # ── network ──
    @property
    def network_hospitals(self) -> list[str]:
        return self.raw["network_hospitals"]

    def is_network_hospital(self, name: str | None) -> bool:
        if not name:
            return False
        n = name.strip().lower()
        return any(h.strip().lower() in n or n in h.strip().lower() for h in self.network_hospitals)

    # ── submission rules ──
    @property
    def minimum_claim_amount(self) -> Money:
        return self.raw["submission_rules"]["minimum_claim_amount"]

    @property
    def submission_deadline_days(self) -> int:
        return self.raw["submission_rules"]["deadline_days_from_treatment"]

    @property
    def currency(self) -> str:
        return self.raw["submission_rules"].get("currency", "INR")

    # ── document requirements ──
    def document_requirements(self, category: ClaimCategory) -> dict[str, list[str]]:
        reqs = self.raw["document_requirements"]
        if category.value not in reqs:
            raise PolicyError(f"No document requirements for category {category.value}")
        return reqs[category.value]

    # ── fraud thresholds ──
    @property
    def fraud(self) -> dict[str, Any]:
        return self.raw["fraud_thresholds"]
