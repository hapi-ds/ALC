"""Documentation Generator Service orchestrator for ALC Corporate governance.

Implements the DocumentationGeneratorService class that programmatically generates
2 guide documents (User Guide + Admin Guide), uploads them into the ALC corporate
governance environment, applies tags and the governance workflow, and supports
versioning on re-execution.

All operations run within the caller-provided session transaction.
The service does NOT commit — the caller (API route or CLI) manages
the transaction boundary.

References:
    - Design doc: .kiro/specs/Step_8-5_documentation-suite-user-admin-guides/design.md
    - Requirements: 4.1, 4.3, 4.9, 5.1
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.schemas.documentation_generation import (
    CrossReferenceSummary,
    DocumentationGenerationReport,
    DocumentReportEntry,
)
from alcoabase.services.documentation_content import (
    ADMIN_GUIDE_TITLE,
    DOCUMENTATION_DOCUMENT_TYPE,
    DOCUMENTATION_TAGS,
    USER_GUIDE_TITLE,
    CrossReferenceContext,
    assemble_admin_guide,
    assemble_user_guide,
)
from alcoabase.services.storage_service import StorageService
from alcoabase.services.uuid_service import UUIDService

logger = logging.getLogger(__name__)

# Advisory lock ID for preventing concurrent documentation generation.
# Chosen as a unique constant that won't collide with other advisory locks.
_ADVISORY_LOCK_ID = 85_0001  # Phase 8.5, lock #1


class DocumentationGeneratorService:
    """Orchestrates User Guide and Admin Guide generation, upload, and workflow application.

    Generates 2 documents (User Guide + Admin Guide) within a single
    database transaction. The service does NOT commit — the caller (API route
    or CLI) manages the transaction boundary.

    Follows the same pattern as GuidelinesGeneratorService (Phase 8.4).

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
        """Initialize the documentation generator service.

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

    async def execute(self) -> DocumentationGenerationReport:
        """Run the full documentation generation sequence for both guides.

        Executes each step in order:
        1. Acquire advisory lock (prevent concurrent generation)
        2. Validate prerequisites (company, doc-admin, workflow)
        3. Load cross-reference data (URS, AI Guidelines, governance docs)
        4. Generate User Guide content
        5. Generate Admin Guide content
        6. Validate all generated content
        7. Upload/version each document (with tags and workflow)
        8. Build and return the generation report

        Returns:
            DocumentationGenerationReport summarizing all created/versioned documents.

        Raises:
            RuntimeError: If any prerequisite is missing, content validation fails,
                or concurrent generation is in progress.
        """
        start_time = time.monotonic()
        logger.info(
            "Starting documentation suite generation",
            extra={"documentation_step": "execute"},
        )

        # Step 1: Acquire advisory lock to prevent concurrent generation
        await self._acquire_advisory_lock()
        logger.info(
            "Advisory lock acquired",
            extra={"documentation_step": "acquire_lock"},
        )

        # Step 2: Validate prerequisites
        company, doc_admin, workflow = await self._validate_prerequisites()
        logger.info(
            "Prerequisites validated: company=%s, doc_admin=%s, workflow=%s",
            company.slug,
            doc_admin.username,
            workflow.name,
            extra={"documentation_step": "validate_prerequisites"},
        )

        # Step 3: Load cross-reference data
        cross_refs = await self._load_cross_reference_data(company)
        logger.info(
            "Cross-reference data loaded: urs_available=%s, ai_guidelines_available=%s, "
            "governance_documents=%d",
            cross_refs.urs_available,
            cross_refs.ai_guidelines_available,
            len(cross_refs.governance_documents),
            extra={"documentation_step": "load_cross_reference_data"},
        )

        # Step 4: Generate User Guide content
        # Detect existing document to determine version number
        user_guide_existing = await self._detect_existing_document(
            USER_GUIDE_TITLE, company
        )
        user_guide_version = (
            1
            if user_guide_existing is None
            else await self._get_next_version_number(user_guide_existing)
        )

        user_guide_content = await self._generate_user_guide(
            cross_refs, user_guide_version
        )
        logger.info(
            "User Guide generated (%d bytes, version %d)",
            len(user_guide_content),
            user_guide_version,
            extra={"documentation_step": "generate_user_guide"},
        )

        # Step 5: Generate Admin Guide content
        admin_guide_existing = await self._detect_existing_document(
            ADMIN_GUIDE_TITLE, company
        )
        admin_guide_version = (
            1
            if admin_guide_existing is None
            else await self._get_next_version_number(admin_guide_existing)
        )

        admin_guide_content = await self._generate_admin_guide(
            cross_refs, admin_guide_version
        )
        logger.info(
            "Admin Guide generated (%d bytes, version %d)",
            len(admin_guide_content),
            admin_guide_version,
            extra={"documentation_step": "generate_admin_guide"},
        )

        # Step 6: Validate all content
        self._validate_content(user_guide_content, USER_GUIDE_TITLE)
        self._validate_section_lengths(user_guide_content, USER_GUIDE_TITLE)
        self._validate_content(admin_guide_content, ADMIN_GUIDE_TITLE)
        self._validate_section_lengths(admin_guide_content, ADMIN_GUIDE_TITLE)
        logger.info(
            "All content validated successfully",
            extra={"documentation_step": "validate_content"},
        )

        # Step 7: Upload/version each document, apply tags and workflow
        user_guide_report = await self._upload_or_version_document(
            USER_GUIDE_TITLE,
            user_guide_content,
            "user_guide",
            company,
            doc_admin,
            workflow,
        )
        logger.info(
            "User Guide uploaded: document_id=%d, uuid=%s, is_new=%s",
            user_guide_report.document_id,
            user_guide_report.document_uuid,
            user_guide_report.is_new_document,
            extra={"documentation_step": "upload_document"},
        )

        admin_guide_report = await self._upload_or_version_document(
            ADMIN_GUIDE_TITLE,
            admin_guide_content,
            "admin_guide",
            company,
            doc_admin,
            workflow,
        )
        logger.info(
            "Admin Guide uploaded: document_id=%d, uuid=%s, is_new=%s",
            admin_guide_report.document_id,
            admin_guide_report.document_uuid,
            admin_guide_report.is_new_document,
            extra={"documentation_step": "upload_document"},
        )

        # Step 8: Build report
        total_duration_ms = int((time.monotonic() - start_time) * 1000)

        documents_created = [user_guide_report, admin_guide_report]
        total_sections = (
            user_guide_report.section_count + admin_guide_report.section_count
        )
        total_procedures = (
            user_guide_report.procedure_count + admin_guide_report.procedure_count
        )

        cross_references_included = CrossReferenceSummary(
            urs_references=cross_refs.urs_available,
            ai_guidelines_references=cross_refs.ai_guidelines_available,
        )

        report = DocumentationGenerationReport(
            documents_created=documents_created,
            total_documents=len(documents_created),
            total_sections=total_sections,
            total_procedures=total_procedures,
            cross_references_included=cross_references_included,
            total_duration_ms=total_duration_ms,
        )

        logger.info(
            "Documentation suite generation complete in %dms "
            "(documents=%d, sections=%d, procedures=%d)",
            total_duration_ms,
            report.total_documents,
            report.total_sections,
            report.total_procedures,
            extra={"documentation_step": "execute"},
        )

        return report

    # ------------------------------------------------------------------
    # Private Methods — Stubs for tasks 2.2–2.6
    # ------------------------------------------------------------------

    async def _acquire_advisory_lock(self) -> None:
        """Acquire a PostgreSQL advisory lock to prevent concurrent generation.

        Uses pg_try_advisory_xact_lock which is automatically released
        at transaction end (commit or rollback). Non-blocking — raises
        RuntimeError immediately if lock is held by another session.

        Raises:
            RuntimeError: If the lock cannot be acquired (concurrent generation).
        """
        from sqlalchemy import text

        result = await self._session.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": _ADVISORY_LOCK_ID},
        )
        acquired = result.scalar()
        if not acquired:
            raise RuntimeError(
                "Documentation generation is already in progress. "
                "Please wait for the current generation to complete."
            )

    async def _validate_prerequisites(
        self,
    ) -> tuple[Company, User, WorkflowDefinition]:
        """Validate ALC company, doc-admin user, and governance workflow exist.

        Checks in order: company → doc-admin → workflow.
        Halts on first failure with a descriptive error message.

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

    async def _load_cross_reference_data(
        self, company: Company
    ) -> CrossReferenceContext:
        """Query for existing governance documents to build cross-references.

        Checks for:
        - Enhanced_URS document (tags ["URS", "ALC-GOV"])
        - AI Usage Guidelines documents (tags ["AI-Guidelines", "ALC-GOV"])
        - All ALC-GOV documents for the Related Governance Documents section

        Args:
            company: The ALC company entity.

        Returns:
            CrossReferenceContext with availability flags and document metadata.
        """
        # --- Query 1: Enhanced_URS document (tags ["URS", "ALC-GOV"]) ---
        # Subquery: document_ids that have the "URS" tag
        urs_tag_subq = (
            select(DocumentTag.document_id)
            .where(DocumentTag.tag == "URS")
            .subquery()
        )

        # Documents in this company with "ALC-GOV" tag whose id is also in urs_tag_subq
        urs_stmt = (
            select(Document)
            .join(DocumentTag, DocumentTag.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company.id,
                    DocumentTag.tag == "ALC-GOV",
                    Document.id.in_(select(urs_tag_subq.c.document_id)),
                )
            )
            .limit(1)
        )
        urs_result = await self._session.execute(urs_stmt)
        urs_document = urs_result.scalar_one_or_none()

        urs_available = urs_document is not None
        urs_document_uuid = urs_document.document_uuid if urs_document else None
        urs_document_title = urs_document.title if urs_document else None

        # --- Query 2: AI Usage Guidelines documents (tags ["AI-Guidelines", "ALC-GOV"]) ---
        # Subquery: document_ids that have the "AI-Guidelines" tag
        ai_tag_subq = (
            select(DocumentTag.document_id)
            .where(DocumentTag.tag == "AI-Guidelines")
            .subquery()
        )

        # Documents in this company with "ALC-GOV" tag whose id is also in ai_tag_subq
        ai_stmt = (
            select(Document)
            .join(DocumentTag, DocumentTag.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company.id,
                    DocumentTag.tag == "ALC-GOV",
                    Document.id.in_(select(ai_tag_subq.c.document_id)),
                )
            )
        )
        ai_result = await self._session.execute(ai_stmt)
        ai_documents = ai_result.scalars().unique().all()

        ai_guidelines_available = len(ai_documents) > 0
        ai_guidelines_documents = [
            {
                "title": doc.title,
                "uuid": doc.document_uuid,
                "state": doc.current_status,
            }
            for doc in ai_documents
        ]

        # --- Query 3: All ALC-GOV documents for Related Governance Documents section ---
        gov_stmt = (
            select(Document)
            .join(DocumentTag, DocumentTag.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company.id,
                    DocumentTag.tag == "ALC-GOV",
                )
            )
        )
        gov_result = await self._session.execute(gov_stmt)
        gov_documents = gov_result.scalars().unique().all()

        governance_documents = [
            {
                "title": doc.title,
                "uuid": doc.document_uuid,
                "state": doc.current_status,
            }
            for doc in gov_documents
        ]

        return CrossReferenceContext(
            urs_available=urs_available,
            urs_document_uuid=urs_document_uuid,
            urs_document_title=urs_document_title,
            ai_guidelines_available=ai_guidelines_available,
            ai_guidelines_documents=ai_guidelines_documents,
            governance_documents=governance_documents,
        )

    async def _generate_user_guide(
        self,
        cross_refs: CrossReferenceContext,
        version_number: int,
    ) -> str:
        """Generate the User Guide Markdown content.

        Assembles: header, table of contents, getting started, document management,
        template builder, report data entry, workflows, training management,
        electronic signatures, search and knowledge base, AI agent interaction,
        AI document generator, related governance documents, and appendices.

        Args:
            cross_refs: Cross-reference data for URS/AI Guidelines links.
            version_number: Version number to embed in header.

        Returns:
            Complete User Guide Markdown string.
        """
        return assemble_user_guide(cross_refs=cross_refs, version_number=version_number)

    async def _generate_admin_guide(
        self,
        cross_refs: CrossReferenceContext,
        version_number: int,
    ) -> str:
        """Generate the Admin Guide Markdown content.

        Assembles: header, table of contents, administration overview,
        user management, RBAC, system configuration, AI model layer,
        storage and backup, audit trail, compliance monitoring,
        agent registry, workflow administration, related governance documents,
        and appendices.

        Args:
            cross_refs: Cross-reference data for URS/AI Guidelines links.
            version_number: Version number to embed in header.

        Returns:
            Complete Admin Guide Markdown string.
        """
        return assemble_admin_guide(cross_refs=cross_refs, version_number=version_number)

    def _validate_content(self, content: str, document_title: str) -> None:
        """Validate guide content is non-empty and contains Markdown headings.

        Args:
            content: The generated Markdown content.
            document_title: Title for error reporting.

        Raises:
            RuntimeError: If content is empty or contains no Markdown headings.
        """
        if not content or not content.strip():
            raise RuntimeError(
                f"Generated content for '{document_title}' is empty."
            )

        if not re.search(r"^#{1,3}\s", content, re.MULTILINE):
            raise RuntimeError(
                f"Generated content for '{document_title}' contains no Markdown headings."
            )

    def _validate_section_lengths(self, content: str, document_title: str) -> None:
        """Validate that no section has < 200 chars of content.

        Splits content by level-2 headings (## ) and checks each section
        body has at least 200 characters of content (excluding the header
        line and Screenshot_Placeholders).

        Args:
            content: The generated Markdown content.
            document_title: Title for error reporting.

        Raises:
            RuntimeError: If any section fails the minimum content check.
        """
        # Split content by level-2 headings
        sections = re.split(r"^(## .+)$", content, flags=re.MULTILINE)

        # sections[0] is content before the first ## heading (preamble/header)
        # After that, sections alternate: [heading, body, heading, body, ...]
        # Start from index 1 to process heading+body pairs
        i = 1
        while i < len(sections):
            heading_line = sections[i]
            # Extract section name from the heading line (strip "## " prefix)
            section_name = heading_line.lstrip("#").strip()

            # Get the body content (next element after heading)
            body = sections[i + 1] if i + 1 < len(sections) else ""

            # Remove screenshot placeholder lines: ![...](screenshots/...)
            body_cleaned = re.sub(
                r"!\[.*?\]\(screenshots/.*?\)", "", body
            )

            # Strip whitespace to get actual content length
            body_stripped = body_cleaned.strip()
            length = len(body_stripped)

            if length < 200:
                raise RuntimeError(
                    f"Section '{section_name}' in '{document_title}' has "
                    f"insufficient content ({length} chars, minimum 200 required)."
                )

            i += 2

    async def _upload_or_version_document(
        self,
        title: str,
        content: str,
        guide_type: str,
        company: Company,
        doc_admin: User,
        workflow: WorkflowDefinition,
    ) -> DocumentReportEntry:
        """Create a new document or new version, apply tags and workflow.

        Detects existing document by title + tags ["DOC-GUIDE", "ALC-GOV"]
        + company_id. Creates new Document if not found, or new DocumentVersion
        if found.

        Args:
            title: Document title for matching and creation.
            content: Markdown content to upload.
            guide_type: "user_guide" or "admin_guide".
            company: ALC company entity.
            doc_admin: Document administrator user.
            workflow: Governance workflow definition.

        Returns:
            DocumentReportEntry with document_id, uuid, version, is_new, tags, state.
        """
        existing_document = await self._detect_existing_document(title, company)
        is_new = existing_document is None

        # Ensure services are available
        uuid_service = self._uuid_service or UUIDService()
        storage_service = self._storage_service or StorageService()

        # Compute file hash (SHA-512)
        file_hash = hashlib.sha512(content.encode()).hexdigest()

        change_reason = (
            "Documentation Suite Generation \u2014 "
            "Phase 8.5 automated governance document creation"
        )

        if is_new:
            # Generate Document-UUID (YYYY-NNNNN format)
            document_uuid = await uuid_service.generate_document_uuid(self._session)

            # Build storage key and upload to MinIO
            storage_key = f"documents/{document_uuid}/1.0/document.md"
            await storage_service.upload_file(
                storage_key, content.encode(), content_type="text/markdown"
            )

            # Create Document record
            document = Document(
                document_uuid=document_uuid,
                title=title,
                document_type=DOCUMENTATION_DOCUMENT_TYPE,
                folder_path="/governance/documentation-suite",
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
                change_reason=change_reason,
            )
            self._session.add(version)
            await self._session.flush()

            version_number = 1
        else:
            document = existing_document

            # Determine next major version
            version_number = await self._get_next_version_number(document)

            # Build storage key and upload to MinIO
            storage_key = (
                f"documents/{document.document_uuid}/"
                f"{version_number}.0/document.md"
            )
            await storage_service.upload_file(
                storage_key, content.encode(), content_type="text/markdown"
            )

            # Create new DocumentVersion record
            version = DocumentVersion(
                document_id=document.id,
                major_version=version_number,
                minor_version=0,
                storage_key=storage_key,
                file_hash=file_hash,
                uploaded_by=doc_admin.id,
                change_reason=change_reason,
            )
            self._session.add(version)
            await self._session.flush()

            # Reset document status to Draft for new governance lifecycle
            document.current_status = "Draft"

        # Apply tags and workflow
        tags_applied = await self._apply_tags(document, is_new)
        workflow_state = await self._apply_workflow(document, workflow, doc_admin)

        return DocumentReportEntry(
            document_id=document.id,
            document_uuid=document.document_uuid,
            title=title,
            guide_type=guide_type,
            version_number=version_number,
            tags_applied=tags_applied,
            workflow_state=workflow_state,
            is_new_document=is_new,
            section_count=self._count_sections(content),
            procedure_count=self._count_procedures(content),
            screenshot_placeholder_count=self._count_screenshot_placeholders(content),
        )

    async def _detect_existing_document(
        self, title: str, company: Company
    ) -> Document | None:
        """Find existing guide document by title + tags + company_id.

        Queries for a Document that belongs to the given company AND has
        both "DOC-GUIDE" and "ALC-GOV" tags AND matches the title exactly.

        Args:
            title: The document title to match.
            company: The ALC company entity.

        Returns:
            The existing Document if found, None otherwise.
        """
        # Subquery: find document_ids that have BOTH required tags
        subq = (
            select(DocumentTag.document_id)
            .where(DocumentTag.tag.in_(DOCUMENTATION_TAGS))
            .group_by(DocumentTag.document_id)
            .having(func.count(DocumentTag.tag.distinct()) == len(DOCUMENTATION_TAGS))
            .subquery()
        )

        # Main query: find the Document matching title + company_id + tags
        stmt = select(Document).where(
            Document.company_id == company.id,
            Document.title == title,
            Document.id.in_(select(subq.c.document_id)),
        )

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def _apply_tags(self, document: Document, is_new: bool) -> list[str]:
        """Apply "DOC-GUIDE" and "ALC-GOV" tags (skip if already present).

        Args:
            document: The Document record to tag.
            is_new: Whether this is a newly created document.

        Returns:
            List of tag strings applied (always ["DOC-GUIDE", "ALC-GOV"]).
        """
        # Query existing tags for this document
        stmt = select(DocumentTag).where(DocumentTag.document_id == document.id)
        result = await self._session.execute(stmt)
        existing_tags = {row.tag for row in result.scalars().all()}

        # Insert missing tags
        for tag in DOCUMENTATION_TAGS:
            if tag not in existing_tags:
                new_tag = DocumentTag(document_id=document.id, tag=tag)
                self._session.add(new_tag)

        await self._session.flush()

        return list(DOCUMENTATION_TAGS)

    async def _apply_workflow(
        self, document: Document, workflow: WorkflowDefinition, doc_admin: User
    ) -> str:
        """Create/reset DocumentState to "Draft" for the governance workflow.

        If a DocumentState already exists for this document, it is updated
        to reflect the new workflow assignment and reset to "Draft". If no
        state exists, a new DocumentState record is created.

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
                extra={"documentation_step": "apply_workflow"},
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
                extra={"documentation_step": "apply_workflow"},
            )

        await self._session.flush()

        return "Draft"

    async def _get_next_version_number(self, document: Document) -> int:
        """Get the next version number for an existing document.

        Args:
            document: The existing Document record.

        Returns:
            The next major_version number (current max + 1).
        """
        stmt = select(func.max(DocumentVersion.major_version)).where(
            DocumentVersion.document_id == document.id
        )
        result = await self._session.execute(stmt)
        max_version = result.scalar_one_or_none()
        return (max_version or 0) + 1

    def _count_sections(self, content: str) -> int:
        """Count level-2 headings (## ) in the generated content.

        Returns:
            Number of Guide_Sections.
        """
        pattern = re.compile(r"^## ", re.MULTILINE)
        return len(pattern.findall(content))

    def _count_procedures(self, content: str) -> int:
        """Count Procedure_Blocks in the generated content.

        Procedure_Blocks are identified by the pattern '### ... Procedure:'
        which matches both '### Procedure:' and '### N.M Procedure:' formats.

        Returns:
            Number of Procedure_Blocks.
        """
        pattern = re.compile(r"^###\s+.*Procedure:", re.MULTILINE)
        return len(pattern.findall(content))

    def _count_screenshot_placeholders(self, content: str) -> int:
        """Count screenshot placeholder image references.

        Matches pattern: ![...](screenshots/...)

        Returns:
            Number of Screenshot_Placeholders.
        """
        pattern = re.compile(r"!\[.*?\]\(screenshots/.*?\)")
        return len(pattern.findall(content))
