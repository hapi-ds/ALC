"""Custom exception hierarchy for the Literature Search & Citation UI.

All exceptions raised by the literature search subsystem inherit from
``LiteratureSearchError``.  Each exception carries contextual attributes
relevant to diagnosing the failure and maps to a specific HTTP status code
in the API router layer.

References:
    - Requirements 1.9, 1.10, 3.8, 4.3, 4.7, 4.8, 5.9, 5.10, 6.5, 6.6, 7.6, 7.7
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Base Exception
# ─────────────────────────────────────────────────────────────────────────────


class LiteratureSearchError(Exception):
    """Base exception for all literature search errors.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context in which the error occurred.
    """

    def __init__(
        self,
        message: str = "A literature search error occurred.",
        *,
        company_id: int | None = None,
    ) -> None:
        self.message = message
        self.company_id = company_id
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Infrastructure / Availability Errors
# ─────────────────────────────────────────────────────────────────────────────


class SearchUnavailableError(LiteratureSearchError):
    """Raised when the search index (OpenSearch) is unreachable.

    Maps to HTTP 503 — indicates the search infrastructure is temporarily
    unavailable (connection timeout after 10s or OpenSearch returning 503).

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        retry_after_seconds: Estimated seconds until the service may recover.
    """

    def __init__(
        self,
        message: str = "Search index is temporarily unavailable.",
        *,
        company_id: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Internalization Errors
# ─────────────────────────────────────────────────────────────────────────────


class DuplicateInternalizationError(LiteratureSearchError):
    """Raised when an IngestionRecord has already been internalized.

    Maps to HTTP 409 — indicates a Document already exists for the given
    IngestionRecord within the same company.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        existing_document_id: The ID of the already-existing Document.
        ingestion_record_id: The IngestionRecord that was already internalized.
    """

    def __init__(
        self,
        message: str = "This literature record has already been internalized.",
        *,
        company_id: int | None = None,
        existing_document_id: int | None = None,
        ingestion_record_id: int | None = None,
    ) -> None:
        self.existing_document_id = existing_document_id
        self.ingestion_record_id = ingestion_record_id
        super().__init__(message, company_id=company_id)


class IngestionRecordNotFoundError(LiteratureSearchError):
    """Raised when the referenced IngestionRecord does not exist or is inaccessible.

    Maps to HTTP 404 — the IngestionRecord either does not exist or does not
    belong to the requesting company (treated as non-existent to prevent
    information leakage).

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        ingestion_record_id: The IngestionRecord ID that was not found.
    """

    def __init__(
        self,
        message: str = "Literature record not found.",
        *,
        company_id: int | None = None,
        ingestion_record_id: int | None = None,
    ) -> None:
        self.ingestion_record_id = ingestion_record_id
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Authorization Errors
# ─────────────────────────────────────────────────────────────────────────────


class InsufficientPermissionsError(LiteratureSearchError):
    """Raised when the user lacks the required role for an operation.

    Maps to HTTP 403 — the user does not have `document_admin` or
    `system_admin` role required for internalization, citation management,
    or traceability link operations.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        required_role: The minimum role required for the operation.
        user_id: The user who attempted the restricted action.
    """

    def __init__(
        self,
        message: str = "Insufficient permissions for this operation.",
        *,
        company_id: int | None = None,
        required_role: str | None = None,
        user_id: int | None = None,
    ) -> None:
        self.required_role = required_role
        self.user_id = user_id
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Capacity / Limit Errors
# ─────────────────────────────────────────────────────────────────────────────


class SavedSearchLimitExceededError(LiteratureSearchError):
    """Raised when a user exceeds the maximum number of active saved searches.

    Maps to HTTP 422 — the user has reached the 200 active saved searches
    limit per company.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        user_id: The user who hit the limit.
        current_count: The current number of active saved searches.
        max_allowed: The maximum number of saved searches allowed (200).
    """

    def __init__(
        self,
        message: str = "Saved search limit reached. Maximum 200 active saved searches allowed.",
        *,
        company_id: int | None = None,
        user_id: int | None = None,
        current_count: int | None = None,
        max_allowed: int = 200,
    ) -> None:
        self.user_id = user_id
        self.current_count = current_count
        self.max_allowed = max_allowed
        super().__init__(message, company_id=company_id)


class CollectionCapacityExceededError(LiteratureSearchError):
    """Raised when adding documents would exceed a citation collection's capacity.

    Maps to HTTP 422 — the citation collection has reached the 500 document
    maximum capacity.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        collection_id: The citation collection that is at capacity.
        current_count: The current number of documents in the collection.
        max_capacity: The maximum number of documents allowed (500).
    """

    def __init__(
        self,
        message: str = "Citation collection capacity reached. Maximum 500 documents allowed.",
        *,
        company_id: int | None = None,
        collection_id: int | None = None,
        current_count: int | None = None,
        max_capacity: int = 500,
    ) -> None:
        self.collection_id = collection_id
        self.current_count = current_count
        self.max_capacity = max_capacity
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Validation Errors
# ─────────────────────────────────────────────────────────────────────────────


class NonInternalizedDocumentError(LiteratureSearchError):
    """Raised when an operation requires an internalized document but receives one that isn't.

    Maps to HTTP 422 — the referenced Document does not have a
    `source_ingestion_record_id` set, meaning it was not created through
    the internalization process and cannot be used for citation collections
    or traceability links.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        document_id: The Document ID that is not internalized.
    """

    def __init__(
        self,
        message: str = "Only internalized literature documents can be used for this operation.",
        *,
        company_id: int | None = None,
        document_id: int | None = None,
    ) -> None:
        self.document_id = document_id
        super().__init__(message, company_id=company_id)


class InvalidTraceabilityTargetError(LiteratureSearchError):
    """Raised when a traceability link target does not exist.

    Maps to HTTP 404 — the specified requirement or test case ID does not
    exist in the Traceability_Engine within the company scope.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        target_type: The type of target ("requirement" or "test_case").
        target_id: The target ID that was not found.
    """

    def __init__(
        self,
        message: str = "Traceability target not found.",
        *,
        company_id: int | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
    ) -> None:
        self.target_type = target_type
        self.target_id = target_id
        super().__init__(message, company_id=company_id)


# ─────────────────────────────────────────────────────────────────────────────
# Export Errors
# ─────────────────────────────────────────────────────────────────────────────


class ExportReferenceNotFoundError(LiteratureSearchError):
    """Raised when a referenced search execution or saved search for export is not found.

    Maps to HTTP 404 — the search_execution_id or saved_search_id provided
    for export does not exist or does not belong to the requesting company.

    Attributes:
        message: Human-readable error description.
        company_id: ID of the company context.
        search_execution_id: The search execution ID that was not found (if applicable).
        saved_search_id: The saved search ID that was not found (if applicable).
    """

    def __init__(
        self,
        message: str = "Referenced search not found for export.",
        *,
        company_id: int | None = None,
        search_execution_id: int | None = None,
        saved_search_id: int | None = None,
    ) -> None:
        self.search_execution_id = search_execution_id
        self.saved_search_id = saved_search_id
        super().__init__(message, company_id=company_id)
