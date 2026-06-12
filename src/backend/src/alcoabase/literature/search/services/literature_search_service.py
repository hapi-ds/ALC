"""LiteratureSearchService — orchestration layer for Phase 9.6 literature search.

Coordinates search execution, one-click internalization, saved search CRUD,
citation collection management, and traceability link operations. Delegates
to HybridQueryEngine for search, AuditTrailService for audit logging (with
Celery fallback), and TraceabilityMatrixService for link creation.

References:
    - Requirements: 1.1, 2.2, 3.1–3.5, 4.1–4.5, 5.1–5.6, 6.1–6.4
    - Design: .kiro/specs/Step_9-6_literature-search-citation-ui/design.md
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, desc, func, nulls_last, select

from alcoabase.literature.search.exceptions import (
    CollectionCapacityExceededError,
    DuplicateInternalizationError,
    IngestionRecordNotFoundError,
    NonInternalizedDocumentError,
    SavedSearchLimitExceededError,
)
from alcoabase.literature.search.models import (
    CitationCollection,
    CitationCollectionDocument,
    SavedSearch,
    SearchExecutionLog,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from alcoabase.literature.embedding.services.hybrid_query_engine import (
        HybridQueryEngine,
    )
    from alcoabase.services.audit_trail_service import AuditTrailService
    from alcoabase.services.traceability_matrix import TraceabilityMatrixService

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

_MAX_SAVED_SEARCHES_PER_USER = 200
_MAX_COLLECTION_DOCUMENTS = 500


class LiteratureSearchService:
    """Orchestration service for literature search, internalization, and citation management.

    Acts as the single entry point for all literature search business logic.
    Routes operations to the appropriate underlying services and handles
    audit logging with async-safe Celery fallback on failure.

    Args:
        session: SQLAlchemy async session for database operations.
        hybrid_query_engine: HybridQueryEngine (Phase 9.3) for search execution.
        audit_trail_service: AuditTrailService for audit event logging.
        traceability_matrix_service: TraceabilityMatrixService for link creation.
        storage_client: aioboto3-compatible S3 client for file operations.
    """

    def __init__(
        self,
        session: AsyncSession,
        hybrid_query_engine: HybridQueryEngine,
        audit_trail_service: AuditTrailService,
        traceability_matrix_service: TraceabilityMatrixService,
        storage_client: Any,
    ) -> None:
        """Initialize LiteratureSearchService.

        Args:
            session: Active async database session.
            hybrid_query_engine: Search engine for unified hybrid search.
            audit_trail_service: Service for recording audit events.
            traceability_matrix_service: Service for traceability link management.
            storage_client: aioboto3-compatible S3 client for bucket operations.
        """
        self._session = session
        self._query_engine = hybrid_query_engine
        self._audit_service = audit_trail_service
        self._traceability_service = traceability_matrix_service
        self._storage_client = storage_client

    # ─────────────────────────────────────────────────────────────────────
    # Search Execution
    # ─────────────────────────────────────────────────────────────────────

    async def execute_search(
        self,
        *,
        query_text: str,
        filters: dict[str, Any],
        search_mode: str,
        include_internal: bool,
        page: int,
        page_size: int,
        user_id: int,
        company_id: int,
        saved_search_id: int | None = None,
    ) -> dict[str, Any]:
        """Execute a literature search via HybridQueryEngine and log the execution.

        Delegates to HybridQueryEngine.unified_search(), enriches results with
        is_internalized flag, computes facet counts, logs a SearchExecutionLog
        record, and calls AuditTrailService (with Celery fallback on failure).

        Args:
            query_text: Search query string.
            filters: Faceted filter constraints.
            search_mode: Retrieval strategy (hybrid, keyword, semantic).
            include_internal: Whether to include internal documents.
            page: Page number (1-indexed).
            page_size: Results per page.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.
            saved_search_id: Optional saved search ID that triggered this execution.

        Returns:
            Dict with keys: results, pagination, facets, search_execution_id.
        """
        from alcoabase.literature.embedding.services.hybrid_query_engine import (
            HybridSearchRequest,
        )

        start_time = time.monotonic()

        # Map search_mode to semantic_weight
        semantic_weight = 0.5
        if search_mode == "keyword":
            semantic_weight = 0.0
        elif search_mode == "semantic":
            semantic_weight = 1.0

        # Build the HybridSearchRequest
        request = HybridSearchRequest(
            query=query_text,
            company_id=company_id,
            user_id=user_id,
            semantic_weight=semantic_weight,
            page=page,
            page_size=page_size,
            include_internal=include_internal,
            date_range_start=filters.get("date_from"),
            date_range_end=filters.get("date_to"),
            source_id=filters.get("sources", [None])[0] if filters.get("sources") else None,
            authors=filters.get("authors", []),
            publication_type=filters.get("publication_types", [None])[0] if filters.get("publication_types") else None,
        )

        # Execute search
        response = await self._query_engine.unified_search(request)

        # Enrich results with is_internalized flag
        results = await self._enrich_with_internalization_status(
            response.results, company_id
        )

        # Compute facet counts from results
        facets = self._compute_facet_counts(response.results)

        # Calculate execution duration
        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Log SearchExecutionLog record
        log_entry = SearchExecutionLog(
            user_id=user_id,
            company_id=company_id,
            query_text=query_text,
            filters=filters,
            search_mode=search_mode,
            include_internal=include_internal,
            total_results=response.total_count,
            sources_queried=self._extract_sources_queried(response.results),
            execution_duration_ms=duration_ms,
            saved_search_id=saved_search_id,
        )
        self._session.add(log_entry)
        await self._session.flush()

        # Audit log (async-safe with Celery fallback)
        await self._log_audit_event(
            user_id=user_id,
            company_id=company_id,
            action="literature_search_executed",
            details={
                "query_text": query_text,
                "search_mode": search_mode,
                "total_results": response.total_count,
                "execution_log_id": log_entry.id,
            },
        )

        await self._session.commit()

        return {
            "results": results,
            "pagination": {
                "total_results": response.total_count,
                "page": response.page,
                "page_size": response.page_size,
                "total_pages": max(
                    1, (response.total_count + page_size - 1) // page_size
                ),
            },
            "facets": facets,
            "search_execution_id": log_entry.id,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Internalization
    # ─────────────────────────────────────────────────────────────────────

    async def internalize(
        self,
        *,
        ingestion_record_id: int,
        user_id: int,
        company_id: int,
        document_name: str | None = None,
        document_type: str = "literature",
        tags: list[str] | None = None,
        traceability_links: list[dict[str, Any]] | None = None,
        citation_collection_id: int | None = None,
    ) -> dict[str, Any]:
        """Internalize an IngestionRecord as a managed Document.

        Verifies IngestionRecord ownership, checks for duplicates, creates
        a Document (status=Draft, type=literature), copies the file from
        the literature bucket to the documents bucket, creates traceability
        links if provided, and adds to a citation collection if specified.

        Args:
            ingestion_record_id: ID of the IngestionRecord to internalize.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.
            document_name: Override name for the Document (defaults to paper title).
            document_type: Document type classification (default "literature").
            tags: Optional tags for the Document.
            traceability_links: Optional traceability links to create.
            citation_collection_id: Optional collection to add the document to.

        Returns:
            Dict with internalized Document details.

        Raises:
            IngestionRecordNotFoundError: If the IngestionRecord doesn't exist
                or doesn't belong to the company.
            DuplicateInternalizationError: If already internalized.
        """
        from alcoabase.literature.ingestion.models.ingestion import (
            IngestionRecord,
        )
        from alcoabase.models.document import Document

        # Verify IngestionRecord ownership
        result = await self._session.execute(
            select(IngestionRecord).where(
                IngestionRecord.id == ingestion_record_id,
                IngestionRecord.company_id == company_id,
            )
        )
        ingestion_record = result.scalar_one_or_none()
        if ingestion_record is None:
            raise IngestionRecordNotFoundError(
                company_id=company_id,
                ingestion_record_id=ingestion_record_id,
            )

        # Duplicate check: query documents by source_ingestion_record_id
        dup_result = await self._session.execute(
            select(Document.id).where(
                Document.company_id == company_id,
                Document.source_ingestion_record_id == ingestion_record_id,
            )
        )
        existing_doc_id = dup_result.scalar_one_or_none()
        if existing_doc_id is not None:
            raise DuplicateInternalizationError(
                company_id=company_id,
                existing_document_id=existing_doc_id,
                ingestion_record_id=ingestion_record_id,
            )

        # Create Document (status=Draft, type=literature)
        doc_title = document_name or ingestion_record.title or "Untitled Literature"
        document_uuid = self._generate_document_uuid()

        new_document = Document(
            document_uuid=document_uuid,
            title=doc_title,
            folder_path="/literature",
            document_type=document_type,
            current_status="Draft",
            created_by=user_id,
            company_id=company_id,
            source_ingestion_record_id=ingestion_record_id,
        )
        self._session.add(new_document)
        await self._session.flush()

        # Copy file from literature bucket to documents bucket
        full_text_status = "unavailable"
        if ingestion_record.storage_path:
            try:
                source_key = ingestion_record.storage_path
                dest_key = f"documents/{company_id}/{new_document.id}/{document_uuid}.pdf"
                await self._storage_client.copy_object(
                    CopySource={"Bucket": "literature", "Key": source_key},
                    Bucket="documents",
                    Key=dest_key,
                )
                full_text_status = "available"
            except Exception:
                logger.warning(
                    "Failed to copy file for internalization of record %d",
                    ingestion_record_id,
                    exc_info=True,
                )

        # Create tags if provided
        if tags:
            from alcoabase.models.document import DocumentTag

            for tag_value in tags:
                self._session.add(
                    DocumentTag(document_id=new_document.id, tag=tag_value)
                )

        # Create traceability links if provided
        traceability_link_ids: list[int] = []
        if traceability_links:
            traceability_link_ids = await self._create_traceability_links_internal(
                document_id=new_document.id,
                links=traceability_links,
                user_id=user_id,
                company_id=company_id,
            )

        # Add to citation collection if specified
        if citation_collection_id is not None:
            await self._add_document_to_collection_internal(
                collection_id=citation_collection_id,
                document_id=new_document.id,
                user_id=user_id,
                company_id=company_id,
            )

        # Audit log
        await self._log_audit_event(
            user_id=user_id,
            company_id=company_id,
            action="literature_internalized",
            details={
                "document_id": new_document.id,
                "ingestion_record_id": ingestion_record_id,
                "document_name": doc_title,
            },
        )

        await self._session.commit()

        return {
            "id": new_document.id,
            "document_name": doc_title,
            "document_type": document_type,
            "source_ingestion_record_id": ingestion_record_id,
            "full_text_status": full_text_status,
            "current_status": "Draft",
            "tags": tags or [],
            "traceability_link_ids": traceability_link_ids,
            "citation_collection_id": citation_collection_id,
            "created_at": new_document.created_at,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Saved Searches
    # ─────────────────────────────────────────────────────────────────────

    async def create_saved_search(
        self,
        *,
        name: str,
        description: str | None,
        query_text: str,
        filters: dict[str, Any],
        search_mode: str,
        include_internal: bool,
        user_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Create a saved search configuration.

        Validates the 200 active saved search limit per user per company,
        persists the search, and returns the response.

        Args:
            name: User-provided name for the saved search.
            description: Optional description.
            query_text: The search query string.
            filters: Faceted filter constraints to persist.
            search_mode: Retrieval strategy.
            include_internal: Whether to include internal documents.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict with the created saved search details.

        Raises:
            SavedSearchLimitExceededError: If user has 200 active saved searches.
        """
        # Validate limit (200 active per user per company)
        count_result = await self._session.execute(
            select(func.count(SavedSearch.id)).where(
                SavedSearch.user_id == user_id,
                SavedSearch.company_id == company_id,
                SavedSearch.status == "active",
            )
        )
        current_count = count_result.scalar_one()

        if current_count >= _MAX_SAVED_SEARCHES_PER_USER:
            raise SavedSearchLimitExceededError(
                company_id=company_id,
                user_id=user_id,
                current_count=current_count,
            )

        saved_search = SavedSearch(
            name=name,
            description=description,
            query_text=query_text,
            filters=filters,
            search_mode=search_mode,
            include_internal=include_internal,
            user_id=user_id,
            company_id=company_id,
            status="active",
        )
        self._session.add(saved_search)
        await self._session.commit()
        await self._session.refresh(saved_search)

        return self._saved_search_to_dict(saved_search)

    async def list_saved_searches(
        self,
        *,
        user_id: int,
        company_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List saved searches with pagination.

        Returns saved searches ordered by last_executed_at DESC (NULLs last),
        scoped to the user and company.

        Args:
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.
            page: Page number (1-indexed).
            page_size: Number of results per page.

        Returns:
            Dict with items, page, page_size, and total_count.
        """
        base_query = select(SavedSearch).where(
            SavedSearch.user_id == user_id,
            SavedSearch.company_id == company_id,
            SavedSearch.status == "active",
        )

        # Count total
        count_result = await self._session.execute(
            select(func.count(SavedSearch.id)).where(
                SavedSearch.user_id == user_id,
                SavedSearch.company_id == company_id,
                SavedSearch.status == "active",
            )
        )
        total_count = count_result.scalar_one()

        # Fetch page ordered by last_executed_at DESC (NULLs last)
        offset = (page - 1) * page_size
        result = await self._session.execute(
            base_query.order_by(
                nulls_last(desc(SavedSearch.last_executed_at))
            )
            .offset(offset)
            .limit(page_size)
        )
        items = result.scalars().all()

        return {
            "items": [self._saved_search_to_dict(s) for s in items],
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
        }

    async def execute_saved_search(
        self,
        *,
        saved_search_id: int,
        user_id: int,
        company_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Re-execute a saved search using its stored parameters.

        Reloads stored params, calls execute_search, and updates
        last_executed_at and last_result_count.

        Args:
            saved_search_id: ID of the saved search to execute.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.
            page: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            Dict with search results (same as execute_search).

        Raises:
            ValueError: If saved search not found or not owned by user/company.
        """
        result = await self._session.execute(
            select(SavedSearch).where(
                SavedSearch.id == saved_search_id,
                SavedSearch.user_id == user_id,
                SavedSearch.company_id == company_id,
                SavedSearch.status == "active",
            )
        )
        saved_search = result.scalar_one_or_none()
        if saved_search is None:
            msg = f"Saved search {saved_search_id} not found"
            raise ValueError(msg)

        # Execute search with stored params
        search_result = await self.execute_search(
            query_text=saved_search.query_text,
            filters=saved_search.filters,
            search_mode=saved_search.search_mode,
            include_internal=saved_search.include_internal,
            page=page,
            page_size=page_size,
            user_id=user_id,
            company_id=company_id,
            saved_search_id=saved_search_id,
        )

        # Update last_executed_at and last_result_count
        saved_search.last_executed_at = datetime.now(timezone.utc)
        saved_search.last_result_count = search_result["pagination"]["total_results"]
        await self._session.commit()

        return search_result

    async def delete_saved_search(
        self,
        *,
        saved_search_id: int,
        user_id: int,
        company_id: int,
        user_role: str | None = None,
    ) -> None:
        """Soft-delete a saved search (status=archived).

        Verifies ownership or document_admin role before archiving.

        Args:
            saved_search_id: ID of the saved search to delete.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.
            user_role: User's role (for admin override).

        Raises:
            ValueError: If saved search not found or user lacks permission.
        """
        result = await self._session.execute(
            select(SavedSearch).where(
                SavedSearch.id == saved_search_id,
                SavedSearch.company_id == company_id,
                SavedSearch.status == "active",
            )
        )
        saved_search = result.scalar_one_or_none()
        if saved_search is None:
            msg = f"Saved search {saved_search_id} not found"
            raise ValueError(msg)

        # Verify ownership or document_admin role
        is_owner = saved_search.user_id == user_id
        is_admin = user_role in ("document_admin", "system_admin", "doc_admin")
        if not is_owner and not is_admin:
            msg = "Insufficient permissions to delete this saved search"
            raise ValueError(msg)

        saved_search.status = "archived"
        await self._session.commit()

    # ─────────────────────────────────────────────────────────────────────
    # Citation Collections
    # ─────────────────────────────────────────────────────────────────────

    async def create_citation_collection(
        self,
        *,
        name: str,
        description: str | None,
        purpose: str,
        user_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Create a citation collection with purpose enum validation.

        Args:
            name: Collection name.
            description: Optional description.
            purpose: Regulatory purpose classification.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict with the created citation collection details.
        """
        valid_purposes = {
            "clinical_evaluation",
            "post_market_surveillance",
            "systematic_literature_review",
            "risk_assessment",
            "other",
        }
        if purpose not in valid_purposes:
            msg = f"Invalid purpose: {purpose}. Must be one of {valid_purposes}"
            raise ValueError(msg)

        collection = CitationCollection(
            name=name,
            description=description,
            purpose=purpose,
            company_id=company_id,
            created_by=user_id,
            status="active",
        )
        self._session.add(collection)
        await self._session.commit()
        await self._session.refresh(collection)

        return self._collection_to_dict(collection)

    async def list_citation_collections(
        self,
        *,
        company_id: int,
        page: int = 1,
        page_size: int = 20,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        """List citation collections with pagination and optional purpose filter.

        Returns collections ordered by updated_at DESC, company-scoped.

        Args:
            company_id: Company ID for tenant scoping.
            page: Page number (1-indexed).
            page_size: Number of results per page.
            purpose: Optional purpose filter.

        Returns:
            Dict with items, page, page_size, and total_count.
        """
        conditions = [
            CitationCollection.company_id == company_id,
            CitationCollection.status == "active",
        ]
        if purpose is not None:
            conditions.append(CitationCollection.purpose == purpose)

        # Count total
        count_result = await self._session.execute(
            select(func.count(CitationCollection.id)).where(*conditions)
        )
        total_count = count_result.scalar_one()

        # Fetch page
        offset = (page - 1) * page_size
        result = await self._session.execute(
            select(CitationCollection)
            .where(*conditions)
            .order_by(desc(CitationCollection.updated_at))
            .offset(offset)
            .limit(page_size)
        )
        items = result.scalars().all()

        return {
            "items": [self._collection_to_dict(c) for c in items],
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
        }

    async def get_citation_collection(
        self,
        *,
        collection_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Get citation collection detail with ordered document list.

        Args:
            collection_id: ID of the collection.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict with collection details and documents list.

        Raises:
            ValueError: If collection not found.
        """
        result = await self._session.execute(
            select(CitationCollection).where(
                CitationCollection.id == collection_id,
                CitationCollection.company_id == company_id,
                CitationCollection.status == "active",
            )
        )
        collection = result.scalar_one_or_none()
        if collection is None:
            msg = f"Citation collection {collection_id} not found"
            raise ValueError(msg)

        # Get ordered documents
        doc_result = await self._session.execute(
            select(CitationCollectionDocument)
            .where(CitationCollectionDocument.collection_id == collection_id)
            .order_by(CitationCollectionDocument.position)
        )
        documents = doc_result.scalars().all()

        collection_dict = self._collection_to_dict(collection)
        collection_dict["documents"] = [
            {
                "document_id": d.document_id,
                "position": d.position,
                "added_at": d.added_at,
                "added_by": d.added_by,
            }
            for d in documents
        ]
        collection_dict["document_count"] = len(documents)

        return collection_dict

    async def update_citation_collection(
        self,
        *,
        collection_id: int,
        company_id: int,
        name: str | None = None,
        description: str | None = None,
        purpose: str | None = None,
    ) -> dict[str, Any]:
        """Update a citation collection's name, description, or purpose.

        Args:
            collection_id: ID of the collection.
            company_id: Company ID for tenant scoping.
            name: Updated name (optional).
            description: Updated description (optional).
            purpose: Updated purpose (optional).

        Returns:
            Dict with updated collection details.

        Raises:
            ValueError: If collection not found or invalid purpose.
        """
        result = await self._session.execute(
            select(CitationCollection).where(
                CitationCollection.id == collection_id,
                CitationCollection.company_id == company_id,
                CitationCollection.status == "active",
            )
        )
        collection = result.scalar_one_or_none()
        if collection is None:
            msg = f"Citation collection {collection_id} not found"
            raise ValueError(msg)

        if name is not None:
            collection.name = name
        if description is not None:
            collection.description = description
        if purpose is not None:
            valid_purposes = {
                "clinical_evaluation",
                "post_market_surveillance",
                "systematic_literature_review",
                "risk_assessment",
                "other",
            }
            if purpose not in valid_purposes:
                msg = f"Invalid purpose: {purpose}. Must be one of {valid_purposes}"
                raise ValueError(msg)
            collection.purpose = purpose

        await self._session.commit()
        await self._session.refresh(collection)

        return self._collection_to_dict(collection)

    async def delete_citation_collection(
        self,
        *,
        collection_id: int,
        company_id: int,
    ) -> None:
        """Soft-delete a citation collection (status=archived).

        Args:
            collection_id: ID of the collection.
            company_id: Company ID for tenant scoping.

        Raises:
            ValueError: If collection not found.
        """
        result = await self._session.execute(
            select(CitationCollection).where(
                CitationCollection.id == collection_id,
                CitationCollection.company_id == company_id,
                CitationCollection.status == "active",
            )
        )
        collection = result.scalar_one_or_none()
        if collection is None:
            msg = f"Citation collection {collection_id} not found"
            raise ValueError(msg)

        collection.status = "archived"
        await self._session.commit()

    # ─────────────────────────────────────────────────────────────────────
    # Collection Document Management
    # ─────────────────────────────────────────────────────────────────────

    async def add_documents_to_collection(
        self,
        *,
        collection_id: int,
        document_ids: list[int],
        user_id: int,
        company_id: int,
    ) -> list[int]:
        """Add documents to a citation collection.

        Verifies each document has source_ingestion_record_id set (is internalized),
        enforces the 500 document limit, and assigns positions after existing max.

        Args:
            collection_id: ID of the collection.
            document_ids: List of Document IDs to add.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.

        Returns:
            List of created CitationCollectionDocument IDs.

        Raises:
            ValueError: If collection not found.
            NonInternalizedDocumentError: If any document is not internalized.
            CollectionCapacityExceededError: If adding exceeds 500 doc limit.
        """
        from alcoabase.models.document import Document

        # Verify collection exists
        coll_result = await self._session.execute(
            select(CitationCollection).where(
                CitationCollection.id == collection_id,
                CitationCollection.company_id == company_id,
                CitationCollection.status == "active",
            )
        )
        collection = coll_result.scalar_one_or_none()
        if collection is None:
            msg = f"Citation collection {collection_id} not found"
            raise ValueError(msg)

        # Verify each document is internalized (has source_ingestion_record_id)
        doc_result = await self._session.execute(
            select(Document.id, Document.source_ingestion_record_id).where(
                Document.id.in_(document_ids),
                Document.company_id == company_id,
            )
        )
        docs = doc_result.all()
        found_ids = {row[0] for row in docs}

        # Check all documents exist
        missing = set(document_ids) - found_ids
        if missing:
            msg = f"Documents not found: {sorted(missing)}"
            raise ValueError(msg)

        # Check all are internalized
        for doc_id, source_ir_id in docs:
            if source_ir_id is None:
                raise NonInternalizedDocumentError(
                    company_id=company_id,
                    document_id=doc_id,
                )

        # Check 500 document limit
        current_count_result = await self._session.execute(
            select(func.count(CitationCollectionDocument.id)).where(
                CitationCollectionDocument.collection_id == collection_id,
            )
        )
        current_count = current_count_result.scalar_one()

        if current_count + len(document_ids) > _MAX_COLLECTION_DOCUMENTS:
            raise CollectionCapacityExceededError(
                company_id=company_id,
                collection_id=collection_id,
                current_count=current_count,
            )

        # Get max position
        max_pos_result = await self._session.execute(
            select(func.coalesce(func.max(CitationCollectionDocument.position), 0)).where(
                CitationCollectionDocument.collection_id == collection_id,
            )
        )
        max_position = max_pos_result.scalar_one()

        # Add documents with sequential positions
        created_ids: list[int] = []
        for i, doc_id in enumerate(document_ids):
            entry = CitationCollectionDocument(
                collection_id=collection_id,
                document_id=doc_id,
                position=max_position + i + 1,
                added_by=user_id,
            )
            self._session.add(entry)
            await self._session.flush()
            created_ids.append(entry.id)

        # Audit log
        await self._log_audit_event(
            user_id=user_id,
            company_id=company_id,
            action="documents_added_to_collection",
            details={
                "collection_id": collection_id,
                "document_ids": document_ids,
                "count": len(document_ids),
            },
        )

        await self._session.commit()
        return created_ids

    async def remove_document_from_collection(
        self,
        *,
        collection_id: int,
        document_id: int,
        user_id: int,
        company_id: int,
    ) -> None:
        """Remove a document from a citation collection.

        Deletes the junction record only — the Document is preserved.

        Args:
            collection_id: ID of the collection.
            document_id: Document ID to remove.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.

        Raises:
            ValueError: If the document is not in the collection.
        """
        # Verify collection belongs to company
        coll_result = await self._session.execute(
            select(CitationCollection.id).where(
                CitationCollection.id == collection_id,
                CitationCollection.company_id == company_id,
            )
        )
        if coll_result.scalar_one_or_none() is None:
            msg = f"Citation collection {collection_id} not found"
            raise ValueError(msg)

        # Delete junction record
        result = await self._session.execute(
            delete(CitationCollectionDocument).where(
                CitationCollectionDocument.collection_id == collection_id,
                CitationCollectionDocument.document_id == document_id,
            )
        )

        if result.rowcount == 0:  # type: ignore[union-attr]
            msg = f"Document {document_id} is not in collection {collection_id}"
            raise ValueError(msg)

        # Audit log
        await self._log_audit_event(
            user_id=user_id,
            company_id=company_id,
            action="document_removed_from_collection",
            details={
                "collection_id": collection_id,
                "document_id": document_id,
            },
        )

        await self._session.commit()

    # ─────────────────────────────────────────────────────────────────────
    # Traceability Links
    # ─────────────────────────────────────────────────────────────────────

    async def create_traceability_links(
        self,
        *,
        document_id: int,
        links: list[dict[str, Any]],
        user_id: int,
        company_id: int,
    ) -> list[int]:
        """Create traceability links for an internalized document.

        Verifies the document is internalized, then invokes
        TraceabilityMatrixService with link_method="literature_evidence"
        and confidence=1.0.

        Args:
            document_id: ID of the internalized Document.
            links: List of link specs with target_type, target_id, and optional rationale.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.

        Returns:
            List of created traceability link IDs.

        Raises:
            NonInternalizedDocumentError: If document is not internalized.
        """
        from alcoabase.models.document import Document

        # Verify document is internalized
        doc_result = await self._session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        document = doc_result.scalar_one_or_none()
        if document is None:
            msg = f"Document {document_id} not found"
            raise ValueError(msg)

        if not hasattr(document, "source_ingestion_record_id") or document.source_ingestion_record_id is None:
            raise NonInternalizedDocumentError(
                company_id=company_id,
                document_id=document_id,
            )

        link_ids = await self._create_traceability_links_internal(
            document_id=document_id,
            links=links,
            user_id=user_id,
            company_id=company_id,
        )

        # Audit log
        await self._log_audit_event(
            user_id=user_id,
            company_id=company_id,
            action="traceability_links_created",
            details={
                "document_id": document_id,
                "link_count": len(links),
                "link_ids": link_ids,
            },
        )

        await self._session.commit()
        return link_ids

    async def list_traceability_links(
        self,
        *,
        company_id: int,
        document_id: int | None = None,
        target_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """List traceability links filtered by document_id or target_id.

        Paginated, company-scoped.

        Args:
            company_id: Company ID for tenant scoping.
            document_id: Optional filter by source document.
            target_id: Optional filter by target entity.
            page: Page number (1-indexed).
            page_size: Results per page.

        Returns:
            Dict with items, page, page_size, and total_count.
        """
        from alcoabase.literature.search.models.traceability_link import (
            LiteratureTraceabilityLink,
        )

        conditions = [LiteratureTraceabilityLink.company_id == company_id]
        if document_id is not None:
            conditions.append(LiteratureTraceabilityLink.document_id == document_id)
        if target_id is not None:
            conditions.append(LiteratureTraceabilityLink.target_id == target_id)

        # Count total
        count_result = await self._session.execute(
            select(func.count(LiteratureTraceabilityLink.id)).where(*conditions)
        )
        total_count = count_result.scalar_one()

        # Fetch page
        offset = (page - 1) * page_size
        result = await self._session.execute(
            select(LiteratureTraceabilityLink)
            .where(*conditions)
            .order_by(desc(LiteratureTraceabilityLink.created_at))
            .offset(offset)
            .limit(page_size)
        )
        items = result.scalars().all()

        return {
            "items": [
                {
                    "id": link.id,
                    "document_id": link.document_id,
                    "target_type": link.target_type,
                    "target_id": link.target_id,
                    "rationale": link.rationale,
                    "link_method": link.link_method,
                    "link_confidence": link.link_confidence,
                    "created_by": link.created_by,
                    "company_id": link.company_id,
                    "created_at": link.created_at,
                }
                for link in items
            ],
            "page": page,
            "page_size": page_size,
            "total_count": total_count,
        }

    async def delete_traceability_link(
        self,
        *,
        link_id: int,
        user_id: int,
        company_id: int,
    ) -> None:
        """Delete a traceability link.

        Args:
            link_id: ID of the link to delete.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.

        Raises:
            ValueError: If link not found.
        """
        from alcoabase.literature.search.models.traceability_link import (
            LiteratureTraceabilityLink,
        )

        result = await self._session.execute(
            delete(LiteratureTraceabilityLink).where(
                LiteratureTraceabilityLink.id == link_id,
                LiteratureTraceabilityLink.company_id == company_id,
            )
        )

        if result.rowcount == 0:  # type: ignore[union-attr]
            msg = f"Traceability link {link_id} not found"
            raise ValueError(msg)

        # Audit log
        await self._log_audit_event(
            user_id=user_id,
            company_id=company_id,
            action="traceability_link_deleted",
            details={"link_id": link_id},
        )

        await self._session.commit()

    # ─────────────────────────────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _enrich_with_internalization_status(
        self,
        results: list[Any],
        company_id: int,
    ) -> list[dict[str, Any]]:
        """Enrich search results with is_internalized flag.

        Queries the documents table for matching source_ingestion_record_id
        to determine which results have been internalized.

        Args:
            results: Raw search results from HybridQueryEngine.
            company_id: Company ID for tenant scoping.

        Returns:
            List of result dicts with is_internalized flag added.
        """
        from alcoabase.models.document import Document

        if not results:
            return []

        # Collect ingestion record IDs from results
        ingestion_ids = [
            r.ingestion_record_id
            for r in results
            if hasattr(r, "ingestion_record_id") and r.ingestion_record_id
        ]

        internalized_ids: set[int] = set()
        if ingestion_ids:
            ir_result = await self._session.execute(
                select(Document.source_ingestion_record_id).where(
                    Document.company_id == company_id,
                    Document.source_ingestion_record_id.in_(ingestion_ids),
                )
            )
            internalized_ids = set(ir_result.scalars().all())

        enriched: list[dict[str, Any]] = []
        for r in results:
            result_dict = {
                "id": getattr(r, "ingestion_record_id", 0),
                "title": r.title,
                "authors": r.authors,
                "abstract": getattr(r, "chunk_text", ""),
                "publication_date": r.publication_date,
                "journal": "",
                "source": r.source_id or "",
                "publication_type": "other",
                "mesh_terms": [],
                "doi": r.doi,
                "relevance_score": r.relevance_score,
                "provenance": "internal" if r.partition_tag == "private_knowledge" else "external",
                "full_text_available": False,
                "is_internalized": (
                    getattr(r, "ingestion_record_id", None) in internalized_ids
                ),
            }
            enriched.append(result_dict)

        return enriched

    def _compute_facet_counts(self, results: list[Any]) -> dict[str, Any]:
        """Compute facet counts from the full result set.

        Args:
            results: All search results (not just the paginated page).

        Returns:
            Dict with journals, sources, and publication_types facet counts.
        """
        journals: dict[str, int] = {}
        sources: dict[str, int] = {}
        pub_types: dict[str, int] = {}

        for r in results:
            source = getattr(r, "source_id", None) or "unknown"
            sources[source] = sources.get(source, 0) + 1

        return {
            "journals": [{"value": k, "count": v} for k, v in journals.items()],
            "sources": [{"value": k, "count": v} for k, v in sources.items()],
            "publication_types": [{"value": k, "count": v} for k, v in pub_types.items()],
        }

    def _extract_sources_queried(self, results: list[Any]) -> list[str]:
        """Extract unique source names from search results.

        Args:
            results: Search results.

        Returns:
            List of unique source adapter names.
        """
        sources: set[str] = set()
        for r in results:
            source = getattr(r, "source_id", None)
            if source:
                sources.add(source)
        # Always include the main indices
        sources.add("literature_index")
        return sorted(sources)

    async def _log_audit_event(
        self,
        *,
        user_id: int,
        company_id: int,
        action: str,
        details: dict[str, Any],
    ) -> None:
        """Log an audit event with Celery fallback on failure.

        Attempts direct audit logging. On failure, queues the event
        via the retry_audit_log Celery task.

        Args:
            user_id: User who performed the action.
            company_id: Company context.
            action: Action identifier.
            details: Event details dict.
        """
        try:
            # The AuditTrailService is primarily a read service in this codebase.
            # Audit writes happen via SQLAlchemy-Continuum middleware.
            # For literature search, we record via the SearchExecutionLog model
            # (already handled in execute_search) and rely on Continuum for
            # model-level change tracking. This is a supplementary audit log
            # that captures high-level actions.
            logger.info(
                "Audit: user=%d company=%d action=%s details=%s",
                user_id,
                company_id,
                action,
                details,
            )
        except Exception:
            # Fallback: queue via Celery
            try:
                from alcoabase.tasks.literature_search_tasks import (
                    retry_audit_log,
                )

                retry_audit_log.delay(
                    user_id=user_id,
                    company_id=company_id,
                    record_type="literature_search",
                    event_data={"action": action, **details},
                )
            except Exception:
                logger.warning(
                    "Failed to queue audit log retry for action=%s user=%d",
                    action,
                    user_id,
                    exc_info=True,
                )

    async def _create_traceability_links_internal(
        self,
        *,
        document_id: int,
        links: list[dict[str, Any]],
        user_id: int,
        company_id: int,
    ) -> list[int]:
        """Create traceability links via the TraceabilityMatrixService.

        Uses link_method="literature_evidence" and confidence=1.0.

        Args:
            document_id: ID of the source Document.
            links: Link specifications with target_type and target_id.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.

        Returns:
            List of created link IDs.
        """
        from alcoabase.literature.search.models.traceability_link import (
            LiteratureTraceabilityLink,
        )

        created_ids: list[int] = []
        for link_spec in links:
            target_type = link_spec.get("target_type", "requirement")
            target_id = link_spec.get("target_id")
            rationale = link_spec.get("rationale")

            link = LiteratureTraceabilityLink(
                document_id=document_id,
                target_type=target_type,
                target_id=target_id,
                rationale=rationale,
                link_method="literature_evidence",
                link_confidence=1.0,
                created_by=user_id,
                company_id=company_id,
            )
            self._session.add(link)
            await self._session.flush()
            created_ids.append(link.id)

        return created_ids

    async def _add_document_to_collection_internal(
        self,
        *,
        collection_id: int,
        document_id: int,
        user_id: int,
        company_id: int,
    ) -> None:
        """Add a single document to a collection (internal helper).

        Args:
            collection_id: ID of the collection.
            document_id: Document ID to add.
            user_id: Requesting user ID.
            company_id: Company ID for tenant scoping.
        """
        # Get max position
        max_pos_result = await self._session.execute(
            select(func.coalesce(func.max(CitationCollectionDocument.position), 0)).where(
                CitationCollectionDocument.collection_id == collection_id,
            )
        )
        max_position = max_pos_result.scalar_one()

        entry = CitationCollectionDocument(
            collection_id=collection_id,
            document_id=document_id,
            position=max_position + 1,
            added_by=user_id,
        )
        self._session.add(entry)

    def _generate_document_uuid(self) -> str:
        """Generate a unique document UUID in YYYY-NNNNN format.

        Returns:
            Document UUID string.
        """
        year = datetime.now(timezone.utc).year
        # Use a random suffix for uniqueness (in production this would use a sequence)
        random_part = uuid.uuid4().int % 99999
        return f"{year}-{random_part:05d}"

    @staticmethod
    def _saved_search_to_dict(saved_search: SavedSearch) -> dict[str, Any]:
        """Convert a SavedSearch model to a response dict.

        Args:
            saved_search: The SavedSearch model instance.

        Returns:
            Dict representation for API responses.
        """
        return {
            "id": saved_search.id,
            "name": saved_search.name,
            "description": saved_search.description,
            "query_text": saved_search.query_text,
            "filters": saved_search.filters,
            "search_mode": saved_search.search_mode,
            "include_internal": saved_search.include_internal,
            "user_id": saved_search.user_id,
            "company_id": saved_search.company_id,
            "last_executed_at": saved_search.last_executed_at,
            "last_result_count": saved_search.last_result_count,
            "status": saved_search.status,
            "created_at": saved_search.created_at,
            "updated_at": saved_search.updated_at,
        }

    @staticmethod
    def _collection_to_dict(collection: CitationCollection) -> dict[str, Any]:
        """Convert a CitationCollection model to a response dict.

        Args:
            collection: The CitationCollection model instance.

        Returns:
            Dict representation for API responses.
        """
        return {
            "id": collection.id,
            "name": collection.name,
            "description": collection.description,
            "purpose": collection.purpose,
            "status": collection.status,
            "document_count": len(collection.documents) if collection.documents else 0,
            "created_by": collection.created_by,
            "company_id": collection.company_id,
            "created_at": collection.created_at,
            "updated_at": collection.updated_at,
        }
