"""Streamlit UI for the claims processing system.

Two modes:
  • Submit a Claim  — fill the form, upload real document images/PDFs → Gemini vision
                      extraction → full pipeline → decision + trace.
  • Run a Test Case — pick one of the 12 spec cases, run deterministically (injected
                      content), inspect the decision + full trace.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import streamlit as st

# Make src/ importable when run via `streamlit run app/streamlit_app.py`.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from claims.config import AppConfig  # noqa: E402
from claims.extraction.injected import InjectedExtractor  # noqa: E402
from claims.llm.semantic_mapper import KeywordSemanticMapper  # noqa: E402
from claims.models import (  # noqa: E402
    ClaimCategory,
    ClaimInput,
    DocumentDescriptor,
)
from claims.pipeline.orchestrator import Orchestrator  # noqa: E402
from claims.policy import PolicyConfig  # noqa: E402
from claims.roster import MemberRoster  # noqa: E402
from claims.service import ClaimsService, build_service  # noqa: E402
from claims.audit.store import JsonAuditStore  # noqa: E402

from app.components import render_decision, render_trace  # noqa: E402

st.set_page_config(page_title="Plum Claims", page_icon="🩺", layout="wide")

CFG = AppConfig.from_env()
POLICY = PolicyConfig.load(CFG.policy_path)
ROSTER = MemberRoster.from_policy_raw(POLICY.raw)

MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "pdf": "application/pdf"}


# ── sidebar ──
with st.sidebar:
    st.title("🩺 Plum Claims")
    st.caption("Health-insurance claims processing — multi-agent pipeline")
    st.write(f"**Policy:** {POLICY.policy_id}")
    st.write(f"**Auth mode:** `{CFG.auth_mode}`")
    st.write(f"**Model:** `{CFG.model}`")
    st.divider()
    audit = JsonAuditStore(CFG.audit_dir)
    recent = audit.list_claims()[-8:]
    st.subheader("Recent claims")
    if not recent:
        st.caption("none yet")
    for r in reversed(recent):
        dec = (r.get("decision") or {}).get("status", "?")
        st.caption(f"{r['claim_id']} · {r['member_id']} · {dec}")


tab_submit, tab_test = st.tabs(["Submit a Claim", "Run a Test Case"])


# ── submit a claim (real vision) ──
with tab_submit:
    st.subheader("Submit a claim")
    members = ROSTER.all()
    member_labels = {f"{m.member_id} — {m.name}": m.member_id for m in members}

    col1, col2 = st.columns(2)
    with col1:
        member_label = st.selectbox("Member", list(member_labels.keys()))
        category = st.selectbox("Treatment type", [c.value for c in ClaimCategory])
        treatment_date = st.date_input("Treatment date", value=date(2024, 11, 1))
    with col2:
        claimed_amount = st.number_input("Claimed amount (₹)", min_value=0, value=1500, step=100)
        hospital_name = st.text_input("Hospital name (optional)")
        ytd = st.number_input("YTD claims amount (₹)", min_value=0, value=0, step=1000)

    files = st.file_uploader(
        "Upload documents (images or PDFs)", type=list(MIME.keys()), accept_multiple_files=True
    )
    use_llm = st.toggle("Use Gemini vision extraction", value=True,
                        help="On: real OCR via Gemini. Off: requires structured input (use the test-case tab).")

    if st.button("Process claim", type="primary", disabled=not files):
        docs = []
        for f in files:
            ext = f.name.rsplit(".", 1)[-1].lower()
            docs.append(DocumentDescriptor(
                file_id=f.name, file_name=f.name,
                raw_bytes=f.getvalue(), mime_type=MIME.get(ext, "application/octet-stream"),
            ))
        claim = ClaimInput(
            member_id=member_labels[member_label], policy_id=POLICY.policy_id,
            claim_category=ClaimCategory(category), treatment_date=treatment_date,
            claimed_amount=int(claimed_amount), hospital_name=hospital_name or None,
            ytd_claims_amount=int(ytd), documents=docs,
        )
        try:
            service = build_service(CFG, use_llm=use_llm)
            with st.spinner("Extracting documents and adjudicating..."):
                decision, trace = service.submit(claim)
            render_decision(decision)
            render_trace(trace)
        except Exception as exc:  # surfaces config/auth issues to the user
            st.error(f"Could not process claim: {type(exc).__name__}: {exc}")


# ── run a test case (deterministic) ──
with tab_test:
    st.subheader("Run a spec test case")
    st.caption("Runs deterministically with injected document content (no LLM).")
    sys.path.insert(0, str(ROOT))
    from eval.cases import build_claim_input, load_cases  # noqa: E402

    cases = load_cases()
    labels = {f"{c['case_id']} — {c['case_name']}": c for c in cases}
    chosen = st.selectbox("Test case", list(labels.keys()))
    case = labels[chosen]
    st.write(case["description"])
    with st.expander("Expected outcome"):
        st.json(case["expected"])

    if st.button("Run case", type="primary"):
        claim = build_claim_input(case)
        cfg = AppConfig(as_of_date=claim.treatment_date)
        orch = Orchestrator(
            policy=POLICY, roster=ROSTER, extractor=InjectedExtractor(),
            mapper=KeywordSemanticMapper(POLICY), config=cfg,
        )
        decision, trace = orch.process(claim)
        render_decision(decision)
        render_trace(trace)
