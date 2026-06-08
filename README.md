# Plum — Health Insurance Claims Processing System

An explainable, multi-agent pipeline that automates the review of employee health-insurance
claims: it accepts a submission, catches document problems early with specific actionable
messages, extracts structured data from messy documents (Gemini vision), adjudicates against
the policy, and produces an `APPROVED / PARTIAL / REJECTED / MANUAL_REVIEW` decision with an
approved amount, reasons, a confidence score, and a full decision trace.

- **Architecture & design rationale:** [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **Component contracts (inputs / outputs / errors):** [`CONTRACTS.md`](CONTRACTS.md)
- **Eval report (all 12 cases, full traces):** [`data/eval_report.md`](data/eval_report.md) — regenerate with `python -m eval.run_eval`

---

## What it does

1. **Accepts a claim** — member, treatment type, claimed amount, and one or more documents (images/PDFs).
2. **Catches document problems early** — a verification *gate* runs before any adjudication and stops with a
   precise, actionable message (missing/wrong document type, unreadable document, or documents belonging to
   different patients). This is distinct from a rejection: `decision = null`, status `NEEDS_RESUBMISSION`.
3. **Extracts structured information** — Gemini vision for real uploads; injected content for the eval cases,
   behind one extractor interface.
4. **Makes an explainable decision** — deterministic rules read from `policy_terms.json` (waiting periods,
   exclusions, pre-auth, limits, network discount → co-pay, fraud). The LLM is used only for reading and
   semantic mapping, never for the money math.
5. **Degrades gracefully** — every component is wrapped; a failure is recorded in the trace, confidence is
   reduced, and the pipeline continues. It never crashes.

## Design in one picture

```
intake → extraction → [GATE] → waiting · exclusions · pre-auth · coverage · limits · financial · fraud → aggregate → trace + audit
                         │                         (run all, collect findings)              │
                  stop w/ message                                                    precedence + confidence
```

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the full reasoning, trade-offs, and 10× scaling notes.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # or: pip install -e ".[dev]" for tests

# Run the 12 spec test cases (no LLM, deterministic) and regenerate the eval report:
python -m eval.run_eval

# Run the test suite:
pytest

# Launch the UI:
streamlit run app/streamlit_app.py
```

The **eval** and **tests** need no API credentials — they run the deterministic path
(`InjectedExtractor` + `KeywordSemanticMapper`). Only the UI's "Submit a Claim" tab with the
Gemini-vision toggle on requires credentials.

## Configuring Gemini (UI vision extraction)

Copy `.env.example` to `.env`. The `GeminiClient` supports **two auth modes** via one factory:

| `GEMINI_AUTH_MODE` | Needs | Backend |
|---|---|---|
| `service_account` (default) | `GOOGLE_APPLICATION_CREDENTIALS` (path to SA JSON), `VERTEX_LOCATION` | Vertex AI |
| `api_key` | `GEMINI_API_KEY` | Gemini Developer API |

`GEMINI_MODEL` defaults to `gemini-2.5-flash` (vision + native PDF). Both modes expose the
identical call interface, so only the factory differs — switch modes by changing one env var.

## Repository layout

```
src/claims/
  models.py            Pydantic models + enums (the shared vocabulary)
  policy.py  roster.py Typed accessors over policy_terms.json (no hardcoded rules)
  config.py            Env-driven AppConfig
  llm/                 Gemini client (2 auth modes), semantic mappers, prompts/schemas
  extraction/          ExtractorBase + InjectedExtractor (eval) + GeminiExtractor (UI)
  pipeline/            intake, document_verifier (gate), checks/*, aggregator, orchestrator
  trace.py             Trace renderers (dict / markdown)
  audit/store.py       JSON-file audit log + fraud history counts
  service.py           Wires an orchestrator + audit store for a mode
app/                   Streamlit UI
eval/                  Test-case loader, runner, report builder
tests/                 Unit + parametrized eval regression tests
config/policy_terms.json
data/
  eval_report.md       Eval results — every case's decision, amount, confidence + full trace
  eval_report.json     Same, machine-readable (per-assertion pass/fail)
  audit/               Runtime audit log — one JSON file per processed claim (gitignored)
```

## Testing & results

`pytest` runs 55 tests: per-check unit tests, intake, the gate, the aggregator precedence
matrix, orchestrator graceful-degradation, the audit store, the LLM fallback, and a
parametrized regression test over all 12 spec cases. The deterministic path means the suite is
fully reproducible and offline.

**Where to find the results:**

| What | How to get it | Persisted? |
|---|---|---|
| Unit/component tests (55) | `pytest` — prints `55 passed` to the terminal | no (run to view) |
| **Eval results** (12 spec cases) | `python -m eval.run_eval` | ✅ `data/eval_report.md` + `data/eval_report.json` |
| Optional JUnit XML | `pytest --junitxml=data/test_results.xml` | ✅ if run |
| Optional coverage | `pytest --cov=claims --cov-report=html` | ✅ `htmlcov/` |

The committed [`data/eval_report.md`](data/eval_report.md) is the primary results artifact — it
shows, for each of the 12 cases, the decision the system produced, the full trace, and whether it
matched the expected outcome.
