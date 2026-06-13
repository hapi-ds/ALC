"""add_rbac_permission_templates

Revision ID: q4r5s6t7u8v9
Revises: p3q4r5s6t7u8
Create Date: 2026-11-01 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "q4r5s6t7u8v9"
down_revision: Union[str, Sequence[str], None] = "p3q4r5s6t7u8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Default role permission definitions for seeding
DEFAULT_ROLE_PERMISSIONS: dict[str, dict[str, list[str]]] = {
    "system_admin": {
        "documents": ["create", "read", "update", "delete", "approve"],
        "workflows": ["create", "read", "update", "delete", "approve"],
        "users": ["create", "read", "update", "delete", "approve"],
        "audit_logs": ["create", "read", "update", "delete", "approve"],
        "templates": ["create", "read", "update", "delete", "approve"],
        "training": ["create", "read", "update", "delete", "approve"],
        "signatures": ["create", "read", "update", "delete", "approve"],
        "system_config": ["create", "read", "update", "delete", "approve"],
    },
    "doc_admin": {
        "documents": ["create", "read", "update", "approve"],
        "workflows": ["create", "read", "update", "approve"],
        "templates": ["create", "read", "update", "approve"],
        "training": ["create", "read", "update", "approve"],
        "audit_logs": ["read"],
        "signatures": ["create", "read", "approve"],
    },
    "it_admin": {
        "system_config": ["read", "update"],
        "audit_logs": ["read"],
        "users": ["read"],
    },
    "member": {
        "documents": ["create", "read", "update"],
        "training": ["create", "read", "update"],
        "workflows": ["read"],
        "templates": ["read"],
    },
    "viewer": {
        "documents": ["read"],
        "workflows": ["read"],
        "templates": ["read"],
        "training": ["read"],
    },
}

# Default permission template definitions
DEFAULT_PERMISSION_TEMPLATES: list[dict] = [
    {
        "name": "Internal SOP",
        "description": "Default template for internal Standard Operating Procedures. "
        "Department members can read, doc_admins and system_admins can approve.",
        "document_type": "sop",
        "role_permissions": {
            "system_admin": ["read", "write", "approve"],
            "doc_admin": ["read", "write", "approve"],
            "it_admin": ["read"],
            "member": ["read"],
            "viewer": ["read"],
        },
    },
    {
        "name": "External Supplier File",
        "description": "Default template for external supplier documentation. "
        "Restricted read access, only doc_admins and system_admins can approve.",
        "document_type": "supplier_file",
        "role_permissions": {
            "system_admin": ["read", "write", "approve"],
            "doc_admin": ["read", "write", "approve"],
            "it_admin": [],
            "member": [],
            "viewer": [],
        },
    },
]

# Role name to legacy string mapping for migration
ROLE_NAME_MAPPING: dict[str, str] = {
    "admin": "system_admin",
    "system_admin": "system_admin",
    "doc_admin": "doc_admin",
    "it_admin": "it_admin",
    "member": "member",
    "viewer": "viewer",
}


def upgrade() -> None:
    """Add RBAC schema changes and seed default data.

    Phase 1: Schema changes (roles, permission_templates, company_memberships)
    Phase 2: Data migration (seed roles, map memberships, seed templates)
    """
    # =========================================================================
    # Phase 1: Schema changes
    # =========================================================================

    # --- 1a. Extend roles table ---
    # Add company_id column (nullable for global roles)
    op.add_column(
        "roles",
        sa.Column("company_id", sa.Integer(), nullable=True),
    )
    # Add is_system column
    op.add_column(
        "roles",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    # Add created_at column
    op.add_column(
        "roles",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Add FK constraint for company_id
    op.create_foreign_key(
        "fk_roles_company_id_companies",
        "roles",
        "companies",
        ["company_id"],
        ["id"],
    )

    # Drop old unique index on name (was globally unique)
    op.drop_index("ix_roles_name", table_name="roles")

    # Add new non-unique index on name
    op.create_index("ix_roles_name", "roles", ["name"], unique=False)

    # Add unique constraint on (name, company_id)
    op.create_unique_constraint(
        "uq_roles_name_company", "roles", ["name", "company_id"]
    )

    # Add index on company_id
    op.create_index("ix_roles_company_id", "roles", ["company_id"])

    # --- 1b. Create permission_templates table ---
    op.create_table(
        "permission_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column(
            "role_permissions",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_permission_templates"),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["companies.id"],
            name="fk_permission_templates_company_id_companies",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_permission_templates_created_by_users",
        ),
        sa.UniqueConstraint(
            "name", "company_id", name="uq_permission_templates_name_company"
        ),
    )
    op.create_index(
        "ix_permission_templates_company_id",
        "permission_templates",
        ["company_id"],
    )
    op.create_index(
        "ix_permission_templates_company_doctype",
        "permission_templates",
        ["company_id", "document_type"],
    )

    # --- 1c. Extend company_memberships table ---
    # Add role_id column (nullable during migration)
    op.add_column(
        "company_memberships",
        sa.Column("role_id", sa.Integer(), nullable=True),
    )
    # Add FK constraint for role_id
    op.create_foreign_key(
        "fk_company_memberships_role_id_roles",
        "company_memberships",
        "roles",
        ["role_id"],
        ["id"],
    )
    # Add composite index on (company_id, role_id)
    op.create_index(
        "ix_company_memberships_company_role",
        "company_memberships",
        ["company_id", "role_id"],
    )

    # =========================================================================
    # Phase 2: Data migration
    # =========================================================================

    # --- 2a. Seed five default roles per existing company ---
    # Get connection for data operations
    connection = op.get_bind()

    # Get all existing companies
    companies = connection.execute(
        sa.text("SELECT id FROM companies")
    ).fetchall()

    import json

    for (company_id,) in companies:
        for role_name, permissions in DEFAULT_ROLE_PERMISSIONS.items():
            connection.execute(
                sa.text(
                    "INSERT INTO roles (name, description, permissions, company_id, is_system) "
                    "VALUES (:name, :description, :permissions, :company_id, true) "
                    "ON CONFLICT (name, company_id) DO NOTHING"
                ),
                {
                    "name": role_name,
                    "description": f"System-defined {role_name.replace('_', ' ')} role",
                    "permissions": json.dumps(permissions),
                    "company_id": company_id,
                },
            )

    # --- 2b. Map existing membership role strings to role_id FK ---
    # For each membership, find the matching role in the same company
    for legacy_role, new_role_name in ROLE_NAME_MAPPING.items():
        connection.execute(
            sa.text(
                "UPDATE company_memberships cm "
                "SET role_id = r.id "
                "FROM roles r "
                "WHERE cm.company_id = r.company_id "
                "AND r.name = :new_role_name "
                "AND cm.role = :legacy_role "
                "AND cm.role_id IS NULL"
            ),
            {"new_role_name": new_role_name, "legacy_role": legacy_role},
        )

    # For any remaining unmapped memberships, default to 'member' role
    connection.execute(
        sa.text(
            "UPDATE company_memberships cm "
            "SET role_id = r.id "
            "FROM roles r "
            "WHERE cm.company_id = r.company_id "
            "AND r.name = 'member' "
            "AND cm.role_id IS NULL"
        )
    )

    # --- 2c. Seed default permission templates per company ---
    # Get the first user per company to use as created_by
    for (company_id,) in companies:
        # Find a user in this company to attribute template creation to
        creator_row = connection.execute(
            sa.text(
                "SELECT user_id FROM company_memberships "
                "WHERE company_id = :company_id "
                "ORDER BY id LIMIT 1"
            ),
            {"company_id": company_id},
        ).fetchone()

        # If no members exist, skip seeding for this company
        # (templates will be seeded during setup wizard)
        if not creator_row:
            continue
        creator_id = creator_row[0]

        for template in DEFAULT_PERMISSION_TEMPLATES:
            connection.execute(
                sa.text(
                    "INSERT INTO permission_templates "
                    "(name, description, document_type, role_permissions, "
                    "company_id, is_default, created_by) "
                    "VALUES (:name, :description, :document_type, "
                    ":role_permissions, :company_id, true, :created_by) "
                    "ON CONFLICT (name, company_id) DO NOTHING"
                ),
                {
                    "name": template["name"],
                    "description": template["description"],
                    "document_type": template["document_type"],
                    "role_permissions": json.dumps(template["role_permissions"]),
                    "company_id": company_id,
                    "created_by": creator_id,
                },
            )


def downgrade() -> None:
    """Reverse all RBAC schema changes in dependency order.

    Phase 1: Remove data (templates, role mappings, seeded roles)
    Phase 2: Remove schema changes (company_memberships, permission_templates, roles)
    """
    connection = op.get_bind()

    # =========================================================================
    # Phase 1: Remove seeded data
    # =========================================================================

    # Remove default permission templates
    connection.execute(
        sa.text("DELETE FROM permission_templates WHERE is_default = true")
    )

    # Clear role_id references before removing roles
    connection.execute(
        sa.text("UPDATE company_memberships SET role_id = NULL")
    )

    # Remove seeded system roles
    connection.execute(
        sa.text("DELETE FROM roles WHERE is_system = true")
    )

    # =========================================================================
    # Phase 2: Remove schema changes (reverse order)
    # =========================================================================

    # --- 2a. Revert company_memberships changes ---
    op.drop_index(
        "ix_company_memberships_company_role",
        table_name="company_memberships",
    )
    op.drop_constraint(
        "fk_company_memberships_role_id_roles",
        "company_memberships",
        type_="foreignkey",
    )
    op.drop_column("company_memberships", "role_id")

    # --- 2b. Drop permission_templates table ---
    op.drop_index(
        "ix_permission_templates_company_doctype",
        table_name="permission_templates",
    )
    op.drop_index(
        "ix_permission_templates_company_id",
        table_name="permission_templates",
    )
    op.drop_table("permission_templates")

    # --- 2c. Revert roles table changes ---
    op.drop_index("ix_roles_company_id", table_name="roles")
    op.drop_constraint("uq_roles_name_company", "roles", type_="unique")

    # Drop the non-unique index on name
    op.drop_index("ix_roles_name", table_name="roles")

    # Restore original unique index on name
    op.create_index("ix_roles_name", "roles", ["name"], unique=True)

    op.drop_constraint(
        "fk_roles_company_id_companies", "roles", type_="foreignkey"
    )
    op.drop_column("roles", "created_at")
    op.drop_column("roles", "is_system")
    op.drop_column("roles", "company_id")
