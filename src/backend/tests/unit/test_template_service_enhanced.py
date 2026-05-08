"""Unit tests for enhanced template creation with elements format.

Tests the TemplateService.create_template method with the enhanced
elements format including field configs, content blocks, and
backward compatibility with the legacy fields format.

References:
    - Requirements 18.6, 18.7: Enhanced template creation
    - Requirements 1.7, 7.7, 8.7, 9.5: Serialization of elements
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.services.template_service import TemplateService
from alcoabase.services.uuid_service import UUIDService


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

FIELD_UUID_PATTERN = re.compile(r"^FLD-[A-F0-9]{8}$")
CB_UUID_PATTERN = re.compile(r"^CB-[A-F0-9]{8}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(seq_value: int = 1) -> AsyncMock:
    """Create a mock AsyncSession that simulates PostgreSQL sequence calls.

    The mock handles:
    - CREATE SEQUENCE IF NOT EXISTS (returns None)
    - SELECT nextval (returns seq_value)
    - session.add (no-op)
    - session.flush (no-op)
    - session.execute for SELECT with selectinload (returns mock template)
    """
    session = AsyncMock()

    # Track added objects
    added_objects: list = []

    def track_add(obj: object) -> None:
        added_objects.append(obj)
        # Assign a fake id for template objects
        if hasattr(obj, "id") and obj.id is None:
            obj.id = 1

    session.add.side_effect = track_add
    session._added_objects = added_objects

    # Mock execute to handle different query types
    call_count = {"value": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_count["value"] += 1
        result_mock = MagicMock()

        # First two calls are for UUID generation (CREATE SEQUENCE + nextval)
        if call_count["value"] <= 2:
            result_mock.scalar_one.return_value = seq_value
            return result_mock

        # Last call is for reloading the template
        # Return a mock template with fields
        template_mock = MagicMock()
        template_mock.id = 1
        template_mock.document_uuid = f"2026-{seq_value:05d}"
        template_mock.name = "Test"
        template_mock.status = "ReadOnly"
        template_mock.fields = added_objects[1:]  # Skip the template itself
        result_mock.scalar_one.return_value = template_mock
        return result_mock

    session.execute = mock_execute
    return session


def _make_enhanced_schema(
    fields: list[dict] | None = None,
    content_blocks: list[dict] | None = None,
) -> dict:
    """Build an enhanced schema with elements array.

    Args:
        fields: List of field element dicts.
        content_blocks: List of content block element dicts.

    Returns:
        Schema dict with {"elements": [...]}.
    """
    elements = []
    if content_blocks:
        elements.extend(content_blocks)
    if fields:
        elements.extend(fields)
    return {"elements": elements}


# ---------------------------------------------------------------------------
# Tests: Format Detection
# ---------------------------------------------------------------------------


class TestFormatDetection:
    """Tests for automatic format detection in create_template."""

    @pytest.mark.asyncio
    async def test_detects_legacy_format(self) -> None:
        """Legacy format with 'fields' key is handled correctly."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {"fields": [{"label": "Name", "type": "Text"}]}
        result = await service.create_template(session, "Test", schema, 1)

        assert result is not None

    @pytest.mark.asyncio
    async def test_detects_enhanced_format(self) -> None:
        """Enhanced format with 'elements' key is handled correctly."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Name",
                    "type": "Text",
                    "required": False,
                    "help_text": None,
                    "default_value": None,
                    "config": None,
                }
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)

        assert result is not None

    @pytest.mark.asyncio
    async def test_rejects_missing_both_keys(self) -> None:
        """Schema without 'fields' or 'elements' raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        with pytest.raises(ValueError, match="'elements' key.*'fields' key"):
            await service.create_template(session, "Test", {}, 1)

    @pytest.mark.asyncio
    async def test_rejects_non_dict_schema(self) -> None:
        """Non-dict json_schema raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        with pytest.raises(ValueError, match="must be a dict"):
            await service.create_template(session, "Test", "invalid", 1)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests: Enhanced Format — Validation
# ---------------------------------------------------------------------------


class TestEnhancedValidation:
    """Tests for validation in the enhanced elements format."""

    @pytest.mark.asyncio
    async def test_rejects_empty_elements(self) -> None:
        """Empty elements array raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        with pytest.raises(ValueError, match="non-empty list"):
            await service.create_template(
                session, "Test", {"elements": []}, 1
            )

    @pytest.mark.asyncio
    async def test_rejects_only_content_blocks(self) -> None:
        """Schema with only content blocks (no fields) raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "content_block",
                    "content_type": "heading_h1",
                    "text": "Section 1",
                },
                {
                    "element_type": "content_block",
                    "content_type": "divider",
                    "text": None,
                },
            ]
        }
        with pytest.raises(ValueError, match="at least one field element"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_rejects_invalid_element_type(self) -> None:
        """Element with invalid element_type raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        # When there's no valid field element, the "at least one field" check
        # fires first. Include a valid field to test element_type validation.
        schema = {
            "elements": [
                {"element_type": "field", "label": "Valid", "type": "Text"},
                {"element_type": "unknown", "label": "X", "type": "Text"},
            ]
        }
        with pytest.raises(ValueError, match="invalid element_type"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_rejects_invalid_field_type(self) -> None:
        """Field element with invalid type raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "X",
                    "type": "InvalidType",
                }
            ]
        }
        with pytest.raises(ValueError, match="invalid type"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_rejects_empty_field_label(self) -> None:
        """Field element with empty label raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {"element_type": "field", "label": "", "type": "Text"}
            ]
        }
        with pytest.raises(ValueError, match="non-empty label"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_rejects_invalid_content_type(self) -> None:
        """Content block with invalid content_type raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {"element_type": "field", "label": "X", "type": "Text"},
                {
                    "element_type": "content_block",
                    "content_type": "invalid_type",
                    "text": "Hello",
                },
            ]
        }
        with pytest.raises(ValueError, match="invalid content_type"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_rejects_non_dict_element(self) -> None:
        """Non-dict element in elements array raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        # Include a valid field so the "at least one field" check passes,
        # then the non-dict element triggers the detailed validation error.
        schema = {
            "elements": [
                {"element_type": "field", "label": "Valid", "type": "Text"},
                "not_a_dict",
            ]
        }
        with pytest.raises(ValueError, match="must be a dict"):
            await service.create_template(session, "Test", schema, 1)


# ---------------------------------------------------------------------------
# Tests: Enhanced Format — Config Validation
# ---------------------------------------------------------------------------


class TestEnhancedConfigValidation:
    """Tests for type-specific config validation in enhanced format."""

    @pytest.mark.asyncio
    async def test_valid_text_config(self) -> None:
        """Valid TextFieldConfig is accepted and stored."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Batch Number",
                    "type": "Text",
                    "required": True,
                    "help_text": "Enter batch number",
                    "default_value": None,
                    "config": {
                        "min_length": 5,
                        "max_length": 20,
                        "placeholder": "BN-2024-001",
                        "regex_pattern": r"^BN-\d{4}-\d{3}$",
                    },
                }
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_text_config_min_exceeds_max(self) -> None:
        """TextFieldConfig with min > max raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Name",
                    "type": "Text",
                    "config": {"min_length": 100, "max_length": 10},
                }
            ]
        }
        with pytest.raises(ValueError, match="invalid config"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_invalid_text_config_bad_regex(self) -> None:
        """TextFieldConfig with invalid regex raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Code",
                    "type": "Text",
                    "config": {"regex_pattern": "[unclosed"},
                }
            ]
        }
        with pytest.raises(ValueError, match="invalid config"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_valid_float_config(self) -> None:
        """Valid FloatFieldConfig is accepted."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "pH Value",
                    "type": "Float",
                    "required": True,
                    "config": {
                        "decimal_precision": 2,
                        "min_value": 0.0,
                        "max_value": 14.0,
                        "unit_label": "pH",
                    },
                }
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_float_config_min_exceeds_max(self) -> None:
        """FloatFieldConfig with min > max raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Temp",
                    "type": "Float",
                    "config": {"min_value": 100.0, "max_value": 0.0},
                }
            ]
        }
        with pytest.raises(ValueError, match="invalid config"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_valid_integer_config(self) -> None:
        """Valid IntegerFieldConfig is accepted."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Count",
                    "type": "Integer",
                    "config": {
                        "min_value": 0,
                        "max_value": 1000,
                        "step_size": 5,
                        "unit_label": "units",
                    },
                }
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_valid_date_config(self) -> None:
        """Valid DateFieldConfig is accepted."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Expiry Date",
                    "type": "Date",
                    "config": {
                        "min_date": "2024-01-01",
                        "max_date": "2025-12-31",
                        "date_format": "YYYY-MM-DD",
                    },
                }
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_invalid_date_config_min_after_max(self) -> None:
        """DateFieldConfig with min > max raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Date",
                    "type": "Date",
                    "config": {
                        "min_date": "2025-12-31",
                        "max_date": "2024-01-01",
                    },
                }
            ]
        }
        with pytest.raises(ValueError, match="invalid config"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_valid_boolean_config(self) -> None:
        """Valid BooleanFieldConfig is accepted."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "QC Passed",
                    "type": "Boolean",
                    "config": {
                        "true_label": "Pass",
                        "false_label": "Fail",
                    },
                }
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_null_config_accepted(self) -> None:
        """Field with null config is accepted (no validation needed)."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Simple",
                    "type": "Text",
                    "config": None,
                }
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_non_dict_config_rejected(self) -> None:
        """Field with non-dict config raises ValueError."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Bad",
                    "type": "Text",
                    "config": "not_a_dict",
                }
            ]
        }
        with pytest.raises(ValueError, match="must be a dict or null"):
            await service.create_template(session, "Test", schema, 1)


# ---------------------------------------------------------------------------
# Tests: Enhanced Format — Content Blocks
# ---------------------------------------------------------------------------


class TestEnhancedContentBlocks:
    """Tests for content block handling in enhanced format."""

    @pytest.mark.asyncio
    async def test_content_blocks_with_fields(self) -> None:
        """Mixed fields and content blocks are accepted."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "content_block",
                    "content_type": "heading_h1",
                    "text": "Section 1",
                },
                {
                    "element_type": "field",
                    "label": "Name",
                    "type": "Text",
                },
                {
                    "element_type": "content_block",
                    "content_type": "paragraph",
                    "text": "Enter the batch details below.",
                },
                {
                    "element_type": "content_block",
                    "content_type": "divider",
                    "text": None,
                },
                {
                    "element_type": "field",
                    "label": "Value",
                    "type": "Float",
                    "config": {"decimal_precision": 2},
                },
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_all_content_block_types_accepted(self) -> None:
        """All valid content_type values are accepted."""
        service = TemplateService()
        session = _make_mock_session()

        schema = {
            "elements": [
                {
                    "element_type": "content_block",
                    "content_type": "heading_h1",
                    "text": "H1",
                },
                {
                    "element_type": "content_block",
                    "content_type": "heading_h2",
                    "text": "H2",
                },
                {
                    "element_type": "content_block",
                    "content_type": "heading_h3",
                    "text": "H3",
                },
                {
                    "element_type": "content_block",
                    "content_type": "paragraph",
                    "text": "Paragraph text",
                },
                {
                    "element_type": "content_block",
                    "content_type": "divider",
                    "text": None,
                },
                {
                    "element_type": "field",
                    "label": "Required Field",
                    "type": "Text",
                },
            ]
        }
        result = await service.create_template(session, "Test", schema, 1)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: Enhanced Format — UUID Assignment
# ---------------------------------------------------------------------------


class TestEnhancedUUIDAssignment:
    """Tests for UUID assignment in enhanced format."""

    def test_field_uuid_format(self) -> None:
        """Field UUIDs match FLD-XXXXXXXX pattern."""
        uuid_service = UUIDService()
        field_uuid = uuid_service.generate_field_uuid()
        assert FIELD_UUID_PATTERN.match(field_uuid)

    def test_content_block_uuid_format(self) -> None:
        """Content block UUIDs match CB-XXXXXXXX pattern."""
        uuid_service = UUIDService()
        cb_uuid = uuid_service.generate_content_block_uuid()
        assert CB_UUID_PATTERN.match(cb_uuid)

    def test_field_and_cb_uuids_are_distinct(self) -> None:
        """Field UUIDs and content block UUIDs have different prefixes."""
        uuid_service = UUIDService()
        field_uuid = uuid_service.generate_field_uuid()
        cb_uuid = uuid_service.generate_content_block_uuid()
        assert field_uuid.startswith("FLD-")
        assert cb_uuid.startswith("CB-")
        assert field_uuid != cb_uuid


# ---------------------------------------------------------------------------
# Tests: Enhanced Format — Element Parsing
# ---------------------------------------------------------------------------


class TestElementParsing:
    """Tests for the _parse_and_validate_elements helper."""

    def test_parses_field_element(self) -> None:
        """Field elements are parsed with validated config."""
        service = TemplateService()
        elements = [
            {
                "element_type": "field",
                "label": "Name",
                "type": "Text",
                "required": True,
                "help_text": "Enter name",
                "default_value": "Default",
                "config": {"max_length": 100},
            }
        ]
        result = service._parse_and_validate_elements(elements)
        assert len(result) == 1
        assert result[0]["element_type"] == "field"
        assert result[0]["type"] == "Text"
        assert result[0]["label"] == "Name"
        assert result[0]["required"] is True
        assert result[0]["help_text"] == "Enter name"
        assert result[0]["default_value"] == "Default"
        assert result[0]["validated_config"] == {"max_length": 100}

    def test_parses_content_block_element(self) -> None:
        """Content block elements are parsed correctly."""
        service = TemplateService()
        elements = [
            {
                "element_type": "content_block",
                "content_type": "heading_h1",
                "text": "Section Title",
            }
        ]
        result = service._parse_and_validate_elements(elements)
        assert len(result) == 1
        assert result[0]["element_type"] == "content_block"
        assert result[0]["content_type"] == "heading_h1"
        assert result[0]["text"] == "Section Title"

    def test_config_none_values_excluded(self) -> None:
        """Config with None values are excluded from validated_config."""
        service = TemplateService()
        elements = [
            {
                "element_type": "field",
                "label": "Name",
                "type": "Text",
                "config": {"max_length": 50, "min_length": None},
            }
        ]
        result = service._parse_and_validate_elements(elements)
        # min_length=None should be excluded
        assert result[0]["validated_config"] == {"max_length": 50}

    def test_empty_config_dict_produces_empty_dict(self) -> None:
        """Empty config dict produces empty validated_config."""
        service = TemplateService()
        elements = [
            {
                "element_type": "field",
                "label": "Name",
                "type": "Text",
                "config": {},
            }
        ]
        result = service._parse_and_validate_elements(elements)
        # All fields are None, so exclude_none produces empty dict
        assert result[0]["validated_config"] == {}
