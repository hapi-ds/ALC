"""Unit tests for training ecosystem API endpoints.

Tests HTTP status codes, header enforcement, pagination, filtering,
and validation across all training ecosystem routers.

Requirements: 9.1–9.15
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

TENANT = TenantContext(
    company_id=1,
    company_slug="test-company",
    user_id=1,
    membership_role="admin",
)

NOW = datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def mock_planner_service():
    """Mock TrainingPlannerService."""
    return AsyncMock()


@pytest.fixture
def mock_material_service():
    """Mock TrainingMaterialGeneratorService."""
    return AsyncMock()


@pytest.fixture
def mock_question_service():
    """Mock QuestionGeneratorService."""
    return AsyncMock()


@pytest.fixture
def mock_feedback_service():
    """Mock DynamicFeedbackService."""
    return AsyncMock()


@pytest.fixture
def mock_db_session():
    """Mock database session for roleplay router."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest_asyncio.fixture
async def client(
    mock_planner_service,
    mock_material_service,
    mock_question_service,
    mock_feedback_service,
    mock_db_session,
):
    """Create an httpx AsyncClient with all training service overrides."""
    from alcoabase.api.training_feedback import get_dynamic_feedback_service
    from alcoabase.api.training_materials import (
        get_training_material_generator_service,
    )
    from alcoabase.api.training_planner import get_training_planner_service
    from alcoabase.api.training_questions import get_question_generator_service
    from alcoabase.database import get_db_session

    async def _override_tenant():
        return TENANT

    app.dependency_overrides[get_tenant_context] = _override_tenant
    app.dependency_overrides[get_training_planner_service] = (
        lambda: mock_planner_service
    )
    app.dependency_overrides[get_training_material_generator_service] = (
        lambda: mock_material_service
    )
    app.dependency_overrides[get_question_generator_service] = (
        lambda: mock_question_service
    )
    app.dependency_overrides[get_dynamic_feedback_service] = (
        lambda: mock_feedback_service
    )
    app.dependency_overrides[get_db_session] = lambda: mock_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-Change-Reason": "Unit test",
            "X-User-Id": "1",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def client_no_reason(
    mock_planner_service,
    mock_material_service,
    mock_question_service,
    mock_feedback_service,
    mock_db_session,
):
    """Create an httpx AsyncClient WITHOUT X-Change-Reason header."""
    from alcoabase.api.training_feedback import get_dynamic_feedback_service
    from alcoabase.api.training_materials import (
        get_training_material_generator_service,
    )
    from alcoabase.api.training_planner import get_training_planner_service
    from alcoabase.api.training_questions import get_question_generator_service
    from alcoabase.database import get_db_session

    async def _override_tenant():
        return TENANT

    app.dependency_overrides[get_tenant_context] = _override_tenant
    app.dependency_overrides[get_training_planner_service] = (
        lambda: mock_planner_service
    )
    app.dependency_overrides[get_training_material_generator_service] = (
        lambda: mock_material_service
    )
    app.dependency_overrides[get_question_generator_service] = (
        lambda: mock_question_service
    )
    app.dependency_overrides[get_dynamic_feedback_service] = (
        lambda: mock_feedback_service
    )
    app.dependency_overrides[get_db_session] = lambda: mock_db_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "X-User-Id": "1",
            "X-Company-Id": "1",
        },
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# X-Change-Reason Header Enforcement Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestXChangeReasonEnforcement:
    """Test that POST/PATCH mutations require X-Change-Reason header."""

    async def test_post_planner_generate_without_reason_returns_400(
        self, client_no_reason
    ):
        """POST /api/training/planner/generate without X-Change-Reason → 400."""
        resp = await client_no_reason.post(
            "/api/training/planner/generate",
            json={"user_id": 1},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_post_materials_generate_without_reason_returns_400(
        self, client_no_reason
    ):
        """POST /api/training/materials/generate without X-Change-Reason → 400."""
        resp = await client_no_reason.post(
            "/api/training/materials/generate",
            json={"document_id": 1, "document_version_id": 1},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_post_questions_generate_without_reason_returns_400(
        self, client_no_reason
    ):
        """POST /api/training/questions/generate without X-Change-Reason → 400."""
        resp = await client_no_reason.post(
            "/api/training/questions/generate",
            json={"document_id": 1, "document_version_id": 1},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_post_roleplay_start_without_reason_returns_400(
        self, client_no_reason
    ):
        """POST /api/training/roleplay/start without X-Change-Reason → 400."""
        resp = await client_no_reason.post(
            "/api/training/roleplay/start",
            json={"document_id": 1, "document_version_id": 1, "user_id": 1},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_post_roleplay_respond_without_reason_returns_400(
        self, client_no_reason
    ):
        """POST /api/training/roleplay/{id}/respond without X-Change-Reason → 400."""
        resp = await client_no_reason.post(
            "/api/training/roleplay/99/respond",
            json={"response_text": "My answer"},
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_patch_materials_approve_without_reason_returns_400(
        self, client_no_reason
    ):
        """PATCH /api/training/materials/{id}/approve without X-Change-Reason → 400."""
        resp = await client_no_reason.patch(
            "/api/training/materials/1/approve",
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_patch_materials_reject_without_reason_returns_400(
        self, client_no_reason
    ):
        """PATCH /api/training/materials/{id}/reject without X-Change-Reason → 400."""
        resp = await client_no_reason.patch(
            "/api/training/materials/1/reject",
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_patch_questions_approve_without_reason_returns_400(
        self, client_no_reason
    ):
        """PATCH /api/training/questions/{id}/approve without X-Change-Reason → 400."""
        resp = await client_no_reason.patch(
            "/api/training/questions/1/approve",
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_patch_questions_reject_without_reason_returns_400(
        self, client_no_reason
    ):
        """PATCH /api/training/questions/{id}/reject without X-Change-Reason → 400."""
        resp = await client_no_reason.patch(
            "/api/training/questions/1/reject",
        )
        assert resp.status_code == 400
        assert "X-Change-Reason" in resp.json()["detail"]

    async def test_get_endpoints_do_not_require_reason(
        self, client_no_reason, mock_feedback_service
    ):
        """GET endpoints should NOT require X-Change-Reason header."""
        from alcoabase.schemas.training_ecosystem import DynamicFeedbackResponse

        mock_feedback_service.get_feedback.return_value = DynamicFeedbackResponse(
            correct_answer="Answer",
            paragraph_text="Paragraph",
            section_reference="Section 1",
            page_number=1,
            explanation="Explanation",
        )

        resp = await client_no_reason.get("/api/training/feedback/1")
        # Should not be 400 for missing X-Change-Reason — GET is exempt
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Training Planner Router Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrainingPlannerRouter:
    """Tests for /api/training/planner/* endpoints."""

    async def test_generate_schedule_returns_202(self, client, mock_planner_service):
        """POST /api/training/planner/generate returns 202 with job_id."""
        mock_planner_service.request_schedule_generation.return_value = "job-abc-123"

        resp = await client.post(
            "/api/training/planner/generate",
            json={"user_id": 1},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_id"] == "job-abc-123"
        assert data["status"] == "pending"

    async def test_get_schedule_returns_200(self, client, mock_planner_service):
        """GET /api/training/planner/schedule/{user_id} returns 200."""
        mock_schedule = MagicMock()
        mock_schedule.id = 1
        mock_schedule.user_id = 1
        mock_schedule.schedule_data = {"items": []}
        mock_schedule.compliance_percentage = 75.0
        mock_schedule.total_items = 10
        mock_schedule.completed_items = 7
        mock_schedule.generated_at = NOW
        mock_schedule.last_recalculated_at = NOW
        mock_planner_service.get_schedule.return_value = mock_schedule

        resp = await client.get("/api/training/planner/schedule/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["compliance_percentage"] == 75.0
        assert data["total_items"] == 10
        assert data["completed_items"] == 7

    async def test_get_schedule_returns_404_when_not_found(
        self, client, mock_planner_service
    ):
        """GET /api/training/planner/schedule/{user_id} returns 404 when no schedule."""
        mock_planner_service.get_schedule.return_value = None

        resp = await client.get("/api/training/planner/schedule/999")
        assert resp.status_code == 404

    async def test_get_company_gaps_returns_200(self, client, mock_planner_service):
        """GET /api/training/planner/gaps returns 200 with report."""
        mock_planner_service.get_company_gaps.return_value = {
            "total_users_with_gaps": 5,
            "company_compliance_percentage": 82.5,
            "top_documents": [{"document_id": 1, "untrained_count": 3}],
            "top_users": [{"user_id": 2, "gap_count": 4}],
            "by_framework": {"GMP": 90.0},
            "total": 15,
        }

        resp = await client.get("/api/training/planner/gaps")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_users_with_gaps"] == 5
        assert data["company_compliance_percentage"] == 82.5
        assert data["total"] == 15

    async def test_get_company_gaps_pagination(self, client, mock_planner_service):
        """GET /api/training/planner/gaps supports limit and offset params."""
        mock_planner_service.get_company_gaps.return_value = {
            "total_users_with_gaps": 0,
            "company_compliance_percentage": 100.0,
            "top_documents": [],
            "top_users": [],
            "total": 0,
        }

        resp = await client.get("/api/training/planner/gaps?limit=5&offset=10")
        assert resp.status_code == 200
        mock_planner_service.get_company_gaps.assert_called_once_with(
            company_id=1, limit=5, offset=10
        )


# ---------------------------------------------------------------------------
# Training Materials Router Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrainingMaterialsRouter:
    """Tests for /api/training/materials/* endpoints."""

    async def test_generate_materials_returns_202(self, client, mock_material_service):
        """POST /api/training/materials/generate returns 202 with job_id."""
        mock_material_service.request_generation.return_value = "mat-job-456"

        resp = await client.post(
            "/api/training/materials/generate",
            json={"document_id": 1, "document_version_id": 2},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_id"] == "mat-job-456"
        assert data["status"] == "pending"

    async def test_generate_materials_404_on_missing_document(
        self, client, mock_material_service
    ):
        """POST /api/training/materials/generate returns 404 for missing doc."""
        mock_material_service.request_generation.side_effect = ValueError(
            "Document not found"
        )

        resp = await client.post(
            "/api/training/materials/generate",
            json={"document_id": 999, "document_version_id": 1},
        )
        assert resp.status_code == 404

    async def test_list_materials_returns_200(self, client, mock_material_service):
        """GET /api/training/materials/{document_id} returns 200 with list."""
        mock_material = MagicMock()
        mock_material.id = 1
        mock_material.document_id = 1
        mock_material.document_version_id = 2
        mock_material.material_type = "executive_summary"
        mock_material.content_data = {"summary": "Test"}
        mock_material.learning_objectives = ["LO1"]
        mock_material.estimated_duration_minutes = 10
        mock_material.status = "pending_review"
        mock_material.generated_by_agent_id = "edu-specialist"
        mock_material.inference_duration_ms = 1500
        mock_material.reviewed_by = None
        mock_material.reviewed_at = None
        mock_material.created_at = NOW

        mock_material_service.get_materials.return_value = ([mock_material], 1)

        resp = await client.get("/api/training/materials/1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["material_type"] == "executive_summary"

    async def test_list_materials_with_filters(self, client, mock_material_service):
        """GET /api/training/materials/{document_id} supports filtering."""
        mock_material_service.get_materials.return_value = ([], 0)

        resp = await client.get(
            "/api/training/materials/1?material_type=executive_summary&status=approved&limit=5&offset=2"
        )
        assert resp.status_code == 200
        mock_material_service.get_materials.assert_called_once_with(
            document_id=1,
            company_id=1,
            material_type="executive_summary",
            status="approved",
            limit=5,
            offset=2,
        )

    async def test_approve_material_returns_200(self, client, mock_material_service):
        """PATCH /api/training/materials/{id}/approve returns 200."""
        mock_material = MagicMock()
        mock_material.id = 1
        mock_material.document_id = 1
        mock_material.document_version_id = 2
        mock_material.material_type = "executive_summary"
        mock_material.content_data = {"summary": "Approved"}
        mock_material.learning_objectives = ["LO1"]
        mock_material.estimated_duration_minutes = 10
        mock_material.status = "approved"
        mock_material.generated_by_agent_id = "edu-specialist"
        mock_material.inference_duration_ms = 1500
        mock_material.reviewed_by = 1
        mock_material.reviewed_at = NOW
        mock_material.created_at = NOW

        mock_material_service.approve_material.return_value = mock_material

        resp = await client.patch("/api/training/materials/1/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_approve_material_404_when_not_found(
        self, client, mock_material_service
    ):
        """PATCH /api/training/materials/{id}/approve returns 404 for missing."""
        mock_material_service.approve_material.side_effect = ValueError(
            "Material not found"
        )

        resp = await client.patch("/api/training/materials/999/approve")
        assert resp.status_code == 404

    async def test_approve_material_400_when_wrong_status(
        self, client, mock_material_service
    ):
        """PATCH /api/training/materials/{id}/approve returns 400 if not pending."""
        mock_material_service.approve_material.side_effect = ValueError(
            "Material is not in pending_review status"
        )

        resp = await client.patch("/api/training/materials/1/approve")
        assert resp.status_code == 400

    async def test_reject_material_returns_200(self, client, mock_material_service):
        """PATCH /api/training/materials/{id}/reject returns 200."""
        mock_material = MagicMock()
        mock_material.id = 1
        mock_material.document_id = 1
        mock_material.document_version_id = 2
        mock_material.material_type = "executive_summary"
        mock_material.content_data = {"summary": "Rejected"}
        mock_material.learning_objectives = ["LO1"]
        mock_material.estimated_duration_minutes = 10
        mock_material.status = "rejected"
        mock_material.generated_by_agent_id = "edu-specialist"
        mock_material.inference_duration_ms = 1500
        mock_material.reviewed_by = 1
        mock_material.reviewed_at = NOW
        mock_material.created_at = NOW

        mock_material_service.reject_material.return_value = mock_material

        resp = await client.patch("/api/training/materials/1/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# Training Questions Router Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrainingQuestionsRouter:
    """Tests for /api/training/questions/* endpoints."""

    async def test_generate_questions_returns_202(self, client, mock_question_service):
        """POST /api/training/questions/generate returns 202 with job_id."""
        mock_question_service.request_generation.return_value = "q-job-789"

        resp = await client.post(
            "/api/training/questions/generate",
            json={"document_id": 1, "document_version_id": 2, "question_count": 10},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["job_id"] == "q-job-789"
        assert data["status"] == "pending"

    async def test_generate_questions_422_count_below_minimum(
        self, client, mock_question_service
    ):
        """POST /api/training/questions/generate returns 422 for count < 5."""
        resp = await client.post(
            "/api/training/questions/generate",
            json={"document_id": 1, "document_version_id": 2, "question_count": 3},
        )
        assert resp.status_code == 422

    async def test_generate_questions_422_count_above_maximum(
        self, client, mock_question_service
    ):
        """POST /api/training/questions/generate returns 422 for count > 20."""
        resp = await client.post(
            "/api/training/questions/generate",
            json={"document_id": 1, "document_version_id": 2, "question_count": 25},
        )
        assert resp.status_code == 422

    async def test_list_questions_returns_200(self, client, mock_question_service):
        """GET /api/training/questions/{document_id} returns 200."""
        mock_question = MagicMock()
        mock_question.id = 1
        mock_question.question_text = "What is the purpose?"
        mock_question.question_type = "multiple_choice"
        mock_question.correct_answer = "Answer A"
        mock_question.distractors = ["B", "C", "D"]
        mock_question.explanation = "Because..."
        mock_question.difficulty_level = "basic"
        mock_question.bloom_taxonomy_level = "remember"
        mock_question.sop_section_ref = "Section 1.1"
        mock_question.status = "pending_review"
        mock_question.created_at = NOW

        mock_question_service.get_questions.return_value = ([mock_question], 1)

        resp = await client.get("/api/training/questions/1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["question_type"] == "multiple_choice"

    async def test_list_questions_with_filters(self, client, mock_question_service):
        """GET /api/training/questions/{document_id} supports all filters."""
        mock_question_service.get_questions.return_value = ([], 0)

        resp = await client.get(
            "/api/training/questions/1"
            "?status=approved&difficulty_level=basic"
            "&question_type=true_false&limit=10&offset=5"
        )
        assert resp.status_code == 200
        mock_question_service.get_questions.assert_called_once_with(
            document_id=1,
            company_id=1,
            status="approved",
            difficulty_level="basic",
            question_type="true_false",
            limit=10,
            offset=5,
        )

    async def test_approve_question_returns_200(self, client, mock_question_service):
        """PATCH /api/training/questions/{id}/approve returns 200."""
        mock_question = MagicMock()
        mock_question.id = 1
        mock_question.question_text = "What is X?"
        mock_question.question_type = "multiple_choice"
        mock_question.correct_answer = "A"
        mock_question.distractors = ["B", "C", "D"]
        mock_question.explanation = "Because A"
        mock_question.difficulty_level = "basic"
        mock_question.bloom_taxonomy_level = "remember"
        mock_question.sop_section_ref = "Section 1"
        mock_question.status = "approved"
        mock_question.created_at = NOW

        mock_question_service.approve_question.return_value = mock_question

        resp = await client.patch("/api/training/questions/1/approve")
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    async def test_reject_question_returns_200(self, client, mock_question_service):
        """PATCH /api/training/questions/{id}/reject returns 200."""
        mock_question = MagicMock()
        mock_question.id = 1
        mock_question.question_text = "What is X?"
        mock_question.question_type = "multiple_choice"
        mock_question.correct_answer = "A"
        mock_question.distractors = ["B", "C", "D"]
        mock_question.explanation = "Because A"
        mock_question.difficulty_level = "basic"
        mock_question.bloom_taxonomy_level = "remember"
        mock_question.sop_section_ref = "Section 1"
        mock_question.status = "rejected"
        mock_question.created_at = NOW

        mock_question_service.reject_question.return_value = mock_question

        resp = await client.patch("/api/training/questions/1/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"


# ---------------------------------------------------------------------------
# Training Roleplay Router Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrainingRoleplayRouter:
    """Tests for /api/training/roleplay/* endpoints."""

    async def test_respond_roleplay_409_on_completed_session(
        self, client, mock_db_session
    ):
        """POST /api/training/roleplay/{id}/respond returns 409 for completed."""
        from alcoabase.models.training_ecosystem import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = 1
        mock_session_obj.company_id = 1
        mock_session_obj.status = SessionStatus.COMPLETED
        mock_session_obj.turns_completed = 5
        mock_session_obj.total_turns = 5

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = await client.post(
            "/api/training/roleplay/1/respond",
            json={"response_text": "My answer to the question"},
        )
        assert resp.status_code == 409
        assert "no longer active" in resp.json()["detail"]

    async def test_respond_roleplay_409_on_abandoned_session(
        self, client, mock_db_session
    ):
        """POST /api/training/roleplay/{id}/respond returns 409 for abandoned."""
        from alcoabase.models.training_ecosystem import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = 2
        mock_session_obj.company_id = 1
        mock_session_obj.status = SessionStatus.ABANDONED
        mock_session_obj.turns_completed = 2
        mock_session_obj.total_turns = 7

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = await client.post(
            "/api/training/roleplay/2/respond",
            json={"response_text": "My answer"},
        )
        assert resp.status_code == 409
        assert "no longer active" in resp.json()["detail"]

    async def test_respond_roleplay_404_when_session_not_found(
        self, client, mock_db_session
    ):
        """POST /api/training/roleplay/{id}/respond returns 404 for missing."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = await client.post(
            "/api/training/roleplay/999/respond",
            json={"response_text": "My answer"},
        )
        assert resp.status_code == 404

    async def test_respond_roleplay_422_response_text_too_long(
        self, client, mock_db_session
    ):
        """POST /api/training/roleplay/{id}/respond returns 422 for > 2000 chars."""
        long_text = "A" * 2001  # Exceeds max_length=2000

        resp = await client.post(
            "/api/training/roleplay/1/respond",
            json={"response_text": long_text},
        )
        assert resp.status_code == 422

    async def test_respond_roleplay_accepts_exactly_2000_chars(
        self, client, mock_db_session
    ):
        """POST /api/training/roleplay/{id}/respond accepts exactly 2000 chars."""
        from alcoabase.models.training_ecosystem import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = 1
        mock_session_obj.company_id = 1
        mock_session_obj.status = SessionStatus.IN_PROGRESS
        mock_session_obj.turns_completed = 1
        mock_session_obj.total_turns = 5
        mock_session_obj.session_data = {"turns": [], "current_question": "Q?"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        text_2000 = "B" * 2000

        resp = await client.post(
            "/api/training/roleplay/1/respond",
            json={"response_text": text_2000},
        )
        # Should not be 422 — the request is valid at exactly 2000 chars
        assert resp.status_code != 422

    async def test_get_session_returns_200(self, client, mock_db_session):
        """GET /api/training/roleplay/{session_id} returns 200."""
        from alcoabase.models.training_ecosystem import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = 1
        mock_session_obj.user_id = 1
        mock_session_obj.document_id = 1
        mock_session_obj.company_id = 1
        mock_session_obj.status = SessionStatus.IN_PROGRESS
        mock_session_obj.overall_score = None
        mock_session_obj.passed = None
        mock_session_obj.turns_completed = 2
        mock_session_obj.total_turns = 5
        mock_session_obj.session_data = {"turns": []}
        mock_session_obj.summary_data = None
        mock_session_obj.started_at = NOW
        mock_session_obj.completed_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_session_obj
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = await client.get("/api/training/roleplay/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["turns_completed"] == 2

    async def test_get_session_returns_404_when_not_found(
        self, client, mock_db_session
    ):
        """GET /api/training/roleplay/{session_id} returns 404 for missing."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        resp = await client.get("/api/training/roleplay/999")
        assert resp.status_code == 404

    async def test_get_history_returns_200_with_pagination(
        self, client, mock_db_session
    ):
        """GET /api/training/roleplay/history/{user_id} returns paginated results."""
        from alcoabase.models.training_ecosystem import SessionStatus

        mock_session_obj = MagicMock()
        mock_session_obj.id = 1
        mock_session_obj.user_id = 1
        mock_session_obj.document_id = 1
        mock_session_obj.status = SessionStatus.COMPLETED
        mock_session_obj.overall_score = 0.85
        mock_session_obj.passed = True
        mock_session_obj.turns_completed = 5
        mock_session_obj.total_turns = 5
        mock_session_obj.session_data = None
        mock_session_obj.summary_data = {"overall_score": 0.85}
        mock_session_obj.started_at = NOW
        mock_session_obj.completed_at = NOW

        # First call: count query
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        # Second call: paginated query
        mock_list_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_session_obj]
        mock_list_result.scalars.return_value = mock_scalars

        mock_db_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        resp = await client.get(
            "/api/training/roleplay/history/1?limit=10&offset=0"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] == 1
        assert data["limit"] == 10
        assert data["offset"] == 0


# ---------------------------------------------------------------------------
# Training Feedback Router Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTrainingFeedbackRouter:
    """Tests for /api/training/feedback/* endpoints."""

    async def test_get_feedback_returns_200(self, client, mock_feedback_service):
        """GET /api/training/feedback/{question_id} returns 200 with feedback."""
        from alcoabase.schemas.training_ecosystem import DynamicFeedbackResponse

        mock_feedback = DynamicFeedbackResponse(
            correct_answer="The correct answer is X",
            paragraph_text="Source paragraph text from the document.",
            section_reference="Section 3.2, Paragraph 1",
            page_number=5,
            explanation="This paragraph explains why X is correct.",
        )
        mock_feedback_service.get_feedback.return_value = mock_feedback

        resp = await client.get("/api/training/feedback/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["correct_answer"] == "The correct answer is X"
        assert data["paragraph_text"] == "Source paragraph text from the document."
        assert data["section_reference"] == "Section 3.2, Paragraph 1"
        assert data["page_number"] == 5
        assert data["explanation"] == "This paragraph explains why X is correct."

    async def test_get_feedback_403_no_failed_attempts(
        self, client, mock_feedback_service
    ):
        """GET /api/training/feedback/{question_id} returns 403 when no failed attempts."""
        mock_feedback_service.get_feedback.side_effect = HTTPException(
            status_code=403,
            detail="Feedback is only available after a failed attempt.",
        )

        resp = await client.get("/api/training/feedback/1")
        assert resp.status_code == 403
        assert "failed attempt" in resp.json()["detail"]

    async def test_get_feedback_404_question_not_found(
        self, client, mock_feedback_service
    ):
        """GET /api/training/feedback/{question_id} returns 404 for missing question."""
        mock_feedback_service.get_feedback.side_effect = HTTPException(
            status_code=404,
            detail="Question not found.",
        )

        resp = await client.get("/api/training/feedback/999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Validation Tests (Pydantic 422 responses)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestValidationErrors:
    """Test Pydantic validation returns 422 for invalid inputs."""

    async def test_roleplay_respond_empty_body_returns_422(self, client):
        """POST /api/training/roleplay/{id}/respond with empty body → 422."""
        resp = await client.post(
            "/api/training/roleplay/1/respond",
            json={},
        )
        assert resp.status_code == 422

    async def test_planner_generate_missing_user_id_returns_422(self, client):
        """POST /api/training/planner/generate with missing user_id → 422."""
        resp = await client.post(
            "/api/training/planner/generate",
            json={},
        )
        assert resp.status_code == 422

    async def test_materials_generate_missing_fields_returns_422(self, client):
        """POST /api/training/materials/generate with missing fields → 422."""
        resp = await client.post(
            "/api/training/materials/generate",
            json={"document_id": 1},  # missing document_version_id
        )
        assert resp.status_code == 422

    async def test_questions_generate_missing_fields_returns_422(self, client):
        """POST /api/training/questions/generate with missing fields → 422."""
        resp = await client.post(
            "/api/training/questions/generate",
            json={},  # missing required fields
        )
        assert resp.status_code == 422

    async def test_roleplay_start_missing_fields_returns_422(self, client):
        """POST /api/training/roleplay/start with missing fields → 422."""
        resp = await client.post(
            "/api/training/roleplay/start",
            json={"document_id": 1},  # missing document_version_id and user_id
        )
        assert resp.status_code == 422
