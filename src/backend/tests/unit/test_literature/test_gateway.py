"""Unit tests for LiteratureGatewayService orchestration.

Tests parallel dispatch to multiple sources, deduplication logic,
priority ordering with tie-breaking, partial failure handling,
and async dispatch threshold logic.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.6, 15.1
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.exceptions import (
    AdapterError,
    AdapterTimeoutError,
    AllSourcesUnavailableError,
    RateLimitExceededError,
)
from alcoabase.literature.models.literature import SourceConfiguration
from alcoabase.literature.schemas.search import (
    LiteratureSearchResult,
    PublicationType,
    SearchQuery,
)
from alcoabase.literature.services.gateway_service import LiteratureGatewayService
from alcoabase.literature.services.rate_limiter import RateLimitResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_config(
    name: str,
    priority: int = 50,
    is_enabled: bool = True,
    company_id: int = 1,
) -> MagicMock:
    """Create a mock SourceConfiguration with the specified attributes."""
    config = MagicMock(spec=SourceConfiguration)
    config.source_adapter_name = name
    config.priority = priority
    config.is_enabled = is_enabled
    config.company_id = company_id
    config.api_key_ciphertext = None
    config.api_key_nonce = None
    config.api_key_tag = None
    return config


def _make_result(
    source_id: str,
    doi: str | None = None,
    title: str = "Test Paper",
    external_id: str | None = None,
) -> LiteratureSearchResult:
    """Create a LiteratureSearchResult for testing."""
    return LiteratureSearchResult(
        title=title,
        authors=["Author A"],
        abstract="Abstract text",
        doi=doi,
        publication_date=date(2024, 1, 15),
        source_id=source_id,
        external_id=external_id or f"{source_id}_001",
        journal_or_venue="Test Journal",
        publication_type=PublicationType.JOURNAL_ARTICLE,
        url=None,
        retrieval_timestamp=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        query_id="test-query-id",
    )


def _make_query(
    terms: str = "machine learning",
    sources: list[str] | None = None,
    page_size: int = 20,
) -> SearchQuery:
    """Create a SearchQuery for testing."""
    return SearchQuery(terms=terms, sources=sources, page_size=page_size)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_source_registry() -> MagicMock:
    """Create a mock SourceRegistry that returns adapters for known names."""
    registry = MagicMock()

    def get_adapter(name: str):
        # Return a mock adapter for any name (simulates all adapters registered)
        adapter = AsyncMock()
        adapter.search = AsyncMock(return_value=[])
        return adapter

    registry.get_adapter = MagicMock(side_effect=get_adapter)
    return registry


@pytest.fixture
def mock_rate_limiter() -> AsyncMock:
    """Create a mock RateLimiter that always allows requests."""
    limiter = AsyncMock()
    limiter.check_and_consume = AsyncMock(
        return_value=RateLimitResult(allowed=True, remaining=100)
    )
    return limiter


@pytest.fixture
def mock_circuit_breaker() -> AsyncMock:
    """Create a mock CircuitBreaker that always allows execution."""
    cb = AsyncMock()
    cb.can_execute = AsyncMock(return_value=True)
    cb.record_success = AsyncMock()
    cb.record_failure = AsyncMock()
    cb.get_estimated_recovery_time = AsyncMock(return_value=None)
    return cb


@pytest.fixture
def mock_api_key_vault() -> MagicMock:
    """Create a mock APIKeyVault."""
    vault = MagicMock()
    vault.decrypt = MagicMock(return_value="decrypted-key")
    return vault


@pytest.fixture
def mock_audit_logger() -> AsyncMock:
    """Create a mock AuditLogger that returns audit IDs."""
    logger = AsyncMock()
    logger.log_request = AsyncMock(return_value=1)
    logger.log_response = AsyncMock()
    logger.log_failure = AsyncMock()
    return logger


@pytest.fixture
def mock_proxy_manager() -> MagicMock:
    """Create a mock ProxyManager."""
    proxy = MagicMock()
    proxy.get_proxy_for_source = MagicMock(return_value=None)
    return proxy


@pytest.fixture
def gateway(
    mock_source_registry: MagicMock,
    mock_rate_limiter: AsyncMock,
    mock_circuit_breaker: AsyncMock,
    mock_api_key_vault: MagicMock,
    mock_audit_logger: AsyncMock,
    mock_proxy_manager: MagicMock,
) -> LiteratureGatewayService:
    """Create a LiteratureGatewayService with all mocked dependencies."""
    return LiteratureGatewayService(
        source_registry=mock_source_registry,
        rate_limiter=mock_rate_limiter,
        circuit_breaker=mock_circuit_breaker,
        api_key_vault=mock_api_key_vault,
        audit_logger=mock_audit_logger,
        proxy_manager=mock_proxy_manager,
    )


# ---------------------------------------------------------------------------
# Tests: Parallel Dispatch to Multiple Sources
# ---------------------------------------------------------------------------


class TestParallelDispatch:
    """Tests for parallel search dispatch to multiple sources."""

    @pytest.mark.asyncio
    async def test_dispatches_to_all_enabled_sources(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Dispatches queries to all enabled source configs in parallel."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
        ]

        # Each adapter returns one result
        def get_adapter(name: str):
            adapter = AsyncMock()
            adapter.search = AsyncMock(
                return_value=[_make_result(name, doi=f"10.1000/{name}")]
            )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        query = _make_query()
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        assert response.total_count == 3
        assert len(response.results) == 3

    @pytest.mark.asyncio
    async def test_dispatches_only_to_enabled_sources(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Disabled sources are not dispatched to."""
        configs = [
            _make_source_config("pubmed", priority=1, is_enabled=True),
            _make_source_config("crossref", priority=2, is_enabled=False),
        ]

        def get_adapter(name: str):
            adapter = AsyncMock()
            adapter.search = AsyncMock(
                return_value=[_make_result(name, doi=f"10.1000/{name}")]
            )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        query = _make_query()
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        # Only pubmed should return results
        assert response.total_count == 1
        assert response.results[0].source_id == "pubmed"

    @pytest.mark.asyncio
    async def test_source_filter_restricts_dispatch(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Query source filter limits dispatch to specified sources only."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
        ]

        def get_adapter(name: str):
            adapter = AsyncMock()
            adapter.search = AsyncMock(
                return_value=[_make_result(name, doi=f"10.1000/{name}")]
            )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        # Only request pubmed and arxiv
        query = _make_query(sources=["pubmed", "arxiv"])
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        assert response.total_count == 2
        source_ids = {r.source_id for r in response.results}
        assert source_ids == {"pubmed", "arxiv"}

    @pytest.mark.asyncio
    async def test_unavailable_source_filter_generates_warning(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Requesting an unavailable source generates a warning in partial_results."""
        configs = [
            _make_source_config("pubmed", priority=1),
        ]

        def get_adapter(name: str):
            adapter = AsyncMock()
            adapter.search = AsyncMock(
                return_value=[_make_result(name, doi=f"10.1000/{name}")]
            )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        # Request a source that's not in configs
        query = _make_query(sources=["pubmed", "ieee"])
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        assert response.partial_results is not None
        assert "ieee" in response.partial_results.unavailable_sources


# ---------------------------------------------------------------------------
# Tests: Deduplication Logic
# ---------------------------------------------------------------------------


class TestDeduplication:
    """Tests for DOI-based deduplication of search results."""

    def test_deduplicates_shared_doi_keeps_highest_priority(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Results with same DOI are deduplicated; highest-priority source wins."""
        results = [
            _make_result("crossref", doi="10.1000/shared"),
            _make_result("pubmed", doi="10.1000/shared"),
        ]
        priorities = {"pubmed": 1, "crossref": 2}

        deduped = gateway.deduplicate_results(results, priorities)

        assert len(deduped) == 1
        assert deduped[0].source_id == "pubmed"

    def test_null_doi_results_never_deduplicated(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Results with null DOI are always kept, even if from same source."""
        results = [
            _make_result("pubmed", doi=None, external_id="pm_001"),
            _make_result("pubmed", doi=None, external_id="pm_002"),
            _make_result("crossref", doi=None, external_id="cr_001"),
        ]
        priorities = {"pubmed": 1, "crossref": 2}

        deduped = gateway.deduplicate_results(results, priorities)

        assert len(deduped) == 3

    def test_mixed_doi_and_null_doi(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Deduplication handles mix of DOI and null-DOI results correctly."""
        results = [
            _make_result("pubmed", doi="10.1000/a"),
            _make_result("crossref", doi="10.1000/a"),  # duplicate
            _make_result("arxiv", doi=None, external_id="arxiv_001"),
            _make_result("pubmed", doi="10.1000/b"),
            _make_result("arxiv", doi=None, external_id="arxiv_002"),
        ]
        priorities = {"pubmed": 1, "crossref": 2, "arxiv": 3}

        deduped = gateway.deduplicate_results(results, priorities)

        # 2 unique DOIs + 2 null DOIs = 4 results
        assert len(deduped) == 4

        # Verify the shared DOI kept pubmed (priority 1)
        doi_a_results = [r for r in deduped if r.doi == "10.1000/a"]
        assert len(doi_a_results) == 1
        assert doi_a_results[0].source_id == "pubmed"

    def test_multiple_shared_dois(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Multiple DOIs shared across sources are each deduplicated correctly."""
        results = [
            _make_result("crossref", doi="10.1000/x"),
            _make_result("pubmed", doi="10.1000/x"),
            _make_result("arxiv", doi="10.1000/y"),
            _make_result("crossref", doi="10.1000/y"),
        ]
        priorities = {"pubmed": 1, "crossref": 2, "arxiv": 3}

        deduped = gateway.deduplicate_results(results, priorities)

        assert len(deduped) == 2
        doi_map = {r.doi: r.source_id for r in deduped}
        assert doi_map["10.1000/x"] == "pubmed"
        assert doi_map["10.1000/y"] == "crossref"

    def test_empty_results(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Empty input returns empty output."""
        deduped = gateway.deduplicate_results([], {})
        assert deduped == []


# ---------------------------------------------------------------------------
# Tests: Priority Ordering with Tie-Breaking
# ---------------------------------------------------------------------------


class TestPriorityOrdering:
    """Tests for result ordering by source priority with alphabetical tie-breaking."""

    def test_orders_by_priority_ascending(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Results are ordered by priority number ascending (lowest = first)."""
        results = [
            _make_result("crossref", doi="10.1000/c"),
            _make_result("arxiv", doi="10.1000/a"),
            _make_result("pubmed", doi="10.1000/p"),
        ]
        priorities = {"pubmed": 1, "crossref": 2, "arxiv": 3}

        ordered = gateway.order_results_by_priority(results, priorities)

        assert ordered[0].source_id == "pubmed"
        assert ordered[1].source_id == "crossref"
        assert ordered[2].source_id == "arxiv"

    def test_alphabetical_tiebreaking_on_same_priority(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Sources with same priority are tie-broken alphabetically by source name."""
        results = [
            _make_result("crossref", doi="10.1000/c"),
            _make_result("arxiv", doi="10.1000/a"),
            _make_result("pubmed", doi="10.1000/p"),
        ]
        # All same priority
        priorities = {"pubmed": 5, "crossref": 5, "arxiv": 5}

        ordered = gateway.order_results_by_priority(results, priorities)

        assert ordered[0].source_id == "arxiv"
        assert ordered[1].source_id == "crossref"
        assert ordered[2].source_id == "pubmed"

    def test_mixed_priorities_with_ties(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Mixed priorities: grouped by priority, tied groups sorted alphabetically."""
        results = [
            _make_result("delta", doi="10.1/d"),
            _make_result("alpha", doi="10.1/a"),
            _make_result("beta", doi="10.1/b"),
            _make_result("gamma", doi="10.1/g"),
        ]
        priorities = {"alpha": 2, "beta": 1, "gamma": 2, "delta": 1}

        ordered = gateway.order_results_by_priority(results, priorities)

        # Priority 1: beta, delta (alphabetical)
        assert ordered[0].source_id == "beta"
        assert ordered[1].source_id == "delta"
        # Priority 2: alpha, gamma (alphabetical)
        assert ordered[2].source_id == "alpha"
        assert ordered[3].source_id == "gamma"

    def test_unknown_source_gets_default_priority(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Sources not in priority map get default priority 100."""
        results = [
            _make_result("unknown_source", doi="10.1/u"),
            _make_result("pubmed", doi="10.1/p"),
        ]
        priorities = {"pubmed": 50}

        ordered = gateway.order_results_by_priority(results, priorities)

        # pubmed (50) before unknown_source (default 100)
        assert ordered[0].source_id == "pubmed"
        assert ordered[1].source_id == "unknown_source"

    def test_empty_results_ordering(
        self, gateway: LiteratureGatewayService
    ) -> None:
        """Ordering empty list returns empty list."""
        ordered = gateway.order_results_by_priority([], {})
        assert ordered == []


# ---------------------------------------------------------------------------
# Tests: Partial Failure Handling
# ---------------------------------------------------------------------------


class TestPartialFailureHandling:
    """Tests that partial failures from some sources still return results from others."""

    @pytest.mark.asyncio
    async def test_timeout_sources_reported_in_partial_results(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Sources that timeout are listed in partial_results.timed_out_sources."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        def get_adapter(name: str):
            adapter = AsyncMock()
            if name == "pubmed":
                adapter.search = AsyncMock(
                    return_value=[_make_result("pubmed", doi="10.1/p")]
                )
            else:
                # crossref times out
                adapter.search = AsyncMock(
                    side_effect=asyncio.TimeoutError()
                )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        query = _make_query()
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        # pubmed results should be present
        assert response.total_count == 1
        assert response.results[0].source_id == "pubmed"
        # crossref should be in timed_out_sources
        assert response.partial_results is not None
        assert "crossref" in response.partial_results.timed_out_sources

    @pytest.mark.asyncio
    async def test_errored_sources_reported_in_partial_results(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Sources that error are listed in partial_results.errored_sources."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        def get_adapter(name: str):
            adapter = AsyncMock()
            if name == "pubmed":
                adapter.search = AsyncMock(
                    return_value=[_make_result("pubmed", doi="10.1/p")]
                )
            else:
                # crossref raises an adapter error
                adapter.search = AsyncMock(
                    side_effect=AdapterError(
                        "Connection failed",
                        source_adapter_name="crossref",
                    )
                )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        query = _make_query()
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        assert response.total_count == 1
        assert response.partial_results is not None
        assert "crossref" in response.partial_results.errored_sources

    @pytest.mark.asyncio
    async def test_all_sources_fail_raises_all_sources_unavailable(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """When all sources fail, AllSourcesUnavailableError is raised."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        def get_adapter(name: str):
            adapter = AsyncMock()
            adapter.search = AsyncMock(side_effect=asyncio.TimeoutError())
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        query = _make_query()
        with pytest.raises(AllSourcesUnavailableError):
            await gateway.search(
                query=query, company_id=1, user_id=42, source_configs=configs
            )

    @pytest.mark.asyncio
    async def test_circuit_breaker_open_skips_source(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
        mock_circuit_breaker: AsyncMock,
    ) -> None:
        """Sources with open circuit breaker are skipped and marked unavailable."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]

        # Circuit breaker is open for crossref only
        async def can_execute(source_name: str) -> bool:
            return source_name != "crossref"

        mock_circuit_breaker.can_execute = AsyncMock(side_effect=can_execute)

        def get_adapter(name: str):
            adapter = AsyncMock()
            adapter.search = AsyncMock(
                return_value=[_make_result(name, doi=f"10.1/{name}")]
            )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        query = _make_query()
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        assert response.total_count == 1
        assert response.results[0].source_id == "pubmed"
        assert response.partial_results is not None
        assert "crossref" in response.partial_results.unavailable_sources

    @pytest.mark.asyncio
    async def test_mixed_success_timeout_and_error(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Mix of success, timeout, and error sources handled correctly."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
        ]

        def get_adapter(name: str):
            adapter = AsyncMock()
            if name == "pubmed":
                adapter.search = AsyncMock(
                    return_value=[_make_result("pubmed", doi="10.1/p")]
                )
            elif name == "crossref":
                adapter.search = AsyncMock(
                    side_effect=asyncio.TimeoutError()
                )
            else:
                adapter.search = AsyncMock(
                    side_effect=AdapterError(
                        "Parse error",
                        source_adapter_name="arxiv",
                    )
                )
            return adapter

        mock_source_registry.get_adapter = MagicMock(side_effect=get_adapter)

        query = _make_query()
        response = await gateway.search(
            query=query, company_id=1, user_id=42, source_configs=configs
        )

        assert response.total_count == 1
        assert response.results[0].source_id == "pubmed"
        assert response.partial_results is not None
        assert "crossref" in response.partial_results.timed_out_sources
        assert "arxiv" in response.partial_results.errored_sources


# ---------------------------------------------------------------------------
# Tests: Async Dispatch Threshold Logic
# ---------------------------------------------------------------------------


class TestAsyncDispatchThreshold:
    """Tests for should_dispatch_async logic."""

    def test_returns_false_for_small_query(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Returns False when <=3 sources and <=50 page_size."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
        ]
        query = _make_query(page_size=20)

        result = gateway.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is False

    def test_returns_true_for_more_than_3_sources(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Returns True when >3 sources are targeted."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
            _make_source_config("ieee", priority=4),
        ]
        query = _make_query(page_size=20)

        result = gateway.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is True

    def test_returns_true_for_page_size_above_50(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Returns True when page_size > 50."""
        configs = [
            _make_source_config("pubmed", priority=1),
        ]
        query = _make_query(page_size=51)

        result = gateway.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is True

    def test_returns_false_for_exactly_3_sources(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Returns False when exactly 3 sources (threshold is >3)."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
        ]
        query = _make_query(page_size=50)

        result = gateway.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is False

    def test_returns_false_for_exactly_50_page_size(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Returns False when page_size is exactly 50 (threshold is >50)."""
        configs = [
            _make_source_config("pubmed", priority=1),
        ]
        query = _make_query(page_size=50)

        result = gateway.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is False

    def test_returns_true_when_both_thresholds_exceeded(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Returns True when both >3 sources and >50 page_size."""
        configs = [
            _make_source_config("pubmed", priority=1),
            _make_source_config("crossref", priority=2),
            _make_source_config("arxiv", priority=3),
            _make_source_config("ieee", priority=4),
        ]
        query = _make_query(page_size=100)

        result = gateway.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        assert result is True

    def test_disabled_sources_not_counted(
        self,
        gateway: LiteratureGatewayService,
        mock_source_registry: MagicMock,
    ) -> None:
        """Disabled sources are not counted toward the threshold."""
        configs = [
            _make_source_config("pubmed", priority=1, is_enabled=True),
            _make_source_config("crossref", priority=2, is_enabled=True),
            _make_source_config("arxiv", priority=3, is_enabled=True),
            _make_source_config("ieee", priority=4, is_enabled=False),
        ]
        query = _make_query(page_size=20)

        result = gateway.should_dispatch_async(
            query=query, company_id=1, source_configs=configs
        )

        # Only 3 enabled sources, so should be False
        assert result is False
