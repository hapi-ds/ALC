"""Audit logger for external literature API interactions.

Records all outbound API requests, responses, and failures in the
ExternalAPIAuditLog model for full traceability. Ensures API keys,
tokens, and credentials are never persisted in audit records.

References:
    - Requirements 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.literature.models.literature import ExternalAPIAuditLog

logger = logging.getLogger(__name__)

# Query parameter names that contain secrets and must be redacted
_SENSITIVE_PARAMS: frozenset[str] = frozenset(
    {"api_key", "key", "token", "apikey"}
)


def redact_url(url: str) -> str:
    """Remove sensitive query parameters from a URL.

    Strips api_key, key, token, and apikey query parameters to prevent
    secrets from being persisted in audit records.

    Args:
        url: The original request URL (may contain sensitive params).

    Returns:
        URL with sensitive query parameters removed entirely.
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query, keep_blank_values=True)

    # Filter out sensitive parameters (case-insensitive check)
    filtered_params: dict[str, list[str]] = {
        k: v
        for k, v in query_params.items()
        if k.lower() not in _SENSITIVE_PARAMS
    }

    # Rebuild query string
    clean_query = urlencode(filtered_params, doseq=True)
    clean_url = urlunparse(parsed._replace(query=clean_query))
    return clean_url


def sanitize_error_message(error_message: str) -> str:
    """Ensure error messages do not contain secrets.

    Truncates overly long messages and strips common credential patterns.
    This is a best-effort sanitization — callers should avoid passing
    secrets into error messages in the first place.

    Args:
        error_message: Raw error message from an adapter or HTTP client.

    Returns:
        Sanitized error message safe for audit storage.
    """
    # Truncate extremely long error messages
    max_length = 2000
    if len(error_message) > max_length:
        error_message = error_message[:max_length] + "...[truncated]"
    return error_message


class AuditLogger:
    """Records external API interactions in the ExternalAPIAuditLog model.

    All methods persist records via an async SQLAlchemy session. The logger
    guarantees that API keys, tokens, and credentials are never stored in
    request URLs or error messages.

    Attributes:
        _session_factory: Async session factory for database access.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Initialize AuditLogger with a session factory.

        Args:
            session_factory: SQLAlchemy async session factory for creating
                database sessions to persist audit records.
        """
        self._session_factory = session_factory

    async def log_request(
        self,
        *,
        source_adapter_name: str,
        request_url: str,
        user_id: int,
        company_id: int,
        query_id: str,
        request_timestamp: datetime | None = None,
    ) -> int:
        """Record an outbound API request in the audit log.

        Creates a new ExternalAPIAuditLog entry with the initial request
        data. The returned ID can be used to update the entry with response
        or failure information via log_response() or log_failure().

        Args:
            source_adapter_name: Name of the adapter making the request.
            request_url: Target URL (API keys will be redacted from query
                params before storage).
            user_id: ID of the user who initiated the search.
            company_id: ID of the company context for the request.
            query_id: UUID linking to the originating search query.
            request_timestamp: When the request was sent. Defaults to now (UTC).

        Returns:
            The ID of the created audit log entry.
        """
        if request_timestamp is None:
            request_timestamp = datetime.now(timezone.utc)

        # Redact sensitive query parameters from the URL
        safe_url = redact_url(request_url)

        audit_entry = ExternalAPIAuditLog(
            query_id=query_id,
            company_id=company_id,
            user_id=user_id,
            source_adapter_name=source_adapter_name,
            request_url=safe_url,
            request_timestamp=request_timestamp,
        )

        async with self._session_factory() as session:
            session.add(audit_entry)
            await session.commit()
            await session.refresh(audit_entry)
            entry_id = audit_entry.id

        logger.debug(
            "Audit log request recorded: id=%d, source=%s, query=%s",
            entry_id,
            source_adapter_name,
            query_id,
        )
        return entry_id

    async def log_response(
        self,
        *,
        audit_log_id: int,
        http_status_code: int,
        result_count: int,
        response_time_ms: int,
        response_timestamp: datetime | None = None,
    ) -> None:
        """Update an existing audit log entry with response data.

        Records the response metadata for a previously logged request.

        Args:
            audit_log_id: ID of the audit log entry to update.
            http_status_code: HTTP status code from the external API.
            result_count: Number of results returned in the response.
            response_time_ms: Response time in milliseconds.
            response_timestamp: When the response was received.
                Defaults to now (UTC).
        """
        if response_timestamp is None:
            response_timestamp = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            entry = await session.get(ExternalAPIAuditLog, audit_log_id)
            if entry is None:
                logger.warning(
                    "Audit log entry %d not found for response update.",
                    audit_log_id,
                )
                return

            entry.response_timestamp = response_timestamp
            entry.http_status_code = http_status_code
            entry.result_count = result_count
            entry.response_time_ms = response_time_ms
            await session.commit()

        logger.debug(
            "Audit log response recorded: id=%d, status=%d, count=%d, time=%dms",
            audit_log_id,
            http_status_code,
            result_count,
            response_time_ms,
        )

    async def log_failure(
        self,
        *,
        audit_log_id: int,
        error_type: str,
        error_message: str,
        retry_attempt: int = 0,
        response_timestamp: datetime | None = None,
    ) -> None:
        """Record failure information for an existing audit log entry.

        Updates the audit log entry with error details. The error_message
        is sanitized to ensure no secrets are persisted.

        Args:
            audit_log_id: ID of the audit log entry to update.
            error_type: Classification of the error (e.g., "timeout",
                "connection_error", "http_error", "parse_error").
            error_message: Human-readable error description. Must NOT
                contain API keys, tokens, or credentials.
            retry_attempt: Which retry attempt this represents (0 = first try).
            response_timestamp: When the failure was detected.
                Defaults to now (UTC).
        """
        if response_timestamp is None:
            response_timestamp = datetime.now(timezone.utc)

        safe_message = sanitize_error_message(error_message)

        async with self._session_factory() as session:
            entry = await session.get(ExternalAPIAuditLog, audit_log_id)
            if entry is None:
                logger.warning(
                    "Audit log entry %d not found for failure update.",
                    audit_log_id,
                )
                return

            entry.response_timestamp = response_timestamp
            entry.error_type = error_type
            entry.error_message = safe_message
            entry.retry_attempt = retry_attempt
            await session.commit()

        logger.debug(
            "Audit log failure recorded: id=%d, error_type=%s, retry=%d",
            audit_log_id,
            error_type,
            retry_attempt,
        )
