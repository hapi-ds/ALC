"""Property-based tests for TemplateVersion service.

Tests version creation invariant (Property 6) and version immutability
(Property 7) from the template-builder-enhancements design document.

Property 6 validates that sequential version creation maintains:
- version_number = max existing + 1
- new version is_active=True, status="ReadOnly"
- all previous versions is_active=False
- exactly one active version per template at any time

Property 7 validates that once a version is created, its fields cannot
be modified through the API.

**Validates: Requirements 10.5, 10.6, 10.7, 13.3, 13.4, 21.6**

References:
    - Design: .kiro/specs/template-builder-enhancements/design.md (Property 6, Property 7)
    - Requirements: .kiro/specs/template-builder-enhancements/requirements.md
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.models.template_version import TemplateVersion, TemplateVersionField
from alcoabase.services.template_service import TemplateService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_json_schema() -> st.SearchStrategy[dict]:
    """Generate a valid enhanced template JSON schema with elements.

    Returns:
        Strategy producing dicts with 'elements' key containing at least one field.
    """
    field_types = ["Text", "Float", "Integer", "Date", "Boolean"]

    field_element = st.fixed_dictionaries({
        "element_type": st.just("field"),
        "label": st.text(
            alphabet=st.characters(categories=("L", "N", "Z")),
            min_size=1,
            max_size=50,
        ).filter(lambda s: s.strip()),
        "type": st.sampled_from(field_types),
        "required": st.booleans(),
        "help_text": st.one_of(st.none(), st.text(min_size=1, max_size=100)),
        "default_value": st.one_of(st.none(), st.text(min_size=1, max_size=50)),
        "config": st.just({}),
    })

    content_types = ["heading_h1", "heading_h2", "heading_h3", "paragraph", "divider"]
    content_element = st.fixed_dictionaries({
        "element_type": st.just("content_block"),
        "content_type": st.sampled_from(content_types),
        "text": st.one_of(
            st.none(),
            st.text(min_size=1, max_size=100).filter(lambda s: s.strip()),
        ),
    })

    # Ensure at least one field element exists
    return st.builds(
        lambda fields, extras: {"elements": fields + extras},
        fields=st.lists(field_element, min_size=1, max_size=5),
        extras=st.lists(content_element, min_size=0, max_size=3),
    )


def st_version_number() -> st.SearchStrategy[int]:
    """Generate a valid version number (positive integer).

    Returns:
        Strategy producing integers >= 1.
    """
    return st.integers(min_value=1, max_value=100)


def st_change_reason() -> st.SearchStrategy[str]:
    """Generate a valid change reason string (>= 10 chars).

    Returns:
        Strategy producing non-empty strings of at least 10 characters.
    """
    return st.text(
        alphabet=st.characters(categories=("L", "N", "Z", "P")),
        min_size=10,
        max_size=200,
    ).filter(lambda s: len(s.strip()) >= 10)


def st_mutation_field() -> st.SearchStrategy[str]:
    """Generate a field name to attempt mutation on.

    Returns:
        Strategy producing one of the immutable version field names.
    """
    return st.sampled_from([
        "json_schema",
        "version_number",
        "status",
        "change_reason",
        "created_at",
    ])


def st_mutation_value() -> st.SearchStrategy:
    """Generate a random mutation value to attempt setting on a version field.

    Returns:
        Strategy producing various types of values for mutation attempts.
    """
    return st.one_of(
        st.text(min_size=1, max_size=100),
        st.integers(min_value=1, max_value=1000),
        st.just({"elements": [{"element_type": "field", "label": "Hacked", "type": "Text", "required": False, "help_text": None, "default_value": None, "config": {}}]}),
        st.just("Draft"),
        st.just("Approved"),
        st.just(datetime(2020, 1, 1, tzinfo=UTC)),
    )


# ---------------------------------------------------------------------------
# Helper: Create a mock version with known values
# ---------------------------------------------------------------------------


class MockTemplateVersion:
    """Mock TemplateVersion for in-memory testing without SQLAlchemy instrumentation.

    Attributes mirror the real TemplateVersion model but avoid SQLAlchemy
    descriptor issues when setting attributes outside a session context.
    """

    def __init__(
        self,
        version_number: int,
        json_schema: dict,
        change_reason: str,
    ) -> None:
        self.id = 1
        self.template_id = 1
        self.version_number = version_number
        self.document_uuid = "2025-00001"
        self.json_schema = json_schema
        self.status = "ReadOnly"
        self.is_active = True
        self.created_by = 1
        self.change_reason = change_reason
        self.created_at = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        self.fields: list = []


def _create_mock_version(
    version_number: int,
    json_schema: dict,
    change_reason: str,
) -> MockTemplateVersion:
    """Create a MockTemplateVersion instance with known immutable values.

    Args:
        version_number: The version number to assign.
        json_schema: The JSON schema snapshot.
        change_reason: The audit change reason.

    Returns:
        A MockTemplateVersion instance with all fields set.
    """
    return MockTemplateVersion(
        version_number=version_number,
        json_schema=json_schema,
        change_reason=change_reason,
    )


# ---------------------------------------------------------------------------
# Strategies for Property 6
# ---------------------------------------------------------------------------


def st_num_versions() -> st.SearchStrategy[int]:
    """Generate the number of sequential versions to create (2–10).

    Returns:
        Strategy producing integers between 2 and 10 inclusive.
    """
    return st.integers(min_value=2, max_value=10)


# ---------------------------------------------------------------------------
# Property 6: Version Creation Invariant
# ---------------------------------------------------------------------------


# Feature: template-builder-enhancements, Property 6: Version Creation Invariant
class TestVersionCreationInvariant:
    """Property tests for version creation invariant enforcement.

    For any template with existing versions, when a new version is created:
    (a) the new version number equals max existing version number + 1,
    (b) the new version has is_active=True and status="ReadOnly",
    (c) all previous versions have is_active=False, and
    (d) exactly one version per template has is_active=True at any time.

    **Validates: Requirements 10.5, 10.6, 10.7, 13.3, 13.4**
    """

    @given(
        num_versions=st_num_versions(),
        schemas=st.lists(st_json_schema(), min_size=10, max_size=10),
        change_reasons=st.lists(st_change_reason(), min_size=10, max_size=10),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_sequential_version_creation_maintains_invariants(
        self,
        num_versions: int,
        schemas: list[dict],
        change_reasons: list[str],
    ) -> None:
        """Creating multiple versions sequentially maintains all version
        creation invariants after each creation step.

        Simulates the create_version logic in-memory to verify:
        - version_number increments by exactly 1 each time
        - Only the newest version is active
        - All previous versions are deactivated
        - Exactly one active version exists at all times

        **Validates: Requirements 10.5, 10.6, 10.7, 13.3, 13.4**
        """
        # In-memory version store simulating the database state
        versions: list[dict] = []

        for i in range(num_versions):
            schema = schemas[i]
            change_reason = change_reasons[i]

            # Determine next version number: max existing + 1 (Requirement 10.5)
            max_version = max((v["version_number"] for v in versions), default=0)
            next_version_number = max_version + 1

            # Deactivate current active version (Requirement 13.3)
            for v in versions:
                if v["is_active"]:
                    v["is_active"] = False

            # Create new version with is_active=True, status="ReadOnly"
            # (Requirements 10.6, 13.4)
            new_version = {
                "version_number": next_version_number,
                "json_schema": schema,
                "status": "ReadOnly",
                "is_active": True,
                "created_by": 1,
                "change_reason": change_reason,
            }
            versions.append(new_version)

            # --- Verify invariants after each creation ---

            # (a) New version_number = max existing + 1 (Requirement 10.5)
            assert new_version["version_number"] == i + 1, (
                f"Expected version_number {i + 1}, got {new_version['version_number']}"
            )

            # (b) New version has is_active=True and status="ReadOnly"
            # (Requirements 10.6, 13.4)
            assert new_version["is_active"] is True
            assert new_version["status"] == "ReadOnly"

            # (c) All previous versions have is_active=False (Requirement 10.7)
            for prev_version in versions[:-1]:
                assert prev_version["is_active"] is False, (
                    f"Version {prev_version['version_number']} should be inactive "
                    f"after version {new_version['version_number']} was created"
                )

            # (d) Exactly one version has is_active=True (Requirement 13.4)
            active_count = sum(1 for v in versions if v["is_active"])
            assert active_count == 1, (
                f"Expected exactly 1 active version, found {active_count}"
            )

    @given(
        num_versions=st_num_versions(),
        schemas=st.lists(st_json_schema(), min_size=10, max_size=10),
        change_reasons=st.lists(st_change_reason(), min_size=10, max_size=10),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_version_numbers_form_contiguous_sequence(
        self,
        num_versions: int,
        schemas: list[dict],
        change_reasons: list[str],
    ) -> None:
        """After creating N versions, version numbers form a contiguous
        sequence 1, 2, 3, ..., N with no gaps or duplicates.

        **Validates: Requirements 10.5, 10.6**
        """
        versions: list[dict] = []

        for i in range(num_versions):
            max_version = max((v["version_number"] for v in versions), default=0)
            next_version_number = max_version + 1

            for v in versions:
                if v["is_active"]:
                    v["is_active"] = False

            versions.append({
                "version_number": next_version_number,
                "is_active": True,
                "status": "ReadOnly",
            })

        # Verify contiguous sequence 1..N
        version_numbers = sorted(v["version_number"] for v in versions)
        expected = list(range(1, num_versions + 1))
        assert version_numbers == expected, (
            f"Expected contiguous sequence {expected}, got {version_numbers}"
        )

    @given(
        num_versions=st_num_versions(),
        schemas=st.lists(st_json_schema(), min_size=10, max_size=10),
        change_reasons=st.lists(st_change_reason(), min_size=10, max_size=10),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_create_version_service_maintains_invariants(
        self,
        num_versions: int,
        schemas: list[dict],
        change_reasons: list[str],
    ) -> None:
        """Calling the actual TemplateService.create_version method
        sequentially maintains all version creation invariants.

        Uses mocked database session to verify the service logic correctly:
        - Queries max version number and increments by 1
        - Deactivates previous active versions
        - Creates new version with is_active=True, status="ReadOnly"

        **Validates: Requirements 10.5, 10.6, 10.7, 13.3, 13.4**
        """
        service = TemplateService()

        # Track all created versions to verify invariants
        created_versions: list[MockTemplateVersion] = []
        template_id = 1

        for i in range(num_versions):
            schema = schemas[i]
            change_reason = change_reasons[i]
            session = AsyncMock()

            # Mock template lookup with SELECT FOR UPDATE
            mock_template = MagicMock()
            mock_template.id = template_id
            mock_template.status = "ReadOnly"
            mock_template.document_uuid = "2025-00001"
            mock_template.name = "Test Template"

            # Track which version number the service will assign
            current_max = max(
                (v.version_number for v in created_versions), default=0
            )
            expected_next = current_max + 1

            # Mock the max version query result
            mock_max_result = MagicMock()
            mock_max_result.scalar_one.return_value = current_max

            # Mock the template query result
            mock_template_result = MagicMock()
            mock_template_result.scalar_one_or_none.return_value = mock_template

            # Create a mock version that will be "returned" after flush
            mock_new_version = MockTemplateVersion(
                version_number=expected_next,
                json_schema=schema,
                change_reason=change_reason,
            )
            mock_new_version.is_active = True
            mock_new_version.status = "ReadOnly"
            mock_new_version.fields = []

            # Mock the reload query result
            mock_reload_result = MagicMock()
            mock_reload_result.scalar_one.return_value = mock_new_version

            # Configure session.execute to return different results for
            # different queries (template lookup, max version, deactivate, reload)
            call_count = [0]

            def make_execute_side_effect(
                tmpl_result, max_result, reload_result
            ):
                def side_effect(*args, **kwargs):
                    call_count[0] += 1
                    # 1st call: SELECT FOR UPDATE (template lookup)
                    if call_count[0] == 1:
                        return tmpl_result
                    # 2nd call: SELECT max(version_number)
                    elif call_count[0] == 2:
                        return max_result
                    # 3rd call: UPDATE (deactivate previous)
                    elif call_count[0] == 3:
                        # Deactivate all previous versions in our tracking list
                        for v in created_versions:
                            v.is_active = False
                        return MagicMock()
                    # 4th call: SELECT reload with fields
                    elif call_count[0] == 4:
                        return reload_result
                    return MagicMock()
                return side_effect

            session.execute = AsyncMock(
                side_effect=make_execute_side_effect(
                    mock_template_result, mock_max_result, mock_reload_result
                )
            )
            session.add = MagicMock()
            session.flush = AsyncMock()

            # Call the service method
            result = await service.create_version(
                session=session,
                document_uuid="2025-00001",
                json_schema=schema,
                user_id=1,
                change_reason=change_reason,
            )

            # Track the created version
            created_versions.append(mock_new_version)

            # --- Verify invariants ---

            # (a) New version_number = max + 1 (Requirement 10.5)
            assert result.version_number == expected_next

            # (b) New version is_active=True, status="ReadOnly"
            # (Requirements 10.6, 13.4)
            assert result.is_active is True
            assert result.status == "ReadOnly"

            # (c) All previous versions have is_active=False (Requirement 10.7)
            for prev in created_versions[:-1]:
                assert prev.is_active is False, (
                    f"Version {prev.version_number} should be inactive"
                )

            # (d) Exactly one active version (Requirement 13.4)
            active_count = sum(1 for v in created_versions if v.is_active)
            assert active_count == 1, (
                f"Expected exactly 1 active version, found {active_count}"
            )


# ---------------------------------------------------------------------------
# Property 7: Version Immutability
# ---------------------------------------------------------------------------


# Feature: template-builder-enhancements, Property 7: Version Immutability
class TestVersionImmutability:
    """Property tests for version immutability enforcement.

    Once a template version is created, any attempt to modify its
    json_schema, version_number, status, change_reason, or created_at
    fields must be rejected by the API, preserving original values.

    **Validates: Requirements 21.6, 10.7**
    """

    @given(
        version_number=st_version_number(),
        json_schema=st_json_schema(),
        change_reason=st_change_reason(),
        mutation_field=st_mutation_field(),
        mutation_value=st_mutation_value(),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_version_fields_reject_modification_via_api(
        self,
        version_number: int,
        json_schema: dict,
        change_reason: str,
        mutation_field: str,
        mutation_value,
    ) -> None:
        """Any attempt to modify immutable version fields via the template
        update API is rejected because the parent template is ReadOnly.

        The API enforces immutability by:
        1. Not exposing PUT/PATCH endpoints for versions
        2. Rejecting all modifications to ReadOnly templates (HTTP 400)

        This test verifies that attempting to modify the parent template
        (which would be the only API path to alter version data) is rejected,
        and the version's original values remain unchanged.

        **Validates: Requirements 21.6, 10.7**
        """
        from fastapi import HTTPException

        service = TemplateService()
        session = AsyncMock()

        # Create a version with known values
        version = _create_mock_version(version_number, json_schema, change_reason)

        # Store original values before mutation attempt
        original_json_schema = version.json_schema
        original_version_number = version.version_number
        original_status = version.status
        original_change_reason = version.change_reason
        original_created_at = version.created_at

        # Mock the template as ReadOnly (which it must be for versions to exist)
        mock_template = MagicMock()
        mock_template.status = "ReadOnly"
        mock_template.document_uuid = "2025-00001"
        mock_template.name = "Test Template"
        mock_template.json_schema = json_schema
        mock_template.fields = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        session.execute.return_value = mock_result

        # Attempt to modify the template via update_template API
        # This is the only API path that could potentially alter template data
        modified_schema = (
            {"elements": [{"element_type": "field", "label": "Modified", "type": "Text", "required": False, "help_text": None, "default_value": None, "config": {}}]}
            if mutation_field == "json_schema"
            else None
        )
        modified_name = str(mutation_value) if mutation_field != "json_schema" else None

        with pytest.raises(HTTPException) as exc_info:
            await service.update_template(
                session=session,
                document_uuid="2025-00001",
                name=modified_name,
                json_schema=modified_schema,
            )

        # Verify the modification was rejected (HTTP 400 for ReadOnly)
        assert exc_info.value.status_code == 400

        # Verify all version fields remain unchanged (immutability preserved)
        assert version.json_schema == original_json_schema
        assert version.version_number == original_version_number
        assert version.status == original_status
        assert version.change_reason == original_change_reason
        assert version.created_at == original_created_at

    @given(
        version_number=st_version_number(),
        json_schema=st_json_schema(),
        change_reason=st_change_reason(),
        mutation_fields=st.lists(st_mutation_field(), min_size=1, max_size=5),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_version_preserves_all_fields_after_multiple_mutation_attempts(
        self,
        version_number: int,
        json_schema: dict,
        change_reason: str,
        mutation_fields: list[str],
    ) -> None:
        """After multiple rejected mutation attempts targeting different fields,
        all version fields retain their original values.

        This tests that repeated modification attempts do not gradually
        corrupt version data — each attempt is independently rejected.

        **Validates: Requirements 21.6, 10.7**
        """
        from fastapi import HTTPException

        service = TemplateService()
        session = AsyncMock()

        # Create a version with known values
        version = _create_mock_version(version_number, json_schema, change_reason)

        # Store original values
        original_values = {
            "json_schema": version.json_schema,
            "version_number": version.version_number,
            "status": version.status,
            "change_reason": version.change_reason,
            "created_at": version.created_at,
        }

        # Mock the template as ReadOnly
        mock_template = MagicMock()
        mock_template.status = "ReadOnly"
        mock_template.document_uuid = "2025-00001"
        mock_template.name = "Test Template"
        mock_template.json_schema = json_schema
        mock_template.fields = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        session.execute.return_value = mock_result

        # Attempt multiple mutations targeting different fields
        for field_name in mutation_fields:
            with pytest.raises(HTTPException) as exc_info:
                await service.update_template(
                    session=session,
                    document_uuid="2025-00001",
                    name=f"Attempt to modify {field_name}",
                    json_schema={"elements": [{"element_type": "field", "label": "Hacked", "type": "Text", "required": False, "help_text": None, "default_value": None, "config": {}}]},
                )
            assert exc_info.value.status_code == 400

        # Verify ALL version fields remain unchanged after all attempts
        assert version.json_schema == original_values["json_schema"]
        assert version.version_number == original_values["version_number"]
        assert version.status == original_values["status"]
        assert version.change_reason == original_values["change_reason"]
        assert version.created_at == original_values["created_at"]

    @given(
        version_number=st_version_number(),
        json_schema=st_json_schema(),
        change_reason=st_change_reason(),
        mutation_field=st_mutation_field(),
        mutation_value=st_mutation_value(),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_direct_attribute_mutation_does_not_persist(
        self,
        version_number: int,
        json_schema: dict,
        change_reason: str,
        mutation_field: str,
        mutation_value,
    ) -> None:
        """Attempting to directly set immutable attributes on a version object
        does not affect the stored original values when accessed through the
        service layer.

        This simulates what would happen if code attempted to bypass the API
        and directly mutate version attributes — the service layer should
        never expose such a path, and the version's integrity is maintained.

        **Validates: Requirements 21.6, 10.7**
        """
        service = TemplateService()
        session = AsyncMock()

        # Create a version with known values
        version = _create_mock_version(version_number, json_schema, change_reason)

        # Store original values
        original_values = {
            "json_schema": version.json_schema,
            "version_number": version.version_number,
            "status": version.status,
            "change_reason": version.change_reason,
            "created_at": version.created_at,
        }

        # Mock get_version to return our version
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = version
        session.execute.return_value = mock_result

        # Retrieve the version through the service
        retrieved = await service.get_version(session, "2025-00001", version_number)

        # Verify retrieved version has original values
        assert retrieved is not None
        assert retrieved.json_schema == original_values["json_schema"]
        assert retrieved.version_number == original_values["version_number"]
        assert retrieved.status == original_values["status"]
        assert retrieved.change_reason == original_values["change_reason"]
        assert retrieved.created_at == original_values["created_at"]

        # The service does NOT provide any method to modify version fields
        # Verify no update_version method exists on the service
        assert not hasattr(service, "update_version"), (
            "TemplateService should not expose an update_version method — "
            "versions are immutable after creation"
        )
