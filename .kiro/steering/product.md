# Product Overview

AlcoaBase (ALC) is a 100% local, open-source Document & Knowledge Management System designed for highly regulated environments (Pharma, Biotech, Manufacturing).

## Core Purpose

Bridge strict ALCOA+ data integrity compliance with AI capabilities in a fully air-gapped deployment. No data ever leaves the local network.

## Key Capabilities

- **ALCOA+ Audit Trail**: Immutable logs for every action (Who, What, When, Why). Cryptographic PAdES digital signatures.
- **Deterministic PDF-to-Database Mapping**: JSON-driven form builder producing React forms and offline PDFs. Dual-UUID concept maps offline PDF data back to PostgreSQL.
- **Local AI / RAG**: Document Q&A via vLLM inference (NVIDIA GPU optimized). Hybrid lexical + semantic search via OpenSearch.
- **BPMN Workflows**: Visual drag-and-drop lifecycle editor (Draft → Review → Approved → InTraining → Active).
- **Training-Gated Access**: Users must hold valid training records AND pass comprehension quizzes before executing tasks on specific SOP versions.
- **Automated CSV (Computer System Validation)**: Playwright-based E2E tests generate tamper-proof validation certificates for FDA/EMA audits.
- **Modular Agent Framework**: YAML-defined AI agent archetypes with personality profiles, hot-reloaded at runtime.

## Regulatory Context

Targets GxP (GMP, GLP, GCP) compliance. Every mutating API request requires an `X-Change-Reason` header for full traceability. Multi-tenancy isolates companies with strict data boundaries.

## Deployment Model

Docker Compose stack. All AI containers run on an isolated internal network with no outbound internet access. Supports GPU (production) and mock (development) modes.
