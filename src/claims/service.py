"""High-level wiring: build an orchestrator + audit store for a given mode, process a
claim, and persist the result. Used by the Streamlit UI and any external caller.
"""

from __future__ import annotations

from typing import Optional

from .audit.store import AuditWriteError, JsonAuditStore
from .config import AppConfig
from .extraction.injected import InjectedExtractor
from .extraction.vision import GeminiExtractor
from .llm.gemini_client import GeminiClient
from .llm.gemini_mapper import GeminiSemanticMapper
from .llm.semantic_mapper import KeywordSemanticMapper
from .models import ClaimDecision, ClaimInput, Trace
from .pipeline.orchestrator import Orchestrator
from .policy import PolicyConfig
from .roster import MemberRoster


class ClaimsService:
    def __init__(self, orchestrator: Orchestrator, audit: JsonAuditStore):
        self.orchestrator = orchestrator
        self.audit = audit

    def submit(self, claim: ClaimInput) -> tuple[ClaimDecision, Trace]:
        decision, trace = self.orchestrator.process(claim)
        try:
            self.audit.append(claim, decision, trace)
        except AuditWriteError:
            decision.notes.append("Warning: audit log write failed; decision still valid.")
        return decision, trace


def build_service(cfg: Optional[AppConfig] = None, use_llm: bool = True) -> ClaimsService:
    """Build a ready-to-use service.

    use_llm=True  → GeminiExtractor + GeminiSemanticMapper (real vision; for UI uploads).
    use_llm=False → InjectedExtractor + KeywordSemanticMapper (deterministic; structured input).
    """
    cfg = cfg or AppConfig.from_env()
    policy = PolicyConfig.load(cfg.policy_path)
    roster = MemberRoster.from_policy_raw(policy.raw)
    audit = JsonAuditStore(cfg.audit_dir)

    if use_llm:
        client = GeminiClient(cfg)
        extractor = GeminiExtractor(client)
        mapper = GeminiSemanticMapper(client, policy)
    else:
        extractor = InjectedExtractor()
        mapper = KeywordSemanticMapper(policy)

    orch = Orchestrator(policy=policy, roster=roster, extractor=extractor, mapper=mapper, config=cfg)
    return ClaimsService(orch, audit)
