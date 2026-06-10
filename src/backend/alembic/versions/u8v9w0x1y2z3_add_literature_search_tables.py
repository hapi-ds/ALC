"""add literature search tables

Revision ID: u8v9w0x1y2z3
Revises: t7u8v9w0x1y2
Create Date: 2027-02-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "u8v9w0x1y2z3"
down_revision: Union[str, Sequence[str], None] = "t7u8v9w0x1y2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all Literature Search Engine tables.

    Tables created:
        - literature_source_configurations: Per-company source adapter configs
        - literature_search_profiles: Named search profiles per company
        - literature_system_rate_limits: System-level rate limit configs per source
        - literature_proxy_configuration: Global proxy settings for outbound requests
        - literature_external_api_audit_log: Immutable audit log of external API calls
        - literature_source_health_checks: Health check results for trend analysis
    """

    # --- literature_source_configurations ---
    op.create_table(
        "literature_source_configurations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("source_adapter_name", sa.String(length=100), nullable=False),
        sa.Column(
            "is_enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("api_key_nonce", sa.String(length=32), nullable=True),
        sa.Column("api_key_tag", sa.String(length=32), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True),
        sa.Column("proxy_override_url", sa.String(length=500), nullable=True),
        sa.Column("contact_email", sa.String(length=320), nullable=True),
        sa.Column(
            "extra_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
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
            name="fk_lit_source_config_company_id_companies",
        ),
        sa.UniqueConstraint(
            "company_id",
            "source_adapter_name",
            name="uq_lit_source_config_company_adapter",
        ),
    )
    op.create_index(
        "ix_literature_source_configurations_company_id",
        "literature_source_configurations",
        ["company_id"],
    )
    op.create_index(
        "ix_literature_source_configurations_source_adapter_name",
        "literature_source_configurations",
        ["source_adapter_name"],
    )
    op.create_index(
        "ix_lit_source_config_company_enabled",
        "literature_source_configurations",
        ["company_id", "is_enabled"],
    )

    # --- literature_search_profiles ---
    op.create_table(
        "literature_search_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "enabled_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "source_priorities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "default_filters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
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
            name="fk_lit_search_profile_company_id_companies",
        ),
        sa.UniqueConstraint(
            "company_id", "name", name="uq_lit_search_profile_company_name"
        ),
    )
    op.create_index(
        "ix_literature_search_profiles_company_id",
        "literature_search_profiles",
        ["company_id"],
    )
    op.create_index(
        "ix_lit_search_profile_company_default",
        "literature_search_profiles",
        ["company_id", "is_default"],
    )

    # --- literature_system_rate_limits ---
    op.create_table(
        "literature_system_rate_limits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "source_adapter_name", sa.String(length=100), nullable=False
        ),
        sa.Column(
            "requests_per_second",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
        sa.Column(
            "max_queue_size", sa.Integer(), nullable=False, server_default="500"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_adapter_name",
            name="uq_lit_system_rate_limits_source_adapter_name",
        ),
    )
    op.create_index(
        "ix_literature_system_rate_limits_source_adapter_name",
        "literature_system_rate_limits",
        ["source_adapter_name"],
    )

    # --- literature_proxy_configuration ---
    op.create_table(
        "literature_proxy_configuration",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proxy_url", sa.String(length=500), nullable=False),
        sa.Column("username_ciphertext", sa.Text(), nullable=True),
        sa.Column("username_nonce", sa.String(length=32), nullable=True),
        sa.Column("username_tag", sa.String(length=32), nullable=True),
        sa.Column("password_ciphertext", sa.Text(), nullable=True),
        sa.Column("password_nonce", sa.String(length=32), nullable=True),
        sa.Column("password_tag", sa.String(length=32), nullable=True),
        sa.Column(
            "no_proxy_list",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- literature_external_api_audit_log ---
    op.create_table(
        "literature_external_api_audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("query_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_adapter_name", sa.String(length=100), nullable=False
        ),
        sa.Column("request_url", sa.Text(), nullable=False),
        sa.Column(
            "request_timestamp", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "response_timestamp", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("http_status_code", sa.Integer(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "retry_attempt", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_lit_audit_log_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_lit_audit_log_user_id_users",
        ),
    )
    op.create_index(
        "ix_literature_external_api_audit_log_query_id",
        "literature_external_api_audit_log",
        ["query_id"],
    )
    op.create_index(
        "ix_literature_external_api_audit_log_company_id",
        "literature_external_api_audit_log",
        ["company_id"],
    )
    op.create_index(
        "ix_literature_external_api_audit_log_source_adapter_name",
        "literature_external_api_audit_log",
        ["source_adapter_name"],
    )
    op.create_index(
        "ix_lit_audit_log_company_timestamp",
        "literature_external_api_audit_log",
        ["company_id", "request_timestamp"],
    )

    # --- literature_source_health_checks ---
    op.create_table(
        "literature_source_health_checks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "source_adapter_name", sa.String(length=100), nullable=False
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_literature_source_health_checks_source_adapter_name",
        "literature_source_health_checks",
        ["source_adapter_name"],
    )
    op.create_index(
        "ix_lit_health_check_source_time",
        "literature_source_health_checks",
        ["source_adapter_name", "checked_at"],
    )


def downgrade() -> None:
    """Drop all literature search tables in reverse creation order."""
    op.drop_table("literature_source_health_checks")
    op.drop_table("literature_external_api_audit_log")
    op.drop_table("literature_proxy_configuration")
    op.drop_table("literature_system_rate_limits")
    op.drop_table("literature_search_profiles")
    op.drop_table("literature_source_configurations")
