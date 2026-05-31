"""URS Generator Service orchestrator for ALC Corporate governance.

Implements the URSGeneratorService class that programmatically generates
the Enhanced User Requirement Specifications (URS) document, uploads it
into the ALC corporate governance environment, applies tags and the
governance workflow, and supports versioning on re-execution.

All operations run within the caller-provided session transaction.
The service does NOT commit — the caller (API route or CLI) manages
the transaction boundary.

References:
    - Design doc: .kiro/specs/Step_8-3_urs-alc-corporate/design.md
    - Requirements: 6.1, 6.3, 6.4
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.schemas.urs_generation import URSGenerationReport
from alcoabase.services.storage_service import StorageService
from alcoabase.services.urs_content import (
    URS_CONTENT,
    URS_DOCUMENT_TITLE,
    URS_DOCUMENT_TYPE,
    URS_TAGS,
)
from alcoabase.services.uuid_service import UUIDService

logger = logging.getLogger(__name__)


class URSGeneratorService:
    """Orchestrates URS document generation, upload, and workflow application.

    All operations run within the caller-provided session transaction.
    The service does NOT commit — the caller (API route or CLI) manages
    the transaction boundary.

    Attributes:
        _session: The async database session for persistence operations.
        _storage_service: Optional MinIO storage service for file uploads.
        _uuid_service: Optional UUID generation service for document IDs.
    """

    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService | None = None,
        uuid_service: UUIDService | None = None,
    ) -> None:
        """Initialize the URS generator service.

        Args:
            session: An async SQLAlchemy session. The caller is responsible
                for managing the transaction boundary (commit/rollback).
            storage_service: Optional storage service for MinIO uploads.
                If None, a default instance will be created when needed.
            uuid_service: Optional UUID service for document ID generation.
                If None, a default instance will be created when needed.
        """
        self._session = session
        self._storage_service = storage_service
        self._uuid_service = uuid_service

    async def execute(self) -> URSGenerationReport:
        """Run the full URS generation sequence and return a URSGenerationReport.

        Executes each step in order:
        1. Validate prerequisites (company, doc-admin, workflow)
        2. Generate content with version metadata
        3. Validate generated content
        4. Detect existing document for versioning
        5. Create new document or new version
        6. Apply tags
        7. Apply governance workflow

        Returns:
            URSGenerationReport summarizing the generation outcome.

        Raises:
            RuntimeError: If any prerequisite is missing or content is invalid.
        """
        start_time = time.monotonic()
        logger.info(
            "Starting URS generation for ALC Corporate",
            extra={"urs_step": "execute"},
        )

        # Step 1: Validate prerequisites
        company, doc_admin, workflow = await self._validate_prerequisites()
        logger.info(
            "Prerequisites validated: company=%s, doc_admin=%s, workflow=%s",
            company.slug,
            doc_admin.username,
            workflow.name,
            extra={"urs_step": "validate_prerequisites"},
        )

        # Step 2: Detect existing document to determine version number
        existing_document = await self._detect_existing_document(company)
        is_new_document = existing_document is None

        if is_new_document:
            version_number = 1
            logger.info(
                "No existing URS document found — will create new document",
                extra={"urs_step": "detect_existing_document"},
            )
        else:
            # Version number will be determined by _create_new_version
            # For content generation, we use a placeholder that gets resolved
            version_number = await self._get_next_version_number(existing_document)
            logger.info(
                "Existing URS document found (id=%d) — will create version %d",
                existing_document.id,
                version_number,
                extra={"urs_step": "detect_existing_document"},
            )

        # Step 3: Generate content
        content = await self._generate_content(version_number)
        logger.info(
            "URS content generated (%d bytes)",
            len(content),
            extra={"urs_step": "generate_content"},
        )

        # Step 4: Validate content
        self._validate_content(content)
        logger.info(
            "URS content validated successfully",
            extra={"urs_step": "validate_content"},
        )

        # Step 5: Create document or new version
        if is_new_document:
            document, version = await self._create_new_document(
                content, company, doc_admin
            )
            logger.info(
                "New document created: id=%d, uuid=%s",
                document.id,
                document.document_uuid,
                extra={"urs_step": "create_new_document"},
            )
        else:
            document = existing_document
            _version = await self._create_new_version(
                document, content, doc_admin, version_number
            )
            logger.info(
                "New version created: document_id=%d, version=%d",
                document.id,
                version_number,
                extra={"urs_step": "create_new_version"},
            )

        # Step 6: Apply tags
        tags_applied = await self._apply_tags(document, is_new_document)
        logger.info(
            "Tags applied: %s",
            tags_applied,
            extra={"urs_step": "apply_tags"},
        )

        # Step 7: Apply workflow
        workflow_state = await self._apply_workflow(document, workflow, doc_admin)
        logger.info(
            "Workflow applied: state=%s",
            workflow_state,
            extra={"urs_step": "apply_workflow"},
        )

        # Assemble the final report
        total_duration_ms = int((time.monotonic() - start_time) * 1000)

        # Count requirements and modules from content
        requirement_count = self._count_requirements(content)
        module_count = self._count_modules(content)

        report = URSGenerationReport(
            document_id=document.id,
            document_uuid=document.document_uuid,
            document_title=URS_DOCUMENT_TITLE,
            version_number=version_number,
            tags_applied=tags_applied,
            workflow_state=workflow_state,
            requirement_count=requirement_count,
            module_count=module_count,
            is_new_document=is_new_document,
            total_duration_ms=total_duration_ms,
        )

        logger.info(
            "URS generation complete in %dms (document_id=%d, version=%d, "
            "requirements=%d, modules=%d, is_new=%s)",
            total_duration_ms,
            document.id,
            version_number,
            requirement_count,
            module_count,
            is_new_document,
            extra={"urs_step": "execute"},
        )

        return report

    async def _validate_prerequisites(
        self,
    ) -> tuple[Company, User, WorkflowDefinition]:
        """Validate ALC company, doc-admin user, and governance workflow exist.

        Returns:
            Tuple of (company, doc_admin_user, workflow_definition).

        Raises:
            RuntimeError: If any prerequisite is missing.
        """
        # Query ALC company by slug
        stmt = select(Company).where(Company.slug == "alc-corporate")
        result = await self._session.execute(stmt)
        company = result.scalar_one_or_none()
        if company is None:
            raise RuntimeError(
                "ALC corporate environment not provisioned. "
                "Run Phase 8.2 seed first."
            )

        # Query doc-admin user by username
        stmt = select(User).where(User.username == "alc-doc-admin")
        result = await self._session.execute(stmt)
        doc_admin = result.scalar_one_or_none()
        if doc_admin is None:
            raise RuntimeError(
                "ALC Document Administrator user not found. "
                "Run Phase 8.2 seed first."
            )

        # Query governance workflow by document_tag and company_id
        stmt = select(WorkflowDefinition).where(
            WorkflowDefinition.document_tag == "ALC-GOV",
            WorkflowDefinition.company_id == company.id,
        )
        result = await self._session.execute(stmt)
        workflow = result.scalar_one_or_none()
        if workflow is None:
            raise RuntimeError(
                "ALC Governance workflow not found. "
                "Run Phase 8.2 seed first."
            )

        return company, doc_admin, workflow

    async def _generate_content(self, version_number: int) -> str:
        """Generate the URS Markdown content with version metadata injected.

        Args:
            version_number: The version number to embed in the header.

        Returns:
            Complete URS Markdown string with header metadata.
        """
        timestamp_str = datetime.now(timezone.utc).isoformat()
        content = URS_CONTENT.replace("{{VERSION}}", str(version_number)).replace(
            "{{TIMESTAMP}}", timestamp_str
        )
        return content

    def _validate_content(self, content: str) -> None:
        """Validate URS content is non-empty and well-formed.

        Args:
            content: The generated URS Markdown content.

        Raises:
            RuntimeError: If content is empty or contains no valid
                Requirement_IDs.
        """
        if not content or not content.strip():
            raise RuntimeError("URS content generation produced empty output")

        req_id_pattern = re.compile(r"REQ-[A-Z]+-\d{2}")
        matches = req_id_pattern.findall(content)
        if not matches:
            raise RuntimeError(
                "URS content generation produced invalid output: "
                "no valid Requirement_IDs found"
            )

    async def _detect_existing_document(self, company: Company) -> Document | None:
        """Find existing URS document by tags ["URS", "ALC-GOV"] + company_id.

        Queries for a Document that belongs to the given company AND has
        both "URS" and "ALC-GOV" tags attached via DocumentTag records.
        Uses a GROUP BY / HAVING COUNT approach to ensure both tags are present.

        Args:
            company: The ALC company entity.

        Returns:
            The existing Document if found, None otherwise.
        """
        # Subquery: find document_ids that have BOTH required tags
        required_tags = ["URS", "ALC-GOV"]
        subq = (
            select(DocumentTag.document_id)
            .where(DocumentTag.tag.in_(required_tags))
            .group_by(DocumentTag.document_id)
            .having(func.count(DocumentTag.tag.distinct()) == len(required_tags))
            .subquery()
        )

        # Main query: find the Document matching company_id and the subquery
        stmt = (
            select(Document)
            .where(
                Document.company_id == company.id,
                Document.id.in_(select(subq.c.document_id)),
            )
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_next_version_number(self, document: Document) -> int:
        """Determine the next version number for an existing document.

        Args:
            document: The existing Document record.

        Returns:
            The next major version number (previous max + 1).
        """
        stmt = select(func.max(DocumentVersion.major_version)).where(
            DocumentVersion.document_id == document.id
        )
        result = await self._session.execute(stmt)
        max_version = result.scalar_one_or_none()
        return (max_version or 0) + 1

    async def _create_new_document(
        self, content: str, company: Company, doc_admin: User
    ) -> tuple[Document, DocumentVersion]:
        """Create a new Document + initial DocumentVersion + upload to MinIO.

        Args:
            content: The URS Markdown content to store.
            company: The ALC company entity.
            doc_admin: The document administrator user.

        Returns:
            Tuple of (document, version).
        """
        # Ensure services are available
        uuid_service = self._uuid_service or UUIDService()
        storage_service = self._storage_service or StorageService()

        # Generate Document-UUID (YYYY-NNNNN format)
        document_uuid = await uuid_service.generate_document_uuid(self._session)

        # Compute file hash (SHA-512)
        file_hash = hashlib.sha512(content.encode()).hexdigest()

        # Build storage key and upload to MinIO
        storage_key = f"documents/{document_uuid}/1.0/document.md"
        await storage_service.upload_file(storage_key, content.encode())

        # Create Document record
        document = Document(
            document_uuid=document_uuid,
            title=URS_DOCUMENT_TITLE,
            document_type=URS_DOCUMENT_TYPE,
            folder_path="/governance/urs",
            current_status="Draft",
            company_id=company.id,
            created_by=doc_admin.id,
        )
        self._session.add(document)
        await self._session.flush()

        # Create initial DocumentVersion record
        version = DocumentVersion(
            document_id=document.id,
            major_version=1,
            minor_version=0,
            storage_key=storage_key,
            file_hash=file_hash,
            uploaded_by=doc_admin.id,
            change_reason="URS Generation — Phase 8.3 automated governance document creation",
        )
        self._session.add(version)
        await self._session.flush()

        return document, version

    async def _create_new_version(
        self, document: Document, content: str, doc_admin: User, version_number: int
    ) -> DocumentVersion:
        """Create a new DocumentVersion for an existing document.

        Args:
            document: The existing Document record.
            content: The URS Markdown content to store.
            doc_admin: The document administrator user.
            version_number: The new major version number.

        Returns:
            The new DocumentVersion record.
        """
        # Ensure storage service is available
        storage_service = self._storage_service or StorageService()

        # Compute file hash (SHA-512)
        file_hash = hashlib.sha512(content.encode()).hexdigest()

        # Build storage key and upload to MinIO
        storage_key = f"documents/{document.document_uuid}/{version_number}.0/document.md"
        await storage_service.upload_file(storage_key, content.encode())

        # Create new DocumentVersion record
        version = DocumentVersion(
            document_id=document.id,
            major_version=version_number,
            minor_version=0,
            storage_key=storage_key,
            file_hash=file_hash,
            uploaded_by=doc_admin.id,
            change_reason=f"URS regeneration — version {version_number}.0",
        )
        self._session.add(version)
        await self._session.flush()

        # Reset document status to Draft for new governance lifecycle
        document.current_status = "Draft"

        return version

    async def _apply_tags(self, document: Document, is_new: bool) -> list[str]:
        """Apply "URS" and "ALC-GOV" tags to the document.

        Skips tags that are already present on the document.

        Args:
            document: The Document record to tag.
            is_new: Whether this is a newly created document.

        Returns:
            List of tag strings applied (always ["URS", "ALC-GOV"]).
        """
        # Query existing tags for this document
        stmt = select(DocumentTag).where(DocumentTag.document_id == document.id)
        result = await self._session.execute(stmt)
        existing_tags = {row.tag for row in result.scalars().all()}

        # Insert missing tags
        for tag in URS_TAGS:
            if tag not in existing_tags:
                new_tag = DocumentTag(document_id=document.id, tag=tag)
                self._session.add(new_tag)

        await self._session.flush()

        return list(URS_TAGS)

    async def _apply_workflow(
        self, document: Document, workflow: WorkflowDefinition, doc_admin: User
    ) -> str:
        """Create/reset DocumentState to "Draft" for the governance workflow.

        If a DocumentState already exists for this document, it is updated
        to reflect the new workflow assignment and reset to "Draft". If no
        state exists, a new DocumentState record is created.

        An audit trail entry is recorded via the updated_at timestamp and
        SQLAlchemy-Continuum's automatic versioning (triggered by the
        X-Change-Reason header pattern at the API layer).

        Args:
            document: The Document record.
            workflow: The governance WorkflowDefinition.
            doc_admin: The document administrator user.

        Returns:
            The workflow state string ("Draft").
        """
        # Check if a DocumentState already exists for this document
        stmt = select(DocumentState).where(
            DocumentState.document_id == document.id
        )
        result = await self._session.execute(stmt)
        doc_state = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if doc_state is not None:
            # Update existing state to Draft with new workflow
            doc_state.current_state = "Draft"
            doc_state.workflow_id = workflow.id
            doc_state.updated_by = doc_admin.id
            doc_state.updated_at = now
            logger.info(
                "DocumentState updated to Draft for document_id=%d, "
                "workflow_id=%d, updated_by=%d",
                document.id,
                workflow.id,
                doc_admin.id,
                extra={"urs_step": "apply_workflow"},
            )
        else:
            # Create new DocumentState record
            doc_state = DocumentState(
                document_id=document.id,
                current_state="Draft",
                workflow_id=workflow.id,
                updated_by=doc_admin.id,
                updated_at=now,
            )
            self._session.add(doc_state)
            logger.info(
                "DocumentState created with state=Draft for document_id=%d, "
                "workflow_id=%d, updated_by=%d",
                document.id,
                workflow.id,
                doc_admin.id,
                extra={"urs_step": "apply_workflow"},
            )

        await self._session.flush()

        return "Draft"

    def _count_requirements(self, content: str) -> int:
        """Count distinct Requirement_IDs in the generated content.

        Args:
            content: The URS Markdown content.

        Returns:
            Number of unique Requirement_IDs found.
        """
        import re

        req_id_pattern = re.compile(r"REQ-[A-Z]+-\d{2,}")
        matches = req_id_pattern.findall(content)
        return len(set(matches))

    def _count_modules(self, content: str) -> int:
        """Count requirement modules in the generated content.

        Modules are identified by level-2 headings that contain
        module-related content (sections with requirements).

        Args:
            content: The URS Markdown content.

        Returns:
            Number of requirement modules found.
        """
        import re

        # Count sections that contain at least one REQ-ID
        # Modules are ## headings followed by requirements
        module_pattern = re.compile(r"^## \d+\.\s+", re.MULTILINE)
        matches = module_pattern.findall(content)
        return len(matches)
