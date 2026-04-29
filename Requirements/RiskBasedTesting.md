# Risk-Based Testing (RBT)

Since we are operating in a GxP environment (GLP/GMP), the transition from **URS** to **Risk-Based Testing (RBT)** is critical for compliance with **GAMP 5**.

---

## 1. Risk Analysis (FMEA)

The risk analysis below uses the standard **FMEA (Failure Mode and Effects Analysis)** approach, assessing **Severity (S)**, **Probability (P)**, and **Detectability (D)** to determine the **Risk Priority Number (RPN)**. This informs the depth of your Playwright test cases.

| ID | Requirement Ref | Potential Hazard | Severity (1-5) | Prob. (1-5) | Detect. (1-5) | RPN | Risk Level |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **R1** | REQ-SIG-01 | Signature bypass or invalidation failure. | 5 | 1 | 2 | **10** | **High** |
| **R2** | REQ-PDF-03 | Field mapping mismatch (wrong data in DB). | 5 | 2 | 4 | **40** | **High** |
| **R3** | REQ-TRN-02 | Untrained staff performing GxP actions. | 4 | 2 | 3 | **24** | **Medium** |
| **R4** | REQ-AUD-01 | Audit trail entry not created or editable. | 5 | 1 | 5 | **25** | **High** |
| **R5** | REQ-DM-01 | Duplicate UUID generation/Collision. | 3 | 1 | 2 | **6** | **Low** |

---

## 2. Risk-Based Test Cases (Playwright)

Based on the RPNs above, we prioritize the "High" risk items with rigorous edge-case testing.

### Test Case 1: Integrity of Data Extraction (High Risk)
**Focus:** Validates `REQ-PDF-02` and `REQ-PDF-03`.
* **Test Objective:** Ensure the `Field-UUID` mapping is deterministic and independent of UI labels.
* **Pre-conditions:** A template `DOC-123` exists with field `FLD-456`.
* **Playwright Script Logic:**
    1.  **Step:** Generate the PDF via the API.
    2.  **Assertion:** Verify the downloaded PDF contains an AcroForm field named `FLD-456`.
    3.  **Step:** Programmatically fill the PDF with value `"7.2"` and upload it.
    4.  **Assertion:** Query the Postgres DB directly (via a test utility) to ensure the column associated with `FLD-456` contains exactly `7.2`.
* **Acceptance Criteria:** Data must be mapped by UUID, not by the visual string "pH-Value".

### Test Case 2: Cryptographic Signature & Invalidation (High Risk)
**Focus:** Validates `REQ-SIG-01` (CFR 21 Part 11).
* **Test Objective:** Ensure the PAdES signature is applied and breaks upon tampering.
* **Pre-conditions:** SOP is in `Review` status.
* **Playwright Script Logic:**
    1.  **Step:** Trigger "Approve" action.
    2.  **Assertion:** Verify the `re-authentication` modal appears.
    3.  **Step:** Input valid credentials.
    4.  **Assertion:** Download the signed PDF and verify the visual stamp (Name/Date/Reason) exists.
    5.  **Step (Negative Test):** Simulate an unauthorized modification to the PDF file bytes.
    6.  **Assertion:** Use a PDF library (e.g., `pdf-lib`) to verify the signature status is reported as `INVALID`.
* **Acceptance Criteria:** Digital signature must be cryptographic and linked to the user's identity.

### Test Case 3: Training Gate "Hard Stop" (Medium Risk)
**Focus:** Validates `REQ-TRN-02`.
* **Test Objective:** Prevent GxP non-compliance by blocking untrained users.
* **Pre-conditions:** SOP-A v2.0 is active; User X has only v1.0 training.
* **Playwright Script Logic:**
    1.  **Step:** Log in as User X.
    2.  **Step:** Attempt to POST a report creation request using the v2.0 template.
    3.  **Assertion:** Verify the response is `403 Forbidden`.
    4.  **Assertion:** Verify the UI displays the specific string: *"Action denied: Valid training record for SOP-A Version 2.0 is missing."*
* **Acceptance Criteria:** System must enforce the training state before allowing data entry.

### Test Case 4: Audit Trail Immutability (High Risk)
**Focus:** Validates `REQ-AUD-01`.
* **Test Objective:** Ensure every change is logged and the log cannot be deleted.
* **Pre-conditions:** A record exists with value "10".
* **Playwright Script Logic:**
    1.  **Step:** Change value from "10" to "15" and provide reason "Correction".
    2.  **Assertion:** Check the audit table via API/DB for a new entry containing "10", "15", and the "Correction" string.
    3.  **Step (Negative Test):** Attempt a `DELETE` request to the audit trail endpoint using a SuperAdmin token.
    4.  **Assertion:** Verify `405 Method Not Allowed` or `403 Forbidden`.
* **Acceptance Criteria:** No user or admin can delete audit logs via the application layer.

---

## 3. CSV Validation Strategy
To satisfy **REQ-CSV-01**, your Playwright `playwright.config.ts` should include a global setup that injects the CSV flag:

```typescript
// Example Playwright Header Injection
test.use({
  extraHTTPHeaders: {
    'X-CSV-Validation': 'true', // Backend uses this to set is_csv_validation_record = True
  }
});
```


### Final Traceability Matrix (Summary)
| URS ID | Risk | Test Case ID | Status |
| :--- | :--- | :--- | :--- |
| REQ-PDF-03 | High | TC-DATA-01 | Playwright Automated |
| REQ-SIG-01 | High | TC-SIG-01 | Playwright Automated |
| REQ-TRN-02 | Med | TC-GATE-01 | Playwright Automated |
| REQ-AUD-01 | High | TC-AUDIT-01 | Playwright Automated |

How would you like to handle the "Reason for Change" prompts in the Playwright scripts—should they be randomized or pulled from a predefined list of GxP-compliant reasons?