"""lxml-based JATS XML sanitizer for scientific articles.

Parses JATS (Journal Article Tag Suite) XML documents and extracts
structured content into the unified StructuredContent schema. Handles
encoding detection, namespace-prefixed elements, and malformed XML.

References:
    - Requirements 6.2, 6.4, 6.5, 6.6, 6.7
"""

from __future__ import annotations

import re

from lxml import etree

from alcoabase.literature.ingestion.exceptions import SanitizationError
from alcoabase.literature.ingestion.schemas.structured_content import (
    BodySection,
    SourceFormat,
    StructuredContent,
)
from alcoabase.literature.ingestion.services.sanitization.pipeline import (
    BaseSanitizer,
)


class XMLJATSSanitizer(BaseSanitizer):
    """lxml-based JATS XML parser and content extractor.

    Maps JATS XML elements to StructuredContent fields:
        - front/article-meta/title-group/article-title → extracted_title
        - front/article-meta/abstract → extracted_abstract
        - body/sec → body_sections (heading + text pairs)
        - back/ref-list/ref → references

    Handles namespace-prefixed JATS documents and normalizes all
    text output to UTF-8.
    """

    # Common JATS namespace URIs
    _JATS_NAMESPACES: list[str] = [
        "http://jats.nlm.nih.gov",
        "http://www.niso.org/schemas/jats",
        "https://jats.nlm.nih.gov/ns/archiving/1.0/",
        "https://jats.nlm.nih.gov/ns/publishing/1.0/",
    ]

    async def sanitize(
        self,
        content: bytes,
        content_type: str,
    ) -> StructuredContent:
        """Parse JATS XML and extract structured content.

        Args:
            content: Raw XML file bytes.
            content_type: MIME type (application/xml, text/xml,
                or application/jats+xml).

        Returns:
            StructuredContent with mapped JATS fields.

        Raises:
            SanitizationError: If XML cannot be parsed or has
                encoding errors (error_type='parse_error').
        """
        # Step 1: Detect encoding and normalize to UTF-8
        xml_bytes = self._normalize_encoding(content)

        # Step 2: Parse with lxml
        root = self._parse_xml(xml_bytes)

        # Step 3: Detect namespace prefix
        ns = self._detect_namespace(root)

        # Step 4: Extract JATS elements
        title = self._extract_title(root, ns)
        abstract = self._extract_abstract(root, ns)
        body_sections = self._extract_body_sections(root, ns)
        references = self._extract_references(root, ns)

        # Step 5: Count figures and tables
        figure_count = self._count_elements(root, ns, "fig")
        table_count = self._count_elements(root, ns, "table-wrap")

        # Step 6: Construct raw_plaintext and word_count
        raw_plaintext = "\n".join(
            [title, abstract, *[s.text for s in body_sections]]
        )
        word_count = len(raw_plaintext.split())

        return StructuredContent(
            source_format=SourceFormat.XML,
            extracted_title=title,
            extracted_abstract=abstract,
            body_sections=body_sections,
            references=references,
            figure_count=figure_count,
            table_count=table_count,
            word_count=word_count,
            raw_plaintext=raw_plaintext,
        )

    def _normalize_encoding(self, content: bytes) -> bytes:
        """Detect encoding from XML declaration or BOM and normalize to UTF-8.

        Checks for:
            1. UTF-8 BOM (\\xef\\xbb\\xbf)
            2. UTF-16 LE/BE BOM
            3. Explicit encoding in XML declaration (<?xml ... encoding="...">)
            4. Falls back to UTF-8

        Args:
            content: Raw bytes from the file.

        Returns:
            Bytes re-encoded as UTF-8 (without BOM).

        Raises:
            SanitizationError: If the encoding cannot be detected or decoded.
        """
        # Strip BOM markers
        if content.startswith(b"\xef\xbb\xbf"):
            content = content[3:]
            return content  # Already UTF-8

        if content.startswith(b"\xff\xfe") or content.startswith(b"\xfe\xff"):
            # UTF-16 BOM detected
            encoding = "utf-16"
            try:
                text = content.decode(encoding)
                return text.encode("utf-8")
            except (UnicodeDecodeError, LookupError) as exc:
                raise SanitizationError(
                    f"Failed to decode UTF-16 XML content: {exc}",
                    error_type="parse_error",
                    content_type="application/xml",
                ) from exc

        # Check for encoding in XML declaration
        declared_encoding = self._extract_declared_encoding(content)
        if declared_encoding and declared_encoding.lower() != "utf-8":
            try:
                text = content.decode(declared_encoding)
                # Re-encode as UTF-8 and update the XML declaration
                utf8_bytes = text.encode("utf-8")
                # Replace the encoding declaration to reflect UTF-8
                utf8_bytes = re.sub(
                    rb'encoding=["\'][^"\']*["\']',
                    b'encoding="UTF-8"',
                    utf8_bytes,
                )
                return utf8_bytes
            except (UnicodeDecodeError, LookupError) as exc:
                raise SanitizationError(
                    f"Failed to decode XML with declared encoding "
                    f"'{declared_encoding}': {exc}",
                    error_type="parse_error",
                    content_type="application/xml",
                ) from exc

        # Default: assume UTF-8
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SanitizationError(
                f"XML content is not valid UTF-8 and has no encoding declaration: {exc}",
                error_type="parse_error",
                content_type="application/xml",
            ) from exc

        return content

    def _extract_declared_encoding(self, content: bytes) -> str | None:
        """Extract encoding from XML declaration if present.

        Args:
            content: Raw bytes (first 200 bytes are sufficient).

        Returns:
            Encoding string (e.g., 'ISO-8859-1') or None.
        """
        # Only look at the first 200 bytes for the declaration
        header = content[:200]
        match = re.search(rb'encoding=["\']([^"\']+)["\']', header)
        if match:
            return match.group(1).decode("ascii", errors="ignore")
        return None

    def _parse_xml(self, xml_bytes: bytes) -> etree._Element:
        """Parse XML bytes with lxml.

        Args:
            xml_bytes: UTF-8 encoded XML bytes.

        Returns:
            Root element of the parsed XML tree.

        Raises:
            SanitizationError: If XML is malformed (error_type='parse_error').
        """
        try:
            # Use a parser that recovers from minor errors
            parser = etree.XMLParser(
                recover=False,
                remove_comments=True,
                remove_pis=False,
                encoding="utf-8",
            )
            root = etree.fromstring(xml_bytes, parser=parser)
        except etree.XMLSyntaxError as exc:
            raise SanitizationError(
                f"Malformed XML: {exc}",
                error_type="parse_error",
                content_type="application/xml",
            ) from exc
        except Exception as exc:
            raise SanitizationError(
                f"Failed to parse XML document: {exc}",
                error_type="parse_error",
                content_type="application/xml",
            ) from exc

        return root

    def _detect_namespace(self, root: etree._Element) -> str | None:
        """Detect the JATS namespace from the root element.

        Args:
            root: Parsed XML root element.

        Returns:
            Namespace URI string or None for unnamespaced documents.
        """
        # Check root element tag for namespace
        tag = root.tag
        if tag.startswith("{"):
            ns_uri = tag.split("}")[0][1:]
            return ns_uri

        # Check nsmap for known JATS namespaces
        for prefix, uri in root.nsmap.items():
            if any(known in uri for known in self._JATS_NAMESPACES):
                return uri

        return None

    def _ns_path(self, path: str, ns: str | None) -> str:
        """Build an XPath with optional namespace prefix.

        Args:
            path: XPath without namespace (e.g., 'front/article-meta').
            ns: Namespace URI or None.

        Returns:
            Namespace-qualified XPath string.
        """
        if ns is None:
            return path

        # Prefix each path segment with the namespace
        parts = path.split("/")
        return "/".join(f"{{{ns}}}{part}" for part in parts)

    def _find(
        self, root: etree._Element, path: str, ns: str | None
    ) -> etree._Element | None:
        """Find an element using a simple path, handling namespaces.

        Args:
            root: Element to search from.
            path: Slash-separated path (e.g., 'front/article-meta').
            ns: Namespace URI or None.

        Returns:
            Found element or None.
        """
        ns_path = self._ns_path(path, ns)
        return root.find(ns_path)

    def _findall(
        self, root: etree._Element, path: str, ns: str | None
    ) -> list[etree._Element]:
        """Find all elements matching a path, handling namespaces.

        Args:
            root: Element to search from.
            path: Slash-separated path.
            ns: Namespace URI or None.

        Returns:
            List of matching elements.
        """
        ns_path = self._ns_path(path, ns)
        return root.findall(ns_path)

    def _get_text_content(self, element: etree._Element | None) -> str:
        """Recursively extract all text content from an element.

        Concatenates element text and tail text from all descendants,
        joining with spaces and collapsing whitespace.

        Args:
            element: XML element or None.

        Returns:
            Cleaned text string (empty string if element is None).
        """
        if element is None:
            return ""

        texts = list(element.itertext())
        raw = " ".join(texts)
        # Collapse multiple whitespace characters
        return re.sub(r"\s+", " ", raw).strip()

    def _extract_title(self, root: etree._Element, ns: str | None) -> str:
        """Extract article title from JATS front matter.

        Looks for: front/article-meta/title-group/article-title

        Args:
            root: Parsed XML root.
            ns: Namespace URI or None.

        Returns:
            Title text or empty string if not found.
        """
        title_elem = self._find(
            root, "front/article-meta/title-group/article-title", ns
        )
        if title_elem is not None:
            return self._get_text_content(title_elem)

        # Fallback: try without title-group wrapper
        title_elem = self._find(root, "front/article-meta/article-title", ns)
        if title_elem is not None:
            return self._get_text_content(title_elem)

        return ""

    def _extract_abstract(self, root: etree._Element, ns: str | None) -> str:
        """Extract abstract from JATS front matter.

        Looks for: front/article-meta/abstract
        Gets all text content including nested paragraphs.

        Args:
            root: Parsed XML root.
            ns: Namespace URI or None.

        Returns:
            Abstract text or empty string if not found.
        """
        abstract_elem = self._find(root, "front/article-meta/abstract", ns)
        return self._get_text_content(abstract_elem)

    def _extract_body_sections(
        self, root: etree._Element, ns: str | None
    ) -> list[BodySection]:
        """Extract body sections from JATS body element.

        Each <sec> element maps to a BodySection with:
            - <title> → heading
            - paragraph text → text

        Args:
            root: Parsed XML root.
            ns: Namespace URI or None.

        Returns:
            List of BodySection objects.
        """
        body_elem = self._find(root, "body", ns)
        if body_elem is None:
            return []

        sections: list[BodySection] = []
        sec_tag = f"{{{ns}}}sec" if ns else "sec"

        for sec_elem in body_elem.iter(sec_tag):
            heading = ""
            title_tag = f"{{{ns}}}title" if ns else "title"
            title_elem = sec_elem.find(title_tag)
            if title_elem is not None:
                heading = self._get_text_content(title_elem)

            # Get paragraph text from <p> elements within this section
            p_tag = f"{{{ns}}}p" if ns else "p"
            paragraphs: list[str] = []
            for p_elem in sec_elem.findall(p_tag):
                p_text = self._get_text_content(p_elem)
                if p_text:
                    paragraphs.append(p_text)

            text = " ".join(paragraphs)
            if heading or text:
                sections.append(BodySection(heading=heading, text=text))

        return sections

    def _extract_references(
        self, root: etree._Element, ns: str | None
    ) -> list[str]:
        """Extract references from JATS back matter.

        Looks for: back/ref-list/ref
        Gets text content of each <ref> element.

        Args:
            root: Parsed XML root.
            ns: Namespace URI or None.

        Returns:
            List of reference text strings.
        """
        ref_list_elem = self._find(root, "back/ref-list", ns)
        if ref_list_elem is None:
            return []

        ref_tag = f"{{{ns}}}ref" if ns else "ref"
        references: list[str] = []
        for ref_elem in ref_list_elem.findall(ref_tag):
            ref_text = self._get_text_content(ref_elem)
            if ref_text:
                references.append(ref_text)

        return references

    def _count_elements(
        self, root: etree._Element, ns: str | None, tag_name: str
    ) -> int:
        """Count occurrences of a specific element tag in the document.

        Args:
            root: Parsed XML root.
            ns: Namespace URI or None.
            tag_name: Local name of the element to count (e.g., 'fig').

        Returns:
            Count of matching elements.
        """
        full_tag = f"{{{ns}}}{tag_name}" if ns else tag_name
        return len(list(root.iter(full_tag)))
