"""Integration tests for the template versioning API.

Tests the full end-to-end versioning flow through the API layer using
httpx.AsyncClient with an async SQLite in-memory database, verifying:
- Full create template -> create version -> list versions -> get version flow
- PDF download with version-aware filename
- Audit trail logging for version events (X-Change-Reason header)
- Version ordering and active version enforcement
- Concurrent version creation rejection (409 Conflict)

References:
    - Task 23.6: Write backend integration tests for versioning API
    - Requirements: 10.3, 10.4, 11.1, 12.3, 21.1, 21.2
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.api.templates import get_storage_service, get_template_service
from alcoabase.database import Base, get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.user import User
from alcoabase.services.template_service import TemplateService
from alcoabase.services.uuid_service import UUIDService

# Ensure sqlalchemy_continuum tables are registered in Base.metadata
# before create_all is called. Required because Template uses AuditMixin.
from sqlalchemy.orm import configure_mappers

configure_mappers()


# ---------------------------------------------------------------------------
# SQLite-compatible UUID service that avoids PostgreSQL sequences
# ---------------------------------------------------------------------------


class SqliteUUIDService(UUIDService):
    """UUID service that works with SQLite (no sequences).

    Uses an in-memory counter instead of PostgreSQL sequences for
    generating Document-UUIDs in integration tests.
    """

    def __init__(self) -> None:
        self._counter = 0

    async def generate_document_uuid(self, session: AsyncSession) -> str:
        """Generate a Document-UUID using an in-memory counter."""
        self._counter += 1
        year = 2025
        return f"{year}-{self._counter:05d}"


# ---------------------------------------------------------------------------
# Fixtures: Async SQLite in-memory database for versioning integration tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite in-memory engine for integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

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
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct test verification."""
    async with session_factory() as session:
        yield session
        await session.commit()


@pytest_asyncio.fixture
async def client(session_factory, db_session) -> AsyncGenerator[AsyncClient, None]:
    """Create an httpx AsyncClient with overridden dependencies.

    Overrides get_db_session to use the in-memory SQLite database,
    get_tenant_context to bypass multi-tenancy resolution,
    get_template_service to use a SQLite-compatible UUID service,
    and get_storage_service to use a mock that avoids MinIO connections.
    """
    # Seed a user and company for tenant context
    user = User(
        id=1,
        username="testuser",
        email="test@alcoabase.local",
        hashed_password="hashed_placeholder",
        full_name="Test User",
        is_active=True,
    )
    db_session.add(user)

    company = Company(
        id=1,
        slug="test-company",
        display_name="Test Company",
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=True,
    )
    db_session.add(company)
    await db_session.flush()

    membership = CompanyMembership(
        user_id=1,
        company_id=1,
        role="admin",
    )
    db_session.add(membership)
    await db_session.commit()

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
            company_id=1,
            company_slug="test-company",
            user_id=1,
            membership_role="admin",
        )

    # Use a SQLite-compatible UUID service for template creation
    sqlite_uuid_service = SqliteUUIDService()
    test_template_service = TemplateService(uuid_service=sqlite_uuid_service)

    def _override_get_template_service():
        return test_template_service

    # Mock storage service to avoid MinIO connections during PDF download
    mock_storage = MagicMock()
    mock_storage.upload_file = AsyncMock(return_value="test/key.pdf")

    def _override_get_storage_service():
        return mock_storage

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context
    app.dependency_overrides[get_template_service] = _override_get_template_service
    app.dependency_overrides[get_storage_service] = _override_get_storage_service

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Integration test",
            "X-User-Id": "1",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helper: Create a template via API
# ---------------------------------------------------------------------------


async def create_template(client: AsyncClient, name: str = "Test Template") -> dict:
    """Create a template via the API and return the response JSON."""
    payload = {
        "name": name,
        "json_schema": {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Batch Number",
                    "type": "Text",
                    "required": True,
                    "help_text": "Enter the batch number",
                    "default_value": None,
                    "config": {
                        "min_length": 1,
                        "max_length": 50,
                        "placeholder": "BN-XXXX",
                        "regex_pattern": None,
                    },
                },
                {
                    "element_type": "content_block",
                    "content_type": "heading_h1",
                    "text": "Section 1: Measurements",
                },
                {
                    "element_type": "field",
                    "label": "Temperature",
                    "type": "Float",
                    "required": False,
                    "help_text": "Measure in Celsius",
                    "default_value": "25.0",
                    "config": {
                        "decimal_precision": 2,
                        "min_value": -40.0,
                        "max_value": 200.0,
                        "unit_label": "\u00b0C",
                    },
                },
            ],
        },
        "user_id": 1,
    }
    resp = await client.post("/api/templates", json=payload)
    assert resp.status_code == 201, f"Template creation failed: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Test: Full create -> list -> get version flow
# ---------------------------------------------------------------------------


class TestVersioningFlow:
    """Test the full versioning lifecycle: create template -> create versions -> list -> get."""

    @pytest.mark.asyncio
    async def test_create_version_and_list(self, client: AsyncClient) -> None:
        """Create a template, then create a version and verify it appears in the list.

        Validates: Requirements 10.3, 10.4, 11.1
        """
        # Step 1: Create a template
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        # Step 2: Create first version
        version_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Batch Number v2",
                        "type": "Text",
                        "required": True,
                        "help_text": "Updated batch number field",
                        "default_value": None,
                        "config": {"max_length": 100},
                    },
                    {
                        "element_type": "field",
                        "label": "Weight",
                        "type": "Float",
                        "required": True,
                        "help_text": None,
                        "default_value": None,
                        "config": {
                            "decimal_precision": 3,
                            "min_value": 0.0,
                            "max_value": 1000.0,
                            "unit_label": "kg",
                        },
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=version_payload,
            headers={"X-Change-Reason": "Added weight field for v2"},
        )
        assert resp.status_code == 201, f"Version creation failed: {resp.text}"
        version_data = resp.json()
        assert version_data["version_number"] == 1
        assert version_data["is_active"] is True
        assert version_data["status"] == "ReadOnly"
        assert version_data["document_uuid"] == doc_uuid
        assert version_data["change_reason"] == "Added weight field for v2"
        assert len(version_data["fields"]) == 2

        # Step 3: List versions - should have exactly one
        resp = await client.get(f"/api/templates/{doc_uuid}/versions")
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 1
        assert versions[0]["version_number"] == 1
        assert versions[0]["is_active"] is True

        # Step 4: Get specific version
        resp = await client.get(f"/api/templates/{doc_uuid}/versions/1")
        assert resp.status_code == 200
        version_detail = resp.json()
        assert version_detail["version_number"] == 1
        assert version_detail["is_active"] is True
        assert len(version_detail["fields"]) == 2

    @pytest.mark.asyncio
    async def test_multiple_versions_deactivate_previous(
        self, client: AsyncClient
    ) -> None:
        """Creating a second version deactivates the first.

        Validates: Requirements 10.4, 10.5, 10.6, 10.7
        """
        # Create template
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        # Create version 1
        v1_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Field A",
                        "type": "Text",
                        "required": False,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=v1_payload,
            headers={"X-Change-Reason": "Initial version"},
        )
        assert resp.status_code == 201
        v1 = resp.json()
        assert v1["version_number"] == 1
        assert v1["is_active"] is True

        # Create version 2
        v2_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Field A Updated",
                        "type": "Text",
                        "required": True,
                        "help_text": "Now required",
                        "default_value": None,
                        "config": {"max_length": 200},
                    },
                    {
                        "element_type": "field",
                        "label": "Field B",
                        "type": "Integer",
                        "required": False,
                        "help_text": None,
                        "default_value": "10",
                        "config": {"min_value": 0, "max_value": 100},
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=v2_payload,
            headers={"X-Change-Reason": "Added Field B, made Field A required"},
        )
        assert resp.status_code == 201
        v2 = resp.json()
        assert v2["version_number"] == 2
        assert v2["is_active"] is True

        # List versions - should be ordered descending (newest first)
        resp = await client.get(f"/api/templates/{doc_uuid}/versions")
        assert resp.status_code == 200
        versions = resp.json()
        assert len(versions) == 2
        assert versions[0]["version_number"] == 2
        assert versions[0]["is_active"] is True
        assert versions[1]["version_number"] == 1
        assert versions[1]["is_active"] is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_version_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Requesting a version that doesn't exist returns 404.

        Validates: Requirement 11.1 (version retrieval)
        """
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        resp = await client.get(f"/api/templates/{doc_uuid}/versions/99")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_version_for_nonexistent_template_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Creating a version for a non-existent template returns 404."""
        payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Test",
                        "type": "Text",
                        "required": False,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            "/api/templates/9999-99999/versions",
            json=payload,
            headers={"X-Change-Reason": "Should fail"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: PDF download with version-aware filename
# ---------------------------------------------------------------------------


class TestPdfDownloadVersioning:
    """Test PDF download with version-aware filename generation."""

    @pytest.mark.asyncio
    async def test_pdf_download_includes_version_in_filename(
        self, client: AsyncClient
    ) -> None:
        """PDF download filename includes the version number.

        Validates: Requirement 12.3
        """
        # Create template and version
        template_data = await create_template(client, name="Batch Release Form")
        doc_uuid = template_data["document_uuid"]

        # Create a version
        version_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Batch ID",
                        "type": "Text",
                        "required": True,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=version_payload,
            headers={"X-Change-Reason": "First version for PDF test"},
        )
        assert resp.status_code == 201

        # Download PDF
        resp = await client.post(
            f"/api/templates/{doc_uuid}/download-pdf",
            headers={"X-Change-Reason": "PDF downloaded for offline data collection"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"

        # Verify filename includes version number
        content_disposition = resp.headers["content-disposition"]
        assert "v1" in content_disposition
        assert "Batch_Release_Form" in content_disposition
        assert doc_uuid in content_disposition
        assert content_disposition.endswith('.pdf"')

    @pytest.mark.asyncio
    async def test_pdf_download_specific_version(
        self, client: AsyncClient
    ) -> None:
        """PDF download for a specific version uses that version's number in filename.

        Validates: Requirement 12.3
        """
        # Create template and two versions
        template_data = await create_template(client, name="QC Report")
        doc_uuid = template_data["document_uuid"]

        # Version 1
        v1_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Result",
                        "type": "Text",
                        "required": True,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=v1_payload,
            headers={"X-Change-Reason": "Version 1"},
        )
        assert resp.status_code == 201

        # Version 2
        v2_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Result Updated",
                        "type": "Text",
                        "required": True,
                        "help_text": "Updated field",
                        "default_value": None,
                        "config": {"max_length": 200},
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=v2_payload,
            headers={"X-Change-Reason": "Version 2"},
        )
        assert resp.status_code == 201

        # Download specific version 1 (historical)
        resp = await client.post(
            f"/api/templates/{doc_uuid}/download-pdf?version=1",
            headers={"X-Change-Reason": "Download historical version"},
        )
        assert resp.status_code == 200
        content_disposition = resp.headers["content-disposition"]
        assert "v1" in content_disposition

        # Download active version (v2)
        resp = await client.post(
            f"/api/templates/{doc_uuid}/download-pdf",
            headers={"X-Change-Reason": "Download active version"},
        )
        assert resp.status_code == 200
        content_disposition = resp.headers["content-disposition"]
        assert "v2" in content_disposition

    @pytest.mark.asyncio
    async def test_pdf_download_nonexistent_version_returns_404(
        self, client: AsyncClient
    ) -> None:
        """Downloading a non-existent version returns 404."""
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        # Create a version first so template is valid
        version_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Field",
                        "type": "Text",
                        "required": False,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=version_payload,
            headers={"X-Change-Reason": "Create version"},
        )
        assert resp.status_code == 201

        # Try to download non-existent version
        resp = await client.post(
            f"/api/templates/{doc_uuid}/download-pdf?version=99",
            headers={"X-Change-Reason": "Download non-existent version"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Audit trail logging for version events
# ---------------------------------------------------------------------------


class TestVersionAuditTrail:
    """Test that version events include proper audit trail information."""

    @pytest.mark.asyncio
    async def test_version_creation_requires_change_reason(
        self, client: AsyncClient
    ) -> None:
        """Version creation without X-Change-Reason header is rejected.

        Validates: Requirements 21.1, 21.2
        """
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        version_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Test Field",
                        "type": "Text",
                        "required": False,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }

        # Send without X-Change-Reason header (override default headers)
        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=version_payload,
            headers={
                "X-User-Id": "1",
                "X-Company-Id": "1",
                "X-Change-Reason": "",
            },
        )
        # Audit middleware should reject with 400
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_version_stores_change_reason(
        self, client: AsyncClient
    ) -> None:
        """Version creation stores the change reason for audit trail.

        Validates: Requirements 21.1, 21.2
        """
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        change_reason = "Updated template to include new regulatory fields"
        version_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Regulatory Field",
                        "type": "Text",
                        "required": True,
                        "help_text": "Required by new regulation",
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }

        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=version_payload,
            headers={"X-Change-Reason": change_reason},
        )
        assert resp.status_code == 201
        version_data = resp.json()
        assert version_data["change_reason"] == change_reason

        # Verify via GET endpoint as well
        resp = await client.get(
            f"/api/templates/{doc_uuid}/versions/{version_data['version_number']}"
        )
        assert resp.status_code == 200
        assert resp.json()["change_reason"] == change_reason

    @pytest.mark.asyncio
    async def test_pdf_download_requires_change_reason(
        self, client: AsyncClient
    ) -> None:
        """PDF download without X-Change-Reason header is rejected.

        Validates: Requirements 21.1, 21.2
        """
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        # Try to download without X-Change-Reason (empty string to override default)
        resp = await client.post(
            f"/api/templates/{doc_uuid}/download-pdf",
            headers={
                "X-User-Id": "1",
                "X-Company-Id": "1",
                "X-Change-Reason": "",
            },
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_version_fields_have_assigned_uuids(
        self, client: AsyncClient
    ) -> None:
        """Version fields are assigned unique Field-UUIDs upon creation.

        Validates: Requirement 10.3
        """
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        version_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Field One",
                        "type": "Text",
                        "required": False,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                    {
                        "element_type": "content_block",
                        "content_type": "heading_h1",
                        "text": "Section Header",
                    },
                    {
                        "element_type": "field",
                        "label": "Field Two",
                        "type": "Integer",
                        "required": True,
                        "help_text": None,
                        "default_value": "5",
                        "config": {"min_value": 0, "max_value": 100},
                    },
                ],
            },
            "user_id": 1,
        }

        resp = await client.post(
            f"/api/templates/{doc_uuid}/versions",
            json=version_payload,
            headers={"X-Change-Reason": "Test field UUID assignment"},
        )
        assert resp.status_code == 201
        version_data = resp.json()

        fields = version_data["fields"]
        assert len(fields) == 3

        # All fields should have unique UUIDs
        uuids = [f["field_uuid"] for f in fields]
        assert len(set(uuids)) == 3  # All unique

        # Field elements should have FLD- prefix
        field_elements = [f for f in fields if f["element_type"] == "field"]
        for f in field_elements:
            assert f["field_uuid"].startswith("FLD-")

        # Content block elements should have CB- prefix
        content_blocks = [f for f in fields if f["element_type"] == "content_block"]
        for cb in content_blocks:
            assert cb["field_uuid"].startswith("CB-")

        # Verify field_order is sequential
        orders = sorted([f["field_order"] for f in fields])
        assert orders == [0, 1, 2]


# ---------------------------------------------------------------------------
# Test: Concurrent version creation returns 409
# ---------------------------------------------------------------------------


class TestConcurrentVersionCreation:
    """Test that concurrent version creation is rejected with 409 Conflict."""

    @pytest.mark.asyncio
    async def test_concurrent_version_creation_returns_409(
        self, client: AsyncClient
    ) -> None:
        """Concurrent version creation attempt returns 409 Conflict.

        The service uses SELECT FOR UPDATE with nowait=True, which raises
        OperationalError when the row is already locked by another transaction.
        We simulate this by patching the TemplateService.create_version to
        raise the HTTPException that the service raises on OperationalError.

        Validates: Requirement 10.8
        """
        # Create a template first
        template_data = await create_template(client)
        doc_uuid = template_data["document_uuid"]

        version_payload = {
            "json_schema": {
                "elements": [
                    {
                        "element_type": "field",
                        "label": "Concurrent Field",
                        "type": "Text",
                        "required": False,
                        "help_text": None,
                        "default_value": None,
                        "config": {},
                    },
                ],
            },
            "user_id": 1,
        }

        # Patch the TemplateService.create_version to simulate a lock conflict
        from fastapi import HTTPException as FastAPIHTTPException

        async def mock_create_version(
            self, session, document_uuid, json_schema, user_id, change_reason
        ):
            raise FastAPIHTTPException(
                status_code=409,
                detail="Version creation in progress for this template",
            )

        with patch.object(
            TemplateService, "create_version", mock_create_version
        ):
            resp = await client.post(
                f"/api/templates/{doc_uuid}/versions",
                json=version_payload,
                headers={"X-Change-Reason": "Should get 409"},
            )
            assert resp.status_code == 409
            assert "Version creation in progress" in resp.json()["detail"]
