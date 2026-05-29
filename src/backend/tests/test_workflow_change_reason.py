"""Unit tests for change reason storage in workflow transitions.

Tests that the X-Change-Reason header is correctly extracted at the API level
and that the WorkflowEngine._record_transition_audit method normalizes the
change_reason value (strip whitespace, store None for empty/whitespace-only,
truncate to 500 characters).

References:
    - Task 13.2: Write unit tests for change reason storage
    - Requirements: 6.1, 6.2, 6.3
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.services.workflow_engine import (
    TransitionResult,
    WorkflowEngine,
    WorkflowTransitionAudit,
)


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


@pytest_asyncio.fixture
async def client(mock_session: AsyncMock, tenant_context: TenantContext) -> AsyncClient:
    """Create an httpx AsyncClient with overridden dependencies."""

    # Configure mock_session.execute to return a result with scalar_one_or_none
    mock_execute_result = MagicMock()
    mock_document = MagicMock()
    mock_document.id = 1
    mock_document.document_uuid = "2025-00001"
    mock_execute_result.scalar_one_or_none.return_value = mock_document
    mock_session.execute.return_value = mock_execute_result

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


# ---------------------------------------------------------------------------
# Test: API-level X-Change-Reason header extraction (Requirements 6.1)
# ---------------------------------------------------------------------------


class TestAPIChangeReasonExtraction:
    """Tests that POST /api/workflows/transition correctly extracts
    the X-Change-Reason header and passes it to the engine."""

    @pytest.mark.asyncio
    async def test_change_reason_header_passed_to_engine(
        self, client: AsyncClient
    ):
        """X-Change-Reason header value is passed to engine.request_transition.

        Requirements: 6.1
        """
        mock_result = TransitionResult(
            success=True,
            previous_state="Draft",
            new_state="Review",
            requires_signature=False,
            triggers_training=False,
        )

        # Mock Document returned by session.execute for the document lookup
        mock_document = MagicMock()
        mock_document.id = 1
        mock_document.document_uuid = "2025-00001"

        # Mock WorkflowDefinition returned by resolve_workflow
        mock_workflow_def = MagicMock()
        mock_workflow_def.signature_required_transitions = []

        # Mock DocumentState returned by get_document_state
        mock_doc_state = MagicMock()
        mock_doc_state.current_state = "Draft"

        with (
            patch(
                "alcoabase.api.workflows.WorkflowEngine.request_transition",
                new_callable=AsyncMock,
                return_value=mock_result,
            ) as mock_request_transition,
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
            ),
        ):
            response = await client.post(
                "/api/workflows/transition",
                json={"document_uuid": "2025-00001", "target_state": "Review"},
                headers={"X-Change-Reason": "Moving to review phase"},
            )

            assert response.status_code == 200
            # Verify change_reason was passed to the engine
            mock_request_transition.assert_called_once()
            call_kwargs = mock_request_transition.call_args
            assert call_kwargs.kwargs["change_reason"] == "Moving to review phase"

    @pytest.mark.asyncio
    async def test_empty_change_reason_header_rejected_by_middleware(
        self, client: AsyncClient
    ):
        """Empty X-Change-Reason header is rejected by AuditMiddleware with 400.

        The AuditMiddleware requires a non-empty X-Change-Reason header on
        mutating requests. Empty or whitespace-only values are rejected before
        reaching the endpoint handler.

        Requirements: 6.3
        """
        response = await client.post(
            "/api/workflows/transition",
            json={"document_uuid": "2025-00001", "target_state": "Review"},
            headers={"X-Change-Reason": ""},
        )

        assert response.status_code == 400
        data = response.json()
        assert "X-Change-Reason" in data["detail"]


# ---------------------------------------------------------------------------
# Test: Engine-level change reason normalization (Requirements 6.1, 6.2, 6.3)
# ---------------------------------------------------------------------------


class TestEngineChangeReasonNormalization:
    """Tests that WorkflowEngine._record_transition_audit normalizes
    the change_reason correctly before storing."""

    @pytest.mark.asyncio
    async def test_normal_change_reason_stored_correctly(
        self, mock_session: AsyncMock
    ):
        """A normal change reason string is stored as-is (after strip).

        Requirements: 6.1
        """
        engine = WorkflowEngine()

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason="Valid reason",
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert isinstance(audit_entry, WorkflowTransitionAudit)
        assert audit_entry.change_reason == "Valid reason"

    @pytest.mark.asyncio
    async def test_whitespace_only_stored_as_none(
        self, mock_session: AsyncMock
    ):
        """Whitespace-only change reason (spaces) is stored as None.

        Requirements: 6.3
        """
        engine = WorkflowEngine()

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason="   ",
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason is None

    @pytest.mark.asyncio
    async def test_tabs_and_newlines_only_stored_as_none(
        self, mock_session: AsyncMock
    ):
        """Whitespace-only change reason with tabs/newlines is stored as None.

        Requirements: 6.3
        """
        engine = WorkflowEngine()

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason="   \t\n  ",
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason is None

    @pytest.mark.asyncio
    async def test_empty_string_stored_as_none(
        self, mock_session: AsyncMock
    ):
        """Empty string change reason is stored as None.

        Requirements: 6.3
        """
        engine = WorkflowEngine()

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason="",
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason is None

    @pytest.mark.asyncio
    async def test_none_stored_as_none(
        self, mock_session: AsyncMock
    ):
        """None change reason is stored as None.

        Requirements: 6.3
        """
        engine = WorkflowEngine()

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason=None,
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason is None

    @pytest.mark.asyncio
    async def test_truncation_at_500_characters(
        self, mock_session: AsyncMock
    ):
        """Change reason exceeding 500 characters is truncated to exactly 500.

        Requirements: 6.2
        """
        engine = WorkflowEngine()
        long_reason = "a" * 600

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason=long_reason,
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason is not None
        assert len(audit_entry.change_reason) == 500
        assert audit_entry.change_reason == "a" * 500

    @pytest.mark.asyncio
    async def test_leading_trailing_whitespace_stripped(
        self, mock_session: AsyncMock
    ):
        """Leading and trailing whitespace is stripped before storing.

        Requirements: 6.1
        """
        engine = WorkflowEngine()

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason="  reason  ",
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason == "reason"

    @pytest.mark.asyncio
    async def test_exactly_500_chars_not_truncated(
        self, mock_session: AsyncMock
    ):
        """A change reason of exactly 500 characters is stored without truncation.

        Requirements: 6.2
        """
        engine = WorkflowEngine()
        exact_reason = "b" * 500

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason=exact_reason,
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason == exact_reason
        assert len(audit_entry.change_reason) == 500

    @pytest.mark.asyncio
    async def test_truncation_applied_after_strip(
        self, mock_session: AsyncMock
    ):
        """Truncation is applied after stripping whitespace.

        A string with leading/trailing whitespace that is >500 chars after
        stripping should be truncated to 500.

        Requirements: 6.1, 6.2
        """
        engine = WorkflowEngine()
        # 510 chars of content + whitespace padding
        reason_with_whitespace = "  " + "c" * 510 + "  "

        await engine._record_transition_audit(
            session=mock_session,
            document_id=1,
            user_id=42,
            previous_state="Draft",
            new_state="Review",
            change_reason=reason_with_whitespace,
        )

        mock_session.add.assert_called_once()
        audit_entry = mock_session.add.call_args[0][0]
        assert audit_entry.change_reason is not None
        assert len(audit_entry.change_reason) == 500
        assert audit_entry.change_reason == "c" * 500
