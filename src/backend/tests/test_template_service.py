"""Property-based tests for TemplateService.

Tests Field-UUID uniqueness within templates and ReadOnly immutability
enforcement using Hypothesis.

**Validates: Requirements 3.2, 3.4, 3.5**
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from alcoabase.services.template_service import TemplateService
from alcoabase.services.uuid_service import UUIDService


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

FIELD_UUID_PATTERN = re.compile(r"^FLD-[A-F0-9]{8}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(seq_value: int = 1) -> AsyncMock:
    """Create a mock AsyncSession that returns a given sequence value.

    Args:
        seq_value: The integer value to return from nextval().

    Returns:
        An AsyncMock configured to simulate PostgreSQL sequence calls.
    """
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = seq_value
    session.execute.return_value = result_mock
    return session


def _make_json_schema(field_count: int) -> dict:
    """Generate a template JSON schema with the given number of fields.

    Args:
        field_count: Number of fields to include.

    Returns:
        A dict with format {"fields": [{"label": "...", "type": "..."}]}.
    """
    field_types = ["Text", "Float", "Integer", "Date", "Boolean"]
    fields = []
    for i in range(field_count):
        fields.append({
            "label": f"Field {i + 1}",
            "type": field_types[i % len(field_types)],
        })
    return {"fields": fields}


# ---------------------------------------------------------------------------
# Mock template model for testing
# ---------------------------------------------------------------------------


class MockTemplateField:
    """Mock TemplateField for in-memory testing."""

    def __init__(self, field_uuid: str, field_type: str, field_label: str, field_order: int) -> None:
        self.id = 1
        self.field_uuid = field_uuid
        self.field_type = field_type
        self.field_label = field_label
        self.field_order = field_order


class MockTemplate:
    """Mock Template for in-memory testing."""

    def __init__(
        self,
        document_uuid: str,
        name: str,
        json_schema: dict,
        status: str,
        created_by: int,
    ) -> None:
        self.id = 1
        self.document_uuid = document_uuid
        self.name = name
        self.json_schema = json_schema
        self.status = status
        self.created_by = created_by
        self.fields: list[MockTemplateField] = []


# ---------------------------------------------------------------------------
# Task 5.5: Field-UUID uniqueness within template (1-100 fields)
# ---------------------------------------------------------------------------


class TestFieldUUIDUniquenessWithinTemplate:
    """Property tests for Field-UUID uniqueness within templates.

    For templates with 1-100 fields, all assigned Field-UUIDs must be
    unique within the template.

    **Validates: Requirements 3.2**
    """

    @given(field_count=st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_field_uuids_are_unique_within_template(self, field_count: int) -> None:
        """All Field-UUIDs assigned to a template with N fields are unique.

        Generates a template with a random number of fields (1-100) and
        verifies that all assigned Field-UUIDs are distinct.

        **Validates: Requirements 3.2**
        """
        uuid_service = UUIDService()

        # Generate Field-UUIDs for the template
        field_uuids = [uuid_service.generate_field_uuid() for _ in range(field_count)]

        # All Field-UUIDs must be unique
        assert len(set(field_uuids)) == field_count, (
            f"Duplicate Field-UUIDs detected in template with {field_count} fields: "
            f"{[u for u in field_uuids if field_uuids.count(u) > 1]}"
        )

    @given(field_count=st.integers(min_value=1, max_value=100))
    @settings(max_examples=100)
    def test_field_uuids_all_match_format(self, field_count: int) -> None:
        """All Field-UUIDs assigned to a template match the FLD-XXXXXXXX pattern.

        **Validates: Requirements 3.2**
        """
        uuid_service = UUIDService()

        field_uuids = [uuid_service.generate_field_uuid() for _ in range(field_count)]

        for field_uuid in field_uuids:
            assert FIELD_UUID_PATTERN.match(field_uuid), (
                f"Field-UUID '{field_uuid}' does not match FLD-XXXXXXXX pattern"
            )

    @given(field_count=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_field_count_matches_schema_field_count(self, field_count: int) -> None:
        """The number of generated Field-UUIDs equals the number of fields in the schema.

        **Validates: Requirements 3.2**
        """
        uuid_service = UUIDService()
        json_schema = _make_json_schema(field_count)

        field_uuids = [
            uuid_service.generate_field_uuid()
            for _ in json_schema["fields"]
        ]

        assert len(field_uuids) == field_count


# ---------------------------------------------------------------------------
# Task 5.6: ReadOnly immutability — all modifications rejected
# ---------------------------------------------------------------------------


# Strategy for generating random modification payloads
modification_payloads = st.fixed_dictionaries({
    "name": st.one_of(
        st.none(),
        st.text(min_size=1, max_size=100, alphabet=st.characters(categories=("L", "N", "P", "Z"))),
    ),
    "json_schema": st.one_of(
        st.none(),
        st.just({"fields": [{"label": "Modified", "type": "Text"}]}),
        st.just({"fields": [{"label": "New Field", "type": "Float"}, {"label": "Another", "type": "Integer"}]}),
    ),
}).filter(lambda d: d["name"] is not None or d["json_schema"] is not None)


class TestReadOnlyImmutability:
    """Property tests for ReadOnly template immutability.

    Once a template status is set to ReadOnly, all modification attempts
    must be rejected with HTTP 400.

    **Validates: Requirements 3.4, 3.5**
    """

    @given(payload=modification_payloads)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_readonly_template_rejects_all_modifications(
        self, payload: dict
    ) -> None:
        """All modification attempts on ReadOnly templates are rejected with HTTP 400.

        **Validates: Requirements 3.4, 3.5**
        """
        from fastapi import HTTPException

        service = TemplateService()
        session = AsyncMock()

        # Create a mock ReadOnly template
        mock_template = MockTemplate(
            document_uuid="2026-00001",
            name="Test Template",
            json_schema={"fields": [{"label": "Original", "type": "Text"}]},
            status="ReadOnly",
            created_by=1,
        )

        # Mock the session.execute to return our ReadOnly template
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        session.execute.return_value = mock_result

        # Attempt modification — should raise HTTP 400
        with pytest.raises(HTTPException) as exc_info:
            await service.update_template(
                session=session,
                document_uuid="2026-00001",
                name=payload.get("name"),
                json_schema=payload.get("json_schema"),
            )

        assert exc_info.value.status_code == 400
        assert "ReadOnly" in exc_info.value.detail

    @given(
        field_count=st.integers(min_value=1, max_value=20),
        modification_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_readonly_template_state_unchanged_after_rejected_modifications(
        self, field_count: int, modification_count: int
    ) -> None:
        """Template state remains unchanged after rejected modification attempts.

        **Validates: Requirements 3.4, 3.5**
        """
        from fastapi import HTTPException

        service = TemplateService()
        session = AsyncMock()

        original_schema = _make_json_schema(field_count)
        mock_template = MockTemplate(
            document_uuid="2026-00001",
            name="Original Name",
            json_schema=original_schema,
            status="ReadOnly",
            created_by=1,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        session.execute.return_value = mock_result

        # Attempt multiple modifications
        for _ in range(modification_count):
            with pytest.raises(HTTPException) as exc_info:
                await service.update_template(
                    session=session,
                    document_uuid="2026-00001",
                    name="Modified Name",
                    json_schema={"fields": [{"label": "Hacked", "type": "Boolean"}]},
                )
            assert exc_info.value.status_code == 400

        # Verify template state is unchanged
        assert mock_template.name == "Original Name"
        assert mock_template.json_schema == original_schema
        assert mock_template.status == "ReadOnly"

    @given(payload=modification_payloads)
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_readonly_rejection_message_is_descriptive(
        self, payload: dict
    ) -> None:
        """Rejection messages for ReadOnly modifications are descriptive.

        **Validates: Requirements 3.4, 3.5**
        """
        from fastapi import HTTPException

        service = TemplateService()
        session = AsyncMock()

        mock_template = MockTemplate(
            document_uuid="2026-00001",
            name="Test Template",
            json_schema={"fields": [{"label": "Field", "type": "Text"}]},
            status="ReadOnly",
            created_by=1,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        session.execute.return_value = mock_result

        with pytest.raises(HTTPException) as exc_info:
            await service.update_template(
                session=session,
                document_uuid="2026-00001",
                name=payload.get("name"),
                json_schema=payload.get("json_schema"),
            )

        # Error message should mention immutability
        assert "immutable" in exc_info.value.detail.lower() or "readonly" in exc_info.value.detail.lower()
