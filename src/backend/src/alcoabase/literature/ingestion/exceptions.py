"""Custom exception hierarchy for the Ingestion Pipeline.

All exceptions raised by the ingestion pipeline subsystem inherit from
``IngestionPipelineError``.  Each exception carries contextual attributes
relevant to diagnosing the failure (record IDs, states, file details, etc.).

References:
    - Requirements 2.2, 3.3, 3.4, 4.2, 4.3, 4.6, 5.3, 6.5, 14.2, 14.3, 14.7
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Base Exception
# ─────────────────────────────────────────────────────────────────────────────


class IngestionPipelineError(Exception):
    """Base exception for all ingestion pipeline errors.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context in which the error occurred.
    """

    def __init__(
        self,
        message: str = "An ingestion pipeline error occurred.",
        *,
        company_id: int | None = None,
    ) -> None:
        self.message = message
        self.company_id = company_id
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# State Machine Errors
# ─────────────────────────────────────────────────────────────────────────────


class InvalidStateTransitionError(IngestionPipelineError):
    """Raised when an invalid state transition is attempted on an IngestionRecord.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        current_state: The current state of the ingestion record.
        target_state: The state that was attempted.
        record_id: The ingestion record ID involved.
    """

    def __init__(
        self,
        message: str = "Invalid state transition attempted.",
        *,
        company_id: int | None = None,
        current_state: str | None = None,
        target_state: str | None = None,
        record_id: int | None = None,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        self.record_id = record_id
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Deduplication and Record Errors
# ─────────────────────────────────────────────────────────────────────────────


class DuplicateRecordError(IngestionPipelineError):
    """Raised when an ingestion submission matches an existing record.

    Duplicate detection is based on (company_id + DOI) or
    (company_id + source_id + external_id).

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        existing_record_id: The ID of the already-existing ingestion record.
        doi: The DOI that caused the duplicate match, if applicable.
        source_id: The source ID that caused the duplicate match, if applicable.
        external_id: The external ID that caused the duplicate match, if applicable.
    """

    def __init__(
        self,
        message: str = "Duplicate ingestion record detected.",
        *,
        company_id: int | None = None,
        existing_record_id: int | None = None,
        doi: str | None = None,
        source_id: str | None = None,
        external_id: str | None = None,
    ) -> None:
        self.existing_record_id = existing_record_id
        self.doi = doi
        self.source_id = source_id
        self.external_id = external_id
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Storage Errors
# ─────────────────────────────────────────────────────────────────────────────


class StorageQuotaExceededError(IngestionPipelineError):
    """Raised when a company's storage quota has been fully consumed.

    New full-text downloads are rejected until storage is freed or
    the quota is increased.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company that exceeded quota.
        quota_mb: The configured storage quota in megabytes.
        usage_mb: The current storage usage in megabytes.
    """

    def __init__(
        self,
        message: str = "Storage quota exceeded. No new downloads permitted.",
        *,
        company_id: int | None = None,
        quota_mb: int | None = None,
        usage_mb: float | None = None,
    ) -> None:
        self.quota_mb = quota_mb
        self.usage_mb = usage_mb
        super().__init__(message, company_id=company_id)


class ChecksumMismatchError(IngestionPipelineError):
    """Raised when a SHA-256 checksum verification fails after upload.

    Indicates data corruption during transfer or storage.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        record_id: The ingestion record ID involved.
        expected_checksum: The expected SHA-256 hex digest.
        actual_checksum: The actual SHA-256 hex digest computed after upload.
    """

    def __init__(
        self,
        message: str = "SHA-256 checksum mismatch detected after upload.",
        *,
        company_id: int | None = None,
        record_id: int | None = None,
        expected_checksum: str | None = None,
        actual_checksum: str | None = None,
    ) -> None:
        self.record_id = record_id
        self.expected_checksum = expected_checksum
        self.actual_checksum = actual_checksum
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Unpaywall / DOI Resolution Errors
# ─────────────────────────────────────────────────────────────────────────────


class DOINotFoundError(IngestionPipelineError):
    """Raised when the Unpaywall API returns HTTP 404 for a DOI.

    The DOI does not exist in the Unpaywall database.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        doi: The DOI that was not found.
        record_id: The ingestion record ID involved.
    """

    def __init__(
        self,
        message: str = "DOI not found in Unpaywall.",
        *,
        company_id: int | None = None,
        doi: str | None = None,
        record_id: int | None = None,
    ) -> None:
        self.doi = doi
        self.record_id = record_id
        super().__init__(message, company_id=company_id)


class NoOpenAccessError(IngestionPipelineError):
    """Raised when no open-access version is available for a DOI.

    The DOI exists in Unpaywall but has no freely accessible full-text.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        doi: The DOI with no OA availability.
        record_id: The ingestion record ID involved.
    """

    def __init__(
        self,
        message: str = "No open-access version available for this DOI.",
        *,
        company_id: int | None = None,
        doi: str | None = None,
        record_id: int | None = None,
    ) -> None:
        self.doi = doi
        self.record_id = record_id
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Download and Content Errors
# ─────────────────────────────────────────────────────────────────────────────


class UnsupportedContentTypeError(IngestionPipelineError):
    """Raised when downloaded content has an unsupported MIME type.

    Allowed types: application/pdf, text/html, application/xml,
    text/xml, application/jats+xml.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        content_type: The unsupported Content-Type that was received.
        record_id: The ingestion record ID involved.
    """

    def __init__(
        self,
        message: str = "Unsupported content type for ingestion.",
        *,
        company_id: int | None = None,
        content_type: str | None = None,
        record_id: int | None = None,
    ) -> None:
        self.content_type = content_type
        self.record_id = record_id
        super().__init__(message, company_id=company_id)


class FileTooLargeError(IngestionPipelineError):
    """Raised when a download exceeds the maximum allowed file size.

    The download is aborted before transfer completes.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        file_size_bytes: The reported file size in bytes.
        max_size_bytes: The maximum allowed file size in bytes.
        record_id: The ingestion record ID involved.
    """

    def __init__(
        self,
        message: str = "File exceeds maximum allowed size.",
        *,
        company_id: int | None = None,
        file_size_bytes: int | None = None,
        max_size_bytes: int | None = None,
        record_id: int | None = None,
    ) -> None:
        self.file_size_bytes = file_size_bytes
        self.max_size_bytes = max_size_bytes
        self.record_id = record_id
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Sanitization Errors
# ─────────────────────────────────────────────────────────────────────────────


class SanitizationError(IngestionPipelineError):
    """Raised when the sanitization pipeline fails to process a file.

    Covers parse errors, encoding failures, corrupted files, and
    scanned-only PDFs requiring OCR.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        record_id: The ingestion record ID involved.
        error_type: Specific sanitization failure category
            (e.g., 'parse_error', 'ocr_required', 'corrupt_file').
        content_type: The MIME type of the file that failed sanitization.
    """

    def __init__(
        self,
        message: str = "Sanitization failed for the ingested file.",
        *,
        company_id: int | None = None,
        record_id: int | None = None,
        error_type: str | None = None,
        content_type: str | None = None,
    ) -> None:
        self.record_id = record_id
        self.error_type = error_type
        self.content_type = content_type
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Batch and Operational Errors
# ─────────────────────────────────────────────────────────────────────────────


class BatchTooLargeError(IngestionPipelineError):
    """Raised when a batch ingestion request exceeds the maximum size.

    The maximum batch size is 100 Literature_Search_Results per request.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        batch_size: The actual number of items submitted.
        max_batch_size: The maximum allowed batch size.
    """

    def __init__(
        self,
        message: str = "Batch size exceeds maximum allowed limit.",
        *,
        company_id: int | None = None,
        batch_size: int | None = None,
        max_batch_size: int = 100,
    ) -> None:
        self.batch_size = batch_size
        self.max_batch_size = max_batch_size
        super().__init__(message, company_id=company_id)


class MaxRetriesExceededError(IngestionPipelineError):
    """Raised when an ingestion record has exhausted all retry attempts.

    The maximum retry count is 3 per state transition failure.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        record_id: The ingestion record ID involved.
        retry_count: The number of retries that have been attempted.
        max_retries: The maximum number of retries allowed.
        last_error: Description of the last error encountered.
    """

    def __init__(
        self,
        message: str = "Maximum retry attempts exceeded.",
        *,
        company_id: int | None = None,
        record_id: int | None = None,
        retry_count: int | None = None,
        max_retries: int = 3,
        last_error: str | None = None,
    ) -> None:
        self.record_id = record_id
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.last_error = last_error
        super().__init__(message, company_id=company_id)


class CompanyPausedError(IngestionPipelineError):
    """Raised when ingestion is paused for a company.

    This can occur due to quota exhaustion, administrative action,
    or circuit breaker activation affecting the company's operations.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the paused company.
        reason: The reason ingestion is paused.
        retry_after_seconds: Estimated seconds until ingestion may resume.
    """

    def __init__(
        self,
        message: str = "Ingestion is currently paused for this company.",
        *,
        company_id: int | None = None,
        reason: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.reason = reason
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Adapter Timeout Error
# ─────────────────────────────────────────────────────────────────────────────


class AdapterTimeoutError(IngestionPipelineError):
    """Raised when a request to an external API exceeds the timeout.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        source_adapter_name: Name of the adapter that raised the error.
        timeout_seconds: The timeout threshold that was exceeded.
    """

    def __init__(
        self,
        message: str = "Request to external API timed out.",
        *,
        company_id: int | None = None,
        source_adapter_name: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.source_adapter_name = source_adapter_name
        self.timeout_seconds = timeout_seconds
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limit Error (for 429 responses)
# ─────────────────────────────────────────────────────────────────────────────


class RateLimitedError(IngestionPipelineError):
    """Raised when an external API returns HTTP 429 (Too Many Requests).

    The caller should respect the retry_after value and requeue the task.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        retry_after_seconds: Seconds to wait before retrying.
        source_adapter_name: Name of the adapter that was rate-limited.
    """

    def __init__(
        self,
        message: str = "External API rate limit exceeded (HTTP 429).",
        *,
        company_id: int | None = None,
        retry_after_seconds: float | None = None,
        source_adapter_name: str | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.source_adapter_name = source_adapter_name
        super().__init__(message, company_id=company_id)
