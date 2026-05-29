"""User and Role models for authentication and RBAC authorization.

This module defines the User, Role, and UserRole models that support
Role-Based Access Control (RBAC) for GxP-regulated operations.

Phase 6.1 extends the Role model with company scoping and system role
flags to support granular RBAC with five specialized roles.

References:
    - RBAC: Role-Based Access Control for fine-grained permissions
    - CFR 21 Part 11: Electronic records and signatures compliance
"""

from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company

# Many-to-many association table for User <-> Role
UserRole = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id"), primary_key=True),
)


class User(Base):
    """User account model for authentication and identity tracking.

    Users are the primary actors in the system. Each user has a unique
    username and email, and can be assigned multiple roles for RBAC
    permission evaluation.

    Attributes:
        id: Primary key.
        username: Unique login identifier.
        email: Unique email address.
        hashed_password: Bcrypt-hashed password (never stored in plaintext).
        full_name: Display name for audit trail attribution.
        is_active: Whether the account is enabled.
        is_csv_test_user: Whether this is a CSV Runner test user (excluded
            from production audit trails).
        created_at: Server-side UTC timestamp of account creation.
        roles: Many-to-many relationship to Role via UserRole association.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_csv_test_user: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    roles: Mapped[list["Role"]] = relationship(
        secondary=UserRole, back_populates="users"
    )


class Role(Base, AuditMixin):
    """Role model for RBAC permission grouping.

    Roles define sets of permissions that can be assigned to users.
    The permissions field stores a structured JSON object mapping
    resource types to allowed actions:
    {
        "documents": ["create", "read", "update", "delete", "approve"],
        "workflows": ["read", "approve"],
        ...
    }

    Extended for Phase 6.1 with company scoping and system role flag.
    System roles (is_system=True) are non-editable defaults provisioned
    per company. Company-scoped roles (company_id != NULL) are isolated
    to a single tenant.

    Attributes:
        id: Primary key.
        name: Role name (unique within a company scope).
        description: Human-readable description of the role's purpose.
        permissions: JSON object mapping resource types to allowed actions.
        company_id: FK to company (NULL for global system roles).
        is_system: Whether this is a system-defined non-editable role.
        created_at: Server-side UTC timestamp.
        users: Many-to-many relationship to User via UserRole association.
        company: Relationship to the Company model.
    """

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("name", "company_id", name="uq_roles_name_company"),
        Index("ix_roles_company_id", "company_id"),
    )
    __versioned__: ClassVar[dict] = {
        "exclude": ["is_csv_validation_record", "users"],
    }

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    is_system: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    users: Mapped[list["User"]] = relationship(
        secondary=UserRole, back_populates="roles"
    )
    company: Mapped["Company | None"] = relationship()
