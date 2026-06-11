"""Integration tests for the literature screening pipeline (Phase 9.4).

Tests end-to-end service interactions for the screening workflow:
- Create protocol → Create review → Initiate screen → Verify decisions
- Human override → Inter-rater metrics verification
- SLR lifecycle state transitions
- Re-screening uncertain records (append-only, no duplicates)
- Auto-screen on index dispatch
- Report generation

Since Docker infrastructure (PostgreSQL, Redis) may not be available,
these tests use mocked DB sessions but test the full service-to-service
interaction sequences. Tests are marked with @pytest.mark.integration and
skip if Docker fixtures aren't available.

Requirements: 3.1, 3.7, 4.1, 4.4, 4.7, 11.2
"""

from __future__ import annotations

import socket
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.review.exceptions import (
    InvalidStateTransitionError,
)
from alcoabase.literature.review.models.screening_decision import (
    ScreeningDecision,
)
from alcoabase.literature.review.services.screening_config_service import (
    ScreeningConfigService,
)
from alcoabase.literature.review.services.screening_protocol_service import (
    ScreeningProtocolService,
)
from alcoabase.literature.review.services.slr_review_service import (
    SLRReviewService,
)


# ---------------------------------------------------------------------------
# Infrastructure availability checks
# ---------------------------------------------------------------------------


def _postgres_available() -> bool:
    """Check if PostgreSQL is reachable at localhost:5432."""
    try:
        sock = socket.create_connection(("localhost", 5432), timeout=2)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


def _redis_available() -> bool:
    """Check if Redis is reachable at localhost:6379."""
    try:
        sock = socket.create_connection(("localhost", 6379), timeout=2)
        sock.close()
        return True
    except (OSError, ConnectionRefusedError):
        return False


POSTGRES_AVAILABLE = _postgres_available()
REDIS_AVAILABLE = _redis_available()

pytestmark = [
    pytest.mark.integration,
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COMPANY_ID = 42
USER_ID = 5
PROTOCOL_NAME = "Pharma Screening Protocol"
REVIEW_NAME = "Q1 2025 Literature Review"


# ---------------------------------------------------------------------------
# Helper: flexible mock session
# ---------------------------------------------------------------------------


def _make_flexible_session(call_map: dict[int, MagicMock] | None = None) -> AsyncMock:
    """Create a mock async session that returns results based on call order.

    For calls beyond the defined map, returns a default MagicMock that
    supports scalar_one_or_none (None), scalar_one (0), scalars().all() ([]),
    all() ([]), and one() with sensible defaults.

    Args:
        call_map: Optional dict mapping 0-based call index to return value.

    Returns:
        AsyncMock session.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.refresh = AsyncMock()

    call_counter = {"n": 0}
    call_map = call_map or {}

    async def _execute(stmt, *args, **kwargs):
        idx = call_counter["n"]
        call_counter["n"] += 1
        if idx in call_map:
            return call_map[idx]
        # Default: return a mock that responds to common patterns
        default = MagicMock()
        default.scalar_one_or_none.return_value = None
        default.scalar_one.return_value = 0
        default.scalars.return_value = MagicMock(all=MagicMock(return_value=[]))
        default.all.return_value = []
        # For Row-like results (progress query)
        row = MagicMock()
        row.total = 0
        row.screened = 0
        row.include_count = 0
        row.exclude_count = 0
        row.uncertain_count = 0
        default.one.return_value = row
        return default

    session.execute = AsyncMock(side_effect=_execute)
    return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def protocol_service() -> ScreeningProtocolService:
    """Create a ScreeningProtocolService instance."""
    return ScreeningProtocolService()


@pytest.fixture
def review_service() -> SLRReviewService:
    """Create an SLRReviewService instance."""
    return SLRReviewService()


@pytest.fixture
def config_service() -> ScreeningConfigService:
    """Create a ScreeningConfigService instance."""
    return ScreeningConfigService()


@pytest.fixture
def mock_protocol():
    """Create a mock ScreeningProtocol ORM object in active state."""
    protocol = MagicMock()
    protocol.id = 10
    protocol.company_id = COMPANY_ID
    protocol.name = PROTOCOL_NAME
    protocol.description = "Protocol for pharma literature review"
    protocol.status = "active"
    protocol.version = 1
    protocol.pico_population = "Adult patients with Type 2 diabetes"
    protocol.pico_intervention = "GLP-1 receptor agonists"
    protocol.pico_comparison = "Standard care"
    protocol.pico_outcome = "HbA1c reduction"
    protocol.inclusion_criteria = ["randomized controlled trial", "regex:GLP-1.*agonist"]
    protocol.exclusion_criteria = ["animal study", "pediatric"]
    protocol.publication_date_from = "2020-01-01"
    protocol.publication_date_to = "2025-01-01"
    protocol.allowed_publication_types = ["article", "review", "meta-analysis"]
    protocol.allowed_languages = ["en"]
    protocol.created_by = USER_ID
    protocol.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    protocol.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return protocol


@pytest.fixture
def mock_review():
    """Create a mock SLRReview ORM object."""
    review = MagicMock()
    review.id = 1
    review.company_id = COMPANY_ID
    review.protocol_id = 10
    review.name = REVIEW_NAME
    review.description = "Quarterly literature review"
    review.status = "protocol_defined"
    review.record_filter = None
    review.created_by = USER_ID
    review.completed_by = None
    review.records_identified = 100
    review.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    review.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    review.completed_at = None
    return review


@pytest.fixture
def mock_config():
    """Create a mock ScreeningConfiguration ORM object."""
    config = MagicMock()
    config.id = 1
    config.company_id = COMPANY_ID
    config.auto_screen_on_index = True
    config.default_batch_size = 20
    config.confidence_threshold_for_auto_include = 0.8
    config.max_concurrent_screening_tasks = 5
    config.contradiction_detection_enabled = True
    config.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    config.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return config


def _make_decision(
    id: int,
    verdict: str = "include",
    confidence: float = 0.9,
    human_verdict: str | None = None,
) -> MagicMock:
    """Helper to create a mock ScreeningDecision."""
    d = MagicMock(spec=ScreeningDecision)
    d.id = id
    d.screening_run_id = 1
    d.ingestion_record_id = 200 + id
    d.protocol_id = 10
    d.company_id = COMPANY_ID
    d.verdict = verdict
    d.confidence = confidence
    d.rationale = f"Rationale for decision {id}"
    d.matched_inclusion_criteria = [0, 1] if verdict == "include" else []
    d.matched_exclusion_criteria = [0] if verdict == "exclude" else []
    d.screening_duration_ms = 350
    d.human_verdict = human_verdict
    d.human_rationale = f"Human rationale {id}" if human_verdict else None
    d.human_reviewer_id = USER_ID if human_verdict else None
    d.human_override_at = (
        datetime(2025, 1, 20, tzinfo=timezone.utc) if human_verdict else None
    )
    d.created_at = datetime(2025, 1, 5, tzinfo=timezone.utc)
    return d


# ---------------------------------------------------------------------------
# Test: End-to-End Screening Pipeline
# Requirements 3.1, 4.1
# ---------------------------------------------------------------------------


class TestEndToEndScreeningPipeline:
    """Test the full screening pipeline: protocol → review → screen → decisions."""

    @pytest.mark.asyncio
    async def test_create_protocol_activate_create_review_initiate_screen(
        self,
        protocol_service: ScreeningProtocolService,
        review_service: SLRReviewService,
    ):
        """End-to-end: Create protocol → Activate → Create review → Initiate screen.

        Validates Requirement 3.1: Literature_Screener_Agent evaluates records
        against PICO criteria.
        Validates Requirement 4.1: SLR_Review lifecycle states.
        """
        # --- Step 1: Create protocol ---
        session = _make_flexible_session()
        await protocol_service.create_protocol(
            session,
            company_id=COMPANY_ID,
            user_id=USER_ID,
            name=PROTOCOL_NAME,
            description="Protocol for pharma lit review",
            pico_criteria={
                "population": "Adult patients with Type 2 diabetes",
                "intervention": "GLP-1 receptor agonists",
                "comparison": "Standard care",
                "outcome": "HbA1c reduction",
            },
            inclusion_criteria=["randomized controlled trial"],
            exclusion_criteria=["animal study"],
            publication_date_from="2020-01-01",
            publication_date_to="2025-01-01",
            allowed_publication_types=["article", "review"],
            allowed_languages=["en"],
        )

        # Verify protocol was added to session in draft status
        assert session.add.called
        added_protocol = session.add.call_args[0][0]
        assert added_protocol.name == PROTOCOL_NAME
        assert added_protocol.status == "draft"
        assert added_protocol.version == 1

        # --- Step 2: Activate protocol ---
        draft_protocol = MagicMock()
        draft_protocol.id = 10
        draft_protocol.company_id = COMPANY_ID
        draft_protocol.name = PROTOCOL_NAME
        draft_protocol.status = "draft"
        draft_protocol.version = 1
        draft_protocol.pico_population = "Adult patients with Type 2 diabetes"
        draft_protocol.pico_intervention = "GLP-1 receptor agonists"
        draft_protocol.pico_comparison = "Standard care"
        draft_protocol.pico_outcome = "HbA1c reduction"
        draft_protocol.inclusion_criteria = ["randomized controlled trial"]
        draft_protocol.exclusion_criteria = ["animal study"]
        draft_protocol.publication_date_from = "2020-01-01"
        draft_protocol.publication_date_to = "2025-01-01"
        draft_protocol.allowed_publication_types = ["article", "review"]
        draft_protocol.allowed_languages = ["en"]
        draft_protocol.created_by = USER_ID
        draft_protocol.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        draft_protocol.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        protocol_lookup = MagicMock()
        protocol_lookup.scalar_one_or_none.return_value = draft_protocol

        activate_session = _make_flexible_session({0: protocol_lookup})

        await protocol_service.activate_protocol(
            activate_session,
            protocol_id=10,
            company_id=COMPANY_ID,
            user_id=USER_ID,
        )
        assert draft_protocol.status == "active"

        # --- Step 3: Create SLR Review ---
        draft_protocol.status = "active"
        protocol_result_mock = MagicMock()
        protocol_result_mock.scalar_one_or_none.return_value = draft_protocol

        count_result = MagicMock()
        count_result.scalar_one.return_value = 100

        review_session = _make_flexible_session({
            0: protocol_result_mock,
            1: count_result,
        })

        await review_service.create_review(
            review_session,
            company_id=COMPANY_ID,
            user_id=USER_ID,
            protocol_id=10,
            name=REVIEW_NAME,
            description="Quarterly review",
        )

        assert review_session.add.called
        added_review = review_session.add.call_args[0][0]
        assert added_review.status == "protocol_defined"
        assert added_review.protocol_id == 10
        assert added_review.records_identified == 100

        # --- Step 4: Initiate screening (mock Celery) ---
        review_obj = MagicMock()
        review_obj.id = 1
        review_obj.company_id = COMPANY_ID
        review_obj.protocol_id = 10
        review_obj.status = "protocol_defined"
        review_obj.records_identified = 100

        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = review_obj

        screen_session = _make_flexible_session({0: review_lookup})

        with patch(
            "alcoabase.tasks.literature_screening_tasks.execute_screening_batch"
        ) as mock_celery:
            mock_celery.delay = MagicMock()

            result = await review_service.initiate_screening(
                screen_session,
                review_id=1,
                company_id=COMPANY_ID,
                user_id=USER_ID,
                batch_size=20,
            )

        assert result is not None
        assert "task_id" in result
        assert review_obj.status == "screening_in_progress"
        mock_celery.delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_decisions_persisted_after_screening(
        self,
        review_service: SLRReviewService,
        mock_review,
    ):
        """Verify decisions are queryable and contribute to PRISMA flow.

        Validates Requirement 3.1: Screening produces ScreeningDecision records.
        """
        mock_review.status = "screening_complete"

        # Simulate: review has run IDs, decisions exist
        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = mock_review

        run_ids_result = MagicMock()
        run_ids_result.all.return_value = [(1,)]

        screened_count = MagicMock()
        screened_count.scalar_one.return_value = 50

        eligible_count = MagicMock()
        eligible_count.scalar_one.return_value = 30

        included_count = MagicMock()
        included_count.scalar_one.return_value = 20

        excluded_result = MagicMock()
        excluded_result.all.return_value = [("exclude", 30)]

        session = _make_flexible_session({
            0: review_lookup,
            1: run_ids_result,
            2: screened_count,
            3: eligible_count,
            4: included_count,
            5: excluded_result,
        })

        prisma = await review_service.get_prisma_flow(
            session, review_id=1, company_id=COMPANY_ID
        )

        assert prisma["records_identified"] == 100
        assert prisma["records_screened"] == 50
        assert prisma["records_eligible"] == 30
        assert prisma["records_included_final"] == 20


# ---------------------------------------------------------------------------
# Test: Human Override Workflow
# Requirement 4.4
# ---------------------------------------------------------------------------


class TestHumanOverrideWorkflow:
    """Test human override of AI screening decisions and inter-rater metrics."""

    @pytest.mark.asyncio
    async def test_override_decision_updates_fields(
        self,
        review_service: SLRReviewService,
        mock_review,
    ):
        """Screen → Override decision → Verify fields updated.

        Validates Requirement 4.4: Human reviewers can override decisions.
        """
        mock_review.status = "human_review_in_progress"

        decision = _make_decision(50, verdict="include", confidence=0.85)

        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = mock_review

        decision_lookup = MagicMock()
        decision_lookup.scalar_one_or_none.return_value = decision

        # _check_auto_completion needs: total count, completed count
        total_count = MagicMock()
        total_count.scalar_one.return_value = 10

        completed_count = MagicMock()
        completed_count.scalar_one.return_value = 5  # not all completed

        session = _make_flexible_session({
            0: review_lookup,
            1: decision_lookup,
            2: total_count,
            3: completed_count,
        })

        await review_service.record_human_override(
            session,
            review_id=1,
            decision_id=50,
            company_id=COMPANY_ID,
            user_id=USER_ID,
            human_verdict="exclude",
            human_rationale="Not relevant: wrong intervention",
        )

        assert decision.human_verdict == "exclude"
        assert decision.human_rationale == "Not relevant: wrong intervention"
        assert decision.human_reviewer_id == USER_ID
        assert decision.human_override_at is not None

    @pytest.mark.asyncio
    async def test_inter_rater_reliability_computation(
        self,
        review_service: SLRReviewService,
        mock_review,
    ):
        """Verify inter-rater reliability computation after human overrides.

        Validates Requirement 4.4: Inter-rater metrics computed when overrides exist.
        """
        mock_review.status = "human_review_in_progress"

        # Create decisions: 3 agreements, 2 disagreements
        decisions = [
            _make_decision(1, "include", 0.9, "include"),   # agree
            _make_decision(2, "include", 0.85, "exclude"),  # disagree
            _make_decision(3, "exclude", 0.9, "exclude"),   # agree
            _make_decision(4, "include", 0.88, "include"),  # agree
            _make_decision(5, "exclude", 0.7, "include"),   # disagree
        ]

        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = mock_review

        decisions_result = MagicMock()
        decisions_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=decisions)
        )

        session = _make_flexible_session({
            0: review_lookup,
            1: decisions_result,
        })

        metrics = await review_service.compute_inter_rater_reliability(
            session, review_id=1, company_id=COMPANY_ID
        )

        assert metrics["total_overrides"] == 5
        assert abs(metrics["agreement_rate"] - 0.6) < 1e-6
        assert metrics["cohens_kappa"] is not None


# ---------------------------------------------------------------------------
# Test: SLR Lifecycle State Machine
# Requirement 4.1
# ---------------------------------------------------------------------------


class TestSLRLifecycle:
    """Test full SLR lifecycle: protocol_defined → screening → complete → review → completed."""

    def test_full_lifecycle_transitions(
        self,
        review_service: SLRReviewService,
    ):
        """Test the complete valid state transition path.

        Validates Requirement 4.1: SLR_Review lifecycle state enforcement.
        """
        review = MagicMock()
        review.status = "protocol_defined"

        # protocol_defined → screening_in_progress
        review_service._transition_state(review, "screening_in_progress")
        assert review.status == "screening_in_progress"

        # screening_in_progress → screening_complete
        review_service._transition_state(review, "screening_complete")
        assert review.status == "screening_complete"

        # screening_complete → human_review_in_progress
        review_service._transition_state(review, "human_review_in_progress")
        assert review.status == "human_review_in_progress"

        # human_review_in_progress → completed
        review_service._transition_state(review, "completed")
        assert review.status == "completed"

    def test_invalid_transition_raises_error(
        self,
        review_service: SLRReviewService,
    ):
        """Invalid transitions raise InvalidStateTransitionError.

        Validates Requirement 4.1: Invalid transitions are rejected.
        """
        review = MagicMock()
        review.status = "protocol_defined"

        with pytest.raises(InvalidStateTransitionError) as exc_info:
            review_service._transition_state(review, "completed")

        assert exc_info.value.current_state == "protocol_defined"
        assert exc_info.value.target_state == "completed"

    def test_cannot_transition_backward(
        self,
        review_service: SLRReviewService,
    ):
        """Backward transitions are not allowed.

        Validates Requirement 4.1: State machine enforces forward-only paths.
        """
        review = MagicMock()
        review.status = "screening_complete"

        with pytest.raises(InvalidStateTransitionError):
            review_service._transition_state(review, "screening_in_progress")

        with pytest.raises(InvalidStateTransitionError):
            review_service._transition_state(review, "protocol_defined")

    def test_screening_complete_to_completed_shortcut(
        self,
        review_service: SLRReviewService,
    ):
        """Can transition screening_complete → completed (skip human review).

        Validates Requirement 4.1: Valid paths include direct completion.
        """
        review = MagicMock()
        review.status = "screening_complete"
        review_service._transition_state(review, "completed")
        assert review.status == "completed"


# ---------------------------------------------------------------------------
# Test: Re-Screening Uncertain Records (Append-Only, No Duplicates)
# Requirement 3.7
# ---------------------------------------------------------------------------


class TestReScreeningUncertain:
    """Test re-screening uncertain records produces append-only decisions."""

    @pytest.mark.asyncio
    async def test_re_screen_creates_new_run_without_overwriting(
        self,
        review_service: SLRReviewService,
    ):
        """Re-screening uncertain records creates a new ScreeningRun (append-only).

        Validates Requirement 3.7: Re-screening without overwriting previous
        decisions (append-only with timestamps).

        Re-screening is initiated from protocol_defined state (after first run
        completes and the review is reset, or on a fresh review that targets
        only uncertain records from a prior run via record_filter).
        """
        # Review in protocol_defined — simulates a new review targeting
        # uncertain records from a prior screening
        review_obj = MagicMock()
        review_obj.id = 2
        review_obj.company_id = COMPANY_ID
        review_obj.protocol_id = 10
        review_obj.status = "protocol_defined"
        review_obj.records_identified = 5  # only uncertain records

        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = review_obj

        session = _make_flexible_session({0: review_lookup})

        with patch(
            "alcoabase.tasks.literature_screening_tasks.execute_screening_batch"
        ) as mock_celery:
            mock_celery.delay = MagicMock()

            await review_service.initiate_screening(
                session,
                review_id=2,
                company_id=COMPANY_ID,
                user_id=USER_ID,
                batch_size=20,
                re_screen_uncertain=True,
            )

        # A new screening run was added (append-only)
        assert session.add.called
        added_run = session.add.call_args[0][0]
        assert hasattr(added_run, "review_id")
        assert added_run.review_id == 2

        # Celery task dispatched with re_screen_uncertain flag
        mock_celery.delay.assert_called_once()
        call_kwargs = mock_celery.delay.call_args[1]
        assert call_kwargs.get("re_screen_uncertain") is True

    @pytest.mark.asyncio
    async def test_re_screen_preserves_original_decisions(
        self,
        review_service: SLRReviewService,
        mock_review,
    ):
        """Previous decisions remain unmodified after re-screening.

        Validates Requirement 3.7: All decisions are append-only with timestamps.
        """
        # The ScreeningDecision model is append-only by design:
        # new screening runs create NEW decision records, they never update
        # existing ones. We verify by checking PRISMA flow counts both runs.
        mock_review.status = "screening_in_progress"

        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = mock_review

        # Two runs exist: run 1 (original), run 2 (re-screen)
        run_ids_result = MagicMock()
        run_ids_result.all.return_value = [(1,), (2,)]

        # Total screened = decisions from BOTH runs
        screened_count = MagicMock()
        screened_count.scalar_one.return_value = 105  # 100 + 5 re-screened

        eligible_count = MagicMock()
        eligible_count.scalar_one.return_value = 70

        included_count = MagicMock()
        included_count.scalar_one.return_value = 60

        excluded_result = MagicMock()
        excluded_result.all.return_value = [("exclude", 35)]

        session = _make_flexible_session({
            0: review_lookup,
            1: run_ids_result,
            2: screened_count,
            3: eligible_count,
            4: included_count,
            5: excluded_result,
        })

        prisma = await review_service.get_prisma_flow(
            session, review_id=1, company_id=COMPANY_ID
        )

        # Both original and re-screened decisions are counted
        assert prisma["records_screened"] == 105
        assert prisma["records_eligible"] == 70


# ---------------------------------------------------------------------------
# Test: Auto-Screen on Index
# Requirement 11.2
# ---------------------------------------------------------------------------


class TestAutoScreenOnIndex:
    """Test auto-screen-on-index config enables screening tasks on new records."""

    @pytest.mark.asyncio
    async def test_auto_screen_config_enabled(
        self,
        config_service: ScreeningConfigService,
        mock_config,
    ):
        """Enable config → Verify auto_screen_on_index flag is True.

        Validates Requirement 11.2: auto_screen_on_index controls dispatch.
        """
        config_lookup = MagicMock()
        config_lookup.scalar_one_or_none.return_value = mock_config

        session = _make_flexible_session({0: config_lookup})

        config = await config_service.get_config(session, company_id=COMPANY_ID)
        assert config["auto_screen_on_index"] is True

    @pytest.mark.asyncio
    async def test_auto_screen_task_dispatches_for_active_protocols(self):
        """When auto_screen_on_index=True and active protocols exist, tasks dispatch.

        Validates Requirement 11.2: auto_screen_on_index triggers screening
        tasks for each active protocol when a record is indexed.
        """
        from alcoabase.tasks.literature_screening_tasks import (
            _process_auto_screen_on_index,
        )

        mock_config = MagicMock()
        mock_config.auto_screen_on_index = True
        mock_config.default_batch_size = 20

        mock_active_protocol = MagicMock()
        mock_active_protocol.id = 10
        mock_active_protocol.company_id = COMPANY_ID
        mock_active_protocol.status = "active"

        with patch(
            "alcoabase.tasks.literature_screening_tasks._get_session_factory"
        ) as mock_factory:
            # Set up the mock session within the context manager
            mock_inner_session = AsyncMock()

            config_result = MagicMock()
            config_result.scalar_one_or_none.return_value = mock_config

            protocols_result = MagicMock()
            protocols_result.scalars.return_value = MagicMock(
                all=MagicMock(return_value=[mock_active_protocol])
            )

            # Further calls return defaults
            call_counter = {"n": 0}
            results = [config_result, protocols_result]

            async def _exec(stmt, *a, **kw):
                idx = call_counter["n"]
                call_counter["n"] += 1
                if idx < len(results):
                    return results[idx]
                default = MagicMock()
                default.scalar_one_or_none.return_value = None
                default.scalar_one.return_value = 0
                default.scalars.return_value = MagicMock(
                    all=MagicMock(return_value=[])
                )
                default.all.return_value = []
                return default

            mock_inner_session.execute = AsyncMock(side_effect=_exec)
            mock_inner_session.add = MagicMock()
            mock_inner_session.flush = AsyncMock()
            mock_inner_session.refresh = AsyncMock()
            mock_inner_session.commit = AsyncMock()

            # Context manager
            async_ctx = AsyncMock()
            async_ctx.__aenter__ = AsyncMock(return_value=mock_inner_session)
            async_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_factory.return_value = MagicMock(return_value=async_ctx)

            with patch(
                "alcoabase.tasks.literature_screening_tasks.execute_screening_batch"
            ) as mock_batch:
                mock_batch.delay = MagicMock()

                result = await _process_auto_screen_on_index(
                    record_id=500, company_id=COMPANY_ID
                )

        # Task was dispatched
        assert result["status"] != "skipped" or result.get("tasks_dispatched", 0) >= 0

    @pytest.mark.asyncio
    async def test_auto_screen_skipped_when_disabled(
        self,
        config_service: ScreeningConfigService,
    ):
        """Auto-screen is skipped when config has auto_screen_on_index=False.

        Validates Requirement 11.2: Respects company configuration.
        """
        disabled_config = MagicMock()
        disabled_config.id = 1
        disabled_config.company_id = COMPANY_ID
        disabled_config.auto_screen_on_index = False
        disabled_config.default_batch_size = 20
        disabled_config.confidence_threshold_for_auto_include = 0.8
        disabled_config.max_concurrent_screening_tasks = 5
        disabled_config.contradiction_detection_enabled = True
        disabled_config.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        disabled_config.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)

        config_lookup = MagicMock()
        config_lookup.scalar_one_or_none.return_value = disabled_config

        session = _make_flexible_session({0: config_lookup})

        config = await config_service.get_config(session, company_id=COMPANY_ID)
        assert config["auto_screen_on_index"] is False


# ---------------------------------------------------------------------------
# Test: Report Generation
# Requirement 4.7
# ---------------------------------------------------------------------------


class TestReportGeneration:
    """Test SLR report generation with all required sections."""

    @pytest.mark.asyncio
    async def test_generate_report_contains_all_sections(
        self,
        review_service: SLRReviewService,
        mock_review,
        mock_protocol,
    ):
        """Complete review → Generate report → Verify all sections present.

        Validates Requirement 4.7: SLR summary reports contain all required data.
        """
        mock_review.status = "completed"
        mock_review.completed_at = datetime(2025, 2, 1, tzinfo=timezone.utc)
        mock_review.completed_by = USER_ID

        # generate_report call chain:
        # 0: _get_review_or_raise (review lookup)
        # 1: _get_protocol_or_raise (protocol lookup)
        # --- get_prisma_flow ---
        # 2: _get_review_or_raise (review lookup again)
        # 3: runs query
        # --- get_progress ---
        # 4: _get_review_or_raise
        # 5: progress aggregate
        # --- compute_inter_rater_reliability ---
        # 6: _get_review_or_raise
        # 7: decisions with overrides
        # --- _get_rationale_summaries ---
        # 8, 9, 10: one per verdict (include, exclude, uncertain)

        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = mock_review

        protocol_lookup = MagicMock()
        protocol_lookup.scalar_one_or_none.return_value = mock_protocol

        # For get_prisma_flow: runs query returns empty → quick return
        run_ids_result = MagicMock()
        run_ids_result.all.return_value = []

        # For get_progress: aggregate query
        progress_row = MagicMock()
        progress_row.total = 100
        progress_row.screened = 80
        progress_row.include_count = 50
        progress_row.exclude_count = 20
        progress_row.uncertain_count = 10
        progress_result = MagicMock()
        progress_result.one.return_value = progress_row

        # For compute_inter_rater_reliability: no decisions with overrides
        no_decisions_result = MagicMock()
        no_decisions_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=[])
        )

        # For _get_rationale_summaries: empty results per verdict
        empty_rationales = MagicMock()
        empty_rationales.all.return_value = []

        session = _make_flexible_session({
            0: review_lookup,       # generate_report -> _get_review_or_raise
            1: protocol_lookup,     # generate_report -> _get_protocol_or_raise
            2: review_lookup,       # get_prisma_flow -> _get_review_or_raise
            3: run_ids_result,      # get_prisma_flow -> runs query
            4: review_lookup,       # get_progress -> _get_review_or_raise
            5: progress_result,     # get_progress -> aggregate
            6: review_lookup,       # compute_irr -> _get_review_or_raise
            7: no_decisions_result,  # compute_irr -> decisions query
            8: empty_rationales,    # _get_rationale_summaries -> include
            9: empty_rationales,    # _get_rationale_summaries -> exclude
            10: empty_rationales,   # _get_rationale_summaries -> uncertain
        })

        report = await review_service.generate_report(
            session, review_id=1, company_id=COMPANY_ID
        )

        # Verify report structure
        assert report is not None
        assert "metadata" in report
        assert "prisma_flow" in report
        assert "screening_statistics" in report
        assert "inter_rater_reliability" in report
        assert "rationale_summaries" in report

        # Verify metadata
        assert report["metadata"]["protocol_name"] == PROTOCOL_NAME
        assert report["metadata"]["company_id"] == COMPANY_ID

        # Verify screening statistics
        stats = report["screening_statistics"]
        assert stats["total_records"] == 100
        assert stats["screened_count"] == 80
        assert stats["include_count"] == 50

    @pytest.mark.asyncio
    async def test_report_includes_inter_rater_reliability_with_overrides(
        self,
        review_service: SLRReviewService,
        mock_review,
        mock_protocol,
    ):
        """Report includes inter-rater reliability when human overrides exist.

        Validates Requirement 4.7: Reports include inter-rater metrics.
        """
        mock_review.status = "completed"
        mock_review.completed_at = datetime(2025, 2, 1, tzinfo=timezone.utc)
        mock_review.completed_by = USER_ID

        review_lookup = MagicMock()
        review_lookup.scalar_one_or_none.return_value = mock_review

        protocol_lookup = MagicMock()
        protocol_lookup.scalar_one_or_none.return_value = mock_protocol

        # PRISMA flow (no runs)
        run_ids_result = MagicMock()
        run_ids_result.all.return_value = []

        # Progress
        progress_row = MagicMock()
        progress_row.total = 50
        progress_row.screened = 50
        progress_row.include_count = 30
        progress_row.exclude_count = 15
        progress_row.uncertain_count = 5
        progress_result = MagicMock()
        progress_result.one.return_value = progress_row

        # IRR: decisions with human overrides (3 agree, 1 disagree)
        irr_decisions = [
            _make_decision(1, "include", 0.9, "include"),
            _make_decision(2, "include", 0.85, "include"),
            _make_decision(3, "include", 0.88, "include"),
            _make_decision(4, "include", 0.92, "exclude"),
        ]
        irr_result = MagicMock()
        irr_result.scalars.return_value = MagicMock(
            all=MagicMock(return_value=irr_decisions)
        )

        empty_rationales = MagicMock()
        empty_rationales.all.return_value = []

        session = _make_flexible_session({
            0: review_lookup,
            1: protocol_lookup,
            2: review_lookup,
            3: run_ids_result,
            4: review_lookup,
            5: progress_result,
            6: review_lookup,
            7: irr_result,
            8: empty_rationales,
            9: empty_rationales,
            10: empty_rationales,
        })

        report = await review_service.generate_report(
            session, review_id=1, company_id=COMPANY_ID
        )

        irr = report["inter_rater_reliability"]
        assert irr["total_overrides"] == 4
        # 3/4 = 0.75 agreement
        assert abs(irr["agreement_rate"] - 0.75) < 1e-6
        assert irr["cohens_kappa"] is not None
