"""Custom exception hierarchy for the Embedding and Indexing Pipeline.

All exceptions raised by the embedding/indexing subsystem inherit from
``EmbeddingPipelineError``.  Errors are organized by failure domain:
vLLM generation failures, OpenSearch indexing/search failures,
tenant isolation violations, and operational errors.

References:
    - Requirements 12.1, 12.2, 12.6, 12.7
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Base Exception
# ─────────────────────────────────────────────────────────────────────────────


class EmbeddingPipelineError(Exception):
    """Base exception for all embedding and indexing pipeline errors.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context in which the error occurred.
    """

    def __init__(
        self,
        message: str = "An embedding pipeline error occurred.",
        *,
        company_id: int | None = None,
    ) -> None:
        self.message = message
        self.company_id = company_id
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Embedding Generation Errors
# ─────────────────────────────────────────────────────────────────────────────


class EmbeddingDimensionMismatchError(EmbeddingPipelineError):
    """Raised when embedding vectors have an unexpected dimension.

    The Embedding_Service validates that all vectors match the configured
    MODEL_EMBEDDING_DIMENSION before indexing. If a vector has a different
    dimension, the entire batch is rejected and the IngestionRecord
    transitions to ``failed`` with error_type ``embedding_dimension_mismatch``.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        expected_dimension: The configured embedding dimension.
        actual_dimension: The dimension of the invalid vector.
        record_id: The ingestion record ID involved.
    """

    def __init__(
        self,
        message: str = "Embedding vector dimension does not match configured value.",
        *,
        company_id: int | None = None,
        expected_dimension: int | None = None,
        actual_dimension: int | None = None,
        record_id: int | None = None,
    ) -> None:
        self.expected_dimension = expected_dimension
        self.actual_dimension = actual_dimension
        self.record_id = record_id
        super().__init__(message, company_id=company_id)


class EmbeddingGenerationError(EmbeddingPipelineError):
    """Raised when vLLM embedding generation fails after all retries.

    Covers vLLM instance unavailability, partial failures, and timeout
    errors. The IngestionRecord transitions to ``failed`` with
    error_type ``embedding_generation_error`` after 3 retry attempts
    with exponential backoff (30s, 2min, 10min).

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        record_id: The ingestion record ID involved.
        retry_count: Number of retries attempted before failure.
        last_error: Description of the final error encountered.
    """

    def __init__(
        self,
        message: str = "Embedding generation failed after exhausting retries.",
        *,
        company_id: int | None = None,
        record_id: int | None = None,
        retry_count: int | None = None,
        last_error: str | None = None,
    ) -> None:
        self.record_id = record_id
        self.retry_count = retry_count
        self.last_error = last_error
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# OpenSearch Indexing Errors
# ─────────────────────────────────────────────────────────────────────────────


class IndexingUnavailableError(EmbeddingPipelineError):
    """Raised when OpenSearch is unreachable during indexing operations.

    The Literature_Index_Manager retries 3 times with 10-second intervals
    before raising this error. The IngestionRecord transitions to ``failed``
    with error_type ``indexing_unavailable``.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        record_id: The ingestion record ID involved.
        index_name: The target OpenSearch index name.
        retry_count: Number of retries attempted before failure.
    """

    def __init__(
        self,
        message: str = "OpenSearch is unreachable after exhausting retries.",
        *,
        company_id: int | None = None,
        record_id: int | None = None,
        index_name: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        self.record_id = record_id
        self.index_name = index_name
        self.retry_count = retry_count
        super().__init__(message, company_id=company_id)


class IndexCreationError(EmbeddingPipelineError):
    """Raised when index creation fails after all retry attempts.

    The Literature_Index_Manager retries index creation up to 3 times
    with 10-second intervals. If all retries are exhausted, this error
    is raised with details about the company and attempted index name.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company whose index could not be created.
        index_name: The index name that failed to be created.
        retry_count: Number of retries attempted before failure.
    """

    def __init__(
        self,
        message: str = "Failed to create OpenSearch index after exhausting retries.",
        *,
        company_id: int | None = None,
        index_name: str | None = None,
        retry_count: int | None = None,
    ) -> None:
        self.index_name = index_name
        self.retry_count = retry_count
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Tenant Isolation Errors
# ─────────────────────────────────────────────────────────────────────────────


class TenantIsolationError(EmbeddingPipelineError):
    """Raised when a cross-tenant data access violation is detected.

    This occurs when a chunk's company_id does not match the authenticated
    company context, or when a search/indexing request targets the wrong
    company's index. Logs a security violation entry to the audit trail.

    Attributes:
        message: Human-readable error description.
        company_id: The authenticated company context.
        target_company_id: The mismatched company_id from the payload.
        user_id: The requesting user ID.
        operation: The operation type (e.g., 'index', 'search', 'delete').
    """

    def __init__(
        self,
        message: str = "Tenant isolation violation detected.",
        *,
        company_id: int | None = None,
        target_company_id: int | None = None,
        user_id: int | None = None,
        operation: str | None = None,
    ) -> None:
        self.target_company_id = target_company_id
        self.user_id = user_id
        self.operation = operation
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Partition and Re-indexing Errors
# ─────────────────────────────────────────────────────────────────────────────


class PartitionTagUpdateError(EmbeddingPipelineError):
    """Raised when an atomic partition_tag update fails or is partial.

    When re-tagging Content_Chunks for an IngestionRecord, either all
    chunks must be updated or none. If partial execution is detected,
    all affected chunks are rolled back to their original tag value.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        record_id: The ingestion record ID involved.
        expected_updates: Number of chunks expected to be updated.
        actual_updates: Number of chunks actually updated before failure.
        original_tag: The original partition_tag value.
        target_tag: The intended new partition_tag value.
    """

    def __init__(
        self,
        message: str = "Partition tag update failed; rollback executed.",
        *,
        company_id: int | None = None,
        record_id: int | None = None,
        expected_updates: int | None = None,
        actual_updates: int | None = None,
        original_tag: str | None = None,
        target_tag: str | None = None,
    ) -> None:
        self.record_id = record_id
        self.expected_updates = expected_updates
        self.actual_updates = actual_updates
        self.original_tag = original_tag
        self.target_tag = target_tag
        super().__init__(message, company_id=company_id)


class ReindexAlreadyActiveError(EmbeddingPipelineError):
    """Raised when a re-indexing request is submitted while one is already active.

    Only one re-indexing job may run per company at a time. Includes the
    existing job's task_id and progress for the caller.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        active_task_id: The UUID of the currently running re-indexing job.
        progress_percent: Current progress percentage of the active job.
    """

    def __init__(
        self,
        message: str = "A re-indexing job is already active for this company.",
        *,
        company_id: int | None = None,
        active_task_id: str | None = None,
        progress_percent: float | None = None,
    ) -> None:
        self.active_task_id = active_task_id
        self.progress_percent = progress_percent
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Search Errors
# ─────────────────────────────────────────────────────────────────────────────


class SearchServiceUnavailableError(EmbeddingPipelineError):
    """Raised when OpenSearch is unreachable during a search query.

    Maps to HTTP 503. The error message does not expose internal
    infrastructure details to the client.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        index_name: The index that could not be queried.
    """

    def __init__(
        self,
        message: str = "Search service is temporarily unavailable.",
        *,
        company_id: int | None = None,
        index_name: str | None = None,
    ) -> None:
        self.index_name = index_name
        super().__init__(message, company_id=company_id)
