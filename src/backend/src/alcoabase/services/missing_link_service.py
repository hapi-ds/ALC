"""Missing Link Detection Service for compliance gap analysis.

This module provides the MissingLinkService that proactively detects
documents in "Approved" or "Active" status that are missing required
training records or electronic signatures.

Severity classification:
    Critical: Both training AND signature are missing
    Major:    Either training OR signature is missing (but not both)

References:
    - Requirement 7.1: GET /api/compliance/missing-links endpoint
    - Requirement 7.2: Training record completeness check
    - Requirement 7.3: Signature completeness check
    - Requirement 7.4: Severity classification
    - Requirement 7.5: Missing link record fields
    - Requirement 7.6: Company-scoped detection
    - Requirement 7.7: Master Auditor integration
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.signature import SignatureRecord
from alcoabase.models.training import TrainingRecord, TrainingTask
from alcoabase.models.workflow import DocumentState, WorkflowDefinition

logger = logging.getLogger(__name__)


@dataclass
class MissingLink:
    """Represents a document with compliance gaps.

    Attributes:
        document_id: Primary key of the document.
        document_uuid: Unique document identifier (YYYY-NNNNN format).
        document_title: Title of the document.
        document_type: Type classification of the document.
        current_status: Current workflow status (Approved or Active).
        missing_items: List of missing compliance items ("training" and/or "signature").
        affected_user_count: Number of users missing training for this document.
        days_since_approval: Days elapsed since the document entered Approved/Active status.
        severity: Gap severity — "Critical" if both missing, "Major" if one missing.
    """

    document_id: int
    document_uuid: str
    document_title: str
    document_type: str
    current_status: str
    missing_items: list[str] = field(default_factory=list)
    affected_user_count: int = 0
    days_since_approval: int = 0
    severity: str = "Major"


def classify_severity(training_missing: bool, signature_missing: bool) -> str:
    """Classify the severity of a missing link based on gap types.

    Args:
        training_missing: Whether training records are incomplete.
        signature_missing: Whether a required signature is missing.

    Returns:
        "Critical" if both are missing, "Major" if exactly one is missing.
    """
    if training_missing and signature_missing:
        return "Critical"
    return "Major"


class MissingLinkService:
    """Detects approved documents missing training or signatures.

    Queries documents in "Approved" or "Active" status and checks:
    1. Training completeness — all assigned users have a valid (Passed)
       training record for the current document version.
    2. Signature completeness — a PAdES signature exists when the
       document's workflow definition includes a signature gate.

    Attributes:
        _session_factory: SQLAlchemy async session factory for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the MissingLinkService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
        """
        self._session_factory = session_factory

    async def detect_missing_links(self, company_id: int) -> list[MissingLink]:
        """Detect all documents with compliance gaps for a company.

        Queries documents in "Approved" or "Active" status, checks training
        and signature completeness for each, and returns a list of documents
        with gaps classified by severity.

        Args:
            company_id: The company to scan for missing links.

        Returns:
            List of MissingLink objects for documents with compliance gaps.
            Documents with no gaps are excluded from the result.
        """
        missing_links: list[MissingLink] = []

        async with self._session_factory() as session:
            # Query all documents in Approved or Active status for this company
            stmt = select(Document).where(
                Document.company_id == company_id,
                Document.current_status.in_(["Approved", "Active"]),
            )
            result = await session.execute(stmt)
            documents = list(result.scalars().all())

            for document in documents:
                # Check training completeness
                training_complete, affected_user_count = (
                    await self._check_training_completeness_detail(
                        session, document
                    )
                )

                # Check signature completeness
                signature_complete = await self._check_signature_completeness_internal(
                    session, document
                )

                # Skip documents with no gaps
                if training_complete and signature_complete:
                    continue

                # Build missing items list
                missing_items: list[str] = []
                if not training_complete:
                    missing_items.append("training")
                if not signature_complete:
                    missing_items.append("signature")

                # Compute days since approval
                days_since = await self._compute_days_since_approval(
                    session, document
                )

                # Classify severity
                severity = classify_severity(
                    training_missing=not training_complete,
                    signature_missing=not signature_complete,
                )

                missing_links.append(
                    MissingLink(
                        document_id=document.id,
                        document_uuid=document.document_uuid,
                        document_title=document.title,
                        document_type=document.document_type,
                        current_status=document.current_status,
                        missing_items=missing_items,
                        affected_user_count=affected_user_count,
                        days_since_approval=days_since,
                        severity=severity,
                    )
                )

        return missing_links

    async def check_training_completeness(self, document_id: int) -> bool:
        """Check if all assigned users have completed training for a document.

        Verifies that every user assigned to the document's training task
        has a valid (is_valid=True) TrainingRecord for the current document
        version.

        Args:
            document_id: The document to check training completeness for.

        Returns:
            True if all assigned users have valid training records,
            False if any user is missing training.
        """
        async with self._session_factory() as session:
            # Get the document
            doc_result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = doc_result.scalar_one_or_none()
            if document is None:
                return True  # Document not found, nothing to flag

            complete, _ = await self._check_training_completeness_detail(
                session, document
            )
            return complete

    async def check_signature_completeness(self, document_id: int) -> bool:
        """Check if a document has the required PAdES signature.

        Verifies that the document's current version has a valid PAdES
        signature when the document's workflow definition includes a
        signature gate (signature_required_transitions is non-empty).

        Args:
            document_id: The document to check signature completeness for.

        Returns:
            True if the signature requirement is satisfied (either a PAdES
            signature exists or no signature is required by the workflow),
            False if a required signature is missing.
        """
        async with self._session_factory() as session:
            # Get the document
            doc_result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = doc_result.scalar_one_or_none()
            if document is None:
                return True  # Document not found, nothing to flag

            return await self._check_signature_completeness_internal(
                session, document
            )

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _check_training_completeness_detail(
        self, session: AsyncSession, document: Document
    ) -> tuple[bool, int]:
        """Check training completeness and return affected user count.

        Args:
            session: Active DB session.
            document: The document to check.

        Returns:
            Tuple of (is_complete, affected_user_count).
            affected_user_count is the number of users missing training.
        """
        # Get the current (latest) version of the document
        version_result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(
                DocumentVersion.major_version.desc(),
                DocumentVersion.minor_version.desc(),
            )
            .limit(1)
        )
        current_version = version_result.scalar_one_or_none()
        if current_version is None:
            # No version exists — no training can be assigned
            return True, 0

        version_str = f"{current_version.major_version}.0"

        # Get all users assigned to training tasks for this document version
        assigned_stmt = select(TrainingTask.assigned_user_id).where(
            TrainingTask.sop_document_uuid == document.document_uuid,
            TrainingTask.sop_version == version_str,
        )
        assigned_result = await session.execute(assigned_stmt)
        assigned_user_ids = set(assigned_result.scalars().all())

        if not assigned_user_ids:
            # No training tasks assigned — training is complete by default
            return True, 0

        # Get users who have valid training records for this version
        trained_stmt = select(TrainingRecord.user_id).where(
            TrainingRecord.sop_document_uuid == document.document_uuid,
            TrainingRecord.sop_version == version_str,
            TrainingRecord.is_valid == True,  # noqa: E712
        )
        trained_result = await session.execute(trained_stmt)
        trained_user_ids = set(trained_result.scalars().all())

        # Users missing training
        missing_users = assigned_user_ids - trained_user_ids
        affected_count = len(missing_users)

        return affected_count == 0, affected_count

    async def _check_signature_completeness_internal(
        self, session: AsyncSession, document: Document
    ) -> bool:
        """Check if the document has the required PAdES signature.

        Determines if the workflow requires a signature by checking
        signature_required_transitions. If required, verifies a PAdES
        signature record exists for the document.

        Args:
            session: Active DB session.
            document: The document to check.

        Returns:
            True if signature requirement is satisfied, False otherwise.
        """
        # Find the workflow definition for this document type
        # Workflows are bound by document_tag which matches document_type
        workflow_result = await session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.document_tag == document.document_type,
                WorkflowDefinition.is_active == True,  # noqa: E712
            )
        )
        workflow = workflow_result.scalar_one_or_none()

        if workflow is None:
            # No workflow defined — no signature requirement
            return True

        # Check if the workflow has any signature-required transitions
        sig_transitions = workflow.signature_required_transitions or []
        if not sig_transitions:
            # Workflow doesn't require signatures
            return True

        # Get the current (latest) version of the document
        version_result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document.id)
            .order_by(
                DocumentVersion.major_version.desc(),
                DocumentVersion.minor_version.desc(),
            )
            .limit(1)
        )
        current_version = version_result.scalar_one_or_none()
        if current_version is None:
            # No version exists — can't have a signature
            return False

        # Check if a PAdES signature exists for this document version
        sig_result = await session.execute(
            select(func.count(SignatureRecord.id)).where(
                SignatureRecord.document_uuid == document.document_uuid,
                SignatureRecord.document_version_id == current_version.id,
                SignatureRecord.signature_mode == "pades",
            )
        )
        sig_count = sig_result.scalar_one()

        return sig_count > 0

    async def _compute_days_since_approval(
        self, session: AsyncSession, document: Document
    ) -> int:
        """Compute the number of days since the document was approved.

        Uses the DocumentState.updated_at timestamp if available,
        otherwise falls back to the document's created_at.

        Args:
            session: Active DB session.
            document: The document to compute days for.

        Returns:
            Number of days since the document entered its current status.
        """
        # Try to get the DocumentState record for this document
        state_result = await session.execute(
            select(DocumentState).where(
                DocumentState.document_id == document.id
            )
        )
        state = state_result.scalar_one_or_none()

        if state is not None and state.updated_at is not None:
            approval_date = state.updated_at
        else:
            # Fallback to document creation date
            approval_date = document.created_at

        now = datetime.now(UTC)

        # Ensure approval_date is timezone-aware
        if approval_date.tzinfo is None:
            from datetime import timezone

            approval_date = approval_date.replace(tzinfo=timezone.utc)

        delta = now - approval_date
        return max(0, delta.days)
