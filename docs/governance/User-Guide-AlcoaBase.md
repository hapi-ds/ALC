# AlcoaBase User Guide

| Field | Value |
|-------|-------|
| **Audience** | All Users (Member, Viewer roles and above) |

---

## 1. Getting Started

### 1.1 Login

1. Navigate to your AlcoaBase instance (e.g., `http://your-server:3000`)
2. Enter your username and password
3. Click **Login**

If this is your first login with a temporary password, you'll be prompted to change it.

### 1.2 Navigation

The left sidebar contains all main sections:

| Section | Purpose |
|---------|---------|
| Documents | Upload, browse, and manage documents |
| Virtual Folders | Tag-based document grouping |
| Templates | Form templates for data collection |
| Reports | Data entry and PDF extraction |
| Workflows | Document lifecycle management |
| Training | Required training tasks and quizzes |
| Search | Full-text and semantic search |
| Knowledge Chat | Ask questions about your documents |
| Signatures | Electronic signing and verification |

### 1.3 Company Context

If you belong to multiple companies, use the **company switcher** in the top-right header to change context. All data is scoped to the active company.

---

## 2. Document Management

### 2.1 Uploading Documents

1. Navigate to **Documents**
2. Click **Upload** (or drag files onto the page)
3. Fill in the title, document type, and folder path
4. Click **Submit**

Supported formats: PDF, DOCX. Maximum file size: 100 MB.

### 2.2 Document Versions

Each document can have multiple versions:
- **Major versions** (1.0, 2.0) — significant content changes
- **Minor versions** (1.1, 1.2) — corrections and formatting

To upload a new version:
1. Open the document detail page
2. Click **New Version**
3. Select major or minor
4. Provide a change reason (mandatory for ALCOA+ compliance)
5. Upload the updated file

### 2.3 Document Status

Documents progress through workflow states (e.g., Draft → Review → Approved → Active). The current status is shown on each document card.

---

## 3. Workflows

### 3.1 State Transitions

When a document is ready to move to the next state:
1. Open the document detail
2. The **available transitions** are shown as buttons
3. Click the transition (e.g., "Submit for Review")
4. Enter a **change reason** (mandatory)
5. If the transition requires a signature, you'll be prompted to re-authenticate

### 3.2 Gate Indicators

Some transitions show gate icons:
- 🔒 **Signature required** — You must sign before this transition completes
- 🎓 **Training required** — You must complete training before accessing this document
- ⚠️ **High risk** — This document type triggers stricter review

---

## 4. Training

### 4.1 Your Training Tasks

Navigate to **Training** to see:
- **Pending tasks** — Training you need to complete
- **Completed tasks** — Your training history

### 4.2 Completing Training

1. Click on a pending training task
2. Read the associated document
3. Click **Take Quiz**
4. Answer the questions (80% correct required to pass)
5. Upon passing, access to the document is granted

### 4.3 Training-Gated Access

If you try to open a document that requires training, you'll see a gate message. Complete the training first, then the document becomes accessible.

---

## 5. Electronic Signatures

### 5.1 Signing a Document

1. Navigate to the document requiring signature
2. Click **Sign**
3. Select the signature meaning (Author / Review / Approval)
4. Re-enter your password to authenticate
5. The signature is embedded in the PDF and recorded immutably

### 5.2 Verifying Signatures

Signed documents show a green badge. Click it to see:
- Signer name and timestamp
- Signature meaning
- Certificate information

---

## 6. Search & Knowledge

### 6.1 Document Search

Use the **Search** page for:
- Full-text keyword search
- Semantic (meaning-based) search
- Filter by document type, status, tags

### 6.2 Knowledge Chat

The **Knowledge Chat** lets you ask questions in natural language:
1. Type your question (e.g., "What are the calibration requirements for pH meters?")
2. The AI searches relevant documents and synthesizes an answer
3. Source citations link directly to the referenced documents

**Important:** Always verify AI answers against the source documents. AI responses are informational and do not constitute approved content.

---

## 7. Reports & Templates

### 7.1 Filling a Report

1. Navigate to **Reports** → **New Report**
2. Select the template
3. Fill in all required fields
4. Submit the report

### 7.2 Offline PDF Workflow

1. Download the blank PDF template from the template detail page
2. Fill it in offline (print or digital)
3. Upload the completed PDF back to AlcoaBase
4. The system extracts field values and compares them to manual entry

---

## 8. Tips & Best Practices

- **Always provide meaningful change reasons** — auditors review these
- **Check your training status** regularly — access may be revoked when documents are updated
- **Use virtual folders** to organize your view without affecting the physical document structure
- **Verify AI responses** — the Knowledge Chat is a research aid, not an authority
- **Report issues** — if AI suggestions seem wrong, use the deviation workflow

---

*End of Document*
