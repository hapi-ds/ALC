"""Unit tests for the VigilanceMonitorService.

Tests cover:
- Boolean query construction (AND/OR logic)
- Exclusion term filtering (case-insensitive substring)
- Deduplication logic (DOI and source_id+external_id)
- Idempotency check
- SearchExecutionResult dataclass immutability
- execute_search orchestration (mocked dependencies)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.vigilance.services.vigilance_monitor_service import (
    SearchExecutionResult,
    VigilanceMonitorService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    session.get = AsyncMock()

    factory = AsyncMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return factory, session


@pytest.fixture
def mock_gateway():
    """Create a mock LiteratureGatewayService."""
    gateway = AsyncMock()
    return gateway


@pytest.fixture
def mock_ingestion():
    """Create a mock IngestionPipelineService."""
    ingestion = AsyncMock()
    return ingestion


@pytest.fixture
def service(mock_session_factory, mock_gateway, mock_ingestion):
    """Create a VigilanceMonitorService instance with mocked dependencies."""
    factory, _ = mock_session_factory
    return VigilanceMonitorService(
        session_factory=factory,
        literature_gateway=mock_gateway,
        ingestion_pipeline=mock_ingestion,
        execution_timeout=3600,
    )


# ---------------------------------------------------------------------------
# SearchExecutionResult Dataclass Tests
# ---------------------------------------------------------------------------


class TestSearchExecutionResult:
    """Tests for the SearchExecutionResult frozen dataclass."""

    def test_creation(self):
        """Test creating a SearchExecutionResult."""
        result = SearchExecutionResult(
            execution_id=1,
            total_results_found=10,
            results_after_exclusion=8,
            results_ingested=5,
            results_duplicate=3,
            execution_duration_ms=1500,
            status="completed",
        )
        assert result.execution_id == 1
        assert result.total_results_found == 10
        assert result.results_after_exclusion == 8
        assert result.results_ingested == 5
        assert result.results_duplicate == 3
        assert result.execution_duration_ms == 1500
        assert result.status == "completed"

    def test_immutability(self):
        """Test that SearchExecutionResult is immutable."""
        result = SearchExecutionResult(
            execution_id=1,
            total_results_found=10,
            results_after_exclusion=8,
            results_ingested=5,
            results_duplicate=3,
            execution_duration_ms=1500,
            status="completed",
        )
        with pytest.raises(AttributeError):
            result.status = "failed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# construct_search_query Tests
# ---------------------------------------------------------------------------


class TestConstructSearchQuery:
    """Tests for Boolean query construction logic."""

    def test_all_terms_present(self, service):
        """Test query with all categories populated."""
        result = service.construct_search_query(
            search_terms=["cardiac stent", "stent X100"],
            mesh_terms=["Coronary Artery Disease"],
            adverse_event_keywords=["fracture", "migration"],
            device_identifiers=["UDI-12345"],
        )

        query = result["query_string"]
        # Product terms are ORed together
        assert '"cardiac stent"' in query
        assert '"stent X100"' in query
        assert '"Coronary Artery Disease"' in query
        assert "UDI-12345" in query
        # Adverse event keywords are ORed within their clause
        assert "fracture" in query
        assert "migration" in query
        # AND connects the two clauses
        assert "AND" in query
        # Structure check
        assert query.startswith("(")
        assert ") AND (" in query

    def test_search_terms_only_with_adverse_keywords(self, service):
        """Test query with only search_terms and adverse keywords."""
        result = service.construct_search_query(
            search_terms=["device A"],
            mesh_terms=[],
            adverse_event_keywords=["malfunction"],
            device_identifiers=[],
        )

        query = result["query_string"]
        assert '"device A"' in query
        assert "malfunction" in query
        assert "AND" in query

    def test_single_word_terms_not_quoted(self, service):
        """Test that single-word terms are not quoted."""
        result = service.construct_search_query(
            search_terms=["stent"],
            mesh_terms=[],
            adverse_event_keywords=["fracture"],
            device_identifiers=[],
        )

        query = result["query_string"]
        assert "(stent) AND (fracture)" == query

    def test_empty_search_terms_only_adverse(self, service):
        """Test query with only adverse event keywords."""
        result = service.construct_search_query(
            search_terms=[],
            mesh_terms=[],
            adverse_event_keywords=["bleeding", "infection"],
            device_identifiers=[],
        )

        query = result["query_string"]
        # Only adverse clause (no product terms)
        assert "bleeding" in query
        assert "infection" in query
        assert "AND" not in query

    def test_empty_adverse_keywords_only_product(self, service):
        """Test query with only product terms (no adverse keywords)."""
        result = service.construct_search_query(
            search_terms=["device X"],
            mesh_terms=[],
            adverse_event_keywords=[],
            device_identifiers=[],
        )

        query = result["query_string"]
        assert '"device X"' in query
        assert "AND" not in query

    def test_all_empty(self, service):
        """Test query with no terms produces empty string."""
        result = service.construct_search_query(
            search_terms=[],
            mesh_terms=[],
            adverse_event_keywords=[],
            device_identifiers=[],
        )
        assert result["query_string"] == ""

    def test_components_preserved_in_output(self, service):
        """Test that original components are recorded for audit."""
        result = service.construct_search_query(
            search_terms=["A", "B"],
            mesh_terms=["C"],
            adverse_event_keywords=["D"],
            device_identifiers=["E"],
        )

        assert result["components"]["search_terms"] == ["A", "B"]
        assert result["components"]["mesh_terms"] == ["C"]
        assert result["components"]["adverse_event_keywords"] == ["D"]
        assert result["components"]["device_identifiers"] == ["E"]

    def test_whitespace_only_terms_excluded(self, service):
        """Test that whitespace-only terms are excluded."""
        result = service.construct_search_query(
            search_terms=["valid", "   ", ""],
            mesh_terms=[],
            adverse_event_keywords=["event"],
            device_identifiers=[],
        )

        query = result["query_string"]
        assert "valid" in query
        assert "   " not in query


# ---------------------------------------------------------------------------
# filter_exclusion_terms Tests
# ---------------------------------------------------------------------------


class TestFilterExclusionTerms:
    """Tests for exclusion term filtering logic."""

    def test_no_exclusion_terms(self, service):
        """Test that no filtering occurs with empty exclusion list."""
        results = [
            {"title": "Study on stent fracture", "abstract": "..."},
            {"title": "Another study", "abstract": "..."},
        ]
        filtered = service.filter_exclusion_terms(results, [])
        assert len(filtered) == 2

    def test_title_match_excluded(self, service):
        """Test exclusion based on title match."""
        results = [
            {"title": "Study on veterinary devices", "abstract": "Good study"},
            {"title": "Cardiac stent fracture", "abstract": "Relevant study"},
        ]
        filtered = service.filter_exclusion_terms(results, ["veterinary"])
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Cardiac stent fracture"

    def test_abstract_match_excluded(self, service):
        """Test exclusion based on abstract match."""
        results = [
            {"title": "Stent Study", "abstract": "This is about veterinary use."},
            {"title": "Cardiac Study", "abstract": "Human cardiac analysis."},
        ]
        filtered = service.filter_exclusion_terms(results, ["veterinary"])
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Cardiac Study"

    def test_case_insensitive(self, service):
        """Test that exclusion matching is case-insensitive."""
        results = [
            {"title": "VETERINARY Device Study", "abstract": "Details here."},
            {"title": "Human study", "abstract": "More details."},
        ]
        filtered = service.filter_exclusion_terms(results, ["veterinary"])
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Human study"

    def test_multiple_exclusion_terms(self, service):
        """Test that multiple exclusion terms all filter correctly."""
        results = [
            {"title": "Dental implant review", "abstract": "..."},
            {"title": "Pediatric device", "abstract": "..."},
            {"title": "Cardiac stent failure", "abstract": "..."},
        ]
        filtered = service.filter_exclusion_terms(results, ["dental", "pediatric"])
        assert len(filtered) == 1
        assert filtered[0]["title"] == "Cardiac stent failure"

    def test_all_results_excluded(self, service):
        """Test that all results can be excluded."""
        results = [
            {"title": "Study A", "abstract": "Contains veterinary content"},
            {"title": "Study B", "abstract": "Also veterinary content"},
        ]
        filtered = service.filter_exclusion_terms(results, ["veterinary"])
        assert len(filtered) == 0

    def test_no_results_excluded(self, service):
        """Test when no results match exclusion terms."""
        results = [
            {"title": "Cardiac Study", "abstract": "Human patients only."},
            {"title": "Stent Analysis", "abstract": "Clinical trial data."},
        ]
        filtered = service.filter_exclusion_terms(results, ["veterinary"])
        assert len(filtered) == 2

    def test_missing_title_or_abstract(self, service):
        """Test handling of results with missing title or abstract."""
        results = [
            {"title": None, "abstract": "Some abstract about veterinary"},
            {"title": "Valid title", "abstract": None},
            {"title": None, "abstract": None},
        ]
        filtered = service.filter_exclusion_terms(results, ["veterinary"])
        assert len(filtered) == 2
        # The first result (with "veterinary" in abstract) is excluded

    def test_substring_match(self, service):
        """Test that exclusion uses substring matching not exact word match."""
        results = [
            {"title": "Biocompatibility study", "abstract": "..."},
        ]
        # "compat" is a substring of "Biocompatibility"
        filtered = service.filter_exclusion_terms(results, ["compat"])
        assert len(filtered) == 0


# ---------------------------------------------------------------------------
# deduplicate_results Tests
# ---------------------------------------------------------------------------


class TestDeduplicateResults:
    """Tests for deduplication logic."""

    @pytest.mark.asyncio
    async def test_empty_results(self, service, mock_session_factory):
        """Test deduplication with empty results returns empty."""
        _, session = mock_session_factory
        non_dupes, count = await service.deduplicate_results(session, [], 1)
        assert non_dupes == []
        assert count == 0

    @pytest.mark.asyncio
    async def test_no_duplicates_found(self, service, mock_session_factory):
        """Test when no duplicates exist in DB."""
        _, session = mock_session_factory
        # Mock execute to return no existing records
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        results = [
            {"title": "Study A", "doi": "10.1000/a", "source_id": "pubmed", "external_id": "123"},
            {"title": "Study B", "doi": "10.1000/b", "source_id": "pubmed", "external_id": "456"},
        ]

        non_dupes, count = await service.deduplicate_results(session, results, 1)
        assert len(non_dupes) == 2
        assert count == 0

    @pytest.mark.asyncio
    async def test_doi_duplicate_detected(self, service, mock_session_factory):
        """Test deduplication via DOI match."""
        _, session = mock_session_factory

        call_count = 0

        def mock_execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            # First call (DOI check for first result) returns existing
            if call_count == 1:
                mock_result.scalar_one_or_none.return_value = 42
            else:
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        results = [
            {"title": "Duplicate", "doi": "10.1000/exists", "source_id": "pubmed", "external_id": "111"},
            {"title": "New", "doi": "10.1000/new", "source_id": "pubmed", "external_id": "222"},
        ]

        non_dupes, count = await service.deduplicate_results(session, results, 1)
        assert len(non_dupes) == 1
        assert non_dupes[0]["title"] == "New"
        assert count == 1

    @pytest.mark.asyncio
    async def test_source_external_id_duplicate(self, service, mock_session_factory):
        """Test deduplication via source_id + external_id match."""
        _, session = mock_session_factory

        call_count = 0

        def mock_execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            # First call: DOI check returns None (no DOI match)
            # Second call: source+external_id check returns existing
            if call_count == 2:
                mock_result.scalar_one_or_none.return_value = 99
            else:
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        session.execute = AsyncMock(side_effect=mock_execute_side_effect)

        results = [
            {"title": "Dup by source", "doi": "10.1000/nodupe", "source_id": "crossref", "external_id": "dup-ext"},
        ]

        non_dupes, count = await service.deduplicate_results(session, results, 1)
        assert len(non_dupes) == 0
        assert count == 1

    @pytest.mark.asyncio
    async def test_no_doi_no_external(self, service, mock_session_factory):
        """Test result with no DOI and no external_id is not a duplicate."""
        _, session = mock_session_factory
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        results = [
            {"title": "Orphan", "doi": None, "source_id": None, "external_id": None},
        ]

        non_dupes, count = await service.deduplicate_results(session, results, 1)
        assert len(non_dupes) == 1
        assert count == 0


# ---------------------------------------------------------------------------
# _check_idempotency Tests
# ---------------------------------------------------------------------------


class TestCheckIdempotency:
    """Tests for idempotency check logic."""

    @pytest.mark.asyncio
    async def test_no_running_execution(self, service, mock_session_factory):
        """Test returns True when no running execution exists."""
        _, session = mock_session_factory
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        result = await service._check_idempotency(session, profile_id=1)
        assert result is True

    @pytest.mark.asyncio
    async def test_running_execution_exists(self, service, mock_session_factory):
        """Test returns False when a running execution exists."""
        _, session = mock_session_factory
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 42  # existing execution ID
        session.execute.return_value = mock_result

        result = await service._check_idempotency(session, profile_id=1)
        assert result is False


# ---------------------------------------------------------------------------
# Service Constants
# ---------------------------------------------------------------------------


class TestServiceConstants:
    """Tests for service configuration constants."""

    def test_max_retries(self, service):
        """Test MAX_RETRIES constant."""
        assert service.MAX_RETRIES == 3

    def test_backoff_intervals(self, service):
        """Test backoff intervals are 5min, 15min, 60min."""
        assert service.BACKOFF_INTERVALS == (300, 900, 3600)

    def test_execution_timeout(self, service):
        """Test default execution timeout is 60 minutes."""
        assert service.EXECUTION_TIMEOUT_S == 3600
