"""Format-dispatching sanitization pipeline.

Routes downloaded files to format-specific sanitizers and produces
a unified StructuredContent output regardless of input format.

References:
    - Requirements 5.1–5.6, 6.1–6.7, 16.1–16.6
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from alcoabase.literature.ingestion.exceptions import (
    SanitizationError,
    UnsupportedContentTypeError,
)

if TYPE_CHECKING:
    from alcoabase.literature.ingestion.schemas.structured_content import (
        StructuredContent,
    )

logger = logging.getLogger(__name__)


class BaseSanitizer(ABC):
    """Abstract base for format-specific sanitizers.

    Subclasses implement the ``sanitize`` method to extract structured
    content from raw file bytes of a specific MIME type (PDF, HTML, XML).
    """

    @abstractmethod
    async def sanitize(
        self,
        content: bytes,
        content_type: str,
    ) -> StructuredContent:
        """Extract structured content from raw file bytes.

        Args:
            content: Raw file bytes.
            content_type: MIME type for validation.

        Returns:
            StructuredContent with extracted sections.

        Raises:
            SanitizationError: If content cannot be processed.
        """
        ...


class SanitizationPipeline:
    """Dispatcher that routes content to the appropriate sanitizer.

    Determines the correct sanitizer based on content_type and delegates
    processing. The pipeline holds concrete sanitizer instances injected
    at construction time.

    The content_type mapping is:
        - "application/pdf" → pdf_sanitizer
        - "text/html" → html_sanitizer
        - "application/xml" → xml_sanitizer
        - "text/xml" → xml_sanitizer
        - "application/jats+xml" → xml_sanitizer
    """

    SUPPORTED_CONTENT_TYPES: dict[str, str] = {
        "application/pdf": "pdf",
        "text/html": "html",
        "application/xml": "xml",
        "text/xml": "xml",
        "application/jats+xml": "xml",
    }

    def __init__(
        self,
        pdf_sanitizer: BaseSanitizer,
        html_sanitizer: BaseSanitizer,
        xml_sanitizer: BaseSanitizer,
    ) -> None:
        """Initialize the sanitization pipeline with format-specific sanitizers.

        Args:
            pdf_sanitizer: Sanitizer for application/pdf content.
            html_sanitizer: Sanitizer for text/html content.
            xml_sanitizer: Sanitizer for application/xml, text/xml,
                and application/jats+xml content.
        """
        self._sanitizers: dict[str, BaseSanitizer] = {
            "pdf": pdf_sanitizer,
            "html": html_sanitizer,
            "xml": xml_sanitizer,
        }

    async def process(
        self,
        content: bytes,
        content_type: str,
        record_id: int,
    ) -> StructuredContent:
        """Route content to the appropriate sanitizer.

        Args:
            content: Raw file bytes.
            content_type: MIME type to select sanitizer.
            record_id: For logging and error context.

        Returns:
            StructuredContent with all extracted sections.

        Raises:
            UnsupportedContentTypeError: If no sanitizer handles this type.
            SanitizationError: If processing fails.
        """
        sanitizer_key = self.SUPPORTED_CONTENT_TYPES.get(content_type)

        if sanitizer_key is None:
            logger.warning(
                "Unsupported content type '%s' for record %d",
                content_type,
                record_id,
            )
            raise UnsupportedContentTypeError(
                f"Content type '{content_type}' is not supported for sanitization.",
                content_type=content_type,
                record_id=record_id,
            )

        sanitizer = self._sanitizers[sanitizer_key]

        logger.info(
            "Dispatching record %d to %s sanitizer (content_type=%s)",
            record_id,
            sanitizer_key,
            content_type,
        )

        try:
            result = await sanitizer.sanitize(content, content_type)
        except SanitizationError:
            raise
        except Exception as exc:
            logger.exception(
                "Unexpected error sanitizing record %d with %s sanitizer",
                record_id,
                sanitizer_key,
            )
            raise SanitizationError(
                f"Unexpected error during {sanitizer_key} sanitization: {exc}",
                record_id=record_id,
                error_type="unexpected_error",
                content_type=content_type,
            ) from exc

        logger.info(
            "Successfully sanitized record %d: word_count=%d",
            record_id,
            result.word_count,
        )

        return result
