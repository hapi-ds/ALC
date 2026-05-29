"""System configuration models for Admin Dashboard Phase 6.2.

This module defines the database models for system configuration management:
- SystemConfiguration: Category-keyed JSON configuration with audit versioning.
- ConfigurationSnapshot: Point-in-time capture of all config values for rollback.
- BackupRecord: Tracks each database backup execution (scheduled or manual).
- StorageQuota: Per-company storage quota configuration with audit versioning.
- HealthCheckResult: Individual health check measurements for infrastructure services.
- ResourceMetricPoint: Time-series resource utilization data for Docker containers.

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - ALCOA+ data integrity: all configuration changes are versioned via Continuum
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company
    from alcoabase.models.user import User


class SystemConfiguration(Base, AuditMixin):
    """Persisted system configuration, one row per category.

    Stores all configuration as category-keyed JSON rows. Categories include
    "ai_hardware", "backup_schedule", "backup_retention", and "health_check".
    Database values override .env defaults at runtime.

    Versioned via SQLAlchemy-Continuum for full audit trail of all changes.

    Attributes:
        id: Primary key.
        category: Unique category identifier (e.g., "ai_hardware").
        values: JSON object containing all configuration values for this category.
        updated_at: Timestamp of last update (server-managed).
        updated_by: Foreign key to the user who last updated this configuration.
    """

    __tablename__ = "system_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    config_values: Mapped[dict] = mapped_column(
        "values", JSON, default=dict
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    user: Mapped["User | None"] = relationship()


class ConfigurationSnapshot(Base):
    """Immutable snapshot of all configuration values at a point in time.

    Used for rollback support. Each snapshot captures the full set of
    configuration values across all categories, enabling restoration to
    any previous state.

    Attributes:
        id: Primary key.
        snapshot_data: JSON containing all category values at snapshot time.
        created_at: Timestamp when the snapshot was taken.
        created_by: Foreign key to the user who triggered the change.
        change_reason: User-provided reason for the configuration change.
        is_rollback: Whether this snapshot was created by a rollback operation.
        rollback_target_id: Self-referencing FK to the snapshot that was restored.
        changed_keys: JSON list of configuration keys that changed in this snapshot.
    """

    __tablename__ = "configuration_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    change_reason: Mapped[str] = mapped_column(String(500))
    is_rollback: Mapped[bool] = mapped_column(default=False)
    rollback_target_id: Mapped[int | None] = mapped_column(
        ForeignKey("configuration_snapshots.id"), nullable=True
    )
    changed_keys: Mapped[list] = mapped_column(JSON, default=list)

    user: Mapped["User"] = relationship()
    rollback_target: Mapped["ConfigurationSnapshot | None"] = relationship(
        remote_side="ConfigurationSnapshot.id"
    )


class BackupRecord(Base):
    """Record of a database backup execution.

    Tracks each backup (scheduled or manual) through its lifecycle:
    queued → running → completed/failed. Stores metadata about the
    resulting backup file for history and recovery purposes.

    Attributes:
        id: Primary key.
        task_id: Unique Celery task identifier.
        backup_type: Type of backup ("scheduled" or "manual").
        status: Current status ("queued", "running", "completed", "failed").
        started_at: Timestamp when backup execution began.
        completed_at: Timestamp when backup finished (success or failure).
        file_size_bytes: Size of the backup file in bytes.
        storage_path: MinIO object key where the backup is stored.
        duration_seconds: Time taken to complete the backup.
        error_message: Error details if the backup failed.
        triggered_by: Foreign key to the user who triggered the backup.
        created_at: Timestamp when the backup record was created.
    """

    __tablename__ = "backup_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    backup_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    file_size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    triggered_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User | None"] = relationship()


class StorageQuota(Base, AuditMixin):
    """Per-company storage quota configuration.

    Manages advisory quota limits and alert thresholds for each company's
    MinIO storage usage. Quotas are advisory (do not block uploads) but
    trigger warning indicators when thresholds are exceeded.

    Versioned via SQLAlchemy-Continuum for audit trail of quota changes.

    Attributes:
        id: Primary key.
        company_id: Foreign key to the company (unique, one quota per company).
        quota_limit_bytes: Maximum storage allowance in bytes (null = unlimited).
        alert_threshold_pct: Warning threshold as percentage of quota (1-99).
        updated_at: Timestamp of last update (server-managed).
        updated_by: Foreign key to the user who last updated this quota.
        company: Relationship to the Company model.
    """

    __tablename__ = "storage_quotas"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), unique=True, index=True
    )
    quota_limit_bytes: Mapped[int | None] = mapped_column(nullable=True)
    alert_threshold_pct: Mapped[int | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    company: Mapped["Company"] = relationship()


class HealthCheckResult(Base):
    """Single health check measurement for a service.

    Records the result of a periodic health check against an infrastructure
    service (PostgreSQL, MinIO, OpenSearch, Redis, vLLM). Supports trend
    analysis and status transition detection.

    Attributes:
        id: Primary key.
        service_name: Name of the monitored service.
        status: Health classification ("healthy", "degraded", "unreachable").
        response_time_ms: Measured response time in milliseconds.
        error_message: Error details if the check failed.
        checked_at: Timestamp when the check was performed.
        previous_status: Status from the preceding check (for transition detection).
        is_transition: Whether this check represents a status transition.
    """

    __tablename__ = "health_check_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20))
    response_time_ms: Mapped[float | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_transition: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index(
            "ix_health_check_results_service_checked",
            "service_name",
            "checked_at",
        ),
    )


class ResourceMetricPoint(Base):
    """Resource utilization data point for a Docker container.

    Time-series data recording CPU and memory usage for each monitored
    Docker container. Used for trend analysis and capacity planning.

    Attributes:
        id: Primary key.
        service_name: Name of the monitored service/container.
        cpu_percent: CPU usage as a percentage.
        memory_used_mb: Memory usage in megabytes.
        memory_limit_mb: Container memory limit in megabytes (null if unlimited).
        recorded_at: Timestamp when the metric was recorded.
    """

    __tablename__ = "resource_metric_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(50), index=True)
    cpu_percent: Mapped[float] = mapped_column()
    memory_used_mb: Mapped[float] = mapped_column()
    memory_limit_mb: Mapped[float | None] = mapped_column(nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index(
            "ix_resource_metrics_service_recorded",
            "service_name",
            "recorded_at",
        ),
    )
