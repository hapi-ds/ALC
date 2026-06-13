# AI Regulatory Guidelines for AlcoaBase
## Cross-Sector Compliance Framework

| Field | Value |
|-------|-------|
| **Classification** | GxP-Relevant |
| **Applicable Regulations** | EU AI Act, 21 CFR Part 11, ISO 13485, GMP Annex 11 |

---

## 1. Purpose

This document defines how AI capabilities within AlcoaBase are governed, validated, and used in compliance with global regulations. It provides practical guidance for all user roles on what AI can and cannot do, how outputs must be reviewed, and what evidence must be maintained.

---

## 2. AI Risk Classification

AlcoaBase classifies all AI operations into three risk tiers based on their potential impact on GxP-regulated processes:

### 2.1 High-Risk AI Operations

| Operation | Risk Justification | Required Controls |
|-----------|-------------------|------------------|
| Document Generation (Phase 5.4) | AI-created regulatory content may contain errors affecting patient safety or compliance | HITL mandatory review before publication; provenance audit trail; human approval gate |
| Multi-Agent Auditing (Phase 5.2) | Automated compliance assessments could miss critical findings or produce false positives | Master Auditor summary requires human sign-off; individual agent reports available for manual review |
| Training Content Generation (Phase 5.3) | Incorrect training materials could lead to improperly trained personnel | Generated content marked as "Draft — Requires Review"; quiz answers validated by SME |

**Control Requirements:**
- Output is NOT visible to end users until HITL reviewer approves
- Full input/output logged immutably (up to 50,000 characters)
- 72-hour expiry on pending HITL checkpoints
- Change impact analysis triggered on approval

### 2.2 Medium-Risk AI Operations

| Operation | Risk Justification | Required Controls |
|-----------|-------------------|------------------|
| Change Impact Analysis (Phase 5.5) | Incorrect dependency mapping could miss affected documents | Results presented as "suggestions" requiring confirmation; human validates affected items |
| Traceability Gap Discovery (Phase 5.6) | False orphan alerts could waste resources; missed gaps could hide compliance issues | Confidence scores displayed; human reviews before creating formal action items |

**Control Requirements:**
- Output visible but clearly marked as "AI-Suggested — Pending Confirmation"
- Automated actions (notifications, workflow triggers) blocked until confirmed
- Input/output logged with medium audit depth

### 2.3 Low-Risk AI Operations

| Operation | Risk Justification | Required Controls |
|-----------|-------------------|------------------|
| RAG Knowledge Query (Phase 4.2) | Informational only; user must verify against source documents | Source citations always provided; disclaimer in UI |
| Document Search (Phase 4.1) | Ranking/relevance is informational; user sees actual document content | No approval required; usage logged at basic level |
| Template Analysis (Phase 5.4 prep) | Structure analysis only; no content generation | Results used as input to generation, not exposed directly |

**Control Requirements:**
- Output returned immediately (no blocking)
- Basic audit logging (timestamp, user, task type)
- Rate-limited per user (100 operations/hour)

---

## 3. Sector-Specific Guidance

### 3.1 Pharmaceutical (GMP)

| Regulation | AI Requirement | AlcoaBase Implementation |
|------------|---------------|------------------------|
| EU GMP Annex 11 §4.1 | Computerized systems shall be validated | CSV runner generates validation certificates |
| EU GMP Annex 11 §7.1 | Data shall be checked for accuracy | AI outputs require HITL review for High/Medium tier |
| EU GMP Annex 11 §9.1 | Audit trail mandatory | All AI operations logged with full attribution |
| 21 CFR Part 11 §11.10(a) | System validation | Property-based tests + E2E Playwright validation |
| 21 CFR Part 11 §11.10(e) | Audit trail | Immutable operation logs per ALCOA+ |

**GMP-Specific Rules:**
- AI-generated SOPs MUST go through full Draft → Review → Approved → Training cycle
- No AI output may bypass the electronic signature requirement
- Batch-related documents require minimum 2 human reviewers before AI-assisted approval

### 3.2 Medical Devices (ISO 13485)

| Regulation | AI Requirement | AlcoaBase Implementation |
|------------|---------------|------------------------|
| ISO 13485 §4.2.4 | Document control procedures | BPMN workflows enforce lifecycle; AI cannot skip states |
| ISO 13485 §7.3.7 | Design changes require review | Change Impact Analysis identifies affected design documents |
| MDR 2017/745 Art. 10(9) | Post-market surveillance | Literature Vigilance monitors adverse events (Phase 9.5) |
| IVDR 2017/746 Art. 78 | Vigilance reporting | Signal detection with escalation to Doc-Admin |

**MedTech-Specific Rules:**
- Design History File (DHF) documents require High-risk classification even for summaries
- AI-assisted traceability matrices must be verified against the formal requirements in the DHF
- Vigilance signals classified as "Critical" bypass normal workflow and escalate immediately

### 3.3 General AI Governance (EU AI Act)

| Article | Requirement | AlcoaBase Implementation |
|---------|------------|------------------------|
| Art. 9(1) | Risk management system | Risk Framework with 3-tier classification |
| Art. 9(2)(a) | Identify and analyse risks | Per-operation risk assessment before execution |
| Art. 13(1) | Transparency and information | AI operations logged; provenance trails maintained |
| Art. 14(1) | Human oversight | HITL checkpoints for High-risk; confirmation for Medium-risk |
| Art. 14(4)(d) | Ability to override AI | All AI outputs can be rejected, edited, or overridden by human |
| Art. 17(1)(f) | Quality management — accountability | Operation logs trace to specific user and company |

---

## 4. User Responsibilities by Role

### 4.1 System Administrator
- Configure risk tier assignments per company
- Monitor HITL checkpoint queue for expiry warnings
- Review AI operation logs for anomalies
- Approve/reject pending High-risk AI outputs

### 4.2 Document Administrator
- Review AI-generated documents before publication
- Validate Change Impact Analysis results
- Confirm traceability link suggestions
- Manage training content accuracy

### 4.3 Quality Manager
- Validate compliance scoring methodology
- Review Multi-Agent Audit findings
- Approve risk profile customizations
- Sign off on AI-assisted regulatory submissions

### 4.4 Standard User
- Use RAG knowledge base for information (verify against sources)
- Complete AI-generated training tasks
- Report incorrect AI suggestions via deviation workflow
- Do NOT approve AI-generated content without appropriate role

---

## 5. Validation Requirements

All AI features must be validated according to:

| Validation Activity | Frequency | Evidence |
|--------------------|-----------|---------| 
| Property-based correctness tests (Hypothesis) | Every code change | Test suite pass report |
| Integration tests (full request lifecycle) | Every code change | CI/CD pipeline results |
| End-to-end Playwright validation | Before deployment; quarterly | CSV Validation Certificate |
| Risk framework tier assignment review | Annually or after major release | Risk assessment document |
| HITL effectiveness audit | Semi-annually | Checkpoint approval/rejection statistics |

---

## 6. Prohibited Uses

The following uses of AI within AlcoaBase are explicitly prohibited:

1. **Autonomous approval** — AI may NEVER approve a document, sign electronically, or complete a workflow transition without human action
2. **Unsupervised content publication** — AI-generated content may NEVER enter "Active" state without human review
3. **Cross-tenant inference** — AI operations for Company A may NEVER access Company B's data
4. **Internet-connected inference** — AI models may NEVER make outbound network requests (except configured literature API gateways)
5. **Training data extraction** — User queries may NEVER be used to retrain or fine-tune models

---

## 7. Change History

> Version history is managed by AlcoaBase document versioning. See document metadata for authoritative version, date, and author information.

---

*End of Document*
