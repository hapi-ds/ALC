"""Unit tests for enhanced TemplateService.

Tests version creation, history retrieval, active enforcement,
enhanced template creation with elements format, and concurrent
version creation rejection.

References:
    - Requirements 10.5: Version number = max existing + 1
    - Requirements 10.6: New version is active with status ReadOnly
    - Requirements 10.8: Concurrent version creation returns 409
    - Requirements 13.3: Previous active version deactivated
    - Requirements 13.4: Exactly one active version per template
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from alcoabase.models.template_version import TemplateVersion, TemplateVersionField
from alcoabase.services.template_service import TemplateService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class FakeTemplate:
    """Lightweight fake Template for unit testing."""

    def __init__(
        self,
        id: int = 1,
        document_uuid: str = "2026-00001",
        name: str = "Test Template",
        status: str = "ReadOnly",
        created_by: int = 1,
    ) -> None:
        self.id = id
        self.document_uuid = document_uuid
        self.name = name
        self.status = status
        self.created_by = created_by
        self.fields: list = []


class FakeVersion:
    """Lightweight fake TemplateVersion for unit testing."""

    def __init__(
        self,
        id: int = 1,
        template_id: int = 1,
        version_number: int = 1,
        document_uuid: str = "2026-00001",
        json_schema: dict | None = None,
        status: str = "ReadOnly",
        is_active: bool = True,
        created_by: int = 1,
        change_reason: str = "Test",
        created_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.template_id = template_id
        self.version_number = version_number
        self.document_uuid = document_uuid
        self.json_schema = json_schema or {"elements": []}
        self.status = status
        self.is_active = is_active
        self.created_by = created_by
        self.change_reason = change_reason
        self.created_at = created_at or datetime.now(timezone.utc)
        self.fields: list = []


@pytest.fixture
def service() -> TemplateService:
    """Create a TemplateService instance for testing."""
    return TemplateService()


@pytest.fixture
def valid_schema() -> dict:
    """A valid enhanced JSON schema with elements array."""
    return {
        "elements": [
            {
                "element_type": "field",
                "label": "Batch Number",
                "type": "Text",
                "required": True,
                "help_text": "Enter batch number",
                "default_value": None,
                "config": {"max_length": 50},
            },
            {
                "element_type": "content_block",
                "content_type": "heading_h1",
                "text": "Section 1",
            },
        ]
    }


@pytest.fixture
def mixed_schema() -> dict:
    """A schema with multiple field types and content blocks."""
    return {
        "elements": [
            {
                "element_type": "content_block",
                "content_type": "heading_h1",
                "text": "Product Information",
            },
            {
                "element_type": "field",
                "label": "Product Name",
                "type": "Text",
                "required": True,
                "help_text": None,
                "default_value": None,
                "config": {"max_length": 100},
            },
            {
                "element_type": "field",
                "label": "pH Value",
                "type": "Float",
                "required": True,
                "help_text": "Measure at 25C",
                "default_value": "7.0",
                "config": {
                    "decimal_precision": 2,
                    "min_value": 0.0,
                    "max_value": 14.0,
                    "unit_label": "pH",
                },
            },
            {
                "element_type": "content_block",
                "content_type": "divider",
                "text": None,
            },
            {
                "element_type": "field",
                "label": "Passed QC",
                "type": "Boolean",
                "required": True,
                "help_text": None,
                "default_value": None,
                "config": {"true_label": "Pass", "false_label": "Fail"},
            },
        ]
    }


# ---------------------------------------------------------------------------
# Session factory helpers
# ---------------------------------------------------------------------------


def _make_create_version_session(
    template: FakeTemplate | None,
    max_version: int = 0,
    raise_lock_error: bool = False,
) -> AsyncMock:
    """Build a mock session for create_version tests.

    Simulates the DB call sequence:
    1. SELECT FOR UPDATE (template lock)
    2. SELECT max(version_number)
    3. UPDATE (deactivate previous active)
    4. SELECT (reload version with fields)
    """
    session = AsyncMock()
    # session.add is synchronous in SQLAlchemy, use MagicMock to avoid warnings
    session.add = MagicMock()
    call_idx = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_idx["n"] += 1
        result = MagicMock()

        if raise_lock_error and call_idx["n"] == 1:
            raise OperationalError("could not obtain lock", {}, None)

        if call_idx["n"] == 1:
            # SELECT FOR UPDATE
            result.scalar_one_or_none.return_value = template
        elif call_idx["n"] == 2:
            # SELECT max(version_number)
            result.scalar_one.return_value = max_version
        elif call_idx["n"] == 3:
            # UPDATE deactivate
            pass
        elif call_idx["n"] == 4:
            # SELECT reload version
            version = FakeVersion(
                id=10,
                template_id=template.id if template else 1,
                version_number=max_version + 1,
                document_uuid=template.document_uuid if template else "2026-00001",
                status="ReadOnly",
                is_active=True,
                created_by=1,
                change_reason="Test",
            )
            version.fields = []
            result.scalar_one.return_value = version

        return result

    session.execute = mock_execute
    return session


def _make_history_session(
    template: FakeTemplate | None,
    versions: list[FakeVersion],
) -> AsyncMock:
    """Build a mock session for get_version_history tests.

    First execute returns template (via get_template),
    second returns version list.
    """
    session = AsyncMock()
    call_idx = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_idx["n"] += 1
        result = MagicMock()

        if call_idx["n"] == 1:
            # get_template lookup
            result.scalar_one_or_none.return_value = template
        else:
            # version history query
            scalars_mock = MagicMock()
            unique_mock = MagicMock()
            unique_mock.all.return_value = versions
            scalars_mock.unique.return_value = unique_mock
            result.scalars.return_value = scalars_mock

        return result

    session.execute = mock_execute
    return session


def _make_enhanced_create_session(seq_value: int = 1) -> AsyncMock:
    """Build a mock session for enhanced template creation tests.

    Simulates:
    1-2. UUID generation (CREATE SEQUENCE + nextval)
    3. SELECT reload template with fields
    """
    session = AsyncMock()
    added_objects: list = []

    def track_add(obj: object) -> None:
        added_objects.append(obj)
        if hasattr(obj, "id") and obj.id is None:
            obj.id = 1

    # session.add is synchronous in SQLAlchemy, so use MagicMock
    session.add = MagicMock(side_effect=track_add)
    session._added_objects = added_objects

    call_idx = {"n": 0}

    async def mock_execute(stmt, *args, **kwargs):
        call_idx["n"] += 1
        result = MagicMock()

        if call_idx["n"] <= 2:
            # UUID generation sequence calls
            result.scalar_one.return_value = seq_value
            return result

        # Reload template with fields
        template_mock = MagicMock()
        template_mock.id = 1
        template_mock.document_uuid = f"2026-{seq_value:05d}"
        template_mock.name = "Test"
        template_mock.status = "ReadOnly"
        template_mock.fields = added_objects[1:]
        result.scalar_one.return_value = template_mock
        return result

    session.execute = mock_execute
    return session


# ---------------------------------------------------------------------------
# Tests: Version creation assigns correct version_number
# ---------------------------------------------------------------------------


class TestVersionNumberAssignment:
    """Version creation assigns version_number = max existing + 1.

    Validates: Requirement 10.5
    """

    @pytest.mark.asyncio
    async def test_first_version_gets_number_one(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """First version for a template gets version_number=1."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=0)

        result = await service.create_version(
            session, "2026-00001", valid_schema, 1, "Initial version"
        )

        assert result.version_number == 1

    @pytest.mark.asyncio
    async def test_increments_from_existing_max(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """Version number increments from the highest existing version."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=5)

        result = await service.create_version(
            session, "2026-00001", valid_schema, 1, "Version 6"
        )

        assert result.version_number == 6

    @pytest.mark.asyncio
    async def test_increments_from_large_version_number(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """Works correctly even with large existing version numbers."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=99)

        result = await service.create_version(
            session, "2026-00001", valid_schema, 1, "Version 100"
        )

        assert result.version_number == 100


# ---------------------------------------------------------------------------
# Tests: Version creation deactivates previous active version
# ---------------------------------------------------------------------------


class TestVersionDeactivatesPrevious:
    """Version creation deactivates the previous active version.

    Validates: Requirement 13.3
    """

    @pytest.mark.asyncio
    async def test_deactivation_update_is_executed(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """The UPDATE to deactivate previous versions is called during creation."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=2)

        # Track all execute calls
        execute_calls: list = []
        original_execute = session.execute

        async def tracking_execute(stmt, *args, **kwargs):
            execute_calls.append(stmt)
            return await original_execute(stmt, *args, **kwargs)

        session.execute = tracking_execute

        await service.create_version(
            session, "2026-00001", valid_schema, 1, "New version"
        )

        # Should have at least 4 execute calls (lock, max, deactivate, reload)
        assert len(execute_calls) >= 4

    @pytest.mark.asyncio
    async def test_new_version_is_active_after_deactivation(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """After deactivation, the new version is the active one."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=3)

        result = await service.create_version(
            session, "2026-00001", valid_schema, 1, "Version 4"
        )

        assert result.is_active is True


# ---------------------------------------------------------------------------
# Tests: Version creation sets new version as active with status ReadOnly
# ---------------------------------------------------------------------------


class TestVersionActiveAndReadOnly:
    """New version has is_active=True and status='ReadOnly'.

    Validates: Requirements 10.6, 13.4
    """

    @pytest.mark.asyncio
    async def test_new_version_is_active(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """New version has is_active=True."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=0)

        result = await service.create_version(
            session, "2026-00001", valid_schema, 1, "First version"
        )

        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_new_version_has_readonly_status(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """New version has status='ReadOnly'."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=0)

        result = await service.create_version(
            session, "2026-00001", valid_schema, 1, "First version"
        )

        assert result.status == "ReadOnly"

    @pytest.mark.asyncio
    async def test_version_object_added_with_correct_attributes(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """The TemplateVersion object added to session has correct attributes."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=1)

        # Track objects added to session
        added: list = []
        session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        await service.create_version(
            session, "2026-00001", valid_schema, 1, "Version 2"
        )

        # Find the TemplateVersion object
        tv_objects = [o for o in added if isinstance(o, TemplateVersion)]
        assert len(tv_objects) == 1

        tv = tv_objects[0]
        assert tv.is_active is True
        assert tv.status == "ReadOnly"
        assert tv.version_number == 2
        assert tv.change_reason == "Version 2"
        assert tv.created_by == 1


# ---------------------------------------------------------------------------
# Tests: get_version_history returns versions in descending order
# ---------------------------------------------------------------------------


class TestGetVersionHistoryOrder:
    """get_version_history returns versions ordered by version_number DESC.

    Validates: Requirements 10.5, 13.3
    """

    @pytest.mark.asyncio
    async def test_returns_descending_order(
        self, service: TemplateService
    ) -> None:
        """Versions are returned newest first."""
        template = FakeTemplate()
        versions = [
            FakeVersion(id=3, version_number=3, is_active=True),
            FakeVersion(id=2, version_number=2, is_active=False),
            FakeVersion(id=1, version_number=1, is_active=False),
        ]
        session = _make_history_session(template, versions)

        result = await service.get_version_history(session, "2026-00001")

        assert len(result) == 3
        assert result[0].version_number == 3
        assert result[1].version_number == 2
        assert result[2].version_number == 1

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_versions(
        self, service: TemplateService
    ) -> None:
        """Returns empty list when template has no versions."""
        template = FakeTemplate()
        session = _make_history_session(template, [])

        result = await service.get_version_history(session, "2026-00001")

        assert result == []

    @pytest.mark.asyncio
    async def test_raises_404_for_missing_template(
        self, service: TemplateService
    ) -> None:
        """Raises 404 when template does not exist."""
        session = _make_history_session(None, [])

        with pytest.raises(HTTPException) as exc_info:
            await service.get_version_history(session, "2026-99999")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_single_version_returned(
        self, service: TemplateService
    ) -> None:
        """Single version is returned correctly."""
        template = FakeTemplate()
        versions = [FakeVersion(id=1, version_number=1, is_active=True)]
        session = _make_history_session(template, versions)

        result = await service.get_version_history(session, "2026-00001")

        assert len(result) == 1
        assert result[0].version_number == 1
        assert result[0].is_active is True


# ---------------------------------------------------------------------------
# Tests: Enhanced template creation with elements format
# ---------------------------------------------------------------------------


class TestEnhancedTemplateCreation:
    """Enhanced template creation with elements array format.

    Validates: Requirements 10.5, 10.6
    """

    @pytest.mark.asyncio
    async def test_creates_template_with_field_elements(
        self, service: TemplateService
    ) -> None:
        """Template with field elements is created successfully."""
        session = _make_enhanced_create_session()
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
        assert result.status == "ReadOnly"

    @pytest.mark.asyncio
    async def test_creates_template_with_mixed_elements(
        self, service: TemplateService, mixed_schema: dict
    ) -> None:
        """Template with mixed fields and content blocks is created."""
        session = _make_enhanced_create_session()

        result = await service.create_template(
            session, "Batch Release", mixed_schema, 1
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_rejects_schema_without_field_elements(
        self, service: TemplateService
    ) -> None:
        """Schema with only content blocks is rejected."""
        session = _make_enhanced_create_session()
        schema = {
            "elements": [
                {
                    "element_type": "content_block",
                    "content_type": "heading_h1",
                    "text": "Title",
                }
            ]
        }

        with pytest.raises(ValueError, match="at least one field element"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_rejects_empty_elements_array(
        self, service: TemplateService
    ) -> None:
        """Empty elements array is rejected."""
        session = _make_enhanced_create_session()

        with pytest.raises(ValueError, match="non-empty list"):
            await service.create_template(
                session, "Test", {"elements": []}, 1
            )

    @pytest.mark.asyncio
    async def test_validates_field_config_types(
        self, service: TemplateService
    ) -> None:
        """Invalid field config is rejected with descriptive error."""
        session = _make_enhanced_create_session()
        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Bad",
                    "type": "Float",
                    "config": {"min_value": 100.0, "max_value": 0.0},
                }
            ]
        }

        with pytest.raises(ValueError, match="invalid config"):
            await service.create_template(session, "Test", schema, 1)

    @pytest.mark.asyncio
    async def test_field_elements_get_fld_uuid_prefix(
        self, service: TemplateService
    ) -> None:
        """Field elements are assigned FLD-XXXXXXXX UUIDs."""
        import re

        session = _make_enhanced_create_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Name",
                    "type": "Text",
                }
            ]
        }

        await service.create_template(session, "Test", schema, 1)

        # Access the tracked objects from the session helper
        from alcoabase.models.template import TemplateField

        added = session._added_objects
        fields = [o for o in added if isinstance(o, TemplateField)]
        assert len(fields) == 1
        assert re.match(r"^FLD-[A-F0-9]{8}$", fields[0].field_uuid)

    @pytest.mark.asyncio
    async def test_content_blocks_get_cb_uuid_prefix(
        self, service: TemplateService
    ) -> None:
        """Content block elements are assigned CB-XXXXXXXX UUIDs."""
        import re

        session = _make_enhanced_create_session()

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Name",
                    "type": "Text",
                },
                {
                    "element_type": "content_block",
                    "content_type": "divider",
                    "text": None,
                },
            ]
        }

        await service.create_template(session, "Test", schema, 1)

        from alcoabase.models.template import TemplateField

        added = session._added_objects
        fields = [o for o in added if isinstance(o, TemplateField)]
        cb_fields = [f for f in fields if f.element_type == "content_block"]
        assert len(cb_fields) == 1
        assert re.match(r"^CB-[A-F0-9]{8}$", cb_fields[0].field_uuid)


# ---------------------------------------------------------------------------
# Tests: Concurrent version creation returns 409
# ---------------------------------------------------------------------------


class TestConcurrentVersionCreation:
    """Concurrent version creation is rejected with HTTP 409.

    Validates: Requirement 10.8
    """

    @pytest.mark.asyncio
    async def test_returns_409_on_lock_conflict(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """Returns 409 when SELECT FOR UPDATE fails due to lock."""
        session = _make_create_version_session(
            template=None, raise_lock_error=True
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.create_version(
                session, "2026-00001", valid_schema, 1, "Concurrent"
            )

        assert exc_info.value.status_code == 409
        assert "Version creation in progress" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_409_detail_message_is_descriptive(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """The 409 error message clearly indicates a concurrent conflict."""
        session = _make_create_version_session(
            template=None, raise_lock_error=True
        )

        with pytest.raises(HTTPException) as exc_info:
            await service.create_version(
                session, "2026-00001", valid_schema, 1, "Retry"
            )

        assert "in progress" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Tests: Exactly one active version per template
# ---------------------------------------------------------------------------


class TestExactlyOneActiveVersion:
    """Exactly one version per template has is_active=True at any time.

    Validates: Requirement 13.4
    """

    @pytest.mark.asyncio
    async def test_new_version_is_the_only_active(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """After creation, the new version is active and previous are deactivated."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=3)

        # Track objects added
        added: list = []
        session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        await service.create_version(
            session, "2026-00001", valid_schema, 1, "Version 4"
        )

        # The TemplateVersion added should have is_active=True
        tv_objects = [o for o in added if isinstance(o, TemplateVersion)]
        assert len(tv_objects) == 1
        assert tv_objects[0].is_active is True

    @pytest.mark.asyncio
    async def test_deactivation_targets_same_template(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """Deactivation UPDATE targets only versions of the same template."""
        template = FakeTemplate(id=42, status="ReadOnly")
        session = _make_create_version_session(template, max_version=1)

        # Track objects added to verify template_id
        added: list = []
        session.add = MagicMock(side_effect=lambda obj: added.append(obj))

        await service.create_version(
            session, "2026-00001", valid_schema, 1, "Version 2"
        )

        # The new version should reference the correct template_id
        tv_objects = [o for o in added if isinstance(o, TemplateVersion)]
        assert tv_objects[0].template_id == 42

    @pytest.mark.asyncio
    async def test_version_history_shows_only_one_active(
        self, service: TemplateService
    ) -> None:
        """In version history, exactly one version is marked active."""
        template = FakeTemplate()
        versions = [
            FakeVersion(id=3, version_number=3, is_active=True),
            FakeVersion(id=2, version_number=2, is_active=False),
            FakeVersion(id=1, version_number=1, is_active=False),
        ]
        session = _make_history_session(template, versions)

        result = await service.get_version_history(session, "2026-00001")

        active_versions = [v for v in result if v.is_active]
        assert len(active_versions) == 1
        assert active_versions[0].version_number == 3


# ---------------------------------------------------------------------------
# Tests: Error handling edge cases
# ---------------------------------------------------------------------------


class TestVersionCreationErrors:
    """Error handling for version creation edge cases."""

    @pytest.mark.asyncio
    async def test_returns_404_for_nonexistent_template(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """Returns 404 when template UUID does not exist."""
        session = _make_create_version_session(template=None)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_version(
                session, "2026-99999", valid_schema, 1, "Should fail"
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_400_for_non_readonly_template(
        self, service: TemplateService, valid_schema: dict
    ) -> None:
        """Returns 400 when template is not in ReadOnly status."""
        template = FakeTemplate(status="Draft")
        session = _make_create_version_session(template, max_version=0)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_version(
                session, "2026-00001", valid_schema, 1, "Should fail"
            )

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_returns_400_for_missing_elements_key(
        self, service: TemplateService
    ) -> None:
        """Returns 400 when json_schema lacks 'elements' key."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=0)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_version(
                session,
                "2026-00001",
                {"fields": [{"label": "X", "type": "Text"}]},
                1,
                "Should fail",
            )

        assert exc_info.value.status_code == 400
        assert "elements" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_400_for_invalid_element_config(
        self, service: TemplateService
    ) -> None:
        """Returns 400 when element config validation fails."""
        template = FakeTemplate(status="ReadOnly")
        session = _make_create_version_session(template, max_version=0)

        schema = {
            "elements": [
                {
                    "element_type": "field",
                    "label": "Bad",
                    "type": "Integer",
                    "config": {"min_value": 100, "max_value": 0},
                }
            ]
        }

        with pytest.raises(HTTPException) as exc_info:
            await service.create_version(
                session, "2026-00001", schema, 1, "Should fail"
            )

        assert exc_info.value.status_code == 400
