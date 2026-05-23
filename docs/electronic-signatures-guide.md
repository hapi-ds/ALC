# Electronic Signatures User Guide

This guide explains how to use the electronic signature features in AlcoaBase. It covers signing documents during workflow transitions, viewing signature records, verifying signature integrity, and configuring the signature backend for production use.

## Overview

AlcoaBase implements electronic signatures compliant with **21 CFR Part 11** (FDA), **EU Annex 11**, and **eIDAS** regulations. The system supports two signing modes:

- **Hash mode** (default) — SHA-256 hash-based signing for development and testing. No certificates required.
- **PAdES mode** — Real cryptographic signatures using pyHanko with x.509 certificates. Produces PDF signatures verifiable by Adobe Acrobat and other standard PDF readers.

Electronic signatures are triggered automatically when a workflow transition requires one (configured by admins in the BPMN Workflow Editor). The signing flow enforces re-authentication before every signature, ensuring non-repudiation.

## Signing a Document

When you trigger a workflow transition that requires a signature, the system intercepts the transition and presents the **Signature Dialog**. You'll recognize signature-required transitions by the lock icon next to the transition button.

### Step 1: Re-Authentication

The dialog first asks you to verify your identity by entering your password. This is required per 21 CFR Part 11 — every signature must be preceded by identity verification.

- Enter your password and click **"Verify Identity"**
- A 120-second countdown timer starts after successful verification
- If the timer expires, you'll need to re-authenticate (your reason selection is preserved)

### Step 2: Select Reason and Provide Note

After re-authentication, you must provide:

1. **Reason category** — select one of three 21 CFR Part 11 compliant categories:
   - **Author** — you authored the document content
   - **Review** — you reviewed the document for accuracy
   - **Approval** — you approve the document for release or use

2. **Signature note** — a descriptive explanation (3-200 characters) of why you're signing. For example: "Approved by QA Manager after final review"

### Step 3: Sign the Document

Click **"Sign Document"** to apply the PAdES signature. The system will:

1. Apply a cryptographic signature to the PDF
2. Embed a visible signature annotation (signer name, timestamp, reason, certificate info)
3. Record the signature event in the audit trail
4. Display a success confirmation with the signature hash

### Step 4: Continue

Click **"Continue"** to complete the workflow transition. The document advances to the next state.

## Viewing Signature Records

### On the Document Detail Page

Every document detail page shows an **"Electronic Signatures"** section listing all signatures applied to that document. Each record shows:

- Signer name (or user ID)
- Workflow transition that triggered the signature
- Reason for signing
- Timestamp (in your locale)
- Signature hash (truncated, with copy-to-clipboard button)
- Certificate subject (for PAdES-mode signatures)

The section auto-expands when signatures exist and collapses when empty.

### On the Document List

Documents with signatures display a small pen icon badge with the signature count. Hover over the badge to see the most recent signer and transition.

### Signatures Overview Page

Navigate to the Signatures page for a dedicated view listing all signature records across documents. Features include:

- **Pagination** — 25 records per page
- **Filtering** — by document UUID, transition name, and date range
- **Sorting** — click column headers to sort by date, signer, or document
- **Document links** — click any document UUID to navigate to its detail page

## Verifying Signature Integrity

To verify that a document has not been tampered with since signing:

1. Open the document detail page
2. In the "Electronic Signatures" section, click the **"Verify"** button
3. The system downloads the signed PDF and verifies all embedded signatures

Results:

- **Green banner: "All signatures valid"** — the document is intact
- **Red banner: "Document integrity compromised"** — one or more signatures are invalid. Tampered records are highlighted with a red border and "Invalid" badge.

## Configuration

### Development Mode (Default)

No configuration needed. The system uses SHA-256 hash-based signing:

```env
SIGNATURE_MODE=hash
```

### Production Mode (PAdES with x.509 Certificates)

For FDA/EMA compliance, configure real cryptographic signatures:

```env
SIGNATURE_MODE=pades
SIGNATURE_KEY_PATH=/certs/signing-key.pem
SIGNATURE_CERT_PATH=/certs/signing-cert-chain.pem
SIGNATURE_KEY_PASSWORD=           # leave empty for unencrypted keys
SIGNATURE_TSA_URL=http://timestamp.digicert.com  # optional: RFC 3161 timestamping
```

#### Certificate Requirements

- **Private key**: RSA >= 2048-bit or ECDSA P-256/P-384, PEM-encoded
- **Certificate chain**: PEM file containing the signer certificate followed by any intermediate CA certificates
- **Key-cert match**: The certificate's public key must match the private key

#### Startup Validation

When `SIGNATURE_MODE=pades`, the application validates at startup that:

1. `SIGNATURE_KEY_PATH` and `SIGNATURE_CERT_PATH` are set
2. Both files exist and are readable
3. The private key can be loaded (with password if provided)
4. The certificate's public key matches the private key

If any check fails, the application refuses to start with a clear error message.

#### Generating a Self-Signed Certificate (Testing)

For testing PAdES mode without a CA-issued certificate:

```bash
# Generate a private key
openssl genrsa -out signing-key.pem 2048

# Generate a self-signed certificate (valid 1 year)
openssl req -new -x509 -key signing-key.pem -out signing-cert-chain.pem -days 365 \
  -subj "/CN=AlcoaBase Signer/O=Your Organization/C=DE"
```

#### Timestamp Authority (Optional)

If `SIGNATURE_TSA_URL` is configured, each signature includes an RFC 3161 timestamp proving when the signature was created. This provides long-term validation even after the signing certificate expires.

Public TSA services:
- `http://timestamp.digicert.com`
- `http://timestamp.sectigo.com`
- `http://tsa.starfieldtech.com`

## How It Works (Technical)

### Signing Flow

1. User clicks a signature-required transition button
2. Frontend opens the Signature Dialog (re-auth, then reason, then sign)
3. Frontend verifies identity via the re-authentication endpoint (120s token)
4. Frontend calls the signing endpoint with document UUID, version, transition, reason, and password
5. Backend re-authenticates the user, downloads the PDF, applies the signature (hash or PAdES), uploads the signed PDF, and records the event
6. Frontend displays success and executes the workflow transition

### Verification Flow

1. User clicks "Verify" on the document detail page
2. Frontend calls the verification endpoint
3. Backend downloads the signed PDF and verifies all embedded signatures
4. Results are displayed inline with per-signature validity

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/signatures/sign` | POST | Sign a document (requires re-auth) |
| `/api/signatures/records/{document_uuid}` | GET | Get all signature records for a document |
| `/api/signatures/verify/{document_uuid}` | GET | Verify all signatures on a document |
| `/api/v1/auth/re-authenticate` | POST | Re-authenticate for signature operations |

## Regulatory Compliance

### 21 CFR Part 11 Requirements Met

| Requirement | Implementation |
|-------------|---------------|
| Unique identification | User ID + password re-authentication before every signature |
| Signature meaning | Mandatory reason category (Author/Review/Approval) + descriptive note |
| Date and time | Server-side UTC timestamp, optionally with RFC 3161 TSA proof |
| Non-repudiation | Asymmetric cryptography (PAdES mode) — only the private key holder can sign |
| Tamper detection | SHA-256 content hash (hash mode) or CMS signature (PAdES mode) |
| Audit trail | Every signature event recorded with signer, reason, timestamp, and hash |

### EU Annex 11 / eIDAS

- PAdES-B-LT signature profile for long-term validation
- Certificate chain embedded in the signed PDF
- Optional timestamping for proof of signing time
- Visible signature annotation on the PDF page
