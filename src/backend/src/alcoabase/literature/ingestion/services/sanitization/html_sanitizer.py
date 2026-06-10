"""BeautifulSoup-based HTML content extraction and sanitization.

Removes navigation elements, scripts, stylesheets, advertisements,
cookie banners, and malicious elements/attributes. Extracts article
content into the unified StructuredContent schema.

References:
    - Requirements 6.1, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import codecs
import logging
import re

from bs4 import BeautifulSoup, Tag

from alcoabase.literature.ingestion.exceptions import SanitizationError
from alcoabase.literature.ingestion.schemas.structured_content import (
    BodySection,
    SourceFormat,
    StructuredContent,
)
from alcoabase.literature.ingestion.services.sanitization.pipeline import (
    BaseSanitizer,
)

logger = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────

# Elements that are always removed (malicious or non-content)
DANGEROUS_ELEMENTS: frozenset[str] = frozenset(
    {
        "script",
        "iframe",
        "object",
        "embed",
        "form",
        "style",
        "noscript",
    }
)

# Structural/navigation elements to remove
NAVIGATION_ELEMENTS: frozenset[str] = frozenset(
    {
        "nav",
        "footer",
        "header",
        "aside",
    }
)

# Dangerous event handler attributes
DANGEROUS_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "onclick",
        "onerror",
        "onload",
        "onmouseover",
        "onfocus",
        "onblur",
        "onsubmit",
        "onchange",
        "oninput",
        "onkeydown",
        "onkeyup",
        "onkeypress",
    }
)

# Class name patterns indicating ads or cookie banners
AD_COOKIE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcookie\b", re.IGNORECASE),
    re.compile(r"\bconsent\b", re.IGNORECASE),
    re.compile(r"\bad[-_]", re.IGNORECASE),
    re.compile(r"\badvertisement\b", re.IGNORECASE),
    re.compile(r"\bbanner\b", re.IGNORECASE),
    re.compile(r"\bgdpr\b", re.IGNORECASE),
    re.compile(r"\bpopup\b", re.IGNORECASE),
)

# BOM markers for encoding detection
_UTF8_BOM = codecs.BOM_UTF8
_UTF16_LE_BOM = codecs.BOM_UTF16_LE
_UTF16_BE_BOM = codecs.BOM_UTF16_BE


# ─── HTMLSanitizer ────────────────────────────────────────────────────────────


class HTMLSanitizer(BaseSanitizer):
    """BeautifulSoup-based HTML content extraction and sanitization.

    Processes raw HTML bytes through the following steps:
        1. Detect and decode character encoding (BOM, Content-Type, meta tag)
        2. Parse with BeautifulSoup
        3. Remove dangerous elements (script, iframe, object, embed, form, style)
        4. Remove navigation/structural noise (nav, footer, header, aside)
        5. Remove stylesheet link tags
        6. Remove cookie banners and advertisements by class/id patterns
        7. Strip dangerous attributes from all remaining elements
        8. Extract article content (title, abstract, body sections, references)
        9. Construct and return StructuredContent
    """

    async def sanitize(
        self,
        content: bytes,
        content_type: str,
    ) -> StructuredContent:
        """Extract structured content from raw HTML bytes.

        Args:
            content: Raw HTML file bytes.
            content_type: MIME type (expected "text/html").

        Returns:
            StructuredContent with extracted title, abstract, body sections,
            and references.

        Raises:
            SanitizationError: If the HTML cannot be parsed or decoded.
        """
        try:
            html_string = self._decode_content(content, content_type)
        except (UnicodeDecodeError, LookupError) as exc:
            raise SanitizationError(
                f"Failed to decode HTML content: {exc}",
                error_type="parse_error",
                content_type=content_type,
            ) from exc

        try:
            soup = BeautifulSoup(html_string, "html.parser")
        except Exception as exc:
            raise SanitizationError(
                f"Failed to parse HTML: {exc}",
                error_type="parse_error",
                content_type=content_type,
            ) from exc

        if soup.find() is None:
            raise SanitizationError(
                "HTML document contains no parseable elements.",
                error_type="parse_error",
                content_type=content_type,
            )

        # Sanitization passes
        self._remove_dangerous_elements(soup)
        self._remove_navigation_elements(soup)
        self._remove_stylesheet_links(soup)
        self._remove_ad_cookie_elements(soup)
        self._strip_dangerous_attributes(soup)

        # Content extraction
        article_root = self._find_article_content(soup)
        title = self._extract_title(soup, article_root)
        abstract = self._extract_abstract(article_root)
        body_sections = self._extract_body_sections(article_root)
        references = self._extract_references(article_root)

        # Build plaintext and word count
        section_texts = [s.text for s in body_sections]
        raw_plaintext = "\n".join([title, abstract, *section_texts])
        word_count = len(raw_plaintext.split())

        return StructuredContent(
            source_format=SourceFormat.HTML,
            extracted_title=title,
            extracted_abstract=abstract,
            body_sections=body_sections,
            references=references,
            figure_count=self._count_figures(article_root),
            table_count=self._count_tables(article_root),
            word_count=word_count,
            raw_plaintext=raw_plaintext,
        )

    # ─── Encoding Detection ──────────────────────────────────────────────

    def _decode_content(self, content: bytes, content_type: str) -> str:
        """Detect encoding and decode bytes to string.

        Detection priority:
            1. Byte Order Mark (BOM)
            2. charset parameter in Content-Type header
            3. <meta charset="..."> or <meta http-equiv="Content-Type"> tag
            4. Default to UTF-8

        Args:
            content: Raw bytes to decode.
            content_type: Content-Type header value (may contain charset).

        Returns:
            Decoded HTML string.

        Raises:
            UnicodeDecodeError: If decoding fails with detected encoding.
            LookupError: If the detected encoding name is invalid.
        """
        encoding = self._detect_encoding(content, content_type)
        # Strip BOM if present
        if content.startswith(_UTF8_BOM):
            content = content[len(_UTF8_BOM) :]
        elif content.startswith(_UTF16_LE_BOM) or content.startswith(_UTF16_BE_BOM):
            content = content[2:]

        return content.decode(encoding)

    def _detect_encoding(self, content: bytes, content_type: str) -> str:
        """Detect character encoding from multiple sources.

        Args:
            content: Raw bytes (checked for BOM).
            content_type: Content-Type header value.

        Returns:
            Encoding name string (e.g., "utf-8").
        """
        # 1. Check BOM
        if content.startswith(_UTF8_BOM):
            return "utf-8"
        if content.startswith(_UTF16_LE_BOM):
            return "utf-16-le"
        if content.startswith(_UTF16_BE_BOM):
            return "utf-16-be"

        # 2. Check Content-Type charset parameter
        charset = self._extract_charset_from_content_type(content_type)
        if charset:
            return charset

        # 3. Check HTML meta tags (parse first 4KB for speed)
        charset = self._extract_charset_from_meta(content[:4096])
        if charset:
            return charset

        # 4. Default to UTF-8
        return "utf-8"

    def _extract_charset_from_content_type(self, content_type: str) -> str | None:
        """Extract charset from Content-Type header value.

        Args:
            content_type: Header value (e.g., "text/html; charset=utf-8").

        Returns:
            Charset string or None if not found.
        """
        match = re.search(r"charset\s*=\s*([^\s;]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1).strip("\"'")
            # Validate the encoding name
            try:
                codecs.lookup(charset)
                return charset
            except LookupError:
                return None
        return None

    def _extract_charset_from_meta(self, head_bytes: bytes) -> str | None:
        """Extract charset from HTML meta tags in the first bytes.

        Looks for:
            - <meta charset="utf-8">
            - <meta http-equiv="Content-Type" content="text/html; charset=utf-8">

        Args:
            head_bytes: First ~4KB of the HTML document.

        Returns:
            Charset string or None if not found.
        """
        # Try to decode as ASCII for meta tag scanning (safe for charset detection)
        try:
            head_text = head_bytes.decode("ascii", errors="ignore")
        except Exception:
            return None

        # <meta charset="...">
        match = re.search(
            r'<meta\s+charset\s*=\s*["\']?([^"\'>\s]+)', head_text, re.IGNORECASE
        )
        if match:
            charset = match.group(1)
            try:
                codecs.lookup(charset)
                return charset
            except LookupError:
                pass

        # <meta http-equiv="Content-Type" content="...; charset=...">
        match = re.search(
            r'<meta\s+http-equiv\s*=\s*["\']?Content-Type["\']?\s+'
            r'content\s*=\s*["\'][^"\']*charset\s*=\s*([^"\';\s]+)',
            head_text,
            re.IGNORECASE,
        )
        if match:
            charset = match.group(1)
            try:
                codecs.lookup(charset)
                return charset
            except LookupError:
                pass

        return None

    # ─── Element Removal ─────────────────────────────────────────────────

    def _remove_dangerous_elements(self, soup: BeautifulSoup) -> None:
        """Remove all dangerous/malicious elements from the document.

        Removes: script, iframe, object, embed, form, style, noscript.

        Args:
            soup: BeautifulSoup document to modify in-place.
        """
        for tag_name in DANGEROUS_ELEMENTS:
            for element in soup.find_all(tag_name):
                element.decompose()

    def _remove_navigation_elements(self, soup: BeautifulSoup) -> None:
        """Remove structural navigation elements.

        Removes: nav, footer, header, aside.

        Args:
            soup: BeautifulSoup document to modify in-place.
        """
        for tag_name in NAVIGATION_ELEMENTS:
            for element in soup.find_all(tag_name):
                element.decompose()

    def _remove_stylesheet_links(self, soup: BeautifulSoup) -> None:
        """Remove stylesheet link tags.

        Args:
            soup: BeautifulSoup document to modify in-place.
        """
        for link in soup.find_all("link", rel="stylesheet"):
            link.decompose()
        # Also remove link tags with type="text/css"
        for link in soup.find_all("link", attrs={"type": "text/css"}):
            link.decompose()

    def _remove_ad_cookie_elements(self, soup: BeautifulSoup) -> None:
        """Remove elements matching advertisement/cookie banner patterns.

        Matches against class and id attributes using common patterns.

        Args:
            soup: BeautifulSoup document to modify in-place.
        """
        for element in soup.find_all(True):
            if not isinstance(element, Tag):
                continue

            class_str = " ".join(element.get("class", []))
            id_str = element.get("id", "") or ""
            combined = f"{class_str} {id_str}"

            if any(pattern.search(combined) for pattern in AD_COOKIE_PATTERNS):
                element.decompose()

    def _strip_dangerous_attributes(self, soup: BeautifulSoup) -> None:
        """Remove dangerous attributes from all remaining elements.

        Strips event handlers (onclick, onerror, etc.) and href/src
        attributes containing "javascript:" URLs.

        Args:
            soup: BeautifulSoup document to modify in-place.
        """
        for element in soup.find_all(True):
            if not isinstance(element, Tag):
                continue

            # Remove dangerous event handler attributes
            attrs_to_remove = []
            for attr_name in list(element.attrs.keys()):
                if attr_name.lower() in DANGEROUS_ATTRIBUTES:
                    attrs_to_remove.append(attr_name)

            for attr_name in attrs_to_remove:
                del element[attr_name]

            # Remove javascript: URLs from href and src
            for url_attr in ("href", "src"):
                value = element.get(url_attr, "")
                if isinstance(value, str) and re.match(
                    r"\s*javascript\s*:", value, re.IGNORECASE
                ):
                    del element[url_attr]

    # ─── Content Extraction ──────────────────────────────────────────────

    def _find_article_content(self, soup: BeautifulSoup) -> Tag | BeautifulSoup:
        """Locate the main article content container.

        Search priority:
            1. <article> tag
            2. <main> tag
            3. Element with role="main"
            4. Largest content block (div with most text)
            5. Fall back to entire document body or soup

        Args:
            soup: Sanitized BeautifulSoup document.

        Returns:
            Tag containing the article content, or the soup itself.
        """
        # Try <article>
        article = soup.find("article")
        if article and isinstance(article, Tag):
            return article

        # Try <main>
        main = soup.find("main")
        if main and isinstance(main, Tag):
            return main

        # Try role="main"
        main_role = soup.find(attrs={"role": "main"})
        if main_role and isinstance(main_role, Tag):
            return main_role

        # Try to find the largest content div
        body = soup.find("body")
        if body and isinstance(body, Tag):
            return self._find_largest_content_block(body)

        return soup

    def _find_largest_content_block(self, container: Tag) -> Tag:
        """Find the div/section with the most text content.

        Args:
            container: Parent element to search within.

        Returns:
            The child element with the most text, or the container itself.
        """
        candidates = container.find_all(["div", "section"], recursive=False)
        if not candidates:
            return container

        best = container
        best_length = 0

        for candidate in candidates:
            if isinstance(candidate, Tag):
                text_length = len(candidate.get_text(strip=True))
                if text_length > best_length:
                    best = candidate
                    best_length = text_length

        return best

    def _extract_title(
        self, soup: BeautifulSoup, article_root: Tag | BeautifulSoup
    ) -> str:
        """Extract the document title.

        Search priority:
            1. First <h1> within article content
            2. <title> tag in document head
            3. Empty string fallback

        Args:
            soup: Full document (for <title> fallback).
            article_root: Article content container.

        Returns:
            Extracted title string.
        """
        # Try h1 in article
        h1 = article_root.find("h1")
        if h1 and isinstance(h1, Tag):
            title_text = h1.get_text(strip=True)
            if title_text:
                return title_text

        # Fallback to <title> tag
        title_tag = soup.find("title")
        if title_tag and isinstance(title_tag, Tag):
            title_text = title_tag.get_text(strip=True)
            if title_text:
                return title_text

        return ""

    def _extract_abstract(self, article_root: Tag | BeautifulSoup) -> str:
        """Extract the abstract from the article content.

        Looks for text following an "Abstract" heading or within a section/div
        with class or id containing "abstract".

        Args:
            article_root: Article content container.

        Returns:
            Extracted abstract text, or empty string if not found.
        """
        # Look for element with class/id containing "abstract"
        abstract_el = article_root.find(
            attrs={"class": re.compile(r"\babstract\b", re.IGNORECASE)}
        )
        if abstract_el and isinstance(abstract_el, Tag):
            text = abstract_el.get_text(separator=" ", strip=True)
            # Strip leading "Abstract" label if present
            text = re.sub(r"^\s*Abstract\s*:?\s*", "", text, flags=re.IGNORECASE)
            if text:
                return text

        abstract_el = article_root.find(
            attrs={"id": re.compile(r"\babstract\b", re.IGNORECASE)}
        )
        if abstract_el and isinstance(abstract_el, Tag):
            text = abstract_el.get_text(separator=" ", strip=True)
            text = re.sub(r"^\s*Abstract\s*:?\s*", "", text, flags=re.IGNORECASE)
            if text:
                return text

        # Look for heading containing "Abstract" and grab following content
        for heading in article_root.find_all(re.compile(r"^h[1-6]$")):
            if isinstance(heading, Tag) and re.search(
                r"\babstract\b", heading.get_text(), re.IGNORECASE
            ):
                abstract_parts: list[str] = []
                for sibling in heading.next_siblings:
                    if isinstance(sibling, Tag):
                        # Stop at next heading
                        if sibling.name and re.match(r"^h[1-6]$", sibling.name):
                            break
                        abstract_parts.append(sibling.get_text(separator=" ", strip=True))
                text = " ".join(part for part in abstract_parts if part)
                if text:
                    return text

        return ""

    def _extract_body_sections(
        self, article_root: Tag | BeautifulSoup
    ) -> list[BodySection]:
        """Extract body sections from heading tags and their content.

        Scans for h2-h6 headings within the article content and collects
        following paragraphs/content until the next heading of equal or
        higher level.

        Args:
            article_root: Article content container.

        Returns:
            List of BodySection objects with heading and text.
        """
        sections: list[BodySection] = []
        headings = article_root.find_all(re.compile(r"^h[2-6]$"))

        if not headings:
            # No section headings found; collect all paragraph text as one section
            paragraphs = article_root.find_all("p")
            body_text = " ".join(
                p.get_text(separator=" ", strip=True)
                for p in paragraphs
                if isinstance(p, Tag) and p.get_text(strip=True)
            )
            if body_text:
                sections.append(BodySection(heading="", text=body_text))
            return sections

        for heading in headings:
            if not isinstance(heading, Tag):
                continue

            heading_text = heading.get_text(strip=True)

            # Skip headings that are "Abstract" or "References" — handled separately
            if re.match(
                r"^(abstract|references|bibliography)$",
                heading_text,
                re.IGNORECASE,
            ):
                continue

            heading_level = int(heading.name[1])
            content_parts: list[str] = []

            for sibling in heading.next_siblings:
                if isinstance(sibling, Tag):
                    # Stop at next heading of same or higher level
                    if sibling.name and re.match(r"^h[1-6]$", sibling.name):
                        sibling_level = int(sibling.name[1])
                        if sibling_level <= heading_level:
                            break
                    content_parts.append(
                        sibling.get_text(separator=" ", strip=True)
                    )

            section_text = " ".join(part for part in content_parts if part)
            if heading_text or section_text:
                sections.append(BodySection(heading=heading_text, text=section_text))

        return sections

    def _extract_references(self, article_root: Tag | BeautifulSoup) -> list[str]:
        """Extract reference/citation list from the article.

        Looks for a "References" or "Bibliography" section and extracts
        individual citation entries.

        Args:
            article_root: Article content container.

        Returns:
            List of citation strings.
        """
        references: list[str] = []

        # Look for a references section by class/id
        ref_section = article_root.find(
            attrs={"class": re.compile(r"\b(references|bibliography)\b", re.IGNORECASE)}
        )
        if not ref_section:
            ref_section = article_root.find(
                attrs={"id": re.compile(r"\b(references|bibliography)\b", re.IGNORECASE)}
            )

        # Try finding by heading
        if not ref_section:
            for heading in article_root.find_all(re.compile(r"^h[1-6]$")):
                if isinstance(heading, Tag) and re.search(
                    r"\b(references|bibliography)\b",
                    heading.get_text(),
                    re.IGNORECASE,
                ):
                    # Collect content after this heading
                    ref_section = heading
                    break

        if ref_section and isinstance(ref_section, Tag):
            # If it's a heading, grab sibling content
            if ref_section.name and re.match(r"^h[1-6]$", ref_section.name):
                for sibling in ref_section.next_siblings:
                    if isinstance(sibling, Tag):
                        if sibling.name and re.match(r"^h[1-6]$", sibling.name):
                            break
                        # Look for list items or paragraphs as individual refs
                        items = sibling.find_all(["li", "p"])
                        if items:
                            for item in items:
                                if isinstance(item, Tag):
                                    text = item.get_text(separator=" ", strip=True)
                                    if text:
                                        references.append(text)
                        else:
                            text = sibling.get_text(separator=" ", strip=True)
                            if text:
                                references.append(text)
            else:
                # It's a container element — look for list items
                items = ref_section.find_all(["li", "p"])
                if items:
                    for item in items:
                        if isinstance(item, Tag):
                            text = item.get_text(separator=" ", strip=True)
                            if text:
                                references.append(text)
                else:
                    text = ref_section.get_text(separator=" ", strip=True)
                    if text:
                        references.append(text)

        return references

    def _count_figures(self, article_root: Tag | BeautifulSoup) -> int:
        """Count figure elements in the article.

        Args:
            article_root: Article content container.

        Returns:
            Number of <figure> elements or <img> tags found.
        """
        figures = article_root.find_all("figure")
        if figures:
            return len(figures)
        # Fallback: count standalone images
        return len(article_root.find_all("img"))

    def _count_tables(self, article_root: Tag | BeautifulSoup) -> int:
        """Count table elements in the article.

        Args:
            article_root: Article content container.

        Returns:
            Number of <table> elements found.
        """
        return len(article_root.find_all("table"))
