"""Template Analysis Service for AI Document Generator (Template-Based).

Handles template registration, structural analysis via python-docx, and
placeholder detection for the Template-Based AI Document Generator (Phase 5.4).

Provides:
- Template registration with duplicate detection
- Structural analysis of .docx files (section hierarchy, numbering, styles,
  tables, headers/footers, placeholders, TOC, page layout)
- Placeholder marker detection using regex pattern matching
- Template retrieval and listing with company scoping and pagination

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.9, 1.10
"""

import io
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from docx import Document as DocxDocument
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import DocumentVersion
from alcoabase.models.document_generation import DocumentTemplate
from alcoabase.services.job_tracker import JobTracker
from alcoabase.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# Regex pattern for placeholder markers: {{IDENTIFIER}} or {{IDENTIFIER:parameter}}
# IDENTIFIER: 1-50 uppercase letters and underscores
# parameter: optional, 1-100 characters (anything except closing braces)
PLACEHOLDER_PATTERN = re.compile(
    r"\{\{([A-Z_]{1,50})(?::([^}]{1,100}))?\}\}"
)


@dataclass
class TemplateSection:
    """A section extracted from the template hierarchy.

    Attributes:
        heading: The heading text of the section.
        level: Heading level (1-4).
        position: 0-indexed order in the document.
        has_placeholder: Whether the section contains placeholder markers.
        placeholder_markers: List of placeholder marker strings in this section.
        has_table: Whether the section contains a table.
        table_columns: Column headers if a table is present.
    """

    heading: str
    level: int
    position: int
    has_placeholder: bool
    placeholder_markers: list[str] = field(default_factory=list)
    has_table: bool = False
    table_columns: list[str] | None = None


@dataclass
class TemplateAnalysis:
    """Complete structural analysis of a template document.

    Attributes:
        section_hierarchy: Ordered list of sections with heading levels.
        numbering_scheme: Detected numbering format (e.g., "1.1.1", "I.A.1").
        paragraph_styles: List of named paragraph styles used in the template.
        table_structures: List of table metadata dicts with columns and row_count.
        header_footer_patterns: Dict with header and footer text content.
        placeholder_markers: List of detected placeholder marker dicts.
        total_sections: Total number of sections detected.
        has_toc: Whether the template contains a Table of Contents.
        page_layout: Dict with margins, orientation, and page size.
    """

    section_hierarchy: list[TemplateSection]
    numbering_scheme: str
    paragraph_styles: list[str]
    table_structures: list[dict[str, Any]]
    header_footer_patterns: dict[str, str]
    placeholder_markers: list[dict[str, str]]
    total_sections: int
    has_toc: bool
    page_layout: dict[str, Any]


class TemplateAnalysisService:
    """Service for template registration and structural analysis.

    Coordinates template registration (with duplicate detection), dispatches
    async Celery tasks for analysis, and provides template retrieval with
    company-scoped access control.

    Attributes:
        _session_factory: Async session factory for database access.
        _storage_service: StorageService for MinIO file operations.
        _job_tracker: JobTracker for async job management.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage_service: StorageService,
        job_tracker: JobTracker,
    ) -> None:
        """Initialize the TemplateAnalysisService.

        Args:
            session_factory: Async session factory for database operations.
            storage_service: StorageService for MinIO document retrieval.
            job_tracker: JobTracker for creating and managing async jobs.
        """
        self._session_factory = session_factory
        self._storage_service = storage_service
        self._job_tracker = job_tracker

    async def register_template(
        self,
        document_id: int,
        document_version_id: int,
        template_name: str,
        document_type_target: str,
        registered_by: int,
        company_id: int,
    ) -> tuple[int, str | None]:
        """Register a document version as a Master Template.

        Checks for duplicate registrations (same document_version_id + company_id).
        If a duplicate exists, returns the existing template_id with job_id=None.
        Otherwise, creates a new DocumentTemplate record and dispatches a Celery
        task for structural analysis.

        Args:
            document_id: Source document ID.
            document_version_id: Specific version to register as template.
            template_name: Human-readable name for the template (max 500 chars).
            document_type_target: Target document type (e.g., "URS", "MVP", "SOP").
            registered_by: User ID of the person registering the template.
            company_id: Company scope for tenant isolation.

        Returns:
            Tuple of (template_id, job_id). job_id is None if template already
            exists (returns existing registration without creating a duplicate).

        Raises:
            ValueError: If the document_version_id does not exist or does not
                belong to the specified company, or if the file is not .docx.
        """
        async with self._session_factory() as session:
            # Check for existing template with same document_version_id + company_id
            existing_result = await session.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.document_version_id == document_version_id,
                    DocumentTemplate.company_id == company_id,
                )
            )
            existing_template = existing_result.scalar_one_or_none()

            if existing_template is not None:
                logger.info(
                    "Template already exists for version %d company %d: template_id=%d",
                    document_version_id,
                    company_id,
                    existing_template.id,
                )
                return (existing_template.id, None)

            # Validate document version exists and belongs to company
            version_result = await session.execute(
                select(DocumentVersion).where(
                    DocumentVersion.id == document_version_id,
                    DocumentVersion.document_id == document_id,
                )
            )
            version = version_result.scalar_one_or_none()

            if version is None:
                raise ValueError(
                    f"Document version {document_version_id} not found "
                    f"for document {document_id}"
                )

            # Validate .docx extension
            if not self.validate_docx_extension(version.storage_key):
                raise ValueError(
                    "Only .docx files can be registered as templates. "
                    f"File has storage key: {version.storage_key}"
                )

            # Create the template record with status "pending"
            template = DocumentTemplate(
                document_id=document_id,
                document_version_id=document_version_id,
                company_id=company_id,
                template_name=template_name,
                document_type_target=document_type_target,
                status="pending",
                registered_by=registered_by,
            )
            session.add(template)
            await session.flush()
            template_id = template.id

            # Create a job for tracking the async analysis
            from alcoabase.models.document import Document

            doc_result = await session.execute(
                select(Document.document_uuid).where(Document.id == document_id)
            )
            document_uuid = doc_result.scalar_one_or_none() or str(uuid.uuid4())

            job = await self._job_tracker.create_job(
                session=session,
                document_uuid=document_uuid,
                operation="template_analysis",
                estimated_duration_seconds=120,
                company_id=company_id,
            )

            await session.commit()

        # Dispatch Celery task for async analysis
        from alcoabase.tasks.document_generation_tasks import analyze_template_task

        analyze_template_task.delay(
            document_id=document_id,
            document_version_id=document_version_id,
            template_name=template_name,
            document_type_target=document_type_target,
            registered_by=registered_by,
            company_id=company_id,
            job_id=job.job_id,
        )

        logger.info(
            "Registered template %d for document %d version %d, job_id=%s",
            template_id,
            document_id,
            document_version_id,
            job.job_id,
        )

        return (template_id, job.job_id)

    async def get_template(
        self,
        template_id: int,
        company_id: int,
    ) -> DocumentTemplate | None:
        """Retrieve a registered template with its analysis.

        Args:
            template_id: The template ID to retrieve.
            company_id: Company scope for tenant isolation.

        Returns:
            The DocumentTemplate instance if found and belongs to the company,
            or None if not found.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(DocumentTemplate).where(
                    DocumentTemplate.id == template_id,
                    DocumentTemplate.company_id == company_id,
                )
            )
            return result.scalar_one_or_none()

    async def list_templates(
        self,
        company_id: int,
        document_type_target: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[DocumentTemplate], int]:
        """List templates with optional filtering and pagination.

        Args:
            company_id: Company scope for tenant isolation.
            document_type_target: Optional filter by target document type.
            limit: Maximum number of results to return (default 20).
            offset: Number of results to skip (default 0).

        Returns:
            Tuple of (list of DocumentTemplate instances, total count).
        """
        async with self._session_factory() as session:
            # Build base query with company scoping
            base_filter = [DocumentTemplate.company_id == company_id]
            if document_type_target is not None:
                base_filter.append(
                    DocumentTemplate.document_type_target == document_type_target
                )

            # Get total count
            count_query = select(func.count(DocumentTemplate.id)).where(
                *base_filter
            )
            total_result = await session.execute(count_query)
            total = total_result.scalar_one()

            # Get paginated results
            list_query = (
                select(DocumentTemplate)
                .where(*base_filter)
                .order_by(DocumentTemplate.registered_at.desc())
                .limit(limit)
                .offset(offset)
            )
            result = await session.execute(list_query)
            templates = list(result.scalars().all())

            return (templates, total)

    def analyze_template(self, docx_bytes: bytes) -> TemplateAnalysis:
        """Extract structural layout from a .docx file using python-docx.

        Detects: section hierarchy, numbering, styles, tables,
        headers/footers, placeholder markers, TOC, page layout.

        Args:
            docx_bytes: Raw bytes of the .docx file.

        Returns:
            TemplateAnalysis dataclass with the complete structural analysis.

        Raises:
            ValueError: If the bytes cannot be parsed as a valid .docx file.
        """
        try:
            doc = DocxDocument(io.BytesIO(docx_bytes))
        except Exception as e:
            raise ValueError(f"Failed to parse .docx file: {e}") from e

        # Extract section hierarchy
        sections = self._extract_section_hierarchy(doc)

        # Detect numbering scheme
        numbering_scheme = self._detect_numbering_scheme(sections)

        # Extract paragraph styles
        paragraph_styles = self._extract_paragraph_styles(doc)

        # Extract table structures
        table_structures = self._extract_table_structures(doc)

        # Extract header/footer patterns
        header_footer_patterns = self._extract_header_footer_patterns(doc)

        # Detect all placeholder markers across the document
        all_placeholders = self._extract_all_placeholders(doc)

        # Detect TOC
        has_toc = self._detect_toc(doc)

        # Extract page layout
        page_layout = self._extract_page_layout(doc)

        return TemplateAnalysis(
            section_hierarchy=sections,
            numbering_scheme=numbering_scheme,
            paragraph_styles=paragraph_styles,
            table_structures=table_structures,
            header_footer_patterns=header_footer_patterns,
            placeholder_markers=all_placeholders,
            total_sections=len(sections),
            has_toc=has_toc,
            page_layout=page_layout,
        )

    def detect_placeholders(self, text: str) -> list[dict[str, str]]:
        """Scan text for {{IDENTIFIER}} or {{IDENTIFIER:parameter}} patterns.

        Args:
            text: The text to scan for placeholder markers.

        Returns:
            List of dicts with keys: marker, identifier, parameter, position.
            Position is the character offset of the match in the text.
        """
        results: list[dict[str, str]] = []
        for match in PLACEHOLDER_PATTERN.finditer(text):
            identifier = match.group(1)
            parameter = match.group(2) or ""
            results.append({
                "marker": match.group(0),
                "identifier": identifier,
                "parameter": parameter,
                "position": str(match.start()),
            })
        return results

    def validate_docx_extension(self, storage_key: str) -> bool:
        """Check if storage_key indicates a .docx file.

        Args:
            storage_key: The MinIO storage key (file path) to validate.

        Returns:
            True if the storage_key ends with .docx (case-insensitive).
        """
        return storage_key.lower().endswith(".docx")

    # -----------------------------------------------------------------------
    # Private helper methods for template analysis
    # -----------------------------------------------------------------------

    def _extract_section_hierarchy(
        self, doc: DocxDocument
    ) -> list[TemplateSection]:
        """Extract section hierarchy from document headings.

        Scans all paragraphs for heading styles (Heading 1-4) and builds
        an ordered list of TemplateSection objects.

        Args:
            doc: The parsed python-docx Document object.

        Returns:
            Ordered list of TemplateSection objects.
        """
        sections: list[TemplateSection] = []
        position = 0
        current_section_text: list[str] = []
        current_tables: list[Any] = []

        # Track which paragraphs belong to which section
        # We'll iterate through body elements to associate tables with sections
        body_elements = list(doc.element.body)
        current_heading_idx = -1

        for paragraph in doc.paragraphs:
            style_name = paragraph.style.name if paragraph.style else ""

            # Check if this is a heading (Heading 1-4)
            heading_level = self._get_heading_level(style_name)

            if heading_level is not None and heading_level <= 4:
                # If we had a previous section, finalize it
                if current_heading_idx >= 0 and sections:
                    # Check for tables in the previous section's text
                    pass

                heading_text = paragraph.text.strip()
                if not heading_text:
                    continue

                # Detect placeholders in the heading and subsequent content
                placeholders = self.detect_placeholders(heading_text)
                placeholder_markers = [p["marker"] for p in placeholders]

                section = TemplateSection(
                    heading=heading_text,
                    level=heading_level,
                    position=position,
                    has_placeholder=len(placeholder_markers) > 0,
                    placeholder_markers=placeholder_markers,
                    has_table=False,
                    table_columns=None,
                )
                sections.append(section)
                position += 1
                current_heading_idx = len(sections) - 1
            elif sections:
                # Check paragraph text for placeholders and add to current section
                text = paragraph.text.strip()
                if text:
                    placeholders = self.detect_placeholders(text)
                    if placeholders:
                        current_section = sections[-1]
                        for p in placeholders:
                            if p["marker"] not in current_section.placeholder_markers:
                                current_section.placeholder_markers.append(
                                    p["marker"]
                                )
                        current_section.has_placeholder = True

        # Associate tables with sections
        self._associate_tables_with_sections(doc, sections)

        return sections

    def _associate_tables_with_sections(
        self, doc: DocxDocument, sections: list[TemplateSection]
    ) -> None:
        """Associate tables with their nearest preceding section.

        Args:
            doc: The parsed python-docx Document object.
            sections: List of sections to update with table info.
        """
        if not sections:
            return

        current_section_idx = -1
        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                # Check if this paragraph is a heading
                for p_elem in element.iter(qn("w:pStyle")):
                    style_val = p_elem.get(qn("w:val"), "")
                    level = self._get_heading_level(style_val)
                    if level is not None and level <= 4:
                        current_section_idx += 1
                        break

            elif tag == "tbl" and current_section_idx >= 0:
                if current_section_idx < len(sections):
                    sections[current_section_idx].has_table = True
                    # Extract column headers from first row
                    columns = self._extract_table_columns_from_element(element)
                    if columns:
                        sections[current_section_idx].table_columns = columns

    def _extract_table_columns_from_element(
        self, tbl_element: Any
    ) -> list[str] | None:
        """Extract column headers from the first row of a table XML element.

        Args:
            tbl_element: The w:tbl XML element.

        Returns:
            List of column header strings, or None if no headers found.
        """
        rows = tbl_element.findall(qn("w:tr"))
        if not rows:
            return None

        first_row = rows[0]
        columns: list[str] = []
        for cell in first_row.findall(qn("w:tc")):
            cell_text = ""
            for p in cell.findall(qn("w:p")):
                for r in p.findall(qn("w:r")):
                    for t in r.findall(qn("w:t")):
                        if t.text:
                            cell_text += t.text
            columns.append(cell_text.strip())

        return columns if any(columns) else None

    def _get_heading_level(self, style_name: str) -> int | None:
        """Extract heading level from a style name.

        Handles both display names ("Heading 1") and internal style IDs
        ("Heading1", "heading 1").

        Args:
            style_name: The paragraph style name or ID.

        Returns:
            Heading level (1-4) or None if not a heading style.
        """
        if not style_name:
            return None

        # Match "Heading 1", "Heading1", "heading 1", etc.
        match = re.match(r"[Hh]eading\s*(\d+)", style_name)
        if match:
            level = int(match.group(1))
            return level if 1 <= level <= 4 else None
        return None

    def _detect_numbering_scheme(
        self, sections: list[TemplateSection]
    ) -> str:
        """Detect the numbering scheme used in section headings.

        Analyzes heading text to determine if numbering follows patterns
        like "1.1.1", "I.A.1", or no numbering.

        Args:
            sections: List of extracted template sections.

        Returns:
            String describing the numbering scheme (e.g., "1.1.1", "none").
        """
        if not sections:
            return "none"

        # Check for decimal numbering (1, 1.1, 1.1.1, 1.1.1.1)
        # Matches patterns like "1 ", "1. ", "1.1 ", "1.1.1 " at start of heading
        decimal_pattern = re.compile(r"^(\d+(?:\.\d+)*)[.\s]")
        decimal_count = 0
        max_depth = 0

        for section in sections:
            match = decimal_pattern.match(section.heading)
            if match:
                decimal_count += 1
                # Count dots in the matched number portion
                number_part = match.group(1)
                depth = number_part.count(".") + 1
                max_depth = max(max_depth, depth)

        if decimal_count > len(sections) * 0.5:
            return ".".join(["1"] * max_depth) if max_depth > 0 else "1"

        # Check for Roman numeral numbering (I, II, III, IV, V)
        roman_pattern = re.compile(
            r"^(I{1,3}|IV|V|VI{0,3}|IX|X{0,3})[.\s]"
        )
        roman_count = sum(
            1 for s in sections if roman_pattern.match(s.heading)
        )
        if roman_count > len(sections) * 0.5:
            return "I.A.1"

        # Check for letter numbering (A, B, C)
        letter_pattern = re.compile(r"^[A-Z][.\s]")
        letter_count = sum(
            1 for s in sections if letter_pattern.match(s.heading)
        )
        if letter_count > len(sections) * 0.5:
            return "A.1"

        return "none"

    def _extract_paragraph_styles(self, doc: DocxDocument) -> list[str]:
        """Extract unique paragraph style names used in the document.

        Args:
            doc: The parsed python-docx Document object.

        Returns:
            Sorted list of unique paragraph style names.
        """
        styles: set[str] = set()
        for paragraph in doc.paragraphs:
            if paragraph.style and paragraph.style.name:
                styles.add(paragraph.style.name)
        return sorted(styles)

    def _extract_table_structures(
        self, doc: DocxDocument
    ) -> list[dict[str, Any]]:
        """Extract table metadata from the document.

        Args:
            doc: The parsed python-docx Document object.

        Returns:
            List of dicts with keys: columns (list of header strings),
            row_count (int).
        """
        table_structures: list[dict[str, Any]] = []

        for table in doc.tables:
            row_count = len(table.rows)
            columns: list[str] = []

            # Extract column headers from first row
            if table.rows:
                first_row = table.rows[0]
                for cell in first_row.cells:
                    columns.append(cell.text.strip())

            table_structures.append({
                "columns": columns,
                "row_count": row_count,
            })

        return table_structures

    def _extract_header_footer_patterns(
        self, doc: DocxDocument
    ) -> dict[str, str]:
        """Extract header and footer text content from the document.

        Extracts text from the default header and footer of the first section.

        Args:
            doc: The parsed python-docx Document object.

        Returns:
            Dict with keys "header" and "footer" containing text content.
        """
        header_text = ""
        footer_text = ""

        if doc.sections:
            first_section = doc.sections[0]

            # Extract header text
            try:
                header = first_section.header
                if header and header.paragraphs:
                    header_text = "\n".join(
                        p.text for p in header.paragraphs if p.text
                    )
            except Exception:
                pass

            # Extract footer text
            try:
                footer = first_section.footer
                if footer and footer.paragraphs:
                    footer_text = "\n".join(
                        p.text for p in footer.paragraphs if p.text
                    )
            except Exception:
                pass

        return {"header": header_text, "footer": footer_text}

    def _extract_all_placeholders(
        self, doc: DocxDocument
    ) -> list[dict[str, str]]:
        """Extract all placeholder markers from the entire document.

        Scans all paragraphs, tables, headers, and footers for placeholder
        patterns.

        Args:
            doc: The parsed python-docx Document object.

        Returns:
            List of dicts with keys: marker, identifier, parameter, position.
            Position here refers to the paragraph index where found.
        """
        all_placeholders: list[dict[str, str]] = []
        seen_markers: set[str] = set()

        # Scan paragraphs
        for idx, paragraph in enumerate(doc.paragraphs):
            text = paragraph.text
            if not text:
                continue
            placeholders = self.detect_placeholders(text)
            for p in placeholders:
                if p["marker"] not in seen_markers:
                    p["position"] = str(idx)
                    all_placeholders.append(p)
                    seen_markers.add(p["marker"])

        # Scan tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text = cell.text
                    if not text:
                        continue
                    placeholders = self.detect_placeholders(text)
                    for p in placeholders:
                        if p["marker"] not in seen_markers:
                            p["position"] = "table"
                            all_placeholders.append(p)
                            seen_markers.add(p["marker"])

        # Scan headers and footers
        for section in doc.sections:
            try:
                for p in section.header.paragraphs:
                    if p.text:
                        placeholders = self.detect_placeholders(p.text)
                        for ph in placeholders:
                            if ph["marker"] not in seen_markers:
                                ph["position"] = "header"
                                all_placeholders.append(ph)
                                seen_markers.add(ph["marker"])
            except Exception:
                pass

            try:
                for p in section.footer.paragraphs:
                    if p.text:
                        placeholders = self.detect_placeholders(p.text)
                        for ph in placeholders:
                            if ph["marker"] not in seen_markers:
                                ph["position"] = "footer"
                                all_placeholders.append(ph)
                                seen_markers.add(ph["marker"])
            except Exception:
                pass

        return all_placeholders

    def _detect_toc(self, doc: DocxDocument) -> bool:
        """Detect whether the document contains a Table of Contents.

        Checks for TOC field codes in the document XML.

        Args:
            doc: The parsed python-docx Document object.

        Returns:
            True if a TOC field is detected.
        """
        # Check for TOC field codes in the document body
        for element in doc.element.body.iter():
            if element.tag.endswith("}fldChar") or element.tag.endswith("}instrText"):
                if element.text and "TOC" in element.text.upper():
                    return True
            # Also check for structured document tag (SDT) based TOC
            if element.tag.endswith("}docPartGallery"):
                val = element.get(qn("w:val"), "")
                if "Table of Contents" in val or "TOC" in val.upper():
                    return True

        # Check for "TOC" style paragraphs
        for paragraph in doc.paragraphs:
            if paragraph.style and paragraph.style.name:
                if paragraph.style.name.lower().startswith("toc"):
                    return True

        return False

    def _extract_page_layout(self, doc: DocxDocument) -> dict[str, Any]:
        """Extract page layout information from the document.

        Extracts margins, orientation, and page size from the first section.

        Args:
            doc: The parsed python-docx Document object.

        Returns:
            Dict with keys: margins (dict), orientation (str), page_size (dict).
        """
        layout: dict[str, Any] = {
            "margins": {},
            "orientation": "portrait",
            "page_size": {},
        }

        if not doc.sections:
            return layout

        first_section = doc.sections[0]

        # Extract margins (convert from EMU to inches for readability)
        # 1 inch = 914400 EMU
        emu_per_inch = 914400
        try:
            layout["margins"] = {
                "top": round(first_section.top_margin / emu_per_inch, 2)
                if first_section.top_margin
                else 1.0,
                "bottom": round(first_section.bottom_margin / emu_per_inch, 2)
                if first_section.bottom_margin
                else 1.0,
                "left": round(first_section.left_margin / emu_per_inch, 2)
                if first_section.left_margin
                else 1.0,
                "right": round(first_section.right_margin / emu_per_inch, 2)
                if first_section.right_margin
                else 1.0,
            }
        except (TypeError, ZeroDivisionError):
            layout["margins"] = {
                "top": 1.0,
                "bottom": 1.0,
                "left": 1.0,
                "right": 1.0,
            }

        # Extract orientation
        try:
            if first_section.orientation == WD_ORIENT.LANDSCAPE:
                layout["orientation"] = "landscape"
            else:
                layout["orientation"] = "portrait"
        except Exception:
            layout["orientation"] = "portrait"

        # Extract page size (convert from EMU to inches)
        try:
            layout["page_size"] = {
                "width": round(first_section.page_width / emu_per_inch, 2)
                if first_section.page_width
                else 8.5,
                "height": round(first_section.page_height / emu_per_inch, 2)
                if first_section.page_height
                else 11.0,
            }
        except (TypeError, ZeroDivisionError):
            layout["page_size"] = {"width": 8.5, "height": 11.0}

        return layout
