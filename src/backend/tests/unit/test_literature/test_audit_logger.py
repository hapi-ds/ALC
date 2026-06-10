"""Unit tests for the AuditLogger service.

Tests cover:
- URL redaction of sensitive query parameters
- Error message sanitization
- log_request() creating audit entries with redacted URLs
- log_response() updating existing entries with response data
- log_failure() recording error information without secrets
- Handling of missing audit log entries on update
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.models.literature import ExternalAPIAuditLog
from alcoabase.literature.services.audit_logger import (
    AuditLogger,
    redact_url,
    sanitize_error_message,
)


# ---------------------------------------------------------------------------
# URL Redaction Tests
# ---------------------------------------------------------------------------


class TestRedactUrl:
    """Tests for the redact_url helper function."""

    def test_removes_api_key_param(self) -> None:
        """Strip api_key query parameter from URL."""
        url = "https://api.example.com/search?query=test&api_key=secret123"
        result = redact_url(url)
        assert "secret123" not in result
        assert "api_key" not in result
        assert "query=test" in result

    def test_removes_key_param(self) -> None:
        """Strip key query parameter from URL."""
        url = "https://api.example.com/search?key=mysecret&term=hello"
        result = redact_url(url)
        assert "mysecret" not in result
        assert "key=" not in result
        assert "term=hello" in result

    def test_removes_token_param(self) -> None:
        """Strip token query parameter from URL."""
        url = "https://api.example.com/data?token=abc123&page=1"
        result = redact_url(url)
        assert "abc123" not in result
        assert "token" not in result
        assert "page=1" in result

    def test_removes_apikey_param(self) -> None:
        """Strip apikey query parameter from URL."""
        url = "https://api.example.com/fetch?apikey=xyz789&format=json"
        result = redact_url(url)
        assert "xyz789" not in result
        assert "apikey" not in result
        assert "format=json" in result

    def test_case_insensitive_removal(self) -> None:
        """Strip sensitive params regardless of case."""
        url = "https://api.example.com/search?API_KEY=secret&query=test"
        result = redact_url(url)
        assert "secret" not in result
        assert "query=test" in result

    def test_preserves_non_sensitive_params(self) -> None:
        """Keep non-sensitive query parameters intact."""
        url = "https://api.example.com/search?query=cancer&retmax=20&db=pubmed"
        result = redact_url(url)
        assert "query=cancer" in result
        assert "retmax=20" in result
        assert "db=pubmed" in result

    def test_url_without_query_params(self) -> None:
        """Return URL unchanged when no query params present."""
        url = "https://api.example.com/search"
        result = redact_url(url)
        assert result == url

    def test_url_with_only_sensitive_params(self) -> None:
        """Return URL with empty query when all params are sensitive."""
        url = "https://api.example.com/search?api_key=secret&token=abc"
        result = redact_url(url)
        assert "secret" not in result
        assert "abc" not in result
        # Should have base URL without query string
        assert "api.example.com/search" in result

    def test_preserves_path_and_fragment(self) -> None:
        """Preserve URL path and fragment while redacting params."""
        url = "https://api.example.com/v1/search?api_key=s&q=test#results"
        result = redact_url(url)
        assert "/v1/search" in result
        assert "q=test" in result
        assert "#results" in result
        assert "api_key" not in result

    def test_multiple_sensitive_params(self) -> None:
        """Remove all sensitive params when multiple are present."""
        url = "https://api.example.com/data?api_key=k1&key=k2&token=k3&apikey=k4&q=test"
        result = redact_url(url)
        assert "k1" not in result
        assert "k2" not in result
        assert "k3" not in result
        assert "k4" not in result
        assert "q=test" in result


# ---------------------------------------------------------------------------
# Error Message Sanitization Tests
# ---------------------------------------------------------------------------


class TestSanitizeErrorMessage:
    """Tests for the sanitize_error_message helper function."""

    def test_short_message_unchanged(self) -> None:
        """Return short messages without modification."""
        msg = "Connection timed out after 15s"
        assert sanitize_error_message(msg) == msg

    def test_truncates_long_messages(self) -> None:
        """Truncate messages exceeding 2000 characters."""
        msg = "x" * 3000
        result = sanitize_error_message(msg)
        assert len(result) <= 2100  # 2000 + truncation suffix
        assert result.endswith("...[truncated]")

    def test_empty_message(self) -> None:
        """Handle empty error message."""
        assert sanitize_error_message("") == ""


# ---------------------------------------------------------------------------
# AuditLogger Tests
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session with context manager support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock):
    """Create a mock session factory that mimics async_sessionmaker behavior.

    async_sessionmaker() returns a sync callable that produces an async
    context manager (the session). It is NOT a coroutine itself.
    """
    # Create a context manager mock that yields the session
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=mock_session)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)

    # The factory is a regular callable returning the context manager
    factory = MagicMock(return_value=ctx_manager)
    return factory


@pytest.fixture
def audit_logger(mock_session_factory) -> AuditLogger:
    """Create an AuditLogger instance with a mock session factory."""
    return AuditLogger(session_factory=mock_session_factory)


class TestLogRequest:
    """Tests for the log_request method."""

    @pytest.mark.asyncio
    async def test_creates_audit_entry(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Create a new ExternalAPIAuditLog entry with request data."""
        # Make refresh set the id on the object
        async def set_id(obj):
            obj.id = 42

        mock_session.refresh.side_effect = set_id

        result = await audit_logger.log_request(
            source_adapter_name="pubmed",
            request_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=cancer",
            user_id=1,
            company_id=5,
            query_id="abc-123-def",
        )

        assert result == 42
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        # Verify the audit entry was created with correct data
        added_entry = mock_session.add.call_args[0][0]
        assert isinstance(added_entry, ExternalAPIAuditLog)
        assert added_entry.source_adapter_name == "pubmed"
        assert added_entry.user_id == 1
        assert added_entry.company_id == 5
        assert added_entry.query_id == "abc-123-def"

    @pytest.mark.asyncio
    async def test_redacts_api_key_from_url(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Redact API keys from the stored request URL."""
        async def set_id(obj):
            obj.id = 1

        mock_session.refresh.side_effect = set_id

        await audit_logger.log_request(
            source_adapter_name="pubmed",
            request_url="https://api.example.com/search?api_key=SUPERSECRET&query=test",
            user_id=1,
            company_id=5,
            query_id="q-1",
        )

        added_entry = mock_session.add.call_args[0][0]
        assert "SUPERSECRET" not in added_entry.request_url
        assert "api_key" not in added_entry.request_url
        assert "query=test" in added_entry.request_url

    @pytest.mark.asyncio
    async def test_uses_provided_timestamp(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Use the provided timestamp instead of generating one."""
        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

        async def set_id(obj):
            obj.id = 1

        mock_session.refresh.side_effect = set_id

        await audit_logger.log_request(
            source_adapter_name="crossref",
            request_url="https://api.crossref.org/works?query=drug",
            user_id=2,
            company_id=3,
            query_id="q-2",
            request_timestamp=ts,
        )

        added_entry = mock_session.add.call_args[0][0]
        assert added_entry.request_timestamp == ts

    @pytest.mark.asyncio
    async def test_defaults_timestamp_to_utc_now(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Default request_timestamp to current UTC time when not provided."""
        async def set_id(obj):
            obj.id = 1

        mock_session.refresh.side_effect = set_id

        before = datetime.now(timezone.utc)
        await audit_logger.log_request(
            source_adapter_name="arxiv",
            request_url="https://export.arxiv.org/api/query?search_query=ai",
            user_id=1,
            company_id=1,
            query_id="q-3",
        )
        after = datetime.now(timezone.utc)

        added_entry = mock_session.add.call_args[0][0]
        assert before <= added_entry.request_timestamp <= after


class TestLogResponse:
    """Tests for the log_response method."""

    @pytest.mark.asyncio
    async def test_updates_existing_entry(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Update an existing audit entry with response data."""
        existing_entry = ExternalAPIAuditLog(
            id=10,
            query_id="q-1",
            company_id=1,
            user_id=1,
            source_adapter_name="pubmed",
            request_url="https://api.example.com/search",
            request_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_session.get.return_value = existing_entry

        await audit_logger.log_response(
            audit_log_id=10,
            http_status_code=200,
            result_count=25,
            response_time_ms=340,
        )

        assert existing_entry.http_status_code == 200
        assert existing_entry.result_count == 25
        assert existing_entry.response_time_ms == 340
        assert existing_entry.response_timestamp is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_provided_response_timestamp(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Use the provided response timestamp."""
        existing_entry = ExternalAPIAuditLog(
            id=11,
            query_id="q-2",
            company_id=1,
            user_id=1,
            source_adapter_name="crossref",
            request_url="https://api.crossref.org/works",
            request_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_session.get.return_value = existing_entry
        ts = datetime(2025, 6, 15, 12, 0, 5, tzinfo=timezone.utc)

        await audit_logger.log_response(
            audit_log_id=11,
            http_status_code=200,
            result_count=10,
            response_time_ms=150,
            response_timestamp=ts,
        )

        assert existing_entry.response_timestamp == ts

    @pytest.mark.asyncio
    async def test_handles_missing_entry(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Gracefully handle when audit entry ID does not exist."""
        mock_session.get.return_value = None

        # Should not raise
        await audit_logger.log_response(
            audit_log_id=999,
            http_status_code=200,
            result_count=0,
            response_time_ms=100,
        )

        mock_session.commit.assert_not_called()


class TestLogFailure:
    """Tests for the log_failure method."""

    @pytest.mark.asyncio
    async def test_records_failure_information(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Record error type and message on an existing entry."""
        existing_entry = ExternalAPIAuditLog(
            id=20,
            query_id="q-fail",
            company_id=2,
            user_id=3,
            source_adapter_name="arxiv",
            request_url="https://export.arxiv.org/api/query",
            request_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_session.get.return_value = existing_entry

        await audit_logger.log_failure(
            audit_log_id=20,
            error_type="timeout",
            error_message="Connection timed out after 15s",
            retry_attempt=2,
        )

        assert existing_entry.error_type == "timeout"
        assert existing_entry.error_message == "Connection timed out after 15s"
        assert existing_entry.retry_attempt == 2
        assert existing_entry.response_timestamp is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sanitizes_long_error_message(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Truncate excessively long error messages."""
        existing_entry = ExternalAPIAuditLog(
            id=21,
            query_id="q-long",
            company_id=1,
            user_id=1,
            source_adapter_name="pubmed",
            request_url="https://api.example.com",
            request_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_session.get.return_value = existing_entry

        long_msg = "x" * 3000
        await audit_logger.log_failure(
            audit_log_id=21,
            error_type="parse_error",
            error_message=long_msg,
        )

        assert len(existing_entry.error_message) <= 2100
        assert existing_entry.error_message.endswith("...[truncated]")

    @pytest.mark.asyncio
    async def test_handles_missing_entry(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Gracefully handle when audit entry ID does not exist."""
        mock_session.get.return_value = None

        await audit_logger.log_failure(
            audit_log_id=999,
            error_type="connection_error",
            error_message="Host unreachable",
        )

        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_defaults_retry_attempt_to_zero(
        self, audit_logger: AuditLogger, mock_session: AsyncMock
    ) -> None:
        """Default retry_attempt to 0 when not provided."""
        existing_entry = ExternalAPIAuditLog(
            id=22,
            query_id="q-retry",
            company_id=1,
            user_id=1,
            source_adapter_name="crossref",
            request_url="https://api.crossref.org",
            request_timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        mock_session.get.return_value = existing_entry

        await audit_logger.log_failure(
            audit_log_id=22,
            error_type="http_error",
            error_message="HTTP 500 Internal Server Error",
        )

        assert existing_entry.retry_attempt == 0
