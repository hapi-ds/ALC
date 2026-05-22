# Implementation Plan: Electronic Signatures UI

## Overview

Implement the Electronic Signatures system for AlcoaBase, covering both the frontend UI and the backend upgrade to real cryptographic PAdES signatures. The implementation provides full FDA/EMA compliance (21 CFR Part 11, EU Annex 11) with configurable signature modes: `pades` (production — pyHanko + x.509 certificates) or `hash` (development — SHA-256 hash-based, no certificates required).

Frontend work covers: TypeScript types, a Zustand signature store, pure utility functions, the multi-step SignatureDialog (re-auth → reason → sign → success), signature records display, status badges, verification UI, and a full Signatures Overview page. Backend work covers: strategy pattern refactor, pyHanko PAdES-B-LT integration, x.509 certificate loading, optional TSA timestamping, database migration for certificate fields, and a verification endpoint.

## Tasks

- [x] 1. Define TypeScript types and pure utility functions
  - [x] 1.1 Create signature TypeScript types
    - Create `src/frontend/src/types/signature.ts` with interfaces: `SignatureReasonCategory`, `SignResponse`, `SignatureStamp`, `SignatureRecordResponse`, `SignatureDialogContext`, `ReAuthResponse`
    - Match backend Pydantic schemas from `src/backend/src/alcoabase/schemas/signature.py`
    - _Requirements: 9.1, 5.1, 6.2_

  - [x] 1.2 Create signature utility functions
    - Create `src/frontend/src/lib/signatureUtils.ts` with pure functions:
      - `isSignatureRequired(currentState, targetState, transitions[])` — checks if transition matches signature-required array
      - `shouldShowWarning(remainingSeconds)` — returns true if ≤ 30
      - `isValidSignatureNote(note)` — trimmed length ≥ 3 AND raw length ≤ 200
      - `formatSignatureReason(category, note)` — produces "{Category}: {trimmedNote}"
      - `isSignButtonEnabled(category, note)` — category is valid AND note passes validation
      - `extractErrorMessage(error)` — parses ApiError body for detail field
      - `sortSignatureRecords(records[], direction)` — sorts by signed_at
      - `formatBadgeCount(count)` — returns count as string or "99+"
      - `filterSignatureRecords(records[], filters)` — applies AND-combined filters
    - _Requirements: 1.1, 3.2, 3.3, 4.2, 4.4, 4.5, 4.6, 5.5, 6.3, 7.2, 8.3, 8.4, 9.9_

  - [x] 1.3 Write property tests for signature utility functions
    - Create `src/frontend/src/lib/__tests__/signatureUtils.property.test.ts`
    - **Property 1: Transition signature-required matching**
    - **Property 2: Token countdown warning threshold**
    - **Property 3: Signature note validation**
    - **Property 4: Reason string formatting**
    - **Property 5: Sign button enablement**
    - **Property 6: Error message extraction from ApiError**
    - **Property 7: Signature records sorting**
    - **Property 8: Badge count display**
    - **Property 9: Signature records filtering**
    - **Validates: Requirements 1.1, 3.2, 3.3, 4.2, 4.4, 4.5, 4.6, 5.5, 6.3, 7.2, 8.3, 8.4, 9.9, 10.1**

- [x] 2. Implement Signature Store
  - [x] 2.1 Create the signatureStore
    - Create `src/frontend/src/stores/signatureStore.ts` using Zustand `create`
    - Implement state shape: re-auth state, signing state, records map, token countdown, dialog state, retained password
    - Implement actions: `openSignatureDialog`, `closeSignatureDialog`, `reAuthenticate`, `signDocument`, `fetchSignatureRecords`, `startTokenCountdown`, `clearToken`, `reset`
    - Use `apiClient.post` for `/api/v1/auth/re-authenticate` and `/api/signatures/sign`
    - Use `apiClient.get` for `/api/signatures/records/{document_uuid}`
    - Use `extractErrorMessage` from signatureUtils for error handling
    - Include `X-Change-Reason: "Electronic signature: {transition}"` on sign requests via apiClient's changeReason option
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11_

  - [x] 2.2 Write unit tests for signatureStore
    - Create `src/frontend/src/stores/__tests__/signatureStore.test.ts`
    - Test state transitions for reAuthenticate (success/failure), signDocument (success/failure), fetchSignatureRecords, clearToken, reset, openSignatureDialog, closeSignatureDialog
    - Mock apiClient calls
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Signature Dialog components
  - [x] 4.1 Create ReAuthForm component
    - Create `src/frontend/src/components/signatures/ReAuthForm.tsx`
    - Password input (type="password", maxLength 128), "Verify Identity" button
    - Button disabled when password empty or isLocked
    - Submit on Enter key press
    - Loading state on button while isReAuthenticating
    - Error message display below input (401, 429 lockout with countdown, network, server errors)
    - Informational text about 21 CFR Part 11 compliance
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [x] 4.2 Create TokenCountdown component
    - Create `src/frontend/src/components/signatures/TokenCountdown.tsx`
    - Display remaining seconds in "{N}s" format
    - Warning indicator (color/icon change) when ≤ 30 seconds
    - Uses `shouldShowWarning` from signatureUtils
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 4.3 Create ReasonSelector component
    - Create `src/frontend/src/components/signatures/ReasonSelector.tsx`
    - Dropdown with placeholder "Select a reason..." and options: Author, Review, Approval
    - Signature note text input with character counter (current/200)
    - Validation message on blur when trimmed note < 3 chars
    - Prevent input beyond 200 characters
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.4 Create SignatureDialog component
    - Create `src/frontend/src/components/signatures/SignatureDialog.tsx`
    - Modal dialog controlled by signatureStore.isDialogOpen
    - Multi-step flow: re-auth → reason/sign → success
    - Display document title, current state, target state, transition name
    - Integrate ReAuthForm, TokenCountdown, ReasonSelector
    - "Sign Document" button enabled via `isSignButtonEnabled`
    - Format reason via `formatSignatureReason` before calling signDocument
    - Loading state "Applying PAdES signature..." during signing
    - Success confirmation with signer name, timestamp, reason, truncated hash
    - "Continue" button triggers transition via workflowExecutionStore with skipSignatureCheck=true
    - Handle token expiry: return to re-auth, preserve reason fields
    - Handle post-sign transition failure: show error with "Close" only
    - Cancel via button or Escape key closes dialog
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.4, 3.5, 3.6, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 10.2_

  - [x] 4.5 Write unit tests for SignatureDialog components
    - Create `src/frontend/src/components/signatures/__tests__/SignatureDialog.test.tsx`
    - Test step rendering (re-auth → reason → signing → success)
    - Test ReAuthForm: button disabled when empty, enabled when non-empty, error display
    - Test ReasonSelector: dropdown options, character counter, validation message
    - Test TokenCountdown: format display, warning state
    - Test cancel/escape closes dialog
    - _Requirements: 1.2, 1.3, 2.1, 2.2, 2.6, 3.1, 3.3, 4.1, 4.3, 4.4, 4.6_

- [x] 5. Integrate with Workflow Execution Store
  - [x] 5.1 Modify workflowExecutionStore to support signature interception
    - Add `skipSignatureCheck?: boolean` as fourth parameter to `executeTransition`
    - When `skipSignatureCheck` is false (default), check if transition matches `signatureRequiredTransitions` using `isSignatureRequired` from signatureUtils
    - If match found, call `signatureStore.openSignatureDialog(context)` instead of calling transition API
    - When `skipSignatureCheck` is true, proceed directly to transition API call
    - Handle case where gate info is not loaded: block transition, show error
    - _Requirements: 10.1, 10.2, 10.3, 1.1, 1.6_

  - [x] 5.2 Add signature icon indicators to workflow transition buttons
    - Modify workflow execution UI components to show a pen-tool icon next to transition buttons whose target state matches a `signatureRequiredTransitions` entry
    - Hide indicators while `isLoadingGateInfo` is true
    - _Requirements: 10.4_

  - [x] 5.3 Write unit tests for workflowExecutionStore signature integration
    - Add tests to `src/frontend/src/stores/__tests__/workflowExecutionStore.test.ts`
    - Test: transition intercepted when signature required
    - Test: transition proceeds when skipSignatureCheck=true
    - Test: transition blocked when gate info unavailable
    - _Requirements: 10.1, 10.2, 10.3, 1.6_

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement Signature Records Panel and Status Badge
  - [x] 7.1 Create SignatureRecordsPanel component
    - Create `src/frontend/src/components/signatures/SignatureRecordsPanel.tsx`
    - Collapsible section "Electronic Signatures ({count})"
    - Default expanded when count > 0, collapsed when count = 0
    - Display each record: resolved username (fallback "User #{id}"), transition, reason, locale-formatted timestamp, truncated hash with copy button
    - Sort records descending by signed_at using `sortSignatureRecords`
    - Empty state: "No electronic signatures have been applied to this document."
    - Loading state: skeleton placeholders
    - Error state with "Retry" button
    - Auto-refresh after successful signing on same page
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

  - [x] 7.2 Create SignatureStatusBadge component
    - Create `src/frontend/src/components/signatures/SignatureStatusBadge.tsx`
    - Pen-tool icon with count using `formatBadgeCount`
    - `aria-label` for screen reader accessibility (e.g., "2 signatures applied")
    - Tooltip on hover/focus: most recent signer name, transition, locale-formatted timestamp
    - Not rendered when count is 0
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 7.3 Integrate SignatureRecordsPanel into document detail page
    - Add SignatureRecordsPanel to the document detail page, passing documentUuid
    - Display regardless of workflow state
    - _Requirements: 6.1, 6.7_

  - [x] 7.4 Integrate SignatureStatusBadge into document list component
    - Add SignatureStatusBadge to each document list item with signature count > 0
    - Derive data from signature records fetched alongside document metadata
    - _Requirements: 7.1, 7.3, 7.5, 7.6_

  - [x] 7.5 Write unit tests for SignatureRecordsPanel and SignatureStatusBadge
    - Create `src/frontend/src/components/signatures/__tests__/SignatureRecordsPanel.test.tsx`
    - Create `src/frontend/src/components/signatures/__tests__/SignatureStatusBadge.test.tsx`
    - Test: records render correctly, empty state, loading skeletons, error with retry
    - Test: badge count, tooltip, aria-label, hidden when count=0
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4_

- [x] 8. Implement Signatures Overview Page
  - [x] 8.1 Replace SignaturesPage placeholder with full implementation
    - Replace `src/frontend/src/pages/SignaturesPage.tsx` with paginated, filterable, sortable signature records list
    - Pagination: 25 records per page, Previous/Next controls, page number and total count display
    - Each record: document UUID (clickable link to detail), signer user ID, transition, reason, locale-formatted timestamp, truncated hash with copy button
    - Filters: document UUID text input (300ms debounce), transition dropdown, date range pickers
    - AND logic for filters, reset to page 1 on filter change
    - Sort by signed_at descending by default; clickable column headers for signed_at, signer_user_id, document_uuid with arrow indicators
    - Loading state: skeleton placeholders
    - Error state with retry button
    - Empty state: "No electronic signatures found. Signatures are created when workflow transitions require signing."
    - Use `filterSignatureRecords` and `sortSignatureRecords` from signatureUtils
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 8.2 Write unit tests for SignaturesPage
    - Create `src/frontend/src/pages/__tests__/SignaturesPage.test.tsx`
    - Test: pagination controls, filter inputs, sort indicators, empty state, loading state, error with retry
    - _Requirements: 8.1, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 9. Backend: Upgrade Signature Service to Real Cryptographic PAdES
  - [x] 9.1 Add signature configuration to Settings and .env
    - Add to `src/backend/src/alcoabase/config.py`: `signature_mode` (Literal["pades", "hash"], default "hash"), `signature_key_path` (str | None), `signature_cert_path` (str | None), `signature_key_password` (str | None), `signature_tsa_url` (str | None)
    - Add to `.env.example`: SIGNATURE_MODE, SIGNATURE_KEY_PATH, SIGNATURE_CERT_PATH, SIGNATURE_KEY_PASSWORD, SIGNATURE_TSA_URL with documentation comments
    - _Requirements: 11.1, 11.3, 11.10_

  - [x] 9.2 Create signing strategy abstraction
    - Create `src/backend/src/alcoabase/services/signing_strategies.py`
    - Define `SigningStrategy` protocol/ABC with methods: `sign_pdf(pdf_bytes, stamp) -> tuple[bytes, str]`, `verify_pdf(pdf_bytes) -> VerificationResult`, `get_certificate_info() -> CertificateInfo | None`
    - Implement `HashSigningStrategy` — move existing `_apply_signature` and `verify_signatures` logic here
    - Implement `PAdESSigningStrategy` — use pyHanko for real PAdES-B-LT signing with x.509 certificates
    - Create factory function `create_signing_strategy(settings) -> SigningStrategy` that returns the correct strategy based on `SIGNATURE_MODE`
    - _Requirements: 11.1, 11.2, 11.7_

  - [x] 9.3 Implement PAdES signing with pyHanko
    - Add `pyhanko` and `pyhanko-certvalidator` to backend dependencies
    - In `PAdESSigningStrategy.sign_pdf()`:
      - Load private key from `SIGNATURE_KEY_PATH` (support RSA ≥ 2048-bit and ECDSA P-256/P-384)
      - Load certificate chain from `SIGNATURE_CERT_PATH`
      - Use `pyhanko.sign.signers.PdfSigner` with `IncrementalPdfFileWriter`
      - Apply PAdES-B-LT signature profile
      - Embed visible signature annotation (bottom-right of last page): signer name, timestamp, reason, transition, certificate subject DN
      - Optionally embed RFC 3161 timestamp from `SIGNATURE_TSA_URL` if configured
    - In `PAdESSigningStrategy.verify_pdf()`:
      - Use pyHanko's validation to verify all embedded signatures
      - Check certificate chain trust
      - Verify timestamps if present
      - Return `VerificationResult` with per-signature validity
    - _Requirements: 11.2, 11.4, 11.5_

  - [x] 9.4 Add startup validation for PAdES mode
    - On application startup, if `SIGNATURE_MODE=pades`:
      - Validate `SIGNATURE_KEY_PATH` and `SIGNATURE_CERT_PATH` are set and files exist
      - Attempt to load the private key (with password if `SIGNATURE_KEY_PASSWORD` set)
      - Verify the certificate matches the private key (public key comparison)
      - If any check fails, raise a clear error and prevent startup
    - If `SIGNATURE_MODE` is unrecognized, default to "hash" and log a warning
    - _Requirements: 11.1, 11.3, 11.11_

  - [x] 9.5 Database migration: add certificate columns to signature_records
    - Create Alembic migration adding nullable columns to `signature_records`:
      - `certificate_subject` VARCHAR(500) NULL
      - `certificate_issuer` VARCHAR(500) NULL
      - `certificate_serial` VARCHAR(128) NULL
      - `signature_mode` VARCHAR(10) NOT NULL DEFAULT 'hash'
    - _Requirements: 11.8_

  - [x] 9.6 Update SignatureService to use strategy pattern
    - Refactor `SignatureService` to accept a `SigningStrategy` (injected via dependency)
    - Replace direct `_apply_signature` calls with `strategy.sign_pdf()`
    - Store `certificate_subject`, `certificate_issuer`, `certificate_serial`, `signature_mode` in the `SignatureRecord` on each sign operation
    - Update `SignResponse` schema to include optional `certificate_subject`, `certificate_issuer`, `certificate_serial` fields
    - _Requirements: 11.2, 11.6, 11.8_

  - [x] 9.7 Implement signature verification endpoint
    - Add `GET /api/signatures/verify/{document_uuid}` to the signatures router
    - Download the signed PDF from storage, call `strategy.verify_pdf()`
    - Return `VerifyResponse` with `is_valid`, `signature_count`, `signatures[]` (each with signer_name, signed_at, reason, is_valid, certificate_subject, certificate_issuer), `tampered_from_index`
    - _Requirements: 11.9, 12.2_

  - [x] 9.8 Write property tests for signing strategies
    - Create `src/backend/tests/properties/test_signature_strategies.py`
    - **Property 10: Signing strategy selection** — factory returns correct strategy based on mode
    - **Property 11: PAdES signature round-trip integrity** — sign then verify returns valid; tamper then verify returns invalid
    - **Property 12: Configuration validation** — missing key/cert raises error in pades mode
    - Test HashSigningStrategy backward compatibility with existing tests
    - _Requirements: 11.1, 11.2, 11.3, 11.7, 11.9, 11.11_

- [x] 10. Frontend: Signature Verification UI and Certificate Display
  - [x] 10.1 Add verification action to signatureStore
    - Add `verifySignatures(document_uuid)` action to signatureStore
    - State: `isVerifying`, `verifyError`, `verifyResult: VerifyResponse | null`
    - Calls `GET /api/signatures/verify/{document_uuid}`
    - _Requirements: 12.2, 12.5, 12.6_

  - [x] 10.2 Update SignatureRecordsPanel with verification UI and certificate display
    - Add "Verify Signatures" button (visible when records exist)
    - Display verification result: green "All signatures valid" banner or red "Document integrity compromised" banner
    - Highlight failed signature records based on `tampered_from_index`
    - Display `certificate_subject` below signature hash when present (pades-mode records)
    - Loading state on verify button while request in progress
    - Error state with retry for verification failures
    - _Requirements: 11.12, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_

  - [x] 10.3 Write unit tests for verification UI
    - Test: verify button visible when records exist, hidden when empty
    - Test: success banner renders on valid verification
    - Test: error banner renders on invalid verification with highlighted records
    - Test: certificate_subject displayed for pades-mode records
    - _Requirements: 12.1, 12.3, 12.4, 11.12_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design uses TypeScript throughout — all frontend implementations use React + TypeScript + Zustand + Tailwind CSS
- The backend uses Python + FastAPI + SQLAlchemy + pyHanko
- The `SIGNATURE_MODE` env var allows development without certificates (hash mode) while production uses real PAdES crypto
- The `apiClient` handles auth headers, token refresh, and `X-Change-Reason` automatically via its options parameter

