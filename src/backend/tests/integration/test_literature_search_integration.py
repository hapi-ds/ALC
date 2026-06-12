"""Integration tests for the literature search and audit pipeline (Phase 9.6).

Tests cross-service flows that exercise the LiteratureSearchService
orchestration logic, verifying correct interaction between:
- HybridQueryEngine (mocked OpenSearch)
- SearchExecutionLog creation and immutability
- Audit trail logging with Celery retry fallback
- Saved search lifecycle (create → execute → archive)
- Search modes (keyword, semantic, hybrid)

These tests mock the infrastructure layer (OpenSearch, Redis, PostgreSQL)
while testing real service integration logic across method boundaries.

References:
    - Task 14.1: Write integration tests for search and audit pipeline
    - Requirements: 1.1–1.10, 2.1–2.5, 3.1–3.8
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base
from alcoabase.literature.search.models import (
    SavedSearch,
    SearchExecutionLog,
)
from alcoabase.literature.search.services.literature_search_service import (
    LiteratureSearchService,
)

# Disable SQLAlchemy-Continuum's session tracking globally for these tests.
# The SavedSearch model uses AuditMixin (__versioned__) which triggers
# Continuum's before_flush hook requiring a 'transaction' table.
# We patch the UoW methods to avoid needing version/transaction tables.
_continuum_patch_before = patch(
    "sqlalchemy_continuum.unit_of_work.UnitOfWork.process_before_flush",
    lambda *a, **kw: None,
)
_continuum_patch_after = patch(
    "sqlalchemy_continuum.unit_of_work.UnitOfWork.process_after_flush",
    lambda *a, **kw: None,
)

pytestmark = pytest.mark.usefixtures("_disable_continuum")


# ---------------------------------------------------------------------------
# Dataclasses to simulate HybridQueryEngine responses without real OpenSearch
# ---------------------------------------------------------------------------


@dataclass
class FakeSearchResult:
    """Simulates a HybridSearchResult from the HybridQueryEngine."""

    chunk_text: str = "Abstract text for testing purposes."
    title: str = "Sample Paper Title"
    authors: list[str] = field(default_factory=lambda: ["Author A", "Author B"])
    doi: str | None = "10.1000/test.2025.001"
    publication_date: str | None = "2025-01-15"
    source_id: str | None = "pubmed"
    relevance_score: float = 0.85
    partition_tag: str = "public_literature"
    section_heading: str = "Methods"
    ingestion_record_id: int = 101


@dataclass
class FakeSearchResponse:
    """Simulates a HybridSearchResponse from the HybridQueryEngine."""

    results: list[FakeSearchResult] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    page_size: int = 20


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _disable_continuum():
    """Disable SQLAlchemy-Continuum version tracking for integration tests.

    Patches the UnitOfWork process methods so versioned models (SavedSearch)
    can be persisted without requiring the 'transaction' table.
    """
    with _continuum_patch_before, _continuum_patch_after:
        yield


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite in-memory engine for integration tests.

    Creates only the tables needed for literature search integration testing.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.close()

    async with engine.begin() as conn:
        # Create tables needed for the service (using raw SQL for SQLite compat)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(100) NOT NULL,
                email VARCHAR(200) NOT NULL,
                hashed_password VARCHAR(500) NOT NULL,
                is_active BOOLEAN DEFAULT 1
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug VARCHAR(100) NOT NULL,
                display_name VARCHAR(200) NOT NULL,
                is_active BOOLEAN DEFAULT 1
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS literature_saved_searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(200) NOT NULL,
                description TEXT,
                query_text TEXT NOT NULL,
                filters TEXT NOT NULL DEFAULT '{}',
                search_mode VARCHAR(20) NOT NULL DEFAULT 'hybrid',
                include_internal BOOLEAN NOT NULL DEFAULT 0,
                user_id INTEGER NOT NULL REFERENCES users(id),
                company_id INTEGER NOT NULL REFERENCES companies(id),
                last_executed_at DATETIME,
                last_result_count INTEGER,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS literature_search_execution_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                company_id INTEGER NOT NULL REFERENCES companies(id),
                query_text TEXT NOT NULL,
                filters TEXT NOT NULL DEFAULT '{}',
                search_mode VARCHAR(20) NOT NULL,
                include_internal BOOLEAN NOT NULL,
                total_results INTEGER NOT NULL,
                sources_queried TEXT NOT NULL,
                execution_duration_ms INTEGER NOT NULL,
                saved_search_id INTEGER REFERENCES literature_saved_searches(id),
                executed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_uuid VARCHAR(50),
                title VARCHAR(500),
                folder_path VARCHAR(500),
                document_type VARCHAR(50),
                current_status VARCHAR(50),
                created_by INTEGER,
                company_id INTEGER,
                source_ingestion_record_id INTEGER,
                full_text_status VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        # Seed a user and company
        await conn.execute(text(
            "INSERT INTO users (id, username, email, hashed_password, is_active) "
            "VALUES (1, 'admin', 'admin@test.local', 'hashed', 1)"
        ))
        await conn.execute(text(
            "INSERT INTO users (id, username, email, hashed_password, is_active) "
            "VALUES (2, 'user2', 'user2@test.local', 'hashed', 1)"
        ))
        await conn.execute(text(
            "INSERT INTO companies (id, slug, display_name, is_active) "
            "VALUES (1, 'pharma-a', 'Pharma A', 1)"
        ))
        await conn.execute(text(
            "INSERT INTO companies (id, slug, display_name, is_active) "
            "VALUES (2, 'pharma-b', 'Pharma B', 1)"
        ))

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_engine):
    """Create an async session factory bound to the test engine."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncSession:
    """Provide a database session for integration tests."""
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
def mock_query_engine():
    """Create a mock HybridQueryEngine returning configurable results."""
    engine = AsyncMock()
    # Default: return 3 results
    results = [
        FakeSearchResult(
            title=f"Paper {i}",
            ingestion_record_id=100 + i,
            relevance_score=0.9 - i * 0.1,
            source_id="pubmed",
        )
        for i in range(3)
    ]
    response = FakeSearchResponse(results=results, total_count=3, page=1, page_size=20)
    engine.unified_search = AsyncMock(return_value=response)
    return engine


@pytest_asyncio.fixture
def mock_audit_service():
    """Create a mock AuditTrailService."""
    return AsyncMock()


@pytest_asyncio.fixture
def mock_traceability_service():
    """Create a mock TraceabilityMatrixService."""
    return AsyncMock()


@pytest_asyncio.fixture
def mock_storage_client():
    """Create a mock S3/MinIO storage client."""
    client = AsyncMock()
    client.copy_object = AsyncMock()
    return client


@pytest_asyncio.fixture
def search_service(
    db_session,
    mock_query_engine,
    mock_audit_service,
    mock_traceability_service,
    mock_storage_client,
):
    """Create a LiteratureSearchService wired to the test session and mocks."""
    return LiteratureSearchService(
        session=db_session,
        hybrid_query_engine=mock_query_engine,
        audit_trail_service=mock_audit_service,
        traceability_matrix_service=mock_traceability_service,
        storage_client=mock_storage_client,
    )


# ---------------------------------------------------------------------------
# Test: Full Search Flow → SearchExecutionLog creation
# ---------------------------------------------------------------------------


class TestFullSearchFlow:
    """Test the end-to-end search flow including audit log creation."""

    @pytest.mark.asyncio
    async def test_execute_search_creates_execution_log(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Execute query → verify SearchExecutionLog created with correct fields."""
        result = await search_service.execute_search(
            query_text="stainless steel biocompatibility",
            filters={"journals": ["Biomaterials"]},
            search_mode="hybrid",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        # Verify response structure
        assert "results" in result
        assert "pagination" in result
        assert "facets" in result
        assert "search_execution_id" in result
        assert result["pagination"]["total_results"] == 3
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["page_size"] == 20

        # Verify SearchExecutionLog was written to the database
        log_id = result["search_execution_id"]
        row = await db_session.execute(
            text("SELECT * FROM literature_search_execution_logs WHERE id = :id"),
            {"id": log_id},
        )
        log_entry = row.mappings().one()
        assert log_entry["user_id"] == 1
        assert log_entry["company_id"] == 1
        assert log_entry["query_text"] == "stainless steel biocompatibility"
        assert log_entry["search_mode"] == "hybrid"
        assert log_entry["include_internal"] == 0  # SQLite stores as 0/1
        assert log_entry["total_results"] == 3
        assert log_entry["execution_duration_ms"] >= 0

    @pytest.mark.asyncio
    async def test_execute_search_enriches_results_with_internalization_status(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Search results include is_internalized flag based on documents table."""
        # Pre-populate a document that was internalized from ingestion record 100
        await db_session.execute(text(
            "INSERT INTO documents "
            "(id, document_uuid, title, folder_path, document_type, current_status, "
            "created_by, company_id, source_ingestion_record_id) "
            "VALUES (1, '2025-00001', 'Internalized Paper', '/literature', "
            "'literature', 'Draft', 1, 1, 100)"
        ))
        await db_session.commit()

        result = await search_service.execute_search(
            query_text="biocompatibility",
            filters={},
            search_mode="hybrid",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        # First result has ingestion_record_id=100 → should be marked internalized
        assert result["results"][0]["is_internalized"] is True
        # Others should not be marked internalized
        assert result["results"][1]["is_internalized"] is False
        assert result["results"][2]["is_internalized"] is False

    @pytest.mark.asyncio
    async def test_execute_search_calls_query_engine_with_correct_params(
        self, search_service: LiteratureSearchService, mock_query_engine: AsyncMock
    ) -> None:
        """Verify HybridQueryEngine.unified_search() called with correct request."""
        await search_service.execute_search(
            query_text="medical device safety",
            filters={"sources": ["pubmed"]},
            search_mode="keyword",
            include_internal=True,
            page=2,
            page_size=10,
            user_id=1,
            company_id=1,
        )

        mock_query_engine.unified_search.assert_called_once()
        call_args = mock_query_engine.unified_search.call_args[0][0]
        assert call_args.query == "medical device safety"
        assert call_args.company_id == 1
        assert call_args.user_id == 1
        assert call_args.semantic_weight == 0.0  # keyword mode
        assert call_args.page == 2
        assert call_args.page_size == 10
        assert call_args.include_internal is True


# ---------------------------------------------------------------------------
# Test: Audit Service Unavailability with Celery Retry
# ---------------------------------------------------------------------------


class TestAuditServiceUnavailability:
    """Test search succeeds when audit service is unavailable, with Celery retry."""

    @pytest.mark.asyncio
    async def test_search_succeeds_when_audit_raises(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Search returns results even if audit logging raises an exception.

        The service logs a warning and queues a Celery retry task.
        """
        # Patch _log_audit_event to simulate audit service failure
        with patch.object(
            search_service,
            "_log_audit_event",
            side_effect=Exception("Audit service timeout"),
        ) as mock_audit:
            # Search should NOT propagate the exception — results should be returned
            # But the implementation catches internally; we need to simulate the
            # raw audit write failure. Let's instead patch at a deeper level.
            pass

        # Actually test the retry path by making logger.info raise
        # (which is what _log_audit_event wraps)
        with patch(
            "alcoabase.literature.search.services.literature_search_service.logger.info",
            side_effect=Exception("Logging infrastructure down"),
        ), patch(
            "alcoabase.tasks.literature_search_tasks.retry_audit_log.delay"
        ) as mock_celery_delay:
            result = await search_service.execute_search(
                query_text="audit failure test",
                filters={},
                search_mode="hybrid",
                include_internal=False,
                page=1,
                page_size=20,
                user_id=1,
                company_id=1,
            )

            # Search still succeeds
            assert result["pagination"]["total_results"] == 3
            assert len(result["results"]) == 3

            # Celery retry task was dispatched
            mock_celery_delay.assert_called_once()
            call_kwargs = mock_celery_delay.call_args[1]
            assert call_kwargs["user_id"] == 1
            assert call_kwargs["company_id"] == 1
            assert call_kwargs["record_type"] == "literature_search"

    @pytest.mark.asyncio
    async def test_search_succeeds_when_celery_also_unavailable(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Search returns results even if both audit AND Celery dispatch fail."""
        with patch(
            "alcoabase.literature.search.services.literature_search_service.logger.info",
            side_effect=Exception("Logging infrastructure down"),
        ), patch(
            "alcoabase.tasks.literature_search_tasks.retry_audit_log.delay",
            side_effect=Exception("Redis connection refused"),
        ):
            # Should still not raise — just logs a warning
            result = await search_service.execute_search(
                query_text="total failure test",
                filters={},
                search_mode="hybrid",
                include_internal=False,
                page=1,
                page_size=20,
                user_id=1,
                company_id=1,
            )

            assert result["pagination"]["total_results"] == 3


# ---------------------------------------------------------------------------
# Test: Saved Search Lifecycle
# ---------------------------------------------------------------------------


class TestSavedSearchLifecycle:
    """Test create → execute → verify metadata updated → archive flow."""

    @pytest.mark.asyncio
    async def test_full_saved_search_lifecycle(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Create a saved search, execute it, verify metadata, then archive."""
        # Step 1: Create a saved search
        created = await search_service.create_saved_search(
            name="MDR Literature Review Q1",
            description="Systematic review for clinical evaluation",
            query_text="implantable cardiac devices",
            filters={"journals": ["JACC", "Circulation"]},
            search_mode="hybrid",
            include_internal=False,
            user_id=1,
            company_id=1,
        )

        assert created["name"] == "MDR Literature Review Q1"
        assert created["query_text"] == "implantable cardiac devices"
        assert created["status"] == "active"
        assert created["last_executed_at"] is None
        assert created["last_result_count"] is None
        saved_id = created["id"]

        # Step 2: Execute the saved search
        exec_result = await search_service.execute_saved_search(
            saved_search_id=saved_id,
            user_id=1,
            company_id=1,
        )

        assert exec_result["pagination"]["total_results"] == 3
        assert exec_result["search_execution_id"] is not None

        # Step 3: Verify metadata was updated
        row = await db_session.execute(
            text("SELECT last_executed_at, last_result_count, status "
                 "FROM literature_saved_searches WHERE id = :id"),
            {"id": saved_id},
        )
        updated = row.mappings().one()
        assert updated["last_executed_at"] is not None
        assert updated["last_result_count"] == 3
        assert updated["status"] == "active"

        # Step 4: Verify SearchExecutionLog references the saved_search_id
        log_row = await db_session.execute(
            text("SELECT saved_search_id FROM literature_search_execution_logs "
                 "WHERE saved_search_id = :id"),
            {"id": saved_id},
        )
        log_entry = log_row.mappings().one()
        assert log_entry["saved_search_id"] == saved_id

        # Step 5: Archive the saved search
        await search_service.delete_saved_search(
            saved_search_id=saved_id,
            user_id=1,
            company_id=1,
        )

        # Verify status is archived
        arch_row = await db_session.execute(
            text("SELECT status FROM literature_saved_searches WHERE id = :id"),
            {"id": saved_id},
        )
        archived = arch_row.mappings().one()
        assert archived["status"] == "archived"

    @pytest.mark.asyncio
    async def test_saved_search_listing_excludes_archived(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Archived saved searches do not appear in listings."""
        # Create two searches
        s1 = await search_service.create_saved_search(
            name="Active Search",
            description=None,
            query_text="test query",
            filters={},
            search_mode="keyword",
            include_internal=False,
            user_id=1,
            company_id=1,
        )
        s2 = await search_service.create_saved_search(
            name="To Be Archived",
            description=None,
            query_text="another query",
            filters={},
            search_mode="semantic",
            include_internal=True,
            user_id=1,
            company_id=1,
        )

        # Archive the second one
        await search_service.delete_saved_search(
            saved_search_id=s2["id"],
            user_id=1,
            company_id=1,
        )

        # List should only return the active one
        listing = await search_service.list_saved_searches(
            user_id=1,
            company_id=1,
        )
        assert listing["total_count"] == 1
        assert listing["items"][0]["name"] == "Active Search"

    @pytest.mark.asyncio
    async def test_saved_search_limit_enforcement(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Creating more than 200 active saved searches raises an error."""
        from alcoabase.literature.search.exceptions import SavedSearchLimitExceededError

        # Insert 200 saved searches directly to avoid calling create 200 times
        for i in range(200):
            await db_session.execute(text(
                "INSERT INTO literature_saved_searches "
                "(name, query_text, filters, search_mode, include_internal, "
                "user_id, company_id, status) "
                f"VALUES ('Search {i}', 'query {i}', '{{}}', 'hybrid', 0, 1, 1, 'active')"
            ))
        await db_session.commit()

        # The 201st should fail
        with pytest.raises(SavedSearchLimitExceededError):
            await search_service.create_saved_search(
                name="One Too Many",
                description=None,
                query_text="overflow",
                filters={},
                search_mode="hybrid",
                include_internal=False,
                user_id=1,
                company_id=1,
            )


# ---------------------------------------------------------------------------
# Test: Search With OpenSearch Mock (Keyword, Semantic, Hybrid Modes)
# ---------------------------------------------------------------------------


class TestSearchModes:
    """Test that search mode selection correctly configures the query engine."""

    @pytest.mark.asyncio
    async def test_keyword_mode_sets_zero_semantic_weight(
        self, search_service: LiteratureSearchService, mock_query_engine: AsyncMock
    ) -> None:
        """Keyword mode passes semantic_weight=0.0 to the query engine."""
        await search_service.execute_search(
            query_text="titanium alloy corrosion",
            filters={},
            search_mode="keyword",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        request = mock_query_engine.unified_search.call_args[0][0]
        assert request.semantic_weight == 0.0

    @pytest.mark.asyncio
    async def test_semantic_mode_sets_full_semantic_weight(
        self, search_service: LiteratureSearchService, mock_query_engine: AsyncMock
    ) -> None:
        """Semantic mode passes semantic_weight=1.0 to the query engine."""
        await search_service.execute_search(
            query_text="biocompatibility mechanisms",
            filters={},
            search_mode="semantic",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        request = mock_query_engine.unified_search.call_args[0][0]
        assert request.semantic_weight == 1.0

    @pytest.mark.asyncio
    async def test_hybrid_mode_sets_balanced_semantic_weight(
        self, search_service: LiteratureSearchService, mock_query_engine: AsyncMock
    ) -> None:
        """Hybrid mode passes semantic_weight=0.5 to the query engine."""
        await search_service.execute_search(
            query_text="polymer degradation in vivo",
            filters={},
            search_mode="hybrid",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        request = mock_query_engine.unified_search.call_args[0][0]
        assert request.semantic_weight == 0.5

    @pytest.mark.asyncio
    async def test_each_mode_produces_valid_execution_log(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """All three modes create correctly tagged SearchExecutionLog entries."""
        modes = ["keyword", "semantic", "hybrid"]
        for mode in modes:
            await search_service.execute_search(
                query_text=f"test {mode}",
                filters={},
                search_mode=mode,
                include_internal=False,
                page=1,
                page_size=20,
                user_id=1,
                company_id=1,
            )

        # Verify 3 log entries with correct search_mode values
        rows = await db_session.execute(
            text("SELECT search_mode FROM literature_search_execution_logs "
                 "ORDER BY id")
        )
        modes_recorded = [r[0] for r in rows.fetchall()]
        assert modes_recorded == ["keyword", "semantic", "hybrid"]

    @pytest.mark.asyncio
    async def test_search_with_filters_passes_to_query_engine(
        self, search_service: LiteratureSearchService, mock_query_engine: AsyncMock
    ) -> None:
        """Filters are correctly passed through to the HybridQueryEngine."""
        filters = {
            "date_from": "2024-01-01",
            "date_to": "2025-06-30",
            "sources": ["pubmed"],
            "publication_types": ["journal_article"],
        }
        await search_service.execute_search(
            query_text="cardiac stent longevity",
            filters=filters,
            search_mode="hybrid",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        request = mock_query_engine.unified_search.call_args[0][0]
        assert request.date_range_start == "2024-01-01"
        assert request.date_range_end == "2025-06-30"
        assert request.source_id == "pubmed"
        assert request.publication_type == "journal_article"

    @pytest.mark.asyncio
    async def test_search_with_empty_results(
        self, search_service: LiteratureSearchService, mock_query_engine: AsyncMock
    ) -> None:
        """Search returning no results still creates a valid execution log."""
        empty_response = FakeSearchResponse(results=[], total_count=0, page=1, page_size=20)
        mock_query_engine.unified_search = AsyncMock(return_value=empty_response)

        result = await search_service.execute_search(
            query_text="obscure topic with no matches",
            filters={},
            search_mode="hybrid",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        assert result["results"] == []
        assert result["pagination"]["total_results"] == 0
        assert result["search_execution_id"] is not None


# ---------------------------------------------------------------------------
# Test: Execution Log Creation Correctness
# ---------------------------------------------------------------------------


class TestExecutionLogCorrectness:
    """Test that SearchExecutionLog records are complete and accurate."""

    @pytest.mark.asyncio
    async def test_execution_log_captures_duration(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Execution duration is recorded and is a positive integer."""
        result = await search_service.execute_search(
            query_text="duration test",
            filters={},
            search_mode="hybrid",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        row = await db_session.execute(
            text("SELECT execution_duration_ms FROM literature_search_execution_logs "
                 "WHERE id = :id"),
            {"id": result["search_execution_id"]},
        )
        duration = row.scalar_one()
        assert isinstance(duration, int)
        assert duration >= 0

    @pytest.mark.asyncio
    async def test_execution_log_records_include_internal_flag(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Execution log correctly records include_internal as True."""
        result = await search_service.execute_search(
            query_text="internal doc test",
            filters={},
            search_mode="hybrid",
            include_internal=True,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        row = await db_session.execute(
            text("SELECT include_internal FROM literature_search_execution_logs "
                 "WHERE id = :id"),
            {"id": result["search_execution_id"]},
        )
        include_internal = row.scalar_one()
        # SQLite stores booleans as 0/1
        assert include_internal in (True, 1)

    @pytest.mark.asyncio
    async def test_execution_log_sources_queried_populated(
        self, search_service: LiteratureSearchService, db_session: AsyncSession
    ) -> None:
        """Execution log captures sources_queried from result metadata."""
        result = await search_service.execute_search(
            query_text="sources test",
            filters={},
            search_mode="hybrid",
            include_internal=False,
            page=1,
            page_size=20,
            user_id=1,
            company_id=1,
        )

        row = await db_session.execute(
            text("SELECT sources_queried FROM literature_search_execution_logs "
                 "WHERE id = :id"),
            {"id": result["search_execution_id"]},
        )
        sources = row.scalar_one()
        # Should contain at least "literature_index" (always added) and "pubmed" (from results)
        assert sources is not None
        assert "literature_index" in str(sources)
