"""Semantic mapping — the only place the pipeline asks "what does this text MEAN?".

Three tasks: map a diagnosis to a waiting-period condition key, map a diagnosis/
treatment to a policy exclusion, and classify a billed line item as covered/excluded
for a category.

`SemanticMapper` is the interface. `KeywordSemanticMapper` is a deterministic
substring/synonym implementation used (a) directly in eval + unit tests for
reproducibility, and (b) as the fallback inside `GeminiSemanticMapper` when the LLM
call fails. Because the deterministic path is real production code, a fallback is
never a stub.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ..models import ClaimCategory
from ..policy import PolicyConfig


@dataclass
class Mapping:
    matched: Optional[str] = None
    confidence: float = 0.0
    method: str = "keyword"  # "keyword" | "llm" | "llm_fallback_keyword"


@dataclass
class LineItemClassification:
    covered: bool
    matched: Optional[str] = None
    confidence: float = 0.0
    method: str = "keyword"
    reason: Optional[str] = None


# Diagnosis shorthand / synonyms → policy waiting-period condition key.
# Obesity is deliberately NOT mapped here: obesity treatment is *globally excluded*,
# so it is handled by the exclusion check, never the waiting-period check.
_WAITING_SYNONYMS: dict[str, list[str]] = {
    "diabetes": ["diabetes", "diabetic", "t2dm", "type 2 diabetes", "type 1 diabetes", "dm mellitus", "diabetes mellitus"],
    "hypertension": ["hypertension", "htn", "high blood pressure"],
    "thyroid_disorders": ["thyroid", "hypothyroid", "hyperthyroid", "goitre", "goiter"],
    "joint_replacement": ["joint replacement", "knee replacement", "hip replacement", "arthroplasty"],
    "maternity": ["maternity", "pregnancy", "antenatal", "delivery", "obstetric"],
    "mental_health": ["mental health", "depression", "anxiety disorder", "bipolar", "psychiatric"],
    "hernia": ["hernia", "herniorrhaphy", "hernioplasty"],
    "cataract": ["cataract"],
}

# Diagnosis/treatment keywords → policy exclusion phrase.
_EXCLUSION_SYNONYMS: dict[str, list[str]] = {
    "Obesity and weight loss programs": ["obesity", "bariatric", "weight loss", "weight-loss", "diet program", "diet and nutrition", "morbid obesity"],
    "Cosmetic or aesthetic procedures": ["cosmetic", "aesthetic", "anti-aging", "anti aging"],
    "Infertility and assisted reproduction": ["infertility", "ivf", "assisted reproduction", "fertility treatment"],
    "Substance abuse treatment": ["substance abuse", "de-addiction", "deaddiction", "rehab", "rehabilitation for addiction"],
    "Experimental treatments": ["experimental", "investigational"],
    "Self-inflicted injuries": ["self-inflicted", "self inflicted"],
    "Vaccination (non-medically necessary)": ["vaccination", "vaccine (cosmetic)"],
    "Health supplements and tonics": ["health supplement", "tonic", "multivitamin tonic"],
}


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


class SemanticMapper(ABC):
    @abstractmethod
    def map_waiting_condition(self, texts: list[str]) -> Mapping: ...

    @abstractmethod
    def map_exclusion(self, texts: list[str], category: ClaimCategory) -> Mapping: ...

    @abstractmethod
    def classify_line_item(self, description: str, category: ClaimCategory) -> LineItemClassification: ...


class KeywordSemanticMapper(SemanticMapper):
    """Deterministic mapper over policy lists + a synonym table. No network."""

    def __init__(self, policy: PolicyConfig):
        self.policy = policy

    def map_waiting_condition(self, texts: list[str]) -> Mapping:
        blob = _norm(" | ".join(t for t in texts if t))
        available = set(self.policy.waiting_condition_keys())
        for key, syns in _WAITING_SYNONYMS.items():
            if key not in available:
                continue
            if any(s in blob for s in syns):
                return Mapping(matched=key, confidence=0.95, method="keyword")
        return Mapping(matched=None, confidence=0.95, method="keyword")

    def map_exclusion(self, texts: list[str], category: ClaimCategory) -> Mapping:
        blob = _norm(" | ".join(t for t in texts if t))
        excluded = set(self.policy.excluded_conditions)
        for phrase, syns in _EXCLUSION_SYNONYMS.items():
            if phrase not in excluded:
                continue
            if any(s in blob for s in syns):
                return Mapping(matched=phrase, confidence=0.95, method="keyword")
        # Direct phrase match as a backstop.
        for phrase in excluded:
            if _norm(phrase) in blob:
                return Mapping(matched=phrase, confidence=0.9, method="keyword")
        return Mapping(matched=None, confidence=0.95, method="keyword")

    def classify_line_item(self, description: str, category: ClaimCategory) -> LineItemClassification:
        desc = _norm(description)
        excluded = self.policy.category_exclusions(category)
        covered = self.policy.category_covered_items(category)

        for item in excluded:
            if _norm(item) in desc or _overlaps(desc, _norm(item)):
                return LineItemClassification(
                    covered=False, matched=item, confidence=0.95,
                    method="keyword", reason=f"'{item}' is excluded under the {category.value} category",
                )
        for item in covered:
            if _norm(item) in desc or _overlaps(desc, _norm(item)):
                return LineItemClassification(covered=True, matched=item, confidence=0.95, method="keyword")

        # Categories without explicit procedure lists: covered by default.
        if not excluded and not covered:
            return LineItemClassification(covered=True, matched=None, confidence=0.9, method="keyword")
        # Has lists but no match: treat as covered but low confidence (unknown procedure).
        return LineItemClassification(covered=True, matched=None, confidence=0.6, method="keyword")


def _overlaps(desc: str, phrase: str) -> bool:
    """Loose token-overlap match so 'Root Canal Treatment' matches 'Root Canal'."""
    dt = set(desc.split())
    pt = set(phrase.split())
    if not pt:
        return False
    # Require the shorter side's significant tokens to be present.
    significant = {t for t in pt if len(t) > 3}
    return bool(significant) and significant.issubset(dt)
