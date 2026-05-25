"""Template Document Generator Service for AI Document Generator (Template-Based).

Orchestrates the full generation pipeline: knowledge retrieval, section-by-section
LLM generation, placeholder processing, and DOCX assembly. This is the core service
that coordinates template-based document generation.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 2.1-2.13, 4.1-4.10, 5.1, 5.2, 5.5, 5.7, 5.8, 7.5, 9.1-9.8
"""

import asyncio
import io
import logging
import re
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from docx import Document as DocxDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.config import get_settings
from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.document_generation import (
    CrossReferenceEntry,
    DocumentTemplate,
    GenerationJobMetadata,
    GenerationProvenance,
)
from alcoabase.services.cross_reference import CrossReferenceService
from alcoabase.services.inference_client import InferenceClient
from alcoabase.services.job_tracker import JobTracker
from alcoabase.services.knowledge_service import KnowledgeService
from alcoabase.services.placeholder_processor import (
    PlaceholderProcessor,
    SectionGenerationContext,
)
from alcoabase.services.storage_service import StorageService
from alcoabase.services.template_analysis import (
    TemplateAnalysis,
    TemplateAnalysisService,
    TemplateSection,
)

logger = logging.getLogger(__name__)

# Maximum output document size: 50 MB
MAX_OUTPUT_SIZE_BYTES = 50 * 1024 * 1024

# Maximum context window tokens for section generation
MAX_CONTEXT_TOKENS = 6000

# Maximum tokens for preceding sections summary
MAX_PRECEDING_SUMMARY_TOKENS = 1000

# Approximate characters per token (rough estimate for context management)
CHARS_PER_TOKEN = 4

# Placeholder text for failed sections
SECTION_FAILURE_PLACEHOLDER = (
    "[GENERATION FAILED: Section requires manual completion]"
)


@dataclass
class SectionResult:
    """Result of generating a single section.

    Attributes:
        heading: The section heading text.
        content: Generated prose/tables/lists content.
        token_count: Estimated token count for this section.
        inference_duration_ms: Time spent on LLM inference in milliseconds.
        kb_chunks_used: Knowledge base chunks used for this section.
        placeholder_processed: List of placeholder markers processed.
        generation_failed: Whether generation failed for this section.
        failure_reason: Reason for failure if generation_failed is True.
    """

    heading: str
    content: str
    token_count: int
    inference_duration_ms: int
    kb_chunks_used: list[dict[str, Any]] = field(default_factory=list)
    placeholder_processed: list[str] = field(default_factory=list)
    generation_failed: bool = False
    failure_reason: str | None = None


class TemplateDocumentGeneratorService:
    """AI-powered template-based document generation service.

    Orchestrates the full generation pipeline: template loading, knowledge
    retrieval, section-by-section LLM generation with context management,
    placeholder processing, DOCX assembly, and storage.

    Args:
        session_factory: Async session factory for database operations.
        inference_client: InferenceClient for vLLM chat completions.
        knowledge_service: KnowledgeService for RAG content retrieval.
        agent_registry: AgentRegistryService for agent archetype access.
        storage_service: StorageService for MinIO file operations.
        job_tracker: JobTracker for async job management.
        template_analysis_service: TemplateAnalysisService for template operations.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        inference_client: InferenceClient,
        knowledge_service: KnowledgeService,
        agent_registry: Any,
        storage_service: StorageService,
        job_tracker: JobTracker,
        template_analysis_service: TemplateAnalysisService,
    ) -> None:
        """Initialize the TemplateDocumentGeneratorService."""
        self._session_factory = session_factory
        self._inference_client = inference_client
        self._knowledge_service = knowledge_service
        self._agent_registry = agent_registry
        self._storage_service = storage_service
        self._job_tracker = job_tracker
        self._template_analysis_service = template_analysis_service
        self._cross_reference_service = CrossReferenceService(
            session_factory=session_factory,
            knowledge_service=knowledge_service,
            storage_service=storage_service,
        )
        self._placeholder_processor = PlaceholderProcessor(
            inference_client=inference_client,
            knowledge_service=knowledge_service,
            cross_reference_service=self._cross_reference_service,
        )

    async def request_generation(
        self,
        template_id: int,
        title: str,
        generation_instructions: str,
        output_folder_path: str,
        requesting_user_id: int,
        company_id: int,
        reference_document_ids: list[int] | None = None,
    ) -> str:
        """Validate inputs and dispatch async generation task. Returns job_id.

        Checks that the template exists and belongs to the company, validates
        reference document IDs, checks for concurrent jobs, creates a
        GenerationJobMetadata record, and dispatches the Celery task.

        Args:
            template_id: ID of the registered template to use.
            title: Title for the generated document (max 500 chars).
            generation_instructions: Instructions for content generation.
            output_folder_path: Target folder path for the output document.
            requesting_user_id: ID of the user requesting generation.
            company_id: Company ID for tenant scoping.
            reference_document_ids: Optional list of reference document IDs.

        Returns:
            The job_id string for tracking the generation task.

        Raises:
            ValueError: If template not found, reference docs invalid, or
                generation_instructions is empty/whitespace.
            RuntimeError: If a concurrent job exists for same template+title.
        """
        async with self._session_factory() as session:
            # Validate template exists and belongs to company
            template = await session.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.id == template_id,
                    DocumentTemplate.company_id == company_id,
                )
            )
            template_record = template.scalar_one_or_none()
            if template_record is None:
                raise ValueError(
                    f"Template {template_id} not found for company {company_id}"
                )

            # Validate generation_instructions is not empty/whitespace
            if not generation_instructions or not generation_instructions.strip():
                raise ValueError(
                    "Generation instructions are required and cannot be empty"
                )

            # Validate reference_document_ids if provided
            if reference_document_ids:
                for doc_id in reference_document_ids:
                    doc_result = await session.execute(
                        select(Document.id).where(
                            Document.id == doc_id,
                            Document.company_id == company_id,
                        )
                    )
                    if doc_result.scalar_one_or_none() is None:
                        raise ValueError(
                            f"Reference document {doc_id} not found "
                            f"for company {company_id}"
                        )

            # Check for concurrent generation (same template_id + title + company)
            concurrent_result = await session.execute(
                select(GenerationJobMetadata).where(
                    GenerationJobMetadata.template_id == template_id,
                    GenerationJobMetadata.title == title,
                    GenerationJobMetadata.company_id == company_id,
                    GenerationJobMetadata.status == "processing",
                )
            )
            concurrent_job = concurrent_result.scalar_one_or_none()
            if concurrent_job is not None:
                raise RuntimeError(
                    f"Concurrent generation job already exists: "
                    f"{concurrent_job.job_id}"
                )

            # Determine sections_total from template analysis
            sections_total = 1
            if template_record.template_analysis:
                sections_total = max(
                    template_record.template_analysis.get("total_sections", 1),
                    1,
                )

            # Create GenerationJobMetadata record
            job_id = str(uuid.uuid4())
            job_metadata = GenerationJobMetadata(
                job_id=job_id,
                template_id=template_id,
                company_id=company_id,
                requesting_user_id=requesting_user_id,
                title=title,
                generation_instructions=generation_instructions,
                reference_document_ids=reference_document_ids or [],
                output_folder_path=output_folder_path,
                status="processing",
                progress_percent=0,
                sections_completed=0,
                sections_total=sections_total,
            )
            session.add(job_metadata)

            # Create job via JobTracker
            doc_result = await session.execute(
                select(Document.document_uuid).where(
                    Document.id == template_record.document_id
                )
            )
            document_uuid = doc_result.scalar_one_or_none() or str(uuid.uuid4())

            await self._job_tracker.create_job(
                session=session,
                document_uuid=document_uuid,
                operation="template_document_generation",
                estimated_duration_seconds=30 * sections_total,
                company_id=company_id,
            )

            await session.commit()

        # Dispatch Celery task
        from alcoabase.tasks.document_generation_tasks import generate_document_task

        generate_document_task.delay(
            job_id=job_id,
            template_id=template_id,
            title=title,
            generation_instructions=generation_instructions,
            output_folder_path=output_folder_path,
            requesting_user_id=requesting_user_id,
            company_id=company_id,
            reference_document_ids=reference_document_ids,
        )

        logger.info(
            "Dispatched generation job %s for template %d, title='%s'",
            job_id,
            template_id,
            title,
        )

        return job_id

    async def get_job_status(
        self,
        job_id: str,
        company_id: int,
    ) -> GenerationJobMetadata | None:
        """Retrieve generation job status and progress with company scoping.

        Args:
            job_id: The UUID string of the generation job.
            company_id: Company ID for tenant scoping.

        Returns:
            The GenerationJobMetadata record if found and belongs to company,
            or None if not found.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(GenerationJobMetadata).where(
                    GenerationJobMetadata.job_id == job_id,
                    GenerationJobMetadata.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()

    # -----------------------------------------------------------------------
    # Core generation pipeline (called within Celery task)
    # -----------------------------------------------------------------------

    async def execute_generation_pipeline(
        self,
        job_id: str,
        template_id: int,
        title: str,
        generation_instructions: str,
        output_folder_path: str,
        requesting_user_id: int,
        company_id: int,
        reference_document_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Full generation pipeline. Returns result metadata dict.

        Pipeline phases:
        1. Load Template (10%)
        2. Knowledge Retrieval + Cross-Reference Map (20%)
        3. Section-by-section generation (20-90%)
        4. DOCX Assembly (95%)
        5. Storage & Records (100%)

        Args:
            job_id: The UUID of the generation job.
            template_id: ID of the template to use.
            title: Title for the generated document.
            generation_instructions: User-provided instructions.
            output_folder_path: Target folder path for output.
            requesting_user_id: ID of the requesting user.
            company_id: Company ID for tenant scoping.
            reference_document_ids: Optional reference document IDs.

        Returns:
            Dict with result metadata (document_id, storage_key, etc.).

        Raises:
            ValueError: If template not found or KB returns no results.
            RuntimeError: If provenance cannot be persisted.
        """
        start_time = time.time()
        settings = get_settings()

        # Phase 1: Load Template (10%)
        async with self._session_factory() as session:
            template_result = await session.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.id == template_id,
                    DocumentTemplate.company_id == company_id,
                )
            )
            template_record = template_result.scalar_one_or_none()
            if template_record is None:
                raise ValueError(
                    f"Template {template_id} not found for company {company_id}"
                )

            # Load template analysis
            template_analysis_data = template_record.template_analysis
            if not template_analysis_data:
                raise ValueError(
                    f"Template {template_id} has no analysis data"
                )

            document_type_target = template_record.document_type_target

            # Get the template .docx bytes from storage
            version_result = await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.id == template_record.document_version_id
                )
            )
            version = version_result.scalar_one_or_none()
            if version is None:
                raise ValueError(
                    f"Template version {template_record.document_version_id} not found"
                )

        template_bytes = await self._storage_service.download_file(
            version.storage_key
        )

        # Reconstruct TemplateAnalysis from stored JSON
        section_hierarchy = [
            TemplateSection(
                heading=s.get("heading", ""),
                level=s.get("level", 1),
                position=s.get("position", i),
                has_placeholder=s.get("has_placeholder", False),
                placeholder_markers=s.get("placeholder_markers", []),
                has_table=s.get("has_table", False),
                table_columns=s.get("table_columns"),
            )
            for i, s in enumerate(
                template_analysis_data.get("section_hierarchy", [])
            )
        ]

        template_analysis = TemplateAnalysis(
            section_hierarchy=section_hierarchy,
            numbering_scheme=template_analysis_data.get("numbering_scheme", "none"),
            paragraph_styles=template_analysis_data.get("paragraph_styles", []),
            table_structures=template_analysis_data.get("table_structures", []),
            header_footer_patterns=template_analysis_data.get(
                "header_footer_patterns", {}
            ),
            placeholder_markers=template_analysis_data.get(
                "placeholder_markers", []
            ),
            total_sections=template_analysis_data.get("total_sections", 0),
            has_toc=template_analysis_data.get("has_toc", False),
            page_layout=template_analysis_data.get("page_layout", {}),
        )

        # Update progress to 10%
        await self._update_job_progress(job_id, 10, company_id)

        # Phase 2: Knowledge Retrieval + Cross-Reference Map (20%)
        kb_chunks, reference_excerpts = await self.retrieve_knowledge_context(
            generation_instructions=generation_instructions,
            document_type_target=document_type_target,
            reference_document_ids=reference_document_ids,
            company_id=company_id,
        )

        # Check if KB returned any results (Requirement 2.11)
        if not kb_chunks and not reference_excerpts:
            raise ValueError(
                "Knowledge base returned no relevant content. "
                "Insufficient source material for generation."
            )

        # Build cross-reference map from reference documents
        cross_reference_map: dict[str, list[Any]] = {}
        if reference_document_ids:
            cross_reference_map = await self._cross_reference_service.build_cross_reference_map(
                reference_document_ids=reference_document_ids,
                company_id=company_id,
            )

        await self._update_job_progress(job_id, 20, company_id)

        # Phase 3: Section-by-section generation (20-90%)
        sections = template_analysis.section_hierarchy
        total_sections = len(sections) if sections else 1
        section_results: list[SectionResult] = []
        total_token_count = 0
        total_inference_duration_ms = 0
        source_document_uuids: set[str] = set()

        for idx, section in enumerate(sections):
            # Calculate progress (20% to 90% distributed across sections)
            section_progress = 20 + int((idx + 1) / total_sections * 70)

            # Build context for this section
            preceding_summary, trimmed_chunks = self.manage_context_window(
                preceding_sections=section_results,
                kb_chunks=kb_chunks,
            )

            # Serialize cross_reference_map for context
            cross_ref_map_serialized: dict[str, list[dict[str, str]]] = {}
            for ref_type, refs in cross_reference_map.items():
                cross_ref_map_serialized[ref_type] = [
                    {
                        "reference_identifier": r.reference_identifier,
                        "reference_text": r.reference_text,
                        "source_document_title": r.source_document_title,
                    }
                    for r in refs
                ]

            context = SectionGenerationContext(
                section_heading=section.heading,
                section_level=section.level,
                section_position=section.position,
                total_sections=total_sections,
                preceding_sections_summary=preceding_summary,
                knowledge_base_chunks=trimmed_chunks,
                reference_doc_excerpts=reference_excerpts,
                placeholder_instructions=section.placeholder_markers,
                cross_reference_map=cross_ref_map_serialized,
                generation_instructions=generation_instructions,
                document_type_target=document_type_target,
            )

            # Generate section content
            section_result = await self.generate_section(context)
            section_results.append(section_result)

            # Track totals
            total_token_count += section_result.token_count
            total_inference_duration_ms += section_result.inference_duration_ms
            for chunk in section_result.kb_chunks_used:
                doc_uuid = chunk.get("chunk_document_uuid", "")
                if doc_uuid:
                    source_document_uuids.add(doc_uuid)

            # Process placeholders in this section
            if section.has_placeholder and section.placeholder_markers:
                for marker_str in section.placeholder_markers:
                    # Parse marker: {{IDENTIFIER}} or {{IDENTIFIER:parameter}}
                    identifier, parameter = self._parse_marker(marker_str)
                    if identifier:
                        placeholder_content = await self._placeholder_processor.process_placeholder(
                            marker=identifier,
                            parameter=parameter,
                            section_context=context,
                            cross_reference_map=cross_reference_map,
                        )
                        # Append placeholder content to section result
                        section_result.content += f"\n\n{placeholder_content}"
                        section_result.placeholder_processed.append(marker_str)

            # Update progress
            await self._update_job_progress(
                job_id, section_progress, company_id,
                current_section=section.heading,
                sections_completed=idx + 1,
            )

        # Phase 4: DOCX Assembly (95%)
        # Get company name and user name for document properties
        async with self._session_factory() as session:
            from alcoabase.models.company import Company
            from alcoabase.models.user import User

            company_result = await session.execute(
                select(Company.display_name).where(Company.id == company_id)
            )
            company_name = company_result.scalar_one_or_none() or "Unknown Company"

            user_result = await session.execute(
                select(User.full_name).where(User.id == requesting_user_id)
            )
            requesting_user_name = user_result.scalar_one_or_none() or "Unknown User"

        docx_bytes = await self.assemble_docx(
            template_bytes=template_bytes,
            sections=section_results,
            template_analysis=template_analysis,
            title=title,
            company_name=company_name,
            requesting_user_name=requesting_user_name,
        )

        # Validate output size (Requirement 2.6: 50 MB limit)
        if len(docx_bytes) > MAX_OUTPUT_SIZE_BYTES:
            # Truncate at last complete section boundary
            docx_bytes = await self._truncate_at_section_boundary(
                template_bytes, section_results, template_analysis,
                title, company_name, requesting_user_name,
            )
            logger.warning(
                "Generated document exceeded 50 MB limit, truncated at section boundary"
            )

        # Validate OPC compliance (Requirement 4.9)
        if not self.validate_output_docx(docx_bytes):
            raise RuntimeError(
                "Generated .docx file failed OPC validation (invalid ZIP structure)"
            )

        await self._update_job_progress(job_id, 95, company_id)

        # Phase 5: Storage & Records (100%)
        generation_duration_ms = int((time.time() - start_time) * 1000)
        file_size_bytes = len(docx_bytes)

        # Upload to MinIO
        storage_key = (
            f"{output_folder_path.rstrip('/')}/{title.replace(' ', '_')}"
            f"_{job_id[:8]}.docx"
        )
        await self._storage_service.upload_file(
            key=storage_key,
            data=docx_bytes,
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )

        # Create Document + DocumentVersion records
        async with self._session_factory() as session:
            # Generate document UUID
            from sqlalchemy import func as sa_func

            max_seq_result = await session.execute(
                select(sa_func.max(Document.id))
            )
            max_seq = max_seq_result.scalar_one_or_none() or 0
            year = datetime.now(timezone.utc).year
            document_uuid = f"{year}-{(max_seq + 1):05d}"

            document = Document(
                document_uuid=document_uuid,
                title=title,
                folder_path=output_folder_path,
                document_type=document_type_target,
                current_status="Draft",
                created_by=requesting_user_id,
                company_id=company_id,
            )
            session.add(document)
            await session.flush()

            import hashlib

            file_hash = hashlib.sha512(docx_bytes).hexdigest()
            doc_version = DocumentVersion(
                document_id=document.id,
                major_version=1,
                minor_version=0,
                storage_key=storage_key,
                file_hash=file_hash,
                uploaded_by=requesting_user_id,
                change_reason="AI-generated document from template",
            )
            session.add(doc_version)
            await session.flush()

            # Build section provenance data
            section_provenance_data = []
            for sr in section_results:
                section_provenance_data.append({
                    "section_heading": sr.heading,
                    "knowledge_base_query_used": generation_instructions,
                    "source_chunks_retrieved": [
                        {
                            "chunk_document_uuid": c.get("chunk_document_uuid", ""),
                            "chunk_text": c.get("chunk_text", "")[:200],
                            "relevance_score": c.get("relevance_score", 0),
                        }
                        for c in sr.kb_chunks_used
                    ],
                    "token_count_for_section": sr.token_count,
                    "inference_duration_ms_for_section": sr.inference_duration_ms,
                    "generation_failed": sr.generation_failed,
                    "failure_reason": sr.failure_reason,
                })

            # Validate cross-references in generated output
            full_generated_text = "\n\n".join(
                sr.content for sr in section_results
            )
            unverified_refs = await self._cross_reference_service.validate_references_in_output(
                generated_text=full_generated_text,
                cross_reference_map=cross_reference_map,
            )

            # Check for previous generation (Requirement 5.7)
            prev_gen_result = await session.execute(
                select(GenerationProvenance.generation_id)
                .where(
                    GenerationProvenance.template_id == template_id,
                    GenerationProvenance.company_id == company_id,
                )
                .order_by(GenerationProvenance.generation_timestamp.desc())
                .limit(1)
            )
            previous_generation_id = prev_gen_result.scalar_one_or_none()

            # Create GenerationProvenance (immutable, Requirement 5.1)
            generation_id = str(uuid.uuid4())
            provenance = GenerationProvenance(
                generation_id=generation_id,
                document_id=document.id,
                document_version_id=doc_version.id,
                template_id=template_id,
                company_id=company_id,
                requesting_user_id=requesting_user_id,
                agent_archetype="technical_writer",
                generation_parameters={
                    "temperature": 0.4,
                    "max_tokens": 8192,
                    "model_name": settings.model_chat_name,
                },
                source_document_uuids=list(source_document_uuids),
                reference_document_ids=reference_document_ids or [],
                section_provenance=section_provenance_data,
                total_inference_duration_ms=total_inference_duration_ms,
                total_token_count=total_token_count,
                unverified_references=unverified_refs,
                previous_generation_id=previous_generation_id,
                generation_timestamp=datetime.now(timezone.utc),
            )
            session.add(provenance)

            try:
                await session.flush()
            except Exception as e:
                # Requirement 5.8: Provenance write failure → entire job fails
                raise RuntimeError(
                    f"Failed to persist generation provenance: {e}"
                ) from e

            # Create CrossReferenceEntry records
            for ref_type, refs in cross_reference_map.items():
                for ref in refs:
                    cross_ref_entry = CrossReferenceEntry(
                        generation_provenance_id=provenance.id,
                        source_document_id=ref.source_document_id,
                        reference_type=ref.reference_type,
                        reference_identifier=ref.reference_identifier,
                        reference_text=ref.reference_text[:150] if ref.reference_text else None,
                        location_in_output={
                            "section_number": "0",
                            "paragraph_index": 0,
                        },
                        company_id=company_id,
                    )
                    session.add(cross_ref_entry)

            # Update GenerationJobMetadata to completed
            job_result = await session.execute(
                select(GenerationJobMetadata).where(
                    GenerationJobMetadata.job_id == job_id
                )
            )
            job_record = job_result.scalar_one_or_none()
            if job_record:
                job_record.status = "completed"
                job_record.progress_percent = 100
                job_record.sections_completed = len(section_results)
                job_record.result_document_id = document.id
                job_record.result_storage_key = storage_key
                job_record.file_size_bytes = file_size_bytes
                job_record.generation_duration_ms = generation_duration_ms
                job_record.completed_at = datetime.now(timezone.utc)
                job_record.current_section = None

            await session.commit()

        logger.info(
            "Generation pipeline completed for job %s: document_id=%d, "
            "duration=%dms, sections=%d",
            job_id,
            document.id,
            generation_duration_ms,
            len(section_results),
        )

        return {
            "job_id": job_id,
            "document_id": document.id,
            "document_uuid": document_uuid,
            "storage_key": storage_key,
            "file_size_bytes": file_size_bytes,
            "sections_generated": len(section_results),
            "sections_total": total_sections,
            "generation_duration_ms": generation_duration_ms,
            "total_token_count": total_token_count,
            "unverified_references_count": len(unverified_refs),
        }

    async def retrieve_knowledge_context(
        self,
        generation_instructions: str,
        document_type_target: str,
        reference_document_ids: list[int] | None,
        company_id: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Retrieve KB chunks and reference doc excerpts.

        Queries KnowledgeService with relevance >= 0.3, top 10 chunks.
        For reference documents, extracts excerpts up to 2000 chars each.

        Args:
            generation_instructions: User-provided generation instructions.
            document_type_target: Target document type for filtering.
            reference_document_ids: Optional list of reference document IDs.
            company_id: Company ID for tenant scoping.

        Returns:
            Tuple of (kb_chunks, reference_excerpts).
            kb_chunks: List of dicts with title, excerpt, relevance_score, etc.
            reference_excerpts: List of dicts with title and text (max 2000 chars).
        """
        # Query knowledge base for relevant chunks (Requirement 9.1)
        search_query = f"{generation_instructions} {document_type_target}"
        search_results, _total = self._knowledge_service.hybrid_search(
            query=search_query,
            user_id=0,  # System-level search
            limit=10,
            filters=None,
        )

        # Filter by relevance >= 0.3 (Requirement 9.1)
        kb_chunks: list[dict[str, Any]] = []
        for result in search_results:
            if result.relevance_score >= 0.3:
                kb_chunks.append({
                    "chunk_document_uuid": result.document_uuid,
                    "title": result.title,
                    "excerpt": result.excerpt,
                    "text": result.excerpt,
                    "relevance_score": result.relevance_score,
                    "document_type": result.document_type,
                })

        # Sort by descending relevance (Requirement 9.2)
        kb_chunks.sort(key=lambda c: c["relevance_score"], reverse=True)

        # Retrieve reference document excerpts (Requirement 9.3)
        reference_excerpts: list[dict[str, str]] = []
        if reference_document_ids:
            async with self._session_factory() as session:
                for doc_id in reference_document_ids:
                    try:
                        # Get document title and latest version
                        doc_result = await session.execute(
                            select(Document).where(
                                Document.id == doc_id,
                                Document.company_id == company_id,
                            )
                        )
                        doc = doc_result.scalar_one_or_none()
                        if doc is None:
                            continue

                        version_result = await session.execute(
                            select(DocumentVersion)
                            .where(DocumentVersion.document_id == doc_id)
                            .order_by(
                                DocumentVersion.major_version.desc(),
                                DocumentVersion.minor_version.desc(),
                            )
                            .limit(1)
                        )
                        version = version_result.scalar_one_or_none()
                        if version is None:
                            continue

                        # Download and extract text
                        file_bytes = await self._storage_service.download_file(
                            version.storage_key
                        )
                        text = self._knowledge_service.extract_text(
                            file_bytes,
                            content_type=self._guess_content_type(
                                version.storage_key
                            ),
                        )

                        # Truncate to 2000 chars (Requirement 9.3)
                        reference_excerpts.append({
                            "title": doc.title,
                            "text": text[:2000],
                            "document_id": str(doc_id),
                        })
                    except Exception:
                        logger.warning(
                            "Failed to retrieve reference document %d, skipping",
                            doc_id,
                        )
                        continue

        return kb_chunks, reference_excerpts

    async def generate_section(
        self,
        context: SectionGenerationContext,
    ) -> SectionResult:
        """Generate content for a single section via InferenceClient.

        Retries once on failure, inserts placeholder on second failure
        (Requirement 2.9).

        Args:
            context: The section generation context with all necessary data.

        Returns:
            SectionResult with generated content or placeholder on failure.
        """
        settings = get_settings()
        messages = self.build_section_prompt(context)

        start_time = time.time()

        try:
            content = await self._inference_client.chat_completion(
                model=settings.model_chat_name,
                messages=messages,
                temperature=0.4,
                max_tokens=8192,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            token_count = len(content) // CHARS_PER_TOKEN

            return SectionResult(
                heading=context.section_heading,
                content=content,
                token_count=token_count,
                inference_duration_ms=duration_ms,
                kb_chunks_used=[
                    {
                        "chunk_document_uuid": c.get("chunk_document_uuid", ""),
                        "chunk_text": c.get("text", c.get("excerpt", ""))[:200],
                        "relevance_score": c.get("relevance_score", 0),
                    }
                    for c in context.knowledge_base_chunks
                ],
            )

        except Exception as first_error:
            logger.warning(
                "Section '%s' generation failed (attempt 1): %s",
                context.section_heading,
                str(first_error),
            )

            # Retry once after 5-second delay (Requirement 2.9)
            await asyncio.sleep(5)

            try:
                start_time = time.time()
                content = await self._inference_client.chat_completion(
                    model=settings.model_chat_name,
                    messages=messages,
                    temperature=0.4,
                    max_tokens=8192,
                )
                duration_ms = int((time.time() - start_time) * 1000)
                token_count = len(content) // CHARS_PER_TOKEN

                return SectionResult(
                    heading=context.section_heading,
                    content=content,
                    token_count=token_count,
                    inference_duration_ms=duration_ms,
                    kb_chunks_used=[
                        {
                            "chunk_document_uuid": c.get("chunk_document_uuid", ""),
                            "chunk_text": c.get("text", c.get("excerpt", ""))[:200],
                            "relevance_score": c.get("relevance_score", 0),
                        }
                        for c in context.knowledge_base_chunks
                    ],
                )

            except Exception as second_error:
                logger.error(
                    "Section '%s' generation failed (attempt 2): %s",
                    context.section_heading,
                    str(second_error),
                )
                duration_ms = int((time.time() - start_time) * 1000)

                return SectionResult(
                    heading=context.section_heading,
                    content=SECTION_FAILURE_PLACEHOLDER,
                    token_count=0,
                    inference_duration_ms=duration_ms,
                    generation_failed=True,
                    failure_reason=str(second_error),
                )

    def build_section_prompt(
        self,
        context: SectionGenerationContext,
    ) -> list[dict[str, str]]:
        """Construct the messages array for the Technical Writer agent.

        Includes system prompt with cross-reference map, section context,
        and generation instructions.

        Args:
            context: The section generation context.

        Returns:
            List of message dicts with 'role' and 'content' keys.
        """
        # Build cross-reference context string
        cross_ref_context = ""
        if context.cross_reference_map:
            cross_ref_parts: list[str] = []
            for ref_type, refs in context.cross_reference_map.items():
                if refs:
                    cross_ref_parts.append(f"\n{ref_type.upper()} REFERENCES:")
                    for ref in refs[:20]:  # Limit to 20 per type
                        identifier = ref.get("reference_identifier", "")
                        text = ref.get("reference_text", "")[:100]
                        cross_ref_parts.append(f"  - {identifier}: {text}")
            cross_ref_context = "\n".join(cross_ref_parts)

        # Build KB context
        kb_context_parts: list[str] = []
        if context.reference_doc_excerpts:
            kb_context_parts.append("--- Reference Documents (Primary Sources) ---")
            for excerpt in context.reference_doc_excerpts:
                title = excerpt.get("title", "Reference")
                text = excerpt.get("text", "")
                kb_context_parts.append(f"[{title}]: {text}")

        if context.knowledge_base_chunks:
            kb_context_parts.append("--- Knowledge Base ---")
            for chunk in context.knowledge_base_chunks:
                title = chunk.get("title", "")
                text = chunk.get("excerpt", chunk.get("text", ""))
                score = chunk.get("relevance_score", 0)
                kb_context_parts.append(
                    f"[{title} (relevance: {score:.2f})]: {text}"
                )

        kb_context = "\n".join(kb_context_parts) if kb_context_parts else ""

        # System prompt with Technical Writer persona
        system_prompt = (
            "You are a Technical Writer specializing in regulatory documentation "
            "for GxP-regulated environments (pharmaceutical, biotech, manufacturing). "
            f"You are generating content for a {context.document_type_target} document.\n\n"
            "RULES:\n"
            "1. Write clear, precise, professional prose appropriate for regulatory documents.\n"
            "2. Use the provided knowledge base content as source material.\n"
            "3. Do NOT fabricate references, identifiers, or document numbers.\n"
            "4. When referencing other documents, use ONLY identifiers from the "
            "Cross-Reference Map provided below.\n"
            "5. Maintain consistency with preceding sections.\n"
            "6. Generate content appropriate to the section heading and document type.\n"
        )

        if cross_ref_context:
            system_prompt += (
                f"\nCROSS-REFERENCE MAP (use these exact identifiers):"
                f"{cross_ref_context}\n"
            )

        # User message with section context
        user_content = (
            f"SECTION: {context.section_heading} "
            f"(Level {context.section_level}, "
            f"Position {context.section_position + 1}/{context.total_sections})\n\n"
            f"DOCUMENT TYPE: {context.document_type_target}\n\n"
            f"GENERATION INSTRUCTIONS: {context.generation_instructions}\n\n"
        )

        if context.preceding_sections_summary:
            user_content += (
                f"PRECEDING SECTIONS SUMMARY:\n"
                f"{context.preceding_sections_summary}\n\n"
            )

        if kb_context:
            user_content += f"SOURCE MATERIAL:\n{kb_context}\n\n"

        if context.placeholder_instructions:
            user_content += (
                f"PLACEHOLDER MARKERS IN THIS SECTION: "
                f"{', '.join(context.placeholder_instructions)}\n\n"
            )

        user_content += (
            "Generate the section content. Write professional regulatory prose "
            "that addresses the section heading topic."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def manage_context_window(
        self,
        preceding_sections: list[SectionResult],
        kb_chunks: list[dict[str, Any]],
        max_tokens: int = MAX_CONTEXT_TOKENS,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Summarize preceding sections and trim KB chunks if context exceeds limit.

        If the combined context exceeds max_tokens (6000), preceding sections
        are summarized to max 1000 tokens and only top 5 KB chunks are kept.

        Args:
            preceding_sections: List of previously generated section results.
            kb_chunks: Knowledge base chunks ordered by relevance.
            max_tokens: Maximum total context tokens (default 6000).

        Returns:
            Tuple of (summarized_preceding, trimmed_chunks).
        """
        # Build preceding sections summary
        preceding_parts: list[str] = []
        for sr in preceding_sections:
            # Include heading and first 200 chars of content
            summary_text = f"[{sr.heading}]: {sr.content[:200]}"
            preceding_parts.append(summary_text)

        preceding_summary = "\n".join(preceding_parts)

        # Estimate token counts
        preceding_tokens = len(preceding_summary) // CHARS_PER_TOKEN
        kb_tokens = sum(
            len(c.get("excerpt", c.get("text", ""))) // CHARS_PER_TOKEN
            for c in kb_chunks
        )
        total_tokens = preceding_tokens + kb_tokens

        # If within limits, return as-is
        if total_tokens <= max_tokens:
            return preceding_summary, kb_chunks

        # Context exceeds limit: summarize preceding to max 1000 tokens
        # and keep only top 5 KB chunks (Requirement 9.4)
        max_preceding_chars = MAX_PRECEDING_SUMMARY_TOKENS * CHARS_PER_TOKEN
        if len(preceding_summary) > max_preceding_chars:
            # Truncate and add ellipsis
            preceding_summary = preceding_summary[:max_preceding_chars] + "..."

        # Keep only top 5 most relevant KB chunks
        trimmed_chunks = kb_chunks[:5]

        return preceding_summary, trimmed_chunks

    async def assemble_docx(
        self,
        template_bytes: bytes,
        sections: list[SectionResult],
        template_analysis: TemplateAnalysis,
        title: str,
        company_name: str,
        requesting_user_name: str,
    ) -> bytes:
        """Assemble output .docx preserving template formatting.

        Handles: styles, numbering, tables, headers/footers, TOC,
        images, section breaks, page breaks, document properties.
        Adds a Sources appendix at the end.

        Args:
            template_bytes: Raw bytes of the template .docx file.
            sections: List of generated section results.
            template_analysis: The template's structural analysis.
            title: Document title for properties and header substitution.
            company_name: Company name for properties and header substitution.
            requesting_user_name: Author name for document properties.

        Returns:
            Assembled .docx file as bytes.
        """
        # Load the template document
        doc = DocxDocument(io.BytesIO(template_bytes))

        # Populate document properties (Requirement 4.2)
        core_props = doc.core_properties
        core_props.title = title
        core_props.author = requesting_user_name
        core_props.company = company_name
        generation_date = datetime.now(timezone.utc)
        core_props.created = generation_date

        # Set custom property "generated_by" (Requirement 4.2)
        self._set_custom_property(
            doc, "generated_by", "AlcoaBase AI Document Generator v1.0"
        )

        # Substitute header/footer tokens (Requirement 4.3)
        date_str = generation_date.strftime("%Y-%m-%d")
        token_map = {
            "{title}": title,
            "{date}": date_str,
            "{version}": "1.0",
            "{company}": company_name,
        }
        self._substitute_header_footer_tokens(doc, token_map)

        # Replace section content in the document
        # Strategy: find heading paragraphs and replace content between them
        self._populate_sections(doc, sections, template_analysis)

        # Add Sources appendix (Requirement 5.5)
        self._add_sources_appendix(doc, sections)

        # Serialize to bytes
        output_buffer = io.BytesIO()
        doc.save(output_buffer)
        return output_buffer.getvalue()

    def validate_output_docx(self, docx_bytes: bytes) -> bool:
        """Validate output conforms to Open Packaging Conventions (valid ZIP).

        Checks that the output is a valid ZIP archive and contains the
        required content types file for OPC compliance.

        Args:
            docx_bytes: The assembled .docx file bytes.

        Returns:
            True if the file is a valid ZIP/OPC structure, False otherwise.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
                # Check for required OPC content types file
                names = zf.namelist()
                if "[Content_Types].xml" not in names:
                    return False
                # Verify no bad files in the archive
                bad_file = zf.testzip()
                if bad_file is not None:
                    return False
                return True
        except (zipfile.BadZipFile, Exception):
            return False

    # -----------------------------------------------------------------------
    # Private helper methods
    # -----------------------------------------------------------------------

    async def _update_job_progress(
        self,
        job_id: str,
        progress_percent: int,
        company_id: int,
        current_section: str | None = None,
        sections_completed: int | None = None,
    ) -> None:
        """Update GenerationJobMetadata progress.

        Args:
            job_id: The job UUID string.
            progress_percent: New progress percentage (0-100).
            company_id: Company ID for scoping.
            current_section: Name of current section being generated.
            sections_completed: Number of sections completed so far.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(GenerationJobMetadata).where(
                    GenerationJobMetadata.job_id == job_id
                )
            )
            job_record = result.scalar_one_or_none()
            if job_record:
                job_record.progress_percent = progress_percent
                if current_section is not None:
                    job_record.current_section = current_section
                if sections_completed is not None:
                    job_record.sections_completed = sections_completed
                await session.commit()

    def _parse_marker(self, marker_str: str) -> tuple[str | None, str | None]:
        """Parse a placeholder marker string into identifier and parameter.

        Handles formats: {{IDENTIFIER}} and {{IDENTIFIER:parameter}}

        Args:
            marker_str: The raw marker string (e.g., "{{TABLE:description}}").

        Returns:
            Tuple of (identifier, parameter). Both None if parsing fails.
        """
        match = re.match(
            r"\{\{([A-Z_]{1,50})(?::([^}]{1,100}))?\}\}", marker_str
        )
        if match:
            return match.group(1), match.group(2)
        return None, None

    @staticmethod
    def _guess_content_type(storage_key: str) -> str:
        """Guess content type from storage key extension.

        Args:
            storage_key: The MinIO storage key (file path).

        Returns:
            MIME type string.
        """
        lower_key = storage_key.lower()
        if lower_key.endswith(".docx"):
            return (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            )
        elif lower_key.endswith(".pdf"):
            return "application/pdf"
        elif lower_key.endswith(".txt"):
            return "text/plain"
        return "application/octet-stream"

    def _set_custom_property(
        self, doc: DocxDocument, name: str, value: str
    ) -> None:
        """Set a custom document property on the .docx file.

        Uses the OPC custom properties part to add a custom property.

        Args:
            doc: The python-docx Document object.
            name: Property name.
            value: Property value.
        """
        from docx.opc.constants import RELATIONSHIP_TYPE as RT

        try:
            # Access or create custom properties part
            custom_props_part = None
            for rel in doc.part.rels.values():
                if "custom-properties" in rel.reltype:
                    custom_props_part = rel.target_part
                    break

            if custom_props_part is None:
                # Custom properties not supported in basic python-docx
                # Store as a comment in core properties instead
                existing_comments = doc.core_properties.comments or ""
                doc.core_properties.comments = (
                    f"{existing_comments}\n{name}: {value}".strip()
                )
        except Exception:
            # Fallback: store in comments
            existing_comments = doc.core_properties.comments or ""
            doc.core_properties.comments = (
                f"{existing_comments}\n{name}: {value}".strip()
            )

    def _substitute_header_footer_tokens(
        self, doc: DocxDocument, token_map: dict[str, str]
    ) -> None:
        """Substitute dynamic tokens in headers and footers.

        Replaces {title}, {date}, {version}, {company} tokens with actual
        values. Unrecognized {identifier} tokens are left unchanged
        (Requirement 4.3).

        Args:
            doc: The python-docx Document object.
            token_map: Dict mapping token strings to replacement values.
        """
        for section in doc.sections:
            # Process headers
            try:
                header = section.header
                if header:
                    for paragraph in header.paragraphs:
                        for token, replacement in token_map.items():
                            if token in paragraph.text:
                                # Replace in runs to preserve formatting
                                self._replace_in_paragraph(
                                    paragraph, token, replacement
                                )
            except Exception:
                pass

            # Process footers
            try:
                footer = section.footer
                if footer:
                    for paragraph in footer.paragraphs:
                        for token, replacement in token_map.items():
                            if token in paragraph.text:
                                self._replace_in_paragraph(
                                    paragraph, token, replacement
                                )
            except Exception:
                pass

    @staticmethod
    def _replace_in_paragraph(paragraph: Any, old_text: str, new_text: str) -> None:
        """Replace text in a paragraph while preserving run formatting.

        Concatenates all run text, performs replacement, then updates
        the first run and clears the rest.

        Args:
            paragraph: A python-docx Paragraph object.
            old_text: Text to find.
            new_text: Replacement text.
        """
        if not paragraph.runs:
            return

        # Concatenate all run text
        full_text = "".join(run.text for run in paragraph.runs)
        if old_text not in full_text:
            return

        # Perform replacement
        new_full_text = full_text.replace(old_text, new_text)

        # Update runs: put all text in first run, clear others
        paragraph.runs[0].text = new_full_text
        for run in paragraph.runs[1:]:
            run.text = ""

    def _populate_sections(
        self,
        doc: DocxDocument,
        sections: list[SectionResult],
        template_analysis: TemplateAnalysis,
    ) -> None:
        """Populate document sections with generated content.

        Finds heading paragraphs in the document and inserts generated
        content after each heading, replacing any placeholder markers.
        Preserves template formatting (styles, section breaks, page breaks).

        Args:
            doc: The python-docx Document object.
            sections: List of generated section results.
            template_analysis: The template's structural analysis.
        """
        # Build a map of section heading → generated content
        section_content_map: dict[str, str] = {}
        for sr in sections:
            section_content_map[sr.heading] = sr.content

        # Find heading paragraphs and insert content after them
        paragraphs = list(doc.paragraphs)
        heading_indices: list[int] = []

        for i, para in enumerate(paragraphs):
            style_name = para.style.name if para.style else ""
            if style_name and re.match(r"[Hh]eading\s*\d+", style_name):
                heading_indices.append(i)

        # Process each heading and its content area
        for i, para in enumerate(paragraphs):
            text = para.text.strip()

            # Check if this paragraph contains placeholder markers
            placeholder_pattern = re.compile(
                r"\{\{([A-Z_]{1,50})(?::([^}]{1,100}))?\}\}"
            )
            if placeholder_pattern.search(para.text):
                # Find matching section content
                matched_content = None
                for sr in sections:
                    if any(
                        marker in para.text
                        for marker in sr.placeholder_processed
                    ):
                        matched_content = sr.content
                        break

                if matched_content:
                    # Replace placeholder text with generated content
                    para.text = placeholder_pattern.sub("", para.text)
                    if not para.text.strip():
                        para.text = matched_content
                    else:
                        para.text = para.text + "\n" + matched_content
                else:
                    # Remove raw placeholder markers
                    para.text = placeholder_pattern.sub("", para.text)

            # For heading paragraphs, check if we have content to add
            style_name = para.style.name if para.style else ""
            if style_name and re.match(r"[Hh]eading\s*\d+", style_name):
                heading_text = text
                if heading_text in section_content_map:
                    # Content will be added after this heading
                    # Check if next paragraph is body text that should be replaced
                    pass

        # Second pass: add generated content after headings that don't have
        # body content yet (only placeholders or empty)
        for i, para in enumerate(paragraphs):
            style_name = para.style.name if para.style else ""
            if not (style_name and re.match(r"[Hh]eading\s*\d+", style_name)):
                continue

            heading_text = para.text.strip()
            if heading_text not in section_content_map:
                continue

            content = section_content_map[heading_text]

            # Find the insertion point (after heading, before next heading)
            # Add content as new paragraphs after the heading
            next_heading_idx = len(paragraphs)
            for j in range(i + 1, len(paragraphs)):
                next_style = paragraphs[j].style.name if paragraphs[j].style else ""
                if next_style and re.match(r"[Hh]eading\s*\d+", next_style):
                    next_heading_idx = j
                    break

            # Check if there's already substantial content between headings
            existing_content = ""
            for j in range(i + 1, next_heading_idx):
                existing_content += paragraphs[j].text

            # Only add content if existing content is minimal or placeholder
            if (
                not existing_content.strip()
                or SECTION_FAILURE_PLACEHOLDER in existing_content
                or "{{" in existing_content
            ):
                # Add generated content as a new paragraph after the heading
                # Use the document's add_paragraph for proper style inheritance
                new_para = doc.add_paragraph(content, style="Normal")
                # Move the new paragraph to after the heading
                para._element.addnext(new_para._element)

    def _add_sources_appendix(
        self, doc: DocxDocument, sections: list[SectionResult]
    ) -> None:
        """Add a Sources appendix at the end of the document.

        Lists all source documents used during generation, including
        document UUID, title, and which sections used them.
        (Requirement 5.5)

        Args:
            doc: The python-docx Document object.
            sections: List of generated section results with KB chunk info.
        """
        # Collect unique sources
        sources: dict[str, dict[str, Any]] = {}
        for sr in sections:
            for chunk in sr.kb_chunks_used:
                doc_uuid = chunk.get("chunk_document_uuid", "")
                if doc_uuid and doc_uuid not in sources:
                    sources[doc_uuid] = {
                        "document_uuid": doc_uuid,
                        "sections_used_in": [],
                    }
                if doc_uuid:
                    sources[doc_uuid]["sections_used_in"].append(sr.heading)

        # Add appendix heading
        doc.add_paragraph(
            "AI Generation Sources — For Audit Purposes",
            style="Heading 1",
        )

        if not sources:
            doc.add_paragraph(
                "No external sources were used during generation.",
                style="Normal",
            )
            return

        # Add source entries
        for doc_uuid, info in sources.items():
            sections_list = ", ".join(
                set(info["sections_used_in"][:10])
            )
            doc.add_paragraph(
                f"• Document UUID: {doc_uuid} | "
                f"Used in sections: {sections_list}",
                style="Normal",
            )

    async def _truncate_at_section_boundary(
        self,
        template_bytes: bytes,
        sections: list[SectionResult],
        template_analysis: TemplateAnalysis,
        title: str,
        company_name: str,
        requesting_user_name: str,
    ) -> bytes:
        """Truncate output at the last complete section within 50 MB.

        Progressively removes sections from the end until the output
        fits within the size limit.

        Args:
            template_bytes: Raw template .docx bytes.
            sections: All generated section results.
            template_analysis: Template structural analysis.
            title: Document title.
            company_name: Company name.
            requesting_user_name: Author name.

        Returns:
            Truncated .docx bytes within the 50 MB limit.
        """
        # Binary search for the maximum number of sections that fit
        for num_sections in range(len(sections) - 1, 0, -1):
            truncated_sections = sections[:num_sections]
            docx_bytes = await self.assemble_docx(
                template_bytes=template_bytes,
                sections=truncated_sections,
                template_analysis=template_analysis,
                title=title,
                company_name=company_name,
                requesting_user_name=requesting_user_name,
            )
            if len(docx_bytes) <= MAX_OUTPUT_SIZE_BYTES:
                return docx_bytes

        # Fallback: return with just the first section
        return await self.assemble_docx(
            template_bytes=template_bytes,
            sections=sections[:1],
            template_analysis=template_analysis,
            title=title,
            company_name=company_name,
            requesting_user_name=requesting_user_name,
        )
