"""Cross-Reference Service for AI Document Generator.

Extracts, stores, and validates cross-document references to ensure
generated documents correctly cite requirements, test cases, and sections
from related documents within the same company scope.

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import io
import logging
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.document_generation import CrossReferenceEntry
from alcoabase.services.knowledge_service import KnowledgeService
from alcoabase.services.storage_service import StorageService

logger = logging.getLogger(__name__)

# Maximum number of cross-reference entries extracted per reference document
MAX_ENTRIES_PER_DOCUMENT = 500

# Regex patterns for reference extraction
_REQUIREMENT_PATTERN = re.compile(
    r"\b(REQ-\d{1,5})\b"
)
_URS_PATTERN = re.compile(
    r"\b(URS-\d{1,3}\.\d{1,3})\b"
)
_TEST_CASE_PATTERN = re.compile(
    r"\b(TC-\d{1,5})\b"
)
_TEST_PATTERN = re.compile(
    r"\b(TEST-\d{1,5})\b"
)
# Heading-level numbering: matches "1", "1.1", "1.1.1", "1.1.1.1" at line start
# Must be at the beginning of a line and followed by whitespace or end of line
_SECTION_NUMBERING_PATTERN = re.compile(
    r"^(\d{1,3}(?:\.\d{1,3}){0,3})\s",
    re.MULTILINE,
)


@dataclass(frozen=True)
class CrossReference:
    """A single cross-reference extracted from a document.

    Attributes:
        reference_type: Type of reference ("requirement", "section", "test_case").
        reference_identifier: The extracted identifier (e.g., "REQ-00123", "1.2.3").
        reference_text: First 150 chars of the surrounding content.
        source_document_id: ID of the document this reference was extracted from.
        source_document_title: Title of the source document.
    """

    reference_type: str
    reference_identifier: str
    reference_text: str
    source_document_id: int
    source_document_title: str


class CrossReferenceService:
    """Service for cross-reference extraction, storage, and validation.

    Extracts identifiable items (requirement IDs, test case IDs, section
    numbers) from reference documents, builds a cross-reference map for
    use during document generation, and validates generated output for
    unverified references.

    Args:
        session_factory: Async session factory for database operations.
        knowledge_service: KnowledgeService for text extraction and search.
        storage_service: StorageService for downloading reference documents.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        knowledge_service: KnowledgeService,
        storage_service: StorageService,
    ) -> None:
        """Initialize CrossReferenceService.

        Args:
            session_factory: Async session factory for database operations.
            knowledge_service: KnowledgeService for text extraction and search.
            storage_service: StorageService for downloading reference documents.
        """
        self._session_factory = session_factory
        self._knowledge_service = knowledge_service
        self._storage_service = storage_service

    async def build_cross_reference_map(
        self,
        reference_document_ids: list[int],
        company_id: int,
    ) -> dict[str, list[CrossReference]]:
        """Extract identifiable items from reference documents.

        Builds a cross-reference map keyed by reference_type from the
        specified reference documents. Each document contributes at most
        MAX_ENTRIES_PER_DOCUMENT (500) entries.

        Patterns detected:
        - REQ-\\d{1,5} or URS-\\d{1,3}\\.\\d{1,3} → requirement
        - TC-\\d{1,5} or TEST-\\d{1,5} → test_case
        - Heading-level numbering (1, 1.1, 1.1.1, 1.1.1.1) → section

        Args:
            reference_document_ids: List of document IDs to extract references from.
            company_id: Company ID for tenant scoping.

        Returns:
            Dict keyed by reference_type ("requirement", "test_case", "section")
            with lists of CrossReference objects as values.
        """
        cross_ref_map: dict[str, list[CrossReference]] = {
            "requirement": [],
            "test_case": [],
            "section": [],
        }

        async with self._session_factory() as session:
            for doc_id in reference_document_ids:
                try:
                    refs = await self._extract_from_document(
                        session, doc_id, company_id
                    )
                    for ref in refs:
                        cross_ref_map[ref.reference_type].append(ref)
                except Exception:
                    # Requirement 3.8: Skip inaccessible documents, log warning
                    logger.warning(
                        "Failed to extract references from document %d, skipping",
                        doc_id,
                    )
                    continue

        return cross_ref_map

    async def _extract_from_document(
        self,
        session: AsyncSession,
        document_id: int,
        company_id: int,
    ) -> list[CrossReference]:
        """Extract references from a single document.

        Downloads the document from storage, extracts text, and parses
        for reference patterns. Enforces the 500-entry cap per document.

        Args:
            session: Active database session.
            document_id: ID of the document to extract from.
            company_id: Company ID for tenant scoping.

        Returns:
            List of CrossReference objects (max 500).

        Raises:
            ValueError: If document not found or doesn't belong to company.
        """
        # Query document with company scoping
        result = await session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.company_id == company_id,
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(
                f"Document {document_id} not found for company {company_id}"
            )

        # Get the latest version to download the file
        version_result = await session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(
                DocumentVersion.major_version.desc(),
                DocumentVersion.minor_version.desc(),
            )
            .limit(1)
        )
        version = version_result.scalar_one_or_none()
        if version is None:
            raise ValueError(
                f"No version found for document {document_id}"
            )

        # Download and extract text
        file_bytes = await self._storage_service.download_file(version.storage_key)
        text = self._extract_text_from_bytes(file_bytes, version.storage_key)

        # Extract references using the pure function
        refs = self.extract_references_from_text(
            text, document_id, document.title
        )

        # Enforce max 500 entries per document
        return refs[:MAX_ENTRIES_PER_DOCUMENT]

    def _extract_text_from_bytes(self, file_bytes: bytes, storage_key: str) -> str:
        """Extract text from file bytes based on file type.

        Args:
            file_bytes: Raw file content.
            storage_key: Storage key (used to determine file type).

        Returns:
            Extracted text content.
        """
        lower_key = storage_key.lower()
        if lower_key.endswith(".docx"):
            return self._knowledge_service._extract_docx_text(file_bytes)
        elif lower_key.endswith(".pdf"):
            return self._knowledge_service._extract_pdf_text(file_bytes)
        else:
            # Attempt plain text decoding for other formats
            try:
                return file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return file_bytes.decode("latin-1")

    def extract_references_from_text(
        self,
        text: str,
        document_id: int,
        document_title: str,
    ) -> list[CrossReference]:
        """Parse text for reference patterns. Pure function.

        Scans the provided text for requirement IDs, test case IDs, and
        section numbering patterns. Returns a deduplicated list of
        CrossReference objects.

        Args:
            text: The text content to scan for references.
            document_id: ID of the source document.
            document_title: Title of the source document.

        Returns:
            List of CrossReference objects found in the text.
        """
        references: list[CrossReference] = []
        seen_identifiers: set[str] = set()

        # Extract requirements (REQ-NNNNN)
        for match in _REQUIREMENT_PATTERN.finditer(text):
            identifier = match.group(1)
            if identifier not in seen_identifiers:
                seen_identifiers.add(identifier)
                context = self._get_surrounding_text(text, match.start(), 150)
                references.append(
                    CrossReference(
                        reference_type="requirement",
                        reference_identifier=identifier,
                        reference_text=context,
                        source_document_id=document_id,
                        source_document_title=document_title,
                    )
                )

        # Extract URS references (URS-N.N)
        for match in _URS_PATTERN.finditer(text):
            identifier = match.group(1)
            if identifier not in seen_identifiers:
                seen_identifiers.add(identifier)
                context = self._get_surrounding_text(text, match.start(), 150)
                references.append(
                    CrossReference(
                        reference_type="requirement",
                        reference_identifier=identifier,
                        reference_text=context,
                        source_document_id=document_id,
                        source_document_title=document_title,
                    )
                )

        # Extract test cases (TC-NNNNN)
        for match in _TEST_CASE_PATTERN.finditer(text):
            identifier = match.group(1)
            if identifier not in seen_identifiers:
                seen_identifiers.add(identifier)
                context = self._get_surrounding_text(text, match.start(), 150)
                references.append(
                    CrossReference(
                        reference_type="test_case",
                        reference_identifier=identifier,
                        reference_text=context,
                        source_document_id=document_id,
                        source_document_title=document_title,
                    )
                )

        # Extract test references (TEST-NNNNN)
        for match in _TEST_PATTERN.finditer(text):
            identifier = match.group(1)
            if identifier not in seen_identifiers:
                seen_identifiers.add(identifier)
                context = self._get_surrounding_text(text, match.start(), 150)
                references.append(
                    CrossReference(
                        reference_type="test_case",
                        reference_identifier=identifier,
                        reference_text=context,
                        source_document_id=document_id,
                        source_document_title=document_title,
                    )
                )

        # Extract section numbering (1, 1.1, 1.1.1, 1.1.1.1)
        for match in _SECTION_NUMBERING_PATTERN.finditer(text):
            identifier = match.group(1)
            if identifier not in seen_identifiers:
                seen_identifiers.add(identifier)
                context = self._get_surrounding_text(text, match.start(), 150)
                references.append(
                    CrossReference(
                        reference_type="section",
                        reference_identifier=identifier,
                        reference_text=context,
                        source_document_id=document_id,
                        source_document_title=document_title,
                    )
                )

        return references

    @staticmethod
    def _get_surrounding_text(text: str, position: int, max_length: int) -> str:
        """Extract surrounding text context around a match position.

        Gets text from the start of the line containing the match,
        truncated to max_length characters.

        Args:
            text: Full text content.
            position: Character position of the match.
            max_length: Maximum length of the context string.

        Returns:
            Surrounding text truncated to max_length.
        """
        # Find the start of the line containing the match
        line_start = text.rfind("\n", 0, position)
        line_start = line_start + 1 if line_start != -1 else 0

        # Find the end of the line
        line_end = text.find("\n", position)
        line_end = line_end if line_end != -1 else len(text)

        # Extract the line and truncate
        context = text[line_start:line_end].strip()
        if len(context) > max_length:
            context = context[:max_length]
        return context

    async def validate_references_in_output(
        self,
        generated_text: str,
        cross_reference_map: dict[str, list[CrossReference]],
    ) -> list[dict[str, Any]]:
        """Check generated text for references not in the cross-reference map.

        Scans the generated text for reference patterns and flags any that
        are not present in the provided cross-reference map as "unverified".

        Args:
            generated_text: The AI-generated document text to validate.
            cross_reference_map: The cross-reference map built from
                reference documents.

        Returns:
            List of dicts describing unverified references, each containing:
            - reference_identifier: The unverified reference string
            - reference_type: The detected type
            - location: Dict with section_number and paragraph_index
        """
        # Build a set of all known identifiers from the map
        known_identifiers: set[str] = set()
        for ref_list in cross_reference_map.values():
            for ref in ref_list:
                known_identifiers.add(ref.reference_identifier)

        unverified: list[dict[str, Any]] = []

        # Split text into paragraphs for location tracking
        paragraphs = generated_text.split("\n")
        current_section = "0"
        paragraph_index = 0

        for para_idx, paragraph in enumerate(paragraphs):
            # Track section numbering for location info
            section_match = _SECTION_NUMBERING_PATTERN.match(paragraph)
            if section_match:
                current_section = section_match.group(1)
                paragraph_index = 0
            else:
                paragraph_index += 1

            # Check for requirement references
            for pattern in [
                _REQUIREMENT_PATTERN,
                _URS_PATTERN,
                _TEST_CASE_PATTERN,
                _TEST_PATTERN,
            ]:
                for match in pattern.finditer(paragraph):
                    identifier = match.group(1)
                    if identifier not in known_identifiers:
                        # Determine reference type
                        if pattern in (_REQUIREMENT_PATTERN, _URS_PATTERN):
                            ref_type = "requirement"
                        else:
                            ref_type = "test_case"

                        unverified.append({
                            "reference_identifier": identifier,
                            "reference_type": ref_type,
                            "location": {
                                "section_number": current_section,
                                "paragraph_index": paragraph_index,
                            },
                        })

        return unverified

    async def get_cross_references(
        self,
        document_id: int,
        company_id: int,
    ) -> list[CrossReferenceEntry]:
        """Retrieve stored cross-references for a generated document.

        Queries the database for CrossReferenceEntry records associated
        with the generation provenance of the specified document.

        Args:
            document_id: ID of the generated document.
            company_id: Company ID for tenant scoping.

        Returns:
            List of CrossReferenceEntry records for the document.
        """
        from alcoabase.models.document_generation import GenerationProvenance

        async with self._session_factory() as session:
            result = await session.execute(
                select(CrossReferenceEntry)
                .join(
                    GenerationProvenance,
                    CrossReferenceEntry.generation_provenance_id
                    == GenerationProvenance.id,
                )
                .where(
                    GenerationProvenance.document_id == document_id,
                    CrossReferenceEntry.company_id == company_id,
                )
            )
            return list(result.scalars().all())

    async def auto_select_reference_documents(
        self,
        document_type: str,
        company_id: int,
        limit: int = 5,
    ) -> list[int]:
        """Auto-select top N documents of specified type from the knowledge base.

        When no reference_document_ids are explicitly provided and the template
        contains cross-reference placeholders, this method selects the most
        relevant documents of the specified type within the company scope.

        Args:
            document_type: The document type to search for (e.g., "URS", "SOP").
            company_id: Company ID for tenant scoping.
            limit: Maximum number of documents to return (default 5).

        Returns:
            List of document IDs for the selected reference documents.
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(Document.id)
                .where(
                    Document.company_id == company_id,
                    Document.document_type == document_type,
                    Document.current_status.in_(["Approved", "Active"]),
                )
                .order_by(Document.created_at.desc())
                .limit(limit)
            )
            return list(result.scalars().all())
