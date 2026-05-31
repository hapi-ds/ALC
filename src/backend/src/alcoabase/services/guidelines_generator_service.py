"""Guidelines Generator Service orchestrator for ALC Corporate governance.

Implements the GuidelinesGeneratorService class that programmatically generates
4 AI usage guideline documents (1 master cross-sector + 3 sector-specific),
uploads them into the ALC corporate governance environment, applies tags and
the governance workflow, and supports versioning on re-execution.

All operations run within the caller-provided session transaction.
The service does NOT commit — the caller (API route or CLI) manages
the transaction boundary.

References:
    - Design doc: .kiro/specs/Step_8-4_cross-sector-ai-regulatory-guidelines/design.md
    - Requirements: 5.1, 5.3, 5.9, 6.1
"""

import hashlib
import logging
import re
import time
from datetime import datetime, timezone

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.company import Company
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.user import User
from alcoabase.models.workflow import DocumentState, WorkflowDefinition
from alcoabase.schemas.guidelines_generation import (
    DocumentReportEntry,
    GuidelinesGenerationReport,
)
from alcoabase.services.guidelines_content import (
    GUIDELINE_DOCUMENT_TYPE,
    GUIDELINE_TAGS,
    MASTER_GUIDELINE_TITLE,
    REGULATORY_FRAMEWORKS,
    SECTOR_MODULES,
    DocumentResult,
    RiskFrameworkContext,
    SectorModule,
    assemble_master_guideline,
    assemble_sector_guideline,
)
from alcoabase.services.storage_service import StorageService
from alcoabase.services.uuid_service import UUIDService

logger = logging.getLogger(__name__)

# Advisory lock ID for preventing concurrent guideline generation.
# Chosen as a unique constant that won't collide with other advisory locks.
_ADVISORY_LOCK_ID = 84_0001  # Phase 8.4, lock #1


class GuidelinesGeneratorService:
    """Orchestrates AI regulatory guideline generation, upload, and workflow application.

    Generates 4 documents (1 master + 3 sector-specific) within a single
    database transaction. The service does NOT commit — the caller (API route
    or CLI) manages the transaction boundary.

    Follows the same pattern as URSGeneratorService (Phase 8.3).

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
        """Initialize the guidelines generator service.

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

    async def execute(self) -> GuidelinesGenerationReport:
        """Run the full guidelines generation sequence for all 4 documents.

        Executes each step in order:
        1. Acquire advisory lock (prevent concurrent generation)
        2. Validate prerequisites (company, doc-admin, workflow)
        3. Load risk framework data (task types, tiers, control sets)
        4. Check URS availability for cross-references
        5. Generate all 4 guideline documents
        6. Validate all generated content
        7. Upload/version each document (with tags and workflow)
        8. Build and return the generation report

        Returns:
            GuidelinesGenerationReport summarizing all created/versioned documents.

        Raises:
            RuntimeError: If any prerequisite is missing, risk data unavailable,
                content validation fails, or concurrent generation is in progress.
        """
        start_time = time.monotonic()
        logger.info(
            "Starting AI regulatory guidelines generation",
            extra={"guidelines_step": "execute"},
        )

        # Step 0: Acquire advisory lock to prevent concurrent generation
        await self._acquire_advisory_lock()
        logger.info(
            "Advisory lock acquired",
            extra={"guidelines_step": "acquire_lock"},
        )

        # Step 1: Validate prerequisites
        company, doc_admin, workflow = await self._validate_prerequisites()
        logger.info(
            "Prerequisites validated: company=%s, doc_admin=%s, workflow=%s",
            company.slug,
            doc_admin.username,
            workflow.name,
            extra={"guidelines_step": "validate_prerequisites"},
        )

        # Step 2: Load risk framework data
        risk_context = await self._load_risk_framework_data(company)
        logger.info(
            "Risk framework data loaded: %d task types, profile_active=%s",
            len(risk_context.task_types),
            risk_context.company_profile_active,
            extra={"guidelines_step": "load_risk_framework_data"},
        )

        # Step 3: Check URS availability
        urs_available = await self._check_urs_availability(company)
        logger.info(
            "URS availability: %s",
            urs_available,
            extra={"guidelines_step": "check_urs_availability"},
        )

        # Step 4: Generate all 4 documents
        # Detect existing documents to determine version numbers
        master_existing = await self._detect_existing_document(
            MASTER_GUIDELINE_TITLE, company
        )
        master_version = (
            1
            if master_existing is None
            else await self._get_next_version_number(master_existing)
        )

        master_content = await self._generate_master_guideline(
            risk_context, master_version, urs_available
        )
        logger.info(
            "Master guideline generated (%d bytes, version %d)",
            len(master_content),
            master_version,
            extra={"guidelines_step": "generate_master_guideline"},
        )

        sector_contents: list[tuple[SectorModule, str, int]] = []
        for sector in SECTOR_MODULES:
            sector_existing = await self._detect_existing_document(
                sector.title, company
            )
            sector_version = (
                1
                if sector_existing is None
                else await self._get_next_version_number(sector_existing)
            )
            sector_content = await self._generate_sector_guideline(
                sector, risk_context, sector_version, urs_available
            )
            sector_contents.append((sector, sector_content, sector_version))
            logger.info(
                "Sector guideline generated: %s (%d bytes, version %d)",
                sector.sector_label,
                len(sector_content),
                sector_version,
                extra={"guidelines_step": "generate_sector_guideline"},
            )

        # Step 5: Validate all content
        self._validate_content(master_content, MASTER_GUIDELINE_TITLE)
        for sector, content, _ver in sector_contents:
            self._validate_content(content, sector.title)
            self._validate_section_lengths(content, sector.title)
        logger.info(
            "All content validated successfully",
            extra={"guidelines_step": "validate_content"},
        )

        # Step 6: Upload/version each document, apply tags and workflow
        document_results: list[DocumentResult] = []

        master_result = await self._upload_or_version_document(
            MASTER_GUIDELINE_TITLE,
            master_content,
            company,
            doc_admin,
            workflow,
        )
        document_results.append(master_result)
        logger.info(
            "Master guideline uploaded: document_id=%d, uuid=%s, is_new=%s",
            master_result.document_id,
            master_result.document_uuid,
            master_result.is_new_document,
            extra={"guidelines_step": "upload_document"},
        )

        for sector, content, _ver in sector_contents:
            sector_result = await self._upload_or_version_document(
                sector.title,
                content,
                company,
                doc_admin,
                workflow,
            )
            document_results.append(sector_result)
            logger.info(
                "Sector guideline uploaded: %s, document_id=%d, is_new=%s",
                sector.sector_label,
                sector_result.document_id,
                sector_result.is_new_document,
                extra={"guidelines_step": "upload_document"},
            )

        # Step 7: Build report
        total_duration_ms = int((time.monotonic() - start_time) * 1000)

        # Count policy sections across all documents
        total_policy_sections = self._count_policy_sections(master_content)
        for _sector, content, _ver in sector_contents:
            total_policy_sections += self._count_policy_sections(content)

        # Collect unique risk tiers referenced
        risk_tiers_referenced = sorted(set(risk_context.effective_tiers.values()))

        # Collect regulatory frameworks covered
        regulatory_frameworks_covered = sorted(
            {fw.identifier for fw in self._get_all_frameworks()}
        )

        # Build report entries
        entries: list[DocumentReportEntry] = []
        for result in document_results:
            # Determine sector from title
            sector_id = self._resolve_sector_id(result.title)
            policy_count = self._count_policy_sections(
                master_content
                if result.title == MASTER_GUIDELINE_TITLE
                else next(
                    c for s, c, _v in sector_contents if s.title == result.title
                )
            )
            entries.append(
                DocumentReportEntry(
                    document_id=result.document_id,
                    document_uuid=result.document_uuid,
                    title=result.title,
                    sector=sector_id,
                    version_number=result.version_number,
                    tags_applied=result.tags_applied,
                    workflow_state=result.workflow_state,
                    is_new_document=result.is_new_document,
                    policy_section_count=policy_count,
                )
            )

        report = GuidelinesGenerationReport(
            documents_created=entries,
            total_documents=len(entries),
            total_policy_sections=total_policy_sections,
            risk_tiers_referenced=risk_tiers_referenced,
            regulatory_frameworks_covered=regulatory_frameworks_covered,
            total_duration_ms=total_duration_ms,
        )

        logger.info(
            "Guidelines generation complete in %dms "
            "(documents=%d, policy_sections=%d, tiers=%s)",
            total_duration_ms,
            report.total_documents,
            report.total_policy_sections,
            risk_tiers_referenced,
            extra={"guidelines_step": "execute"},
        )

        return report

    # ------------------------------------------------------------------
    # Private Methods — Stubs for tasks 2.2–2.6
    # ------------------------------------------------------------------

    async def _acquire_advisory_lock(self) -> None:
        """Acquire a PostgreSQL advisory lock to prevent concurrent generation.

        Uses pg_try_advisory_xact_lock which is automatically released
        at transaction end (commit or rollback).

        Raises:
            RuntimeError: If the lock cannot be acquired (concurrent generation).
        """
        result = await self._session.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": _ADVISORY_LOCK_ID},
        )
        acquired = result.scalar()
        if not acquired:
            raise RuntimeError(
                "Guidelines generation is already in progress. "
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

    async def _load_risk_framework_data(
        self, company: Company
    ) -> RiskFrameworkContext:
        """Query the Risk Classification Service for active AI task types and tiers.

        Retrieves all active AI_Task_Types, the active Company_Risk_Profile
        (or defaults), and TIER_DEFINITIONS to compose Risk_Integration_Blocks.

        Args:
            company: The ALC company entity.

        Returns:
            RiskFrameworkContext containing task types, effective tiers, and control sets.

        Raises:
            RuntimeError: If zero active AI_Task_Types are found.
        """
        from alcoabase.models.risk_framework import (
            AITaskType,
            CompanyRiskProfile,
            RiskTierOverride,
        )
        from alcoabase.services.risk_classification_service import TIER_DEFINITIONS

        # Query all active AI_Task_Types for this company
        # (system-defined with company_id=NULL, or company-specific)
        stmt = (
            select(AITaskType)
            .where(
                AITaskType.is_active.is_(True),
                (
                    AITaskType.company_id.is_(None)
                    | (AITaskType.company_id == company.id)
                ),
            )
            .order_by(AITaskType.task_type_id.asc())
        )
        result = await self._session.execute(stmt)
        task_types = list(result.scalars().all())

        if not task_types:
            raise RuntimeError(
                "No AI task types registered. Run Phase 8.1 seed first."
            )

        # Query active Company_Risk_Profile for tier overrides
        profile_stmt = select(CompanyRiskProfile).where(
            CompanyRiskProfile.company_id == company.id,
            CompanyRiskProfile.is_active.is_(True),
        )
        profile_result = await self._session.execute(profile_stmt)
        active_profile = profile_result.scalar_one_or_none()

        # Build overrides map from the active profile (if exists)
        overrides_map: dict[str, str] = {}
        if active_profile is not None:
            overrides_stmt = select(
                RiskTierOverride.task_type_id,
                RiskTierOverride.assigned_tier,
            ).where(RiskTierOverride.profile_id == active_profile.id)
            overrides_result = await self._session.execute(overrides_stmt)
            overrides_map = {
                row.task_type_id: row.assigned_tier for row in overrides_result
            }

        # Resolve effective tier per task type:
        # company override if present, else default_risk_tier
        effective_tiers: dict[str, str] = {}
        risk_factors_map: dict[str, list[str]] = {}
        for tt in task_types:
            effective_tiers[tt.task_type_id] = overrides_map.get(
                tt.task_type_id, tt.default_risk_tier
            )
            risk_factors_map[tt.task_type_id] = tt.risk_factors or []

        # Determine whether a company-specific profile is active
        company_profile_active = active_profile is not None

        return RiskFrameworkContext(
            task_types=task_types,
            effective_tiers=effective_tiers,
            tier_definitions=TIER_DEFINITIONS,
            company_profile_active=company_profile_active,
            risk_factors_map=risk_factors_map,
        )

    async def _check_urs_availability(self, company: Company) -> bool:
        """Check if the Enhanced_URS document exists for URS cross-references.

        Args:
            company: The ALC company entity.

        Returns:
            True if URS document with tags ["URS", "ALC-GOV"] exists, False otherwise.
        """
        # Find documents in this company that have BOTH "URS" and "ALC-GOV" tags.
        # We use a subquery approach: find document_ids that have both tags,
        # then check if any of those documents belong to this company.

        # Subquery: document_ids that have the "URS" tag
        urs_docs = (
            select(DocumentTag.document_id)
            .where(DocumentTag.tag == "URS")
            .subquery()
        )

        # Query: documents in this company with "ALC-GOV" tag whose id is also in urs_docs
        stmt = (
            select(Document.id)
            .join(DocumentTag, DocumentTag.document_id == Document.id)
            .where(
                and_(
                    Document.company_id == company.id,
                    DocumentTag.tag == "ALC-GOV",
                    Document.id.in_(select(urs_docs.c.document_id)),
                )
            )
            .limit(1)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _generate_master_guideline(
        self,
        risk_context: RiskFrameworkContext,
        version_number: int,
        urs_available: bool,
    ) -> str:
        """Generate the cross-sector master guideline Markdown content.

        Assembles: header, purpose/scope, regulatory framework overview,
        risk classification summary, AI feature usage policies (one per task type),
        human oversight requirements, audit/evidence requirements, prohibited uses,
        roles and responsibilities, periodic review, glossary, URS traceability
        references, and regulatory reference table.

        Args:
            risk_context: Risk framework data for Risk_Integration_Blocks.
            version_number: Version number to embed in header.
            urs_available: Whether to include URS_Reference_Blocks.

        Returns:
            Complete master guideline Markdown string.
        """
        return assemble_master_guideline(risk_context, version_number, urs_available)

    async def _generate_sector_guideline(
        self,
        sector: SectorModule,
        risk_context: RiskFrameworkContext,
        version_number: int,
        urs_available: bool,
    ) -> str:
        """Generate a sector-specific guideline Markdown content.

        Assembles: header, sector regulatory context, sector-specific risk
        considerations, AI feature usage policies with sector restrictions,
        sector risk mapping table, validation requirements, record keeping
        requirements, dedicated subsections, roles and responsibilities,
        periodic review, cross-references, and regulatory reference table.

        Args:
            sector: The sector module configuration (Pharma/MedTech/IVD).
            risk_context: Risk framework data for sector risk mapping table.
            version_number: Version number to embed in header.
            urs_available: Whether to include URS cross-references.

        Returns:
            Complete sector guideline Markdown string.

        Raises:
            RuntimeError: If any section has fewer than 100 characters of content.
        """
        return assemble_sector_guideline(
            sector, risk_context, version_number, urs_available
        )

    def _validate_content(self, content: str, document_title: str) -> None:
        """Validate guideline content is non-empty and contains Markdown headings.

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

        heading_pattern = re.compile(r"^#{1,3}\s", re.MULTILINE)
        if not heading_pattern.search(content):
            raise RuntimeError(
                f"Generated content for '{document_title}' contains no "
                "Markdown headings (expected at least one level 1–3 heading)."
            )

    def _validate_section_lengths(self, content: str, document_title: str) -> None:
        """Validate that no section in a sector guideline has < 100 chars of content.

        Splits content by Markdown headings (## or ###) and checks each section
        body has at least 100 characters of content (excluding the header line).

        Args:
            content: The generated Markdown content.
            document_title: Title for error reporting.

        Raises:
            RuntimeError: If any section fails the minimum content check.
        """
        # Split content by ## or ### headings
        section_pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
        matches = list(section_pattern.finditer(content))

        for i, match in enumerate(matches):
            section_name = match.group(2).strip()
            # Section body starts after the heading line
            body_start = match.end()
            # Section body ends at the next heading or end of content
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_body = content[body_start:body_end].strip()

            if len(section_body) < 100:
                raise RuntimeError(
                    f"Section '{section_name}' in '{document_title}' has "
                    f"insufficient content ({len(section_body)} characters, "
                    f"minimum 100 required)."
                )

    async def _upload_or_version_document(
        self,
        title: str,
        content: str,
        company: Company,
        doc_admin: User,
        workflow: WorkflowDefinition,
    ) -> DocumentResult:
        """Create a new document or new version, apply tags and workflow.

        Detects existing document by title + tags ["AI-Guidelines", "ALC-GOV"]
        + company_id. Creates new Document if not found, or new DocumentVersion
        if found.

        Args:
            title: Document title for matching and creation.
            content: Markdown content to upload.
            company: ALC company entity.
            doc_admin: Document administrator user.
            workflow: Governance workflow definition.

        Returns:
            DocumentResult with document_id, uuid, version, is_new, tags, state.
        """
        existing_document = await self._detect_existing_document(title, company)
        is_new = existing_document is None

        # Ensure services are available
        uuid_service = self._uuid_service or UUIDService()
        storage_service = self._storage_service or StorageService()

        # Compute file hash (SHA-512)
        file_hash = hashlib.sha512(content.encode()).hexdigest()

        change_reason = (
            "AI Regulatory Guidelines Generation \u2014 "
            "Phase 8.4 automated governance document creation"
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
                document_type=GUIDELINE_DOCUMENT_TYPE,
                folder_path="/governance/ai-guidelines",
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
            stmt = select(func.max(DocumentVersion.major_version)).where(
                DocumentVersion.document_id == document.id
            )
            result = await self._session.execute(stmt)
            max_version = result.scalar_one_or_none() or 0
            version_number = max_version + 1

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

        # Resolve sector_id from title
        sector_id = self._resolve_sector_id(title)

        return DocumentResult(
            document_id=document.id,
            document_uuid=document.document_uuid,
            title=title,
            sector=sector_id,
            version_number=version_number,
            is_new_document=is_new,
            tags_applied=tags_applied,
            workflow_state=workflow_state,
        )

    async def _detect_existing_document(
        self, title: str, company: Company
    ) -> Document | None:
        """Find existing guideline document by title + tags + company_id.

        Queries for a Document that belongs to the given company AND has
        both "AI-Guidelines" and "ALC-GOV" tags AND matches the title exactly.

        Args:
            title: The document title to match.
            company: The ALC company entity.

        Returns:
            The existing Document if found, None otherwise.
        """
        # Subquery: find document_ids that have BOTH required tags
        subq = (
            select(DocumentTag.document_id)
            .where(DocumentTag.tag.in_(GUIDELINE_TAGS))
            .group_by(DocumentTag.document_id)
            .having(func.count(DocumentTag.tag.distinct()) == len(GUIDELINE_TAGS))
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
        """Apply "AI-Guidelines" and "ALC-GOV" tags (skip if already present).

        Args:
            document: The Document record to tag.
            is_new: Whether this is a newly created document.

        Returns:
            List of tag strings applied (always ["AI-Guidelines", "ALC-GOV"]).
        """
        # Query existing tags for this document
        stmt = select(DocumentTag).where(DocumentTag.document_id == document.id)
        result = await self._session.execute(stmt)
        existing_tags = {row.tag for row in result.scalars().all()}

        # Insert missing tags
        for tag in GUIDELINE_TAGS:
            if tag not in existing_tags:
                new_tag = DocumentTag(document_id=document.id, tag=tag)
                self._session.add(new_tag)

        await self._session.flush()

        return list(GUIDELINE_TAGS)

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
                extra={"guidelines_step": "apply_workflow"},
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
                extra={"guidelines_step": "apply_workflow"},
            )

        await self._session.flush()

        return "Draft"

    # ------------------------------------------------------------------
    # Helper Methods
    # ------------------------------------------------------------------

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

    def _count_policy_sections(self, content: str) -> int:
        """Count Policy_Section headings in generated content.

        Policy sections are identified by ### headings starting with "Policy:".

        Args:
            content: The generated Markdown content.

        Returns:
            Number of policy sections found.
        """
        pattern = re.compile(r"^### Policy:", re.MULTILINE)
        return len(pattern.findall(content))

    def _resolve_sector_id(self, title: str) -> str:
        """Resolve a document title to its sector identifier.

        Args:
            title: The document title.

        Returns:
            Sector identifier string.
        """
        if title == MASTER_GUIDELINE_TITLE:
            return "cross-sector"
        for sector in SECTOR_MODULES:
            if title == sector.title:
                return sector.sector_id
        return "unknown"

    def _get_all_frameworks(self) -> list:
        """Get all regulatory frameworks referenced across all documents.

        Returns:
            List of all RegulatoryFramework objects from the content module.
        """
        return REGULATORY_FRAMEWORKS
