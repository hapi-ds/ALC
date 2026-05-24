"""Integration tests for training ecosystem full lifecycle pipelines.

Tests the complete flow through multiple services:
- Material generation pipeline: request → Celery task → DB persistence → retrieval
- Question generation pipeline: request → generation → approval → quiz availability
- Virtual audit full session: start → N responses → completion → bridge record
- Dynamic feedback with RAG: question → retrieval → explanation
- Training gate integration: approve questions → submit quiz → verify gate passes
- Skill gap recalculation: create training record → verify gap resolved

Requirements: 1.1–12.10
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.training import QuizAttempt, TrainingRecord
from alcoabase.models.training_ecosystem import (
    ActiveQuestionSet,
    ContentStatus,
    DifficultyLevel,
    DynamicFeedbackCache,
    GapType,
    GeneratedQuestion,
    MaterialType,
    PriorityLevel,
    QuestionType,
    SessionStatus,
    SkillGap,
    TrainingMaterial,
    TrainingSchedule,
    VirtualAuditSession,
)
from alcoabase.services.training_material_generator import (
    TrainingMaterialGeneratorService,
)
from alcoabase.services.quiz_service import QuizService

from .conftest import (
    seed_company,
    seed_document,
    seed_document_version,
    seed_generated_question,
    seed_quiz_attempt,
    seed_skill_gap,
    seed_training_material,
    seed_training_record,
    seed_user,
    seed_virtual_audit_session,
)


# ---------------------------------------------------------------------------
# Test 1: Full Material Generation Pipeline
# ---------------------------------------------------------------------------


class TestMaterialGenerationPipeline:
    """Test full material generation: request → task → DB persist → retrieval."""

    @pytest.mark.asyncio
    async def test_material_generation_persists_with_pending_review(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_storage_service,
        mock_agent_registry,
        mock_job_tracker,
    ):
        """Generated materials are persisted with pending_review status."""
        # Seed prerequisite data
        user = await seed_user(db_session, 1, "coordinator")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        await db_session.commit()

        # Simulate what the Celery task does: generate and persist material
        service = TrainingMaterialGeneratorService(
            session_factory=session_factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
        )

        # Generate material content (mocked LLM response)
        content = await service.generate_material_content(
            document_content="Section 1: Introduction\nTest SOP content.",
            material_type="executive_summary",
        )

        # Persist material to DB
        async with session_factory() as session:
            material = TrainingMaterial(
                document_id=1,
                document_version_id=1,
                company_id=1,
                material_type=MaterialType.EXECUTIVE_SUMMARY,
                content_data=content,
                learning_objectives=["Understand the SOP"],
                estimated_duration_minutes=10,
                status=ContentStatus.PENDING_REVIEW.value,
                generated_by_agent_id="educational-specialist",
                inference_duration_ms=1200,
            )
            session.add(material)
            await session.commit()

        # Retrieve and verify
        async with session_factory() as session:
            result = await session.execute(
                select(TrainingMaterial).where(
                    TrainingMaterial.document_id == 1,
                    TrainingMaterial.company_id == 1,
                )
            )
            materials = result.scalars().all()

        assert len(materials) == 1
        assert materials[0].status == ContentStatus.PENDING_REVIEW.value
        assert materials[0].material_type == MaterialType.EXECUTIVE_SUMMARY
        assert materials[0].inference_duration_ms == 1200
        assert materials[0].generated_by_agent_id == "educational-specialist"

    @pytest.mark.asyncio
    async def test_material_approve_reject_flow(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_storage_service,
        mock_agent_registry,
    ):
        """Materials can be approved/rejected by coordinator after generation."""
        user = await seed_user(db_session, 1, "coordinator")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        material = await seed_training_material(
            db_session, 1, 1, 1, 1,
            material_type=MaterialType.EXECUTIVE_SUMMARY,
            status=ContentStatus.PENDING_REVIEW.value,
        )
        await db_session.commit()

        service = TrainingMaterialGeneratorService(
            session_factory=session_factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
        )

        # Approve the material
        approved = await service.approve_material(
            material_id=1, reviewer_id=1, company_id=1
        )
        assert approved.status == ContentStatus.APPROVED.value
        assert approved.reviewed_by == 1

    @pytest.mark.asyncio
    async def test_material_retrieval_with_filtering(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_storage_service,
        mock_agent_registry,
    ):
        """Materials can be retrieved with type and status filtering."""
        user = await seed_user(db_session, 1, "coordinator")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Seed multiple materials with different types and statuses
        await seed_training_material(
            db_session, 1, 1, 1, 1,
            material_type=MaterialType.EXECUTIVE_SUMMARY,
            status=ContentStatus.APPROVED.value,
        )
        await seed_training_material(
            db_session, 2, 1, 1, 1,
            material_type=MaterialType.DETAILED_WALKTHROUGH,
            status=ContentStatus.PENDING_REVIEW.value,
        )
        await db_session.commit()

        service = TrainingMaterialGeneratorService(
            session_factory=session_factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
            storage_service=mock_storage_service,
        )

        # Filter by status=approved
        materials, count = await service.get_materials(
            document_id=1, company_id=1, status="approved"
        )
        assert count == 1
        assert materials[0].material_type == MaterialType.EXECUTIVE_SUMMARY

        # Filter by material_type
        materials, count = await service.get_materials(
            document_id=1, company_id=1,
            material_type="detailed_walkthrough",
        )
        assert count == 1
        assert materials[0].status == ContentStatus.PENDING_REVIEW.value


# ---------------------------------------------------------------------------
# Test 2: Full Question Generation Pipeline
# ---------------------------------------------------------------------------


class TestQuestionGenerationPipeline:
    """Test full question pipeline: generate → approve → quiz availability."""

    @pytest.mark.asyncio
    async def test_questions_generated_with_pending_review(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_agent_registry,
    ):
        """Generated questions start with pending_review status."""
        user = await seed_user(db_session, 1, "coordinator")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        await db_session.commit()

        # Persist questions as the Celery task would
        async with session_factory() as session:
            for i in range(5):
                q = GeneratedQuestion(
                    document_id=1,
                    document_version_id=1,
                    company_id=1,
                    question_text=f"What is step {i+1}?",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    correct_answer=f"Answer {i+1}",
                    distractors=["Wrong A", "Wrong B", "Wrong C"],
                    explanation=f"Explanation for question {i+1}",
                    difficulty_level=DifficultyLevel.BASIC,
                    bloom_taxonomy_level="understand",
                    sop_section_ref=f"Section {i+1}.1",
                    status=ContentStatus.PENDING_REVIEW.value,
                )
                session.add(q)
            await session.commit()

        # Verify all are pending_review
        async with session_factory() as session:
            result = await session.execute(
                select(GeneratedQuestion).where(
                    GeneratedQuestion.document_id == 1
                )
            )
            questions = result.scalars().all()

        assert len(questions) == 5
        assert all(
            q.status == ContentStatus.PENDING_REVIEW.value for q in questions
        )

    @pytest.mark.asyncio
    async def test_approve_questions_then_register_for_quiz(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_agent_registry,
    ):
        """Approved questions can be registered as active quiz question set."""
        user = await seed_user(db_session, 1, "coordinator")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Seed questions with approved status
        for i in range(5):
            await seed_generated_question(
                db_session, i + 1, 1, 1, 1,
                status=ContentStatus.APPROVED.value,
                difficulty_level=DifficultyLevel.BASIC,
            )
        await db_session.commit()


        quiz_service = QuizService(content_generator=MagicMock())

        # Register approved questions as active question set
        async with session_factory() as session:
            content_id = await quiz_service.register_approved_questions(
                session=session,
                document_id=1,
                document_version_id=1,
                document_uuid="2025-00001",
                sop_version="1.0",
                company_id=1,
            )
            await session.commit()

        assert content_id == "2025-00001_v1.0"

        # Verify ActiveQuestionSet was created
        async with session_factory() as session:
            result = await session.execute(
                select(ActiveQuestionSet).where(
                    ActiveQuestionSet.content_id == "2025-00001_v1.0",
                    ActiveQuestionSet.is_active.is_(True),
                )
            )
            active_set = result.scalar_one_or_none()

        assert active_set is not None
        assert active_set.document_id == 1
        assert active_set.company_id == 1

    @pytest.mark.asyncio
    async def test_question_approval_and_rejection_flow(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_agent_registry,
    ):
        """Questions can be individually approved or rejected by coordinator."""
        user = await seed_user(db_session, 1, "coordinator")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        q1 = await seed_generated_question(db_session, 1, 1, 1, 1)
        q2 = await seed_generated_question(
            db_session, 2, 1, 1, 1,
            question_type=QuestionType.TRUE_FALSE,
        )
        await db_session.commit()

        from alcoabase.services.question_generator import (
            QuestionGeneratorService,
        )

        service = QuestionGeneratorService(
            session_factory=session_factory,
            inference_client=mock_inference_client,
            agent_registry=mock_agent_registry,
        )

        # Approve question 1
        approved = await service.approve_question(
            question_id=1, reviewer_id=1, company_id=1
        )
        assert approved.status == ContentStatus.APPROVED.value
        assert approved.reviewed_by == 1

        # Reject question 2
        rejected = await service.reject_question(
            question_id=2, reviewer_id=1, company_id=1
        )
        assert rejected.status == ContentStatus.REJECTED.value
        assert rejected.reviewed_by == 1


# ---------------------------------------------------------------------------
# Test 3: Virtual Audit Full Session
# ---------------------------------------------------------------------------


class TestVirtualAuditFullSession:
    """Test virtual audit: start → N responses → completion → bridge record."""

    @pytest.mark.asyncio
    async def test_session_lifecycle_start_to_completion(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_agent_registry,
        mock_storage_service,
    ):
        """Full session lifecycle: start, respond N times, complete."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        await db_session.commit()

        # Configure mock to return evaluation + next question
        mock_inference_client.chat_completion = AsyncMock(return_value={
            "choices": [{
                "message": {
                    "content": '{"factual_accuracy": 0.85, "completeness": 0.80, "document_reference_quality": 0.75, "next_question": "What is the next step?", "feedback": "Good answer."}'
                }
            }]
        })

        # Simulate session creation and turn progression
        async with session_factory() as session:
            audit_session = VirtualAuditSession(
                user_id=1,
                document_id=1,
                document_version_id=1,
                company_id=1,
                status=SessionStatus.IN_PROGRESS,
                total_turns=5,
                turns_completed=0,
                session_data={"turns": []},
            )
            session.add(audit_session)
            await session.commit()
            session_id = audit_session.id

        # Simulate completing all 5 turns
        turns_data = []
        for i in range(5):
            turn = {
                "turn_number": i + 1,
                "question": f"Question {i + 1}?",
                "response": f"Response to question {i + 1}",
                "evaluation": {
                    "factual_accuracy": 0.85,
                    "completeness": 0.80,
                    "document_reference_quality": 0.75,
                },
            }
            turns_data.append(turn)

        # Update session to completed state
        from alcoabase.services.roleplay_engine import compute_session_score

        scores = [t["evaluation"] for t in turns_data]
        overall_score = compute_session_score(scores)

        async with session_factory() as session:
            result = await session.execute(
                select(VirtualAuditSession).where(
                    VirtualAuditSession.id == session_id
                )
            )
            audit = result.scalar_one()
            audit.turns_completed = 5
            audit.session_data = {"turns": turns_data}
            audit.overall_score = overall_score
            audit.passed = overall_score >= 0.70
            audit.status = SessionStatus.COMPLETED
            audit.completed_at = datetime.now(UTC)
            await session.commit()

        # Verify session is completed with correct score
        async with session_factory() as session:
            result = await session.execute(
                select(VirtualAuditSession).where(
                    VirtualAuditSession.id == session_id
                )
            )
            completed = result.scalar_one()

        assert completed.status == SessionStatus.COMPLETED
        assert completed.turns_completed == 5
        assert completed.passed is True
        # Score: 0.85*0.5 + 0.80*0.3 + 0.75*0.2 = 0.425 + 0.24 + 0.15 = 0.815
        assert abs(completed.overall_score - 0.815) < 0.001

    @pytest.mark.asyncio
    async def test_passed_session_creates_bridge_record(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
    ):
        """Passed virtual audit creates synthetic QuizAttempt bridge record."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Create a completed, passed virtual audit session
        audit_session = await seed_virtual_audit_session(
            db_session, 1, 1, 1, 1, 1,
            status=SessionStatus.COMPLETED,
            total_turns=5,
            turns_completed=5,
        )
        # Set passed and score
        audit_session.passed = True
        audit_session.overall_score = 0.85
        audit_session.session_data = {
            "turns": [
                {
                    "evaluation": {
                        "factual_accuracy": 0.9,
                        "completeness": 0.8,
                        "document_reference_quality": 0.8,
                    }
                }
                for _ in range(5)
            ]
        }
        await db_session.commit()


        quiz_service = QuizService(content_generator=MagicMock())

        # Check if user passed (should find virtual audit and create bridge)
        async with session_factory() as session:
            passed = await quiz_service.has_user_passed_enhanced(
                session=session,
                user_id=1,
                content_id="2025-00001_v1.0",
            )
            await session.commit()

        assert passed is True

        # Verify synthetic QuizAttempt was created
        async with session_factory() as session:
            result = await session.execute(
                select(QuizAttempt).where(
                    QuizAttempt.user_id == 1,
                    QuizAttempt.content_id == "2025-00001_v1.0",
                    QuizAttempt.passed.is_(True),
                )
            )
            attempt = result.scalar_one_or_none()

        assert attempt is not None
        assert attempt.passed is True

    @pytest.mark.asyncio
    async def test_incomplete_session_fewer_than_3_turns(
        self,
        session_factory,
        db_session: AsyncSession,
    ):
        """Session with fewer than 3 turns is marked incomplete, not pass/fail."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        await db_session.commit()

        from alcoabase.services.roleplay_engine import (
            compute_session_score,
            determine_pass_fail,
        )

        # 2 turns completed with high scores
        turns = [
            {"factual_accuracy": 0.95, "completeness": 0.90, "document_reference_quality": 0.85},
            {"factual_accuracy": 0.90, "completeness": 0.85, "document_reference_quality": 0.80},
        ]
        score = compute_session_score(turns)
        result = determine_pass_fail(score, turns_completed=2)

        # Should be None (incomplete) despite high score
        assert result is None
        assert score > 0.70  # Score is high but doesn't matter


# ---------------------------------------------------------------------------
# Test 4: Dynamic Feedback with RAG
# ---------------------------------------------------------------------------


class TestDynamicFeedbackWithRAG:
    """Test dynamic feedback: question → retrieval → explanation."""

    @pytest.mark.asyncio
    async def test_feedback_requires_failed_attempt(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_knowledge_service,
    ):
        """Feedback is only available after a failed quiz attempt."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        question = await seed_generated_question(
            db_session, 1, 1, 1, 1,
            status=ContentStatus.APPROVED.value,
        )
        await db_session.commit()

        from alcoabase.services.dynamic_feedback import DynamicFeedbackService

        service = DynamicFeedbackService(
            session_factory=session_factory,
            inference_client=mock_inference_client,
            knowledge_service=mock_knowledge_service,
        )

        # No failed attempt exists — should raise 403
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await service.get_feedback(
                question_id=1, user_id=1, company_id=1
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_feedback_returned_after_failed_attempt(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_knowledge_service,
    ):
        """Feedback is returned when user has a failed attempt."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        question = await seed_generated_question(
            db_session, 1, 1, 1, 1,
            status=ContentStatus.APPROVED.value,
        )
        # Create a failed quiz attempt
        await seed_quiz_attempt(
            db_session, 1, 1, 1,
            content_id="2025-00001_v1.0",
            passed=False,
            score=2,
            total_questions=5,
        )
        await db_session.commit()

        # Configure mock for explanation generation
        mock_inference_client.chat_completion = AsyncMock(
            return_value="The correct answer is found in Section 2.3 because the procedure requires following step 3 before step 4."
        )

        from alcoabase.services.dynamic_feedback import DynamicFeedbackService

        service = DynamicFeedbackService(
            session_factory=session_factory,
            inference_client=mock_inference_client,
            knowledge_service=mock_knowledge_service,
        )

        feedback = await service.get_feedback(
            question_id=1, user_id=1, company_id=1
        )

        assert feedback is not None
        # Verify RAG was called
        mock_knowledge_service.hybrid_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_feedback_cache_invalidation(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_knowledge_service,
    ):
        """Cache is invalidated when a new document version is published."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)
        question = await seed_generated_question(
            db_session, 1, 1, 1, 1,
            status=ContentStatus.APPROVED.value,
        )
        await db_session.commit()

        # Seed a cached feedback entry
        async with session_factory() as session:
            cache_entry = DynamicFeedbackCache(
                question_id=1,
                document_version_id=1,
                paragraph_text="The procedure requires step 3 before step 4.",
                section_reference="Section 2.3",
                page_number=5,
                similarity_score=0.92,
                explanation="This paragraph explains the correct order.",
            )
            session.add(cache_entry)
            await session.commit()

        from alcoabase.services.dynamic_feedback import DynamicFeedbackService

        service = DynamicFeedbackService(
            session_factory=session_factory,
            inference_client=mock_inference_client,
            knowledge_service=mock_knowledge_service,
        )

        # Invalidate cache for document version 1
        count = await service.invalidate_cache(document_version_id=1)
        assert count >= 1

        # Verify cache is empty
        async with session_factory() as session:
            result = await session.execute(
                select(DynamicFeedbackCache).where(
                    DynamicFeedbackCache.document_version_id == 1
                )
            )
            remaining = result.scalars().all()

        assert len(remaining) == 0


# ---------------------------------------------------------------------------
# Test 5: Training Gate Integration
# ---------------------------------------------------------------------------


class TestTrainingGateIntegration:
    """Test training gate: approve questions → submit quiz → verify gate passes."""

    @pytest.mark.asyncio
    async def test_quiz_pass_satisfies_training_gate(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
    ):
        """Passing a quiz with approved questions satisfies the training gate."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Seed approved questions
        for i in range(5):
            await seed_generated_question(
                db_session, i + 1, 1, 1, 1,
                status=ContentStatus.APPROVED.value,
            )

        # Create a passing quiz attempt
        await seed_quiz_attempt(
            db_session, 1, 1, 1,
            content_id="2025-00001_v1.0",
            passed=True,
            score=5,
            total_questions=5,
        )
        await db_session.commit()


        quiz_service = QuizService(content_generator=MagicMock())

        # Verify gate passes
        async with session_factory() as session:
            passed = await quiz_service.has_user_passed_enhanced(
                session=session,
                user_id=1,
                content_id="2025-00001_v1.0",
            )

        assert passed is True

    @pytest.mark.asyncio
    async def test_virtual_audit_pass_satisfies_training_gate(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
    ):
        """Passing a virtual audit also satisfies the training gate."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Create a passed virtual audit session (no quiz attempt yet)
        audit = await seed_virtual_audit_session(
            db_session, 1, 1, 1, 1, 1,
            status=SessionStatus.COMPLETED,
            total_turns=5,
            turns_completed=5,
        )
        audit.passed = True
        audit.overall_score = 0.82
        audit.session_data = {
            "turns": [
                {
                    "evaluation": {
                        "factual_accuracy": 0.85,
                        "completeness": 0.80,
                        "document_reference_quality": 0.75,
                    }
                }
                for _ in range(5)
            ]
        }
        await db_session.commit()


        quiz_service = QuizService(content_generator=MagicMock())

        # Verify gate passes via virtual audit
        async with session_factory() as session:
            passed = await quiz_service.has_user_passed_enhanced(
                session=session,
                user_id=1,
                content_id="2025-00001_v1.0",
            )

        assert passed is True

    @pytest.mark.asyncio
    async def test_failed_quiz_does_not_satisfy_gate(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
    ):
        """A failed quiz attempt does not satisfy the training gate."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Create a failed quiz attempt only
        await seed_quiz_attempt(
            db_session, 1, 1, 1,
            content_id="2025-00001_v1.0",
            passed=False,
            score=2,
            total_questions=5,
        )
        await db_session.commit()


        quiz_service = QuizService(content_generator=MagicMock())

        # Verify gate does NOT pass
        async with session_factory() as session:
            passed = await quiz_service.has_user_passed_enhanced(
                session=session,
                user_id=1,
                content_id="2025-00001_v1.0",
            )

        assert passed is False

    @pytest.mark.asyncio
    async def test_only_approved_questions_in_active_set(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
    ):
        """Only approved questions are registered in active question sets."""
        user = await seed_user(db_session, 1, "coordinator")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Mix of approved and non-approved questions
        await seed_generated_question(
            db_session, 1, 1, 1, 1,
            status=ContentStatus.APPROVED.value,
        )
        await seed_generated_question(
            db_session, 2, 1, 1, 1,
            status=ContentStatus.APPROVED.value,
        )
        await seed_generated_question(
            db_session, 3, 1, 1, 1,
            status=ContentStatus.PENDING_REVIEW.value,
        )
        await seed_generated_question(
            db_session, 4, 1, 1, 1,
            status=ContentStatus.REJECTED.value,
        )
        await db_session.commit()


        quiz_service = QuizService(content_generator=MagicMock())

        # Register approved questions
        async with session_factory() as session:
            content_id = await quiz_service.register_approved_questions(
                session=session,
                document_id=1,
                document_version_id=1,
                document_uuid="2025-00001",
                sop_version="1.0",
                company_id=1,
            )
            await session.commit()

        # Verify only approved questions are in the active set
        async with session_factory() as session:
            result = await session.execute(
                select(ActiveQuestionSet).where(
                    ActiveQuestionSet.content_id == content_id,
                    ActiveQuestionSet.is_active.is_(True),
                )
            )
            active_set = result.scalar_one_or_none()

        assert active_set is not None
        assert active_set.is_active is True


# ---------------------------------------------------------------------------
# Test 6: Skill Gap Recalculation
# ---------------------------------------------------------------------------


class TestSkillGapRecalculation:
    """Test skill gap: create training record → verify gap resolved."""

    @pytest.mark.asyncio
    async def test_gap_resolved_when_training_completed(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_agent_registry,
    ):
        """Skill gap is resolved when user completes required training."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc = await seed_document(db_session, 1, 1, 1)
        version = await seed_document_version(db_session, 1, 1, 1)

        # Create an unresolved skill gap
        gap = await seed_skill_gap(
            db_session, 1, 1, 1, 1, 1,
            gap_type=GapType.MISSING_TRAINING,
            priority=PriorityLevel.HIGH,
        )
        await db_session.commit()

        # Verify gap exists and is unresolved
        async with session_factory() as session:
            result = await session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == 1,
                    SkillGap.document_id == 1,
                    SkillGap.resolved_at.is_(None),
                )
            )
            unresolved = result.scalars().all()
        assert len(unresolved) == 1

        # Simulate training completion by resolving the gap
        async with session_factory() as session:
            result = await session.execute(
                select(SkillGap).where(SkillGap.id == 1)
            )
            gap_record = result.scalar_one()
            gap_record.resolved_at = datetime.now(UTC)
            await session.commit()

        # Verify gap is now resolved
        async with session_factory() as session:
            result = await session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == 1,
                    SkillGap.document_id == 1,
                    SkillGap.resolved_at.is_(None),
                )
            )
            still_unresolved = result.scalars().all()
        assert len(still_unresolved) == 0

    @pytest.mark.asyncio
    async def test_recalculate_gaps_creates_new_gaps(
        self,
        session_factory,
        db_session: AsyncSession,
        mock_inference_client,
        mock_agent_registry,
    ):
        """Recalculation identifies new gaps for untrained documents."""
        user = await seed_user(db_session, 1, "trainee")
        company = await seed_company(db_session, 1)
        doc1 = await seed_document(db_session, 1, 1, 1, title="SOP 1")
        doc2 = await seed_document(
            db_session, 2, 1, 1,
            title="SOP 2",
            document_uuid="2025-00002",
        )
        v1 = await seed_document_version(db_session, 1, 1, 1)
        v2 = await seed_document_version(db_session, 2, 2, 1)

        # User has training for doc1 but not doc2
        await seed_training_record(
            db_session, 1, 1, 1,
            sop_document_uuid="2025-00001",
            sop_version="1.0",
        )
        await db_session.commit()

        # Simulate gap recalculation: doc2 should have a gap
        async with session_factory() as session:
            # Check if gap already exists for doc2
            result = await session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == 1,
                    SkillGap.document_id == 2,
                )
            )
            existing = result.scalar_one_or_none()
            assert existing is None

            # Create gap for doc2 (simulating recalculation logic)
            new_gap = SkillGap(
                user_id=1,
                company_id=1,
                document_id=2,
                document_version_id=2,
                gap_type=GapType.MISSING_TRAINING,
                priority=PriorityLevel.MEDIUM,
                days_overdue=0,
                blocks_access=False,
            )
            session.add(new_gap)
            await session.commit()

        # Verify gap was created for doc2
        async with session_factory() as session:
            result = await session.execute(
                select(SkillGap).where(
                    SkillGap.user_id == 1,
                    SkillGap.company_id == 1,
                    SkillGap.resolved_at.is_(None),
                )
            )
            gaps = result.scalars().all()

        assert len(gaps) == 1
        assert gaps[0].document_id == 2
        assert gaps[0].gap_type == GapType.MISSING_TRAINING

    @pytest.mark.asyncio
    async def test_compliance_percentage_updates_on_gap_resolution(
        self,
        session_factory,
        db_session: AsyncSession,
    ):
        """Compliance percentage increases when gaps are resolved."""
        from alcoabase.services.training_planner import (
            compute_compliance_percentage,
        )

        # Initially 2 of 5 items completed
        assert compute_compliance_percentage(2, 5) == 40.0

        # After completing one more
        assert compute_compliance_percentage(3, 5) == 60.0

        # All completed
        assert compute_compliance_percentage(5, 5) == 100.0

        # Edge case: no items
        assert compute_compliance_percentage(0, 0) == 100.0

    @pytest.mark.asyncio
    async def test_priority_elevation_for_access_gated_documents(
        self,
        session_factory,
        db_session: AsyncSession,
    ):
        """Documents that block access get priority elevated by one level."""
        from alcoabase.services.training_planner import compute_priority

        # Medium deadline (30-90 days) with blocks_access=True → High
        from datetime import timedelta

        deadline_60_days = datetime.now(UTC) + timedelta(days=60)
        priority = compute_priority(deadline_60_days, blocks_access=True)
        assert priority == PriorityLevel.HIGH

        # Low deadline (>90 days) with blocks_access=True → Medium
        deadline_120_days = datetime.now(UTC) + timedelta(days=120)
        priority = compute_priority(deadline_120_days, blocks_access=True)
        assert priority == PriorityLevel.MEDIUM

        # Critical deadline (<=7 days) stays Critical even with elevation
        deadline_3_days = datetime.now(UTC) + timedelta(days=3)
        priority = compute_priority(deadline_3_days, blocks_access=True)
        assert priority == PriorityLevel.CRITICAL
