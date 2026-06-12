"""add phase 9.5 vigilance tables

Revision ID: x1y2z3a4b5c6
Revises: e94f1a2b3c4d
Create Date: 2027-04-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "e94f1a2b3c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create Phase 9.5 Medical Device Vigilance & PMS tables.

    Tables created (in dependency order):
        - vigilance_medical_products
        - vigilance_search_profiles
        - vigilance_search_executions
        - vigilance_signals
        - vigilance_configurations
        - vigilance_periodic_safety_reports
    """

    # --- vigilance_medical_products ---
    op.create_table(
        "vigilance_medical_products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("udi", sa.String(length=128), nullable=True),
        sa.Column("device_class", sa.String(length=10), nullable=False),
        sa.Column("gmdn_code", sa.String(length=20), nullable=True),
        sa.Column("intended_purpose", sa.Text(), nullable=False),
        sa.Column("manufacturer_name", sa.String(length=300), nullable=True),
        sa.Column(
            "predicate_devices",
            postgresql.ARRAY(sa.String(length=300)),
            nullable=True,
        ),
        sa.Column("risk_class_justification", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_vigilance_medical_products_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_vigilance_medical_products_created_by",
        ),
    )

    op.create_index(
        "ix_vigilance_medical_products_company_id",
        "vigilance_medical_products",
        ["company_id"],
    )
    op.create_index(
        "ix_vigilance_medical_products_company_status",
        "vigilance_medical_products",
        ["company_id", "status"],
    )
    # Partial unique index: UDI must be unique within a company when provided
    op.create_index(
        "uq_vigilance_medical_products_company_udi",
        "vigilance_medical_products",
        ["company_id", "udi"],
        unique=True,
        postgresql_where=sa.text("udi IS NOT NULL"),
    )

    # --- vigilance_search_profiles ---
    op.create_table(
        "vigilance_search_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "search_terms",
            postgresql.ARRAY(sa.String(length=500)),
            nullable=False,
        ),
        sa.Column(
            "mesh_terms",
            postgresql.ARRAY(sa.String(length=200)),
            nullable=True,
        ),
        sa.Column(
            "adverse_event_keywords",
            postgresql.ARRAY(sa.String(length=500)),
            nullable=False,
        ),
        sa.Column(
            "device_identifiers",
            postgresql.ARRAY(sa.String(length=200)),
            nullable=True,
        ),
        sa.Column(
            "exclusion_terms",
            postgresql.ARRAY(sa.String(length=500)),
            nullable=True,
        ),
        sa.Column(
            "source_ids",
            postgresql.ARRAY(sa.String(length=100)),
            nullable=True,
        ),
        sa.Column("schedule_cron", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["vigilance_medical_products.id"],
            name="fk_vigilance_search_profiles_product_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_vigilance_search_profiles_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_vigilance_search_profiles_created_by",
        ),
    )

    op.create_index(
        "ix_vigilance_search_profiles_company_id",
        "vigilance_search_profiles",
        ["company_id"],
    )
    op.create_index(
        "ix_vigilance_search_profiles_product",
        "vigilance_search_profiles",
        ["product_id"],
    )
    op.create_index(
        "ix_vigilance_search_profiles_company_status",
        "vigilance_search_profiles",
        ["company_id", "status"],
    )

    # --- vigilance_search_executions ---
    op.create_table(
        "vigilance_search_executions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "execution_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "search_parameters",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "sources_queried",
            postgresql.ARRAY(sa.String(length=100)),
            nullable=False,
        ),
        sa.Column(
            "total_results_found",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "results_after_exclusion",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "results_ingested",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "results_duplicate",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "execution_duration_ms",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="running",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["vigilance_search_profiles.id"],
            name="fk_vigilance_search_executions_profile_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_vigilance_search_executions_company_id",
        ),
    )

    op.create_index(
        "ix_vigilance_search_executions_company_id",
        "vigilance_search_executions",
        ["company_id"],
    )
    op.create_index(
        "ix_vigilance_search_executions_profile",
        "vigilance_search_executions",
        ["profile_id"],
    )
    op.create_index(
        "ix_vigilance_search_executions_company_status",
        "vigilance_search_executions",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_vigilance_search_executions_timestamp",
        "vigilance_search_executions",
        ["company_id", "execution_timestamp"],
    )

    # --- vigilance_signals ---
    op.create_table(
        "vigilance_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ingestion_record_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("evidence_summary", sa.Text(), nullable=False),
        sa.Column(
            "affected_product_aspects",
            postgresql.ARRAY(sa.String(length=500)),
            nullable=False,
        ),
        sa.Column(
            "regulatory_references",
            postgresql.ARRAY(sa.String(length=200)),
            nullable=False,
        ),
        sa.Column(
            "recommended_actions",
            postgresql.ARRAY(sa.String(length=500)),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "disposition",
            sa.String(length=20),
            nullable=False,
            server_default="under_review",
        ),
        sa.Column("dismissal_reason", sa.Text(), nullable=True),
        sa.Column("confirmation_note", sa.Text(), nullable=True),
        sa.Column("reviewer_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "detection_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["ingestion_record_id"],
            ["literature_ingestion_records.id"],
            name="fk_vigilance_signals_ingestion_record_id",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["vigilance_medical_products.id"],
            name="fk_vigilance_signals_product_id",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["vigilance_search_profiles.id"],
            name="fk_vigilance_signals_profile_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_vigilance_signals_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_vigilance_signals_created_by",
        ),
    )

    op.create_index(
        "ix_vigilance_signals_company_id",
        "vigilance_signals",
        ["company_id"],
    )
    op.create_index(
        "ix_vigilance_signals_product",
        "vigilance_signals",
        ["product_id"],
    )
    op.create_index(
        "ix_vigilance_signals_profile",
        "vigilance_signals",
        ["profile_id"],
    )
    op.create_index(
        "ix_vigilance_signals_ingestion_record",
        "vigilance_signals",
        ["ingestion_record_id"],
    )
    op.create_index(
        "ix_vigilance_signals_company_severity",
        "vigilance_signals",
        ["company_id", "severity"],
    )
    op.create_index(
        "ix_vigilance_signals_company_disposition",
        "vigilance_signals",
        ["company_id", "disposition"],
    )

    # --- vigilance_configurations ---
    op.create_table(
        "vigilance_configurations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "critical_signal_auto_escalate",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "major_signal_daily_digest",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "escalation_notification_channels",
            postgresql.ARRAY(sa.String(length=50)),
            nullable=False,
        ),
        sa.Column(
            "report_period",
            sa.String(length=20),
            nullable=False,
            server_default="quarterly",
        ),
        sa.Column(
            "report_generation_day",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "auto_report_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_vigilance_configurations_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_vigilance_configurations_created_by",
        ),
        sa.UniqueConstraint(
            "company_id", name="uq_vigilance_configurations_company_id"
        ),
    )

    op.create_index(
        "ix_vigilance_configurations_company_id",
        "vigilance_configurations",
        ["company_id"],
    )

    # --- vigilance_periodic_safety_reports ---
    op.create_table(
        "vigilance_periodic_safety_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "report_content",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="generated",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "status_history",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["vigilance_medical_products.id"],
            name="fk_vigilance_periodic_reports_product_id",
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_vigilance_periodic_reports_company_id",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_vigilance_periodic_reports_created_by",
        ),
    )

    op.create_index(
        "ix_vigilance_periodic_reports_company_id",
        "vigilance_periodic_safety_reports",
        ["company_id"],
    )
    op.create_index(
        "ix_vigilance_periodic_reports_product",
        "vigilance_periodic_safety_reports",
        ["product_id"],
    )
    op.create_index(
        "ix_vigilance_periodic_reports_company_status",
        "vigilance_periodic_safety_reports",
        ["company_id", "status"],
    )
    op.create_index(
        "ix_vigilance_periodic_reports_period",
        "vigilance_periodic_safety_reports",
        ["company_id", "period_start", "period_end"],
    )


def downgrade() -> None:
    """Drop Phase 9.5 Vigilance tables in reverse dependency order."""
    op.drop_table("vigilance_periodic_safety_reports")
    op.drop_table("vigilance_configurations")
    op.drop_table("vigilance_signals")
    op.drop_table("vigilance_search_executions")
    op.drop_table("vigilance_search_profiles")
    op.drop_table("vigilance_medical_products")
