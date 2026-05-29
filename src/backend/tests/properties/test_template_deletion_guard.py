"""Property-based tests for Template Deletion Guard.

Tests Property 6 from the admin-dashboard-user-management design document,
validating that for any permission template with varying active document
counts (0 to N), deletion fails with HTTPException(409) when count > 0
and succeeds when count == 0.

**Validates: Requirements 4.4**

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md (Property 6)
    - Requirements: .kiro/specs/Step_6-1_admin-dashboard-user-management/requirements.md (4.4)
"""

from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from fastapi import HTTPException
from hypothesis import given, settings

from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.services.permission_template import PermissionTemplateService

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOCUMENT_TYPES = ["SOP", "Supplier", "Report", "Protocol", "Manual", "Policy"]
ROLE_NAMES = ["system_admin", "doc_admin", "it_admin", "member", "viewer"]
TEMPLATE_ACTIONS = ["read", "write", "approve"]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_permission_template(draw: st.DrawFn) -> PermissionTemplate:
    """Generate a random PermissionTemplate instance.

    Returns:
        A PermissionTemplate with randomized fields.
    """
    template_id = draw(st.integers(min_value=1, max_value=10000))
    company_id = draw(st.integers(min_value=1, max_value=1000))
    name = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N", "Z"),
    )))
    document_type = draw(st.sampled_from(DOCUMENT_TYPES))

    # Generate role_permissions: random subset of roles with random actions
    included_roles = draw(
        st.lists(
            st.sampled_from(ROLE_NAMES),
            min_size=1,
            max_size=len(ROLE_NAMES),
            unique=True,
        )
    )
    role_permissions = {}
    for role in included_roles:
        actions = draw(
            st.lists(
                st.sampled_from(TEMPLATE_ACTIONS),
                min_size=1,
                max_size=len(TEMPLATE_ACTIONS),
                unique=True,
            )
        )
        role_permissions[role] = actions

    return PermissionTemplate(
        id=template_id,
        name=name,
        description="Test template",
        document_type=document_type,
        role_permissions=role_permissions,
        company_id=company_id,
        is_default=False,
        created_by=1,
    )


@st.composite
def st_active_document_count(draw: st.DrawFn) -> int:
    """Generate a positive active document count (1 to N).

    Returns:
        An integer >= 1 representing active documents using the template.
    """
    return draw(st.integers(min_value=1, max_value=500))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_mock_session_for_delete(
    template: PermissionTemplate,
    active_count: int,
) -> AsyncMock:
    """Build a mock AsyncSession for the delete_template flow.

    The PermissionTemplateService.delete_template calls:
    1. _get_template_or_404: select(PermissionTemplate) → returns template
    2. _get_active_document_count: select(func.count(Document.id)) → returns count

    Args:
        template: The PermissionTemplate to return from the lookup.
        active_count: The active document count to return.

    Returns:
        A configured AsyncMock session.
    """
    session = AsyncMock()

    # Call 1: _get_template_or_404 → select(PermissionTemplate)
    template_result = MagicMock()
    template_result.scalar_one_or_none.return_value = template

    # Call 2: _get_active_document_count → select(func.count(...))
    count_result = MagicMock()
    count_result.scalar_one.return_value = active_count

    session.execute = AsyncMock(side_effect=[template_result, count_result])
    session.delete = AsyncMock()
    session.flush = AsyncMock()

    return session


# ---------------------------------------------------------------------------
# Property 6: Template Deletion Guard
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None)
@given(
    template=st_permission_template(),
    active_count=st_active_document_count(),
)
@pytest.mark.asyncio
async def test_deletion_fails_when_active_documents_exist(
    template: PermissionTemplate,
    active_count: int,
) -> None:
    """For any permission template with active_count > 0, deletion SHALL
    fail with HTTPException(409) and the template SHALL remain unchanged.

    **Validates: Requirements 4.4**
    """
    session = build_mock_session_for_delete(template, active_count)
    service = PermissionTemplateService()

    with pytest.raises(HTTPException) as exc_info:
        await service.delete_template(
            template_id=template.id,
            company_id=template.company_id,
            session=session,
        )

    assert exc_info.value.status_code == 409
    assert "active document" in exc_info.value.detail.lower()

    # Template should NOT have been deleted
    session.delete.assert_not_called()


@settings(max_examples=200, deadline=None)
@given(template=st_permission_template())
@pytest.mark.asyncio
async def test_deletion_succeeds_when_no_active_documents(
    template: PermissionTemplate,
) -> None:
    """For any permission template with active_count == 0, deletion SHALL
    succeed and the template SHALL be removed.

    **Validates: Requirements 4.4**
    """
    session = build_mock_session_for_delete(template, active_count=0)
    service = PermissionTemplateService()

    # Should not raise
    await service.delete_template(
        template_id=template.id,
        company_id=template.company_id,
        session=session,
    )

    # Template should have been deleted
    session.delete.assert_called_once_with(template)
    session.flush.assert_called()


@settings(max_examples=200, deadline=None)
@given(
    template=st_permission_template(),
    active_count=st_active_document_count(),
)
@pytest.mark.asyncio
async def test_deletion_guard_preserves_template_state(
    template: PermissionTemplate,
    active_count: int,
) -> None:
    """When deletion is blocked by active documents, the template's fields
    SHALL remain unchanged (no side effects on the template object).

    **Validates: Requirements 4.4**
    """
    # Capture original state
    original_name = template.name
    original_document_type = template.document_type
    original_role_permissions = dict(template.role_permissions)
    original_company_id = template.company_id

    session = build_mock_session_for_delete(template, active_count)
    service = PermissionTemplateService()

    with pytest.raises(HTTPException):
        await service.delete_template(
            template_id=template.id,
            company_id=template.company_id,
            session=session,
        )

    # Verify template state is unchanged
    assert template.name == original_name
    assert template.document_type == original_document_type
    assert template.role_permissions == original_role_permissions
    assert template.company_id == original_company_id
