"""Integration tests for AI-Driven Change Impact Analysis API endpoints.

Tests all 12 endpoints with an in-memory SQLite database, verifying HTTP
status codes, pagination, filtering, X-Change-Reason enforcement, and
error responses (404, 409, 422, 503).

References:
    - Task 10.4: Write integration tests for API endpoints
    - Requirements: 1.1–1.15, 2.4–2.5, 4.1–4.11, 5.3–5.4, 6.3–6.9, 8.2–8.3, 8.5
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import configure_mappers

from alcoabase.database import Base, get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.impact_analysis import (
    DependencyEdge,
    GapAnalysisResult,
    ImpactNotification,
    ImpactReport,
)
from alcoabase.models.user import User
from alcoabase.models.video import ProcessingJob


# Render JSONB as JSON in SQLite (must be registered before configure_mappers)
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


configure_mappers()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPANY_ID = 1
USER_ID = 1
DOC_UUID_1 = "2025-00001"
DOC_UUID_2 = "2025-00002"
DOC_UUID_3 = "2025-00003"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite in-memory engine for integration tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_engine):
    """Create an async session factory bound to the test engine."""
    return async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct test setup operations."""
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Seed the database with base data: user, company, membership, documents."""
    user = User(
        id=USER_ID,
        username="testuser",
        email="test@alcoabase.local",
        hashed_password="hashed_placeholder",
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    company = Company(
        id=COMPANY_ID,
        slug="test-co",
        display_name="Test Company",
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    membership = CompanyMembership(
        user_id=USER_ID, company_id=COMPANY_ID, role="admin"
    )
    db_session.add(membership)
    await db_session.flush()

    # Create documents
    for i, (doc_uuid, title) in enumerate(
        [
            (DOC_UUID_1, "URS Document"),
            (DOC_UUID_2, "MVP Document"),
            (DOC_UUID_3, "SOP Document"),
        ],
        start=1,
    ):
        doc = Document(
            id=i,
            document_uuid=doc_uuid,
            title=title,
            folder_path="/docs",
            document_type="SOP",
            current_status="Approved",
            created_by=USER_ID,
            company_id=COMPANY_ID,
        )
        db_session.add(doc)
    await db_session.flush()

    # Create a document version for doc 1
    version = DocumentVersion(
        id=1,
        document_id=1,
        major_version=1,
        minor_version=0,
        storage_key="documents/2025-00001/1.0/file.pdf",
        file_hash="a" * 128,
        uploaded_by=USER_ID,
        change_reason="Initial upload",
    )
    db_session.add(version)
    await db_session.flush()
    await db_session.commit()


@pytest_asyncio.fixture
async def client(
    session_factory, seeded_db
) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient with overridden dependencies."""

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=COMPANY_ID,
            company_slug="test-co",
            user_id=USER_ID,
            membership_role="admin",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": str(USER_ID),
            "X-Company-Id": str(COMPANY_ID),
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_reason(
    session_factory, seeded_db
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient WITHOUT X-Change-Reason header for testing enforcement."""

    async def _override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _override_get_tenant_context():
        return TenantContext(
            company_id=COMPANY_ID,
            company_slug="test-co",
            user_id=USER_ID,
            membership_role="admin",
        )

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": str(USER_ID),
            "X-Company-Id": str(COMPANY_ID),
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: seed additional data for specific tests
# ---------------------------------------------------------------------------


async def seed_dependency_edge(
    session_factory,
    source_uuid: str = DOC_UUID_1,
    target_uuid: str = DOC_UUID_2,
    dep_type: str = "validates",
    confidence: float = 0.9,
) -> DependencyEdge:
    """Insert a dependency edge into the database."""
    async with session_factory() as session:
        edge = DependencyEdge(
            source_document_uuid=source_uuid,
            target_document_uuid=target_uuid,
            dependency_type=dep_type,
            confidence_score=confidence,
            detected_references=["REQ-001"],
            last_verified_at=datetime.now(timezone.utc),
            company_id=COMPANY_ID,
        )
        session.add(edge)
        await session.commit()
        await session.refresh(edge)
        return edge


async def seed_processing_job(
    session_factory,
    job_id: str | None = None,
    document_id: int = 1,
    operation: str = "change_impact_analysis",
    status: str = "processing",
    progress: int = 50,
) -> ProcessingJob:
    """Insert a processing job into the database."""
    async with session_factory() as session:
        job = ProcessingJob(
            job_id=job_id or str(uuid.uuid4()),
            document_id=document_id,
            operation=operation,
            status=status,
            progress_percent=progress,
            company_id=COMPANY_ID,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


async def seed_impact_report(
    session_factory,
    report_id: str | None = None,
    triggering_uuid: str = DOC_UUID_1,
) -> ImpactReport:
    """Insert an impact report into the database."""
    async with session_factory() as session:
        report = ImpactReport(
            report_id=report_id or str(uuid.uuid4()),
            triggering_document_uuid=triggering_uuid,
            triggering_version_id=1,
            change_delta_summary={
                "sections_added": [],
                "sections_modified": [{"heading": "Section 1"}],
                "sections_deleted": [],
                "significance_levels": {"high": 1, "medium": 0, "low": 0},
            },
            affected_items=[],
            gap_findings=[],
            status="completed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=5000,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=1500,
            requesting_user_id=USER_ID,
            company_id=COMPANY_ID,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return report


async def seed_gap_analysis_result(
    session_factory,
    job_id: str,
    status: str = "completed",
) -> GapAnalysisResult:
    """Insert a gap analysis result into the database."""
    async with session_factory() as session:
        result = GapAnalysisResult(
            job_id=job_id,
            source_document_uuid=DOC_UUID_1,
            target_document_uuid=DOC_UUID_2,
            gap_findings=[
                {
                    "source_section": "Section 1.1",
                    "source_content_excerpt": "Requirement A",
                    "target_section": "not_found",
                    "target_content_excerpt": "",
                    "gap_type": "missing",
                    "severity": "major",
                    "remediation_suggestion": "Add coverage",
                    "inference_prompt_summary": "prompt",
                    "model_response_summary": "response",
                    "token_count": 200,
                }
            ],
            total_gaps_detected=1,
            gaps_retained=1,
            status=status,
            analysis_duration_ms=3000,
            company_id=COMPANY_ID,
        )
        session.add(result)
        await session.commit()
        await session.refresh(result)
        return result


async def seed_notification(
    session_factory,
    notification_id: int | None = None,
    severity: str = "critical",
    acknowledged: bool = False,
) -> ImpactNotification:
    """Insert an impact notification into the database."""
    async with session_factory() as session:
        notif = ImpactNotification(
            report_id=str(uuid.uuid4()),
            affected_document_uuid=DOC_UUID_2,
            notification_type="change_impact",
            impact_severity=severity,
            change_summary="Test change summary",
            target_user_id=USER_ID,
            is_acknowledged=acknowledged,
            company_id=COMPANY_ID,
        )
        if notification_id:
            notif.id = notification_id
        session.add(notif)
        await session.commit()
        await session.refresh(notif)
        return notif


# ---------------------------------------------------------------------------
# Test: POST /dependency-graph/build → 202
# ---------------------------------------------------------------------------


class TestBuildDependencyGraph:
    """Tests for POST /api/impact-analysis/dependency-graph/build."""

    @pytest.mark.asyncio
    async def test_build_returns_202_with_job_id(
        self, client: AsyncClient
    ) -> None:
        """Successful build request returns 202 with a job_id."""
        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock()
            resp = await client.post(
                "/api/impact-analysis/dependency-graph/build",
                json={"scope": "full"},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        # Validate job_id is a valid UUID
        uuid.UUID(data["job_id"])

    @pytest.mark.asyncio
    async def test_build_returns_503_when_celery_unavailable(
        self, client: AsyncClient
    ) -> None:
        """Returns 503 when Celery broker is unavailable."""
        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock(
                side_effect=Exception("Broker unavailable")
            )
            resp = await client.post(
                "/api/impact-analysis/dependency-graph/build",
                json={"scope": "incremental"},
            )
        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_build_requires_x_change_reason(
        self, client_no_reason: AsyncClient
    ) -> None:
        """Mutation endpoint requires X-Change-Reason header."""
        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock()
            resp = await client_no_reason.post(
                "/api/impact-analysis/dependency-graph/build",
                json={"scope": "full"},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: GET /dependency-graph → paginated edges
# ---------------------------------------------------------------------------


class TestListDependencyEdges:
    """Tests for GET /api/impact-analysis/dependency-graph."""

    @pytest.mark.asyncio
    async def test_list_edges_empty(self, client: AsyncClient) -> None:
        """Returns empty list when no edges exist."""
        resp = await client.get("/api/impact-analysis/dependency-graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["edges"] == []
        assert data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_list_edges_with_data(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns edges with pagination metadata."""
        await seed_dependency_edge(session_factory)
        await seed_dependency_edge(
            session_factory,
            source_uuid=DOC_UUID_2,
            target_uuid=DOC_UUID_3,
            dep_type="references",
        )

        resp = await client.get("/api/impact-analysis/dependency-graph")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert len(data["edges"]) == 2

    @pytest.mark.asyncio
    async def test_list_edges_with_filter(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Filters edges by source_document_uuid."""
        await seed_dependency_edge(session_factory)
        await seed_dependency_edge(
            session_factory,
            source_uuid=DOC_UUID_2,
            target_uuid=DOC_UUID_3,
            dep_type="references",
        )

        resp = await client.get(
            "/api/impact-analysis/dependency-graph",
            params={"source_document_uuid": DOC_UUID_1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["edges"][0]["source_document_uuid"] == DOC_UUID_1

    @pytest.mark.asyncio
    async def test_list_edges_pagination(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Respects limit and offset parameters."""
        await seed_dependency_edge(session_factory)
        await seed_dependency_edge(
            session_factory,
            source_uuid=DOC_UUID_2,
            target_uuid=DOC_UUID_3,
            dep_type="references",
        )

        resp = await client.get(
            "/api/impact-analysis/dependency-graph",
            params={"limit": 1, "offset": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["edges"]) == 1
        assert data["total_count"] == 2


# ---------------------------------------------------------------------------
# Test: GET /dependency-graph/{document_uuid} → grouped dependencies
# ---------------------------------------------------------------------------


class TestGetDocumentDependencies:
    """Tests for GET /api/impact-analysis/dependency-graph/{document_uuid}."""

    @pytest.mark.asyncio
    async def test_get_document_deps_returns_grouped(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns upstream and downstream edges grouped by type."""
        await seed_dependency_edge(session_factory)

        resp = await client.get(
            f"/api/impact-analysis/dependency-graph/{DOC_UUID_1}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_uuid"] == DOC_UUID_1
        assert "upstream" in data
        assert "downstream" in data

    @pytest.mark.asyncio
    async def test_get_document_deps_404_for_missing_doc(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when document_uuid is not in company scope."""
        resp = await client.get(
            "/api/impact-analysis/dependency-graph/9999-99999"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: POST /trigger → 202, 409, 404
# ---------------------------------------------------------------------------


class TestTriggerImpactAnalysis:
    """Tests for POST /api/impact-analysis/trigger."""

    @pytest.mark.asyncio
    async def test_trigger_returns_202(
        self, client: AsyncClient
    ) -> None:
        """Successful trigger returns 202 with job_id."""
        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock()
            resp = await client.post(
                "/api/impact-analysis/trigger",
                json={"document_id": 1},
            )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        uuid.UUID(data["job_id"])

    @pytest.mark.asyncio
    async def test_trigger_returns_404_for_missing_document(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when document_id does not exist."""
        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock()
            resp = await client.post(
                "/api/impact-analysis/trigger",
                json={"document_id": 9999},
            )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_trigger_returns_409_for_concurrent_job(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 409 when an active non-stale job exists."""
        await seed_processing_job(session_factory, document_id=1)

        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock()
            resp = await client.post(
                "/api/impact-analysis/trigger",
                json={"document_id": 1},
            )
        assert resp.status_code == 409
        assert "already in progress" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_trigger_requires_x_change_reason(
        self, client_no_reason: AsyncClient
    ) -> None:
        """Mutation endpoint requires X-Change-Reason header."""
        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock()
            resp = await client_no_reason.post(
                "/api/impact-analysis/trigger",
                json={"document_id": 1},
            )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: POST /gap-analysis → 202, 422, 404
# ---------------------------------------------------------------------------


class TestTriggerGapAnalysis:
    """Tests for POST /api/impact-analysis/gap-analysis."""

    @pytest.mark.asyncio
    async def test_gap_analysis_returns_202(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Successful gap analysis request returns 202 with job_id."""
        # Need a dependency edge between the two docs
        await seed_dependency_edge(session_factory)

        with patch(
            "alcoabase.tasks.celery_app.celery_app"
        ) as mock_celery:
            mock_celery.send_task = MagicMock()
            resp = await client.post(
                "/api/impact-analysis/gap-analysis",
                json={
                    "source_document_id": 1,
                    "target_document_id": 2,
                },
            )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        uuid.UUID(data["job_id"])

    @pytest.mark.asyncio
    async def test_gap_analysis_422_same_document(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when source and target are the same document."""
        resp = await client.post(
            "/api/impact-analysis/gap-analysis",
            json={
                "source_document_id": 1,
                "target_document_id": 1,
            },
        )
        assert resp.status_code == 422
        assert "distinct" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_gap_analysis_404_missing_source(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when source document does not exist."""
        resp = await client.post(
            "/api/impact-analysis/gap-analysis",
            json={
                "source_document_id": 9999,
                "target_document_id": 2,
            },
        )
        assert resp.status_code == 404
        assert "source" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_gap_analysis_404_missing_target(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 404 when target document does not exist."""
        resp = await client.post(
            "/api/impact-analysis/gap-analysis",
            json={
                "source_document_id": 1,
                "target_document_id": 9999,
            },
        )
        assert resp.status_code == 404
        assert "target" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_gap_analysis_422_no_dependency(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when no dependency edge exists between documents."""
        resp = await client.post(
            "/api/impact-analysis/gap-analysis",
            json={
                "source_document_id": 1,
                "target_document_id": 2,
            },
        )
        assert resp.status_code == 422
        assert "dependency" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: GET /gap-analysis/{job_id}/results → findings, 202, 404
# ---------------------------------------------------------------------------


class TestGetGapAnalysisResults:
    """Tests for GET /api/impact-analysis/gap-analysis/{job_id}/results."""

    @pytest.mark.asyncio
    async def test_results_returns_findings(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns gap findings for a completed job."""
        job_id = str(uuid.uuid4())
        await seed_processing_job(
            session_factory, job_id=job_id, status="completed", progress=100
        )
        await seed_gap_analysis_result(session_factory, job_id=job_id)

        resp = await client.get(
            f"/api/impact-analysis/gap-analysis/{job_id}/results"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["total_count"] == 1
        assert len(data["gap_findings"]) == 1
        assert data["gap_findings"][0]["gap_type"] == "missing"

    @pytest.mark.asyncio
    async def test_results_returns_202_if_processing(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 202 when job is still processing."""
        job_id = str(uuid.uuid4())
        await seed_processing_job(
            session_factory, job_id=job_id, status="processing", progress=40
        )

        resp = await client.get(
            f"/api/impact-analysis/gap-analysis/{job_id}/results"
        )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_results_returns_404_for_unknown_job(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when job_id does not exist."""
        resp = await client.get(
            f"/api/impact-analysis/gap-analysis/{uuid.uuid4()}/results"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: GET /reports → paginated reports with filters
# ---------------------------------------------------------------------------


class TestListReports:
    """Tests for GET /api/impact-analysis/reports."""

    @pytest.mark.asyncio
    async def test_list_reports_empty(self, client: AsyncClient) -> None:
        """Returns empty list when no reports exist."""
        resp = await client.get("/api/impact-analysis/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reports"] == []
        assert data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_list_reports_with_data(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns reports with pagination metadata."""
        await seed_impact_report(session_factory)
        await seed_impact_report(session_factory)

        resp = await client.get("/api/impact-analysis/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert len(data["reports"]) == 2

    @pytest.mark.asyncio
    async def test_list_reports_filter_by_document(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Filters reports by triggering_document_uuid."""
        await seed_impact_report(
            session_factory, triggering_uuid=DOC_UUID_1
        )
        await seed_impact_report(
            session_factory, triggering_uuid=DOC_UUID_2
        )

        resp = await client.get(
            "/api/impact-analysis/reports",
            params={"triggering_document_uuid": DOC_UUID_1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert (
            data["reports"][0]["triggering_document_uuid"] == DOC_UUID_1
        )

    @pytest.mark.asyncio
    async def test_list_reports_pagination(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Respects limit and offset parameters."""
        await seed_impact_report(session_factory)
        await seed_impact_report(session_factory)

        resp = await client.get(
            "/api/impact-analysis/reports",
            params={"limit": 1, "offset": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["reports"]) == 1
        assert data["total_count"] == 2


# ---------------------------------------------------------------------------
# Test: GET /reports/{report_id} → full report, 404, 422
# ---------------------------------------------------------------------------


class TestGetReport:
    """Tests for GET /api/impact-analysis/reports/{report_id}."""

    @pytest.mark.asyncio
    async def test_get_report_returns_full_report(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns full report for a valid report_id."""
        report_id = str(uuid.uuid4())
        await seed_impact_report(session_factory, report_id=report_id)

        resp = await client.get(
            f"/api/impact-analysis/reports/{report_id}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] == report_id
        assert data["status"] == "completed"
        assert "change_delta_summary" in data
        assert "affected_items" in data

    @pytest.mark.asyncio
    async def test_get_report_404_not_found(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when report_id does not exist."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/impact-analysis/reports/{fake_id}"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_report_422_invalid_uuid(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when report_id is not a valid UUID."""
        resp = await client.get(
            "/api/impact-analysis/reports/not-a-uuid"
        )
        assert resp.status_code == 422
        assert "invalid" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: GET /jobs/{job_id}/status → job status, 404
# ---------------------------------------------------------------------------


class TestGetJobStatus:
    """Tests for GET /api/impact-analysis/jobs/{job_id}/status."""

    @pytest.mark.asyncio
    async def test_get_job_status_returns_status(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns job status with progress details."""
        job_id = str(uuid.uuid4())
        await seed_processing_job(
            session_factory, job_id=job_id, status="processing", progress=50
        )

        resp = await client.get(
            f"/api/impact-analysis/jobs/{job_id}/status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "processing"
        assert data["progress_percent"] == 50
        assert data["current_phase"] == "assessing_impact"

    @pytest.mark.asyncio
    async def test_get_job_status_404_not_found(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when job_id does not exist."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/api/impact-analysis/jobs/{fake_id}/status"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: GET /notifications → unacknowledged for user
# ---------------------------------------------------------------------------


class TestListNotifications:
    """Tests for GET /api/impact-analysis/notifications."""

    @pytest.mark.asyncio
    async def test_list_notifications_empty(
        self, client: AsyncClient
    ) -> None:
        """Returns empty list when no notifications exist."""
        resp = await client.get("/api/impact-analysis/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert data["notifications"] == []
        assert data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_list_notifications_returns_unacknowledged(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns only unacknowledged notifications for the user."""
        await seed_notification(session_factory, severity="critical")
        await seed_notification(
            session_factory, severity="major", acknowledged=True
        )

        resp = await client.get("/api/impact-analysis/notifications")
        assert resp.status_code == 200
        data = resp.json()
        # Only the unacknowledged one should be returned
        assert data["total_count"] == 1
        assert data["notifications"][0]["impact_severity"] == "critical"
        assert data["notifications"][0]["is_acknowledged"] is False


# ---------------------------------------------------------------------------
# Test: POST /notifications/{id}/acknowledge → 200, 404
# ---------------------------------------------------------------------------


class TestAcknowledgeNotification:
    """Tests for POST /api/impact-analysis/notifications/{id}/acknowledge."""

    @pytest.mark.asyncio
    async def test_acknowledge_returns_200(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Successful acknowledgment returns 200."""
        notif = await seed_notification(session_factory)

        resp = await client.post(
            f"/api/impact-analysis/notifications/{notif.id}/acknowledge"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_acknowledge_idempotent(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Acknowledging the same notification twice returns 200 both times."""
        notif = await seed_notification(session_factory)

        resp1 = await client.post(
            f"/api/impact-analysis/notifications/{notif.id}/acknowledge"
        )
        assert resp1.status_code == 200

        resp2 = await client.post(
            f"/api/impact-analysis/notifications/{notif.id}/acknowledge"
        )
        assert resp2.status_code == 200

    @pytest.mark.asyncio
    async def test_acknowledge_404_not_found(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when notification does not exist."""
        resp = await client.post(
            "/api/impact-analysis/notifications/99999/acknowledge"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_acknowledge_requires_x_change_reason(
        self, client_no_reason: AsyncClient, session_factory
    ) -> None:
        """Mutation endpoint requires X-Change-Reason header."""
        notif = await seed_notification(session_factory)
        resp = await client_no_reason.post(
            f"/api/impact-analysis/notifications/{notif.id}/acknowledge",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: GET /documents/{document_uuid}/status → document impact status
# ---------------------------------------------------------------------------


class TestGetDocumentImpactStatus:
    """Tests for GET /api/impact-analysis/documents/{document_uuid}/status."""

    @pytest.mark.asyncio
    async def test_document_status_up_to_date(
        self, client: AsyncClient
    ) -> None:
        """Returns is_up_to_date=True when no outstanding findings."""
        resp = await client.get(
            f"/api/impact-analysis/documents/{DOC_UUID_1}/status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_uuid"] == DOC_UUID_1
        assert data["is_up_to_date"] is True
        assert data["outstanding_critical_count"] == 0
        assert data["outstanding_major_count"] == 0

    @pytest.mark.asyncio
    async def test_document_status_with_outstanding_findings(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns outstanding counts when unacknowledged notifications exist."""
        # Seed notifications targeting DOC_UUID_1 as affected document
        async with session_factory() as session:
            notif = ImpactNotification(
                report_id=str(uuid.uuid4()),
                affected_document_uuid=DOC_UUID_1,
                notification_type="change_impact",
                impact_severity="critical",
                change_summary="Critical finding",
                target_user_id=USER_ID,
                is_acknowledged=False,
                company_id=COMPANY_ID,
            )
            session.add(notif)
            await session.commit()

        resp = await client.get(
            f"/api/impact-analysis/documents/{DOC_UUID_1}/status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_up_to_date"] is False
        assert data["outstanding_critical_count"] == 1
