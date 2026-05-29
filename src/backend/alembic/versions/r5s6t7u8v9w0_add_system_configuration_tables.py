"""add_system_configuration_tables

Revision ID: r5s6t7u8v9w0
Revises: q4r5s6t7u8v9
Create Date: 2026-11-15 10:00:00.000000

"""

import json
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "r5s6t7u8v9w0"
down_revision: Union[str, Sequence[str], None] = "q4r5s6t7u8v9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default configuration values seeded from .env defaults
DEFAULT_CONFIGS: dict[str, dict] = {
    "ai_hardware": {
        "model_chat_name": os.environ.get("MODEL_CHAT_NAME", "Qwen/Qwen3.6-35B-A3B"),
        "model_chat_path": os.environ.get("MODEL_CHAT_PATH", "/models/qwen3.6-35b-a3b"),
        "model_chat_max_gpu_memory_gb": int(
            os.environ.get("MODEL_CHAT_MAX_GPU_MEMORY_GB", "24")
        ),
        "model_embedding_name": os.environ.get(
            "MODEL_EMBEDDING_NAME", "Qwen/Qwen3-Embedding-0.6B"
        ),
        "model_embedding_path": os.environ.get(
            "MODEL_EMBEDDING_PATH", "/models/qwen3-embedding-0.6b"
        ),
        "model_embedding_dimension": int(
            os.environ.get("MODEL_EMBEDDING_DIMENSION", "1024")
        ),
        "model_ocr_name": os.environ.get("MODEL_OCR_NAME", "google/gemma-4-E4B-it"),
        "model_ocr_path": os.environ.get("MODEL_OCR_PATH", "/models/gemma-4-e4b-it"),
        "inference_mode": os.environ.get("MODEL_MANAGER_MODE", "mock"),
        "gpu_device_id": int(os.environ.get("GPU_DEVICE_ID", "0")),
    },
    "backup_schedule": {
        "cron_expression": "0 2 * * *",
        "human_readable": "Daily at 02:00 UTC",
    },
    "backup_retention": {
        "retention_days": 30,
    },
    "health_check": {
        "polling_interval_seconds": 30,
        "degraded_threshold_seconds": 5,
        "unreachable_timeout_seconds": 10,
    },
}


def upgrade() -> None:
    """Create system configuration tables and seed initial data.

    Tables created:
    1. system_configurations - Category-keyed JSON config with audit versioning
    2. configuration_snapshots - Point-in-time config captures for rollback
    3. backup_records - Database backup execution tracking
    4. storage_quotas - Per-company storage quota configuration
    5. health_check_results - Service health check measurements
    6. resource_metric_points - Docker container resource utilization metrics
    """
    # =========================================================================
    # 1. Create system_configurations table
    # =========================================================================
    op.create_table(
        "system_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column(
            "values",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_system_configurations_updated_by_users",
        ),
        sa.UniqueConstraint("category", name="uq_system_configurations_category"),
    )
    op.create_index(
        "ix_system_configurations_category",
        "system_configurations",
        ["category"],
        unique=True,
    )

    # =========================================================================
    # 2. Create configuration_snapshots table
    # =========================================================================
    op.create_table(
        "configuration_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "snapshot_data",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("change_reason", sa.String(length=500), nullable=False),
        sa.Column(
            "is_rollback",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("rollback_target_id", sa.Integer(), nullable=True),
        sa.Column(
            "changed_keys",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_configuration_snapshots_created_by_users",
        ),
        sa.ForeignKeyConstraint(
            ["rollback_target_id"],
            ["configuration_snapshots.id"],
            name="fk_configuration_snapshots_rollback_target_id",
        ),
    )

    # =========================================================================
    # 3. Create backup_records table
    # =========================================================================
    op.create_table(
        "backup_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("backup_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=500), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["triggered_by"],
            ["users.id"],
            name="fk_backup_records_triggered_by_users",
        ),
        sa.UniqueConstraint("task_id", name="uq_backup_records_task_id"),
    )
    op.create_index(
        "ix_backup_records_task_id",
        "backup_records",
        ["task_id"],
        unique=True,
    )

    # =========================================================================
    # 4. Create storage_quotas table
    # =========================================================================
    op.create_table(
        "storage_quotas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("quota_limit_bytes", sa.BigInteger(), nullable=True),
        sa.Column("alert_threshold_pct", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_storage_quotas_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_storage_quotas_updated_by_users",
        ),
        sa.UniqueConstraint("company_id", name="uq_storage_quotas_company_id"),
    )
    op.create_index(
        "ix_storage_quotas_company_id",
        "storage_quotas",
        ["company_id"],
        unique=True,
    )

    # =========================================================================
    # 5. Create health_check_results table
    # =========================================================================
    op.create_table(
        "health_check_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_name", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_time_ms", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("previous_status", sa.String(length=20), nullable=True),
        sa.Column(
            "is_transition",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_health_check_results_service_name",
        "health_check_results",
        ["service_name"],
    )
    op.create_index(
        "ix_health_check_results_checked_at",
        "health_check_results",
        ["checked_at"],
    )
    op.create_index(
        "ix_health_check_results_service_checked",
        "health_check_results",
        ["service_name", "checked_at"],
    )

    # =========================================================================
    # 6. Create resource_metric_points table
    # =========================================================================
    op.create_table(
        "resource_metric_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_name", sa.String(length=50), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=False),
        sa.Column("memory_used_mb", sa.Float(), nullable=False),
        sa.Column("memory_limit_mb", sa.Float(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resource_metric_points_service_name",
        "resource_metric_points",
        ["service_name"],
    )
    op.create_index(
        "ix_resource_metric_points_recorded_at",
        "resource_metric_points",
        ["recorded_at"],
    )
    op.create_index(
        "ix_resource_metrics_service_recorded",
        "resource_metric_points",
        ["service_name", "recorded_at"],
    )

    # =========================================================================
    # Data migration: Seed initial configuration rows
    # =========================================================================
    connection = op.get_bind()

    for category, values in DEFAULT_CONFIGS.items():
        connection.execute(
            sa.text(
                "INSERT INTO system_configurations (category, values) "
                "VALUES (:category, :values) "
                "ON CONFLICT (category) DO NOTHING"
            ),
            {"category": category, "values": json.dumps(values)},
        )


def downgrade() -> None:
    """Drop all six system configuration tables in reverse dependency order.

    Tables are dropped in reverse order to respect foreign key constraints:
    6. resource_metric_points (no FKs to other new tables)
    5. health_check_results (no FKs to other new tables)
    4. storage_quotas (FK to companies)
    3. backup_records (FK to users)
    2. configuration_snapshots (self-referencing FK, FK to users)
    1. system_configurations (FK to users)
    """
    # Drop indexes and tables in reverse creation order
    op.drop_index(
        "ix_resource_metrics_service_recorded",
        table_name="resource_metric_points",
    )
    op.drop_index(
        "ix_resource_metric_points_recorded_at",
        table_name="resource_metric_points",
    )
    op.drop_index(
        "ix_resource_metric_points_service_name",
        table_name="resource_metric_points",
    )
    op.drop_table("resource_metric_points")

    op.drop_index(
        "ix_health_check_results_service_checked",
        table_name="health_check_results",
    )
    op.drop_index(
        "ix_health_check_results_checked_at",
        table_name="health_check_results",
    )
    op.drop_index(
        "ix_health_check_results_service_name",
        table_name="health_check_results",
    )
    op.drop_table("health_check_results")

    op.drop_index(
        "ix_storage_quotas_company_id",
        table_name="storage_quotas",
    )
    op.drop_table("storage_quotas")

    op.drop_index(
        "ix_backup_records_task_id",
        table_name="backup_records",
    )
    op.drop_table("backup_records")

    op.drop_table("configuration_snapshots")

    op.drop_index(
        "ix_system_configurations_category",
        table_name="system_configurations",
    )
    op.drop_table("system_configurations")
