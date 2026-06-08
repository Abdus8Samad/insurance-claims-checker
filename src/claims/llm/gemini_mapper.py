"""GeminiSemanticMapper — LLM-backed semantic mapping with a deterministic fallback.

Each mapping task asks Gemini for a constrained JSON answer. If the LLM call fails for
any reason, it falls back to the KeywordSemanticMapper (real production logic, not a
stub) and marks the method as 'llm_fallback_keyword' so the confidence model can apply
a penalty. This keeps the system intelligent when the LLM is healthy and resilient when
it is not.
"""

from __future__ import annotations

from ..models import ClaimCategory
from ..policy import PolicyConfig
from .gemini_client import GeminiClient, LLMError
from .prompts import ConditionMapping, ExclusionMapping, LineItemMapping
from .semantic_mapper import (
    KeywordSemanticMapper,
    LineItemClassification,
    Mapping,
    SemanticMapper,
)


class GeminiSemanticMapper(SemanticMapper):
    def __init__(self, client: GeminiClient, policy: PolicyConfig):
        self.client = client
        self.policy = policy
        self.fallback = KeywordSemanticMapper(policy)

    def map_waiting_condition(self, texts: list[str]) -> Mapping:
        keys = self.policy.waiting_condition_keys()
        prompt = (
            "Map the following medical diagnosis/treatment text to exactly one of these policy "
            f"waiting-period condition keys, or null if none apply: {keys}. "
            "Do not map obesity-related text (it is excluded, not waiting-period). "
            f"Text: {' | '.join(texts)}"
        )
        try:
            data = self.client.generate_structured(prompt, ConditionMapping)
            return Mapping(matched=data.get("condition_key"),
                           confidence=float(data.get("confidence", 0.0)), method="llm")
        except LLMError:
            m = self.fallback.map_waiting_condition(texts)
            m.method = "llm_fallback_keyword"
            return m

    def map_exclusion(self, texts: list[str], category: ClaimCategory) -> Mapping:
        prompt = (
            "Decide whether the following diagnosis/treatment matches any of these policy exclusions. "
            f"Return the exact matching exclusion phrase or null. Exclusions: {self.policy.excluded_conditions}. "
            f"Text: {' | '.join(texts)}"
        )
        try:
            data = self.client.generate_structured(prompt, ExclusionMapping)
            return Mapping(matched=data.get("matched_exclusion"),
                           confidence=float(data.get("confidence", 0.0)), method="llm")
        except LLMError:
            m = self.fallback.map_exclusion(texts, category)
            m.method = "llm_fallback_keyword"
            return m

    def classify_line_item(self, description: str, category: ClaimCategory) -> LineItemClassification:
        covered = self.policy.category_covered_items(category)
        excluded = self.policy.category_exclusions(category)
        prompt = (
            f"Classify this billed line item for the {category.value} category as covered or excluded. "
            f"Covered procedures/items: {covered}. Excluded: {excluded}. "
            f"If neither list applies, default covered=true. Line item: '{description}'"
        )
        try:
            data = self.client.generate_structured(prompt, LineItemMapping)
            return LineItemClassification(
                covered=bool(data.get("covered", True)), matched=data.get("matched"),
                confidence=float(data.get("confidence", 0.0)), method="llm", reason=data.get("reason"),
            )
        except LLMError:
            c = self.fallback.classify_line_item(description, category)
            c.method = "llm_fallback_keyword"
            return c
