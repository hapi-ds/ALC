"""Unit tests for RBAC integration with workflow execution.

Tests that the workflow transition endpoint enforces permission checks:
- Approval transitions (in signature_required_transitions) require
  ``workflows:approve`` permission.
- Document edit transitions (all others) require ``documents:update``
  permission.
- HTTP 403 is returned with a descriptive error message on denial.

References:
    - Task 10.1: Integrate RBAC with Workflow Execution
    - Requirements: 12.1, 12.2, 12.3
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.services.workflow_engine import TransitionResult


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession for database operations."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.execute = AsyncMock()
    session.close = AsyncMock()

    # Configure execute to return a result with scalar_one_or_none
    mock_execute_result = MagicMock()
    mock_document = MagicMock()
    mock_document.id = 1
    mock_document.document_uuid = "2025-00001"
    mock_execute_result.scalar_one_or_none.return_value = mock_document
    session.execute.return_value = mock_execute_result

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
            "Authorization": "Bearer test-token",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


class TestWorkflowRBACApprovalTransitions:
    """Tests that approval transitions require workflows:approve permission.

    Requirements: 12.1, 12.3
    """

    @pytest.mark.asyncio
    async def test_approval_transition_allowed_with_permission(
        self, client: AsyncClient
    ):
        """User with workflows:approve permission can execute approval transitions.

        Requirements: 12.1
        """
        mock_result = TransitionResult(
            success=True,
            previous_state="Review",
            new_state="Approved",
            requires_signature=True,
            triggers_training=False,
        )

        # Workflow with "Review→Approved" as a signature-required transition
        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = ["Review\u2192Approved"]

        mock_doc_state = MagicMock()
        mock_doc_state.current_state = "Review"

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.request_transition",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.resolve_workflow",
                new_callable=AsyncMock,
                return_value=mock_workflow_def,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.get_document_state",
                new_callable=AsyncMock,
                return_value=mock_doc_state,
            ),
            patch(
                "alcoabase.api.workflows.require_permission",
                return_value=AsyncMock(return_value=None),
            ) as mock_require_perm,
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Approved"},
                headers={"X-Change-Reason": "Approving document"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["new_state"] == "Approved"

            # Verify workflows:approve permission was checked
            mock_require_perm.assert_called_once_with("workflows", "approve")

    @pytest.mark.asyncio
    async def test_approval_transition_denied_returns_403(
        self, client: AsyncClient
    ):
        """User without workflows:approve permission gets HTTP 403.

        Requirements: 12.1, 12.3
        """
        from fastapi import HTTPException

        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = ["Review\u2192Approved"]

        mock_doc_state = MagicMock()
        mock_doc_state.current_state = "Review"

        # Permission check raises 403
        async def _deny_permission(*args, **kwargs):
            raise HTTPException(
                status_code=403,
                detail="Missing permission: approve on workflows",
            )

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.resolve_workflow",
                new_callable=AsyncMock,
                return_value=mock_workflow_def,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.get_document_state",
                new_callable=AsyncMock,
                return_value=mock_doc_state,
            ),
            patch(
                "alcoabase.api.workflows.require_permission",
                return_value=_deny_permission,
            ),
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Approved"},
                headers={"X-Change-Reason": "Attempting approval"},
            )

            assert response.status_code == 403
            data = response.json()
            assert "Missing permission" in data["detail"]
            assert "approve" in data["detail"]
            assert "workflows" in data["detail"]


class TestWorkflowRBACDocumentEditTransitions:
    """Tests that document edit transitions require documents:update permission.

    Requirements: 12.2, 12.3
    """

    @pytest.mark.asyncio
    async def test_edit_transition_allowed_with_permission(
        self, client: AsyncClient
    ):
        """User with documents:update permission can execute edit transitions.

        Requirements: 12.2
        """
        mock_result = TransitionResult(
            success=True,
            previous_state="Draft",
            new_state="Review",
            requires_signature=False,
            triggers_training=False,
        )

        # Workflow where "Draft→Review" is NOT in signature_required_transitions
        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = ["Review\u2192Approved"]

        mock_doc_state = MagicMock()
        mock_doc_state.current_state = "Draft"

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.request_transition",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.resolve_workflow",
                new_callable=AsyncMock,
                return_value=mock_workflow_def,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.get_document_state",
                new_callable=AsyncMock,
                return_value=mock_doc_state,
            ),
            patch(
                "alcoabase.api.workflows.require_permission",
                return_value=AsyncMock(return_value=None),
            ) as mock_require_perm,
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Review"},
                headers={"X-Change-Reason": "Moving to review"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["new_state"] == "Review"

            # Verify documents:update permission was checked
            mock_require_perm.assert_called_once_with("documents", "update")

    @pytest.mark.asyncio
    async def test_edit_transition_denied_returns_403(
        self, client: AsyncClient
    ):
        """User without documents:update permission gets HTTP 403.

        Requirements: 12.2, 12.3
        """
        from fastapi import HTTPException

        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = ["Review\u2192Approved"]

        mock_doc_state = MagicMock()
        mock_doc_state.current_state = "Draft"

        # Permission check raises 403
        async def _deny_permission(*args, **kwargs):
            raise HTTPException(
                status_code=403,
                detail="Missing permission: update on documents",
            )

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.resolve_workflow",
                new_callable=AsyncMock,
                return_value=mock_workflow_def,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.get_document_state",
                new_callable=AsyncMock,
                return_value=mock_doc_state,
            ),
            patch(
                "alcoabase.api.workflows.require_permission",
                return_value=_deny_permission,
            ),
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Review"},
                headers={"X-Change-Reason": "Attempting edit transition"},
            )

            assert response.status_code == 403
            data = response.json()
            assert "Missing permission" in data["detail"]
            assert "update" in data["detail"]
            assert "documents" in data["detail"]


class TestWorkflowRBACTransitionTypeDetection:
    """Tests that the correct permission type is determined based on
    whether the transition is in signature_required_transitions.

    Requirements: 12.1, 12.2
    """

    @pytest.mark.asyncio
    async def test_transition_in_signature_list_checks_approve(
        self, client: AsyncClient
    ):
        """Transition matching signature_required_transitions checks workflows:approve.

        Requirements: 12.1
        """
        mock_result = TransitionResult(
            success=True,
            previous_state="Review",
            new_state="Approved",
            requires_signature=True,
            triggers_training=False,
        )

        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = [
            "Review\u2192Approved",
            "Approved\u2192Active",
        ]

        mock_doc_state = MagicMock()
        mock_doc_state.current_state = "Review"

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.request_transition",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.resolve_workflow",
                new_callable=AsyncMock,
                return_value=mock_workflow_def,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.get_document_state",
                new_callable=AsyncMock,
                return_value=mock_doc_state,
            ),
            patch(
                "alcoabase.api.workflows.require_permission",
                return_value=AsyncMock(return_value=None),
            ) as mock_require_perm,
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Approved"},
                headers={"X-Change-Reason": "Approving"},
            )

            assert response.status_code == 200
            mock_require_perm.assert_called_once_with("workflows", "approve")

    @pytest.mark.asyncio
    async def test_transition_not_in_signature_list_checks_update(
        self, client: AsyncClient
    ):
        """Transition NOT in signature_required_transitions checks documents:update.

        Requirements: 12.2
        """
        mock_result = TransitionResult(
            success=True,
            previous_state="Draft",
            new_state="Review",
            requires_signature=False,
            triggers_training=False,
        )

        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = ["Review\u2192Approved"]

        mock_doc_state = MagicMock()
        mock_doc_state.current_state = "Draft"

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.request_transition",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.resolve_workflow",
                new_callable=AsyncMock,
                return_value=mock_workflow_def,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.get_document_state",
                new_callable=AsyncMock,
                return_value=mock_doc_state,
            ),
            patch(
                "alcoabase.api.workflows.require_permission",
                return_value=AsyncMock(return_value=None),
            ) as mock_require_perm,
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Review"},
                headers={"X-Change-Reason": "Moving to review"},
            )

            assert response.status_code == 200
            mock_require_perm.assert_called_once_with("documents", "update")

    @pytest.mark.asyncio
    async def test_no_doc_state_uses_empty_current_state(
        self, client: AsyncClient
    ):
        """When no document state exists, current_state defaults to empty string.

        This means the transition string won't match signature_required_transitions,
        so documents:update permission is checked.

        Requirements: 12.2
        """
        mock_result = TransitionResult(
            success=True,
            previous_state="",
            new_state="Draft",
            requires_signature=False,
            triggers_training=False,
        )

        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = ["Review\u2192Approved"]

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.request_transition",
                new_callable=AsyncMock,
                return_value=mock_result,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.resolve_workflow",
                new_callable=AsyncMock,
                return_value=mock_workflow_def,
            ),
            patch(
                "alcoabase.api.workflows.WorkflowEngine.get_document_state",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "alcoabase.api.workflows.require_permission",
                return_value=AsyncMock(return_value=None),
            ) as mock_require_perm,
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Draft"},
                headers={"X-Change-Reason": "Initial state"},
            )

            assert response.status_code == 200
            mock_require_perm.assert_called_once_with("documents", "update")
