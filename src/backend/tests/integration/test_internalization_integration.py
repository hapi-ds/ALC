"""Integration tests for internalization and traceability workflows.

Tests the multi-step internalization flow crossing service method boundaries:
- Full internalization: IngestionRecord → Document creation → file copy → traceability → collection
- Duplicate internalization detection (HTTP 409)
- MinIO failure graceful handling (Document created, full_text_status="unavailable")
- Traceability link creation via mocked TraceabilityMatrixService
- Non-internalized document rejection (422 for collection add and traceability)

Since Docker PostgreSQL may not be available, these tests mock the DB session
but exercise deeper multi-step flows that cross service method boundaries.

Requirements: 4.1–4.10, 5.1–5.11, 6.1–6.9
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.search.exceptions import (
    CollectionCapacityExceededError,
    DuplicateInternalizationError,
    IngestionRecordNotFoundError,
    NonInternalizedDocumentError,
)
from alcoabase.literature.search.services.literature_search_service import (
    LiteratureSearchService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scalar_result(value):
    """Create a mock result that behaves like session.execute().scalar_one_or_none()."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = value
    mock_result.scalar_one.return_value = value
    mock_result.scalars.return_value.all.return_value = []
    return mock_result


def _make_scalars_result(values):
    """Create a mock result that behaves like session.execute().scalars().all()."""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = values
    mock_result.scalar_one.return_value = len(values)
    return mock_result


def _make_ingestion_record(
    *,
    company_id: int = 1,
    title: str = "Machine Learning in Drug Discovery",
    storage_path: str | None = "papers/2024/ml-drug.pdf",
) -> MagicMock:
    """Create a mock IngestionRecord with standard fields."""
    record = MagicMock()
    record.id = 42
    record.title = title
    record.company_id = company_id
    record.storage_path = storage_path
    record.authors = ["Smith J", "Doe A"]
    record.abstract = "A study on ML approaches to drug discovery."
    record.publication_date = "2024-03-15"
    record.doi = "10.1038/s41591-024-0001"
    record.source_id = "pubmed"
    return record


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock AsyncSession with standard methods."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_query_engine() -> AsyncMock:
    """Create a mock HybridQueryEngine."""
    return AsyncMock()


@pytest.fixture
def mock_audit_service() -> AsyncMock:
    """Create a mock AuditTrailService."""
    service = AsyncMock()
    service.log_event = AsyncMock()
    return service


@pytest.fixture
def mock_traceability_service() -> AsyncMock:
    """Create a mock TraceabilityMatrixService."""
    service = AsyncMock()
    service.create_link = AsyncMock(return_value={"id": 1})
    return service


@pytest.fixture
def mock_storage_client() -> AsyncMock:
    """Create a mock aioboto3 S3 client (MinIO)."""
    client = AsyncMock()
    client.copy_object = AsyncMock()
    return client


@pytest.fixture
def service(
    mock_session: AsyncMock,
    mock_query_engine: AsyncMock,
    mock_audit_service: AsyncMock,
    mock_traceability_service: AsyncMock,
    mock_storage_client: AsyncMock,
) -> LiteratureSearchService:
    """Create LiteratureSearchService with all dependencies mocked."""
    return LiteratureSearchService(
        session=mock_session,
        hybrid_query_engine=mock_query_engine,
        audit_trail_service=mock_audit_service,
        traceability_matrix_service=mock_traceability_service,
        storage_client=mock_storage_client,
    )


# ---------------------------------------------------------------------------
# Test: Full Internalization Workflow
# Requirements: 4.1, 4.2, 4.4, 4.5, 4.6
# ---------------------------------------------------------------------------


class TestFullInternalizationWorkflow:
    """Integration tests for the complete internalization pipeline.

    Exercises the full flow: IngestionRecord retrieval → duplicate check →
    Document creation → file copy → traceability links → collection add → audit.
    """

    @pytest.mark.asyncio
    async def test_full_internalization_with_traceability_and_collection(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
        mock_audit_service: AsyncMock,
    ) -> None:
        """Full flow: internalize with file copy, traceability links, and collection add."""
        ingestion_record = _make_ingestion_record()

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # IngestionRecord lookup
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                # Duplicate check — no existing document
                return _make_scalar_result(None)
            else:
                # Subsequent calls: collection position queries, etc.
                return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        # Track what gets added to the session for link ID assignment
        added_objects = []
        link_id_counter = [0]

        def track_add(obj):
            added_objects.append(obj)

        async def mock_flush():
            # Assign IDs to newly added objects (simulates DB flush)
            for obj in added_objects:
                if not hasattr(obj, "id") or obj.id is None:
                    link_id_counter[0] += 1
                    obj.id = link_id_counter[0]

        mock_session.add = MagicMock(side_effect=track_add)
        mock_session.flush = AsyncMock(side_effect=mock_flush)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00042",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
                document_name=None,
                document_type="literature",
                tags=["pharma", "ML"],
                traceability_links=[
                    {"target_type": "requirement", "target_id": 101, "rationale": "Supports claim A"},
                    {"target_type": "test_case", "target_id": 202},
                ],
                citation_collection_id=5,
            )

        # Verify Document creation
        assert result["document_name"] == "Machine Learning in Drug Discovery"
        assert result["current_status"] == "Draft"
        assert result["source_ingestion_record_id"] == 42
        assert result["full_text_status"] == "available"
        assert result["tags"] == ["pharma", "ML"]
        assert result["citation_collection_id"] == 5

        # Verify file was copied from literature bucket to documents bucket
        mock_storage_client.copy_object.assert_awaited_once()
        copy_call = mock_storage_client.copy_object.call_args
        assert copy_call.kwargs["CopySource"]["Bucket"] == "literature"
        assert copy_call.kwargs["Bucket"] == "documents"

        # Verify traceability links created
        assert len(result["traceability_link_ids"]) == 2

        # Verify session.commit was called at the end
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_internalization_without_full_text(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """Internalization succeeds without file copy when no storage_path exists."""
        ingestion_record = _make_ingestion_record(storage_path=None)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00043",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
            )

        # No file copy attempted
        assert result["full_text_status"] == "unavailable"
        mock_storage_client.copy_object.assert_not_awaited()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_internalization_records_audit_event(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """Internalization logs audit event with correct action and details."""
        ingestion_record = _make_ingestion_record()

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00044",
        ), patch(
            "alcoabase.literature.search.services.literature_search_service.logger"
        ) as mock_logger:
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
            )

        # _log_audit_event logs via logger.info with action details
        mock_logger.info.assert_called()
        log_call_args = mock_logger.info.call_args
        # Verify the audit log contains internalization action
        assert "literature_internalized" in str(log_call_args)


# ---------------------------------------------------------------------------
# Test: Duplicate Internalization Detection
# Requirements: 4.3
# ---------------------------------------------------------------------------


class TestDuplicateInternalizationDetection:
    """Tests that attempting to internalize an already-internalized record is rejected."""

    @pytest.mark.asyncio
    async def test_duplicate_internalization_returns_existing_document_id(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Second internalization attempt raises DuplicateInternalizationError with existing ID."""
        ingestion_record = _make_ingestion_record()
        existing_doc_id = 777

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # IngestionRecord found
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                # Duplicate check: returns existing document ID
                return _make_scalar_result(existing_doc_id)
            return _make_scalar_result(None)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(DuplicateInternalizationError) as exc_info:
            await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.existing_document_id == existing_doc_id
        assert exc_info.value.ingestion_record_id == 42

        # No commit should have been called
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_duplicate_detection_does_not_create_document(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """When duplicate detected, no Document is created and no file is copied."""
        ingestion_record = _make_ingestion_record()

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(500)  # existing doc
            return _make_scalar_result(None)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(DuplicateInternalizationError):
            await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
            )

        # No file copy, no session add for Document
        mock_storage_client.copy_object.assert_not_awaited()
        mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Test: MinIO Failure Graceful Handling
# Requirements: 4.9
# ---------------------------------------------------------------------------


class TestMinIOFailureHandling:
    """Tests that internalization succeeds even when MinIO file copy fails."""

    @pytest.mark.asyncio
    async def test_minio_connection_refused_creates_document_with_unavailable_status(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """MinIO connection failure: Document created with full_text_status='unavailable'."""
        ingestion_record = _make_ingestion_record(
            storage_path="papers/2024/important.pdf",
        )

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)  # No duplicate
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_storage_client.copy_object = AsyncMock(
            side_effect=ConnectionError("MinIO connection refused")
        )

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00045",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
            )

        # Document created but full text unavailable
        assert result["full_text_status"] == "unavailable"
        assert result["document_name"] == "Machine Learning in Drug Discovery"
        assert result["current_status"] == "Draft"
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_minio_timeout_creates_document_with_unavailable_status(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """MinIO timeout: Document still created successfully."""
        ingestion_record = _make_ingestion_record(
            storage_path="papers/2024/timeout.pdf",
        )

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_storage_client.copy_object = AsyncMock(
            side_effect=TimeoutError("S3 operation timed out")
        )

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00046",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
            )

        assert result["full_text_status"] == "unavailable"
        assert result["source_ingestion_record_id"] == 42
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_minio_failure_still_creates_traceability_links(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """Even when MinIO fails, traceability links are still created."""
        ingestion_record = _make_ingestion_record(
            storage_path="papers/2024/failing.pdf",
        )

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)
        mock_storage_client.copy_object = AsyncMock(
            side_effect=OSError("Disk full")
        )

        # Track added objects for link ID assignment
        added_objects = []
        link_counter = [0]

        def track_add(obj):
            added_objects.append(obj)

        async def mock_flush():
            for obj in added_objects:
                if not hasattr(obj, "id") or obj.id is None:
                    link_counter[0] += 1
                    obj.id = link_counter[0]

        mock_session.add = MagicMock(side_effect=track_add)
        mock_session.flush = AsyncMock(side_effect=mock_flush)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00047",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
                traceability_links=[
                    {"target_type": "requirement", "target_id": 10},
                ],
            )

        assert result["full_text_status"] == "unavailable"
        assert len(result["traceability_link_ids"]) == 1
        mock_session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: Traceability Link Creation via TraceabilityMatrixService
# Requirements: 6.1, 6.2, 6.5, 6.8
# ---------------------------------------------------------------------------


class TestTraceabilityLinkCreation:
    """Tests for traceability link creation with internalized document validation."""

    @pytest.mark.asyncio
    async def test_create_traceability_links_for_internalized_document(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Traceability links created for a properly internalized document."""
        mock_document = MagicMock()
        mock_document.id = 10
        mock_document.company_id = 1
        mock_document.source_ingestion_record_id = 42  # Internalized

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_document))

        # Track link objects
        added_links = []
        link_counter = [0]

        def track_add(obj):
            added_links.append(obj)

        async def mock_flush():
            for obj in added_links:
                if not hasattr(obj, "id") or obj.id is None:
                    link_counter[0] += 1
                    obj.id = link_counter[0]

        mock_session.add = MagicMock(side_effect=track_add)
        mock_session.flush = AsyncMock(side_effect=mock_flush)

        result = await service.create_traceability_links(
            document_id=10,
            links=[
                {"target_type": "requirement", "target_id": 101, "rationale": "Primary evidence"},
                {"target_type": "test_case", "target_id": 202, "rationale": "Supports OQ-3"},
                {"target_type": "requirement", "target_id": 103},
            ],
            user_id=1,
            company_id=1,
        )

        assert len(result) == 3
        # Verify link objects have correct attributes
        assert added_links[0].link_method == "literature_evidence"
        assert added_links[0].link_confidence == 1.0
        assert added_links[0].target_type == "requirement"
        assert added_links[0].target_id == 101
        assert added_links[0].rationale == "Primary evidence"
        assert added_links[1].target_type == "test_case"
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_traceability_links_rejects_non_internalized_document(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Traceability link creation rejected for document without source_ingestion_record_id."""
        mock_document = MagicMock()
        mock_document.id = 10
        mock_document.company_id = 1
        mock_document.source_ingestion_record_id = None  # Not internalized

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_document))

        with pytest.raises(NonInternalizedDocumentError) as exc_info:
            await service.create_traceability_links(
                document_id=10,
                links=[{"target_type": "requirement", "target_id": 1}],
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.document_id == 10
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_traceability_links_document_not_found(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Traceability link creation raises ValueError if document doesn't exist."""
        mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

        with pytest.raises(ValueError, match="not found"):
            await service.create_traceability_links(
                document_id=999,
                links=[{"target_type": "requirement", "target_id": 1}],
                user_id=1,
                company_id=1,
            )


# ---------------------------------------------------------------------------
# Test: Non-Internalized Document Rejection
# Requirements: 5.9, 6.5
# ---------------------------------------------------------------------------


class TestNonInternalizedDocumentRejection:
    """Tests that operations requiring internalized documents reject non-internalized ones."""

    @pytest.mark.asyncio
    async def test_add_non_internalized_document_to_collection_rejected(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Adding non-internalized document to collection raises NonInternalizedDocumentError."""
        mock_collection = MagicMock()
        mock_collection.id = 1

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection lookup — found
                return _make_scalar_result(mock_collection)
            elif call_count[0] == 2:
                # Document lookup — returns doc without source_ingestion_record_id
                mock_result = MagicMock()
                mock_result.all.return_value = [(10, None)]  # (doc_id, source_ir_id=None)
                return mock_result
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(NonInternalizedDocumentError) as exc_info:
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[10],
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.document_id == 10
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_mixed_internalized_and_non_internalized_rejected(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """If any document in a batch is not internalized, the entire add is rejected."""
        mock_collection = MagicMock()
        mock_collection.id = 1

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(mock_collection)
            elif call_count[0] == 2:
                # Mixed: doc 10 internalized, doc 11 not
                mock_result = MagicMock()
                mock_result.all.return_value = [
                    (10, 42),   # internalized
                    (11, None),  # NOT internalized
                ]
                return mock_result
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(NonInternalizedDocumentError) as exc_info:
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[10, 11],
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.document_id == 11

    @pytest.mark.asyncio
    async def test_traceability_link_for_non_internalized_rejected(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Creating traceability link for non-internalized document raises NonInternalizedDocumentError."""
        mock_document = MagicMock()
        mock_document.id = 20
        mock_document.company_id = 1
        mock_document.source_ingestion_record_id = None

        mock_session.execute = AsyncMock(return_value=_make_scalar_result(mock_document))

        with pytest.raises(NonInternalizedDocumentError) as exc_info:
            await service.create_traceability_links(
                document_id=20,
                links=[
                    {"target_type": "requirement", "target_id": 1},
                    {"target_type": "test_case", "target_id": 2},
                ],
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.document_id == 20

    @pytest.mark.asyncio
    async def test_collection_capacity_enforcement_with_internalized_docs(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Adding documents exceeding 500 limit raises CollectionCapacityExceededError."""
        mock_collection = MagicMock()
        mock_collection.id = 1

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                # Collection lookup
                return _make_scalar_result(mock_collection)
            elif call_count[0] == 2:
                # Document lookup — internalized
                mock_result = MagicMock()
                mock_result.all.return_value = [(10, 42)]
                return mock_result
            elif call_count[0] == 3:
                # Current count at capacity
                return _make_scalar_result(500)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with pytest.raises(CollectionCapacityExceededError) as exc_info:
            await service.add_documents_to_collection(
                collection_id=1,
                document_ids=[10],
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.collection_id == 1
        assert exc_info.value.current_count == 500


# ---------------------------------------------------------------------------
# Test: IngestionRecord Not Found
# Requirements: 4.7
# ---------------------------------------------------------------------------


class TestIngestionRecordNotFound:
    """Tests for internalization when the IngestionRecord doesn't exist."""

    @pytest.mark.asyncio
    async def test_nonexistent_ingestion_record(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Internalization of nonexistent IngestionRecord raises IngestionRecordNotFoundError."""
        mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

        with pytest.raises(IngestionRecordNotFoundError) as exc_info:
            await service.internalize(
                ingestion_record_id=999,
                user_id=1,
                company_id=1,
            )

        assert exc_info.value.ingestion_record_id == 999

    @pytest.mark.asyncio
    async def test_ingestion_record_wrong_company(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
    ) -> None:
        """Internalization of IngestionRecord from different company raises NotFoundError."""
        # The query filters by company_id, so wrong company returns None
        mock_session.execute = AsyncMock(return_value=_make_scalar_result(None))

        with pytest.raises(IngestionRecordNotFoundError) as exc_info:
            await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=999,  # Wrong company
            )

        assert exc_info.value.ingestion_record_id == 42
        assert exc_info.value.company_id == 999


# ---------------------------------------------------------------------------
# Test: Multi-Step Error Path Validation
# Requirements: 4.1–4.10
# ---------------------------------------------------------------------------


class TestMultiStepErrorPaths:
    """Integration tests that validate error behavior across multi-step flows."""

    @pytest.mark.asyncio
    async def test_internalization_with_tags_and_collection_but_no_traceability(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """Internalization with partial optional fields: tags + collection, no traceability."""
        ingestion_record = _make_ingestion_record()

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00050",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
                tags=["review", "critical"],
                traceability_links=None,
                citation_collection_id=3,
            )

        assert result["tags"] == ["review", "critical"]
        assert result["traceability_link_ids"] == []
        assert result["citation_collection_id"] == 3
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_internalization_custom_document_name(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """Custom document_name overrides the IngestionRecord title."""
        ingestion_record = _make_ingestion_record(title="Original Title")

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00051",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
                document_name="My Custom Name",
            )

        assert result["document_name"] == "My Custom Name"

    @pytest.mark.asyncio
    async def test_internalization_with_empty_title_uses_fallback(
        self,
        service: LiteratureSearchService,
        mock_session: AsyncMock,
        mock_storage_client: AsyncMock,
    ) -> None:
        """When IngestionRecord title is None and no custom name, uses fallback."""
        ingestion_record = _make_ingestion_record(title=None)

        call_count = [0]

        async def mock_execute(stmt):
            call_count[0] += 1
            if call_count[0] == 1:
                return _make_scalar_result(ingestion_record)
            elif call_count[0] == 2:
                return _make_scalar_result(None)
            return _make_scalar_result(0)

        mock_session.execute = AsyncMock(side_effect=mock_execute)

        with patch(
            "alcoabase.literature.search.services.literature_search_service.LiteratureSearchService._generate_document_uuid",
            return_value="2024-00052",
        ):
            result = await service.internalize(
                ingestion_record_id=42,
                user_id=1,
                company_id=1,
                document_name=None,
            )

        assert result["document_name"] == "Untitled Literature"
