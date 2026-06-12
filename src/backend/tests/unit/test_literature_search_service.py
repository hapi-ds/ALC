"""Unit tests for LiteratureSearchService.

Tests cover:
- execute_search with valid params (mocked HybridQueryEngine)
- execute_search enriches is_internalized flag
- execute_search records SearchExecutionLog
- execute_search handles OpenSearch unavailability (raises SearchServiceUnavailableError)
- internalize with valid IngestionRecord (creates Document, copies file)
- internalize duplicate detection (returns 409 with existing doc ID)
- internalize with wrong company (returns 404)
- internalize with MinIO failure (Document created, full_text_status="unavailable")
- create_saved_search success and limit enforcement (200 max)
- list_saved_searches ordering (last_executed_at DESC, NULLs last)
- execute_saved_search updates metadata
- delete_saved_search (soft-delete, role check)
- citation collection CRUD
- add_documents_to_collection validates internalized-only, 500 limit
- remove_document_from_collection preserves Document
- create_traceability_links validates internalized doc
- list_traceability_links filtering
- delete_traceability_link

References:
    - Requirements: 1.1–1.10, 2.1–2.5, 3.1–3.8, 4.1–4.10, 5.1–5.11, 6.1–6.9
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.embedding.exceptions import SearchServiceUnavailableError
from alcoabase.literature.search.exceptions import (
    CollectionCapacityExceededError,
    DuplicateInternalizationError,
    IngestionRecordNotFoundError,
    NonInternalizedDocumentError,
    SavedSearchLimitExceededError,
)
from alcoabase.literature.search.services.literature_search_service import (
    LiteratureSearchService,
    _MAX_COLLECTION_DOCUMENTS,
    _MAX_SAVED_SEARCHES_PER_USER,
)


# ---------------------------------------------------------------------------
# Helper dataclass to simulate HybridSearchResult
# ---------------------------------------------------------------------------


@dataclass
class FakeHybridSearchResult:
    """Mimics HybridSearchResult from the query engine."""

    chunk_text: str
    title: str
    authors: list[str]
    doi: str | None
    publication_date: str | None
    source_id: str | None
    relevance_score: float
    partition_tag: str
    section_heading: str
    ingestion_record_id: int


@dataclass
class FakeHybridSearchResponse:
    """Mimics HybridSearchResponse from the query engine."""

    results: list[FakeHybridSearchResult]
    total_count: int
    page: int
    page_size: int
    degraded_mode: bool = False
    partial_results: bool = False
    unavailable_index: str | None = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession with common setup."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_query_engine() -> AsyncMock:
    """Create a mock HybridQueryEngine."""
    engine = AsyncMock()
    return engine


@pytest.fixture
def mock_audit_service() -> AsyncMock:
    """Create a mock AuditTrailService."""
    return AsyncMock()


@pytest.fixture
def mock_traceability_service() -> AsyncMock:
    """Create a mock TraceabilityMatrixService."""
    return AsyncMock()


@pytest.fixture
def mock_storage_client() -> AsyncMock:
    """Create a mock aioboto3 S3 client."""
    client = AsyncMock()
    client.copy_object = AsyncMock()
    return client


@pytest.fixture
def service(
    mock_session: AsyncMock,
    mock_query_engine: AsyncMock,
    mock_audit_service: AsyncMock,
    mock_traceability_service: AsyncMock,
    mock_storage_client: AsyncMock,
) -> LiteratureSearchService:
    """Create a LiteratureSearchService with all dependencies mocked."""
    return LiteratureSearchService(
        session=mock_session,
        hybrid_query_engine=mock_query_engine,
        audit_trail_service=mock_audit_service,
        traceability_matrix_service=mock_traceability_service,
        storage_client=mock_storage_client,
    )


def _make_scalar_result(value):
    """Create a mock result that behaves like session.execute().scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    mock_result.scalar_one.return_value = value
    mock_result.scalars.return_value.all.return_value = []
    return mock_result


def _make_scalars_result(values):
    """Create a mock result that behaves like session.execute().scalars().all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = values
    mock_result.scalar_one.return_value = len(values)
    return mock_result


# ---------------------------------------------------------------------------
# Search Execution Tests
# ---------------------------------------------------------------------------


class TestExecuteSearch:
    """Tests for LiteratureSearchService.execute_search."""

    @pytest.mark.asyncio
    async def test_execute_search_valid_params(
        self, service: LiteratureSearchService, mock_query_engine: AsyncMock, mock_session: AsyncMock
    ):
        """execute_search delegates to HybridQueryEngine and returns structured results."""
        fake_result = FakeHybridSearchResult(
            chunk_text="Test abstract content",
            title="Test Paper",
            authors=["Author A"],
            doi="10.1234/test",
            publication_date="2024-01-15",
            source_id="pubmed",
            relevance_score=0.85,
            partition_tag="public_literature",
            section_heading="Abstract",
            ingestion_record_id=42,
        )
        mock_query_engine.unified_search = AsyncMock(
            return_value=FakeHybridSearchResponse(
                results=[fake_result],
                total_count=1,
                page=1,
                page_size=20,
            )
        )

        # Mock session.execute for _enrich_with_internalization_status (returns no internalized docs)
        mock_session.execute = AsyncMock(return_value=_make_scalars_result([]))

        # Mock session.add and flush for SearchExecutionLog
        log_entry_mock = MagicMock()
        log_entry_mock.id = 99
        mock_session.add = MagicMock()
        mock_session.flush = AsyncMock()

        # Patch SearchExecutionLog so we can control its id
        with patch(
            "alcoabase.literature.search.services.literature_search_service.SearchExecutionLog"
        ) as MockLog:
            MockLog.return_value = log_entry_mock

            result = await service.execute_search(
                query_text="protein folding",
                filters={},
                search_mode="hybrid",
                include_internal=False,
                page=1,
                page_size=20,
                user_id=1,
                company_id=1,
            )

        assert "results" in result
        assert "pagination" in result
        assert "facets" in result
        assert "search_execution_id" in result
        assert result["search_execution_id"] == 99
        assert result["pagination"]["total_results"] == 1
        mock_query_engine.unified_search.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_execute_search_enriches_is_internalized(
        self, service: LiteratureSearchService, mock_query_engine: AsyncMock, mock_session: AsyncMock
    ):
        """execute_search sets is_internalized=True for results already internalized."""
        fake_result = FakeHybridSearchResult(
            chunk_text="Already internalized paper",
            title="Internalized Paper",
            authors=["Author B"],
            doi="10.5678/int",
            publication_date="2024-02-01",
            source_id="pubmed",
            relevance_score=0.9,
            partition_tag="public_literature",
            section_heading="Methods",
            ingestion_record_id=100,
        )
        mock_query_engine.unified_search = AsyncMock(
            return_value=FakeHybridSearchResponse(
                results=[fake_result],
                total_count=1,
                page=1,
                page_size=20,
            )
        )

        # Mock: ingestion_record_id=100 is already internalized
        internalized_result = MagicMock()
        internalized_result.scalars.return_value.all.return_value = [100]

        mock_session.execute = AsyncMock(return_value=internalized_result)

        log_entry_mock = MagicMock()
        log_entry_mock.id = 101

        with patch(
            "alcoabase.literature.search.services.literature_search_service.SearchExecutionLog"
        ) as MockLog:
            MockLog.return_value = log_entry_mock

            result = await service.execute_search(
                query_text="internalized paper",
                filters={},
                search_mode="hybrid",
                include_internal=False,
                page=1,
                page_size=20,
                user_id=1,
                company_id=1,
            )

        assert result["results"][0]["is_internalized"] is True

    @pytest.mark.asyncio
    async def test_execute_search_records_execution_log(
        self, service: LiteratureSearchService, mock_query_engine: AsyncMock, mock_session: AsyncMock
    ):
        """execute_search creates a SearchExecutionLog record."""
        mock_query_engine.unified_search = AsyncMock(
            return_value=FakeHybridSearchResponse(
                results=[],
                total_count=0,
                page=1,
                page_size=20,
            )
        )
        mock_session.execute = AsyncMock(return_value=_make_scalars_result([]))

        log_entry_mock = MagicMock()
        log_entry_mock.id = 200

        with patch(
            "alcoabase.literature.search.services.literature_search_service.SearchExecutionLog"
        ) as MockLog:
            MockLog.return_value = log_entry_mock

            await service.execute_search(
                query_text="test query",
                filters={"date_from": "2024-01-01"},
                search_mode="keyword",
                include_internal=True,
                page=1,
                page_size=20,
                user_id=5,
                company_id=2,
            )

        # Verify SearchExecutionLog was constructed with correct params
        MockLog.assert_called_once()
        call_kwargs = MockLog.call_args[1] if MockLog.call_args[1] else {}
        call_args = MockLog.call_args
        # Check key fields were passed
        if call_kwargs:
            assert call_kwargs["query_text"] == "test query"
            assert call_kwargs["search_mode"] == "keyword"
        else:
            # Positional keyword arguments
            assert call_args.kwargs.get("query_text") == "test query"
        mock_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_execute_search_opensearch_unavailable(
        self, service: LiteratureSearchService, mock_query_engine: AsyncMock
    ):
        """execute_search propagates SearchServiceUnavailableError when OpenSearch is down."""
        mock_query_engine.unified_search = AsyncMock(
            side_effect=SearchServiceUnavailableError("OpenSearch connection timeout")
        )

        with pytest.raises(SearchServiceUnavailableError):
            await service.execute_search(
                query_text="test query",
                filters={},
                search_mode="hybrid",
                include_internal=False,
                page=1,
                page_size=20,
                user_id=1,
                company_id=1,
            )


# ---------------------------------------------------------------------------
# Internalization Tests
# ---------------------------------------------------------------------------


class TestInternalize:
    """Tests for LiteratureSearchService.internalize."""

    @pytest.mark.asyncio
    async def test_internalize_valid_ingestion_record(
        self, service: LiteratureSearchService, mock_session: AsyncMock, mock_storage_client: AsyncMock
    ):
        """internalize creates Document, copies file from MinIO."""
        # Mock IngestionRecord lookup
        mock_ingestion_record = MagicMock()
        mock_ingestion_record.title = "Test Paper Title"
        mock_ingestion_record.storage_path = "papers/2024/test.pdf"
        mock_ingestion_record.company_id = 1

        # Track call count to session.execute to return different results
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # IngestionRecord lookup
                return _make_scalar_result(mock_ingestion_record)
            elif call_count[0] == 2:
                # Duplicate check (no existing doc)
                return _make_scalar_result(None)
            else:
                # Other queries (e.g., coalesce for collection position)
                return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00001",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
                document_name=None,
                document_type="literature",
                tags=["review"],
            )

        assert result["document_name"] == "Test Paper Title"
        assert result["full_text_status"] == "available"
        assert result["current_status"] == "Draft"
        assert result["source_ingestion_record_id"] == 42
        mock_storage_client.copy_object.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_internalize_duplicate_detection(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """internalize raises DuplicateInternalizationError if already internalized."""
        mock_ingestion_record = MagicMock()
        mock_ingestion_record.title = "Already Internalized"
        mock_ingestion_record.company_id = 1

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # IngestionRecord found
                return _make_scalar_result(mock_ingestion_record)
            elif call_count[0] == 2:
                # Duplicate check returns existing document ID
                return _make_scalar_result(999)
            return _make_scalar_result(None)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(DuplicateInternalizationError) as exc_info:
            await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.existing_document_id == 999

    @pytest.mark.asyncio
    async def test_internalize_wrong_company(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """internalize raises IngestionRecordNotFoundError for wrong company."""
        # IngestionRecord not found (wrong company)
        mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

        with pytest.raises(IngestionRecordNotFoundError) as exc_info:
            await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=999,
            )

        assert exc_info.value.ingestion_record_id == 42

    @pytest.mark.asyncio
    async def test_internalize_minio_failure(
        self, service: LiteratureSearchService, mock_session: AsyncMock, mock_storage_client: AsyncMock
    ):
        """internalize creates Document with full_text_status='unavailable' on MinIO failure."""
        mock_ingestion_record = MagicMock()
        mock_ingestion_record.title = "Paper With Missing PDF"
        mock_ingestion_record.storage_path = "papers/missing.pdf"
        mock_ingestion_record.company_id = 1

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(mock_ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)  # No duplicate
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_storage_client.copy_object = AsyncMock(
            side_effect=Exception("MinIO connection refused")
        )

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00002",
        ):
            result = await service.internalize(
                ingestion_record_id=55,
                user_id=1,
                company_id=1,
            )

        assert result["full_text_status"] == "unavailable"
        assert result["document_name"] == "Paper With Missing PDF"


# ---------------------------------------------------------------------------
# Saved Searches Tests
# ---------------------------------------------------------------------------


class TestSavedSearches:
    """Tests for saved search CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_saved_search_success(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """create_saved_search persists search and returns dict."""
        # Mock count check: user has 0 saved searches
        mock_session.execute = AsyncMock(return_value=_make_scalar_result(0))

        # Mock the saved search object after refresh
        mock_saved_search = MagicMock()
        mock_saved_search.id = 10
        mock_saved_search.name = "My Search"
        mock_saved_search.description = "A test search"
        mock_saved_search.query_text = "protein"
        mock_saved_search.filters = {}
        mock_saved_search.search_mode = "hybrid"
        mock_saved_search.include_internal = False
        mock_saved_search.user_id = 1
        mock_saved_search.company_id = 1
        mock_saved_search.last_executed_at = None
        mock_saved_search.last_result_count = None
        mock_saved_search.status = "active"
        mock_saved_search.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_saved_search.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        # After commit + refresh, the service calls _saved_search_to_dict
        # We need to capture what gets added and mock refresh to set attributes
        original_add = mock_session.add

        async def mock_refresh(obj):
            # Copy attributes from mock_saved_search onto the added object
            for attr in ("id", "name", "description", "query_text", "filters",
                         "search_mode", "include_internal", "user_id", "company_id",
                         "last_executed_at", "last_result_count", "status",
                         "created_at", "updated_at"):
                setattr(obj, attr, getattr(mock_saved_search, attr))

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_saved_search(
            name="My Search",
            description="A test search",
            query_text="protein",
            filters={},
            search_mode="hybrid",
            include_internal=False,
            user_id=1,
            company_id=1,
        )

        assert result["name"] == "My Search"
        assert result["status"] == "active"
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_saved_search_limit_exceeded(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """create_saved_search raises SavedSearchLimitExceededError at 200 limit."""
        # User already has 200 saved searches
        mock_session.execute = AsyncMock(
            return_value=_make_scalar_result(_MAX_SAVED_SEARCHES_PER_USER)
        )

        with pytest.raises(SavedSearchLimitExceededError) as exc_info:
            await service.create_saved_search(
                name="One Too Many",
                description=None,
                query_text="overflow",
                filters={},
                search_mode="hybrid",
                include_internal=False,
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.current_count == _MAX_SAVED_SEARCHES_PER_USER

    @pytest.mark.asyncio
    async def test_list_saved_searches_ordering(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """list_saved_searches returns items ordered by last_executed_at DESC, NULLs last."""
        # Mock count query and items query
        mock_ss_1 = MagicMock()
        mock_ss_1.id = 1
        mock_ss_1.name = "Recent"
        mock_ss_1.description = None
        mock_ss_1.query_text = "q1"
        mock_ss_1.filters = {}
        mock_ss_1.search_mode = "hybrid"
        mock_ss_1.include_internal = False
        mock_ss_1.user_id = 1
        mock_ss_1.company_id = 1
        mock_ss_1.last_executed_at = datetime(2024, 3, 1, tzinfo=timezone.utc)
        mock_ss_1.last_result_count = 10
        mock_ss_1.status = "active"
        mock_ss_1.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_ss_1.updated_at = datetime(2024, 3, 1, tzinfo=timezone.utc)

        mock_ss_2 = MagicMock()
        mock_ss_2.id = 2
        mock_ss_2.name = "Never Executed"
        mock_ss_2.description = None
        mock_ss_2.query_text = "q2"
        mock_ss_2.filters = {}
        mock_ss_2.search_mode = "keyword"
        mock_ss_2.include_internal = True
        mock_ss_2.user_id = 1
        mock_ss_2.company_id = 1
        mock_ss_2.last_executed_at = None
        mock_ss_2.last_result_count = None
        mock_ss_2.status = "active"
        mock_ss_2.created_at = datetime(2024, 2, 1, tzinfo=timezone.utc)
        mock_ss_2.updated_at = datetime(2024, 2, 1, tzinfo=timezone.utc)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Count query
                return _make_scalar_result(2)
            else:
                # Items query
                return _make_scalars_result([mock_ss_1, mock_ss_2])

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        result = await service.list_saved_searches(
            user_id=1,
            company_id=1,
            page=1,
            page_size=20,
        )

        assert result["total_count"] == 2
        assert len(result["items"]) == 2
        # First item should be the most recently executed
        assert result["items"][0]["name"] == "Recent"
        assert result["items"][1]["name"] == "Never Executed"

    @pytest.mark.asyncio
    async def test_execute_saved_search_updates_metadata(
        self, service: LiteratureSearchService, mock_query_engine: AsyncMock, mock_session: AsyncMock
    ):
        """execute_saved_search updates last_executed_at and last_result_count."""
        mock_saved_search = MagicMock()
        mock_saved_search.id = 5
        mock_saved_search.query_text = "saved query"
        mock_saved_search.filters = {}
        mock_saved_search.search_mode = "hybrid"
        mock_saved_search.include_internal = False
        mock_saved_search.last_executed_at = None
        mock_saved_search.last_result_count = None

        # First call: fetch saved search, subsequent calls: search internals
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Fetch saved search
                return _make_scalar_result(mock_saved_search)
            else:
                # Internalization enrichment / other queries
                return _make_scalars_result([])

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        mock_query_engine.unified_search = AsyncMock(
            return_value=FakeHybridSearchResponse(
                results=[],
                total_count=5,
                page=1,
                page_size=20,
            )
        )

        log_entry_mock = MagicMock()
        log_entry_mock.id = 300

        with patch(
            "alcoabase.literature.search.services.literature_search_service.SearchExecutionLog"
        ) as MockLog:
            MockLog.return_value = log_entry_mock

            result = await service.execute_saved_search(
                saved_search_id=5,
                user_id=1,
                company_id=1,
            )

        # Verify metadata was updated
        assert mock_saved_search.last_executed_at is not None
        assert mock_saved_search.last_result_count == 5

    @pytest.mark.asyncio
    async def test_delete_saved_search_soft_delete(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """delete_saved_search sets status to 'archived'."""
        mock_saved_search = MagicMock()
        mock_saved_search.id = 10
        mock_saved_search.user_id = 1
        mock_saved_search.status = "active"

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_saved_search))

        await service.delete_saved_search(
            saved_search_id=10,
            user_id=1,
            company_id=1,
        )

        assert mock_saved_search.status == "archived"
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_saved_search_non_owner_non_admin_rejected(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """delete_saved_search raises ValueError for non-owner without admin role."""
        mock_saved_search = MagicMock()
        mock_saved_search.id = 10
        mock_saved_search.user_id = 99  # Different user
        mock_saved_search.status = "active"

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_saved_search))

        with pytest.raises(ValueError, match="Insufficient permissions"):
            await service.delete_saved_search(
                saved_search_id=10,
                user_id=1,
                company_id=1,
                user_role="member",
            )

    @pytest.mark.asyncio
    async def test_delete_saved_search_admin_override(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """delete_saved_search allows document_admin to delete another user's search."""
        mock_saved_search = MagicMock()
        mock_saved_search.id = 10
        mock_saved_search.user_id = 99  # Different user
        mock_saved_search.status = "active"

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_saved_search))

        await service.delete_saved_search(
            saved_search_id=10,
            user_id=1,
            company_id=1,
            user_role="document_admin",
        )

        assert mock_saved_search.status == "archived"


# ---------------------------------------------------------------------------
# Citation Collection Tests
# ---------------------------------------------------------------------------


class TestCitationCollections:
    """Tests for citation collection CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_citation_collection_success(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """create_citation_collection creates with valid purpose."""
        mock_collection = MagicMock()
        mock_collection.id = 1
        mock_collection.name = "MDR CER Q1 2025"
        mock_collection.description = "Clinical evaluation literature"
        mock_collection.purpose = "clinical_evaluation"
        mock_collection.status = "active"
        mock_collection.document_count = 0
        mock_collection.documents = []
        mock_collection.created_by = 1
        mock_collection.company_id = 1
        mock_collection.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_collection.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        async def mock_refresh(obj):
            for attr in ("id", "name", "description", "purpose", "status",
                         "documents", "created_by", "company_id", "created_at", "updated_at"):
                setattr(obj, attr, getattr(mock_collection, attr))

        mock_session.refresh = AsyncMock(side_effect=mock_refresh)

        result = await service.create_citation_collection(
            name="MDR CER Q1 2025",
            description="Clinical evaluation literature",
            purpose="clinical_evaluation",
            user_id=1,
            company_id=1,
        )

        assert result["name"] == "MDR CER Q1 2025"
        assert result["purpose"] == "clinical_evaluation"
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_create_citation_collection_invalid_purpose(
        self, service: LiteratureSearchService
    ):
        """create_citation_collection raises ValueError for invalid purpose."""
        with pytest.raises(ValueError, match="Invalid purpose"):
            await service.create_citation_collection(
                name="Bad Collection",
                description=None,
                purpose="invalid_purpose",
                user_id=1,
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_list_citation_collections(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """list_citation_collections returns paginated results."""
        mock_coll = MagicMock()
        mock_coll.id = 1
        mock_coll.name = "Collection 1"
        mock_coll.description = None
        mock_coll.purpose = "risk_assessment"
        mock_coll.status = "active"
        mock_coll.documents = []
        mock_coll.created_by = 1
        mock_coll.company_id = 1
        mock_coll.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_coll.updated_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(1)  # count
            return _make_scalars_result([mock_coll])

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        result = await service.list_citation_collections(
            company_id=1,
            page=1,
            page_size=20,
        )

        assert result["total_count"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["purpose"] == "risk_assessment"

    @pytest.mark.asyncio
    async def test_delete_citation_collection_soft_delete(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """delete_citation_collection sets status to 'archived'."""
        mock_coll = MagicMock()
        mock_coll.id = 5
        mock_coll.status = "active"

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_coll))

        await service.delete_citation_collection(
            collection_id=5,
            company_id=1,
        )

        assert mock_coll.status == "archived"
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_citation_collection_not_found(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """delete_citation_collection raises ValueError when not found."""
        mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

        with pytest.raises(ValueError, match="not found"):
            await service.delete_citation_collection(
                collection_id=999,
                company_id=1,
            )


# ---------------------------------------------------------------------------
# Collection Document Management Tests
# ---------------------------------------------------------------------------


class TestCollectionDocumentManagement:
    """Tests for add/remove documents in citation collections."""

    @pytest.mark.asyncio
    async def test_add_documents_validates_internalized_only(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """add_documents_to_collection raises NonInternalizedDocumentError for non-internalized docs."""
        mock_collection = MagicMock()
        mock_collection.id = 1

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection lookup
                return _make_scalar_result(mock_collection)
            elif call_count[0] == 2:
                # Document lookup - returns doc with source_ingestion_record_id=None
                mock_result = MagicMock()
                mock_result.all.return_value = [(10, None)]  # doc_id=10, no source_ir_id
                return mock_result
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(NonInternalizedDocumentError):
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[10],
                user_id=1,
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_add_documents_enforces_500_limit(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """add_documents_to_collection raises CollectionCapacityExceededError at 500."""
        mock_collection = MagicMock()
        mock_collection.id = 1

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection lookup
                return _make_scalar_result(mock_collection)
            elif call_count[0] == 2:
                # Document lookup - valid internalized doc
                mock_result = MagicMock()
                mock_result.all.return_value = [(10, 42)]  # doc_id=10, source_ir_id=42
                return mock_result
            elif call_count[0] == 3:
                # Current count of docs in collection = 500
                return _make_scalar_result(_MAX_COLLECTION_DOCUMENTS)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(CollectionCapacityExceededError):
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[10],
                user_id=1,
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_remove_document_from_collection_preserves_document(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """remove_document_from_collection deletes junction but Document remains."""
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection ownership check
                return _make_scalar_result(1)  # collection exists
            else:
                # Delete junction record
                mock_result = MagicMock()
                mock_result.rowcount = 1
                return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        # Should not raise
        await service.remove_document_from_collection(
            collection_id=1,
            document_id=10,
            user_id=1,
            company_id=1,
        )

        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_remove_document_not_in_collection(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """remove_document_from_collection raises ValueError if not in collection."""
        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(1)  # collection exists
            else:
                mock_result = MagicMock()
                mock_result.rowcount = 0
                return mock_result

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(ValueError, match="not in collection"):
            await service.remove_document_from_collection(
                collection_id=1,
                document_id=99,
                user_id=1,
                company_id=1,
            )


# ---------------------------------------------------------------------------
# Traceability Link Tests
# ---------------------------------------------------------------------------


class TestTraceabilityLinks:
    """Tests for traceability link CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_traceability_links_validates_internalized(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """create_traceability_links raises NonInternalizedDocumentError if not internalized."""
        mock_document = MagicMock()
        mock_document.id = 10
        mock_document.company_id = 1
        mock_document.source_ingestion_record_id = None

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_document))

        with pytest.raises(NonInternalizedDocumentError):
            await service.create_traceability_links(
                document_id=10,
                links=[{"target_type": "requirement", "target_id": 1}],
                user_id=1,
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_create_traceability_links_success(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """create_traceability_links creates links for internalized document."""
        mock_document = MagicMock()
        mock_document.id = 10
        mock_document.company_id = 1
        mock_document.source_ingestion_record_id = 42  # Is internalized

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_document))

        # Mock the link creation (flush sets id)
        link_id_counter = [0]
        original_flush = mock_session.flush

        async def mock_flush():
            link_id_counter[0] += 1
            # Find the last added object and set its id
            if mock_session.add.call_args:
                obj = mock_session.add.call_args[0][0]
                obj.id = link_id_counter[0]

        mock_session.flush = AsyncMock(side_effect=mock_flush)

        result = await service.create_traceability_links(
            document_id=10,
            links=[
                {"target_type": "requirement", "target_id": 1, "rationale": "Supports claim"},
                {"target_type": "test_case", "target_id": 2},
            ],
            user_id=1,
            company_id=1,
        )

        assert len(result) == 2
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_list_traceability_links_filtering(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """list_traceability_links returns filtered, paginated results."""
        mock_link = MagicMock()
        mock_link.id = 1
        mock_link.document_id = 10
        mock_link.target_type = "requirement"
        mock_link.target_id = 5
        mock_link.rationale = "Evidence for requirement"
        mock_link.link_method = "literature_evidence"
        mock_link.link_confidence = 1.0
        mock_link.created_by = 1
        mock_link.company_id = 1
        mock_link.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Count query
                return _make_scalar_result(1)
            else:
                # Items query
                return _make_scalars_result([mock_link])

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        result = await service.list_traceability_links(
            company_id=1,
            document_id=10,
            page=1,
            page_size=20,
        )

        assert result["total_count"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["target_type"] == "requirement"
        assert result["items"][0]["link_method"] == "literature_evidence"

    @pytest.mark.asyncio
    async def test_delete_traceability_link_success(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """delete_traceability_link removes the link and commits."""
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_session.execute = AsyncMock(return_value=mock_result)

        await service.delete_traceability_link(
            link_id=1,
            user_id=1,
            company_id=1,
        )

        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_delete_traceability_link_not_found(
        self, service: LiteratureSearchService, mock_session: AsyncMock
    ):
        """delete_traceability_link raises ValueError when link not found."""
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="not found"):
            await service.delete_traceability_link(
                link_id=999,
                user_id=1,
                company_id=1,
            )
