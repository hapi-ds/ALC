# Requirements Document

## Introduction

This feature implements the Electronic Signatures system for AlcoaBase, providing both a frontend UI and a backend upgrade to real cryptographic PAdES signatures using pyHanko with x.509 certificates. The system is fully FDA/EMA compliant (21 CFR Part 11, EU Annex 11, eIDAS) and supports configurable signature modes via environment variable (`SIGNATURE_MODE`): `pades` for production cryptographic signatures or `hash` for development/testing with the existing SHA-256 hash-based approach.

The frontend UI integrates with the backend signature service endpoints (`POST /api/signatures/sign`, `GET /api/signatures/records/{document_uuid}`) and the re-authentication endpoint (`POST /api/v1/auth/re-authenticate`). The feature replaces the current placeholder `SignaturesPage.tsx` with a fully functional electronic signatures experience. It intercepts workflow transitions that require signatures (as defined in `signature_required_transitions` on workflow definitions), presents a re-authentication dialog with mandatory "Reason for Signature" fields compliant with 21 CFR Part 11 (Author, Review, Approval categories), and displays signature records and visual stamp information on document detail pages. The feature integrates with Phase 3.2 (Workflow Execution & State Transitions) by intercepting transitions flagged with `requires_signature: true` in the transition response, and with Phase 2.5 (Report Data Entry & PDF Extraction) where the backend applies the visual signature overlay to the PDF.

The backend upgrade replaces the simplified hash-based signing with real asymmetric cryptography (RSA/ECDSA private keys, x.509 certificates, pyHanko PAdES-B-LT signatures) while maintaining backward compatibility through the configurable mode switch.

## Glossary

- **Signature_Dialog**: The modal dialog component presented when a workflow transition requires an electronic signature, containing re-authentication fields, reason selection, and signing controls.
- **Re_Auth_Form**: The form section within the Signature_Dialog that collects the user's password for identity verification before signing.
- **Reason_Selector**: The form control within the Signature_Dialog that allows the user to select a 21 CFR Part 11 compliant signature reason category (Author, Review, Approval) and provide an optional descriptive note.
- **Signature_Token**: A short-lived JWT token (120 seconds expiry) issued by `POST /api/v1/auth/re-authenticate` upon successful password verification, authorizing the subsequent signing operation.
- **Signature_Records_Panel**: A component displayed on the document detail page showing all signature records for a document, including signer name, transition, reason, timestamp, and signature hash.
- **Signature_Status_Badge**: A visual indicator displayed on document list items and document detail pages showing whether a document has been signed and the count of signatures.
- **Signature_Store**: The Zustand state store managing re-authentication state, signing operations, signature records, and token lifecycle for the electronic signatures feature.
- **Signature_Stamp**: The visual overlay data embedded in the signed PDF by the backend, containing signer name, timestamp, reason, and transition information.
- **Signatures_Page**: The main React page component at route `/signatures` displaying a searchable list of all signature records across documents accessible to the current user.
- **Sign_Request_API**: The backend endpoint at `POST /api/signatures/sign` that performs credential verification, PAdES signing with visual stamp, and audit trail recording.
- **Signature_Records_API**: The backend endpoint at `GET /api/signatures/records/{document_uuid}` returning all signature records for a specific document.
- **Re_Auth_API**: The backend endpoint at `POST /api/v1/auth/re-authenticate` that verifies the user's password and issues a short-lived signature token (120 seconds).
- **Signature_Required_Transitions**: The array of workflow transition names (e.g., "Review→Approved") defined on a workflow definition that require an electronic signature before execution.
- **Token_Countdown**: A visual timer displayed in the Signature_Dialog showing the remaining validity of the signature token (counting down from 120 seconds).
- **API_Client**: The fetch wrapper at `src/frontend/src/lib/apiClient.ts` handling authentication, token refresh, tenant headers, and the X-Change-Reason audit header.
- **Change_Reason**: A mandatory text value sent via the `X-Change-Reason` header on mutating requests for ALCOA+ audit compliance.
- **SIGNATURE_MODE**: Environment variable controlling the signing backend: `pades` (production, real cryptographic PAdES signatures with pyHanko + x.509) or `hash` (development/testing, SHA-256 hash-based tamper detection only).
- **PAdES_B_LT**: PDF Advanced Electronic Signatures Baseline Long-Term level, the target signature profile providing long-term validation with embedded timestamps and revocation data.
- **x509_Certificate**: A digital certificate binding a public key to an identity (signer), issued by a Certificate Authority (CA) or self-signed for internal use.
- **Signing_Key**: The RSA or ECDSA private key used to create cryptographic signatures, stored at the path specified by `SIGNATURE_KEY_PATH`.
- **Certificate_Chain**: The ordered list of certificates from the signer's certificate up to the root CA, embedded in the signed PDF for trust chain validation.
- **TSA**: Timestamp Authority — an external service providing RFC 3161 timestamps to prove when a signature was created, configured via `SIGNATURE_TSA_URL`.

## Requirements

### Requirement 1: Signature-Required Transition Interception

**User Story:** As a user executing a workflow transition, I want the system to intercept transitions that require a signature and present the signing dialog, so that I can provide my electronic signature before the document state changes.

#### Acceptance Criteria

1. WHEN the user initiates a workflow transition and the transition name is present in the `signatureRequiredTransitions` array from the workflowExecutionStore, THE Workflow_Execution_UI SHALL intercept the transition, prevent the standard transition execution, and open the Signature_Dialog pre-populated with the document UUID, document version ID, and transition name. THE Workflow_Execution_UI SHALL disable the transition button immediately upon click to prevent duplicate dialog invocations.
2. WHEN the Signature_Dialog is opened for a signature-required transition, THE Signature_Dialog SHALL display the document title, current workflow state, target state (extracted as the substring after the "→" separator in the transition name), and the transition name requiring the signature.
3. IF the user cancels the Signature_Dialog (via cancel button or Escape key), THEN THE Workflow_Execution_UI SHALL abort the transition, close the dialog, re-enable the transition button, and leave the document in its current workflow state without recording any signature event.
4. WHEN the signing operation completes successfully via the Signature_Dialog, THE Workflow_Execution_UI SHALL proceed with the workflow transition by calling the `executeTransition` action in the workflowExecutionStore with the original documentUuid, targetState, and changeReason parameters, then refresh the document state and transition history by invoking `fetchDocumentState` and `fetchTransitionHistory`.
5. IF the workflow transition execution fails after a successful signing operation, THEN THE Signature_Dialog SHALL display an error message indicating the transition failed despite the signature being recorded, and advise the user to contact an administrator. THE Signature_Dialog SHALL provide only a "Close" button (no retry) since the signature has already been recorded.
6. IF the `signatureRequiredTransitions` array has not been loaded (i.e., `fetchWorkflowGateInfo` has not completed or has failed) when the user initiates a workflow transition, THEN THE Workflow_Execution_UI SHALL block the transition execution, display an inline error message indicating that workflow gate information is unavailable, and provide a retry button that re-invokes `fetchWorkflowGateInfo` before allowing the transition to proceed.

### Requirement 2: Re-Authentication Flow

**User Story:** As a user signing a document, I want to verify my identity by entering my password, so that the system confirms I am the person authorizing the signature in compliance with 21 CFR Part 11.

#### Acceptance Criteria

1. WHEN the Signature_Dialog is opened, THE Re_Auth_Form SHALL display a password input field (type="password") with the label "Password" and a maximum input length of 128 characters, a "Verify Identity" button, and informational text explaining that re-authentication is required per 21 CFR Part 11 for electronic signature operations.
2. THE Re_Auth_Form SHALL require the password field to contain at least 1 character before enabling the "Verify Identity" button. THE Re_Auth_Form SHALL submit when the user presses the Enter key while the password input is focused and the button is enabled.
3. WHEN the user submits the Re_Auth_Form, THE Signature_Store SHALL send a POST request to `POST /api/v1/auth/re-authenticate` with the password in the request body, using the existing Bearer token for authentication.
4. WHILE the re-authentication request is in progress, THE Re_Auth_Form SHALL display a loading indicator on the "Verify Identity" button and disable the password input and button to prevent duplicate submissions.
5. WHEN the re-authentication succeeds (response `verified` is true), THE Signature_Store SHALL store the `signature_token` and `expires_in` value, start the Token_Countdown timer, and THE Signature_Dialog SHALL advance to the signing step (Reason_Selector and sign button become visible).
6. IF the re-authentication fails with a 401 error (invalid credentials), THEN THE Re_Auth_Form SHALL display the error message "Invalid password. Please try again." below the password input, clear the password field, re-enable the input and button, and keep focus on the password input.
7. IF the re-authentication request fails due to a network error (no response received), THEN THE Re_Auth_Form SHALL display the message "Network error: Unable to reach the server. Please check your connection." below the password input, retain the entered password, and re-enable the input and button.
8. IF the re-authentication request fails with a 429 error (too many attempts), THEN THE Re_Auth_Form SHALL display an error message indicating the account is temporarily locked due to too many failed attempts, disable the password input and "Verify Identity" button for 60 seconds, and display a countdown showing the remaining lockout duration before the user may retry.
9. IF the re-authentication request fails with a server error (HTTP 500, 502, or 503), THEN THE Re_Auth_Form SHALL display an error message indicating a server error occurred and to try again shortly, retain the entered password, and re-enable the input and button.

### Requirement 3: Signature Token Lifecycle Management

**User Story:** As a user who has re-authenticated, I want to see how much time remains on my signature token, so that I can complete the signing operation before the token expires.

#### Acceptance Criteria

1. WHEN a signature token is obtained, THE Token_Countdown SHALL display a countdown timer showing the remaining seconds until token expiry in the format "{N}s" (e.g., "120s", "45s"), starting from the `expires_in` value (120 seconds) and decrementing by 1 every second.
2. WHILE the signature token has more than 30 seconds remaining, THE Token_Countdown SHALL display the remaining time without any visual warning indicator, using the default text style of the dialog.
3. WHILE the signature token has 30 seconds or fewer remaining, THE Token_Countdown SHALL display the remaining time with a visually distinct warning indicator (differentiated from the neutral state by color or iconography) to alert the user that time is running low.
4. WHEN the signature token expires (countdown reaches 0), THE Signature_Store SHALL clear the stored signature token, THE Signature_Dialog SHALL disable the "Sign Document" button, display the message "Session expired. Please re-authenticate to continue.", and re-display the Re_Auth_Form so the user can re-authenticate.
5. IF the user successfully re-authenticates after a token expiry, THEN THE Signature_Dialog SHALL reset the Token_Countdown with the new `expires_in` value, re-display the Reason_Selector and "Sign Document" button in their enabled states, and preserve any previously entered reason category selection and signature note text so the user does not need to re-enter them.
6. WHEN the signing operation completes successfully while the Token_Countdown is active, THE Signature_Store SHALL stop the countdown timer and THE Token_Countdown SHALL no longer be displayed.

### Requirement 4: Signature Reason Selection (21 CFR Part 11 Compliance)

**User Story:** As a user signing a document, I want to select a reason category and provide a descriptive note for my signature, so that the signature record complies with 21 CFR Part 11 requirements for meaning attribution.

#### Acceptance Criteria

1. WHEN the user has successfully re-authenticated, THE Reason_Selector SHALL display a required dropdown with a placeholder option "Select a reason..." (non-selectable) and three 21 CFR Part 11 compliant reason categories: "Author" (meaning the signer authored the document content), "Review" (meaning the signer reviewed the document for accuracy), and "Approval" (meaning the signer approves the document for release or use).
2. WHEN the user has successfully re-authenticated, THE Reason_Selector SHALL display a required text input labeled "Signature Note" where the user provides a descriptive note (minimum 3 characters, maximum 200 characters after trimming leading and trailing whitespace) explaining the specific reason for signing (e.g., "Approved by QA Manager after final review").
3. THE Reason_Selector SHALL display a character counter for the signature note showing the current raw (untrimmed) character count out of 200, and SHALL prevent the user from entering more than 200 characters.
4. IF the signature note contains fewer than 3 non-whitespace characters after trimming, THEN THE Reason_Selector SHALL display a validation message "Signature note must contain at least 3 characters" below the text input when the input loses focus.
5. WHEN the user clicks the "Sign Document" button, THE Signature_Dialog SHALL combine the selected reason category and the trimmed signature note into the `reason` field for the sign request, formatted as "{Category}: {Note}" (e.g., "Approval: Approved by QA Manager after final review").
6. THE Signature_Dialog SHALL NOT enable the "Sign Document" button until both a reason category is selected (not the placeholder) and the signature note meets the minimum length requirement of 3 characters after trimming leading and trailing whitespace.

### Requirement 5: Document Signing Execution

**User Story:** As a user who has re-authenticated and provided a reason, I want to execute the PAdES signing operation, so that the document receives a legally binding electronic signature with a visual stamp.

#### Acceptance Criteria

1. WHEN the user clicks the "Sign Document" button, THE Signature_Store SHALL send a POST request to `POST /api/signatures/sign` with the request body containing: `document_uuid`, `document_version_id`, `transition` (the workflow transition name), `reason` (the combined category and note), and `password` (the user's password from the re-authentication step). THE request SHALL include the `X-Change-Reason` header with the value "Electronic signature: {transition}" via apiClient's changeReason option.
2. WHILE the signing request is in progress, THE Signature_Dialog SHALL display a loading indicator on the "Sign Document" button, disable all form inputs and buttons, and display a progress message "Applying PAdES signature...".
3. WHEN the signing request succeeds, THE Signature_Store SHALL store the response data (signature_hash, signature_record_id, stamp), THE Signature_Dialog SHALL display a success confirmation showing the signer name, signed timestamp formatted in the user's locale, reason, and signature hash (truncated to first 16 characters followed by "…"), and provide a "Continue" button that closes the dialog and triggers the workflow transition.
4. IF the signing request fails with a 401 error (re-authentication failure or token expired), THEN THE Signature_Dialog SHALL display the message "Authentication expired. Please re-authenticate.", clear the signature token, preserve the previously selected reason category and signature note, and return to the re-authentication step so the user can re-verify identity without re-entering the reason fields.
5. IF the signing request fails with a 400 error (document not found, version not found, or other validation error), THEN THE Signature_Dialog SHALL display the error message extracted from the response body's `detail` field (falling back to "An unexpected error occurred. Please try again." if no `detail` field is present), re-enable the "Sign Document" button, and allow the user to retry or cancel.
6. IF the signing request fails due to a network error (no response received), THEN THE Signature_Dialog SHALL display the message "Network error: Unable to complete the signing operation. Please check your connection and try again.", re-enable the "Sign Document" button, and allow the user to retry.
7. IF the signing request fails with a server error (HTTP 500, 502, or 503), THEN THE Signature_Dialog SHALL display the message "Server error: The signing service is temporarily unavailable. Please try again shortly.", re-enable the "Sign Document" button, and allow the user to retry.

### Requirement 6: Signature Records Display on Document Detail Page

**User Story:** As a user viewing a document, I want to see all electronic signatures applied to the document, so that I can verify the document's signature history and compliance status.

#### Acceptance Criteria

1. WHEN the document detail page loads, THE Signature_Records_Panel SHALL fetch signature records from `GET /api/signatures/records/{document_uuid}` and display them in a collapsible section labeled "Electronic Signatures" with the count of signatures shown in the section header (e.g., "Electronic Signatures (3)"). The section SHALL default to expanded when the document has 1 or more signature records, and collapsed when the document has zero records.
2. THE Signature_Records_Panel SHALL display each signature record entry with: the signer user ID displayed as the resolved username (fetched from user data already available in the application context), falling back to "User #{signer_user_id}" if the username cannot be resolved; the workflow transition that triggered the signature; the signature reason; the signing timestamp formatted in the user's locale using the browser's `Intl.DateTimeFormat`; and the signature hash truncated to the first 16 characters followed by an ellipsis with a copy-to-clipboard button that copies the full 64-character SHA-256 hash.
3. THE Signature_Records_Panel SHALL sort signature records by `signed_at` in descending order (most recent signature first).
4. IF the document has no signature records, THEN THE Signature_Records_Panel SHALL display an empty state message: "No electronic signatures have been applied to this document."
5. WHILE the signature records are loading, THE Signature_Records_Panel SHALL display skeleton placeholders matching the layout of the records list (one placeholder per expected row, minimum 1 placeholder shown).
6. IF the signature records request fails with an HTTP status code of 4xx or 5xx or due to a network error (no response received), THEN THE Signature_Records_Panel SHALL display an error message indicating that signature records could not be loaded, along with a "Retry" button that re-invokes the fetch when clicked.
7. THE Signature_Records_Panel SHALL be displayed on the document detail page regardless of the document's workflow state, showing historical signatures even for documents that have progressed past signature-required transitions.
8. WHEN a signing operation completes successfully via the Signature_Dialog on the same document detail page, THE Signature_Records_Panel SHALL automatically re-fetch and re-render the signature records list to include the newly created record without requiring a full page reload.

### Requirement 7: Signature Status Badge on Document List

**User Story:** As a user browsing documents, I want to see at a glance which documents have been signed, so that I can quickly identify documents with electronic signatures applied.

#### Acceptance Criteria

1. WHEN the documents list page loads, THE Document_List component SHALL display a Signature_Status_Badge on each document list item that has one or more signature records. THE Signature_Status_Badge SHALL include an `aria-label` attribute describing the signature count (e.g., "2 signatures applied") to support screen reader accessibility.
2. THE Signature_Status_Badge SHALL display a pen-tool icon with the count of signatures. IF the signature count exceeds 99, THEN THE badge SHALL display "99+" as the count value.
3. IF a document has zero signature records, THEN THE Document_List component SHALL NOT display a Signature_Status_Badge for that document.
4. WHEN the user hovers over or focuses on a Signature_Status_Badge, THE badge SHALL display a tooltip showing the most recent signer's display name (or user ID if the display name is unavailable), the workflow transition name, and the signing timestamp formatted in the user's locale (date and time).
5. THE Signature_Status_Badge data SHALL be derived from the signature records fetched alongside document metadata, without requiring a separate API call per document.
6. THE Signature_Store SHALL provide a method to retrieve signature record counts and most-recent-signer metadata for documents returned in the current document list response, caching results keyed by document UUID until the document list is re-fetched or a new signature is recorded via the Signature_Store's signDocument action.

### Requirement 8: Signatures Overview Page

**User Story:** As a user, I want a dedicated page listing all signature records across documents, so that I can review my signing history and audit signature activity.

#### Acceptance Criteria

1. WHEN the user navigates to the `/signatures` route, THE Signatures_Page SHALL fetch signature records accessible to the current user from the Signature_Store and display them as a paginated list with a maximum of 25 records per page, providing "Previous" and "Next" navigation controls and a display of the current page number and total record count.
2. THE Signatures_Page SHALL display each signature record with: document UUID (as a clickable link navigating to the document detail page), signer user ID, workflow transition, reason, signing timestamp formatted in the user's locale, and signature hash (truncated to first 16 characters with ellipsis and a copy-to-clipboard button for the full hash).
3. THE Signatures_Page SHALL provide filter controls for: document UUID (text input performing substring match after the user stops typing for 300 milliseconds), transition name (dropdown populated from the distinct transition values present in the fetched records), and date range (start date and end date pickers). All active filters SHALL be combined with AND logic, and THE Signatures_Page SHALL reset to page 1 when any filter value changes.
4. THE Signatures_Page SHALL sort records by `signed_at` in descending order (most recent first) by default. THE column headers for signed_at, signer user ID, and document UUID SHALL be clickable to toggle sort direction between ascending and descending, with a visual arrow indicator showing the current sort column and direction.
5. WHILE the signature records are loading, THE Signatures_Page SHALL display skeleton placeholders matching the layout of the records list.
6. IF the signature records request fails due to a network or server error, THEN THE Signatures_Page SHALL display an error message with a retry button that re-invokes the fetch when clicked.
7. IF no signature records match the current filters (or no records exist at all), THEN THE Signatures_Page SHALL display an empty state message: "No electronic signatures found. Signatures are created when workflow transitions require signing."

### Requirement 9: Signature Store (Zustand State Management)

**User Story:** As a developer, I want a centralized state store for signature operations, so that re-authentication, signing, token lifecycle, and signature records flow consistently across components.

#### Acceptance Criteria

1. THE Signature_Store SHALL maintain state for: re-authentication (isReAuthenticating, reAuthError, signatureToken, tokenExpiresAt), signing (isSigning, signError, lastSignResult), signature records (records mapping document_uuid to SignatureRecordResponse array, isLoadingRecords, recordsError), token countdown (remainingSeconds), and dialog state (isDialogOpen, dialogContext containing document_uuid, document_version_id, transition, documentTitle).
2. THE Signature_Store SHALL expose actions for: openSignatureDialog(context), closeSignatureDialog(), reAuthenticate(password), signDocument(document_uuid, document_version_id, transition, reason, password), fetchSignatureRecords(document_uuid), startTokenCountdown(), clearToken(), and reset().
3. WHEN reAuthenticate is called, THE Signature_Store SHALL set isReAuthenticating to true, clear reAuthError, send a POST request to `/api/v1/auth/re-authenticate` with the password in the request body, store the signatureToken and compute tokenExpiresAt (current time plus expires_in seconds) on success, start the token countdown, and set isReAuthenticating to false. IF the request fails, THEN THE store SHALL set reAuthError to the extracted error message and set isReAuthenticating to false.
4. WHEN signDocument is called, THE Signature_Store SHALL set isSigning to true, clear signError, send a POST request to `/api/signatures/sign` with the document_uuid, document_version_id, transition, reason, and password in the request body and "Electronic signature: {transition}" as the X-Change-Reason header, store the response in lastSignResult on success, and set isSigning to false. IF the request fails, THEN THE store SHALL set signError to the extracted error message and set isSigning to false.
5. WHEN fetchSignatureRecords is called, THE Signature_Store SHALL set isLoadingRecords to true, clear recordsError, send a GET request to `/api/signatures/records/{document_uuid}`, store the response array in the records map keyed by document_uuid on success, and set isLoadingRecords to false. IF the request fails, THEN THE store SHALL set recordsError to the extracted error message and set isLoadingRecords to false.
6. WHEN startTokenCountdown is called, THE Signature_Store SHALL clear any previously active countdown interval before starting a new one, compute remainingSeconds from the difference between tokenExpiresAt and the current time (rounded down to whole seconds), then decrement remainingSeconds by 1 every 1000 milliseconds using a setInterval. WHEN remainingSeconds reaches 0, THE store SHALL clear the interval, set signatureToken to null, and set tokenExpiresAt to null.
7. WHEN clearToken is called, THE Signature_Store SHALL set signatureToken to null, tokenExpiresAt to null, remainingSeconds to 0, and clear any active countdown interval.
8. WHEN reset is called, THE Signature_Store SHALL clear all state to initial values: isReAuthenticating false, reAuthError null, signatureToken null, tokenExpiresAt null, isSigning false, signError null, lastSignResult null, records empty map, isLoadingRecords false, recordsError null, remainingSeconds 0, isDialogOpen false, dialogContext null, and clear any active countdown interval.
9. IF any API request initiated by the Signature_Store fails with an ApiError, THEN THE Signature_Store SHALL extract the error message by parsing the ApiError `body` property as JSON and reading the `detail` field; IF parsing fails or `detail` is absent, THEN THE store SHALL fall back to the ApiError `message` property. THE store SHALL store the extracted string in the corresponding error state property (reAuthError, signError, or recordsError) and set the corresponding loading flag to false.
10. WHEN closeSignatureDialog is called, THE Signature_Store SHALL set isDialogOpen to false and dialogContext to null, clear signError and lastSignResult, and invoke clearToken to reset the token and countdown state.
11. WHEN openSignatureDialog is called while isDialogOpen is already true, THE Signature_Store SHALL first invoke closeSignatureDialog to reset prior state, then set isDialogOpen to true and dialogContext to the provided context.

### Requirement 10: Integration with Workflow Execution Store

**User Story:** As a developer, I want the signature flow to integrate seamlessly with the existing workflow execution store, so that signature-required transitions are handled without duplicating workflow logic.

#### Acceptance Criteria

1. WHEN the user initiates a workflow transition via the workflowExecutionStore's `executeTransition` action, THE action SHALL check whether the `targetState` matches any transition in the `signatureRequiredTransitions` array (by comparing `targetState` against the target portion of each transition name, e.g., "Approved" matches "Review→Approved" given the current state is "Review"). IF the transition requires a signature, THEN THE action SHALL NOT call the transition API directly but instead open the Signature_Dialog via the Signature_Store's `openSignatureDialog` action with the context containing `document_uuid`, `document_version_id` (from the current document state), `transition` (the matched transition name), and `documentTitle`.
2. WHEN the Signature_Dialog completes a successful signing operation and the user clicks "Continue", THE Signature_Store SHALL invoke the workflowExecutionStore's `executeTransition` action with the original parameters (documentUuid, targetState, changeReason) and a `skipSignatureCheck` flag set to true, so that the action bypasses the signature-required check and proceeds directly to calling the transition API.
3. THE workflowExecutionStore's `executeTransition` action SHALL accept an optional fourth parameter `skipSignatureCheck` (boolean, default false). IF `skipSignatureCheck` is true, THEN THE action SHALL proceed directly to calling the transition API without checking the `signatureRequiredTransitions` array, preventing infinite recursion after signing completion.
4. WHEN the workflowExecutionStore's `fetchWorkflowGateInfo` action loads `signature_required_transitions` for a workflow, THE Workflow_Execution_UI SHALL display a signature icon indicator next to each transition button whose target state matches an entry in the `signatureRequiredTransitions` array, providing a visual cue before the user initiates the transition. WHILE `isLoadingGateInfo` is true, THE Workflow_Execution_UI SHALL render transition buttons without signature indicators.
5. IF the workflow transition API returns `requires_signature: true` in the transition response and the Signature_Dialog was not shown prior to the API call (i.e., the transition was not in the locally loaded `signatureRequiredTransitions` array), THEN THE Workflow_Execution_UI SHALL open the Signature_Dialog for the completed transition so that a signature record is captured retroactively, and SHALL display an informational message indicating that the transition has been applied and a signature is now required for compliance.

### Requirement 11: Backend Cryptographic PAdES Signature Service (pyHanko + x.509)

**User Story:** As a system administrator, I want the signature service to use real asymmetric cryptographic signatures with x.509 certificates for FDA/EMA compliance, with the ability to fall back to hash-based signing for development environments, so that production signatures are legally binding and tamper-proof while development remains lightweight.

#### Acceptance Criteria

1. THE backend SHALL support a `SIGNATURE_MODE` environment variable with two valid values: `pades` (default for production — real cryptographic PAdES signatures using pyHanko with x.509 certificates) and `hash` (development/testing — existing SHA-256 hash-based approach). IF `SIGNATURE_MODE` is not set or is set to an unrecognized value, THEN THE backend SHALL default to `hash` mode and log a warning at startup.
2. WHEN `SIGNATURE_MODE` is `pades`, THE signature service SHALL use pyHanko to apply a PAdES-B-LT (Baseline Long-Term) compliant signature to the PDF, using the private key at the path specified by `SIGNATURE_KEY_PATH` and the certificate chain at `SIGNATURE_CERT_PATH`. THE signed PDF SHALL be a valid PDF 2.0 document whose signature is verifiable by standard PDF readers (Adobe Acrobat, Foxit).
3. WHEN `SIGNATURE_MODE` is `pades`, THE backend SHALL require the following environment variables to be set: `SIGNATURE_KEY_PATH` (path to PEM-encoded private key file, RSA ≥ 2048-bit or ECDSA P-256/P-384), `SIGNATURE_CERT_PATH` (path to PEM-encoded certificate chain file containing the signer certificate and any intermediate CA certificates), and optionally `SIGNATURE_KEY_PASSWORD` (passphrase for encrypted private keys, empty string or absent for unencrypted keys). IF any required variable is missing when `SIGNATURE_MODE` is `pades`, THEN THE backend SHALL fail to start with a clear error message indicating which configuration is missing.
4. WHEN `SIGNATURE_MODE` is `pades`, THE signature service SHALL optionally embed an RFC 3161 timestamp from a Timestamp Authority (TSA) if `SIGNATURE_TSA_URL` is configured. IF `SIGNATURE_TSA_URL` is set, THEN THE signed PDF SHALL include an embedded timestamp proving the signing time. IF `SIGNATURE_TSA_URL` is not set, THEN THE signature SHALL use the server's local UTC time without an external timestamp.
5. WHEN `SIGNATURE_MODE` is `pades`, THE signature service SHALL embed a visible signature annotation on the last page of the PDF displaying: signer full name, signing timestamp (UTC), reason for signature, workflow transition, and the certificate subject DN (Distinguished Name). THE annotation SHALL be positioned in the bottom-right quadrant of the page and SHALL NOT overlap existing page content.
6. WHEN `SIGNATURE_MODE` is `pades`, THE `POST /api/signatures/sign` response SHALL include additional fields: `certificate_subject` (the signer certificate's subject DN as a string), `certificate_issuer` (the issuing CA's subject DN), and `certificate_serial` (the certificate serial number as hex string). THE existing response fields (success, signature_hash, signature_record_id, stamp) SHALL remain unchanged.
7. WHEN `SIGNATURE_MODE` is `hash`, THE signature service SHALL behave exactly as the current implementation (SHA-256 hash-based signing with custom binary block appended to PDF). No x.509 certificates or pyHanko are required.
8. THE `signature_records` database table SHALL be extended with nullable columns: `certificate_subject` (VARCHAR 500), `certificate_issuer` (VARCHAR 500), `certificate_serial` (VARCHAR 128), and `signature_mode` (VARCHAR 10, values 'pades' or 'hash'). Existing records SHALL have `signature_mode` set to 'hash' via migration default.
9. THE backend SHALL expose a new endpoint `GET /api/signatures/verify/{document_uuid}` that downloads the signed PDF from storage and verifies all embedded signatures. WHEN `SIGNATURE_MODE` is `pades`, THE verification SHALL validate the cryptographic signature against the embedded certificate, check the certificate chain trust, and verify the timestamp if present. THE response SHALL include: `is_valid` (boolean), `signature_count` (integer), `signatures` (array of objects with signer_name, signed_at, reason, is_valid, certificate_subject, certificate_issuer), and `tampered_from_index` (integer, -1 if all valid).
10. THE backend Settings class in `config.py` SHALL include the new fields: `signature_mode` (Literal["pades", "hash"], default "hash", alias "SIGNATURE_MODE"), `signature_key_path` (str | None, default None, alias "SIGNATURE_KEY_PATH"), `signature_cert_path` (str | None, default None, alias "SIGNATURE_CERT_PATH"), `signature_key_password` (str | None, default None, alias "SIGNATURE_KEY_PASSWORD"), and `signature_tsa_url` (str | None, default None, alias "SIGNATURE_TSA_URL").
11. WHEN the backend starts with `SIGNATURE_MODE=pades`, THE application startup SHALL validate that the key file and certificate file exist and are readable, that the private key can be loaded (with password if provided), and that the certificate matches the private key. IF validation fails, THEN THE backend SHALL fail to start with a descriptive error message.
12. THE frontend Signature_Records_Panel and Signatures_Page SHALL display the `certificate_subject` field (when present) alongside each signature record, showing it as "Certificate: {subject}" below the signature hash. IF `certificate_subject` is null (hash-mode signatures), THEN THE field SHALL NOT be displayed.

### Requirement 12: Signature Verification UI

**User Story:** As a user, I want to verify the cryptographic integrity of signatures on a document, so that I can confirm the document has not been tampered with since signing.

#### Acceptance Criteria

1. THE Signature_Records_Panel SHALL display a "Verify Signatures" button when the document has one or more signature records.
2. WHEN the user clicks "Verify Signatures", THE Signature_Store SHALL send a GET request to `GET /api/signatures/verify/{document_uuid}` and display the verification results inline within the Signature_Records_Panel.
3. WHEN verification succeeds with `is_valid` true, THE Signature_Records_Panel SHALL display a green "All signatures valid" banner with a checkmark icon.
4. WHEN verification returns `is_valid` false, THE Signature_Records_Panel SHALL display a red "Document integrity compromised" banner with a warning icon, and SHALL highlight the specific signature record(s) that failed verification (identified by `tampered_from_index`).
5. WHILE the verification request is in progress, THE "Verify Signatures" button SHALL display a loading indicator and be disabled.
6. IF the verification request fails due to a network or server error, THEN THE Signature_Records_Panel SHALL display an error message with a retry button.
