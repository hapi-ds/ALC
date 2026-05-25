"""Dependency Graph Service for AI-Driven Change Impact Analysis.

Builds and maintains a directed dependency graph between documents within
a company scope. Uses CrossReferenceService for explicit reference detection,
KnowledgeService for semantic similarity, and database queries for
TrainingTask/GenerationProvenance relationships.

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.10, 1.12, 1.13, 1.14
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.document_generation import GenerationProvenance
from alcoabase.models.impact_analysis import DependencyEdge
from alcoabase.models.training import TrainingTask
from alcoabase.schemas.impact_analysis import GraphFilters, PaginationParams
from alcoabase.services.cross_reference import CrossReferenceService
from alcoabase.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)

# Timeout for dependency graph builds (seconds)
BUILD_TIMEOUT_SECONDS = 300

# Minimum embedding similarity threshold for creating semantic edges
SEMANTIC_SIMILARITY_THRESHOLD = 0.5

# Valid dependency types
VALID_DEPENDENCY_TYPES = frozenset(
    {"validates", "references", "implements", "trains_on", "derived_from"}
)

# Document type patterns for dependency type classification
_VALIDATION_DOC_TYPES = frozenset({"MVP", "IQ", "OQ", "PQ"})
_URS_DOC_TYPES = frozenset({"URS"})


class DependencyGraphService:
    """Service for building and querying the document dependency graph.

    Constructs directed edges between documents based on:
    - Explicit cross-references (confidence 1.0)
    - Database-linked relationships via TrainingTask/GenerationProvenance (confidence 0.9)
    - Semantic similarity via embeddings (confidence 0.5-0.8)

    The service supports two usage patterns:
    - Query methods (get_edges, get_document_dependencies) accept a session directly
    - Build methods (build_full_graph, build_incremental_graph) use the session_factory

    Args:
        session_factory: Async session factory for database operations (optional for query-only use).
        cross_reference_service: Service for extracting cross-references (optional for query-only use).
        knowledge_service: Service for text extraction and semantic search (optional for query-only use).
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        cross_reference_service: CrossReferenceService | None = None,
        knowledge_service: KnowledgeService | None = None,
    ) -> None:
        """Initialize DependencyGraphService.

        Args:
            session_factory: Async session factory for database operations.
            cross_reference_service: Service for extracting cross-references.
            knowledge_service: Service for text extraction and semantic search.
        """
        self._session_factory = session_factory
        self._cross_reference_service = cross_reference_service
        self._knowledge_service = knowledge_service

    async def build_full_graph(
        self,
        company_id: int,
    ) -> dict:
        """Build the complete dependency graph for a company.

        Scans all documents within the company scope, extracts cross-references
        via CrossReferenceService, computes semantic similarity via
        KnowledgeService, and creates/updates edges.

        Args:
            company_id: ID of the company to build the graph for.

        Returns:
            Dict with build results:
                - status: "completed" or "partial_success"
                - edges_created: Number of edges created/updated
                - documents_processed: Number of documents processed
                - skipped_documents: List of document UUIDs that failed
                - unprocessed_documents: List of UUIDs not processed (timeout)
        """
        start_time = time.monotonic()
        edges_created = 0
        documents_processed = 0
        skipped_documents: list[str] = []
        unprocessed_documents: list[str] = []

        async with self._session_factory() as session:
            # Get all documents in the company scope
            result = await session.execute(
                select(Document).where(Document.company_id == company_id)
            )
            documents = list(result.scalars().all())

            # Build edges from DB-linked relationships (TrainingTask, GenerationProvenance)
            db_edges = await self._build_db_linked_edges(session, company_id)
            for edge_data in db_edges:
                await self._upsert_edge(session, edge_data)
                edges_created += 1

            # Process each document for cross-references and semantic similarity
            for doc in documents:
                # Check timeout
                elapsed = time.monotonic() - start_time
                if elapsed >= BUILD_TIMEOUT_SECONDS:
                    unprocessed_documents.append(doc.document_uuid)
                    continue

                try:
                    doc_edges = await self._process_document_edges(
                        session, doc, documents, company_id
                    )
                    for edge_data in doc_edges:
                        await self._upsert_edge(session, edge_data)
                        edges_created += 1
                    documents_processed += 1
                except Exception:
                    logger.warning(
                        "Failed to process document %s for dependency graph, skipping",
                        doc.document_uuid,
                    )
                    skipped_documents.append(doc.document_uuid)
                    continue

            await session.commit()

        status = "partial_success" if unprocessed_documents else "completed"
        return {
            "status": status,
            "edges_created": edges_created,
            "documents_processed": documents_processed,
            "skipped_documents": skipped_documents,
            "unprocessed_documents": unprocessed_documents,
        }

    async def build_incremental_graph(
        self,
        company_id: int,
        last_build_at: datetime | None = None,
    ) -> dict:
        """Build an incremental dependency graph update for a company.

        Scans only documents modified since the last successful build,
        prunes stale edges whose detected_references are no longer present,
        and creates/updates new edges.

        If no previous successful build exists (last_build_at is None),
        delegates to build_full_graph.

        Args:
            company_id: ID of the company to build the graph for.
            last_build_at: Timestamp of the last successful build (None for first build).

        Returns:
            Dict with build results (same structure as build_full_graph).
        """
        if last_build_at is None:
            return await self.build_full_graph(company_id)

        start_time = time.monotonic()
        edges_created = 0
        edges_pruned = 0
        documents_processed = 0
        skipped_documents: list[str] = []
        unprocessed_documents: list[str] = []

        async with self._session_factory() as session:
            # Get documents modified since last build
            modified_docs_result = await session.execute(
                select(Document)
                .where(
                    Document.company_id == company_id,
                )
                .join(
                    DocumentVersion,
                    DocumentVersion.document_id == Document.id,
                )
                .where(
                    DocumentVersion.uploaded_at > last_build_at,
                )
                .distinct()
            )
            modified_documents = list(modified_docs_result.scalars().all())

            if not modified_documents:
                return {
                    "status": "completed",
                    "edges_created": 0,
                    "edges_pruned": 0,
                    "documents_processed": 0,
                    "skipped_documents": [],
                    "unprocessed_documents": [],
                }

            # Get all documents for cross-reference matching
            all_docs_result = await session.execute(
                select(Document).where(Document.company_id == company_id)
            )
            all_documents = list(all_docs_result.scalars().all())

            # Rebuild DB-linked edges (always refresh these)
            db_edges = await self._build_db_linked_edges(session, company_id)
            for edge_data in db_edges:
                await self._upsert_edge(session, edge_data)
                edges_created += 1

            # Process each modified document
            for doc in modified_documents:
                elapsed = time.monotonic() - start_time
                if elapsed >= BUILD_TIMEOUT_SECONDS:
                    unprocessed_documents.append(doc.document_uuid)
                    continue

                try:
                    # Prune stale edges from this document
                    pruned = await self._prune_stale_edges(
                        session, doc, company_id
                    )
                    edges_pruned += pruned

                    # Build new edges
                    doc_edges = await self._process_document_edges(
                        session, doc, all_documents, company_id
                    )
                    for edge_data in doc_edges:
                        await self._upsert_edge(session, edge_data)
                        edges_created += 1
                    documents_processed += 1
                except Exception:
                    logger.warning(
                        "Failed to process document %s during incremental build, skipping",
                        doc.document_uuid,
                    )
                    skipped_documents.append(doc.document_uuid)
                    continue

            await session.commit()

        status = "partial_success" if unprocessed_documents else "completed"
        return {
            "status": status,
            "edges_created": edges_created,
            "edges_pruned": edges_pruned,
            "documents_processed": documents_processed,
            "skipped_documents": skipped_documents,
            "unprocessed_documents": unprocessed_documents,
        }

    async def _build_db_linked_edges(
        self,
        session: AsyncSession,
        company_id: int,
    ) -> list[dict]:
        """Build edges from database-linked relationships.

        Queries TrainingTask and GenerationProvenance records to create
        "trains_on" and "derived_from" edges with confidence 0.9.

        Args:
            session: Active database session.
            company_id: Company ID for tenant scoping.

        Returns:
            List of edge data dicts ready for upsert.
        """
        edges: list[dict] = []
        now = datetime.now(timezone.utc)

        # TrainingTask → trains_on edges
        training_result = await session.execute(
            select(TrainingTask.sop_document_uuid)
            .where(TrainingTask.company_id == company_id)
            .distinct()
        )
        training_sop_uuids = list(training_result.scalars().all())

        for sop_uuid in training_sop_uuids:
            # Create a trains_on edge from the SOP to a virtual training node
            # We use the sop_uuid as both source and represent training as target
            # Per design: "trains_on" edges from SOP to training task group
            edges.append(
                {
                    "source_document_uuid": sop_uuid,
                    "target_document_uuid": f"TT-{sop_uuid}",
                    "dependency_type": "trains_on",
                    "confidence_score": 0.9,
                    "detected_references": [f"TrainingTask:{sop_uuid}"],
                    "last_verified_at": now,
                    "company_id": company_id,
                }
            )

        # GenerationProvenance → derived_from edges
        provenance_result = await session.execute(
            select(GenerationProvenance)
            .where(GenerationProvenance.company_id == company_id)
            .where(GenerationProvenance.document_id.isnot(None))
        )
        provenance_records = list(provenance_result.scalars().all())

        for prov in provenance_records:
            # Get the generated document's UUID
            gen_doc_result = await session.execute(
                select(Document.document_uuid).where(
                    Document.id == prov.document_id
                )
            )
            gen_doc_uuid = gen_doc_result.scalar_one_or_none()
            if not gen_doc_uuid:
                continue

            # Create derived_from edges from generated doc to each source doc
            source_uuids = prov.source_document_uuids or []
            for source_uuid in source_uuids:
                edges.append(
                    {
                        "source_document_uuid": source_uuid,
                        "target_document_uuid": gen_doc_uuid,
                        "dependency_type": "derived_from",
                        "confidence_score": 0.9,
                        "detected_references": [
                            f"GenerationProvenance:{prov.generation_id}"
                        ],
                        "last_verified_at": now,
                        "company_id": company_id,
                    }
                )

        return edges

    async def _process_document_edges(
        self,
        session: AsyncSession,
        doc: Document,
        all_documents: list[Document],
        company_id: int,
    ) -> list[dict]:
        """Process a single document to extract dependency edges.

        Extracts cross-references from the document text and classifies
        dependency types based on reference patterns and document types.

        Args:
            session: Active database session.
            doc: The document to process.
            all_documents: All documents in the company for matching.
            company_id: Company ID for tenant scoping.

        Returns:
            List of edge data dicts ready for upsert.
        """
        edges: list[dict] = []
        now = datetime.now(timezone.utc)

        # Get the latest version's text content
        text = await self._get_document_text(session, doc)
        if not text:
            return edges

        # Extract cross-references from the document text
        references = self._cross_reference_service.extract_references_from_text(
            text=text,
            document_id=doc.id,
            document_title=doc.title,
        )

        # Build a lookup of document_uuid → Document for matching
        uuid_to_doc = {d.document_uuid: d for d in all_documents}
        title_to_doc = {d.title.lower(): d for d in all_documents}

        # Process explicit cross-references (confidence 1.0)
        for ref in references:
            target_doc = self._find_target_document(
                ref, uuid_to_doc, title_to_doc, doc, all_documents
            )
            if target_doc is None:
                continue

            dep_type = self._classify_dependency_type(
                ref, doc, target_doc
            )
            edges.append(
                {
                    "source_document_uuid": doc.document_uuid,
                    "target_document_uuid": target_doc.document_uuid,
                    "dependency_type": dep_type,
                    "confidence_score": 1.0,
                    "detected_references": [ref.reference_identifier],
                    "last_verified_at": now,
                    "company_id": company_id,
                }
            )

        # Compute semantic similarity edges (confidence 0.5-0.8)
        semantic_edges = await self._compute_semantic_edges(
            doc, all_documents, company_id, text
        )
        edges.extend(semantic_edges)

        return edges

    async def _get_document_text(
        self,
        session: AsyncSession,
        doc: Document,
    ) -> str | None:
        """Get the text content of a document's latest version.

        Args:
            session: Active database session.
            doc: The document to extract text from.

        Returns:
            Extracted text content, or None if extraction fails.
        """
        try:
            # Get the latest version
            version_result = await session.execute(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == doc.id)
                .order_by(DocumentVersion.uploaded_at.desc())
                .limit(1)
            )
            latest_version = version_result.scalar_one_or_none()
            if not latest_version:
                return None

            # Use KnowledgeService to get indexed text if available
            # Fall back to searching the knowledge index
            results, _ = self._knowledge_service.hybrid_search(
                query=doc.title,
                user_id=0,  # System-level access
                limit=1,
                filters={"document_uuid": [doc.document_uuid]},
            )
            if results:
                return results[0].excerpt

            return None
        except Exception:
            logger.warning(
                "Failed to extract text for document %s",
                doc.document_uuid,
            )
            return None

    def _find_target_document(
        self,
        ref,
        uuid_to_doc: dict[str, Document],
        title_to_doc: dict[str, Document],
        source_doc: Document,
        all_documents: list[Document],
    ) -> Document | None:
        """Find the target document for a cross-reference.

        Matches references by document_uuid, title mention, or requirement/test
        case ID patterns against other documents in the company.

        Args:
            ref: The CrossReference to match.
            uuid_to_doc: Lookup by document_uuid.
            title_to_doc: Lookup by lowercase title.
            source_doc: The source document (to exclude self-references).
            all_documents: All documents for pattern matching.

        Returns:
            The matched Document, or None if no match found.
        """
        # Check if the reference identifier is a document UUID
        if ref.reference_identifier in uuid_to_doc:
            target = uuid_to_doc[ref.reference_identifier]
            if target.id != source_doc.id:
                return target

        # Check if the reference text mentions a document title
        ref_text_lower = ref.reference_text.lower()
        for title_lower, target_doc in title_to_doc.items():
            if target_doc.id == source_doc.id:
                continue
            if title_lower in ref_text_lower:
                return target_doc

        # For requirement/test case references, find documents that likely
        # contain the referenced item based on document type
        if ref.reference_type == "requirement":
            # Requirements are typically in URS documents
            for target_doc in all_documents:
                if target_doc.id == source_doc.id:
                    continue
                if target_doc.document_type in _URS_DOC_TYPES:
                    return target_doc

        if ref.reference_type == "test_case":
            # Test cases are typically in validation documents
            for target_doc in all_documents:
                if target_doc.id == source_doc.id:
                    continue
                if target_doc.document_type in _VALIDATION_DOC_TYPES:
                    return target_doc

        return None

    def _classify_dependency_type(
        self,
        ref,
        source_doc: Document,
        target_doc: Document,
    ) -> str:
        """Classify the dependency type based on reference and document types.

        Classification rules:
        - "validates": requirement ID cross-refs between MVP/IQ/OQ/PQ and URS
        - "references": explicit document_uuid citations or title mentions
        - "implements": test case IDs referencing requirement IDs
        - "trains_on": TrainingTask records (handled in _build_db_linked_edges)
        - "derived_from": GenerationProvenance records (handled in _build_db_linked_edges)

        Args:
            ref: The CrossReference being classified.
            source_doc: The source document.
            target_doc: The target document.

        Returns:
            The dependency type string.
        """
        # Validates: validation doc referencing URS requirements
        if (
            source_doc.document_type in _VALIDATION_DOC_TYPES
            and target_doc.document_type in _URS_DOC_TYPES
            and ref.reference_type == "requirement"
        ):
            return "validates"

        # Implements: test case IDs referencing requirement IDs
        if ref.reference_type == "test_case":
            return "implements"

        # Validates: URS doc referenced by validation doc (reverse direction)
        if (
            source_doc.document_type in _URS_DOC_TYPES
            and target_doc.document_type in _VALIDATION_DOC_TYPES
            and ref.reference_type == "requirement"
        ):
            return "validates"

        # Default: references (explicit document_uuid citations or title mentions)
        return "references"

    async def _compute_semantic_edges(
        self,
        doc: Document,
        all_documents: list[Document],
        company_id: int,
        doc_text: str,
    ) -> list[dict]:
        """Compute semantic similarity edges between documents.

        Uses KnowledgeService embeddings to find semantically similar
        documents. Creates edges with confidence 0.5-0.8 based on
        similarity score. Rejects candidates below 0.5 threshold.

        Args:
            doc: The source document.
            all_documents: All documents in the company.
            company_id: Company ID for tenant scoping.
            doc_text: Text content of the source document.

        Returns:
            List of edge data dicts for semantic relationships.
        """
        edges: list[dict] = []
        now = datetime.now(timezone.utc)

        if not doc_text or len(doc_text.strip()) < 50:
            return edges

        try:
            # Generate embedding for the source document
            source_embeddings = await self._knowledge_service.generate_embeddings(
                [doc_text[:2000]]  # Use first 2000 chars for efficiency
            )
            if not source_embeddings:
                return edges

            # Compare against other documents via hybrid search
            # Use the document title + first section as query
            search_query = f"{doc.title} {doc_text[:200]}"
            results, _ = self._knowledge_service.hybrid_search(
                query=search_query,
                user_id=0,  # System-level access
                limit=20,
            )

            for result in results:
                # Skip self-references
                if result.document_uuid == doc.document_uuid:
                    continue

                # Map relevance_score to confidence (0.5-0.8 range)
                similarity = result.relevance_score
                if similarity < SEMANTIC_SIMILARITY_THRESHOLD:
                    continue

                # Scale similarity from [0.5, 1.0] to [0.5, 0.8]
                confidence = 0.5 + (similarity - 0.5) * 0.6
                confidence = min(confidence, 0.8)

                edges.append(
                    {
                        "source_document_uuid": doc.document_uuid,
                        "target_document_uuid": result.document_uuid,
                        "dependency_type": "references",
                        "confidence_score": round(confidence, 3),
                        "detected_references": [
                            f"semantic:{doc.document_uuid}->{result.document_uuid}"
                        ],
                        "last_verified_at": now,
                        "company_id": company_id,
                    }
                )

        except Exception:
            logger.warning(
                "Failed to compute semantic edges for document %s",
                doc.document_uuid,
            )

        return edges

    async def _prune_stale_edges(
        self,
        session: AsyncSession,
        doc: Document,
        company_id: int,
    ) -> int:
        """Prune stale edges from a modified document.

        Removes edges originating from the document whose detected_references
        are no longer present in the document's current content.

        Args:
            session: Active database session.
            doc: The modified document.
            company_id: Company ID for tenant scoping.

        Returns:
            Number of edges pruned.
        """
        # Get current document text
        text = await self._get_document_text(session, doc)
        if text is None:
            # If we can't get text, don't prune (conservative approach)
            return 0

        # Get current references from the document
        current_refs = self._cross_reference_service.extract_references_from_text(
            text=text,
            document_id=doc.id,
            document_title=doc.title,
        )
        current_ref_ids = {ref.reference_identifier for ref in current_refs}

        # Get existing edges from this document
        existing_edges_result = await session.execute(
            select(DependencyEdge).where(
                DependencyEdge.source_document_uuid == doc.document_uuid,
                DependencyEdge.company_id == company_id,
            )
        )
        existing_edges = list(existing_edges_result.scalars().all())

        pruned_count = 0
        for edge in existing_edges:
            # Skip DB-linked edges (trains_on, derived_from with DB references)
            detected_refs = edge.detected_references or []
            if isinstance(detected_refs, list) and any(
                ref.startswith("TrainingTask:")
                or ref.startswith("GenerationProvenance:")
                or ref.startswith("semantic:")
                for ref in detected_refs
            ):
                continue

            # Check if any detected reference is still present
            if isinstance(detected_refs, list):
                still_present = any(
                    ref in current_ref_ids for ref in detected_refs
                )
                if not still_present and detected_refs:
                    await session.delete(edge)
                    pruned_count += 1

        return pruned_count

    async def _upsert_edge(
        self,
        session: AsyncSession,
        edge_data: dict,
    ) -> None:
        """Upsert a dependency edge using PostgreSQL INSERT...ON CONFLICT.

        If an edge with the same (source_document_uuid, target_document_uuid,
        dependency_type, company_id) already exists, updates confidence_score,
        detected_references, and last_verified_at.

        Args:
            session: Active database session.
            edge_data: Dict with edge fields to insert/update.
        """
        stmt = pg_insert(DependencyEdge).values(**edge_data)

        # On conflict, update the mutable fields
        stmt = stmt.on_conflict_do_update(
            constraint="uq_dependency_edge_source_target_type_company",
            set_={
                "confidence_score": stmt.excluded.confidence_score,
                "detected_references": stmt.excluded.detected_references,
                "last_verified_at": stmt.excluded.last_verified_at,
            },
        )

        await session.execute(stmt)

    # -----------------------------------------------------------------------
    # Query Methods (Task 2.2)
    # -----------------------------------------------------------------------

    async def get_edges(
        self,
        session: AsyncSession,
        company_id: int,
        filters: GraphFilters | None = None,
        pagination: PaginationParams | None = None,
    ) -> dict:
        """List dependency edges with filtering and pagination.

        Args:
            session: Active database session.
            company_id: Company ID for tenant scoping.
            filters: Optional filters (source_document_uuid, target_document_uuid, dependency_type).
            pagination: Optional pagination (limit max 200, offset).

        Returns:
            Dict with "edges" (list of DependencyEdge) and "total_count" (int).
        """
        from sqlalchemy import func as sa_func

        if pagination is None:
            pagination = PaginationParams()
        if filters is None:
            filters = GraphFilters()

        # Build base query conditions
        conditions = [DependencyEdge.company_id == company_id]
        if filters.source_document_uuid:
            conditions.append(
                DependencyEdge.source_document_uuid == filters.source_document_uuid
            )
        if filters.target_document_uuid:
            conditions.append(
                DependencyEdge.target_document_uuid == filters.target_document_uuid
            )
        if filters.dependency_type:
            conditions.append(
                DependencyEdge.dependency_type == filters.dependency_type
            )

        # Count query
        count_stmt = select(sa_func.count(DependencyEdge.id)).where(*conditions)
        count_result = await session.execute(count_stmt)
        total_count = count_result.scalar_one()

        # Data query with pagination
        data_stmt = (
            select(DependencyEdge)
            .where(*conditions)
            .order_by(DependencyEdge.last_verified_at.desc())
            .limit(pagination.limit)
            .offset(pagination.offset)
        )
        data_result = await session.execute(data_stmt)
        edges = list(data_result.scalars().all())

        return {"edges": edges, "total_count": total_count}

    async def get_document_dependencies(
        self,
        session: AsyncSession,
        company_id: int,
        document_uuid: str,
    ) -> dict | None:
        """Get all dependencies for a specific document.

        Returns upstream (edges pointing to this document) and downstream
        (edges originating from this document) grouped by dependency_type.
        Returns None if the document doesn't exist in the company scope.

        Args:
            session: Active database session.
            company_id: Company ID for tenant scoping.
            document_uuid: UUID of the document to query.

        Returns:
            Dict with "document_uuid", "upstream", and "downstream" grouped
            by dependency_type, or None if document not found.
        """
        # Check document exists in company scope
        exists = await self._document_exists_in_company(
            session, company_id, document_uuid
        )
        if not exists:
            return None

        # Initialize empty groups for all dependency types
        dep_types = ["validates", "references", "implements", "trains_on", "derived_from"]
        upstream: dict[str, list[DependencyEdge]] = {t: [] for t in dep_types}
        downstream: dict[str, list[DependencyEdge]] = {t: [] for t in dep_types}

        # Query upstream edges (this document is the target)
        upstream_result = await session.execute(
            select(DependencyEdge).where(
                DependencyEdge.target_document_uuid == document_uuid,
                DependencyEdge.company_id == company_id,
            )
        )
        for edge in upstream_result.scalars().all():
            if edge.dependency_type in upstream:
                upstream[edge.dependency_type].append(edge)

        # Query downstream edges (this document is the source)
        downstream_result = await session.execute(
            select(DependencyEdge).where(
                DependencyEdge.source_document_uuid == document_uuid,
                DependencyEdge.company_id == company_id,
            )
        )
        for edge in downstream_result.scalars().all():
            if edge.dependency_type in downstream:
                downstream[edge.dependency_type].append(edge)

        return {
            "document_uuid": document_uuid,
            "upstream": upstream,
            "downstream": downstream,
        }

    async def _document_exists_in_company(
        self,
        session: AsyncSession,
        company_id: int,
        document_uuid: str,
    ) -> bool:
        """Check if a document exists within a company scope.

        Args:
            session: Active database session.
            company_id: Company ID for tenant scoping.
            document_uuid: UUID of the document to check.

        Returns:
            True if the document exists in the company, False otherwise.
        """
        from sqlalchemy import func as sa_func

        result = await session.execute(
            select(sa_func.count(Document.id)).where(
                Document.document_uuid == document_uuid,
                Document.company_id == company_id,
            )
        )
        count = result.scalar_one()
        return count > 0
