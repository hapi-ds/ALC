"""Unit tests for Workflow API endpoints.

Tests the CRUD operations, versioning, validation, and tenant scoping
for the /api/workflows endpoints.

References:
    - Tasks 3.1-3.6: Backend API endpoint additions and tenant scoping fixes
    - Requirements: 5.1, 5.2, 8.1, 8.2, 8.7, 9.3, 9.4, 10.1-10.7, 11.1-11.6, 12.1-12.5, 16.4
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.workflow import (
    DocumentState,
    WorkflowDefinition,
    WorkflowVersion,
)
from alcoabase.services.workflow_engine import ValidationResult, WorkflowEngine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession for database operations."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def tenant_context() -> TenantContext:
    """Create a test TenantContext."""
    return TenantContext(
        company_id=1,
        company_slug="test-company",
        user_id=42,
        membership_role="admin",
    )


@pytest.fixture
def sample_workflow() -> WorkflowDefinition:
    """Create a sample WorkflowDefinition model instance."""
    wf = WorkflowDefinition(
        id=1,
        name="SOP Lifecycle",
        document_tag="SOP",
        bpmn_xml="<definitions><process></process></definitions>",
        signature_required_transitions=["Review\u2192Approved"],
        training_trigger_transitions=["Approved\u2192InTraining"],
        is_active=True,
        risk_level="medium",
        auto_assignment_config={"strategy": "round-robin"},
        current_version=2,
        created_by=42,
        company_id=1,
    )
    return wf


@pytest.fixture
def sample_version() -> WorkflowVersion:
    """Create a sample WorkflowVersion model instance."""
    v = WorkflowVersion(
        id=10,
        workflow_id=1,
        version_number=1,
        bpmn_xml="<definitions><process></process></definitions>",
        name="SOP Lifecycle",
        document_tag="SOP",
        risk_level="low",
        signature_required_transitions=[],
        training_trigger_transitions=[],
        auto_assignment_config=None,
        created_by=42,
        change_reason="Initial creation",
        company_id=1,
    )
    v.created_at = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)
    return v


@pytest_asyncio.fixture
async def client(mock_session: AsyncMock, tenant_context: TenantContext) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""

    async def _override_get_db_session():
        yield mock_session

    async def _override_get_tenant_context():
        return tenant_context

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_tenant_context] = _override_get_tenant_context

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Unit test operation",
            "X-User-Id": "42",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_scalar_result(value):
    """Create a mock execute result that returns a scalar."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    return mock_result


def _mock_scalars_result(values):
    """Create a mock execute result that returns scalars."""
    mock_result = MagicMock()
    mock_result.scalars.return_value = MagicMock(all=MagicMock(return_value=values))
    return mock_result


# ---------------------------------------------------------------------------
# Test: GET /api/workflows/{workflow_id} (Task 3.1)
# ---------------------------------------------------------------------------


class TestGetWorkflow:
    """Tests for GET /api/workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_get_workflow_success(
        self, client: AsyncClient, mock_session: AsyncMock, sample_workflow: WorkflowDefinition
    ):
        """Returns workflow when found and belongs to tenant."""
        mock_session.execute.return_value = _mock_scalar_result(sample_workflow)

        response = await client.get("/api/workflows/1")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "SOP Lifecycle"
        assert data["risk_level"] == "medium"
        assert data["auto_assignment_config"] == {"strategy": "round-robin"}
        assert data["current_version_number"] == 2

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(
        self, client: AsyncClient, mock_session: AsyncMock
    ):
        """Returns 404 when workflow not found or wrong tenant."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.get("/api/workflows/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Workflow not found"


# ---------------------------------------------------------------------------
# Test: DELETE /api/workflows/{workflow_id} (Task 3.2)
# ---------------------------------------------------------------------------


class TestDeleteWorkflow:
    """Tests for DELETE /api/workflows/{workflow_id}."""

    @pytest.mark.asyncio
    async def test_delete_workflow_success(
        self, client: AsyncClient, mock_session: AsyncMock, sample_workflow: WorkflowDefinition
    ):
        """Returns 204 when workflow deleted successfully."""
        mock_session.execute.side_effect = [
            _mock_scalar_result(sample_workflow),  # find workflow
            _mock_scalar_result(None),  # no active document states
            MagicMock(),  # delete versions
        ]

        response = await client.delete("/api/workflows/1")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_workflow_not_found(
        self, client: AsyncClient, mock_session: AsyncMock
    ):
        """Returns 404 when workflow not found or wrong tenant."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.delete("/api/workflows/999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_workflow_in_use(
        self, client: AsyncClient, mock_session: AsyncMock, sample_workflow: WorkflowDefinition
    ):
        """Returns 409 when workflow has active document states."""
        doc_state = DocumentState(
            id=1, document_id=1, current_state="Draft", workflow_id=1, updated_by=1
        )
        mock_session.execute.side_effect = [
            _mock_scalar_result(sample_workflow),  # find workflow
            _mock_scalar_result(doc_state),  # active document state found
        ]

        response = await client.delete("/api/workflows/1")

        assert response.status_code == 409
        assert "in use" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Test: GET /api/workflows/{workflow_id}/versions (Task 3.3)
# ---------------------------------------------------------------------------


class TestListWorkflowVersions:
    """Tests for GET /api/workflows/{workflow_id}/versions."""

    @pytest.mark.asyncio
    async def test_list_versions_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_workflow: WorkflowDefinition,
        sample_version: WorkflowVersion,
    ):
        """Returns version list ordered by version_number descending."""
        mock_session.execute.side_effect = [
            _mock_scalar_result(sample_workflow),  # verify workflow exists
            _mock_scalars_result([sample_version]),  # versions
        ]

        response = await client.get("/api/workflows/1/versions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["version_number"] == 1
        assert data[0]["change_reason"] == "Initial creation"

    @pytest.mark.asyncio
    async def test_list_versions_workflow_not_found(
        self, client: AsyncClient, mock_session: AsyncMock
    ):
        """Returns 404 when workflow not found or wrong tenant."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.get("/api/workflows/999/versions")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: GET /api/workflows/{workflow_id}/versions/{version_id} (Task 3.4)
# ---------------------------------------------------------------------------


class TestGetWorkflowVersion:
    """Tests for GET /api/workflows/{workflow_id}/versions/{version_id}."""

    @pytest.mark.asyncio
    async def test_get_version_success(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_workflow: WorkflowDefinition,
        sample_version: WorkflowVersion,
    ):
        """Returns version detail with all fields."""
        mock_session.execute.side_effect = [
            _mock_scalar_result(sample_workflow),  # verify workflow
            _mock_scalar_result(sample_version),  # get version
        ]

        response = await client.get("/api/workflows/1/versions/10")

        assert response.status_code == 200
        data = response.json()
        assert data["version_number"] == 1
        assert data["bpmn_xml"] == "<definitions><process></process></definitions>"
        assert data["name"] == "SOP Lifecycle"
        assert data["change_reason"] == "Initial creation"

    @pytest.mark.asyncio
    async def test_get_version_not_found(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_workflow: WorkflowDefinition,
    ):
        """Returns 404 when version not found."""
        mock_session.execute.side_effect = [
            _mock_scalar_result(sample_workflow),  # workflow exists
            _mock_scalar_result(None),  # version not found
        ]

        response = await client.get("/api/workflows/1/versions/999")

        assert response.status_code == 404
        assert response.json()["detail"] == "Version not found"

    @pytest.mark.asyncio
    async def test_get_version_workflow_not_found(
        self, client: AsyncClient, mock_session: AsyncMock
    ):
        """Returns 404 when workflow not found."""
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.get("/api/workflows/999/versions/10")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Test: POST /api/workflows/validate (Task 3.5)
# ---------------------------------------------------------------------------


class TestValidateWorkflow:
    """Tests for POST /api/workflows/validate."""

    @pytest.mark.asyncio
    @patch("alcoabase.services.workflow_engine.validate_bpmn_workflow")
    async def test_validate_valid_workflow(
        self, mock_validate, client: AsyncClient
    ):
        """Returns is_valid=true for valid BPMN XML."""
        mock_validate.return_value = ValidationResult(is_valid=True, errors=[])

        response = await client.post(
            "/api/workflows/validate",
            json={
                "bpmn_xml": "<definitions><process><task/></process></definitions>",
                "signature_required_transitions": [],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["errors"] == []

    @pytest.mark.asyncio
    @patch("alcoabase.services.workflow_engine.validate_bpmn_workflow")
    async def test_validate_invalid_workflow(
        self, mock_validate, client: AsyncClient
    ):
        """Returns is_valid=false with errors for invalid BPMN XML."""
        mock_validate.return_value = ValidationResult(
            is_valid=False, errors=["Unreachable states detected: ['Orphan']"]
        )

        response = await client.post(
            "/api/workflows/validate",
            json={"bpmn_xml": "<definitions><process></process></definitions>"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert len(data["errors"]) == 1

    @pytest.mark.asyncio
    async def test_validate_empty_bpmn_xml(self, client: AsyncClient):
        """Returns 422 when bpmn_xml is empty."""
        response = await client.post(
            "/api/workflows/validate",
            json={"bpmn_xml": ""},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_validate_missing_bpmn_xml(self, client: AsyncClient):
        """Returns 422 when bpmn_xml is missing."""
        response = await client.post(
            "/api/workflows/validate",
            json={},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Tenant scoping on existing endpoints (Task 3.6)
# ---------------------------------------------------------------------------


class TestTenantScoping:
    """Tests for tenant scoping on POST, PUT, and GET list endpoints."""

    @pytest.mark.asyncio
    async def test_list_workflows_tenant_scoped(
        self,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_workflow: WorkflowDefinition,
    ):
        """GET list returns only workflows for the current tenant."""
        mock_session.execute.return_value = _mock_scalars_result([sample_workflow])

        response = await client.get("/api/workflows")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == 1
        assert data[0]["risk_level"] == "medium"
        assert data[0]["current_version_number"] == 2

    @pytest.mark.asyncio
    @patch.object(WorkflowEngine, "validate_workflow_definition")
    async def test_create_workflow_sets_tenant(
        self,
        mock_validate,
        client: AsyncClient,
        mock_session: AsyncMock,
    ):
        """POST creates workflow with company_id and created_by from tenant."""
        mock_validate.return_value = ValidationResult(is_valid=True, errors=[])

        # Mock flush to set the id on the workflow
        created_workflows = []

        def capture_add(obj):
            if isinstance(obj, WorkflowDefinition):
                obj.id = 1
                obj.current_version = 1
                created_workflows.append(obj)

        mock_session.add.side_effect = capture_add

        response = await client.post(
            "/api/workflows",
            json={
                "name": "New Workflow",
                "document_tag": "REPORT",
                "bpmn_xml": "<definitions><process><task/></process></definitions>",
                "risk_level": "high",
            },
        )

        assert response.status_code == 201
        # Verify the workflow was created with tenant fields
        assert len(created_workflows) == 1
        wf = created_workflows[0]
        assert wf.company_id == 1
        assert wf.created_by == 42

    @pytest.mark.asyncio
    @patch.object(WorkflowEngine, "validate_workflow_definition")
    async def test_update_workflow_tenant_scoped(
        self,
        mock_validate,
        client: AsyncClient,
        mock_session: AsyncMock,
        sample_workflow: WorkflowDefinition,
    ):
        """PUT returns 404 for workflow belonging to different tenant."""
        # Simulate workflow not found (wrong tenant)
        mock_session.execute.return_value = _mock_scalar_result(None)

        response = await client.put(
            "/api/workflows/1",
            json={"name": "Updated Name"},
        )

        assert response.status_code == 404
