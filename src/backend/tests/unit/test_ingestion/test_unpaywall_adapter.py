"""Unit tests for UnpaywallAdapter DOI resolution.

Tests:
    - Successful DOI resolution with various OA location configurations
    - select_best_location() priority ordering with all combinations
    - HTTP 404 → DOINotFoundError, no OA → NoOpenAccessError, 429 → rate limit
    - Circuit breaker integration (open circuit rejects immediately)

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx

from alcoabase.literature.ingestion.adapters.unpaywall_adapter import (
    UnpaywallAdapter,
    UnpaywallResult,
)
from alcoabase.literature.ingestion.exceptions import (
    AdapterTimeoutError,
    DOINotFoundError,
    NoOpenAccessError,
    RateLimitedError,
)


@pytest.fixture
def mock_rate_limiter() -> AsyncMock:
    rl = AsyncMock()
    rl.check_and_consume = AsyncMock()
    return rl


@pytest.fixture
def mock_circuit_breaker() -> AsyncMock:
    cb = AsyncMock()
    cb.can_execute = AsyncMock(return_value=True)
    cb.record_success = AsyncMock()
    cb.record_failure = AsyncMock()
    return cb


@pytest.fixture
def mock_proxy_manager() -> MagicMock:
    pm = MagicMock()
    pm.get_proxy_for_source = MagicMock(return_value=None)
    return pm


@pytest.fixture
def mock_audit_logger() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def adapter(
    mock_rate_limiter: AsyncMock,
    mock_circuit_breaker: AsyncMock,
    mock_proxy_manager: MagicMock,
    mock_audit_logger: AsyncMock,
) -> UnpaywallAdapter:
    return UnpaywallAdapter(
        base_url="https://api.unpaywall.org",
        rate_limiter=mock_rate_limiter,
        circuit_breaker=mock_circuit_breaker,
        proxy_manager=mock_proxy_manager,
        audit_logger=mock_audit_logger,
        user_agent="AlcoaBase/1.0 (test)",
    )


# ─── select_best_location() Tests ────────────────────────────────────────────


class TestSelectBestLocation:
    """Test OA location priority ordering."""

    def test_empty_list_returns_none(self, adapter: UnpaywallAdapter) -> None:
        assert adapter.select_best_location([]) is None

    def test_priority_1_publisher_pdf_best(self, adapter: UnpaywallAdapter) -> None:
        """Publisher PDF with is_best=True is highest priority."""
        locations = [
            {
                "host_type": "repository",
                "url_for_pdf": "http://repo.org/paper.pdf",
                "is_best": False,
            },
            {
                "host_type": "publisher",
                "url_for_pdf": "http://pub.org/best.pdf",
                "is_best": True,
            },
        ]
        result = adapter.select_best_location(locations)
        assert result == ("http://pub.org/best.pdf", "pdf")

    def test_priority_2_repository_pdf(self, adapter: UnpaywallAdapter) -> None:
        """Repository PDF is second priority when no publisher best PDF."""
        locations = [
            {
                "host_type": "publisher",
                "url_for_landing_page": "http://pub.org/article",
                "url_for_pdf": None,
                "is_best": False,
            },
            {
                "host_type": "repository",
                "url_for_pdf": "http://repo.org/paper.pdf",
                "is_best": False,
            },
        ]
        result = adapter.select_best_location(locations)
        assert result == ("http://repo.org/paper.pdf", "pdf")

    def test_priority_3_publisher_html(self, adapter: UnpaywallAdapter) -> None:
        """Publisher HTML is third priority."""
        locations = [
            {
                "host_type": "publisher",
                "url_for_pdf": None,
                "url_for_landing_page": "http://pub.org/article",
                "is_best": False,
            },
        ]
        result = adapter.select_best_location(locations)
        assert result == ("http://pub.org/article", "html")

    def test_priority_4_any_pdf(self, adapter: UnpaywallAdapter) -> None:
        """Any PDF source is fourth priority."""
        locations = [
            {
                "host_type": "other",
                "url_for_pdf": "http://other.org/paper.pdf",
                "url_for_landing_page": None,
                "is_best": False,
            },
        ]
        result = adapter.select_best_location(locations)
        assert result == ("http://other.org/paper.pdf", "pdf")

    def test_priority_5_any_html_xml(self, adapter: UnpaywallAdapter) -> None:
        """Any HTML/XML landing page is lowest priority."""
        locations = [
            {
                "host_type": "other",
                "url_for_pdf": None,
                "url_for_landing_page": "http://other.org/article",
                "is_best": False,
            },
        ]
        result = adapter.select_best_location(locations)
        assert result == ("http://other.org/article", "html")

    def test_no_valid_urls_returns_none(self, adapter: UnpaywallAdapter) -> None:
        """If no location has any URL, returns None."""
        locations = [
            {
                "host_type": "publisher",
                "url_for_pdf": None,
                "url_for_landing_page": None,
                "is_best": True,
            },
        ]
        result = adapter.select_best_location(locations)
        assert result is None

    def test_publisher_pdf_without_is_best_not_priority_1(
        self, adapter: UnpaywallAdapter
    ) -> None:
        """Publisher PDF without is_best falls to priority 4 (any PDF)."""
        locations = [
            {
                "host_type": "publisher",
                "url_for_pdf": "http://pub.org/paper.pdf",
                "url_for_landing_page": "http://pub.org/article",
                "is_best": False,
            },
            {
                "host_type": "repository",
                "url_for_pdf": "http://repo.org/paper.pdf",
                "is_best": False,
            },
        ]
        # Repository PDF has priority 2, so it should be selected
        result = adapter.select_best_location(locations)
        assert result == ("http://repo.org/paper.pdf", "pdf")


# ─── resolve_doi() Tests ─────────────────────────────────────────────────────


class TestResolveDOI:
    """Test DOI resolution with mocked HTTP responses."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_successful_resolution(self, adapter: UnpaywallAdapter) -> None:
        """Successful DOI resolution returns UnpaywallResult with best URL."""
        respx.get("https://api.unpaywall.org/v2/10.1000/test123").mock(
            return_value=httpx.Response(
                200,
                json={
                    "doi": "10.1000/test123",
                    "is_oa": True,
                    "oa_locations": [
                        {
                            "host_type": "publisher",
                            "url_for_pdf": "http://pub.org/paper.pdf",
                            "url_for_landing_page": "http://pub.org/article",
                            "is_best": True,
                            "version": "publishedVersion",
                        }
                    ],
                },
            )
        )

        result = await adapter.resolve_doi(
            "10.1000/test123", "test@example.com", company_id=1
        )

        assert isinstance(result, UnpaywallResult)
        assert result.doi == "10.1000/test123"
        assert result.is_oa is True
        assert result.best_url == "http://pub.org/paper.pdf"
        assert result.content_type == "pdf"
        assert result.host_type == "publisher"

    @respx.mock
    @pytest.mark.asyncio
    async def test_404_raises_doi_not_found(self, adapter: UnpaywallAdapter) -> None:
        """HTTP 404 raises DOINotFoundError."""
        respx.get("https://api.unpaywall.org/v2/10.9999/notexist").mock(
            return_value=httpx.Response(404)
        )

        with pytest.raises(DOINotFoundError) as exc_info:
            await adapter.resolve_doi(
                "10.9999/notexist", "test@example.com", company_id=1
            )

        assert exc_info.value.doi == "10.9999/notexist"

    @respx.mock
    @pytest.mark.asyncio
    async def test_no_oa_raises_no_open_access(
        self, adapter: UnpaywallAdapter
    ) -> None:
        """DOI exists but no OA locations raises NoOpenAccessError."""
        respx.get("https://api.unpaywall.org/v2/10.1000/noooa").mock(
            return_value=httpx.Response(
                200,
                json={
                    "doi": "10.1000/noooa",
                    "is_oa": False,
                    "oa_locations": [],
                },
            )
        )

        with pytest.raises(NoOpenAccessError) as exc_info:
            await adapter.resolve_doi(
                "10.1000/noooa", "test@example.com", company_id=1
            )

        assert exc_info.value.doi == "10.1000/noooa"

    @respx.mock
    @pytest.mark.asyncio
    async def test_429_raises_rate_limited(self, adapter: UnpaywallAdapter) -> None:
        """HTTP 429 raises RateLimitedError with retry_after."""
        respx.get("https://api.unpaywall.org/v2/10.1000/ratelimit").mock(
            return_value=httpx.Response(
                429, headers={"Retry-After": "30"}
            )
        )

        with pytest.raises(RateLimitedError) as exc_info:
            await adapter.resolve_doi(
                "10.1000/ratelimit", "test@example.com", company_id=1
            )

        assert exc_info.value.retry_after_seconds == 30.0

    @pytest.mark.asyncio
    async def test_open_circuit_rejects_immediately(
        self, adapter: UnpaywallAdapter, mock_circuit_breaker: AsyncMock
    ) -> None:
        """When circuit breaker is open, request is blocked immediately."""
        mock_circuit_breaker.can_execute.return_value = False

        with pytest.raises(AdapterTimeoutError) as exc_info:
            await adapter.resolve_doi(
                "10.1000/blocked", "test@example.com", company_id=1
            )

        assert exc_info.value.source_adapter_name == "unpaywall"

    @respx.mock
    @pytest.mark.asyncio
    async def test_timeout_raises_adapter_timeout(
        self, adapter: UnpaywallAdapter
    ) -> None:
        """HTTP timeout raises AdapterTimeoutError."""
        respx.get("https://api.unpaywall.org/v2/10.1000/timeout").mock(
            side_effect=httpx.TimeoutException("timed out")
        )

        with pytest.raises(AdapterTimeoutError):
            await adapter.resolve_doi(
                "10.1000/timeout", "test@example.com", company_id=1
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_is_oa_true_but_no_locations_raises_no_open_access(
        self, adapter: UnpaywallAdapter
    ) -> None:
        """is_oa=True but empty oa_locations still raises NoOpenAccessError."""
        respx.get("https://api.unpaywall.org/v2/10.1000/empty").mock(
            return_value=httpx.Response(
                200,
                json={
                    "doi": "10.1000/empty",
                    "is_oa": True,
                    "oa_locations": [],
                },
            )
        )

        with pytest.raises(NoOpenAccessError):
            await adapter.resolve_doi(
                "10.1000/empty", "test@example.com", company_id=1
            )
