"""User and Role models for authentication and ABAC authorization.

This module defines the User, Role, and UserRole models that support
attribute-based access control (ABAC) for GxP-regulated operations.

References:
    - ABAC: Attribute-Based Access Control for fine-grained permissions
    - CFR 21 Part 11: Electronic records and signatures compliance
"""

from datetime import datetime
from typing import ClassVar

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base

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
    username and email, and can be assigned multiple roles for ABAC
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


class Role(Base):
    """Role model for ABAC permission grouping.

    Roles define sets of permissions that can be assigned to users.
    The permissions field stores a JSON object describing ABAC attributes
    (e.g., allowed document types, workflow actions, SOP scopes).

    Attributes:
        id: Primary key.
        name: Unique role name (e.g., "QA Manager", "Lab Analyst").
        description: Human-readable description of the role's purpose.
        permissions: JSON object containing ABAC permission attributes.
        users: Many-to-many relationship to User via UserRole association.
    """

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)

    users: Mapped[list["User"]] = relationship(
        secondary=UserRole, back_populates="roles"
    )
