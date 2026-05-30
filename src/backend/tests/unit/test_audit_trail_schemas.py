"""Unit tests for audit trail Pydantic request/response schemas.

Tests validation rules for AuditTrailFilters, AuditEvent, AuditTrailListParams,
ExportRequest, and FieldChange schemas.

References:
    - Requirements 1.3: Event serialization with field truncation
    - Requirements 2.2: Page size clamping
    - Requirements 3.1–3.4: Filter validation
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from alcoabase.schemas.audit_trail import (
    ALLOWED_RECORD_TYPES,
    AuditEvent,
    AuditTrailFilters,
    AuditTrailListParams,
    ExportRequest,
    FieldChange,
)


# ---------------------------------------------------------------------------
# AuditTrailFilters Tests
# ---------------------------------------------------------------------------


class TestAuditTrailFilters:
    """Tests for AuditTrailFilters validation."""

    def test_all_fields_optional_defaults_to_none(self) -> None:
        filters = AuditTrailFilters()
        assert filters.user_id is None
        assert filters.date_start is None
        assert filters.date_end is None
        assert filters.record_type is None
        assert filters.operation_type is None

    def test_valid_record_type_documents(self) -> None:
        filters = AuditTrailFilters(record_type="documents")
        assert filters.record_type == "documents"

    def test_valid_record_type_templates(self) -> None:
        filters = AuditTrailFilters(record_type="templates")
        assert filters.record_type == "templates"

    def test_valid_record_type_reports(self) -> None:
        filters = AuditTrailFilters(record_type="reports")
        assert filters.record_type == "reports"

    def test_valid_record_type_workflows(self) -> None:
        filters = AuditTrailFilters(record_type="workflows")
        assert filters.record_type == "workflows"

    def test_valid_record_type_signatures(self) -> None:
        filters = AuditTrailFilters(record_type="signatures")
        assert filters.record_type == "signatures"

    def test_valid_record_type_training_tasks(self) -> None:
        filters = AuditTrailFilters(record_type="training_tasks")
        assert filters.record_type == "training_tasks"

    def test_valid_record_type_training_records(self) -> None:
        filters = AuditTrailFilters(record_type="training_records")
        assert filters.record_type == "training_records"

    def test_all_allowed_record_types_accepted(self) -> None:
        for rt in ALLOWED_RECORD_TYPES:
            filters = AuditTrailFilters(record_type=rt)
            assert filters.record_type == rt

    def test_invalid_record_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid record_type"):
            AuditTrailFilters(record_type="invalid_type")

    def test_empty_string_record_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid record_type"):
            AuditTrailFilters(record_type="")

    def test_record_type_none_accepted(self) -> None:
        filters = AuditTrailFilters(record_type=None)
        assert filters.record_type is None

    def test_valid_operation_type_insert(self) -> None:
        filters = AuditTrailFilters(operation_type="INSERT")
        assert filters.operation_type == "INSERT"

    def test_valid_operation_type_update(self) -> None:
        filters = AuditTrailFilters(operation_type="UPDATE")
        assert filters.operation_type == "UPDATE"

    def test_valid_operation_type_delete(self) -> None:
        filters = AuditTrailFilters(operation_type="DELETE")
        assert filters.operation_type == "DELETE"

    def test_invalid_operation_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditTrailFilters(operation_type="UPSERT")  # type: ignore[arg-type]

    def test_lowercase_operation_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditTrailFilters(operation_type="insert")  # type: ignore[arg-type]

    def test_operation_type_none_accepted(self) -> None:
        filters = AuditTrailFilters(operation_type=None)
        assert filters.operation_type is None

    def test_date_start_before_date_end_accepted(self) -> None:
        now = datetime.now(tz=timezone.utc)
        filters = AuditTrailFilters(
            date_start=now - timedelta(days=7),
            date_end=now,
        )
        assert filters.date_start < filters.date_end  # type: ignore[operator]

    def test_date_start_after_date_end_rejected(self) -> None:
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(ValidationError, match="date_start must be before date_end"):
            AuditTrailFilters(
                date_start=now + timedelta(days=1),
                date_end=now,
            )

    def test_date_start_equal_to_date_end_accepted(self) -> None:
        now = datetime.now(tz=timezone.utc)
        filters = AuditTrailFilters(date_start=now, date_end=now)
        assert filters.date_start == filters.date_end

    def test_date_start_only_accepted(self) -> None:
        now = datetime.now(tz=timezone.utc)
        filters = AuditTrailFilters(date_start=now)
        assert filters.date_start == now
        assert filters.date_end is None

    def test_date_end_only_accepted(self) -> None:
        now = datetime.now(tz=timezone.utc)
        filters = AuditTrailFilters(date_end=now)
        assert filters.date_end == now
        assert filters.date_start is None

    def test_valid_user_id(self) -> None:
        filters = AuditTrailFilters(user_id=42)
        assert filters.user_id == 42

    def test_serialization_round_trip(self) -> None:
        now = datetime.now(tz=timezone.utc)
        filters = AuditTrailFilters(
            user_id=1,
            date_start=now - timedelta(days=30),
            date_end=now,
            record_type="documents",
            operation_type="UPDATE",
        )
        data = filters.model_dump()
        restored = AuditTrailFilters(**data)
        assert restored == filters


# ---------------------------------------------------------------------------
# AuditEvent Tests
# ---------------------------------------------------------------------------


class TestAuditEvent:
    """Tests for AuditEvent serialization and validation."""

    def _make_event(self, **kwargs) -> dict:
        """Helper to create a valid AuditEvent dict with overrides."""
        defaults = {
            "transaction_id": 1,
            "timestamp": datetime.now(tz=timezone.utc),
            "user_id": 10,
            "record_type": "documents",
            "record_id": 100,
            "operation_type": "UPDATE",
            "company_id": 1,
        }
        defaults.update(kwargs)
        return defaults

    def test_valid_event_with_all_fields(self) -> None:
        event = AuditEvent(**self._make_event(
            user_display_name="John Doe",
            change_reason="Updated title",
            changed_fields=["title", "description"],
            total_changed_fields=2,
        ))
        assert event.transaction_id == 1
        assert event.user_display_name == "John Doe"
        assert event.changed_fields == ["title", "description"]
        assert event.total_changed_fields == 2

    def test_changed_fields_max_10_items_accepted(self) -> None:
        fields = [f"field_{i}" for i in range(10)]
        event = AuditEvent(**self._make_event(
            changed_fields=fields,
            total_changed_fields=10,
        ))
        assert len(event.changed_fields) == 10

    def test_changed_fields_exceeds_10_rejected(self) -> None:
        fields = [f"field_{i}" for i in range(11)]
        with pytest.raises(ValidationError):
            AuditEvent(**self._make_event(
                changed_fields=fields,
                total_changed_fields=11,
            ))

    def test_total_changed_fields_reflects_actual_count(self) -> None:
        event = AuditEvent(**self._make_event(
            changed_fields=["a", "b", "c"],
            total_changed_fields=25,
        ))
        assert len(event.changed_fields) == 3
        assert event.total_changed_fields == 25

    def test_changed_fields_empty_list_accepted(self) -> None:
        event = AuditEvent(**self._make_event(
            changed_fields=[],
            total_changed_fields=0,
        ))
        assert event.changed_fields == []
        assert event.total_changed_fields == 0

    def test_change_reason_none_accepted(self) -> None:
        event = AuditEvent(**self._make_event(change_reason=None))
        assert event.change_reason is None

    def test_user_display_name_none_accepted(self) -> None:
        event = AuditEvent(**self._make_event(user_display_name=None))
        assert event.user_display_name is None

    def test_all_operation_types_accepted(self) -> None:
        for op in ("INSERT", "UPDATE", "DELETE"):
            event = AuditEvent(**self._make_event(operation_type=op))
            assert event.operation_type == op

    def test_invalid_operation_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditEvent(**self._make_event(operation_type="MERGE"))

    def test_from_attributes_config(self) -> None:
        assert AuditEvent.model_config.get("from_attributes") is True

    def test_serialization_round_trip(self) -> None:
        event = AuditEvent(**self._make_event(
            user_display_name="Jane",
            change_reason="Test reason",
            changed_fields=["field_a"],
            total_changed_fields=1,
        ))
        data = event.model_dump()
        restored = AuditEvent(**data)
        assert restored == event


# ---------------------------------------------------------------------------
# AuditTrailListParams Tests
# ---------------------------------------------------------------------------


class TestAuditTrailListParams:
    """Tests for AuditTrailListParams validation."""

    def test_defaults(self) -> None:
        params = AuditTrailListParams()
        assert params.cursor is None
        assert params.page_size == 50
        assert params.search is None
        assert params.user_id is None
        assert params.date_start is None
        assert params.date_end is None
        assert params.record_type is None
        assert params.operation_type is None

    def test_page_size_default_50(self) -> None:
        params = AuditTrailListParams()
        assert params.page_size == 50

    def test_page_size_minimum_1_accepted(self) -> None:
        params = AuditTrailListParams(page_size=1)
        assert params.page_size == 1

    def test_page_size_maximum_200_accepted(self) -> None:
        params = AuditTrailListParams(page_size=200)
        assert params.page_size == 200

    def test_page_size_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditTrailListParams(page_size=0)

    def test_page_size_negative_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditTrailListParams(page_size=-1)

    def test_page_size_exceeds_200_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditTrailListParams(page_size=201)

    def test_page_size_boundary_values(self) -> None:
        # Just inside boundaries
        params_low = AuditTrailListParams(page_size=1)
        assert params_low.page_size == 1
        params_high = AuditTrailListParams(page_size=200)
        assert params_high.page_size == 200

    def test_cursor_none_for_first_page(self) -> None:
        params = AuditTrailListParams(cursor=None)
        assert params.cursor is None

    def test_cursor_string_accepted(self) -> None:
        params = AuditTrailListParams(cursor="2024-01-01T00:00:00Z|123|documents")
        assert params.cursor == "2024-01-01T00:00:00Z|123|documents"

    def test_valid_record_type_accepted(self) -> None:
        params = AuditTrailListParams(record_type="workflows")
        assert params.record_type == "workflows"

    def test_invalid_record_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Invalid record_type"):
            AuditTrailListParams(record_type="unknown")

    def test_valid_operation_type_accepted(self) -> None:
        params = AuditTrailListParams(operation_type="DELETE")
        assert params.operation_type == "DELETE"

    def test_invalid_operation_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AuditTrailListParams(operation_type="TRUNCATE")  # type: ignore[arg-type]

    def test_search_query_accepted(self) -> None:
        params = AuditTrailListParams(search="updated title")
        assert params.search == "updated title"

    def test_user_id_filter(self) -> None:
        params = AuditTrailListParams(user_id=5)
        assert params.user_id == 5

    def test_date_filters(self) -> None:
        now = datetime.now(tz=timezone.utc)
        params = AuditTrailListParams(
            date_start=now - timedelta(days=7),
            date_end=now,
        )
        assert params.date_start is not None
        assert params.date_end is not None

    def test_serialization_round_trip(self) -> None:
        params = AuditTrailListParams(
            cursor="abc|123|docs",
            page_size=100,
            search="test",
            user_id=7,
            record_type="signatures",
            operation_type="INSERT",
        )
        data = params.model_dump()
        restored = AuditTrailListParams(**data)
        assert restored == params


# ---------------------------------------------------------------------------
# ExportRequest Tests
# ---------------------------------------------------------------------------


class TestExportRequest:
    """Tests for ExportRequest validation."""

    def test_empty_request_accepted(self) -> None:
        req = ExportRequest()
        assert req.filters is None
        assert req.search_query is None

    def test_filters_none_accepted(self) -> None:
        req = ExportRequest(filters=None)
        assert req.filters is None

    def test_empty_filters_accepted(self) -> None:
        req = ExportRequest(filters=AuditTrailFilters())
        assert req.filters is not None
        assert req.filters.user_id is None
        assert req.filters.record_type is None

    def test_filters_with_values_accepted(self) -> None:
        req = ExportRequest(
            filters=AuditTrailFilters(record_type="documents", operation_type="UPDATE")
        )
        assert req.filters is not None
        assert req.filters.record_type == "documents"
        assert req.filters.operation_type == "UPDATE"

    def test_search_query_optional(self) -> None:
        req = ExportRequest(search_query=None)
        assert req.search_query is None

    def test_search_query_with_value(self) -> None:
        req = ExportRequest(search_query="compliance review")
        assert req.search_query == "compliance review"

    def test_both_filters_and_search_query(self) -> None:
        req = ExportRequest(
            filters=AuditTrailFilters(user_id=5),
            search_query="audit",
        )
        assert req.filters is not None
        assert req.filters.user_id == 5
        assert req.search_query == "audit"

    def test_serialization_round_trip(self) -> None:
        req = ExportRequest(
            filters=AuditTrailFilters(record_type="reports"),
            search_query="quarterly",
        )
        data = req.model_dump()
        restored = ExportRequest(**data)
        assert restored == req


# ---------------------------------------------------------------------------
# FieldChange Tests
# ---------------------------------------------------------------------------


class TestFieldChange:
    """Tests for FieldChange validation — old_value/new_value accept Any type."""

    def test_string_values(self) -> None:
        fc = FieldChange(field_name="title", old_value="Old Title", new_value="New Title")
        assert fc.old_value == "Old Title"
        assert fc.new_value == "New Title"

    def test_int_values(self) -> None:
        fc = FieldChange(field_name="version", old_value=1, new_value=2)
        assert fc.old_value == 1
        assert fc.new_value == 2

    def test_dict_values(self) -> None:
        fc = FieldChange(
            field_name="metadata",
            old_value={"key": "old"},
            new_value={"key": "new", "extra": True},
        )
        assert fc.old_value == {"key": "old"}
        assert fc.new_value == {"key": "new", "extra": True}

    def test_list_values(self) -> None:
        fc = FieldChange(
            field_name="tags",
            old_value=["tag1", "tag2"],
            new_value=["tag1", "tag2", "tag3"],
        )
        assert fc.old_value == ["tag1", "tag2"]
        assert fc.new_value == ["tag1", "tag2", "tag3"]

    def test_none_old_value_for_insert(self) -> None:
        fc = FieldChange(field_name="title", old_value=None, new_value="Created")
        assert fc.old_value is None
        assert fc.new_value == "Created"

    def test_none_new_value_for_delete(self) -> None:
        fc = FieldChange(field_name="title", old_value="Deleted", new_value=None)
        assert fc.old_value == "Deleted"
        assert fc.new_value is None

    def test_both_none_values(self) -> None:
        fc = FieldChange(field_name="nullable_field", old_value=None, new_value=None)
        assert fc.old_value is None
        assert fc.new_value is None

    def test_mixed_types(self) -> None:
        fc = FieldChange(field_name="config", old_value="string_val", new_value=42)
        assert fc.old_value == "string_val"
        assert fc.new_value == 42

    def test_nested_complex_value(self) -> None:
        complex_val = {"nested": [1, 2, {"deep": True}]}
        fc = FieldChange(field_name="data", old_value=None, new_value=complex_val)
        assert fc.new_value == complex_val

    def test_boolean_values(self) -> None:
        fc = FieldChange(field_name="is_active", old_value=True, new_value=False)
        assert fc.old_value is True
        assert fc.new_value is False

    def test_float_values(self) -> None:
        fc = FieldChange(field_name="score", old_value=3.14, new_value=2.71)
        assert fc.old_value == 3.14
        assert fc.new_value == 2.71

    def test_field_name_required(self) -> None:
        with pytest.raises(ValidationError):
            FieldChange(old_value="x", new_value="y")  # type: ignore[call-arg]

    def test_serialization_round_trip(self) -> None:
        fc = FieldChange(
            field_name="status",
            old_value={"state": "draft"},
            new_value={"state": "approved"},
        )
        data = fc.model_dump()
        restored = FieldChange(**data)
        assert restored == fc
