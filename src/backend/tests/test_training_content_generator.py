"""Unit tests for Training Content Generator service.

Tests cover:
- Training content generation pipeline
- Comprehension quiz generation
- Procedural steps and safety points extraction
- Coordinator review gate (approve/reject)
- Audit trail recording

References:
    - Task 16.8: Unit tests for training content generation pipeline and review gate
"""

import pytest

from alcoabase.services.training_content_generator import (
    ContentStatus,
    TrainingContent,
    TrainingContentGenerator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def generator() -> TrainingContentGenerator:
    """Create a TrainingContentGenerator instance."""
    return TrainingContentGenerator()


@pytest.fixture
def sample_sop_text() -> str:
    """Sample SOP text for testing."""
    return """
# SOP: Equipment Cleaning Procedure

## 1. Purpose
This SOP defines the standard procedure for cleaning laboratory equipment.

## 2. Scope
Applies to all laboratory equipment in Building A, Rooms 101-110.

## 3. Responsibilities
- Lab Technicians: Perform daily cleaning
- Lab Supervisor: Verify cleaning completion
- QA: Audit cleaning records monthly

## 4. Procedure
1. Gather all required cleaning materials
2. Don appropriate PPE (gloves, lab coat, safety glasses)
3. Disconnect equipment from power sources
4. Clean all surfaces with approved cleaning solution
5. Allow to air dry for minimum 15 minutes
6. Document cleaning in the equipment log

## 5. Safety Precautions
- Always wear PPE before handling cleaning chemicals
- Ensure adequate ventilation in the work area
- Report any spills immediately to the supervisor
- Do not use damaged or expired cleaning solutions

## 6. References
- ISO 14644-1: Cleanroom standards
- Company Policy QP-001: Equipment Maintenance
"""


@pytest.fixture
async def generated_content(
    generator: TrainingContentGenerator, sample_sop_text: str
) -> TrainingContent:
    """Generate training content for testing."""
    return await generator.generate_training_content(
        sop_document_uuid="2024-00001",
        sop_version="2.0",
        sop_text=sample_sop_text,
        user_id=1,
    )


# ---------------------------------------------------------------------------
# Generation Pipeline Tests (Task 16.1)
# ---------------------------------------------------------------------------


class TestGenerationPipeline:
    """Tests for the training content generation pipeline."""

    @pytest.mark.asyncio
    async def test_generate_returns_training_content(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Generation returns a TrainingContent instance."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
            user_id=1,
        )

        assert isinstance(content, TrainingContent)
        assert content.sop_document_uuid == "2024-00001"
        assert content.sop_version == "1.0"
        assert content.content_id is not None

    @pytest.mark.asyncio
    async def test_generate_produces_summary(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Generation produces a non-empty training summary."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        assert content.summary is not None
        assert len(content.summary) > 0

    @pytest.mark.asyncio
    async def test_generate_with_previous_version(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Generation with previous version text produces diff-aware summary."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="2.0",
            sop_text=sample_sop_text,
            previous_version_text="Previous version content here.",
        )

        assert "Changes" in content.summary or "updated" in content.summary.lower()

    @pytest.mark.asyncio
    async def test_generated_content_starts_pending_review(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Generated content starts in PENDING_REVIEW status."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        assert content.status == ContentStatus.PENDING_REVIEW

    @pytest.mark.asyncio
    async def test_content_stored_and_retrievable(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Generated content is stored and retrievable by ID."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        retrieved = generator.get_content(content.content_id)
        assert retrieved is not None
        assert retrieved.content_id == content.content_id


# ---------------------------------------------------------------------------
# Quiz Generation Tests (Task 16.2)
# ---------------------------------------------------------------------------


class TestQuizGeneration:
    """Tests for comprehension quiz generation."""

    @pytest.mark.asyncio
    async def test_quiz_questions_generated(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Quiz questions are generated from SOP text."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        assert len(content.quiz_questions) > 0

    @pytest.mark.asyncio
    async def test_quiz_questions_have_required_fields(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Each quiz question has question, answer, distractors, and section ref."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        for question in content.quiz_questions:
            assert question.question_id is not None
            assert len(question.question) > 0
            assert len(question.correct_answer) > 0
            assert len(question.distractors) > 0
            assert len(question.sop_section_ref) > 0

    @pytest.mark.asyncio
    async def test_quiz_questions_have_unique_ids(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Quiz question IDs are unique."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        ids = [q.question_id for q in content.quiz_questions]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Procedural Steps and Safety Points Tests (Task 16.3)
# ---------------------------------------------------------------------------


class TestProceduralStepsAndSafety:
    """Tests for procedural steps and safety points extraction."""

    @pytest.mark.asyncio
    async def test_procedural_steps_extracted(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Procedural steps are extracted from SOP text."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        assert len(content.procedural_steps) > 0

    @pytest.mark.asyncio
    async def test_procedural_steps_numbered_sequentially(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Procedural steps are numbered sequentially."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        step_numbers = [s.step_number for s in content.procedural_steps]
        assert step_numbers == list(range(1, len(step_numbers) + 1))

    @pytest.mark.asyncio
    async def test_safety_critical_steps_flagged(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Safety-critical steps are flagged with safety notes."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        safety_steps = [
            s for s in content.procedural_steps if s.is_safety_critical
        ]
        assert len(safety_steps) > 0

        for step in safety_steps:
            assert len(step.safety_note) > 0

    @pytest.mark.asyncio
    async def test_safety_points_extracted(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Safety points are extracted from SOP text."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        assert len(content.safety_points) > 0
        for point in content.safety_points:
            assert len(point) > 0


# ---------------------------------------------------------------------------
# Coordinator Review Gate Tests (Task 16.5)
# ---------------------------------------------------------------------------


class TestReviewGate:
    """Tests for the coordinator review gate."""

    @pytest.mark.asyncio
    async def test_approve_content(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Content can be approved by a coordinator."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        approved = generator.approve_content(
            content_id=content.content_id,
            reviewer_id=99,
            notes="Looks good, approved for training.",
        )

        assert approved.status == ContentStatus.APPROVED
        assert approved.reviewed_by == 99
        assert approved.reviewed_at is not None
        assert "approved" in approved.review_notes.lower()

    @pytest.mark.asyncio
    async def test_reject_content(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Content can be rejected by a coordinator."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        rejected = generator.reject_content(
            content_id=content.content_id,
            reviewer_id=99,
            notes="Quiz questions need improvement.",
        )

        assert rejected.status == ContentStatus.REJECTED
        assert rejected.reviewed_by == 99
        assert rejected.reviewed_at is not None

    @pytest.mark.asyncio
    async def test_cannot_approve_already_approved(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Cannot approve content that is already approved."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        generator.approve_content(content.content_id, reviewer_id=99)

        with pytest.raises(ValueError):
            generator.approve_content(content.content_id, reviewer_id=100)

    @pytest.mark.asyncio
    async def test_cannot_reject_already_rejected(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Cannot reject content that is already rejected."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        generator.reject_content(content.content_id, reviewer_id=99)

        with pytest.raises(ValueError):
            generator.reject_content(content.content_id, reviewer_id=100)

    @pytest.mark.asyncio
    async def test_is_content_approved(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """is_content_approved returns correct status."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        assert generator.is_content_approved(content.content_id) is False

        generator.approve_content(content.content_id, reviewer_id=99)

        assert generator.is_content_approved(content.content_id) is True

    def test_nonexistent_content_raises(
        self, generator: TrainingContentGenerator
    ) -> None:
        """Operations on non-existent content raise KeyError."""
        with pytest.raises(KeyError):
            generator.approve_content("nonexistent-id", reviewer_id=1)

        with pytest.raises(KeyError):
            generator.reject_content("nonexistent-id", reviewer_id=1)


# ---------------------------------------------------------------------------
# Audit Trail Tests (Task 16.6)
# ---------------------------------------------------------------------------


class TestAuditTrail:
    """Tests for training content generation audit trail."""

    @pytest.mark.asyncio
    async def test_generation_recorded_in_audit(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Content generation is recorded in the audit trail."""
        await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
            user_id=5,
        )

        log = generator.get_audit_log()
        assert len(log) == 1
        assert log[0].event_type == "generated"
        assert log[0].sop_document_uuid == "2024-00001"
        assert log[0].user_id == 5

    @pytest.mark.asyncio
    async def test_approval_recorded_in_audit(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Content approval is recorded in the audit trail."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        generator.approve_content(content.content_id, reviewer_id=99)

        log = generator.get_audit_log()
        assert len(log) == 2
        assert log[1].event_type == "approved"
        assert log[1].user_id == 99

    @pytest.mark.asyncio
    async def test_rejection_recorded_in_audit(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Content rejection is recorded in the audit trail."""
        content = await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )

        generator.reject_content(
            content.content_id, reviewer_id=99, notes="Needs work"
        )

        log = generator.get_audit_log()
        assert len(log) == 2
        assert log[1].event_type == "rejected"
        assert "Needs work" in log[1].details


# ---------------------------------------------------------------------------
# Content Retrieval Tests
# ---------------------------------------------------------------------------


class TestContentRetrieval:
    """Tests for content retrieval methods."""

    @pytest.mark.asyncio
    async def test_get_content_for_sop(
        self, generator: TrainingContentGenerator, sample_sop_text: str
    ) -> None:
        """Can retrieve all content for a specific SOP version."""
        await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="1.0",
            sop_text=sample_sop_text,
        )
        await generator.generate_training_content(
            sop_document_uuid="2024-00001",
            sop_version="2.0",
            sop_text=sample_sop_text,
        )

        content_v1 = generator.get_content_for_sop("2024-00001", "1.0")
        content_v2 = generator.get_content_for_sop("2024-00001", "2.0")

        assert len(content_v1) == 1
        assert len(content_v2) == 1
        assert content_v1[0].sop_version == "1.0"
        assert content_v2[0].sop_version == "2.0"

    def test_get_nonexistent_content_returns_none(
        self, generator: TrainingContentGenerator
    ) -> None:
        """Getting non-existent content returns None."""
        result = generator.get_content("nonexistent-id")
        assert result is None
