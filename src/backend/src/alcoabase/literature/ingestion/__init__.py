"""Automated Ingestion Pipeline (Phase 9.2).

This sub-package implements the dual-stage asynchronous ingestion pipeline
that consumes LiteratureSearchResult objects from Phase 9.1, retrieves
full-text content via Unpaywall, sanitizes downloaded files (PDF, HTML,
XML/JATS) into a unified StructuredContent format, and stores all artifacts
in MinIO with company-level isolation.
"""
