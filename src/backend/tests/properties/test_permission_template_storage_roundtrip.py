"""Property-based tests for permission template storage round-trip.

Property 5: Permission Template Storage Round-Trip
For any valid permission template creation payload (name, description,
document_type, role_permissions), creating and then retrieving the template
SHALL return an equivalent object with all fields preserved.

**Validates: Requirements 4.1, 4.2**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import configure_mappers

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.document import Document
from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.models.user import User
from alcoabase.schemas.admin_permission_templates import (
    PermissionTemplateCreateRequest,
    RoleActionMapping,
)
from alcoabase.services.permission_template import PermissionTemplateService

# Ensure sqlalchemy_continuum tables (transaction, *_version) are registered
# in Base.metadata before create_all is called. This is required because
# PermissionTemplate uses AuditMixin which triggers continuum's before_flush hook.
configure_mappers()

# Tables required for this test (avoids creating all tables which may use
# PostgreSQL-specific types like JSONB that SQLite cannot handle)
_REQUIRED_TABLE_NAMES = [
    "users",
    "companies",
    "permission_templates",
    "documents",
    "transaction",
    "permission_templates_version",
]
_REQUIRED_TABLES = [
    Base.metadata.tables[name]
    for name in _REQUIRED_TABLE_NAMES
    if name in Base.metadata.tables
]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VALID_ROLES = ["system_admin", "doc_admin", "it_admin", "member", "viewer"]
VALID_ACTIONS = ["read", "write", "approve"]

# Template name: 1-200 printable characters (no leading/trailing whitespace)
TEMPLATE_NAMES = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=1,
    max_size=100,
).filter(lambda s: len(s.strip()) > 0 and s == s.strip())

# Template description: optional, up to 1000 chars
TEMPLATE_DESCRIPTIONS = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Z"),
            min_codepoint=32,
            max_codepoint=126,
        ),
        min_size=1,
        max_size=200,
    ).filter(lambda s: len(s.strip()) > 0),
)

# Document type: 1-100 printable characters
DOCUMENT_TYPES = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        min_codepoint=48,
        max_codepoint=122,
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: len(s.strip()) > 0 and s == s.strip())


@st.composite
def role_action_mapping(draw: st.DrawFn) -> RoleActionMapping:
    """Generate a valid RoleActionMapping with a role and non-empty action list."""
    role = draw(st.sampled_from(VALID_ROLES))
    actions = draw(
        st.lists(
            st.sampled_from(VALID_ACTIONS),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )
    return RoleActionMapping(role=role, actions=actions)


@st.composite
def template_create_payload(draw: st.DrawFn) -> PermissionTemplateCreateRequest:
    """Generate a valid PermissionTemplateCreateRequest payload.

    Ensures at least one role_permission mapping with unique roles.
    """
    name = draw(TEMPLATE_NAMES)
    description = draw(TEMPLATE_DESCRIPTIONS)
    document_type = draw(DOCUMENT_TYPES)

    # Generate 1-5 role_permissions with unique roles
    num_mappings = draw(st.integers(min_value=1, max_value=5))
    selected_roles = draw(
        st.lists(
            st.sampled_from(VALID_ROLES),
            min_size=num_mappings,
            max_size=num_mappings,
            unique=True,
        )
    )

    role_permissions = []
    for role in selected_roles:
        actions = draw(
            st.lists(
                st.sampled_from(VALID_ACTIONS),
                min_size=1,
                max_size=3,
                unique=True,
            )
        )
        role_permissions.append(RoleActionMapping(role=role, actions=actions))

    return PermissionTemplateCreateRequest(
        name=name,
        description=description,
        document_type=document_type,
        role_permissions=role_permissions,
    )


# ---------------------------------------------------------------------------
# Property 5: Permission Template Storage Round-Trip
# ---------------------------------------------------------------------------


@settings(max_examples=30)
@given(payload=template_create_payload())
@pytest.mark.asyncio
async def test_permission_template_storage_roundtrip(
    payload: PermissionTemplateCreateRequest,
) -> None:
    """For any valid permission template creation payload, creating and then
    retrieving the template SHALL return an equivalent object with all fields
    preserved (name, description, document_type, role_permissions).

    **Validates: Requirements 4.1, 4.2**
    """
    # Set up in-memory async database with only the required tables
    async_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with async_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(
                sync_conn, tables=_REQUIRED_TABLES
            )
        )

    async_session_factory = async_sessionmaker(
        bind=async_engine, class_=AsyncSession, expire_on_commit=False
    )

    company_id = 1
    user_id = 1

    # Seed required foreign key records (company and user)
    async with async_session_factory() as session:
        company = Company(
            id=company_id,
            slug="test-company",
            display_name="Test Company",
            regulatory_framework="ISO_13485",
            is_active=True,
        )
        session.add(company)

        user = User(
            id=user_id,
            username="admin_user",
            email="admin@test.local",
            hashed_password="hashed",
            full_name="Admin User",
            is_active=True,
        )
        session.add(user)
        await session.commit()

    # Create the template via the service
    service = PermissionTemplateService()

    async with async_session_factory() as session:
        created_template = await service.create_template(
            payload=payload,
            company_id=company_id,
            user_id=user_id,
            session=session,
        )
        await session.commit()
        template_id = created_template.id

    # Retrieve the template via the service
    async with async_session_factory() as session:
        retrieved = await service.get_template_detail(
            template_id=template_id,
            company_id=company_id,
            session=session,
        )

    # Verify all fields are preserved in the round-trip
    assert retrieved["name"] == payload.name
    assert retrieved["description"] == payload.description
    assert retrieved["document_type"] == payload.document_type

    # Verify role_permissions are preserved
    expected_role_permissions = {
        mapping.role: sorted(mapping.actions)
        for mapping in payload.role_permissions
    }
    actual_role_permissions = {
        role: sorted(actions)
        for role, actions in retrieved["role_permissions"].items()
    }
    assert actual_role_permissions == expected_role_permissions

    # Verify metadata fields are set correctly
    assert retrieved["id"] == template_id
    assert retrieved["is_default"] is False
    assert retrieved["created_by"] == user_id
    assert retrieved["created_at"] is not None
    assert retrieved["active_document_count"] == 0

    await async_engine.dispose()
