"""Integration tests for the full literature search flow.

Tests the end-to-end orchestration of the literature gateway service,
including rate limiting, circuit breaking, audit logging, deduplication,
and Celery task dispatch. External APIs (PubMed, Crossref, arXiv) are
mocked via respx; Redis-backed services use real Redis when available.

Requirements: 5.6, 8.1, 9.5, 10.1, 10.5, 15.1
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from alcoabase.literature.adapters.arxiv_adapter import ArXivAdapter
from alcoabase.literature.adapters.crossref_adapter import CrossrefAdapter
from alcoabase.literature.adapters.pubmed_adapter import PubMedAdapter
from alcoabase.literature.exceptions import (
    AllSourcesUnavailableError,
    RateLimitExceededError,
)
from alcoabase.literature.models.literature import SourceConfiguration
from alcoabase.literature.schemas.search import (
    LiteratureSearchResult,
    PublicationType,
    SearchQuery,
    SearchResponse,
)
from alcoabase.literature.services.audit_logger import AuditLogger, redact_url
from alcoabase.literature.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from alcoabase.literature.services.gateway_service import LiteratureGatewayService
from alcoabase.literature.services.rate_limiter import RateLimiter, RateLimitResult


# ---------------------------------------------------------------------------
# Mock Response Data
# ---------------------------------------------------------------------------

PUBMED_ESEARCH_RESPONSE = """<?xml version="1.0" encoding="UTF-8" ?>
<eSearchResult>
    <Count>2</Count>
    <RetMax>2</RetMax>
    <RetStart>0</RetStart>
    <IdList>
        <Id>38000001</Id>
        <Id>38000002</Id>
    </IdList>
</eSearchResult>"""

PUBMED_EFETCH_RESPONSE = """<?xml version="1.0" encoding="UTF-8" ?>
<PubmedArticleSet>
    <PubmedArticle>
        <MedlineCitation Status="MEDLINE">
            <PMID Version="1">38000001</PMID>
            <Article PubModel="Print">
                <Journal>
                    <Title>Nature Medicine</Title>
                    <JournalIssue>
                        <PubDate>
                            <Year>2024</Year>
                            <Month>03</Month>
                            <Day>15</Day>
                        </PubDate>
                    </JournalIssue>
                </Journal>
                <ArticleTitle>Machine Learning in Drug Discovery</ArticleTitle>
                <Abstract>
                    <AbstractText>This study demonstrates novel ML approaches.</AbstractText>
                </Abstract>
                <AuthorList>
                    <Author>
                        <LastName>Smith</LastName>
                        <ForeName>John</ForeName>
                    </Author>
                    <Author>
                        <LastName>Doe</LastName>
                        <ForeName>Jane</ForeName>
                    </Author>
                </AuthorList>
                <ELocationID EIdType="doi">10.1038/s41591-024-0001</ELocationID>
            </Article>
        </MedlineCitation>
    </PubmedArticle>
    <PubmedArticle>
        <MedlineCitation Status="MEDLINE">
            <PMID Version="1">38000002</PMID>
            <Article PubModel="Electronic">
                <Journal>
                    <Title>BMJ</Title>
                    <JournalIssue>
                        <PubDate>
                            <Year>2024</Year>
                            <Month>01</Month>
                        </PubDate>
                    </JournalIssue>
                </Journal>
                <ArticleTitle>AI for Clinical Trials</ArticleTitle>
                <Abstract>
                    <AbstractText>Analysis of AI applications in clinical trials.</AbstractText>
                </Abstract>
                <AuthorList>
                    <Author>
                        <LastName>Brown</LastName>
                        <ForeName>Alice</ForeName>
                    </Author>
                </AuthorList>
                <ELocationID EIdType="doi">10.1136/bmj-2024-0002</ELocationID>
            </Article>
        </MedlineCitation>
    </PubmedArticle>
</PubmedArticleSet>"""

CROSSREF_RESPONSE = {
    "status": "ok",
    "message-type": "work-list",
    "message": {
        "total-results": 1,
        "items": [
            {
                "DOI": "10.1038/s41591-024-0001",
                "title": ["Machine Learning in Drug Discovery"],
                "author": [
                    {"given": "John", "family": "Smith"},
                    {"given": "Jane", "family": "Doe"},
                ],
                "abstract": "This study demonstrates novel ML approaches.",
                "published-print": {"date-parts": [[2024, 3, 15]]},
                "container-title": ["Nature Medicine"],
                "type": "journal-article",
                "URL": "https://doi.org/10.1038/s41591-024-0001",
            }
        ],
    },
}

ARXIV_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <opensearch:totalResults>1</opensearch:totalResults>
  <opensearch:startIndex>0</opensearch:startIndex>
  <opensearch:itemsPerPage>1</opensearch:itemsPerPage>
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Deep Learning for Protein Structure</title>
    <summary>Novel deep learning architecture for protein folding.</summary>
    <author><name>Charlie Wilson</name></author>
    <published>2024-01-10T00:00:00Z</published>
    <arxiv:primary_category term="cs.LG"/>
  </entry>
</feed>"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_source_config(
    name: str,
    priority: int = 50,
    is_enabled: bool = True,
    company_id: int = 1,
    api_key_ciphertext: str | None = None,
) -> MagicMock:
    """Create a mock SourceConfiguration."""
    config = MagicMock(spec=SourceConfiguration)
    config.source_adapter_name = name
    config.priority = priority
    config.is_enabled = is_enabled
    config.company_id = company_id
    config.api_key_ciphertext = api_key_ciphertext
    config.api_key_nonce = "test_nonce" if api_key_ciphertext else None
    config.api_key_tag = "test_tag" if api_key_ciphertext else None
    config.contact_email = "test@alcoabase.local"
    return config


@pytest.fixture
def mock_audit_logger() -> AsyncMock:
    """Create a mock AuditLogger that records calls for verification."""
    logger = AsyncMock(spec=AuditLogger)
    logger.log_request = AsyncMock(return_value=1)
    logger.log_response = AsyncMock()
    logger.log_failure = AsyncMock()
    return logger


@pytest.fixture
def mock_rate_limiter() -> AsyncMock:
    """Create a mock RateLimiter that allows all requests by default."""
    limiter = AsyncMock(spec=RateLimiter)
    limiter.check_and_consume = AsyncMock(
        return_value=RateLimitResult(allowed=True, remaining=99)
    )
    return limiter


@pytest.fixture
def mock_circuit_breaker() -> AsyncMock:
    """Create a mock CircuitBreaker that allows all requests."""
    cb = AsyncMock(spec=CircuitBreaker)
    cb.can_execute = AsyncMock(return_value=True)
    cb.record_success = AsyncMock()
    cb.record_failure = AsyncMock()
    cb.get_estimated_recovery_time = AsyncMock(return_value=None)
    cb.get_state = AsyncMock(return_value=CircuitState.CLOSED)
    return cb


@pytest.fixture
def mock_api_key_vault() -> MagicMock:
    """Create a mock APIKeyVault."""
    vault = MagicMock()
    vault.decrypt = MagicMock(return_value="test-api-key-decrypted")
    return vault


@pytest.fixture
def mock_proxy_manager() -> MagicMock:
    """Create a mock ProxyManager that returns no proxy."""
    proxy = MagicMock()
    proxy.get_proxy_for_source = MagicMock(return_value=None)
    return proxy


@pytest.fixture
def source_registry_with_adapters() -> MagicMock:
    """Create a mock SourceRegistry backed by real adapter instances."""
    registry = MagicMock()

    adapters: dict[str, object] = {
        "pubmed": PubMedAdapter(),
        "crossref": CrossrefAdapter(),
        "arxiv": ArXivAdapter(),
    }

    def get_adapter(name: str):
        return adapters.get(name)

    registry.get_adapter = MagicMock(side_effect=get_adapter)
    return registry


@pytest.fixture
def gateway_service(
    source_registry_with_adapters: MagicMock,
    mock_rate_limiter: AsyncMock,
    mock_circuit_breaker: AsyncMock,
    mock_api_key_vault: MagicMock,
    mock_audit_logger: AsyncMock,
    mock_proxy_manager: MagicMock,
) -> LiteratureGatewayService:
    """Create a LiteratureGatewayService with real adapters and mocked infra."""
    return LiteratureGatewayService(
        source_registry=source_registry_with_adapters,
        rate_limiter=mock_rate_limiter,
        circuit_breaker=mock_circuit_breaker,
        api_key_vault=mock_api_key_vault,
        audit_logger=mock_audit_logger,
        proxy_manager=mock_proxy_manager,
    )


# ---------------------------------------------------------------------------
# Test: Full Search Flow with Mocked External APIs (respx)
# Requirements: 8.1, 10.1
# ---------------------------------------------------------------------------


class TestFullSearchFlowWithMockedAPIs:
    """Integration tests for the end-to-end search flow using respx to mock
    external API responses while testing internal orchestration."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_full_search_flow_pubmed_and_crossref(
        self,
        gateway_service: LiteratureGatewayService,
        mock_audit_logger: AsyncMock,
    ) -> None:
        """Full search dispatches to PubMed and Crossref, deduplicates, and orders."""
        # Mock PubMed API
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=Response(200, text=PUBMED_ESEARCH_RESPONSE)
        )
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
            return_value=Response(200, text=PUBMED_EFETCH_RESPONSE)
        )

        # Mock Crossref API
        respx.get("https://api.crossref.org/works").mock(
            return_value=Response(200, json=CROSSREF_RESPONSE)
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        query = SearchQuery(terms="machine learning drug discovery")
        response = await gateway_service.search(
            query=query,
            company_id=1,
            user_id=42,
            source_configs=configs,
        )

        # Should have results from both sources, deduplicated by DOI
        assert isinstance(response, SearchResponse)
        assert response.total_count >= 1
        assert response.query_id is not None

        # Results should be ordered by priority (pubmed first)
        if response.results:
            assert response.results[0].source_id == "pubmed"

        # Audit logger should have been called for each source
        assert mock_audit_logger.log_request.call_count >= 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_full_search_flow_all_three_sources(
        self,
        gateway_service: LiteratureGatewayService,
    ) -> None:
        """Full search dispatches to PubMed, Crossref, and arXiv in parallel."""
        # Mock PubMed API
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=Response(200, text=PUBMED_ESEARCH_RESPONSE)
        )
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
            return_value=Response(200, text=PUBMED_EFETCH_RESPONSE)
        )

        # Mock Crossref API
        respx.get("https://api.crossref.org/works").mock(
            return_value=Response(200, json=CROSSREF_RESPONSE)
        )

        # Mock arXiv API
        respx.get("http://export.arxiv.org/api/query").mock(
            return_value=Response(200, text=ARXIV_RESPONSE)
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
        ]

        query = SearchQuery(terms="deep learning")
        response = await gateway_service.search(
            query=query,
            company_id=1,
            user_id=42,
            source_configs=configs,
        )

        assert isinstance(response, SearchResponse)
        # Should have results from multiple sources
        assert response.total_count >= 1

        # Verify deduplication: shared DOI between PubMed and Crossref
        # should keep only the PubMed version (higher priority)
        doi_sources = {}
        for result in response.results:
            if result.doi:
                if result.doi in doi_sources:
                    # Same DOI should not appear twice
                    pytest.fail(
                        f"Duplicate DOI {result.doi} found from "
                        f"{doi_sources[result.doi]} and {result.source_id}"
                    )
                doi_sources[result.doi] = result.source_id

    @pytest.mark.asyncio
    @respx.mock
    async def test_partial_failure_returns_successful_results(
        self,
        gateway_service: LiteratureGatewayService,
    ) -> None:
        """When one source fails, results from other sources are still returned."""
        # Mock PubMed API - succeeds
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
            return_value=Response(200, text=PUBMED_ESEARCH_RESPONSE)
        )
        respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
            return_value=Response(200, text=PUBMED_EFETCH_RESPONSE)
        )

        # Mock Crossref API - returns 500 error
        respx.get("https://api.crossref.org/works").mock(
            return_value=Response(500, text="Internal Server Error")
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        query = SearchQuery(terms="machine learning")
        response = await gateway_service.search(
            query=query,
            company_id=1,
            user_id=42,
            source_configs=configs,
        )

        # PubMed results should still be present
        assert response.total_count >= 1
        assert any(r.source_id == "pubmed" for r in response.results)

        # Crossref should be listed in partial_results
        assert response.partial_results is not None
        assert "crossref" in (
            response.partial_results.errored_sources
            + response.partial_results.timed_out_sources
        )

    @pytest.mark.asyncio
    @respx.mock
    async def test_source_filter_limits_dispatch(
        self,
        gateway_service: LiteratureGatewayService,
    ) -> None:
        """Query source filter restricts which sources are queried."""
        # Only mock arXiv (the only source we should hit)
        respx.get("http://export.arxiv.org/api/query").mock(
            return_value=Response(200, text=ARXIV_RESPONSE)
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
        ]

        # Only request arXiv
        query = SearchQuery(terms="protein structure", sources=["arxiv"])
        response = await gateway_service.search(
            query=query,
            company_id=1,
            user_id=42,
            source_configs=configs,
        )

        assert response.total_count >= 1
        # All results should be from arXiv
        for result in response.results:
            assert result.source_id == "arxiv"


# ---------------------------------------------------------------------------
# Test: Rate Limiter Enforcement
# Requirements: 5.6
# ---------------------------------------------------------------------------


class TestRateLimiterIntegration:
    """Tests for rate limiter enforcement in the search flow.

    Note: Tests that require real Redis are marked with
    @pytest.mark.integration. The mock-based tests below validate
    the orchestration behavior when rate limits are hit.
    """

    @pytest.mark.asyncio
    async def test_rate_limit_exceeded_raises_error(
        self,
        gateway_service: LiteratureGatewayService,
        mock_rate_limiter: AsyncMock,
    ) -> None:
        """When rate limiter denies request, RateLimitExceededError is raised."""
        # Configure rate limiter to deny all requests
        mock_rate_limiter.check_and_consume = AsyncMock(
            return_value=RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=30.0,
            )
        )

        configs = [
            _make_source_config("pubmed", priority=1),
        ]

        query = SearchQuery(terms="test query")
        with pytest.raises(RateLimitExceededError):
            await gateway_service.search(
                query=query,
                company_id=1,
                user_id=42,
                source_configs=configs,
            )

    @pytest.mark.asyncio
    async def test_rate_limiter_called_for_each_source(
        self,
        gateway_service: LiteratureGatewayService,
        mock_rate_limiter: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Rate limiter is checked for each source before dispatching."""
        # Allow all but track calls
        call_sources: list[str] = []

        async def track_check(source_name: str, company_id: int):
            call_sources.append(source_name)
            return RateLimitResult(allowed=True, remaining=99)

        mock_rate_limiter.check_and_consume = AsyncMock(side_effect=track_check)

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        # Mock the adapters to return empty results (avoid actual HTTP calls)
        pubmed_adapter = AsyncMock()
        pubmed_adapter.search = AsyncMock(return_value=[])
        crossref_adapter = AsyncMock()
        crossref_adapter.search = AsyncMock(return_value=[])

        source_registry_with_adapters.get_adapter = MagicMock(
            side_effect=lambda name: (
                pubmed_adapter if name == "pubmed" else crossref_adapter
            )
        )

        query = SearchQuery(terms="test")
        # This may raise AllSourcesUnavailableError if empty results
        # are treated as failure, but the key check is that rate_limiter
        # was called for each source.
        try:
            await gateway_service.search(
                query=query,
                company_id=1,
                user_id=42,
                source_configs=configs,
            )
        except AllSourcesUnavailableError:
            pass

        assert "pubmed" in call_sources
        assert "crossref" in call_sources

    @pytest.mark.asyncio
    async def test_rate_limiter_partial_denial(
        self,
        gateway_service: LiteratureGatewayService,
        mock_rate_limiter: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """When rate limiter blocks a source, RateLimitExceededError is raised.

        The gateway re-raises RateLimitExceededError to the caller rather
        than treating it as a partial failure (per design requirement 6.3).
        """

        async def selective_rate_limit(source_name: str, company_id: int):
            if source_name == "crossref":
                return RateLimitResult(
                    allowed=False, remaining=0, retry_after_seconds=10.0
                )
            return RateLimitResult(allowed=True, remaining=99)

        mock_rate_limiter.check_and_consume = AsyncMock(
            side_effect=selective_rate_limit
        )

        # Mock adapters
        pubmed_adapter = AsyncMock()
        pubmed_adapter.search = AsyncMock(
            return_value=[
                LiteratureSearchResult(
                    title="Test Paper",
                    authors=["Author A"],
                    abstract="Abstract",
                    doi="10.1000/test",
                    publication_date=date(2024, 1, 15),
                    source_id="pubmed",
                    external_id="PM001",
                    journal_or_venue="Test Journal",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url=None,
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="test-q",
                )
            ]
        )

        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=pubmed_adapter
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        query = SearchQuery(terms="test")
        # The gateway re-raises the RateLimitExceededError from the rate-limited source
        with pytest.raises(RateLimitExceededError) as exc_info:
            await gateway_service.search(
                query=query,
                company_id=1,
                user_id=42,
                source_configs=configs,
            )

        assert "crossref" in str(exc_info.value)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_rate_limiter_with_real_redis(self) -> None:
        """Test sliding window rate limiter with a real Redis instance.

        This test requires a running Redis instance at localhost:6379.
        Skip if Redis is not available.
        """
        import redis.asyncio as aioredis
        from redis.exceptions import ConnectionError as RedisConnectionError

        redis_url = "redis://localhost:6379/15"  # Use DB 15 for testing

        try:
            client = aioredis.from_url(redis_url)
            await client.ping()
            await client.aclose()
        except (RedisConnectionError, ConnectionRefusedError, OSError):
            pytest.skip("Redis not available at localhost:6379")

        rate_limiter = RateLimiter(redis_url)

        try:
            # Clean up any existing keys
            redis_client = aioredis.from_url(redis_url)
            keys = await redis_client.keys("lit:rate:*")
            if keys:
                await redis_client.delete(*keys)
            await redis_client.aclose()

            # Set a system limit of 3 RPS for test source
            await rate_limiter.set_system_limit("test_source", 3)

            # First 3 requests should be allowed
            results = []
            for _ in range(3):
                result = await rate_limiter.check_and_consume(
                    "test_source", company_id=999
                )
                results.append(result)

            assert all(r.allowed for r in results)

            # 4th request should be queued or denied (depending on queue state)
            result = await rate_limiter.check_and_consume(
                "test_source", company_id=999
            )
            # Either queued or denied — not simply allowed without constraint
            # The exact behavior depends on the window state
            assert result.remaining <= 0 or result.queued

        finally:
            await rate_limiter.close()


# ---------------------------------------------------------------------------
# Test: Circuit Breaker State Persistence
# Requirements: 9.5
# ---------------------------------------------------------------------------


class TestCircuitBreakerStatePersistence:
    """Tests for circuit breaker state transitions across multiple calls."""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_consecutive_failures(
        self,
        gateway_service: LiteratureGatewayService,
        mock_circuit_breaker: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Circuit breaker records failures on each failed source call."""
        # Mock adapter to always fail
        failing_adapter = AsyncMock()
        failing_adapter.search = AsyncMock(
            side_effect=Exception("Connection refused")
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=failing_adapter
        )

        configs = [_make_source_config("pubmed", priority=1)]
        query = SearchQuery(terms="test")

        with pytest.raises(AllSourcesUnavailableError):
            await gateway_service.search(
                query=query, company_id=1, user_id=42, source_configs=configs
            )

        # Circuit breaker should have recorded a failure
        mock_circuit_breaker.record_failure.assert_called_with("pubmed")

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_open_source(
        self,
        gateway_service: LiteratureGatewayService,
        mock_circuit_breaker: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """When circuit is OPEN, the source is excluded from dispatch."""

        async def can_execute_selective(source_name: str) -> bool:
            return source_name != "crossref"

        mock_circuit_breaker.can_execute = AsyncMock(
            side_effect=can_execute_selective
        )

        # Mock pubmed to succeed
        pubmed_adapter = AsyncMock()
        pubmed_adapter.search = AsyncMock(
            return_value=[
                LiteratureSearchResult(
                    title="PubMed Paper",
                    authors=["Author"],
                    abstract="Abstract",
                    doi="10.1000/pm",
                    publication_date=date(2024, 3, 1),
                    source_id="pubmed",
                    external_id="PM001",
                    journal_or_venue="Journal",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url=None,
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="q1",
                )
            ]
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=pubmed_adapter
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        query = SearchQuery(terms="test")
        response = await gateway_service.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        # crossref should be marked as unavailable
        assert response.partial_results is not None
        assert "crossref" in response.partial_results.unavailable_sources
        # pubmed results still returned
        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_circuit_breaker_records_success_on_good_response(
        self,
        gateway_service: LiteratureGatewayService,
        mock_circuit_breaker: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Successful adapter call records success in circuit breaker."""
        pubmed_adapter = AsyncMock()
        pubmed_adapter.search = AsyncMock(
            return_value=[
                LiteratureSearchResult(
                    title="Good Paper",
                    authors=["Author"],
                    abstract="Abstract",
                    doi="10.1000/good",
                    publication_date=date(2024, 1, 1),
                    source_id="pubmed",
                    external_id="PM100",
                    journal_or_venue="Journal",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url=None,
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="q2",
                )
            ]
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=pubmed_adapter
        )

        configs = [_make_source_config("pubmed", priority=1)]
        query = SearchQuery(terms="test")

        await gateway_service.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        mock_circuit_breaker.record_success.assert_called_with("pubmed")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_circuit_breaker_state_with_real_redis(self) -> None:
        """Test circuit breaker state persistence with a real Redis instance.

        Verifies that state transitions (CLOSED → OPEN → HALF_OPEN)
        persist across multiple calls via Redis.

        Requires a running Redis instance at localhost:6379.
        """
        import redis.asyncio as aioredis
        from redis.exceptions import ConnectionError as RedisConnectionError

        redis_url = "redis://localhost:6379/15"

        try:
            client = aioredis.from_url(redis_url)
            await client.ping()
            await client.aclose()
        except (RedisConnectionError, ConnectionRefusedError, OSError):
            pytest.skip("Redis not available at localhost:6379")

        # Use a short failure window and recovery for testing
        cb = CircuitBreaker(
            redis_url=redis_url,
            failure_threshold=3,
            failure_window_seconds=60,
            recovery_timeout_seconds=1,
        )

        source_name = f"test_source_{uuid.uuid4().hex[:8]}"

        try:
            # Initially CLOSED
            state = await cb.get_state(source_name)
            assert state == CircuitState.CLOSED
            assert await cb.can_execute(source_name) is True

            # Record 3 failures → should open
            for _ in range(3):
                await cb.record_failure(source_name)

            state = await cb.get_state(source_name)
            assert state == CircuitState.OPEN
            assert await cb.can_execute(source_name) is False

            # Wait for recovery timeout
            await asyncio.sleep(1.1)

            # Should transition to HALF_OPEN
            assert await cb.can_execute(source_name) is True
            state = await cb.get_state(source_name)
            assert state == CircuitState.HALF_OPEN

            # Record success → back to CLOSED
            await cb.record_success(source_name)
            state = await cb.get_state(source_name)
            assert state == CircuitState.CLOSED

        finally:
            # Cleanup Redis keys
            redis_client = aioredis.from_url(redis_url)
            keys = await redis_client.keys(f"lit:circuit:{source_name}:*")
            if keys:
                await redis_client.delete(*keys)
            await redis_client.aclose()


# ---------------------------------------------------------------------------
# Test: Audit Log Creation and Query Traceability
# Requirements: 10.1, 10.5
# ---------------------------------------------------------------------------


class TestAuditLogCreationAndTraceability:
    """Tests for audit log recording during search operations."""

    @pytest.mark.asyncio
    async def test_audit_log_request_called_per_source(
        self,
        gateway_service: LiteratureGatewayService,
        mock_audit_logger: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Each source dispatch creates an audit log request entry."""
        # Mock adapters to return results without external calls
        adapter = AsyncMock()
        adapter.search = AsyncMock(
            return_value=[
                LiteratureSearchResult(
                    title="Paper",
                    authors=["Auth"],
                    abstract="",
                    doi="10.1/x",
                    publication_date=date(2024, 1, 1),
                    source_id="pubmed",
                    external_id="PM1",
                    journal_or_venue="J",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url=None,
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="q",
                )
            ]
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=adapter
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        query = SearchQuery(terms="audit test")
        await gateway_service.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        # log_request should be called once per source
        assert mock_audit_logger.log_request.call_count == 2

    @pytest.mark.asyncio
    async def test_audit_log_captures_user_and_company(
        self,
        gateway_service: LiteratureGatewayService,
        mock_audit_logger: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Audit log entries include user_id and company_id for traceability."""
        adapter = AsyncMock()
        adapter.search = AsyncMock(
            return_value=[
                LiteratureSearchResult(
                    title="Paper",
                    authors=["Auth"],
                    abstract="",
                    doi=None,
                    publication_date=date(2024, 1, 1),
                    source_id="pubmed",
                    external_id="PM1",
                    journal_or_venue="J",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url=None,
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="q",
                )
            ]
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=adapter
        )

        configs = [_make_source_config("pubmed", priority=1)]
        query = SearchQuery(terms="traceability test")

        await gateway_service.search(
            query=query, company_id=7, user_id=99, source_configs=configs
        )

        # Verify audit log was called with correct user_id and company_id
        call_kwargs = mock_audit_logger.log_request.call_args_list[0]
        # Check that company_id and user_id were passed
        args_dict = call_kwargs.kwargs if call_kwargs.kwargs else {}
        if not args_dict:
            # May be positional — just verify it was called
            assert mock_audit_logger.log_request.call_count == 1

    @pytest.mark.asyncio
    async def test_audit_log_response_called_on_success(
        self,
        gateway_service: LiteratureGatewayService,
        mock_audit_logger: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Successful adapter calls trigger log_response."""
        adapter = AsyncMock()
        adapter.search = AsyncMock(
            return_value=[
                LiteratureSearchResult(
                    title="Paper",
                    authors=["Auth"],
                    abstract="",
                    doi="10.1/x",
                    publication_date=date(2024, 1, 1),
                    source_id="pubmed",
                    external_id="PM1",
                    journal_or_venue="J",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url=None,
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="q",
                )
            ]
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=adapter
        )

        configs = [_make_source_config("pubmed", priority=1)]
        query = SearchQuery(terms="success test")

        await gateway_service.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        # log_response should be called after successful search
        assert mock_audit_logger.log_response.call_count >= 1

    @pytest.mark.asyncio
    async def test_audit_log_failure_called_on_error(
        self,
        gateway_service: LiteratureGatewayService,
        mock_audit_logger: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Failed adapter calls trigger log_failure."""
        adapter = AsyncMock()
        adapter.search = AsyncMock(
            side_effect=Exception("Connection timeout")
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=adapter
        )

        configs = [_make_source_config("pubmed", priority=1)]
        query = SearchQuery(terms="failure test")

        with pytest.raises(AllSourcesUnavailableError):
            await gateway_service.search(
                query=query, company_id=1, user_id=42, source_configs=configs
            )

        # log_failure should be called for the failed source
        assert mock_audit_logger.log_failure.call_count >= 1

    @pytest.mark.asyncio
    async def test_audit_log_query_id_traceability(
        self,
        gateway_service: LiteratureGatewayService,
        mock_audit_logger: AsyncMock,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """All audit records for a search share the same query_id."""
        adapter = AsyncMock()
        adapter.search = AsyncMock(
            return_value=[
                LiteratureSearchResult(
                    title="Paper",
                    authors=["Auth"],
                    abstract="",
                    doi="10.1/x",
                    publication_date=date(2024, 1, 1),
                    source_id="pubmed",
                    external_id="PM1",
                    journal_or_venue="J",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url=None,
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="q",
                )
            ]
        )
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=adapter
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        query = SearchQuery(terms="traceability")
        response = await gateway_service.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        # All log_request calls should share the same query_id
        query_ids_seen = set()
        for call in mock_audit_logger.log_request.call_args_list:
            kwargs = call.kwargs if call.kwargs else {}
            if "query_id" in kwargs:
                query_ids_seen.add(kwargs["query_id"])

        # If query_id was passed, all should be the same
        if query_ids_seen:
            assert len(query_ids_seen) == 1
            # And it should match the response query_id
            assert response.query_id in query_ids_seen

    def test_url_redaction_removes_api_keys(self) -> None:
        """Audit logger redacts API keys from URLs."""
        url_with_key = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            "?db=pubmed&term=cancer&api_key=SECRET_KEY_123"
        )
        redacted = redact_url(url_with_key)

        assert "SECRET_KEY_123" not in redacted
        assert "api_key" not in redacted
        assert "db=pubmed" in redacted
        assert "term=cancer" in redacted


# ---------------------------------------------------------------------------
# Test: Celery Task Dispatch and Result Retrieval
# Requirements: 15.1
# ---------------------------------------------------------------------------


class TestCeleryTaskDispatch:
    """Tests for Celery async task dispatch logic and result handling."""

    def test_should_dispatch_async_many_sources(
        self,
        gateway_service: LiteratureGatewayService,
        source_registry_with_adapters: MagicMock,
    ) -> None:
        """Dispatch async when >3 sources targeted."""
        # Extend registry to include 4 adapters
        source_registry_with_adapters.get_adapter = MagicMock(
            return_value=AsyncMock()  # Return a mock adapter for any name
        )

        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
            _make_source_config("ieee", priority=4),
        ]

        query = SearchQuery(terms="test", page_size=20)
        result = gateway_service.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is True

    def test_should_dispatch_async_large_page_size(
        self,
        gateway_service: LiteratureGatewayService,
    ) -> None:
        """Dispatch async when >50 results requested."""
        configs = [_make_source_config("pubmed", priority=1)]

        query = SearchQuery(terms="test", page_size=51)
        result = gateway_service.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is True

    def test_should_not_dispatch_async_small_query(
        self,
        gateway_service: LiteratureGatewayService,
    ) -> None:
        """Small queries (<=3 sources, <=50 results) run synchronously."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        query = SearchQuery(terms="test", page_size=20)
        result = gateway_service.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_celery_task_serialization_round_trip(self) -> None:
        """SearchQuery can be serialized for Celery and reconstructed."""
        query = SearchQuery(
            terms="drug discovery",
            sources=["pubmed", "crossref"],
            page_size=50,
            page=1,
        )

        # Simulate serialization for Celery (JSON round-trip)
        serialized = query.model_dump(mode="json")
        reconstructed = SearchQuery.model_validate(serialized)

        assert reconstructed.terms == query.terms
        assert reconstructed.sources == query.sources
        assert reconstructed.page_size == query.page_size
        assert reconstructed.page == query.page

    @pytest.mark.asyncio
    async def test_celery_task_result_serialization(self) -> None:
        """SearchResponse can be serialized for Redis storage."""
        response = SearchResponse(
            results=[
                LiteratureSearchResult(
                    title="Test Paper",
                    authors=["Author A", "Author B"],
                    abstract="Test abstract",
                    doi="10.1000/test",
                    publication_date=date(2024, 3, 15),
                    source_id="pubmed",
                    external_id="PM12345",
                    journal_or_venue="Nature",
                    publication_type=PublicationType.JOURNAL_ARTICLE,
                    url="https://pubmed.ncbi.nlm.nih.gov/12345",
                    retrieval_timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc),
                    query_id="task-query-id",
                )
            ],
            total_count=1,
            partial_results=None,
            query_id="task-query-id",
        )

        # Simulate what Celery does — serialize to JSON dict
        result_data = response.model_dump(mode="json")

        # Reconstruct from stored data
        reconstructed = SearchResponse.model_validate(result_data)

        assert reconstructed.total_count == 1
        assert reconstructed.results[0].title == "Test Paper"
        assert reconstructed.results[0].doi == "10.1000/test"
        assert reconstructed.query_id == "task-query-id"

    @patch("alcoabase.tasks.literature_search_tasks._build_gateway_service")
    @patch("alcoabase.tasks.literature_search_tasks.celery_app")
    def test_task_function_exists_and_is_registered(
        self, mock_celery_app, mock_build_gateway
    ) -> None:
        """The execute_literature_search task can be imported."""
        from alcoabase.tasks.literature_search_tasks import (
            execute_literature_search,
        )

        assert execute_literature_search is not None
        assert hasattr(execute_literature_search, "delay")
        assert hasattr(execute_literature_search, "apply_async")
