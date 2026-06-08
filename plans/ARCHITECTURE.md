# Architecture

## 1. The problem and the shape of the solution

A member submits a claim — member details, treatment type, claimed amount, and one or more
documents. The system must decide `APPROVED / PARTIAL / REJECTED / MANUAL_REVIEW`, attach an
approved amount, reasons, and a confidence score, and make the whole thing reconstructable
after the fact. Two properties dominate every design choice:

1. **Explainability is a first-class output, not a log.** Operations must be able to read *why*
   a claim got its decision. So the trace is a structured artifact produced by the pipeline, and
   every check — even ones that passed, even ones that were skipped — appears in it.
2. **Money decisions must be trustworthy.** An LLM is the right tool for reading a blurry
   handwritten prescription; it is the wrong tool for deciding whether ₹3,600 minus a 10% co-pay
   is correct. So the system is a **hybrid**: LLMs read and map meaning; deterministic code
   applies policy and computes money.

## 2. Component model (multi-agent pipeline)

The pipeline is a sequence of single-responsibility components ("agents") coordinated by a
lightweight custom **Orchestrator**. There is no agent framework (LangGraph/CrewAI): the control
flow here is a deterministic staged pipeline with fan-in at the decision step, and a hand-rolled
orchestrator makes that flow — and its failure handling — completely transparent, which is
exactly what the observability requirement rewards.

```
                 ┌──────────┐   ┌────────────┐   ┌───────────────────┐
ClaimInput  ───► │  Intake  ├──►│ Extraction ├──►│ Document Verifier  │── fail ─► NEEDS_RESUBMISSION
                 └──────────┘   └────────────┘   │      (GATE)        │           (decision = null)
                                                 └─────────┬──────────┘
                                                      pass │
                          ┌──────────────────────────────────────────────────────────┐
                          │                    Adjudication (run all)                  │
                          │  waiting · exclusions · pre_auth · coverage · limits ·     │
                          │  financial · fraud      → each emits a CheckResult         │
                          └───────────────────────────────┬──────────────────────────┘
                                                           ▼
                                              ┌─────────────────────────┐
                                              │   Decision Aggregator    │  precedence + confidence
                                              └────────────┬────────────┘
                                                           ▼
                                        ClaimDecision + Trace ──► JSON Audit Store
```

| Component | Responsibility | Intelligence |
|---|---|---|
| **IntakeValidator** | member exists, policy matches, amount/window valid | deterministic |
| **Extractor** (`Injected` / `Gemini`) | classify doc type, quality, patient, content | LLM (UI) / injected (eval) |
| **DocumentVerifier** (gate) | required-type completeness → readability → patient consistency | deterministic |
| **WaitingPeriodCheck** | diagnosis → condition key; eligible-date math | LLM map + deterministic math |
| **ExclusionCheck** | diagnosis/treatment → policy exclusion (whole-claim) | LLM map + deterministic verdict |
| **PreAuthCheck** | high-value test above threshold without pre-auth | deterministic |
| **CoverageCheck** | per-line-item covered/excluded (drives PARTIAL) | LLM classify + deterministic sum |
| **LimitCheck** | per-claim ceiling (hard reject) | deterministic |
| **FinancialCheck** | network discount → co-pay → annual cap | deterministic |
| **FraudCheck** *(non-critical)* | same-day/monthly counts, high-value | deterministic |
| **DecisionAggregator** | precedence resolution, confidence, message | deterministic (pure) |
| **Orchestrator** | run stages, wrap failures, build trace | deterministic |
| **JsonAuditStore** | persist claim + trace, fraud history counts | deterministic |

Each adjudication check is an independent object implementing `Check.run(ctx) -> CheckResult`.
Checks **never short-circuit each other** — they all run and emit findings, and the aggregator
resolves precedence at the end. This is deliberate: a rejected claim's trace still shows that
fraud and limits were evaluated, so a reviewer can reconstruct the *complete* state, not just the
first failing rule.

## 3. Why this decomposition

- **Separation of reading from ruling.** All LLM use is confined to `extraction/` and the
  `SemanticMapper`. Everything that touches money or eligibility is deterministic and reads its
  numbers from `policy_terms.json`. This is what makes decisions reproducible and auditable, and
  it means a model regression can never silently change a payout.
- **The gate is a separate stage, not a check.** Document problems are categorically different
  from claim rejections — the member needs to *do something and resubmit*, not be told "no." The
  gate short-circuits with `decision = null` and a specific message, and never reaches adjudication.
- **One extractor interface, two implementations.** The eval injects ground-truth content; the UI
  runs real Gemini vision. The orchestrator and all checks are identical in both paths, so the 12
  cases exercise the exact production decision logic — only the bytes→fields step differs.
- **Confidence is computed, explainable, and bounded.** It starts at 0.95 and accumulates labeled
  penalties (doc quality, uncertain mapping, skipped component), each visible in the trace.

## 4. The decision logic

### Precedence (aggregator)
```
Tier 0  gate failed                         → decision = null (NEEDS_RESUBMISSION)
Tier 1  any hard rejection                   → REJECTED         (list ALL reasons)
Tier 2  fraud / high-value / critical-degrade → MANUAL_REVIEW
Tier 3  some line items excluded, some covered → PARTIAL
Tier 4  otherwise                            → APPROVED
```
Hard rejections (`EXCLUDED_CONDITION`, `WAITING_PERIOD`, `PRE_AUTH_MISSING`, `PER_CLAIM_EXCEEDED`,
`INTAKE_INVALID`) are *categorical ineligibility* — the member was never entitled to this claim.
**Hard rejection beats manual review:** routing a definitionally-rejected claim to a human adds
cost with no upside, and the fraud signal is still recorded in the trace. No test forces the
conflict; this is a documented, defensible tie-break.

### Financial order (mandated)
`covered_base → network discount (if network hospital) → co-pay → annual-OPD cap`.
Network discount is applied **before** co-pay (TC010: ₹4,500 ×0.8 = ₹3,600 ×0.9 = **₹3,240**).
Because two multiplicative percentages commute, a unit test asserts the *step order itself*, not
just the final number.

### Confidence
Base **0.95**, minus: doc quality (−0.08/doc), low-confidence field (−0.03), uncertain semantic
mapping <0.8 (−0.10), **non-critical component skipped (−0.20)**, critical failure (−0.35), LLM
keyword-fallback (−0.10). Clamped to `[0.30, 1.0]`; below the floor escalates to MANUAL_REVIEW.

### Graceful degradation
The orchestrator wraps every component call. An exception becomes an `ERROR` trace step; the
component is added to `degraded_components` and the pipeline continues. A failed **non-critical**
check (fraud) only lowers confidence and adds a "manual review recommended" note — the
deterministic decision stands (TC011 → still APPROVED, confidence 0.75). A failed **critical**
check forces MANUAL_REVIEW because no safe automated decision is possible. The `simulate_component_failure`
flag injects a real exception into the fraud check, so the genuine try/except path is exercised
rather than special-cased.

## 5. Resolved spec ambiguities (conscious trade-offs)

1. **Per-claim limit vs sub-limits.** The policy's `per_claim_limit` (₹5,000) and category
   `sub_limit`s are mutually inconsistent against the ground truth: TC008 rejects consultation
   ₹7,500 (>5,000); TC006 approves dental ₹8,000 (>5,000); TC010 approves consultation ₹3,240
   (> the consultation sub_limit of 2,000). The single rule consistent with all three:
   **ceiling = `max(category.sub_limit, per_claim_limit)`; exceeding it → REJECTED `PER_CLAIM_EXCEEDED`.**
   Consultation binds on 5,000; dental binds on its 10,000 sub-limit. The consultation sub-limit of
   2,000 is treated as informational (TC010 requires it). Implemented in `policy.effective_claim_ceiling`.
2. **Submission-deadline clock.** No case carries a submission date, and the treatment dates are >30
   days before "today," so a real `now()` would fail every case on the deadline. `as_of_date` is
   injectable: eval freezes it to the treatment date; the UI uses real `today()`.
3. **Obesity is excluded, not waiting-period.** Obesity appears in *both* the exclusions and the
   waiting-period table. It is handled as an exclusion only (a permanent bar), so TC012 produces a
   clean `EXCLUDED_CONDITION` rather than also flagging a waiting period.
4. **Pre-auth detection.** Absence of any pre-auth reference in the documents is treated as "not
   obtained." A production system would query a pre-auth registry.
5. **Treatment date authority.** `claim.treatment_date` is authoritative for date math (documents
   may omit dates, as in TC005).
6. **Patient consistency is doc-vs-doc**, not doc-vs-roster, with honorific/case/whitespace
   normalization and an 0.88 similarity threshold to tolerate OCR noise without false positives.

## 6. What I considered and rejected

- **An agent framework (LangGraph/CrewAI).** Rejected: the flow is a deterministic staged pipeline,
  not a dynamic agent conversation. A framework would add abstraction between the decision and the
  trace — the opposite of what observability needs here.
- **LLM-driven adjudication / "ask the model to decide the payout."** Rejected: non-reproducible,
  unauditable, and impossible to unit-test against exact rupee amounts. The LLM reads; rules rule.
- **A single mega-extraction-and-decision prompt.** Rejected: collapses separation of concerns,
  makes failures all-or-nothing, and defeats graceful degradation.
- **A real database.** Deferred (per scope): a JSON-file audit log gives a complete audit trail and
  the fraud-history counts we need, with zero infra. Section 8 covers the migration.
- **Per-claim soft-capping at sub-limit instead of rejecting.** Rejected because TC008 expects a full
  rejection when the per-claim limit is exceeded, not a capped payout.

## 7. Limitations of the current design

- **Document classification trusts the model's `doc_type`** in the UI path; a mis-classification
  could mis-route the gate. Mitigation today: quality/patient checks and confidence penalties; a
  production fix is a second-opinion classifier or a human confirm step on low confidence.
- **Fraud detection is threshold-based**, not behavioral/graph-based; it catches the volume signals
  the policy defines but not collusion across members or providers.
- **Branded-drug co-pay and the annual-OPD cap are implemented but lightly exercised** by the 12
  cases (covered by extra unit tests).
- **Single-process, synchronous.** Fine for the assignment; Section 8 addresses scale.
- **No idempotency key** on submission yet — a double-submit creates two audit records.

## 8. Scaling to 10× (and beyond)

The architecture is already shaped for this: components are pure-ish and stateless, the orchestrator
is the only coordinator, and persistence is behind one interface.

- **Async + batching.** The only slow, IO-bound step is Gemini extraction. Make extraction `async`
  and run a claim's documents concurrently; the deterministic checks stay synchronous (microseconds).
  At fleet scale, move extraction to a queue (e.g. SQS/PubSub) with a worker pool and Vertex batch
  prediction for non-interactive claims.
- **Stateless API + horizontal scale.** Wrap the orchestrator in a stateless FastAPI service behind a
  load balancer; the pipeline holds no per-request global state.
- **Swap the audit store for a database.** `JsonAuditStore` is one interface (`append`, `list_claims`,
  `same_day_count`, `monthly_count`). Replace with Postgres (claims + traces as JSONB) without
  touching the pipeline; the fraud-count queries become indexed SQL. Add an idempotency key on
  `(member_id, treatment_date, claimed_amount, doc-hash)`.
- **Cache + cost control.** Cache extraction by document hash (the same bill is often resubmitted);
  use `gemini-2.5-flash` for the bulk and escalate to `pro` only on low extraction confidence.
- **Decouple read from rule for independent scaling.** Extraction (GPU/LLM-bound) and adjudication
  (CPU, trivial) scale on different curves; splitting them into separate services lets each scale to
  its own bottleneck.
- **Observability at scale.** The per-step trace is already structured; ship it to a warehouse to
  monitor decision-mix drift, confidence distribution, and gate-failure reasons over time.
- **Policy versioning.** Stamp each decision with the policy hash/version so historical decisions
  remain explainable after the policy changes.
