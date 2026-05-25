"""Generated Document Review Service for AI-generated document workflow.

This module implements the review workflow for AI-generated documents,
managing the transition from Draft/pending_review through approval or
rejection. Only documents with an associated GenerationProvenance record
(i.e., AI-generated documents) can be reviewed through this service.

Key behaviors:
- approve: transitions document current_status from "Draft" to "Review"
  (enters standard BPMN workflow)
- reject: marks content_status as "rejected", document remains in "Draft"
- All operations scoped to company_id for multi-tenancy isolation

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10
"""

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document
from alcoabase.models.document_generation import (
    DocumentTemplate,
    GenerationJobMetadata,
    GenerationProvenance,
)


class GeneratedDocReviewService:
    """Review workflow for AI-generated documents.

    Manages the approval/rejection lifecycle for documents produced by
    the Template-Based AI Document Generator. Ensures only AI-generated
    documents (those with an associated GenerationProvenance record) can
    be reviewed through this endpoint.

    Attributes:
        _session_factory: Async session factory for database operations.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Initialize the GeneratedDocReviewService.

        Args:
            session_factory: Async session factory for database operations.
        """
        self._session_factory = session_factory

    async def review_document(
        self,
        document_id: int,
        action: str,
        reviewer_id: int,
        company_id: int,
        reviewer_comments: str | None = None,
    ) -> dict[str, Any]:
        """Approve or reject a generated document.

        - approve: Draft → Review (enters standard BPMN workflow)
        - reject: ContentStatus → rejected, remains Draft

        Args:
            document_id: ID of the document to review.
            action: Review action ("approve" or "reject").
            reviewer_id: ID of the user performing the review.
            company_id: Company scope for tenant isolation.
            reviewer_comments: Optional reviewer comments (max 2000 chars).

        Returns:
            Dict with document_id, current_status, and content_status.

        Raises:
            ValueError: If the document is not AI-generated (no provenance),
                or if the document has already been reviewed.
            LookupError: If the document is not found within the company scope.
        """
        async with self._session_factory() as session:
            # Verify document exists and belongs to company
            doc_result = await session.execute(
                select(Document).where(
                    Document.id == document_id,
                    Document.company_id == company_id,
                )
            )
            document = doc_result.scalar_one_or_none()
            if document is None:
                raise LookupError(
                    f"Document {document_id} not found in company {company_id}"
                )

            # Verify document is AI-generated (has GenerationProvenance)
            provenance_result = await session.execute(
                select(GenerationProvenance.id).where(
                    GenerationProvenance.document_id == document_id,
                    GenerationProvenance.company_id == company_id,
                )
            )
            if provenance_result.scalar_one_or_none() is None:
                raise ValueError(
                    "Only AI-generated documents can be reviewed through "
                    "this endpoint"
                )

            # Get the generation job metadata for content_status tracking
            job_result = await session.execute(
                select(GenerationJobMetadata).where(
                    GenerationJobMetadata.result_document_id == document_id,
                    GenerationJobMetadata.company_id == company_id,
                )
            )
            job_metadata = job_result.scalar_one_or_none()
            if job_metadata is None:
                raise LookupError(
                    f"Generation job metadata not found for document {document_id}"
                )

            # Check if already reviewed (not pending_review)
            if job_metadata.content_status != "pending_review":
                raise ValueError(
                    f"Document has already been reviewed. "
                    f"Current content_status: {job_metadata.content_status}"
                )

            # Perform the review action
            if action == "approve":
                document.current_status = "Review"
                job_metadata.content_status = "approved"
            elif action == "reject":
                # Document remains in Draft, content_status set to rejected
                job_metadata.content_status = "rejected"
            else:
                raise ValueError(
                    f"Invalid action '{action}'. Must be 'approve' or 'reject'."
                )

            await session.commit()

            return {
                "document_id": document_id,
                "current_status": document.current_status,
                "content_status": job_metadata.content_status,
            }

    async def list_generated_documents(
        self,
        company_id: int,
        content_status: str | None = None,
        document_type: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """List AI-generated documents with filtering and pagination.

        Returns documents that have an associated GenerationProvenance record,
        filtered by content_status, document_type, and date range.

        Args:
            company_id: Company scope for tenant isolation.
            content_status: Optional filter by content review status
                (pending_review, approved, rejected).
            document_type: Optional filter by document classification type.
            start_date: Optional ISO 8601 date string for range start.
            end_date: Optional ISO 8601 date string for range end.
            limit: Maximum number of results (default 20).
            offset: Number of results to skip (default 0).

        Returns:
            Tuple of (list of document dicts, total count).
        """
        async with self._session_factory() as session:
            # Base query: join Document with GenerationJobMetadata
            # to get only AI-generated documents
            base_conditions = [
                GenerationJobMetadata.company_id == company_id,
                GenerationJobMetadata.status == "completed",
                GenerationJobMetadata.result_document_id.isnot(None),
            ]

            if content_status is not None:
                base_conditions.append(
                    GenerationJobMetadata.content_status == content_status
                )

            if document_type is not None:
                base_conditions.append(
                    Document.document_type == document_type
                )

            if start_date is not None:
                start_dt = datetime.fromisoformat(start_date)
                base_conditions.append(
                    GenerationJobMetadata.completed_at >= start_dt
                )

            if end_date is not None:
                end_dt = datetime.fromisoformat(end_date)
                base_conditions.append(
                    GenerationJobMetadata.completed_at <= end_dt
                )

            # Count query
            count_query = (
                select(func.count(GenerationJobMetadata.id))
                .join(
                    Document,
                    Document.id == GenerationJobMetadata.result_document_id,
                )
                .join(
                    DocumentTemplate,
                    DocumentTemplate.id == GenerationJobMetadata.template_id,
                )
                .where(*base_conditions)
            )
            total_result = await session.execute(count_query)
            total = total_result.scalar_one()

            # Data query
            data_query = (
                select(
                    Document.id,
                    Document.document_uuid,
                    Document.title,
                    Document.document_type,
                    Document.current_status,
                    GenerationJobMetadata.content_status,
                    DocumentTemplate.template_name,
                    GenerationJobMetadata.completed_at,
                    GenerationJobMetadata.generation_duration_ms,
                )
                .join(
                    Document,
                    Document.id == GenerationJobMetadata.result_document_id,
                )
                .join(
                    DocumentTemplate,
                    DocumentTemplate.id == GenerationJobMetadata.template_id,
                )
                .where(*base_conditions)
                .order_by(GenerationJobMetadata.completed_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(data_query)
            rows = result.all()

            documents = [
                {
                    "id": row.id,
                    "document_uuid": row.document_uuid,
                    "title": row.title,
                    "document_type": row.document_type,
                    "current_status": row.current_status,
                    "content_status": row.content_status,
                    "template_name": row.template_name,
                    "generated_at": row.completed_at,
                    "generation_duration_ms": row.generation_duration_ms,
                }
                for row in rows
            ]

            return (documents, total)

    async def is_ai_generated(
        self, document_id: int, company_id: int
    ) -> bool:
        """Check if document has an associated GenerationProvenance record.

        Args:
            document_id: ID of the document to check.
            company_id: Company scope for tenant isolation.

        Returns:
            True if the document has a GenerationProvenance record, False otherwise.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(GenerationProvenance.id).where(
                    GenerationProvenance.document_id == document_id,
                    GenerationProvenance.company_id == company_id,
                ).limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def get_content_status(
        self, document_id: int, company_id: int
    ) -> str | None:
        """Get current ContentStatus for a document.

        Retrieves the content_status from the GenerationJobMetadata
        associated with the given document.

        Args:
            document_id: ID of the document.
            company_id: Company scope for tenant isolation.

        Returns:
            The content_status string, or None if the document is not
            AI-generated or not found.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(GenerationJobMetadata.content_status).where(
                    GenerationJobMetadata.result_document_id == document_id,
                    GenerationJobMetadata.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()
