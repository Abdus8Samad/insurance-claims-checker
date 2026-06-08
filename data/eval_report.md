# Eval Report

**12/12 cases passed.** Deterministic run: InjectedExtractor + KeywordSemanticMapper, as_of_date frozen to each case's treatment date.

| Case | Name | Expected | Produced | Amount | Conf | Result |
|---|---|---|---|---:|---:|---|
| TC001 | Wrong Document Uploaded | — | null | ₹0 | 1.00 | PASS |
| TC002 | Unreadable Document | — | null | ₹0 | 1.00 | PASS |
| TC003 | Documents Belong to Different Patients | — | null | ₹0 | 1.00 | PASS |
| TC004 | Clean Consultation — Full Approval | — | APPROVED | ₹1,350 | 0.95 | PASS |
| TC005 | Waiting Period — Diabetes | — | REJECTED | ₹0 | 0.95 | PASS |
| TC006 | Dental Partial Approval — Cosmetic Exclusion | — | PARTIAL | ₹8,000 | 0.95 | PASS |
| TC007 | MRI Without Pre-Authorization | — | REJECTED | ₹0 | 0.95 | PASS |
| TC008 | Per-Claim Limit Exceeded | — | REJECTED | ₹0 | 0.95 | PASS |
| TC009 | Fraud Signal — Multiple Same-Day Claims | — | MANUAL_REVIEW | ₹4,320 | 0.95 | PASS |
| TC010 | Network Hospital — Discount Applied | — | APPROVED | ₹3,240 | 0.95 | PASS |
| TC011 | Component Failure — Graceful Degradation | — | APPROVED | ₹4,000 | 0.75 | PASS |
| TC012 | Excluded Treatment | — | REJECTED | ₹0 | 0.95 | PASS |

---

### Claim `CLM_0acc4e8c53` — case TC001

- **Decision:** null (NEEDS_RESUBMISSION)
- **Approved amount:** ₹0
- **Confidence:** 1.00
- **Reasons:** MISSING_DOC
- **Member message:** This CONSULTATION claim requires the following document type(s): PRESCRIPTION, HOSPITAL_BILL. You uploaded: 2× PRESCRIPTION. Missing required document(s): HOSPITAL_BILL. Please upload the missing HOSPITAL_BILL and resubmit.
- **Notes:** Stopped at document verification; no claim decision was made.

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F001] | PASS | 0 |  |
| extraction | Extractor[F002] | PASS | 0 |  |
| document_verification | DocumentVerifier | FAIL | 0 |  |

---

### Claim `CLM_91a59cb74a` — case TC002

- **Decision:** null (NEEDS_RESUBMISSION)
- **Approved amount:** ₹0
- **Confidence:** 1.00
- **Reasons:** UNREADABLE
- **Member message:** The document you uploaded as your PHARMACY_BILL (file 'F004') could not be read — it appears blurry or unreadable. Please re-upload a clearer photo or scan of your PHARMACY_BILL. The rest of your submission looks fine; only this document needs to be replaced.
- **Notes:** Stopped at document verification; no claim decision was made.

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F003] | PASS | 0 |  |
| extraction | Extractor[F004] | PASS | 0 |  |
| document_verification | DocumentVerifier | FAIL | 0 |  |

---

### Claim `CLM_731a0e0ebc` — case TC003

- **Decision:** null (NEEDS_RESUBMISSION)
- **Approved amount:** ₹0
- **Confidence:** 1.00
- **Reasons:** PATIENT_MISMATCH
- **Member message:** The documents appear to belong to different patients: 'Rajesh Kumar' on file 'F005' and 'Arjun Mehta' on file 'F006'. All documents in a single claim must be for the same patient. Please check you have uploaded the correct documents and resubmit.
- **Notes:** Stopped at document verification; no claim decision was made.

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F005] | PASS | 0 |  |
| extraction | Extractor[F006] | PASS | 0 |  |
| document_verification | DocumentVerifier | FAIL | 0 |  |

---

### Claim `CLM_7d55231207` — case TC004

- **Decision:** APPROVED
- **Approved amount:** ₹1,350
- **Confidence:** 0.95
- **Reasons:** APPROVED

| Line item | Amount | Covered | Reason |
|---|---:|---|---|
| Consultation Fee | ₹1,000 | ✓ |  |
| CBC Test | ₹300 | ✓ |  |
| Dengue NS1 Test | ₹200 | ✓ |  |

**Financial breakdown:**
- `covered_base` → ₹1,500  {}
- `network_discount` → ₹1,500  {"hospital": "City Clinic, Bengaluru", "is_network": false, "discount_percent": 0}
- `copay` → ₹1,350  {"copay_percent": 10, "copay_deducted": 150}
- `annual_cap` → ₹1,350  {"annual_opd_limit": 50000, "ytd_claims_amount": 5000, "annual_remaining": 45000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F007] | PASS | 0 |  |
| extraction | Extractor[F008] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | PASS | 0 |  |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | PASS | 0 |  |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | PASS | 0 |  |

---

### Claim `CLM_60212106df` — case TC005

- **Decision:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.95
- **Reasons:** WAITING_PERIOD
- **Member message:** This claim is for diabetes, which has a 90-day waiting period from your policy start (2024-09-01). You will be eligible for diabetes-related claims from 2024-11-30.
- **Notes:** This claim is for diabetes, which has a 90-day waiting period from your policy start (2024-09-01). You will be eligible for diabetes-related claims from 2024-11-30.

**Financial breakdown:**
- `covered_base` → ₹3,000  {}
- `network_discount` → ₹3,000  {"hospital": null, "is_network": false, "discount_percent": 0}
- `copay` → ₹2,700  {"copay_percent": 10, "copay_deducted": 300}
- `annual_cap` → ₹2,700  {"annual_opd_limit": 50000, "ytd_claims_amount": 0, "annual_remaining": 50000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F009] | PASS | 0 |  |
| extraction | Extractor[F010] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | FAIL | 0 | WAITING_PERIOD |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | PASS | 0 |  |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | PASS | 0 |  |

---

### Claim `CLM_edf8299e2e` — case TC006

- **Decision:** PARTIAL
- **Approved amount:** ₹8,000
- **Confidence:** 0.95
- **Reasons:** PARTIAL
- **Member message:** Some billed items were approved and others were excluded. Teeth Whitening excluded ('Teeth Whitening' is excluded under the DENTAL category)

| Line item | Amount | Covered | Reason |
|---|---:|---|---|
| Root Canal Treatment | ₹8,000 | ✓ |  |
| Teeth Whitening | ₹4,000 | ✗ | 'Teeth Whitening' is excluded under the DENTAL category |

**Financial breakdown:**
- `covered_base` → ₹8,000  {}
- `network_discount` → ₹8,000  {"hospital": "Smile Dental Clinic", "is_network": false, "discount_percent": 0}
- `copay` → ₹8,000  {"copay_percent": 0, "copay_deducted": 0}
- `annual_cap` → ₹8,000  {"annual_opd_limit": 50000, "ytd_claims_amount": 0, "annual_remaining": 50000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F011] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | PASS | 0 |  |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | FLAG | 0 | Excluded: Teeth Whitening — 'Teeth Whitening' is excluded under the DENTAL category |
| adjudication | LimitCheck | PASS | 0 |  |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | PASS | 0 |  |

---

### Claim `CLM_bf1029698c` — case TC007

- **Decision:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.95
- **Reasons:** WAITING_PERIOD, PRE_AUTH_MISSING, PER_CLAIM_EXCEEDED
- **Member message:** This claim is for hernia, which has a 365-day waiting period from your policy start (2024-04-01). You will be eligible for hernia-related claims from 2025-04-01. MRI above ₹10,000 requires pre-authorization before the procedure, which was not obtained for this claim. To resubmit: obtain pre-authorization from the insurer for the MRI, then submit the claim with the pre-authorization reference number attached. The covered amount of ₹15,000 exceeds the DIAGNOSTIC sub-limit of ₹10,000. The claim cannot be approved as submitted.
- **Notes:** This claim is for hernia, which has a 365-day waiting period from your policy start (2024-04-01). You will be eligible for hernia-related claims from 2025-04-01. MRI above ₹10,000 requires pre-authorization before the procedure, which was not obtained for this claim. To resubmit: obtain pre-authorization from the insurer for the MRI, then submit the claim with the pre-authorization reference number attached. The covered amount of ₹15,000 exceeds the DIAGNOSTIC sub-limit of ₹10,000. The claim cannot be approved as submitted.

| Line item | Amount | Covered | Reason |
|---|---:|---|---|
| MRI Lumbar Spine | ₹15,000 | ✓ |  |

**Financial breakdown:**
- `covered_base` → ₹15,000  {}
- `network_discount` → ₹15,000  {"hospital": null, "is_network": false, "discount_percent": 0}
- `copay` → ₹15,000  {"copay_percent": 0, "copay_deducted": 0}
- `annual_cap` → ₹15,000  {"annual_opd_limit": 50000, "ytd_claims_amount": 0, "annual_remaining": 50000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F012] | PASS | 0 |  |
| extraction | Extractor[F013] | PASS | 0 |  |
| extraction | Extractor[F014] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | FAIL | 0 | WAITING_PERIOD |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | FAIL | 0 | PRE_AUTH_MISSING |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | FAIL | 0 | PER_CLAIM_EXCEEDED |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | PASS | 0 |  |

---

### Claim `CLM_472770fd6f` — case TC008

- **Decision:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.95
- **Reasons:** PER_CLAIM_EXCEEDED
- **Member message:** The claimed amount of ₹7,500 exceeds the per-claim limit of ₹5,000 for this policy. The claim cannot be approved as submitted.
- **Notes:** The claimed amount of ₹7,500 exceeds the per-claim limit of ₹5,000 for this policy. The claim cannot be approved as submitted.

| Line item | Amount | Covered | Reason |
|---|---:|---|---|
| Consultation Fee | ₹2,000 | ✓ |  |
| Medicines | ₹5,500 | ✓ |  |

**Financial breakdown:**
- `covered_base` → ₹7,500  {}
- `network_discount` → ₹7,500  {"hospital": null, "is_network": false, "discount_percent": 0}
- `copay` → ₹6,750  {"copay_percent": 10, "copay_deducted": 750}
- `annual_cap` → ₹6,750  {"annual_opd_limit": 50000, "ytd_claims_amount": 10000, "annual_remaining": 40000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F015] | PASS | 0 |  |
| extraction | Extractor[F016] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | PASS | 0 |  |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | FAIL | 0 | PER_CLAIM_EXCEEDED |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | PASS | 0 |  |

---

### Claim `CLM_9a14d45dee` — case TC009

- **Decision:** MANUAL_REVIEW
- **Approved amount:** ₹4,320
- **Confidence:** 0.95
- **Reasons:** MANUAL_REVIEW
- **Fraud signals:** Same-day claims: 4 claims on 2024-10-30 exceeds the limit of 2
- **Member message:** This claim has been routed to manual review. Same-day claims: 4 claims on 2024-10-30 exceeds the limit of 2
- **Notes:** Same-day claims: 4 claims on 2024-10-30 exceeds the limit of 2

**Financial breakdown:**
- `covered_base` → ₹4,800  {}
- `network_discount` → ₹4,800  {"hospital": null, "is_network": false, "discount_percent": 0}
- `copay` → ₹4,320  {"copay_percent": 10, "copay_deducted": 480}
- `annual_cap` → ₹4,320  {"annual_opd_limit": 50000, "ytd_claims_amount": 0, "annual_remaining": 50000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F017] | PASS | 0 |  |
| extraction | Extractor[F018] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | PASS | 0 |  |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | PASS | 0 |  |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | FLAG | 0 | Same-day claims: 4 claims on 2024-10-30 exceeds the limit of 2 |

---

### Claim `CLM_31c5f8aa4b` — case TC010

- **Decision:** APPROVED
- **Approved amount:** ₹3,240
- **Confidence:** 0.95
- **Reasons:** APPROVED

| Line item | Amount | Covered | Reason |
|---|---:|---|---|
| Consultation Fee | ₹1,500 | ✓ |  |
| Medicines | ₹3,000 | ✓ |  |

**Financial breakdown:**
- `covered_base` → ₹4,500  {}
- `network_discount` → ₹3,600  {"hospital": "Apollo Hospitals", "is_network": true, "discount_percent": 20}
- `copay` → ₹3,240  {"copay_percent": 10, "copay_deducted": 360}
- `annual_cap` → ₹3,240  {"annual_opd_limit": 50000, "ytd_claims_amount": 8000, "annual_remaining": 42000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F019] | PASS | 0 |  |
| extraction | Extractor[F020] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | PASS | 0 |  |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | PASS | 0 |  |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | PASS | 0 |  |

---

### Claim `CLM_817c174201` — case TC011

- **Decision:** APPROVED
- **Approved amount:** ₹4,000
- **Confidence:** 0.75
- **Reasons:** APPROVED
- **Degraded:** yes
- **Member message:** Manual review recommended: processing was incomplete — the following component(s) failed and were skipped: fraud. The decision was made from the remaining checks and confidence was reduced accordingly.
- **Notes:** Manual review recommended: processing was incomplete — the following component(s) failed and were skipped: fraud. The decision was made from the remaining checks and confidence was reduced accordingly.

| Line item | Amount | Covered | Reason |
|---|---:|---|---|
| Panchakarma Therapy (5 sessions) | ₹3,000 | ✓ |  |
| Consultation | ₹1,000 | ✓ |  |

**Financial breakdown:**
- `covered_base` → ₹4,000  {}
- `network_discount` → ₹4,000  {"hospital": "Ayur Wellness Centre", "is_network": false, "discount_percent": 0}
- `copay` → ₹4,000  {"copay_percent": 0, "copay_deducted": 0}
- `annual_cap` → ₹4,000  {"annual_opd_limit": 50000, "ytd_claims_amount": 0, "annual_remaining": 50000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F021] | PASS | 0 |  |
| extraction | Extractor[F022] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | PASS | 0 |  |
| adjudication | ExclusionCheck | PASS | 0 |  |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | PASS | 0 |  |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | ERROR | 0 | _ForcedFailure: Simulated failure of the fraud component (TC011) |

---

### Claim `CLM_08d83c4184` — case TC012

- **Decision:** REJECTED
- **Approved amount:** ₹0
- **Confidence:** 0.95
- **Reasons:** EXCLUDED_CONDITION, PER_CLAIM_EXCEEDED
- **Member message:** This claim relates to 'Obesity and weight loss programs', which is explicitly excluded under your policy and cannot be reimbursed. The claimed amount of ₹8,000 exceeds the per-claim limit of ₹5,000 for this policy. The claim cannot be approved as submitted.
- **Notes:** This claim relates to 'Obesity and weight loss programs', which is explicitly excluded under your policy and cannot be reimbursed. The claimed amount of ₹8,000 exceeds the per-claim limit of ₹5,000 for this policy. The claim cannot be approved as submitted.

| Line item | Amount | Covered | Reason |
|---|---:|---|---|
| Bariatric Consultation | ₹3,000 | ✓ |  |
| Personalised Diet and Nutrition Program | ₹5,000 | ✓ |  |

**Financial breakdown:**
- `covered_base` → ₹8,000  {}
- `network_discount` → ₹8,000  {"hospital": null, "is_network": false, "discount_percent": 0}
- `copay` → ₹7,200  {"copay_percent": 10, "copay_deducted": 800}
- `annual_cap` → ₹7,200  {"annual_opd_limit": 50000, "ytd_claims_amount": 0, "annual_remaining": 50000, "capped": false}

**Trace:**

| Stage | Component | Status | ms | Reasons / Error |
|---|---|---|---:|---|
| intake | IntakeValidator | PASS | 0 |  |
| extraction | Extractor[F023] | PASS | 0 |  |
| extraction | Extractor[F024] | PASS | 0 |  |
| document_verification | DocumentVerifier | PASS | 0 |  |
| adjudication | WaitingPeriodCheck | PASS | 0 |  |
| adjudication | ExclusionCheck | FAIL | 0 | EXCLUDED_CONDITION |
| adjudication | PreAuthCheck | PASS | 0 |  |
| adjudication | CoverageCheck | PASS | 0 |  |
| adjudication | LimitCheck | FAIL | 0 | PER_CLAIM_EXCEEDED |
| adjudication | FinancialCheck | PASS | 0 |  |
| adjudication | FraudCheck | PASS | 0 |  |

---
