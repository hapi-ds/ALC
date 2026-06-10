"""Content sanitization pipeline for ingested literature.

This sub-package provides format-specific sanitizers (PDF, HTML, XML/JATS)
that extract and normalize downloaded full-text content into the unified
StructuredContent schema.
"""

from alcoabase.literature.ingestion.services.sanitization.pdf_sanitizer import (
    PDFSanitizer,
)
from alcoabase.literature.ingestion.services.sanitization.pipeline import (
    BaseSanitizer,
    SanitizationPipeline,
)

__all__ = [
    "BaseSanitizer",
    "PDFSanitizer",
    "SanitizationPipeline",
]
