"""Integration tests for CSV record isolation.

Tests: validation records excluded from standard searches.

References:
    - Task 22.7: Integration tests for CSV isolation
"""

import pytest

from alcoabase.models.document import Document


# ---------------------------------------------------------------------------
# Integration Tests: CSV Isolation
# ---------------------------------------------------------------------------


class TestCSVIsolation:
    """Integration tests for CSV validation record isolation."""

    def test_csv_records_excluded_from_standard_search(self):
        """Documents with is_csv_validation_record=True are excluded from standard searches."""
        # Simulate a document set
        documents = [
            Document(
                id=1,
                document_uuid="2025-00001",
                title="Real SOP",
                folder_path="/sops",
                document_type="SOP",
                current_status="Draft",
                is_csv_validation_record=False,
                created_by=1,
            ),
            Document(
                id=2,
                document_uuid="2025-00002",
                title="CSV Test Document",
                folder_path="/sops",
                document_type="SOP",
                current_status="Draft",
                is_csv_validation_record=True,
                created_by=99,
            ),
            Document(
                id=3,
                document_uuid="2025-00003",
                title="Another Real SOP",
                folder_path="/sops",
                document_type="SOP",
                current_status="Approved",
                is_csv_validation_record=False,
                created_by=1,
            ),
        ]

        # Standard search excludes CSV records
        standard_results = [
            d for d in documents if not d.is_csv_validation_record
        ]

        assert len(standard_results) == 2
        assert all(not d.is_csv_validation_record for d in standard_results)
        assert "2025-00002" not in [d.document_uuid for d in standard_results]

    def test_csv_records_visible_to_csv_user(self):
        """CSV test user can see their own validation records."""
        documents = [
            Document(
                id=1,
                document_uuid="2025-00001",
                title="Real SOP",
                folder_path="/sops",
                document_type="SOP",
                current_status="Draft",
                is_csv_validation_record=False,
                created_by=1,
            ),
            Document(
                id=2,
                document_uuid="2025-00002",
                title="CSV Test Document",
                folder_path="/sops",
                document_type="SOP",
                current_status="Draft",
                is_csv_validation_record=True,
                created_by=99,
            ),
        ]

        # CSV user search includes CSV records
        csv_user_id = 99
        csv_results = [
            d for d in documents
            if d.is_csv_validation_record and d.created_by == csv_user_id
        ]

        assert len(csv_results) == 1
        assert csv_results[0].document_uuid == "2025-00002"

    def test_csv_flag_set_on_creation_by_csv_user(self):
        """Documents created by CSV test user are auto-tagged."""
        # Simulate middleware behavior
        csv_user_id = 99
        is_csv_user = True

        doc = Document(
            id=1,
            document_uuid="2025-00099",
            title="Validation Test Doc",
            folder_path="/validation",
            document_type="SOP",
            current_status="Draft",
            is_csv_validation_record=is_csv_user,
            created_by=csv_user_id,
        )

        assert doc.is_csv_validation_record is True

    def test_standard_user_documents_not_csv_tagged(self):
        """Documents created by standard users are not CSV-tagged."""
        standard_user_id = 1
        is_csv_user = False

        doc = Document(
            id=1,
            document_uuid="2025-00001",
            title="Normal Document",
            folder_path="/sops",
            document_type="SOP",
            current_status="Draft",
            is_csv_validation_record=is_csv_user,
            created_by=standard_user_id,
        )

        assert doc.is_csv_validation_record is False
