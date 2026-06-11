"""Unit tests for SLRReviewService.

Tests SLR review creation, state machine transitions, screening initiation,
human overrides, PRISMA flow computation, inter-rater reliability metrics,
auto-completion logic, and report generation.

References:
    - Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.9
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.review.exceptions import (
    DecisionNotFoundError,
    InvalidStateTransitionError,
    ProtocolNotFoundError,
    ReviewNotFoundError,
)
from alcoabase.literature.review.services.slr_review_service import (
    SLRReviewService,
)


@pytest.fixture
def service() -> SLRReviewService:
    """Create an SLRReviewService instance."""
    return SLRReviewService()


@pytest.fixture
def mock_protocol():
    """Create a mock ScreeningProtocol ORM object."""
    protocol = MagicMock()
    protocol.id = 10
    protocol.company_id = 42
    protocol.name = "Test Protocol"
    protocol.status = "active"
    protocol.version = 1
    protocol.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return protocol


@pytest.fixture
def mock_review():
    """Create a mock SLRReview ORM object in protocol_defined state."""
    review = MagicMock()
    review.id = 1
    review.company_id = 42
    review.protocol_id = 10
    review.name = "Test Review"
    review.description = "A test review"
    review.status = "protocol_defined"
    review.record_filter = None
    review.created_by = 5
    review.completed_by = None
    review.records_identified = 100
    review.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    review.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    review.completed_at = None
    return review


@pytest.fixture
def mock_decision():
    """Create a mock ScreeningDecision ORM object."""
    decision = MagicMock()
    decision.id = 50
    decision.screening_run_id = 1
    decision.ingestion_record_id = 200
    decision.protocol_id = 10
    decision.company_id = 42
    decision.verdict = "include"
    decision.confidence = 0.85
    decision.rationale = "Matches PICO criteria."
    decision.matched_inclusion_criteria = [0, 1]
    decision.matched_exclusion_criteria = []
    decision.screening_duration_ms = 350
    decision.human_verdict = None
    decision.human_rationale = None
    decision.human_reviewer_id = None
    decision.human_override_at = None
    decision.created_at = datetime(2025, 1, 5, tzinfo=timezone.utc)
    return decision


class TestCreateReview:
    """Tests for SLRReviewService.create_review()."""

    @pytest.mark.asyncio
    async def test_raises_when_protocol_not_found(
        self, service: SLRReviewService, async_session: AsyncMock
    ):
        """Raises ProtocolNotFoundError if protocol not in company scope."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = mock_result

        with pytest.raises(ProtocolNotFoundError) as exc_info:
            await service.create_review(
                async_session,
                company_id=42,
                user_id=1,
                protocol_id=999,
                name="Review",
            )

        assert exc_info.value.protocol_id == 999
        assert exc_info.value.company_id == 42

    @pytest.mark.asyncio
    async def test_creates_review_in_protocol_defined_state(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_protocol,
    ):
        """Successfully creates review with initial state protocol_defined."""
        # First call: _get_protocol_or_raise (protocol lookup)
        protocol_result = MagicMock()
        protocol_result.scalar_one_or_none.return_value = mock_protocol

        # Second call: _resolve_record_count (count query)
        count_result = MagicMock()
        count_result.scalar_one.return_value = 50

        async_session.execute.side_effect = [protocol_result, count_result]
        async_session.refresh = AsyncMock()

        result = await service.create_review(
            async_session,
            company_id=42,
            user_id=5,
            protocol_id=10,
            name="My Review",
            description="Test description",
        )

        # Verify returned dict
        assert result is not None

        # Verify review was added to session
        async_session.add.assert_called_once()
        added_review = async_session.add.call_args[0][0]
        assert added_review.company_id == 42
        assert added_review.protocol_id == 10
        assert added_review.status == "protocol_defined"
        assert added_review.name == "My Review"
        assert added_review.records_identified == 50


class TestStateTransitions:
    """Tests for _transition_state state machine enforcement."""

    def test_valid_transition_protocol_defined_to_screening(
        self, service: SLRReviewService, mock_review
    ):
        """Valid: protocol_defined → screening_in_progress."""
        service._transition_state(mock_review, "screening_in_progress")
        assert mock_review.status == "screening_in_progress"

    def test_valid_transition_screening_to_complete(
        self, service: SLRReviewService, mock_review
    ):
        """Valid: screening_in_progress → screening_complete."""
        mock_review.status = "screening_in_progress"
        service._transition_state(mock_review, "screening_complete")
        assert mock_review.status == "screening_complete"

    def test_valid_transition_screening_complete_to_human_review(
        self, service: SLRReviewService, mock_review
    ):
        """Valid: screening_complete → human_review_in_progress."""
        mock_review.status = "screening_complete"
        service._transition_state(mock_review, "human_review_in_progress")
        assert mock_review.status == "human_review_in_progress"

    def test_valid_transition_screening_complete_to_completed(
        self, service: SLRReviewService, mock_review
    ):
        """Valid: screening_complete → completed."""
        mock_review.status = "screening_complete"
        service._transition_state(mock_review, "completed")
        assert mock_review.status == "completed"

    def test_valid_transition_human_review_to_completed(
        self, service: SLRReviewService, mock_review
    ):
        """Valid: human_review_in_progress → completed."""
        mock_review.status = "human_review_in_progress"
        service._transition_state(mock_review, "completed")
        assert mock_review.status == "completed"

    def test_invalid_transition_protocol_defined_to_completed(
        self, service: SLRReviewService, mock_review
    ):
        """Invalid: protocol_defined → completed raises error."""
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            service._transition_state(mock_review, "completed")

        assert exc_info.value.current_state == "protocol_defined"
        assert exc_info.value.target_state == "completed"

    def test_invalid_transition_screening_to_protocol_defined(
        self, service: SLRReviewService, mock_review
    ):
        """Invalid: screening_in_progress → protocol_defined raises error."""
        mock_review.status = "screening_in_progress"
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            service._transition_state(mock_review, "protocol_defined")

        assert exc_info.value.current_state == "screening_in_progress"
        assert exc_info.value.target_state == "protocol_defined"

    def test_invalid_transition_completed_to_any(
        self, service: SLRReviewService, mock_review
    ):
        """Invalid: completed → any state raises error (terminal state)."""
        mock_review.status = "completed"
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            service._transition_state(mock_review, "screening_in_progress")

        assert exc_info.value.current_state == "completed"

    def test_invalid_transition_human_review_to_screening(
        self, service: SLRReviewService, mock_review
    ):
        """Invalid: human_review_in_progress → screening_in_progress."""
        mock_review.status = "human_review_in_progress"
        with pytest.raises(InvalidStateTransitionError):
            service._transition_state(mock_review, "screening_in_progress")


class TestInitiateScreening:
    """Tests for SLRReviewService.initiate_screening()."""

    @pytest.mark.asyncio
    async def test_creates_screening_run_and_dispatches_celery(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Creates ScreeningRun and dispatches Celery task on valid initiation."""
        # _get_review_or_raise returns the review
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review
        async_session.execute.return_value = review_result
        async_session.refresh = AsyncMock()

        with patch(
            "alcoabase.tasks.literature_screening_tasks.execute_screening_batch"
        ) as mock_celery_task:
            mock_celery_task.delay = MagicMock()

            result = await service.initiate_screening(
                async_session,
                review_id=1,
                company_id=42,
                user_id=5,
                batch_size=25,
            )

        assert result["review_id"] == 1
        assert result["status"] == "queued"
        assert result["batch_size"] == 25
        assert result["total_records"] == 100
        assert "task_id" in result
        assert "screening_run_id" in result

        # Verify screening run was added to session
        async_session.add.assert_called_once()
        added_run = async_session.add.call_args[0][0]
        assert added_run.review_id == 1
        assert added_run.batch_size == 25
        assert added_run.total_records == 100

        # Verify Celery task was dispatched
        mock_celery_task.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_invalid_state_for_screening(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Raises InvalidStateTransitionError if review not in valid state."""
        mock_review.status = "completed"
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review
        async_session.execute.return_value = review_result

        with pytest.raises(InvalidStateTransitionError):
            await service.initiate_screening(
                async_session,
                review_id=1,
                company_id=42,
                user_id=5,
            )

    @pytest.mark.asyncio
    async def test_raises_when_review_not_found(
        self, service: SLRReviewService, async_session: AsyncMock
    ):
        """Raises ReviewNotFoundError if review not in company scope."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = review_result

        with pytest.raises(ReviewNotFoundError):
            await service.initiate_screening(
                async_session,
                review_id=999,
                company_id=42,
                user_id=5,
            )


class TestRecordHumanOverride:
    """Tests for SLRReviewService.record_human_override()."""

    @pytest.mark.asyncio
    async def test_stores_verdict_and_rationale(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
        mock_decision,
    ):
        """Records human_verdict and human_rationale on the decision."""
        mock_review.status = "human_review_in_progress"

        # First call: _get_review_or_raise
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        # Second call: find decision
        decision_result = MagicMock()
        decision_result.scalar_one_or_none.return_value = mock_decision

        # Third+ calls: _check_auto_completion queries
        auto_complete_total = MagicMock()
        auto_complete_total.scalar_one.return_value = 10

        auto_complete_completed = MagicMock()
        auto_complete_completed.scalar_one.return_value = 5  # Not all completed

        async_session.execute.side_effect = [
            review_result,
            decision_result,
            auto_complete_total,
            auto_complete_completed,
        ]

        result = await service.record_human_override(
            async_session,
            review_id=1,
            decision_id=50,
            company_id=42,
            user_id=7,
            human_verdict="exclude",
            human_rationale="Does not meet population criteria.",
        )

        # Verify return value is a dict
        assert result is not None

        # Verify override was recorded on the decision object
        assert mock_decision.human_verdict == "exclude"
        assert mock_decision.human_rationale == "Does not meet population criteria."
        assert mock_decision.human_reviewer_id == 7
        assert mock_decision.human_override_at is not None

    @pytest.mark.asyncio
    async def test_raises_when_decision_not_found(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Raises DecisionNotFoundError if decision not in scope."""
        mock_review.status = "human_review_in_progress"

        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        decision_result = MagicMock()
        decision_result.scalar_one_or_none.return_value = None

        async_session.execute.side_effect = [review_result, decision_result]

        with pytest.raises(DecisionNotFoundError) as exc_info:
            await service.record_human_override(
                async_session,
                review_id=1,
                decision_id=999,
                company_id=42,
                user_id=7,
                human_verdict="include",
                human_rationale="Relevant paper.",
            )

        assert exc_info.value.decision_id == 999
        assert exc_info.value.review_id == 1


class TestGetPrismaFlow:
    """Tests for SLRReviewService.get_prisma_flow()."""

    @pytest.mark.asyncio
    async def test_returns_zeros_when_no_runs(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Returns zero counts when no screening runs exist."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        # Screening runs query returns empty
        runs_result = MagicMock()
        runs_result.all.return_value = []

        async_session.execute.side_effect = [review_result, runs_result]

        result = await service.get_prisma_flow(
            async_session, review_id=1, company_id=42
        )

        assert result["review_id"] == 1
        assert result["records_identified"] == 100
        assert result["records_screened"] == 0
        assert result["records_eligible"] == 0
        assert result["records_included_final"] == 0
        assert result["records_excluded_with_reasons"] == {}

    @pytest.mark.asyncio
    async def test_computes_correct_aggregates(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Computes correct PRISMA statistics from decision data."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        # Screening runs query returns run IDs
        runs_result = MagicMock()
        runs_result.all.return_value = [(1,), (2,)]

        # Screened count
        screened_result = MagicMock()
        screened_result.scalar_one.return_value = 80

        # Eligible count
        eligible_result = MagicMock()
        eligible_result.scalar_one.return_value = 60

        # Included final
        included_result = MagicMock()
        included_result.scalar_one.return_value = 40

        # Excluded with reasons
        excluded_result = MagicMock()
        excluded_result.all.return_value = [("exclude", 20)]

        async_session.execute.side_effect = [
            review_result,
            runs_result,
            screened_result,
            eligible_result,
            included_result,
            excluded_result,
        ]

        result = await service.get_prisma_flow(
            async_session, review_id=1, company_id=42
        )

        assert result["records_identified"] == 100
        assert result["records_screened"] == 80
        assert result["records_eligible"] == 60
        assert result["records_included_final"] == 40
        assert result["records_excluded_with_reasons"] == {"exclude": 20}


class TestComputeInterRaterReliability:
    """Tests for SLRReviewService.compute_inter_rater_reliability()."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_overrides(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Returns None metrics when no human overrides exist."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = []

        async_session.execute.side_effect = [review_result, decisions_result]

        result = await service.compute_inter_rater_reliability(
            async_session, review_id=1, company_id=42
        )

        assert result["total_overrides"] == 0
        assert result["agreement_rate"] is None
        assert result["cohens_kappa"] is None

    @pytest.mark.asyncio
    async def test_perfect_agreement_kappa_one(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Computes kappa=1.0 for perfect agreement between AI and human."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        # Create decisions where AI and human always agree
        decisions = []
        for i in range(10):
            d = MagicMock()
            d.verdict = "include"
            d.human_verdict = "include"
            d.matched_inclusion_criteria = [0]
            d.matched_exclusion_criteria = []
            decisions.append(d)
        for i in range(10):
            d = MagicMock()
            d.verdict = "exclude"
            d.human_verdict = "exclude"
            d.matched_inclusion_criteria = []
            d.matched_exclusion_criteria = [0]
            decisions.append(d)

        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = decisions

        async_session.execute.side_effect = [review_result, decisions_result]

        result = await service.compute_inter_rater_reliability(
            async_session, review_id=1, company_id=42
        )

        assert result["total_overrides"] == 20
        assert result["agreement_rate"] == 1.0
        assert result["cohens_kappa"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_complete_disagreement(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """Computes negative kappa for complete disagreement."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        # AI says include, human says exclude; and vice versa
        decisions = []
        for i in range(5):
            d = MagicMock()
            d.verdict = "include"
            d.human_verdict = "exclude"
            d.matched_inclusion_criteria = [0]
            d.matched_exclusion_criteria = []
            decisions.append(d)
        for i in range(5):
            d = MagicMock()
            d.verdict = "exclude"
            d.human_verdict = "include"
            d.matched_inclusion_criteria = []
            d.matched_exclusion_criteria = [0]
            decisions.append(d)

        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = decisions

        async_session.execute.side_effect = [review_result, decisions_result]

        result = await service.compute_inter_rater_reliability(
            async_session, review_id=1, company_id=42
        )

        assert result["total_overrides"] == 10
        assert result["agreement_rate"] == 0.0
        # Kappa should be -1.0 for perfect disagreement with balanced marginals
        assert result["cohens_kappa"] == pytest.approx(-1.0)

    @pytest.mark.asyncio
    async def test_uncertain_maps_to_exclude_for_kappa(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
    ):
        """AI uncertain verdicts are treated as exclude for kappa computation."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        d = MagicMock()
        d.verdict = "uncertain"
        d.human_verdict = "exclude"
        d.matched_inclusion_criteria = []
        d.matched_exclusion_criteria = []

        decisions_result = MagicMock()
        decisions_result.scalars.return_value.all.return_value = [d]

        async_session.execute.side_effect = [review_result, decisions_result]

        result = await service.compute_inter_rater_reliability(
            async_session, review_id=1, company_id=42
        )

        # uncertain → exclude; human = exclude → agreement
        assert result["agreement_rate"] == 1.0


class TestCheckAutoCompletion:
    """Tests for SLRReviewService._check_auto_completion()."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_decisions(
        self, service: SLRReviewService, async_session: AsyncMock
    ):
        """Returns False when no decisions exist."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0

        async_session.execute.side_effect = [total_result]

        result = await service._check_auto_completion(
            async_session, review_id=1, company_id=42
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_true_when_all_resolved(
        self, service: SLRReviewService, async_session: AsyncMock
    ):
        """Returns True when all decisions meet completion criteria."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 10

        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 10

        async_session.execute.side_effect = [total_result, completed_result]

        result = await service._check_auto_completion(
            async_session, review_id=1, company_id=42
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_some_unresolved(
        self, service: SLRReviewService, async_session: AsyncMock
    ):
        """Returns False when some decisions lack resolution."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 10

        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 7  # 3 unresolved

        async_session.execute.side_effect = [total_result, completed_result]

        result = await service._check_auto_completion(
            async_session, review_id=1, company_id=42
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_custom_confidence_threshold(
        self, service: SLRReviewService, async_session: AsyncMock
    ):
        """Accepts custom confidence_threshold parameter."""
        total_result = MagicMock()
        total_result.scalar_one.return_value = 5

        completed_result = MagicMock()
        completed_result.scalar_one.return_value = 5

        async_session.execute.side_effect = [total_result, completed_result]

        result = await service._check_auto_completion(
            async_session,
            review_id=1,
            company_id=42,
            confidence_threshold=0.9,
        )

        assert result is True


class TestGenerateReport:
    """Tests for SLRReviewService.generate_report()."""

    @pytest.mark.asyncio
    async def test_includes_all_required_sections(
        self,
        service: SLRReviewService,
        async_session: AsyncMock,
        mock_review,
        mock_protocol,
    ):
        """Report includes metadata, prisma_flow, statistics, rationale, IRR."""
        mock_review.status = "completed"
        mock_review.completed_at = datetime(2025, 2, 1, tzinfo=timezone.utc)

        # _get_review_or_raise
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = mock_review

        # _get_protocol_or_raise
        protocol_result = MagicMock()
        protocol_result.scalar_one_or_none.return_value = mock_protocol

        # get_prisma_flow calls: runs query returns empty (simple case)
        prisma_review_result = MagicMock()
        prisma_review_result.scalar_one_or_none.return_value = mock_review
        prisma_runs_result = MagicMock()
        prisma_runs_result.all.return_value = []

        # get_progress calls
        progress_review_result = MagicMock()
        progress_review_result.scalar_one_or_none.return_value = mock_review
        progress_agg_result = MagicMock()
        progress_row = MagicMock()
        progress_row.total = 100
        progress_row.screened = 80
        progress_row.include_count = 40
        progress_row.exclude_count = 30
        progress_row.uncertain_count = 10
        progress_agg_result.one.return_value = progress_row

        # get_progress: avg_duration query (screened > 0 and pending > 0)
        avg_duration_result = MagicMock()
        avg_duration_result.scalar_one.return_value = 500.0

        # compute_inter_rater_reliability calls
        irr_review_result = MagicMock()
        irr_review_result.scalar_one_or_none.return_value = mock_review
        irr_decisions_result = MagicMock()
        irr_decisions_result.scalars.return_value.all.return_value = []

        # _get_rationale_summaries calls (3 verdict queries)
        rationale_include = MagicMock()
        rationale_include.all.return_value = [("Good paper.",)]
        rationale_exclude = MagicMock()
        rationale_exclude.all.return_value = [("Off topic.",)]
        rationale_uncertain = MagicMock()
        rationale_uncertain.all.return_value = []

        async_session.execute.side_effect = [
            review_result,           # generate_report: _get_review_or_raise
            protocol_result,         # generate_report: _get_protocol_or_raise
            prisma_review_result,    # get_prisma_flow: _get_review_or_raise
            prisma_runs_result,      # get_prisma_flow: runs query
            progress_review_result,  # get_progress: _get_review_or_raise
            progress_agg_result,     # get_progress: aggregate query
            avg_duration_result,     # get_progress: avg_duration query
            irr_review_result,       # compute_irr: _get_review_or_raise
            irr_decisions_result,    # compute_irr: decisions query
            rationale_include,       # _get_rationale_summaries: include
            rationale_exclude,       # _get_rationale_summaries: exclude
            rationale_uncertain,     # _get_rationale_summaries: uncertain
        ]

        result = await service.generate_report(
            async_session, review_id=1, company_id=42
        )

        # Verify all required top-level sections present
        assert "review_id" in result
        assert "metadata" in result
        assert "prisma_flow" in result
        assert "screening_statistics" in result
        assert "rationale_summaries" in result
        assert "inter_rater_reliability" in result

        # Verify metadata contents
        assert result["metadata"]["protocol_name"] == "Test Protocol"
        assert result["metadata"]["company_id"] == 42
        assert result["metadata"]["duration_days"] is not None

        # Verify screening statistics
        assert result["screening_statistics"]["total_records"] == 100
        assert result["screening_statistics"]["include_count"] == 40

    @pytest.mark.asyncio
    async def test_raises_when_review_not_found(
        self, service: SLRReviewService, async_session: AsyncMock
    ):
        """Raises ReviewNotFoundError if review does not exist."""
        review_result = MagicMock()
        review_result.scalar_one_or_none.return_value = None
        async_session.execute.return_value = review_result

        with pytest.raises(ReviewNotFoundError):
            await service.generate_report(
                async_session, review_id=999, company_id=42
            )
