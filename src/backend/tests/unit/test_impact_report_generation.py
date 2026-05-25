"""Unit tests for ImpactAnalysisService.create_impact_report.

Tests report generation, persistence, user attribution handling,
database write failure handling, and terminal state coverage.

References:
    - Requirements 5.1: Report creation for all terminal states
    - Requirements 5.2: Immutable report persistence
    - Requirements 5.3: Report fields
    - Requirements 5.4: Report retrieval
    - Requirements 5.5: Per-item AI reasoning
    - Requirements 5.7: DB write failure handling
    - Requirements 5.8: User attribution from DocumentVersion.uploaded_by
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.schemas.impact_analysis import (
    AffectedItemSchema,
    ChangeDeltaSchema,
    GapFindingSchema,
)
from alcoabase.services.impact_analysis import ImpactAnalysisService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    return session


@pytest.fixture
def mock_job_tracker() -> AsyncMock:
    """Create a mock JobTracker."""
    tracker = AsyncMock()
    tracker.fail_job = AsyncMock()
    return tracker


@pytest.fixture
def service(mock_job_tracker: AsyncMock) -> ImpactAnalysisService:
    """Create an ImpactAnalysisService with mocked dependencies."""
    return ImpactAnalysisService(
        knowledge_service=None,
        inference_client=None,
        agent_registry=None,
        session_factory=None,
        job_tracker=mock_job_tracker,
    )


@pytest.fixture
def sample_change_delta() -> ChangeDeltaSchema:
    """Create a sample ChangeDeltaSchema for testing."""
    return ChangeDeltaSchema(
        sections_added=[{"title": "New Section", "content": "New content"}],
        sections_modified=[],
        sections_deleted=[],
        significance_levels={"high": 1, "medium": 0, "low": 0},
        metadata={},
    )


@pytest.fixture
def sample_affected_items() -> list[AffectedItemSchema]:
    """Create sample affected items for testing."""
    return [
        AffectedItemSchema(
            affected_document_uuid="2024-00002",
            training_task_id=None,
            affected_document_title="SOP-001 Safety Procedures",
            dependency_type="validates",
            impact_severity="critical",
            affected_sections=["Section 3.1", "Section 3.2"],
            change_summary="Safety requirements updated in source document",
            recommended_action="update_required",
            inference_prompt_summary="Assess impact of changes...",
            model_response_summary="The dependent document contradicts...",
            token_count=512,
        ),
    ]


@pytest.fixture
def sample_gap_findings() -> list[GapFindingSchema]:
    """Create sample gap findings for testing."""
    return [
        GapFindingSchema(
            source_section="1.1 Purpose",
            source_content_excerpt="The purpose of this document is...",
            target_section="1.1 Purpose",
            target_content_excerpt="This document describes...",
            gap_type="outdated",
            severity="minor",
            remediation_suggestion="Update target section to reflect new purpose.",
            inference_prompt_summary="Compare source and target sections...",
            model_response_summary="The target uses outdated terminology...",
            token_count=256,
        ),
    ]


# ---------------------------------------------------------------------------
# Report Creation Tests
# ---------------------------------------------------------------------------


class TestCreateImpactReport:
    """Tests for create_impact_report method."""

    @pytest.mark.asyncio
    async def test_creates_report_with_all_fields(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
        sample_affected_items: list[AffectedItemSchema],
        sample_gap_findings: list[GapFindingSchema],
    ) -> None:
        """Report is created with all required fields populated."""
        report_id = await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=5,
            change_delta_summary=sample_change_delta,
            affected_items=sample_affected_items,
            gap_findings=sample_gap_findings,
            status="completed",
            analysis_timestamp=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
            analysis_duration_ms=5000,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=768,
            company_id=1,
            requesting_user_id=42,
        )

        # Verify report_id is a valid UUID string
        assert len(report_id) == 36
        assert report_id.count("-") == 4

        # Verify session.add was called with an ImpactReport
        mock_session.add.assert_called_once()
        report = mock_session.add.call_args[0][0]

        from alcoabase.models.impact_analysis import ImpactReport

        assert isinstance(report, ImpactReport)
        assert report.report_id == report_id
        assert report.triggering_document_uuid == "2024-00001"
        assert report.triggering_version_id == 5
        assert report.status == "completed"
        assert report.analysis_duration_ms == 5000
        assert report.agent_archetype_used == "Change Impact Analyst"
        assert report.model_used == "gemma-4-e4b-it"
        assert report.total_token_count == 768
        assert report.requesting_user_id == 42
        assert report.company_id == 1

        # Verify flush was called
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_report_id_is_unique_uuid(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """Each report gets a unique UUID report_id."""
        ids = set()
        for _ in range(5):
            report_id = await service.create_impact_report(
                session=mock_session,
                job_id="job-123",
                triggering_document_uuid="2024-00001",
                triggering_version_id=1,
                change_delta_summary=sample_change_delta,
                affected_items=[],
                gap_findings=[],
                status="completed",
                analysis_timestamp=datetime.now(timezone.utc),
                analysis_duration_ms=100,
                agent_archetype_used="Change Impact Analyst",
                model_used="gemma-4-e4b-it",
                total_token_count=0,
                company_id=1,
            )
            ids.add(report_id)

        assert len(ids) == 5  # All unique

    @pytest.mark.asyncio
    async def test_change_delta_serialized_correctly(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """ChangeDeltaSchema is serialized to dict for JSONB storage."""
        await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=sample_change_delta,
            affected_items=[],
            gap_findings=[],
            status="completed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=100,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=0,
            company_id=1,
        )

        report = mock_session.add.call_args[0][0]
        assert isinstance(report.change_delta_summary, dict)
        assert "sections_added" in report.change_delta_summary
        assert "significance_levels" in report.change_delta_summary

    @pytest.mark.asyncio
    async def test_affected_items_serialized_to_list(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
        sample_affected_items: list[AffectedItemSchema],
    ) -> None:
        """AffectedItemSchema list is serialized to list of dicts."""
        await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=sample_change_delta,
            affected_items=sample_affected_items,
            gap_findings=[],
            status="completed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=100,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=512,
            company_id=1,
        )

        report = mock_session.add.call_args[0][0]
        assert isinstance(report.affected_items, list)
        assert len(report.affected_items) == 1
        assert report.affected_items[0]["impact_severity"] == "critical"
        assert report.affected_items[0]["affected_document_uuid"] == "2024-00002"

    @pytest.mark.asyncio
    async def test_gap_findings_serialized_to_list(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
        sample_gap_findings: list[GapFindingSchema],
    ) -> None:
        """GapFindingSchema list is serialized to list of dicts."""
        await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=sample_change_delta,
            affected_items=[],
            gap_findings=sample_gap_findings,
            status="completed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=100,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=256,
            company_id=1,
        )

        report = mock_session.add.call_args[0][0]
        assert isinstance(report.gap_findings, list)
        assert len(report.gap_findings) == 1
        assert report.gap_findings[0]["gap_type"] == "outdated"
        assert report.gap_findings[0]["severity"] == "minor"


# ---------------------------------------------------------------------------
# Terminal State Tests (Requirement 5.1)
# ---------------------------------------------------------------------------


class TestTerminalStates:
    """Tests that reports are created for all terminal states."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["completed", "partial_success", "failed"])
    async def test_report_created_for_all_terminal_states(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
        status: str,
    ) -> None:
        """Report is created regardless of terminal status."""
        report_id = await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=sample_change_delta,
            affected_items=[],
            gap_findings=[],
            status=status,
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=100,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=0,
            company_id=1,
        )

        assert report_id is not None
        report = mock_session.add.call_args[0][0]
        assert report.status == status

    @pytest.mark.asyncio
    async def test_failed_report_has_empty_items(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
    ) -> None:
        """Failed reports have empty affected_items and gap_findings."""
        delta = ChangeDeltaSchema(
            sections_added=[],
            sections_modified=[],
            sections_deleted=[],
            significance_levels={"high": 0, "medium": 0, "low": 0},
            metadata={"error": "Inference service unavailable"},
        )

        await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=delta,
            affected_items=[],
            gap_findings=[],
            status="failed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=500,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=0,
            company_id=1,
        )

        report = mock_session.add.call_args[0][0]
        assert report.affected_items == []
        assert report.gap_findings == []
        assert report.status == "failed"


# ---------------------------------------------------------------------------
# User Attribution Tests (Requirement 5.8)
# ---------------------------------------------------------------------------


class TestUserAttribution:
    """Tests for requesting_user_id attribution handling."""

    @pytest.mark.asyncio
    async def test_requesting_user_id_set_from_uploaded_by(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """requesting_user_id is set when provided."""
        await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=sample_change_delta,
            affected_items=[],
            gap_findings=[],
            status="completed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=100,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=0,
            company_id=1,
            requesting_user_id=42,
        )

        report = mock_session.add.call_args[0][0]
        assert report.requesting_user_id == 42

    @pytest.mark.asyncio
    async def test_user_attribution_unavailable_flag(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """When user_attribution_unavailable=True, metadata flag is set."""
        await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=sample_change_delta,
            affected_items=[],
            gap_findings=[],
            status="completed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=100,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=0,
            company_id=1,
            requesting_user_id=None,
            user_attribution_unavailable=True,
        )

        report = mock_session.add.call_args[0][0]
        assert report.requesting_user_id is None
        assert report.change_delta_summary["metadata"]["user_attribution_unavailable"] is True

    @pytest.mark.asyncio
    async def test_user_attribution_available_no_flag(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """When user_attribution_unavailable=False, no flag is added."""
        await service.create_impact_report(
            session=mock_session,
            job_id="job-123",
            triggering_document_uuid="2024-00001",
            triggering_version_id=1,
            change_delta_summary=sample_change_delta,
            affected_items=[],
            gap_findings=[],
            status="completed",
            analysis_timestamp=datetime.now(timezone.utc),
            analysis_duration_ms=100,
            agent_archetype_used="Change Impact Analyst",
            model_used="gemma-4-e4b-it",
            total_token_count=0,
            company_id=1,
            requesting_user_id=42,
            user_attribution_unavailable=False,
        )

        report = mock_session.add.call_args[0][0]
        metadata = report.change_delta_summary.get("metadata", {})
        assert "user_attribution_unavailable" not in metadata

    def test_resolve_requesting_user_id_with_uploaded_by(
        self,
    ) -> None:
        """resolve_requesting_user_id returns user_id when uploaded_by is set."""
        version = MagicMock()
        version.uploaded_by = 42

        user_id, unavailable = ImpactAnalysisService.resolve_requesting_user_id(version)
        assert user_id == 42
        assert unavailable is False

    def test_resolve_requesting_user_id_without_uploaded_by(
        self,
    ) -> None:
        """resolve_requesting_user_id returns None when uploaded_by is None."""
        version = MagicMock()
        version.uploaded_by = None

        user_id, unavailable = ImpactAnalysisService.resolve_requesting_user_id(version)
        assert user_id is None
        assert unavailable is True

    def test_resolve_requesting_user_id_missing_attribute(
        self,
    ) -> None:
        """resolve_requesting_user_id handles missing uploaded_by attribute."""
        version = MagicMock(spec=[])  # No attributes

        user_id, unavailable = ImpactAnalysisService.resolve_requesting_user_id(version)
        assert user_id is None
        assert unavailable is True


# ---------------------------------------------------------------------------
# Database Write Failure Tests (Requirement 5.7)
# ---------------------------------------------------------------------------


class TestDatabaseWriteFailure:
    """Tests for database write failure handling."""

    @pytest.mark.asyncio
    async def test_db_write_failure_marks_job_failed(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        mock_job_tracker: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """On DB write failure, job is marked as failed via JobTracker."""
        mock_session.flush.side_effect = Exception("Connection refused")

        with pytest.raises(Exception, match="Connection refused"):
            await service.create_impact_report(
                session=mock_session,
                job_id="job-456",
                triggering_document_uuid="2024-00001",
                triggering_version_id=1,
                change_delta_summary=sample_change_delta,
                affected_items=[],
                gap_findings=[],
                status="completed",
                analysis_timestamp=datetime.now(timezone.utc),
                analysis_duration_ms=100,
                agent_archetype_used="Change Impact Analyst",
                model_used="gemma-4-e4b-it",
                total_token_count=0,
                company_id=1,
            )

        # Verify JobTracker.fail_job was called
        mock_job_tracker.fail_job.assert_awaited_once()
        call_args = mock_job_tracker.fail_job.call_args
        assert call_args[0][0] == mock_session
        assert call_args[0][1] == "job-456"
        assert "persistence failed" in call_args[0][2].lower()

    @pytest.mark.asyncio
    async def test_db_write_failure_without_job_tracker(
        self,
        mock_session: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """On DB write failure without JobTracker, exception still raised."""
        svc = ImpactAnalysisService(
            knowledge_service=None,
            inference_client=None,
            agent_registry=None,
            session_factory=None,
            job_tracker=None,
        )
        mock_session.flush.side_effect = Exception("DB error")

        with pytest.raises(Exception, match="DB error"):
            await svc.create_impact_report(
                session=mock_session,
                job_id="job-789",
                triggering_document_uuid="2024-00001",
                triggering_version_id=1,
                change_delta_summary=sample_change_delta,
                affected_items=[],
                gap_findings=[],
                status="completed",
                analysis_timestamp=datetime.now(timezone.utc),
                analysis_duration_ms=100,
                agent_archetype_used="Change Impact Analyst",
                model_used="gemma-4-e4b-it",
                total_token_count=0,
                company_id=1,
            )

    @pytest.mark.asyncio
    async def test_job_tracker_failure_does_not_mask_original_error(
        self,
        service: ImpactAnalysisService,
        mock_session: AsyncMock,
        mock_job_tracker: AsyncMock,
        sample_change_delta: ChangeDeltaSchema,
    ) -> None:
        """If JobTracker also fails, original DB error is still raised."""
        mock_session.flush.side_effect = Exception("DB write failed")
        mock_job_tracker.fail_job.side_effect = Exception("Tracker also down")

        with pytest.raises(Exception, match="DB write failed"):
            await service.create_impact_report(
                session=mock_session,
                job_id="job-999",
                triggering_document_uuid="2024-00001",
                triggering_version_id=1,
                change_delta_summary=sample_change_delta,
                affected_items=[],
                gap_findings=[],
                status="completed",
                analysis_timestamp=datetime.now(timezone.utc),
                analysis_duration_ms=100,
                agent_archetype_used="Change Impact Analyst",
                model_used="gemma-4-e4b-it",
                total_token_count=0,
                company_id=1,
            )
