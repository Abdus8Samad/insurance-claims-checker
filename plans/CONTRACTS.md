# Component Contracts

Precise interface for every significant component: what it accepts, what it produces, and what
errors it can raise. Another engineer could reimplement any one of these from this alone. All
models live in [`src/claims/models.py`](src/claims/models.py); money is integer rupees.

## Shared types

```
DocumentType   = PRESCRIPTION | HOSPITAL_BILL | PHARMACY_BILL | LAB_REPORT
               | DIAGNOSTIC_REPORT | DISCHARGE_SUMMARY | DENTAL_REPORT | UNKNOWN
Quality        = GOOD | LOW | PARTIAL | UNREADABLE
ClaimCategory  = CONSULTATION | DIAGNOSTIC | PHARMACY | DENTAL | VISION | ALTERNATIVE_MEDICINE
Decision       = APPROVED | PARTIAL | REJECTED | MANUAL_REVIEW | NEEDS_RESUBMISSION
CheckStatus    = PASS | FAIL | FLAG | SKIPPED | ERROR
RejectionReason= EXCLUDED_CONDITION | WAITING_PERIOD | PRE_AUTH_MISSING | PER_CLAIM_EXCEEDED
               | INTAKE_INVALID | NOT_COVERED

LineItem { description: str, amount: int, covered: bool?, rejection_reason: str?,
           mapped_to: str?, map_confidence: float? }
CheckResult { name: str, status: CheckStatus, critical: bool, reasons: [str],
              data: dict, confidence_delta: float, user_facing_note: str? }
```

---

## ClaimInput  (system input)
```
ClaimInput {
  member_id: str, policy_id: str, claim_category: ClaimCategory,
  treatment_date: date, claimed_amount: int,
  hospital_name: str?, ytd_claims_amount: int = 0,
  claims_history: [ClaimHistoryEntry] = [],
  simulate_component_failure: bool = false,
  documents: [DocumentDescriptor], case_id: str?
}
DocumentDescriptor {
  file_id: str, file_name: str?, actual_type: DocumentType?, quality: Quality?,
  patient_name_on_doc: str?, content: dict?,      # injected (eval)
  raw_bytes: bytes?, mime_type: str?              # UI upload
}
```

## IntakeValidator
- **`run(claim: ClaimInput, as_of_date: date) -> (CheckResult, Member?)`**
- Checks: member exists in roster; `policy_id` matches; `claimed_amount ≥ minimum_claim_amount`;
  `as_of_date ≤ treatment_date + deadline_days`.
- Output: `CheckResult` (status PASS, or FAIL with reason `INTAKE_INVALID`) and the resolved `Member`
  (or `None`).
- Raises: nothing (lookups handled internally). The orchestrator turns a FAIL/None into a REJECTED.

## ExtractorBase  (interface)
- **`classify_and_extract(doc: DocumentDescriptor, category: ClaimCategory) -> ExtractedDocument`**
- `ExtractedDocument { file_id, doc_type, quality, patient_name?, content: dict,
   field_confidences: dict, extraction_confidence: float, warnings: [str] }`
- Raises: `ExtractionError` (and subclasses `LLMTimeoutError`/`LLMResponseParseError` via the client).

**InjectedExtractor** — maps test-case metadata/content into `ExtractedDocument`; `extraction_confidence = 1.0`
(ground truth). Never raises.

**GeminiExtractor** — sends `raw_bytes` + `mime_type` to Gemini with the `VisionExtraction` JSON schema;
maps the response into `ExtractedDocument`; derives `extraction_confidence` from self-reported quality and
warning count. Raises `ExtractionError` if bytes are missing or the LLM call fails.

## DocumentVerifier  (the gate)
- **`run(extracted: [ExtractedDocument], category: ClaimCategory) -> GateResult`**
- `GateResult { passed: bool, failure_kind: MISSING_DOC|WRONG_DOC|UNREADABLE|PATIENT_MISMATCH?,
   user_message: str?, details: dict }`
- Ordered: (1) required-type completeness, (2) readability of required docs, (3) cross-document patient-name
  consistency (normalized, 0.88 similarity threshold). On the first failure returns `passed=false` with a
  specific message naming the offending document(s)/type(s).
- Raises: nothing (gate failures are normal control flow).

## Check  (interface for all adjudication checks)
- **`run(ctx: AdjudicationContext) -> CheckResult`**; class attrs `name: str`, `critical: bool`.
- `AdjudicationContext { claim, member, policy, extracted, line_items, mapper, as_of_date,
   diagnoses: [str], treatments: [str], tests: [str] }`.
- Business outcomes are `CheckResult(status=FAIL/FLAG/PASS)`, never exceptions. Genuine internal errors may
  raise and are caught by the orchestrator (→ ERROR step, degradation).

| Check | `critical` | FAIL reason | Key output `data` |
|---|---|---|---|
| WaitingPeriodCheck | yes | `WAITING_PERIOD` | `mapped_condition, waiting_days, eligible_from` |
| ExclusionCheck | yes | `EXCLUDED_CONDITION` | `matched_exclusion` |
| PreAuthCheck | yes | `PRE_AUTH_MISSING` | `high_value_test_found, threshold, over_threshold` |
| CoverageCheck | yes | — (FLAG) | `covered_items, excluded_items, min_map_confidence` |
| LimitCheck | yes | `PER_CLAIM_EXCEEDED` | `covered_amount, effective_ceiling, binding_limit` |
| FinancialCheck | yes | — | `payable, covered_base, breakdown[]` |
| FraudCheck | **no** | — (FLAG) | `same_day_count, monthly_count, fraud_score, signals, manual_review` |

## SemanticMapper  (interface)
- **`map_waiting_condition(texts: [str]) -> Mapping`** → `{matched: condition_key?, confidence, method}`
- **`map_exclusion(texts: [str], category) -> Mapping`** → `{matched: exclusion_phrase?, confidence, method}`
- **`classify_line_item(description: str, category) -> LineItemClassification`** → `{covered, matched?, confidence, method, reason?}`
- `KeywordSemanticMapper` (deterministic, used in eval/tests and as fallback) — never raises.
- `GeminiSemanticMapper` — calls the LLM, falls back to keyword on `LLMError`, marking `method="llm_fallback_keyword"`.

## GeminiClient
- **`generate_structured(prompt: str, response_schema: type[BaseModel], parts: [(bytes, mime)]?, max_retries=1) -> dict`**
- Built by **`build_gemini_client(cfg)`** factory: `service_account` (Vertex, SA file) or `api_key` (Developer API).
- Retries 429/5xx with backoff. Raises `LLMAuthError` (401/403/credential), `LLMTimeoutError`,
  `LLMResponseParseError`, or `LLMError`.

## DecisionAggregator  (pure function)
- **`aggregate(inp: AggregationInput, claim_id: str) -> ClaimDecision`**
- `AggregationInput { claim, policy, gate: GateResult?, intake: CheckResult, checks: {name: CheckResult},
   line_items, extracted, degraded_components: [str], critical_degraded: bool }`
- `ClaimDecision { claim_id, decision: Decision?, status: Decision, approved_amount, reasons: [str],
   line_item_breakdown, financial_breakdown, confidence_score, fraud_signals, notes, degraded, user_message }`
- Applies the Tier 0→4 precedence and the confidence model. Raises nothing.

## Orchestrator
- **`process(claim: ClaimInput) -> (ClaimDecision, Trace)`**
- Runs intake → extraction → gate → adjudication → aggregate; wraps every call so exceptions become
  `ERROR` trace steps and the pipeline continues. **Never raises to the caller** — always returns a decision.
- `Trace { claim_id, case_id?, created_at, steps: [TraceStep], final_decision }`;
  `TraceStep { stage, component, status, started_at, ended_at, duration_ms, input_summary, output_summary,
   reasons, confidence_delta, error? }`.

## JsonAuditStore
- **`append(claim, decision, trace) -> Path`** — one JSON file per `claim_id` (write-once). Raises `AuditWriteError` (non-fatal).
- **`list_claims(member_id?) -> [dict]`**
- **`same_day_count(member_id, day: date) -> int`**, **`monthly_count(member_id, year, month) -> int`**

## ClaimsService  (facade)
- **`build_service(cfg?, use_llm: bool) -> ClaimsService`** — wires orchestrator + audit store for a mode.
- **`submit(claim) -> (ClaimDecision, Trace)`** — process + persist; audit failure is downgraded to a note.
