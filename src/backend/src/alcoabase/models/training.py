"""Training models for SOP training assignment and execution gate.

This module defines the TrainingTask, TrainingRecord, and QuizAttempt models
that support automatic training assignment on SOP approval, the training
execution gate that blocks untrained users from regulated activities, and
quiz-based comprehension verification for ALCOA+ compliance.

References:
    - ABAC: Training records are used for attribute-based access control
    - Training gate: Users must hold valid training for exact SOP version
    - Quiz gate: Users must pass comprehension quiz before task completion
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class TrainingTask(Base, AuditMixin):
    """Training task assigned to a user for a specific SOP version.

    Tasks are automatically generated when an SOP enters "InTraining"
    status. Each user with an assigned role receives a task to read
    and understand the new SOP version.

    Attributes:
        id: Primary key.
        sop_document_uuid: Document-UUID of the SOP requiring training.
        sop_version: Version string of the SOP (e.g., "2.0").
        assigned_user_id: Foreign key to the assigned user.
        task_title: Description of the training task.
        is_completed: Whether the user has completed the task.
        completed_at: Timestamp when the task was completed (nullable).
        created_at: Server-side UTC timestamp of task creation.
        company_id: Foreign key to the owning company.
    """

    __tablename__ = "training_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    sop_document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    sop_version: Mapped[str] = mapped_column(String(20))
    assigned_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    task_title: Mapped[str] = mapped_column(Text)
    is_completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))


class TrainingRecord(Base, AuditMixin):
    """Training completion record for execution gate enforcement.

    Records track which users have valid training for which SOP versions.
    The execution gate checks these records before allowing regulated
    activities. Records are invalidated when a new major SOP version
    is activated.

    Attributes:
        id: Primary key.
        user_id: Foreign key to the trained user.
        sop_document_uuid: Document-UUID of the SOP.
        sop_version: Version string of the SOP trained on.
        is_valid: Whether this training record is still valid.
        completed_at: Timestamp when training was completed.
        invalidated_at: Timestamp when the record was invalidated (nullable).
        company_id: Foreign key to the owning company.
    """

    __tablename__ = "training_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    sop_document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    sop_version: Mapped[str] = mapped_column(String(20))
    is_valid: Mapped[bool] = mapped_column(default=True)
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))


class QuizAttempt(Base, AuditMixin):
    """Quiz attempt record for comprehension verification and audit trail.

    Records each attempt by a user to answer quiz questions for a specific
    training content. Quiz attempts are immutable (append-only) to maintain
    a complete audit trail for ALCOA+ compliance. Both passed and failed
    attempts are preserved.

    The AuditMixin enables SQLAlchemy-Continuum versioning, which
    automatically records all INSERT operations in a corresponding
    `quiz_attempts_version` table.

    Attributes:
        id: Primary key.
        user_id: Foreign key to the user who took the quiz.
        content_id: Training content identifier ({sop_document_uuid}_v{sop_version}).
        sop_document_uuid: Document-UUID of the associated SOP.
        sop_version: Version string of the SOP (e.g., "2.0").
        answers: JSON mapping of question_id to selected answer (max 50 entries).
        score: Number of correct answers (0 <= score <= total_questions).
        total_questions: Total number of questions in the quiz (minimum 1).
        passed: Whether the score meets or exceeds the passing threshold.
        attempted_at: Server-side UTC timestamp of the attempt.
        company_id: Foreign key to the owning company (tenant isolation).
    """

    __tablename__ = "quiz_attempts"
    __table_args__ = (
        Index(
            "ix_quiz_attempts_user_content_passed",
            "user_id",
            "content_id",
            "passed",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    content_id: Mapped[str] = mapped_column(String(255), index=True)
    sop_document_uuid: Mapped[str] = mapped_column(String(36), index=True)
    sop_version: Mapped[str] = mapped_column(String(20))
    answers: Mapped[dict] = mapped_column(JSON)
    score: Mapped[int] = mapped_column()
    total_questions: Mapped[int] = mapped_column()
    passed: Mapped[bool] = mapped_column()
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
