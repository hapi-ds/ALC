"""Integration tests for AI-Powered Traceability & Gap Discovery API endpoints.

Tests all 13 endpoints with an in-memory SQLite database, verifying HTTP
status codes, pagination, filtering, X-Change-Reason enforcement, and
error responses (404, 409, 422, 503).

References:
    - Task 10.6: Write integration tests for API endpoints
    - Requirements: 1.1–1.12, 2.3–2.7, 3.3–3.7, 4.5, 5.1–5.6, 7.3–7.7,
                    9.2–9.6, 11.3–11.10
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

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
from alcoabase.models.traceability import (
    CoverageSnapshot,
    StaleLinkMarker,
    TraceabilityAlert,
    TraceabilityMatrix,
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

SAMPLE_LINKS = [
    {
        "requirement_id": "REQ-001",
        "requirement_text": "System shall validate user input",
        "source_document_uuid": DOC_UUID_1,
        "source_section": "Section 1.1",
        "target_document_uuid": DOC_UUID_2,
        "target_section": "Section 2.1",
        "test_case_id": "TC-001",
        "test_case_text": "Verify input validation works",
        "link_confidence": 0.95,
        "link_method": "exact_id_match",
        "link_methods": ["exact_id_match"],
        "verification_status": "verified",
    },
    {
        "requirement_id": "REQ-002",
        "requirement_text": "System shall log all actions",
        "source_document_uuid": DOC_UUID_1,
        "source_section": "Section 1.2",
        "target_document_uuid": DOC_UUID_2,
        "target_section": "Section 2.2",
        "test_case_id": "TC-002",
        "test_case_text": "Verify audit logging",
        "link_confidence": 0.75,
        "link_method": "semantic_match",
        "link_methods": ["semantic_match"],
        "verification_status": "unverified",
    },
]

SAMPLE_ORPHAN_REQUIREMENTS = [
    {
        "requirement_id": "REQ-003",
        "requirement_text": "System shall ensure sterility",
        "source_document_uuid": DOC_UUID_1,
        "source_section": "Section 1.3",
        "severity": "critical",
        "suggested_action": "create_test_case",
    },
    {
        "requirement_id": "REQ-004",
        "requirement_text": "System should display status",
        "source_document_uuid": DOC_UUID_1,
        "source_section": "Section 1.4",
        "severity": "minor",
        "suggested_action": "review_requirement",
    },
]

SAMPLE_ORPHAN_TEST_CASES = [
    {
        "test_case_id": "TC-010",
        "test_case_text": "Verify alarm triggers correctly",
        "target_document_uuid": DOC_UUID_2,
        "target_section": "Section 3.1",
        "risk_level": "high",
        "suggested_action": "link_to_requirement",
    },
    {
        "test_case_id": "TC-011",
        "test_case_text": "Check label formatting",
        "target_document_uuid": DOC_UUID_2,
        "target_section": "Section 3.2",
        "risk_level": "low",
        "suggested_action": "remove_test_case",
    },
    {
        "test_case_id": "TC-012",
        "test_case_text": "Verify calculation accuracy",
        "target_document_uuid": DOC_UUID_2,
        "target_section": "Section 3.3",
        "risk_level": "medium",
        "suggested_action": "create_requirement",
    },
]

SAMPLE_COVERAGE_METRICS = {
    "total_requirements": 4,
    "covered_requirements": 2,
    "orphan_requirements_count": 2,
    "coverage_percentage": 50.0,
    "total_test_cases": 5,
    "linked_test_cases": 2,
    "orphan_test_cases_count": 3,
    "average_link_confidence": 0.85,
    "compliance_readiness_score": 55.0,
}


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
            (DOC_UUID_2, "IQ Document"),
            (DOC_UUID_3, "OQ Document"),
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

    # Create document versions
    for i in range(1, 4):
        version = DocumentVersion(
            id=i,
            document_id=i,
            major_version=1,
            minor_version=0,
            storage_key=f"documents/2025-0000{i}/1.0/file.pdf",
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
# Helper: seed traceability data
# ---------------------------------------------------------------------------


async def seed_matrix(
    session_factory,
    matrix_id: str | None = None,
    matrix_name: str = "Test Matrix",
    status: str = "completed",
    deleted_at: datetime | None = None,
    company_id: int = COMPANY_ID,
) -> TraceabilityMatrix:
    """Insert a traceability matrix into the database."""
    async with session_factory() as session:
        matrix = TraceabilityMatrix(
            matrix_id=matrix_id or str(uuid.uuid4()),
            matrix_name=matrix_name,
            description="Test matrix description",
            source_document_uuids=[DOC_UUID_1],
            target_document_uuids=[DOC_UUID_2],
            source_document_versions=[
                {"document_uuid": DOC_UUID_1, "version_id": 1}
            ],
            target_document_versions=[
                {"document_uuid": DOC_UUID_2, "version_id": 1}
            ],
            traceability_links=SAMPLE_LINKS,
            orphan_requirements=SAMPLE_ORPHAN_REQUIREMENTS,
            orphan_test_cases=SAMPLE_ORPHAN_TEST_CASES,
            coverage_metrics=SAMPLE_COVERAGE_METRICS,
            status=status,
            parent_matrix_id=None,
            generation_timestamp=datetime.now(timezone.utc),
            generation_duration_ms=5000,
            agent_archetype_used="Traceability Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=2000,
            requesting_user_id=USER_ID,
            company_id=company_id,
            deleted_at=deleted_at,
        )
        session.add(matrix)
        await session.commit()
        await session.refresh(matrix)
        return matrix


async def seed_coverage_snapshot(
    session_factory,
    matrix_id: str,
    source_document_uuid: str = DOC_UUID_1,
    coverage_percentage: float = 50.0,
    company_id: int = COMPANY_ID,
) -> CoverageSnapshot:
    """Insert a coverage snapshot into the database."""
    async with session_factory() as session:
        snapshot = CoverageSnapshot(
            matrix_id=matrix_id,
            source_document_uuid=source_document_uuid,
            coverage_percentage=coverage_percentage,
            orphan_requirements_count=2,
            orphan_test_cases_count=3,
            compliance_readiness_score=55.0,
            total_requirements=4,
            covered_requirements=2,
            total_test_cases=5,
            linked_test_cases=2,
            snapshot_date=datetime.now(timezone.utc),
            company_id=company_id,
        )
        session.add(snapshot)
        await session.commit()
        await session.refresh(snapshot)
        return snapshot


async def seed_alert(
    session_factory,
    alert_id: str | None = None,
    is_resolved: bool = False,
    severity: str = "critical",
    company_id: int = COMPANY_ID,
) -> TraceabilityAlert:
    """Insert a traceability alert into the database."""
    async with session_factory() as session:
        alert = TraceabilityAlert(
            alert_id=alert_id or str(uuid.uuid4()),
            triggering_report_id=str(uuid.uuid4()),
            affected_matrix_ids=[str(uuid.uuid4())],
            affected_link_count=3,
            alert_severity=severity,
            is_resolved=is_resolved,
            company_id=company_id,
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)
        return alert


async def seed_processing_job(
    session_factory,
    job_id: str | None = None,
    document_id: int = 1,
    operation: str = "traceability_matrix_generation",
    status: str = "processing",
    progress: int = 50,
    result_reference: str | None = None,
) -> ProcessingJob:
    """Insert a processing job into the database."""
    async with session_factory() as session:
        job = ProcessingJob(
            job_id=job_id or str(uuid.uuid4()),
            document_id=document_id,
            operation=operation,
            status=status,
            progress_percent=progress,
            result_reference=result_reference,
            company_id=COMPANY_ID,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return job


# ---------------------------------------------------------------------------
# Test: POST /matrices/generate → 202, 404, 409, 422, 503
# ---------------------------------------------------------------------------


class TestGenerateMatrix:
    """Tests for POST /api/traceability/matrices/generate."""

    @pytest.mark.asyncio
    async def test_generate_returns_202_with_job_id(
        self, client: AsyncClient
    ) -> None:
        """Successful generation request returns 202 with a job_id."""
        mock_job_id = str(uuid.uuid4())
        with patch(
            "alcoabase.services.traceability_matrix.TraceabilityMatrixService.validate_and_enqueue",
            new_callable=AsyncMock,
            return_value={"job_id": mock_job_id},
        ):
            with patch(
                "alcoabase.tasks.celery_app.celery_app"
            ) as mock_celery:
                mock_celery.send_task = MagicMock()
                resp = await client.post(
                    "/api/traceability/matrices/generate",
                    json={
                        "source_document_ids": [1],
                        "target_document_ids": [2],
                        "matrix_name": "Test Matrix",
                    },
                )
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["job_id"] == mock_job_id

    @pytest.mark.asyncio
    async def test_generate_returns_422_for_overlap(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when a document appears in both source and target."""
        from alcoabase.services.traceability_matrix import _ValidationError

        with patch(
            "alcoabase.services.traceability_matrix.TraceabilityMatrixService.validate_and_enqueue",
            new_callable=AsyncMock,
            side_effect=_ValidationError(
                "Documents cannot be both source and target: [2]"
            ),
        ):
            with patch(
                "alcoabase.tasks.celery_app.celery_app"
            ) as mock_celery:
                mock_celery.send_task = MagicMock()
                resp = await client.post(
                    "/api/traceability/matrices/generate",
                    json={
                        "source_document_ids": [1, 2],
                        "target_document_ids": [2, 3],
                        "matrix_name": "Overlap Matrix",
                    },
                )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_returns_422_for_empty_name(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when matrix_name is empty."""
        resp = await client.post(
            "/api/traceability/matrices/generate",
            json={
                "source_document_ids": [1],
                "target_document_ids": [2],
                "matrix_name": "",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_returns_422_for_too_many_sources(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when source_document_ids exceeds max 10."""
        resp = await client.post(
            "/api/traceability/matrices/generate",
            json={
                "source_document_ids": list(range(1, 12)),
                "target_document_ids": [2],
                "matrix_name": "Too Many Sources",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_returns_404_for_missing_document(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when a document ID does not exist."""
        from alcoabase.services.traceability_matrix import _DocumentNotFoundError

        with patch(
            "alcoabase.services.traceability_matrix.TraceabilityMatrixService.validate_and_enqueue",
            new_callable=AsyncMock,
            side_effect=_DocumentNotFoundError(
                "Documents not found in company scope: [999]"
            ),
        ):
            with patch(
                "alcoabase.tasks.celery_app.celery_app"
            ) as mock_celery:
                mock_celery.send_task = MagicMock()
                resp = await client.post(
                    "/api/traceability/matrices/generate",
                    json={
                        "source_document_ids": [999],
                        "target_document_ids": [2],
                        "matrix_name": "Missing Doc Matrix",
                    },
                )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_returns_503_when_celery_unavailable(
        self, client: AsyncClient
    ) -> None:
        """Returns 503 when Celery broker is unavailable."""
        mock_job_id = str(uuid.uuid4())
        with patch(
            "alcoabase.services.traceability_matrix.TraceabilityMatrixService.validate_and_enqueue",
            new_callable=AsyncMock,
            return_value={"job_id": mock_job_id},
        ):
            with patch(
                "alcoabase.tasks.celery_app.celery_app"
            ) as mock_celery:
                mock_celery.send_task = MagicMock(
                    side_effect=Exception("Broker unavailable")
                )
                resp = await client.post(
                    "/api/traceability/matrices/generate",
                    json={
                        "source_document_ids": [1],
                        "target_document_ids": [2],
                        "matrix_name": "Test Matrix",
                    },
                )
        assert resp.status_code == 503
        assert "temporarily unavailable" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_generate_requires_x_change_reason(
        self, client_no_reason: AsyncClient
    ) -> None:
        """Mutation endpoint requires X-Change-Reason header."""
        resp = await client_no_reason.post(
            "/api/traceability/matrices/generate",
            json={
                "source_document_ids": [1],
                "target_document_ids": [2],
                "matrix_name": "No Reason Matrix",
            },
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: GET /matrices → paginated matrices list
# ---------------------------------------------------------------------------


class TestListMatrices:
    """Tests for GET /api/traceability/matrices."""

    @pytest.mark.asyncio
    async def test_list_matrices_empty(self, client: AsyncClient) -> None:
        """Returns empty list when no matrices exist."""
        resp = await client.get("/api/traceability/matrices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["matrices"] == []
        assert data["total_count"] == 0

    @pytest.mark.asyncio
    async def test_list_matrices_with_data(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns matrices with pagination metadata."""
        await seed_matrix(session_factory, matrix_name="Matrix A")
        await seed_matrix(session_factory, matrix_name="Matrix B")

        resp = await client.get("/api/traceability/matrices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert len(data["matrices"]) == 2

    @pytest.mark.asyncio
    async def test_list_matrices_excludes_soft_deleted(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Soft-deleted matrices are excluded from list queries."""
        await seed_matrix(session_factory, matrix_name="Active")
        await seed_matrix(
            session_factory,
            matrix_name="Deleted",
            deleted_at=datetime.now(timezone.utc),
        )

        resp = await client.get("/api/traceability/matrices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["matrices"][0]["matrix_name"] == "Active"

    @pytest.mark.asyncio
    async def test_list_matrices_filter_by_status(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Filters matrices by status."""
        await seed_matrix(session_factory, status="completed")
        await seed_matrix(session_factory, status="partial_success")

        resp = await client.get(
            "/api/traceability/matrices",
            params={"status": "completed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["matrices"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_matrices_pagination(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Respects limit and offset parameters."""
        await seed_matrix(session_factory, matrix_name="M1")
        await seed_matrix(session_factory, matrix_name="M2")
        await seed_matrix(session_factory, matrix_name="M3")

        resp = await client.get(
            "/api/traceability/matrices",
            params={"limit": 2, "offset": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["matrices"]) == 2
        assert data["total_count"] == 3

    @pytest.mark.asyncio
    async def test_list_matrices_filter_by_status_no_match(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns empty when status filter doesn't match."""
        await seed_matrix(session_factory, status="completed")

        resp = await client.get(
            "/api/traceability/matrices",
            params={"status": "failed"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_count"] == 0


# ---------------------------------------------------------------------------
# Test: GET /matrices/{matrix_id} → full matrix detail
# ---------------------------------------------------------------------------


class TestGetMatrix:
    """Tests for GET /api/traceability/matrices/{matrix_id}."""

    @pytest.mark.asyncio
    async def test_get_matrix_returns_full_detail(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns full matrix detail for a valid matrix_id."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(f"/api/traceability/matrices/{mid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["matrix_id"] == mid
        assert data["status"] == "completed"
        assert "traceability_links" in data
        assert "orphan_requirements" in data
        assert "orphan_test_cases" in data
        assert "coverage_metrics" in data

    @pytest.mark.asyncio
    async def test_get_matrix_returns_404_for_missing(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when matrix_id does not exist."""
        resp = await client.get(
            f"/api/traceability/matrices/{uuid.uuid4()}"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_matrix_returns_422_for_invalid_uuid(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when matrix_id is not a valid UUID."""
        resp = await client.get("/api/traceability/matrices/not-a-uuid")
        assert resp.status_code == 422
        assert "invalid" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_matrix_returns_404_for_other_company(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 404 when matrix belongs to a different company."""
        # Seed a second company
        async with session_factory() as session:
            company2 = Company(
                id=2,
                slug="other-co",
                display_name="Other Company",
                regulatory_framework="ISO_13485",
                audit_config={},
                is_active=True,
            )
            session.add(company2)
            await session.commit()

        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid, company_id=2)

        resp = await client.get(f"/api/traceability/matrices/{mid}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: GET /matrices/{matrix_id}/links → paginated links
# ---------------------------------------------------------------------------


class TestGetMatrixLinks:
    """Tests for GET /api/traceability/matrices/{matrix_id}/links."""

    @pytest.mark.asyncio
    async def test_get_links_returns_paginated(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns paginated links for a valid matrix."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/links"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert len(data["links"]) == 2

    @pytest.mark.asyncio
    async def test_get_links_filter_by_confidence(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Filters links by link_confidence_min."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/links",
            params={"link_confidence_min": 0.9},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["links"][0]["link_confidence"] >= 0.9

    @pytest.mark.asyncio
    async def test_get_links_filter_by_method(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Filters links by link_method."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/links",
            params={"link_method": "exact_id_match"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["links"][0]["link_method"] == "exact_id_match"

    @pytest.mark.asyncio
    async def test_get_links_returns_422_for_invalid_confidence(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 422 when link_confidence_min is out of range."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/links",
            params={"link_confidence_min": 1.5},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_links_returns_404_for_missing_matrix(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when matrix_id does not exist."""
        resp = await client.get(
            f"/api/traceability/matrices/{uuid.uuid4()}/links"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_links_returns_422_for_invalid_uuid(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when matrix_id is not a valid UUID."""
        resp = await client.get(
            "/api/traceability/matrices/bad-id/links"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_links_pagination(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Respects limit and offset for links."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/links",
            params={"limit": 1, "offset": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["links"]) == 1
        assert data["total_count"] == 2


# ---------------------------------------------------------------------------
# Test: GET /matrices/{matrix_id}/orphan-requirements
# ---------------------------------------------------------------------------


class TestGetOrphanRequirements:
    """Tests for GET /api/traceability/matrices/{matrix_id}/orphan-requirements."""

    @pytest.mark.asyncio
    async def test_get_orphan_requirements_returns_list(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns orphan requirements for a valid matrix."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/orphan-requirements"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert len(data["orphan_requirements"]) == 2

    @pytest.mark.asyncio
    async def test_get_orphan_requirements_filter_by_severity(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Filters orphan requirements by severity."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/orphan-requirements",
            params={"severity": "critical"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["orphan_requirements"][0]["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_get_orphan_requirements_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when matrix_id does not exist."""
        resp = await client.get(
            f"/api/traceability/matrices/{uuid.uuid4()}/orphan-requirements"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_orphan_requirements_pagination(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Respects limit and offset for orphan requirements."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/orphan-requirements",
            params={"limit": 1, "offset": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["orphan_requirements"]) == 1
        assert data["total_count"] == 2


# ---------------------------------------------------------------------------
# Test: GET /matrices/{matrix_id}/orphan-test-cases
# ---------------------------------------------------------------------------


class TestGetOrphanTestCases:
    """Tests for GET /api/traceability/matrices/{matrix_id}/orphan-test-cases."""

    @pytest.mark.asyncio
    async def test_get_orphan_test_cases_returns_ordered(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns orphan test cases ordered by risk_level desc, test_case_id asc."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/orphan-test-cases"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3
        # Should be ordered: high, medium, low
        risk_levels = [o["risk_level"] for o in data["orphan_test_cases"]]
        assert risk_levels == ["high", "medium", "low"]

    @pytest.mark.asyncio
    async def test_get_orphan_test_cases_filter_by_risk_level(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Filters orphan test cases by risk_level."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.get(
            f"/api/traceability/matrices/{mid}/orphan-test-cases",
            params={"risk_level": "high"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["orphan_test_cases"][0]["risk_level"] == "high"

    @pytest.mark.asyncio
    async def test_get_orphan_test_cases_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when matrix_id does not exist."""
        resp = await client.get(
            f"/api/traceability/matrices/{uuid.uuid4()}/orphan-test-cases"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: DELETE /matrices/{matrix_id} → soft-delete (204)
# ---------------------------------------------------------------------------


class TestDeleteMatrix:
    """Tests for DELETE /api/traceability/matrices/{matrix_id}."""

    @pytest.mark.asyncio
    async def test_delete_returns_204(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Successful soft-delete returns 204."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client.delete(f"/api/traceability/matrices/{mid}")
        assert resp.status_code == 204

        # Verify it's excluded from list
        resp = await client.get("/api/traceability/matrices")
        assert resp.json()["total_count"] == 0

    @pytest.mark.asyncio
    async def test_delete_returns_404_for_missing(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when matrix_id does not exist."""
        resp = await client.delete(
            f"/api/traceability/matrices/{uuid.uuid4()}"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_returns_404_for_already_deleted(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 404 when matrix is already soft-deleted."""
        mid = str(uuid.uuid4())
        await seed_matrix(
            session_factory,
            matrix_id=mid,
            deleted_at=datetime.now(timezone.utc),
        )

        resp = await client.delete(f"/api/traceability/matrices/{mid}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_returns_422_for_invalid_uuid(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when matrix_id is not a valid UUID."""
        resp = await client.delete(
            "/api/traceability/matrices/not-a-uuid"
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_requires_x_change_reason(
        self, client_no_reason: AsyncClient, session_factory
    ) -> None:
        """DELETE requires X-Change-Reason header."""
        mid = str(uuid.uuid4())
        await seed_matrix(session_factory, matrix_id=mid)

        resp = await client_no_reason.delete(
            f"/api/traceability/matrices/{mid}"
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Test: GET /documents/{document_uuid}/coverage
# ---------------------------------------------------------------------------


class TestGetDocumentCoverage:
    """Tests for GET /api/traceability/documents/{document_uuid}/coverage."""

    @pytest.mark.asyncio
    async def test_coverage_returns_null_when_never_analyzed(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns null coverage when document has never been in a matrix."""
        with patch.object(
            app.dependency_overrides.get(get_tenant_context, get_tenant_context),
            "__call__",
            return_value=TenantContext(
                company_id=COMPANY_ID,
                company_slug="test-co",
                user_id=USER_ID,
                membership_role="admin",
            ),
        ):
            pass
        # Mock the service to return empty coverage
        mock_service = AsyncMock()
        mock_service.get_document_coverage = AsyncMock(
            return_value={
                "document_uuid": DOC_UUID_1,
                "latest_matrix_id": None,
                "latest_matrix_date": None,
                "coverage_percentage": None,
                "orphan_requirement_count": 0,
                "total_requirements": 0,
                "compliance_readiness_score": None,
            }
        )
        from alcoabase.api.traceability import get_coverage_metrics_service
        app.dependency_overrides[get_coverage_metrics_service] = lambda: mock_service

        resp = await client.get(
            f"/api/traceability/documents/{DOC_UUID_1}/coverage"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["coverage_percentage"] is None
        assert data["total_requirements"] == 0

        # Cleanup
        app.dependency_overrides.pop(get_coverage_metrics_service, None)

    @pytest.mark.asyncio
    async def test_coverage_returns_data_when_analyzed(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns coverage data when document has been analyzed."""
        mid = str(uuid.uuid4())
        mock_service = AsyncMock()
        mock_service.get_document_coverage = AsyncMock(
            return_value={
                "document_uuid": DOC_UUID_1,
                "latest_matrix_id": mid,
                "latest_matrix_date": datetime.now(timezone.utc).isoformat(),
                "coverage_percentage": 75.0,
                "orphan_requirement_count": 1,
                "total_requirements": 4,
                "compliance_readiness_score": 65.0,
            }
        )
        from alcoabase.api.traceability import get_coverage_metrics_service
        app.dependency_overrides[get_coverage_metrics_service] = lambda: mock_service

        resp = await client.get(
            f"/api/traceability/documents/{DOC_UUID_1}/coverage"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["coverage_percentage"] == 75.0
        assert data["total_requirements"] == 4

        app.dependency_overrides.pop(get_coverage_metrics_service, None)

    @pytest.mark.asyncio
    async def test_coverage_returns_422_for_invalid_uuid(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when document_uuid is not a valid format."""
        resp = await client.get(
            "/api/traceability/documents/!!!invalid!!!/coverage"
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: GET /coverage/summary
# ---------------------------------------------------------------------------


class TestGetCoverageSummary:
    """Tests for GET /api/traceability/coverage/summary."""

    @pytest.mark.asyncio
    async def test_summary_returns_zeros_when_no_matrices(
        self, client: AsyncClient
    ) -> None:
        """Returns zero values when no matrices exist."""
        mock_service = AsyncMock()
        mock_service.get_coverage_summary = AsyncMock(
            return_value={
                "total_matrices_generated": 0,
                "latest_matrix_date": None,
                "average_coverage_percentage": 0.0,
                "total_orphan_requirements": 0,
                "total_orphan_test_cases": 0,
                "average_compliance_readiness_score": 0.0,
                "breakdown": [],
            }
        )
        from alcoabase.api.traceability import get_coverage_metrics_service
        app.dependency_overrides[get_coverage_metrics_service] = lambda: mock_service

        resp = await client.get("/api/traceability/coverage/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matrices_generated"] == 0
        assert data["average_coverage_percentage"] == 0.0

        app.dependency_overrides.pop(get_coverage_metrics_service, None)

    @pytest.mark.asyncio
    async def test_summary_returns_aggregated_data(
        self, client: AsyncClient
    ) -> None:
        """Returns aggregated coverage data when matrices exist."""
        mock_service = AsyncMock()
        mock_service.get_coverage_summary = AsyncMock(
            return_value={
                "total_matrices_generated": 3,
                "latest_matrix_date": datetime.now(timezone.utc).isoformat(),
                "average_coverage_percentage": 65.5,
                "total_orphan_requirements": 5,
                "total_orphan_test_cases": 3,
                "average_compliance_readiness_score": 70.0,
                "breakdown": [
                    {
                        "document_uuid": DOC_UUID_1,
                        "document_name": "URS Document",
                        "coverage_percentage": 75.0,
                        "orphan_count": 2,
                    }
                ],
            }
        )
        from alcoabase.api.traceability import get_coverage_metrics_service
        app.dependency_overrides[get_coverage_metrics_service] = lambda: mock_service

        resp = await client.get("/api/traceability/coverage/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_matrices_generated"] == 3
        assert data["average_coverage_percentage"] == 65.5
        assert len(data["breakdown"]) == 1

        app.dependency_overrides.pop(get_coverage_metrics_service, None)


# ---------------------------------------------------------------------------
# Test: GET /coverage/history → paginated snapshots
# ---------------------------------------------------------------------------


class TestGetCoverageHistory:
    """Tests for GET /api/traceability/coverage/history."""

    @pytest.mark.asyncio
    async def test_history_returns_paginated_snapshots(
        self, client: AsyncClient
    ) -> None:
        """Returns paginated coverage snapshots."""
        mock_service = AsyncMock()
        mock_service.get_coverage_history = AsyncMock(
            return_value={
                "snapshots": [
                    {
                        "snapshot_date": datetime.now(timezone.utc),
                        "matrix_id": str(uuid.uuid4()),
                        "source_document_uuid": DOC_UUID_1,
                        "coverage_percentage": 50.0,
                        "orphan_requirements_count": 2,
                        "orphan_test_cases_count": 3,
                        "compliance_readiness_score": 55.0,
                        "total_requirements": 4,
                        "covered_requirements": 2,
                        "total_test_cases": 5,
                        "linked_test_cases": 2,
                    }
                ],
                "total_count": 1,
            }
        )
        from alcoabase.api.traceability import get_coverage_metrics_service
        app.dependency_overrides[get_coverage_metrics_service] = lambda: mock_service

        resp = await client.get("/api/traceability/coverage/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert len(data["snapshots"]) == 1

        app.dependency_overrides.pop(get_coverage_metrics_service, None)

    @pytest.mark.asyncio
    async def test_history_with_filters(
        self, client: AsyncClient
    ) -> None:
        """Passes filter parameters to the service."""
        mock_service = AsyncMock()
        mock_service.get_coverage_history = AsyncMock(
            return_value={"snapshots": [], "total_count": 0}
        )
        from alcoabase.api.traceability import get_coverage_metrics_service
        app.dependency_overrides[get_coverage_metrics_service] = lambda: mock_service

        resp = await client.get(
            "/api/traceability/coverage/history",
            params={
                "source_document_uuid": DOC_UUID_1,
                "limit": 10,
                "offset": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 0

        app.dependency_overrides.pop(get_coverage_metrics_service, None)


# ---------------------------------------------------------------------------
# Test: GET /alerts → unresolved alerts
# ---------------------------------------------------------------------------


class TestListAlerts:
    """Tests for GET /api/traceability/alerts."""

    @pytest.mark.asyncio
    async def test_list_alerts_empty(self, client: AsyncClient) -> None:
        """Returns empty list when no alerts exist."""
        mock_service = AsyncMock()
        mock_service.get_alerts = AsyncMock(return_value=([], 0))
        from alcoabase.api.traceability import get_traceability_alert_service
        app.dependency_overrides[get_traceability_alert_service] = lambda: mock_service

        resp = await client.get("/api/traceability/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["alerts"] == []
        assert data["total_count"] == 0

        app.dependency_overrides.pop(get_traceability_alert_service, None)

    @pytest.mark.asyncio
    async def test_list_alerts_with_data(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns alerts sorted by severity then created_at."""
        alert1 = await seed_alert(session_factory, severity="minor")
        alert2 = await seed_alert(session_factory, severity="critical")

        mock_service = AsyncMock()
        # Return alerts in correct order (critical first)
        mock_service.get_alerts = AsyncMock(
            return_value=([alert2, alert1], 2)
        )
        from alcoabase.api.traceability import get_traceability_alert_service
        app.dependency_overrides[get_traceability_alert_service] = lambda: mock_service

        resp = await client.get("/api/traceability/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert data["alerts"][0]["alert_severity"] == "critical"
        assert data["alerts"][1]["alert_severity"] == "minor"

        app.dependency_overrides.pop(get_traceability_alert_service, None)


# ---------------------------------------------------------------------------
# Test: POST /alerts/{alert_id}/resolve → resolve alert
# ---------------------------------------------------------------------------


class TestResolveAlert:
    """Tests for POST /api/traceability/alerts/{alert_id}/resolve."""

    @pytest.mark.asyncio
    async def test_resolve_returns_200(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Successful resolution returns 200."""
        alert = await seed_alert(session_factory)

        mock_service = AsyncMock()
        # Simulate successful resolution
        resolved_alert = alert
        resolved_alert.is_resolved = True
        resolved_alert.resolution_action = "links_verified"
        mock_service.resolve_alert = AsyncMock(
            return_value=(resolved_alert, 200)
        )
        from alcoabase.api.traceability import get_traceability_alert_service
        app.dependency_overrides[get_traceability_alert_service] = lambda: mock_service

        resp = await client.post(
            f"/api/traceability/alerts/{alert.alert_id}/resolve",
            json={
                "resolution_action": "links_verified",
                "resolution_note": "Verified all links are still valid",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "resolved"

        app.dependency_overrides.pop(get_traceability_alert_service, None)

    @pytest.mark.asyncio
    async def test_resolve_returns_404_for_missing(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when alert_id does not exist."""
        mock_service = AsyncMock()
        mock_service.resolve_alert = AsyncMock(return_value=(None, 404))
        from alcoabase.api.traceability import get_traceability_alert_service
        app.dependency_overrides[get_traceability_alert_service] = lambda: mock_service

        resp = await client.post(
            f"/api/traceability/alerts/{uuid.uuid4()}/resolve",
            json={"resolution_action": "links_verified"},
        )
        assert resp.status_code == 404

        app.dependency_overrides.pop(get_traceability_alert_service, None)

    @pytest.mark.asyncio
    async def test_resolve_returns_409_for_already_resolved(
        self, client: AsyncClient
    ) -> None:
        """Returns 409 when alert is already resolved."""
        mock_service = AsyncMock()
        mock_service.resolve_alert = AsyncMock(return_value=(None, 409))
        from alcoabase.api.traceability import get_traceability_alert_service
        app.dependency_overrides[get_traceability_alert_service] = lambda: mock_service

        resp = await client.post(
            f"/api/traceability/alerts/{uuid.uuid4()}/resolve",
            json={"resolution_action": "no_action_needed"},
        )
        assert resp.status_code == 409

        app.dependency_overrides.pop(get_traceability_alert_service, None)

    @pytest.mark.asyncio
    async def test_resolve_requires_x_change_reason(
        self, client_no_reason: AsyncClient
    ) -> None:
        """POST resolve requires X-Change-Reason header."""
        resp = await client_no_reason.post(
            f"/api/traceability/alerts/{uuid.uuid4()}/resolve",
            json={"resolution_action": "links_verified"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_resolve_returns_422_for_invalid_action(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when resolution_action is invalid."""
        resp = await client.post(
            f"/api/traceability/alerts/{uuid.uuid4()}/resolve",
            json={"resolution_action": "invalid_action"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: GET /jobs/{job_id}/status → job status with progress
# ---------------------------------------------------------------------------


class TestGetJobStatus:
    """Tests for GET /api/traceability/jobs/{job_id}/status."""

    @pytest.mark.asyncio
    async def test_job_status_returns_progress(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns job status with progress information."""
        job_id = str(uuid.uuid4())
        await seed_processing_job(
            session_factory,
            job_id=job_id,
            status="processing",
            progress=45,
        )

        resp = await client.get(
            f"/api/traceability/jobs/{job_id}/status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["status"] == "processing"
        assert data["progress_percent"] == 45
        assert data["current_phase"] == "extracting_test_cases"

    @pytest.mark.asyncio
    async def test_job_status_returns_completion_data(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns completion data for a finished job."""
        job_id = str(uuid.uuid4())
        mid = str(uuid.uuid4())
        result_data = json.dumps({
            "matrix_id": mid,
            "total_requirements": 10,
            "total_test_cases": 15,
            "total_links": 8,
            "coverage_percentage": 80.0,
            "orphan_requirements_count": 2,
            "orphan_test_cases_count": 7,
            "compliance_readiness_score": 72.5,
            "generation_duration_ms": 45000,
            "summary_sentence": "Matrix generated successfully.",
        })
        await seed_processing_job(
            session_factory,
            job_id=job_id,
            status="completed",
            progress=100,
            result_reference=result_data,
        )

        resp = await client.get(
            f"/api/traceability/jobs/{job_id}/status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["matrix_id"] == mid
        assert data["total_requirements"] == 10
        assert data["coverage_percentage"] == 80.0

    @pytest.mark.asyncio
    async def test_job_status_returns_404_for_missing(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when job_id does not exist."""
        resp = await client.get(
            f"/api/traceability/jobs/{uuid.uuid4()}/status"
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_job_status_returns_404_for_other_company(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 404 when job belongs to a different company."""
        from sqlalchemy import select as sa_select

        # Seed a second company
        async with session_factory() as session:
            from alcoabase.models.company import Company as Co
            result = await session.execute(
                sa_select(Co).where(Co.id == 2)
            )
            if result.scalar_one_or_none() is None:
                company2 = Co(
                    id=2,
                    slug="other-co",
                    display_name="Other Company",
                    regulatory_framework="ISO_13485",
                    audit_config={},
                    is_active=True,
                )
                session.add(company2)
                await session.commit()

        job_id = str(uuid.uuid4())
        async with session_factory() as session:
            job = ProcessingJob(
                job_id=job_id,
                document_id=1,
                operation="traceability_matrix_generation",
                status="processing",
                progress_percent=50,
                company_id=2,
            )
            session.add(job)
            await session.commit()

        resp = await client.get(
            f"/api/traceability/jobs/{job_id}/status"
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Concurrent job detection (409)
# ---------------------------------------------------------------------------


class TestConcurrentJobDetection:
    """Tests for concurrent job detection on POST /matrices/generate."""

    @pytest.mark.asyncio
    async def test_concurrent_job_returns_409(
        self, client: AsyncClient, session_factory
    ) -> None:
        """Returns 409 when a processing job already exists for same docs."""
        from alcoabase.services.job_tracker import JobConflictError

        with patch(
            "alcoabase.services.traceability_matrix.TraceabilityMatrixService.validate_and_enqueue",
            new_callable=AsyncMock,
            side_effect=JobConflictError(
                existing_job_id="existing-job-123",
                document_uuid="trace:[1]:[2]",
                operation="traceability_matrix_generation",
            ),
        ):
            with patch(
                "alcoabase.tasks.celery_app.celery_app"
            ) as mock_celery:
                mock_celery.send_task = MagicMock()
                resp = await client.post(
                    "/api/traceability/matrices/generate",
                    json={
                        "source_document_ids": [1],
                        "target_document_ids": [2],
                        "matrix_name": "Duplicate Job",
                    },
                )
        assert resp.status_code == 409
        assert "already in progress" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test: Document validation on generate
# ---------------------------------------------------------------------------


class TestDocumentValidation:
    """Tests for document validation in POST /matrices/generate."""

    @pytest.mark.asyncio
    async def test_generate_validates_document_existence(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when source documents don't exist."""
        from alcoabase.services.traceability_matrix import _DocumentNotFoundError

        with patch(
            "alcoabase.services.traceability_matrix.TraceabilityMatrixService.validate_and_enqueue",
            new_callable=AsyncMock,
            side_effect=_DocumentNotFoundError(
                "Documents not found in company scope: [100, 200]"
            ),
        ):
            with patch(
                "alcoabase.tasks.celery_app.celery_app"
            ) as mock_celery:
                mock_celery.send_task = MagicMock()
                resp = await client.post(
                    "/api/traceability/matrices/generate",
                    json={
                        "source_document_ids": [100, 200],
                        "target_document_ids": [2],
                        "matrix_name": "Missing Docs",
                    },
                )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_validates_target_document_existence(
        self, client: AsyncClient
    ) -> None:
        """Returns 404 when target documents don't exist."""
        from alcoabase.services.traceability_matrix import _DocumentNotFoundError

        with patch(
            "alcoabase.services.traceability_matrix.TraceabilityMatrixService.validate_and_enqueue",
            new_callable=AsyncMock,
            side_effect=_DocumentNotFoundError(
                "Documents not found in company scope: [100, 200]"
            ),
        ):
            with patch(
                "alcoabase.tasks.celery_app.celery_app"
            ) as mock_celery:
                mock_celery.send_task = MagicMock()
                resp = await client.post(
                    "/api/traceability/matrices/generate",
                    json={
                        "source_document_ids": [1],
                        "target_document_ids": [100, 200],
                        "matrix_name": "Missing Target Docs",
                    },
                )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_generate_validates_too_many_targets(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when target_document_ids exceeds max 20."""
        resp = await client.post(
            "/api/traceability/matrices/generate",
            json={
                "source_document_ids": [1],
                "target_document_ids": list(range(1, 22)),
                "matrix_name": "Too Many Targets",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_generate_validates_description_length(
        self, client: AsyncClient
    ) -> None:
        """Returns 422 when description exceeds 1000 characters."""
        resp = await client.post(
            "/api/traceability/matrices/generate",
            json={
                "source_document_ids": [1],
                "target_document_ids": [2],
                "matrix_name": "Long Desc",
                "description": "x" * 1001,
            },
        )
        assert resp.status_code == 422
