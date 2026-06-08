"""KeywordSemanticMapper behavior + GeminiSemanticMapper fallback-on-LLM-failure."""

from claims.llm.gemini_client import LLMError
from claims.llm.gemini_mapper import GeminiSemanticMapper
from claims.llm.semantic_mapper import KeywordSemanticMapper
from claims.models import ClaimCategory


def test_keyword_maps_diabetes(policy):
    m = KeywordSemanticMapper(policy)
    assert m.map_waiting_condition(["Type 2 Diabetes Mellitus"]).matched == "diabetes"
    assert m.map_waiting_condition(["T2DM"]).matched == "diabetes"


def test_keyword_does_not_map_obesity_to_waiting(policy):
    m = KeywordSemanticMapper(policy)
    # obesity is excluded, not a waiting-period condition
    assert m.map_waiting_condition(["Morbid Obesity"]).matched is None
    assert m.map_exclusion(["Morbid Obesity", "Bariatric Consultation"],
                           ClaimCategory.CONSULTATION).matched == "Obesity and weight loss programs"


def test_keyword_line_item_dental(policy):
    m = KeywordSemanticMapper(policy)
    assert m.classify_line_item("Root Canal Treatment", ClaimCategory.DENTAL).covered is True
    assert m.classify_line_item("Teeth Whitening", ClaimCategory.DENTAL).covered is False


class _RaisingClient:
    def generate_structured(self, *a, **k):
        raise LLMError("simulated LLM outage")


def test_gemini_mapper_falls_back_to_keyword(policy):
    m = GeminiSemanticMapper(_RaisingClient(), policy)
    res = m.map_waiting_condition(["Type 2 Diabetes Mellitus"])
    assert res.matched == "diabetes"
    assert res.method == "llm_fallback_keyword"
