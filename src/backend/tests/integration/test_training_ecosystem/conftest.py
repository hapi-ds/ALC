"""Shared fixtures for training ecosystem integration tests.

Provides:
- Async SQLite in-memory database with all tables
- Mock external dependencies (InferenceClient, StorageService, KnowledgeService)
- Seed data helpers for users, companies, documents, and training records
- Session factory and httpx AsyncClient for full request lifecycle testing

References:
    - Task 16.3: Write backend integration tests
    - Requirements: 1.1–12.10
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentVersion
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
from alcoabase.models.user import User

# Ensure sqlalchemy_continuum tables (transaction, *_version) are registered
# in Base.metadata before create_all is called. Required because models
# with AuditMixin trigger continuum's before_flush hook.
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import configure_mappers

# Render JSONB as JSON in SQLite (must be registered before configure_mappers)
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


configure_mappers()


# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite in-memory engine for integration tests.

    Maps PostgreSQL-specific JSONB type to generic JSON for SQLite compatibility.
    Uses configure_mappers() to register Continuum versioning tables.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(async_engine):
    """Create an async session factory bound to the test engine."""
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return factory


@pytest_asyncio.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for direct test setup operations."""
    async with session_factory() as session:
        yield session
        # Commit any pending changes from seed operations
        try:
            await session.commit()
        except Exception:
            await session.rollback()


# ---------------------------------------------------------------------------
# Mock External Dependencies
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_inference_client():
    """Mock InferenceClient for LLM inference calls."""
    client = AsyncMock()
    # chat_completion returns a string (the assistant message content)
    client.chat_completion = AsyncMock(return_value='{"title": "Test Material", "sections": [{"heading": "Overview", "content": "Test content"}], "key_points": ["Point 1"], "learning_objectives": ["Understand the SOP"], "estimated_duration_minutes": 10}')
    # get_embeddings returns list of embedding vectors
    client.get_embeddings = AsyncMock(return_value=[[0.1] * 768])
    return client


@pytest.fixture
def mock_storage_service():
    """Mock StorageService for MinIO document retrieval."""
    storage = AsyncMock()
    storage.download_file = AsyncMock(
        return_value=b"Section 1: Introduction\nThis is a test SOP document.\n\nSection 2: Procedure\nFollow these steps carefully."
    )
    storage.upload_file = AsyncMock(return_value="documents/test/1.0/file.pdf")
    storage.file_exists = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def mock_knowledge_service():
    """Mock KnowledgeService for RAG retrieval."""
    service = MagicMock()
    # hybrid_search is called synchronously in DynamicFeedbackService
    mock_result = MagicMock()
    mock_result.relevance_score = 0.92
    mock_result.excerpt = "The correct procedure is to follow step 3 before step 4."
    mock_result.text = "The correct procedure is to follow step 3 before step 4."
    mock_result.metadata = {
        "section_reference": "Section 2.3",
        "page_number": 5,
    }
    service.hybrid_search = MagicMock(return_value=([mock_result], 1))
    return service


@pytest.fixture
def mock_agent_registry():
    """Mock AgentRegistryService for archetype retrieval."""
    registry = MagicMock()
    registry.get_agent = AsyncMock(return_value={
        "name": "Educational Specialist",
        "system_prompt": "You are an educational specialist...",
        "temperature": 0.6,
        "max_tokens": 8192,
    })
    # _load_archetype_raw is synchronous in the actual service
    registry._load_archetype_raw = MagicMock(return_value={
        "name": "Educational Specialist",
        "system_prompt": "You are an educational specialist that creates training materials.",
        "contextual_tuning": {
            "temperature": 0.6,
            "max_tokens": 8192,
        },
    })
    return registry


@pytest.fixture
def mock_job_tracker():
    """Mock JobTracker for async task progress tracking."""
    tracker = AsyncMock()
    tracker.create_job = AsyncMock(return_value="job-test-123")
    tracker.update_progress = AsyncMock()
    tracker.complete_job = AsyncMock()
    tracker.fail_job = AsyncMock()
    tracker.get_job = AsyncMock(return_value={
        "job_id": "job-test-123",
        "status": "completed",
        "progress": 100,
    })
    tracker.has_active_job = AsyncMock(return_value=False)
    return tracker


# ---------------------------------------------------------------------------
# Seed Data Helpers
# ---------------------------------------------------------------------------


async def seed_user(session: AsyncSession, user_id: int, username: str) -> User:
    """Insert a user directly into the database."""
    user = User(
        id=user_id,
        username=username,
        email=f"{username}@test.local",
        hashed_password="hashed_placeholder",
        full_name=f"Test User {username}",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def seed_company(
    session: AsyncSession,
    company_id: int,
    slug: str = "test-company",
    display_name: str = "Test Company",
) -> Company:
    """Insert a company directly into the database."""
    company = Company(
        id=company_id,
        slug=slug,
        display_name=display_name,
        regulatory_framework="ISO_13485",
        audit_config={},
        is_active=True,
    )
    session.add(company)
    await session.flush()
    return company


async def seed_document(
    session: AsyncSession,
    document_id: int,
    company_id: int,
    user_id: int,
    title: str = "Test SOP Document",
    document_uuid: str = "2025-00001",
) -> Document:
    """Insert a document directly into the database."""
    doc = Document(
        id=document_id,
        document_uuid=document_uuid,
        title=title,
        folder_path="/sops/test",
        document_type="SOP",
        current_status="Active",
        created_by=user_id,
        company_id=company_id,
    )
    session.add(doc)
    await session.flush()
    return doc


async def seed_document_version(
    session: AsyncSession,
    version_id: int,
    document_id: int,
    user_id: int,
    major_version: int = 1,
    minor_version: int = 0,
) -> DocumentVersion:
    """Insert a document version directly into the database."""
    version = DocumentVersion(
        id=version_id,
        document_id=document_id,
        major_version=major_version,
        minor_version=minor_version,
        storage_key=f"documents/test/{major_version}.{minor_version}/file.pdf",
        file_hash="a" * 128,
        uploaded_by=user_id,
        change_reason="Test version",
    )
    session.add(version)
    await session.flush()
    return version


async def seed_generated_question(
    session: AsyncSession,
    question_id: int,
    document_id: int,
    document_version_id: int,
    company_id: int,
    status: str = ContentStatus.PENDING_REVIEW.value,
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    difficulty_level: DifficultyLevel = DifficultyLevel.BASIC,
) -> GeneratedQuestion:
    """Insert a generated question directly into the database."""
    question = GeneratedQuestion(
        id=question_id,
        document_id=document_id,
        document_version_id=document_version_id,
        company_id=company_id,
        question_text=f"Test question {question_id}?",
        question_type=question_type,
        correct_answer="Correct answer",
        distractors=["Wrong A", "Wrong B", "Wrong C"],
        explanation="This is the explanation.",
        difficulty_level=difficulty_level,
        bloom_taxonomy_level="understand",
        sop_section_ref=f"Section {question_id}.1",
        status=status,
    )
    session.add(question)
    await session.flush()
    return question


async def seed_training_material(
    session: AsyncSession,
    material_id: int,
    document_id: int,
    document_version_id: int,
    company_id: int,
    material_type: MaterialType = MaterialType.EXECUTIVE_SUMMARY,
    status: str = ContentStatus.PENDING_REVIEW.value,
) -> TrainingMaterial:
    """Insert a training material directly into the database."""
    material = TrainingMaterial(
        id=material_id,
        document_id=document_id,
        document_version_id=document_version_id,
        company_id=company_id,
        material_type=material_type,
        content_data={"title": "Test Material", "sections": []},
        learning_objectives=["Objective 1"],
        estimated_duration_minutes=15,
        status=status,
        generated_by_agent_id="educational-specialist",
        inference_duration_ms=1500,
    )
    session.add(material)
    await session.flush()
    return material


async def seed_skill_gap(
    session: AsyncSession,
    gap_id: int,
    user_id: int,
    company_id: int,
    document_id: int,
    document_version_id: int,
    gap_type: GapType = GapType.MISSING_TRAINING,
    priority: PriorityLevel = PriorityLevel.HIGH,
) -> SkillGap:
    """Insert a skill gap directly into the database."""
    gap = SkillGap(
        id=gap_id,
        user_id=user_id,
        company_id=company_id,
        document_id=document_id,
        document_version_id=document_version_id,
        gap_type=gap_type,
        priority=priority,
        days_overdue=5,
        blocks_access=True,
    )
    session.add(gap)
    await session.flush()
    return gap


async def seed_virtual_audit_session(
    session: AsyncSession,
    session_id: int,
    user_id: int,
    document_id: int,
    document_version_id: int,
    company_id: int,
    status: SessionStatus = SessionStatus.IN_PROGRESS,
    total_turns: int = 5,
    turns_completed: int = 0,
) -> VirtualAuditSession:
    """Insert a virtual audit session directly into the database."""
    audit_session = VirtualAuditSession(
        id=session_id,
        user_id=user_id,
        document_id=document_id,
        document_version_id=document_version_id,
        company_id=company_id,
        status=status,
        total_turns=total_turns,
        turns_completed=turns_completed,
        session_data={"turns": []},
    )
    session.add(audit_session)
    await session.flush()
    return audit_session


async def seed_quiz_attempt(
    session: AsyncSession,
    attempt_id: int,
    user_id: int,
    company_id: int,
    content_id: str = "2025-00001_v1.0",
    passed: bool = False,
    score: int = 3,
    total_questions: int = 5,
) -> QuizAttempt:
    """Insert a quiz attempt directly into the database."""
    attempt = QuizAttempt(
        id=attempt_id,
        user_id=user_id,
        content_id=content_id,
        sop_document_uuid="2025-00001",
        sop_version="1.0",
        answers={"q1": "a", "q2": "b"},
        score=score,
        total_questions=total_questions,
        passed=passed,
        company_id=company_id,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def seed_training_record(
    session: AsyncSession,
    record_id: int,
    user_id: int,
    company_id: int,
    sop_document_uuid: str = "2025-00001",
    sop_version: str = "1.0",
    is_valid: bool = True,
) -> TrainingRecord:
    """Insert a training record directly into the database."""
    record = TrainingRecord(
        id=record_id,
        user_id=user_id,
        sop_document_uuid=sop_document_uuid,
        sop_version=sop_version,
        is_valid=is_valid,
        company_id=company_id,
    )
    session.add(record)
    await session.flush()
    return record
