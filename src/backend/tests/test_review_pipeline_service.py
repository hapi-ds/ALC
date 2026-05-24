"""Unit tests for ReviewPipelineService.

Tests the core review pipeline orchestration including submission,
session queries, approval/rejection, and action item CRUD.

References:
    - Task 5.1: Implement ReviewPipelineService core
    - Requirements: 1.1, 1.2, 1.3, 1.8, 1.9, 1.10, 10.1–10.8
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.models.audit_profile import AuditProfile
from alcoabase.models.document import Document
from alcoabase.models.review import ActionItem, AgentReview, ReviewSession
from alcoabase.services.review_pipeline import (
    ConflictError,
    ReviewPipelineService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session_factory():
    """Create a mock async session factory with context manager support."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.refresh = AsyncMock()
    session.expunge = MagicMock()

    # async_sessionmaker() returns an async context manager directly
    factory = MagicMock(
        return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=session),
            __aexit__=AsyncMock(return_value=False),
        )
    )

    return factory, session


@pytest.fixture
def mock_agent_registry():
    """Create a mock AgentRegistryService."""
    return AsyncMock()


@pytest.fixture
def mock_storage_service():
    """Create a mock StorageService."""
    return AsyncMock()


@pytest.fixture
def mock_inference_client():
    """Create a mock InferenceClient."""
    return AsyncMock()


@pytest.fixture
def service(
    mock_session_factory,
    mock_agent_registry,
    mock_storage_service,
    mock_inference_client,
):
    """Create a ReviewPipelineService with mocked dependencies."""
    factory, _ = mock_session_factory
    return ReviewPipelineService(
        session_factory=factory,
        agent_registry=mock_agent_registry,
        storage_service=mock_storage_service,
        inference_client=mock_inference_client,
    )


@pytest.fixture
def sample_audit_profile():
    """Create a sample audit profile for testing."""
    profile = AuditProfile(
        id=1,
        company_id=1,
        name="Default Profile",
        regulatory_frameworks=["GMP", "ISO 13485"],
        assigned_agent_ids=[10, 20, 30],
        quorum=2,
        severity_thresholds={
            "critical": 25.0,
            "major": 10.0,
            "minor": 3.0,
            "informational": 0.5,
        },
        is_default=True,
        is_active=True,
    )
    return profile


@pytest.fixture
def sample_document():
    """Create a sample document for testing."""
    return Document(
        id=1,
        document_uuid="2025-00001",
        title="Test SOP",
        folder_path="/sops",
        document_type="SOP",
        current_status="Approved",
        created_by=1,
        company_id=1,
    )


# ---------------------------------------------------------------------------
# submit_review Tests
# ---------------------------------------------------------------------------


class TestSubmitReview:
    """Tests for ReviewPipelineService.submit_review."""

    @pytest.mark.asyncio
    async def test_submit_review_document_not_found(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should raise ValueError when document doesn't exist."""
        factory, session = mock_session_factory

        # Document query returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        with pytest.raises(ValueError, match="Document 999 not found"):
            await svc.submit_review(
                document_id=999,
                document_version_id=1,
                audit_profile_id=None,
                company_id=1,
                user_id=1,
            )

    @pytest.mark.asyncio
    async def test_submit_review_active_session_conflict(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client, sample_document,
    ):
        """Should raise ConflictError when active session exists."""
        factory, session = mock_session_factory

        # First call: document found; Second call: active session found
        existing_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="InProgress",
            submitted_by=1,
        )
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = sample_document
        active_result = MagicMock()
        active_result.scalar_one_or_none.return_value = existing_session

        session.execute.side_effect = [doc_result, active_result]

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        with pytest.raises(ConflictError, match="active review session"):
            await svc.submit_review(
                document_id=1,
                document_version_id=1,
                audit_profile_id=None,
                company_id=1,
                user_id=1,
            )

    @pytest.mark.asyncio
    async def test_submit_review_no_default_profile(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client, sample_document,
    ):
        """Should raise ValueError when no default audit profile exists."""
        factory, session = mock_session_factory

        # Document found, no active session
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = sample_document
        no_active_result = MagicMock()
        no_active_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [doc_result, no_active_result]

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        # Mock the audit profile service to return None for default
        with patch.object(
            svc._audit_profile_service, "get_default_profile",
            new_callable=AsyncMock, return_value=None,
        ):
            with pytest.raises(ValueError, match="No default audit profile"):
                await svc.submit_review(
                    document_id=1,
                    document_version_id=1,
                    audit_profile_id=None,
                    company_id=1,
                    user_id=1,
                )

    @pytest.mark.asyncio
    async def test_submit_review_success(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client, sample_document, sample_audit_profile,
    ):
        """Should create session and agent reviews on successful submission."""
        factory, session = mock_session_factory

        # Document found, no active session
        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = sample_document
        no_active_result = MagicMock()
        no_active_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [doc_result, no_active_result]

        # Mock refresh to set IDs
        call_count = [0]

        async def mock_refresh(obj):
            if isinstance(obj, ReviewSession):
                obj.id = 42
            elif isinstance(obj, AgentReview):
                call_count[0] += 1
                obj.id = 100 + call_count[0]

        session.refresh.side_effect = mock_refresh

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        # Mock audit profile service
        with patch.object(
            svc._audit_profile_service, "get_default_profile",
            new_callable=AsyncMock, return_value=sample_audit_profile,
        ):
            # Mock Celery task dispatch
            with patch.object(svc, "_dispatch_agent_tasks"):
                result = await svc.submit_review(
                    document_id=1,
                    document_version_id=1,
                    audit_profile_id=None,
                    company_id=1,
                    user_id=1,
                )

        assert result.status == "Pending"
        assert result.company_id == 1
        assert result.document_id == 1
        # session.add should be called for session + 3 agent reviews
        assert session.add.call_count == 4


# ---------------------------------------------------------------------------
# approve_session / reject_session Tests
# ---------------------------------------------------------------------------


class TestApproveRejectSession:
    """Tests for session approval and rejection."""

    @pytest.mark.asyncio
    async def test_approve_completed_session(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should approve a session with Completed status."""
        factory, session = mock_session_factory

        completed_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Completed",
            submitted_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = completed_session
        session.execute.return_value = result_mock

        async def mock_refresh(obj):
            pass  # Status already set by the service

        session.refresh.side_effect = mock_refresh

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        result = await svc.approve_session(session_id=1, company_id=1)
        assert result.status == "Approved"

    @pytest.mark.asyncio
    async def test_reject_completed_session(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should reject a session with Completed status."""
        factory, session = mock_session_factory

        completed_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Completed",
            submitted_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = completed_session
        session.execute.return_value = result_mock

        async def mock_refresh(obj):
            pass

        session.refresh.side_effect = mock_refresh

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        result = await svc.reject_session(session_id=1, company_id=1)
        assert result.status == "Rejected"

    @pytest.mark.asyncio
    async def test_approve_non_completed_session_raises(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should raise ValueError when approving a non-Completed session."""
        factory, session = mock_session_factory

        pending_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Pending",
            submitted_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = pending_session
        session.execute.return_value = result_mock

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        with pytest.raises(ValueError, match="Only completed sessions"):
            await svc.approve_session(session_id=1, company_id=1)

    @pytest.mark.asyncio
    async def test_reject_non_completed_session_raises(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should raise ValueError when rejecting a non-Completed session."""
        factory, session = mock_session_factory

        in_progress_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="InProgress",
            submitted_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = in_progress_session
        session.execute.return_value = result_mock

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        with pytest.raises(ValueError, match="Only completed sessions"):
            await svc.reject_session(session_id=1, company_id=1)

    @pytest.mark.asyncio
    async def test_approve_session_not_found(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should raise ValueError when session doesn't exist."""
        factory, session = mock_session_factory

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        with pytest.raises(ValueError, match="not found"):
            await svc.approve_session(session_id=999, company_id=1)


# ---------------------------------------------------------------------------
# Action Item Tests
# ---------------------------------------------------------------------------


class TestActionItems:
    """Tests for action item CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_action_item_success(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should create an action item with Open status."""
        factory, session = mock_session_factory

        # Session exists
        review_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Completed",
            submitted_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = review_session
        session.execute.return_value = result_mock

        async def mock_refresh(obj):
            if isinstance(obj, ActionItem):
                obj.id = 1

        session.refresh.side_effect = mock_refresh

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        item = await svc.create_action_item(
            session_id=1,
            finding_id="F-001",
            title="Fix critical finding",
            description="Address the critical compliance gap",
            severity="Critical",
            assigned_to=5,
            company_id=1,
        )

        assert item.status == "Open"
        assert item.finding_id == "F-001"
        assert item.severity == "Critical"
        assert item.assigned_to == 5

    @pytest.mark.asyncio
    async def test_create_action_item_session_not_found(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should raise ValueError when session doesn't exist."""
        factory, session = mock_session_factory

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        with pytest.raises(ValueError, match="not found"):
            await svc.create_action_item(
                session_id=999,
                finding_id="F-001",
                title="Test",
                description="Test",
                severity="Minor",
                assigned_to=None,
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_update_action_item_valid_transition(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should update action item with valid status transition."""
        factory, session = mock_session_factory

        review_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Completed",
            submitted_by=1,
        )
        action_item = ActionItem(
            id=10, session_id=1, finding_id="F-001",
            title="Test", description="Test",
            severity="Major", status="Open",
        )

        # First call returns session, second returns action item
        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = review_session
        item_result = MagicMock()
        item_result.scalar_one_or_none.return_value = action_item

        session.execute.side_effect = [session_result, item_result]

        async def mock_refresh(obj):
            pass

        session.refresh.side_effect = mock_refresh

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        result = await svc.update_action_item(
            session_id=1,
            item_id=10,
            status="InProgress",
            resolution_note=None,
            company_id=1,
        )

        assert result.status == "InProgress"

    @pytest.mark.asyncio
    async def test_update_action_item_invalid_transition(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should raise ValueError for invalid status transition."""
        factory, session = mock_session_factory

        review_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Completed",
            submitted_by=1,
        )
        # Action item in terminal state "Resolved"
        action_item = ActionItem(
            id=10, session_id=1, finding_id="F-001",
            title="Test", description="Test",
            severity="Major", status="Resolved",
        )

        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = review_session
        item_result = MagicMock()
        item_result.scalar_one_or_none.return_value = action_item

        session.execute.side_effect = [session_result, item_result]

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        with pytest.raises(ValueError, match="Invalid status transition"):
            await svc.update_action_item(
                session_id=1,
                item_id=10,
                status="Open",
                resolution_note=None,
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_list_action_items(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should return action items for a valid session."""
        factory, session = mock_session_factory

        review_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Completed",
            submitted_by=1,
        )
        items = [
            ActionItem(
                id=1, session_id=1, finding_id="F-001",
                title="Item 1", description="Desc 1",
                severity="Critical", status="Open",
            ),
            ActionItem(
                id=2, session_id=1, finding_id="F-002",
                title="Item 2", description="Desc 2",
                severity="Minor", status="InProgress",
            ),
        ]

        session_result = MagicMock()
        session_result.scalar_one_or_none.return_value = review_session

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = items

        session.execute.side_effect = [session_result, items_result]

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        result = await svc.list_action_items(session_id=1, company_id=1)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# get_session / list_sessions Tests
# ---------------------------------------------------------------------------


class TestSessionQueries:
    """Tests for session query operations."""

    @pytest.mark.asyncio
    async def test_get_session_found(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should return session when found."""
        factory, session = mock_session_factory

        review_session = ReviewSession(
            id=1, company_id=1, document_id=1,
            document_version_id=1, status="Completed",
            submitted_by=1,
        )
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = review_session
        session.execute.return_value = result_mock

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        result = await svc.get_session(session_id=1, company_id=1)
        assert result is not None
        assert result.id == 1

    @pytest.mark.asyncio
    async def test_get_session_not_found(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should return None when session not found."""
        factory, session = mock_session_factory

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        result = await svc.get_session(session_id=999, company_id=1)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_wrong_company(
        self, mock_session_factory, mock_agent_registry, mock_storage_service,
        mock_inference_client,
    ):
        """Should return None when session belongs to different company."""
        factory, session = mock_session_factory

        # Query with wrong company returns None
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        svc = ReviewPipelineService(
            session_factory=factory,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
            inference_client=mock_inference_client,
        )

        result = await svc.get_session(session_id=1, company_id=999)
        assert result is None
