# AlcoaBase Documentation Index

Welcome to the AlcoaBase user documentation. This index organizes all feature guides by domain, giving you a clear path through the platform from initial setup to advanced AI-powered workflows.

---

## How to Use This Documentation

Each guide is a self-contained reference for a specific feature. Start with the **Getting Started** section if this is a fresh deployment, then explore guides by domain as you configure and adopt capabilities. Guides are ordered within each section to reflect a natural progression — earlier guides cover prerequisites for later ones.

---

## 1. Getting Started

| Guide | What You'll Learn |
|-------|-------------------|
| [Setup Wizard](setup-wizard-guide.md) | First-run initialization: create admin account, establish your company, configure AI hardware, seed demo data |
| [Document Upload](document-upload-guide.md) | Upload documents via the web UI or bulk CLI tool, manage versions, browse and filter |

---

## 2. Document Lifecycle & Compliance

| Guide | What You'll Learn |
|-------|-------------------|
| [Workflow Editor](workflow-editor-guide.md) | Design BPMN document lifecycle workflows with states, transitions, signature gates, and training triggers |
| [Workflow Execution](workflow-execution-guide.md) | Execute state transitions, understand gate indicators, provide change reasons, review audit history |
| [Electronic Signatures](electronic-signatures-guide.md) | PAdES digital signing, re-authentication, 21 CFR Part 11 compliance, certificate configuration |
| [Training Management](training-management-guide.md) | View training tasks, complete training, content viewer, records, gate enforcement, admin monitoring |
| [Comprehension Quiz](quiz-comprehension-guide.md) | Quiz taking, scoring, pass/fail threshold, dual gate verification, immutable audit trail |

---

## 3. Search & Knowledge

| Guide | What You'll Learn |
|-------|-------------------|
| [Search & Knowledge Base](search-knowledge-guide.md) | Hybrid search (BM25+kNN), RAG knowledge chat, document indexing, visual content discovery |
| [AI Inference](ai-inference-guide.md) | vLLM integration: RAG queries, embedding generation, OCR, health monitoring, mock mode for development |

---

## 4. AI-Powered Document Intelligence

| Guide | What You'll Learn |
|-------|-------------------|
| [Agent Management](agent-management-guide.md) | Agent registry, archetypes, personality profiles, tuning parameters, YAML definitions, hot-reload |
| [Multi-Agent Auditing](multi-agent-auditing-guide.md) | Parallel AI document review, audit profiles, compliance scoring, anomaly detection, missing link reports |
| [AI Document Generator](ai-document-generator-guide.md) | Template-based generation, provenance audit trail, cross-references, mandatory human review workflow |
| [AI Training Ecosystem](ai-training-ecosystem-guide.md) | Personalized schedules, AI material generation, semantic quiz grading, virtual audit role-play, dynamic feedback |
| [Change Impact Analysis](change-impact-analysis-guide.md) | Dependency graphs, automatic impact detection, section-level gap analysis, notifications, training resets |
| [Traceability & Gap Discovery](traceability-gap-discovery-guide.md) | Automated traceability matrices, three-pass matching, orphan detection, coverage metrics, stale link alerts |

---

## 5. Literature Research & Evidence Management

This section covers the complete literature research pipeline — from querying external databases through to managing citation evidence for regulatory submissions. Features build on each other in sequence.

| Guide | What You'll Learn |
|-------|-------------------|
| [Literature Search Engine](literature-search-guide.md) | External database gateways (PubMed, Crossref, arXiv), API key management, rate limiting, proxy routing |
| [Literature Ingestion Pipeline](literature-ingestion-guide.md) | Automated full-text retrieval via Unpaywall, PDF/HTML/XML sanitization, storage quotas, retention policies |
| [Literature Embedding & Hybrid Search](literature-embedding-hybrid-search-guide.md) | Semantic embedding generation, hybrid BM25+kNN indexing, unified cross-corpus search, partition tagging |
| [Literature Review & Synthesis Agents](literature-review-synthesis-guide.md) | AI-powered SLR screening, PICO criteria, contradiction detection, novelty flagging, inter-rater reliability |
| [Medical Device Vigilance & PMS](medical-device-vigilance-pms-guide.md) | Product registration, vigilance search profiles, safety signal detection, periodic reports, MDR/IVDR compliance |
| [Literature Search & Citation UI](literature-search-citation-ui-guide.md) | Faceted search dashboard, one-click internalization, citation collections, traceability mapping, PRISMA exports |

---

## 6. Administration & Governance

| Guide | What You'll Learn |
|-------|-------------------|
| [Admin — User Management](admin-dashboard-user-management-guide.md) | RBAC roles, user CRUD, permission templates, company memberships, deactivation, password reset |
| [Admin — System Configuration](admin-system-configuration-guide.md) | AI hardware, storage quotas, backup scheduling, health monitoring, service status, rollback |
| [Audit Trail Viewer](audit-trail-viewer-guide.md) | Centralized audit log, filtering, search, PDF export, immutability enforcement, meta-auditing |
| [AI Risk & Compliance Framework](ai-risk-compliance-framework-guide.md) | Risk tiers (High/Medium/Low), HITL checkpoints, control gates, operation logging, company risk profiles |

---

## 7. Corporate Environment & Regulatory Documents

| Guide | What You'll Learn |
|-------|-------------------|
| [ALC Corporate Environment](alc-corporate-environment-guide.md) | Corporate tenant seeding, user provisioning, regulatory baselines, governance folders, agent activations |
| [Cross-Sector AI Guidelines](cross-sector-ai-guidelines-guide.md) | AI usage policy generation, sector-specific modules (Pharma/MedTech/IVD), risk tier integration |
| [Documentation Suite](documentation-suite-guide.md) | User Guide & Admin Guide generation, cross-references, versioning, governance workflow integration |

---

## Quick Reference

### Role Requirements by Feature Area

| Area | Minimum Role |
|------|--------------|
| Document browsing, search, knowledge chat | `viewer` |
| Document upload, transitions, training | `member` |
| Literature search, saved searches, export | `member` |
| Internalization, citation management, traceability | `document_admin` |
| User management, system configuration | `system_admin` / `it_admin` |
| Audit trail access | `system_admin` / `doc_admin` / `it_admin` |

### Key Concepts Across All Features

| Concept | Description |
|---------|-------------|
| `X-Company-Id` | Header identifying the tenant context; required on all API calls |
| `X-Change-Reason` | Header required on all mutating requests (POST/PUT/DELETE) for ALCOA+ compliance |
| Multi-tenancy | All data is scoped to a company; cross-tenant access is impossible |
| Immutable audit | Every state change, access event, and AI operation is logged permanently |
| Soft-delete | Records are archived (status → "archived") rather than physically deleted |

---

## 8. Manual Testing & Validation

| Document | Location | Purpose |
|----------|----------|---------|
| Test Protocols | `docs/test-protocols/` | Reusable step-by-step test procedures (GxP-compliant format) |
| Test Reports | `docs/test-reports/` | Executed results with pass/fail, tester sign-off, and deviations |

### Available Protocols (Phase 10)

| Protocol | Title |
|----------|-------|
| TP-10.1.1 | Docker Services Health |
| TP-10.1.2 | Setup Wizard — Admin Account |
| TP-10.1.3 | Setup Wizard — Company Creation & Multi-Tenancy |
| TP-10.1.4 | Setup Wizard — AI Mode Configuration |

---

## Regulatory Alignment

AlcoaBase documentation and features are designed to support compliance with:

- **21 CFR Part 11** — Electronic records and signatures (FDA)
- **EU Annex 11** — Computerized systems in GxP environments (EMA)
- **EU AI Act** — Risk-based AI governance framework
- **ISO 13485** — Quality management for medical devices
- **MDR 2017/745** — Medical Device Regulation (EU)
- **IVDR 2017/746** — In Vitro Diagnostic Regulation (EU)
- **GMP / GLP / GCP** — Good Manufacturing/Laboratory/Clinical Practice

---

*Last updated: June 2026*
