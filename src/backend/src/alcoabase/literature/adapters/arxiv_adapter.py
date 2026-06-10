"""arXiv source adapter for the Literature Search Engine.

Queries the arXiv API (http://export.arxiv.org/api/query) and normalizes
Atom XML responses into LiteratureSearchResult objects. arXiv does not
require API keys — all access is unauthenticated.

References:
    - Requirements 2.3, 2.4, 2.7, 2.8, 2.9, 12.1, 12.2, 12.3, 12.5
"""

from __future__ import annotations

import logging
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from typing import Any

import httpx

from alcoabase.literature.adapters.base import AdapterMetadata, BaseSourceAdapter
from alcoabase.literature.exceptions import (
    AdapterConnectionError,
    AdapterParseError,
    AdapterTimeoutError,
)
from alcoabase.literature.schemas.search import (
    AdapterCapabilities,
    DatePrecision,
    LiteratureSearchResult,
    PublicationType,
    SearchQuery,
)

logger = logging.getLogger(__name__)

# arXiv API base URL
ARXIV_API_URL = "http://export.arxiv.org/api/query"

# Atom XML namespaces used in arXiv responses
ATOM_NS = "http://www.w3.org/2005/Atom"
OPENSEARCH_NS = "http://a9.com/-/spec/opensearch/1.1/"

# Namespace map for ElementTree xpath queries
NS = {
    "atom": ATOM_NS,
    "opensearch": OPENSEARCH_NS,
}


class ArXivAdapter(BaseSourceAdapter):
    """Source adapter for querying the arXiv preprint repository.

    arXiv operates in unauthenticated mode only — no API key is required.
    The adapter translates SearchQuery objects into arXiv query format,
    executes HTTP requests against the arXiv API, and parses Atom XML
    responses into normalized LiteratureSearchResult objects.

    Attributes:
        _http_client: Optional pre-configured httpx.AsyncClient for testing.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        """Initialize the arXiv adapter.

        Args:
            http_client: Optional httpx.AsyncClient instance. If not provided,
                a new client is created per request.
        """
        self._http_client = http_client

    async def search(
        self,
        query: SearchQuery,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> list[LiteratureSearchResult]:
        """Execute a search against the arXiv API.

        Translates the SearchQuery into arXiv query format, sends the request,
        and parses the Atom XML response into normalized results.

        Args:
            query: Structured search query with terms and filters.
            api_key: Ignored — arXiv does not require authentication.
            timeout: Per-request timeout in seconds (default 15s).

        Returns:
            List of normalized LiteratureSearchResult objects.

        Raises:
            AdapterTimeoutError: If the request exceeds the timeout.
            AdapterConnectionError: If the arXiv API is unreachable.
            AdapterParseError: If the response cannot be parsed as Atom XML.
        """
        search_query = self._build_query_string(query)
        start_index = (query.page - 1) * query.page_size

        params = {
            "search_query": search_query,
            "start": str(start_index),
            "max_results": str(query.page_size),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        query_id = str(uuid.uuid4())
        response = await self._execute_request(params, timeout)
        return self._parse_response(response, query_id)

    async def get_metadata(self, external_id: str) -> dict[str, Any]:
        """Retrieve detailed metadata for a specific arXiv paper.

        Args:
            external_id: arXiv paper ID (e.g., "2301.12345").

        Returns:
            Dict of metadata fields from the arXiv API.

        Raises:
            AdapterTimeoutError: If the request exceeds the timeout.
            AdapterConnectionError: If the arXiv API is unreachable.
            AdapterParseError: If the response cannot be parsed.
        """
        params = {
            "id_list": external_id,
            "max_results": "1",
        }

        response = await self._execute_request(params, timeout=15.0)
        results = self._parse_response(response, query_id=str(uuid.uuid4()))

        if results:
            result = results[0]
            return {
                "title": result.title,
                "authors": result.authors,
                "abstract": result.abstract,
                "publication_date": result.publication_date.isoformat(),
                "external_id": result.external_id,
                "url": result.url,
                "doi": result.doi,
            }
        return {}

    async def health_check(self) -> float:
        """Perform a lightweight health check against the arXiv API.

        Sends a minimal query and measures the response time.

        Returns:
            Response time in seconds.

        Raises:
            AdapterConnectionError: If the arXiv API is unreachable.
        """
        params = {
            "search_query": "all:test",
            "start": "0",
            "max_results": "1",
        }

        start_time = time.monotonic()
        try:
            await self._execute_request(params, timeout=15.0)
        except AdapterTimeoutError:
            raise AdapterConnectionError(
                "arXiv API health check timed out",
                source_adapter_name="arxiv",
                target_url=ARXIV_API_URL,
            )
        elapsed = time.monotonic() - start_time
        return elapsed

    def get_capabilities(self) -> AdapterCapabilities:
        """Declare the query capabilities supported by the arXiv adapter.

        Returns:
            AdapterCapabilities indicating support for keyword, author,
            and date_range queries.
        """
        return AdapterCapabilities(
            supports_keyword=True,
            supports_author=True,
            supports_date_range=True,
            supports_publication_type=False,
            supports_doi=False,
        )

    def get_adapter_metadata(self) -> AdapterMetadata:
        """Return immutable metadata about the arXiv adapter.

        Returns:
            AdapterMetadata with name, version, display name, and key requirement.
        """
        return AdapterMetadata(
            name="arxiv",
            version="1.0.0",
            display_name="arXiv",
            requires_api_key=False,
        )

    # ─── Private Methods ──────────────────────────────────────────────────

    def _build_query_string(self, query: SearchQuery) -> str:
        """Translate a SearchQuery into arXiv query syntax.

        arXiv query format uses prefixes like all:, au:, ti: for field-specific
        searches. Multiple terms are combined with AND.

        Args:
            query: The search query to translate.

        Returns:
            arXiv-formatted query string.
        """
        parts: list[str] = []

        # Main search terms use the all: prefix for broad matching
        if query.terms:
            parts.append(f"all:{query.terms}")

        # Author filter uses au: prefix (if present on the query)
        author = getattr(query, "author", None)
        if author:
            parts.append(f"au:{author}")

        # Combine with AND
        query_string = " AND ".join(parts) if parts else "all:*"

        return query_string

    async def _execute_request(
        self,
        params: dict[str, str],
        timeout: float,
    ) -> str:
        """Execute an HTTP GET request against the arXiv API.

        Args:
            params: Query parameters for the request.
            timeout: Request timeout in seconds.

        Returns:
            Raw XML response body as string.

        Raises:
            AdapterTimeoutError: If the request exceeds the timeout.
            AdapterConnectionError: If the network connection fails.
        """
        try:
            if self._http_client:
                response = await self._http_client.get(
                    ARXIV_API_URL,
                    params=params,
                    timeout=timeout,
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        ARXIV_API_URL,
                        params=params,
                        timeout=timeout,
                    )

            response.raise_for_status()
            return response.text

        except httpx.TimeoutException as e:
            raise AdapterTimeoutError(
                f"arXiv API request timed out after {timeout}s",
                source_adapter_name="arxiv",
                timeout_seconds=timeout,
            ) from e
        except httpx.ConnectError as e:
            raise AdapterConnectionError(
                "Failed to connect to arXiv API",
                source_adapter_name="arxiv",
                target_url=ARXIV_API_URL,
            ) from e
        except httpx.HTTPStatusError as e:
            raise AdapterConnectionError(
                f"arXiv API returned HTTP {e.response.status_code}",
                source_adapter_name="arxiv",
                target_url=ARXIV_API_URL,
            ) from e
        except httpx.HTTPError as e:
            raise AdapterConnectionError(
                f"HTTP error communicating with arXiv API: {e}",
                source_adapter_name="arxiv",
                target_url=ARXIV_API_URL,
            ) from e

    def _parse_response(
        self,
        xml_text: str,
        query_id: str,
    ) -> list[LiteratureSearchResult]:
        """Parse an arXiv Atom XML response into normalized results.

        Handles the Atom namespace and extracts title, authors, abstract,
        publication date, arXiv ID, and links from each entry.

        Args:
            xml_text: Raw Atom XML response body.
            query_id: Unique identifier for the originating search query.

        Returns:
            List of normalized LiteratureSearchResult objects.

        Raises:
            AdapterParseError: If the XML cannot be parsed.
        """
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            raise AdapterParseError(
                "Failed to parse arXiv Atom XML response",
                source_adapter_name="arxiv",
                content_type="application/atom+xml",
                response_size_bytes=len(xml_text.encode("utf-8")),
            ) from e

        results: list[LiteratureSearchResult] = []
        retrieval_timestamp = datetime.now(UTC)

        entries = root.findall(f"{{{ATOM_NS}}}entry")

        for entry in entries:
            result = self._parse_entry(entry, query_id, retrieval_timestamp)
            if result is not None:
                results.append(result)

        return results

    def _parse_entry(
        self,
        entry: ET.Element,
        query_id: str,
        retrieval_timestamp: datetime,
    ) -> LiteratureSearchResult | None:
        """Parse a single Atom entry into a LiteratureSearchResult.

        Skips entries missing required fields (title and external_id).

        Args:
            entry: XML Element representing an arXiv entry.
            query_id: Unique identifier for the search query.
            retrieval_timestamp: When this result was fetched.

        Returns:
            A normalized LiteratureSearchResult, or None if required fields
            are missing.
        """
        # Extract title (required)
        title_elem = entry.find(f"{{{ATOM_NS}}}title")
        title = self._clean_text(title_elem.text) if title_elem is not None and title_elem.text else None

        # Extract arXiv ID from the <id> element (required)
        id_elem = entry.find(f"{{{ATOM_NS}}}id")
        raw_id = id_elem.text.strip() if id_elem is not None and id_elem.text else None

        # Validate required fields
        if not title or not raw_id:
            missing = []
            if not title:
                missing.append("title")
            if not raw_id:
                missing.append("external_id")
            logger.warning(
                "arXiv result missing required fields: %s (partial_id=%s, partial_title=%s)",
                missing,
                raw_id,
                title[:50] if title else None,
            )
            return None

        # Extract arXiv ID from the full URL (e.g., http://arxiv.org/abs/2301.12345v1)
        external_id = self._extract_arxiv_id(raw_id)

        # Extract authors
        authors = self._extract_authors(entry)

        # Extract abstract/summary
        summary_elem = entry.find(f"{{{ATOM_NS}}}summary")
        abstract = self._clean_text(summary_elem.text) if summary_elem is not None and summary_elem.text else ""

        # Extract publication date
        published_elem = entry.find(f"{{{ATOM_NS}}}published")
        publication_date, date_precision = self._parse_date(
            published_elem.text.strip() if published_elem is not None and published_elem.text else None
        )

        # Extract DOI from arxiv:doi element (if present)
        doi = self._extract_doi(entry)

        # Extract URL (prefer abstract link)
        url = self._extract_url(entry, raw_id)

        # Extract journal reference (if present)
        journal_or_venue = self._extract_journal_ref(entry)

        # Truncate fields to schema limits
        title = title[:2000]
        abstract = abstract[:50000]
        authors = authors[:500]

        return LiteratureSearchResult(
            title=title,
            authors=authors,
            abstract=abstract,
            doi=doi,
            publication_date=publication_date,
            source_id="arxiv",
            external_id=external_id,
            journal_or_venue=journal_or_venue,
            publication_type=PublicationType.PREPRINT,
            url=url,
            date_precision=date_precision,
            retrieval_timestamp=retrieval_timestamp,
            query_id=query_id,
        )

    def _extract_authors(self, entry: ET.Element) -> list[str]:
        """Extract author names from an Atom entry.

        Args:
            entry: XML Element containing author elements.

        Returns:
            List of author name strings.
        """
        authors: list[str] = []
        for author_elem in entry.findall(f"{{{ATOM_NS}}}author"):
            name_elem = author_elem.find(f"{{{ATOM_NS}}}name")
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())
        return authors

    def _extract_arxiv_id(self, raw_id: str) -> str:
        """Extract the arXiv paper ID from a full URL or raw ID string.

        arXiv IDs come in the form:
        - http://arxiv.org/abs/2301.12345v1
        - 2301.12345v1
        - 2301.12345

        Args:
            raw_id: The raw ID string from the XML response.

        Returns:
            Clean arXiv ID (e.g., "2301.12345v1").
        """
        # Handle full URL format
        if "/abs/" in raw_id:
            return raw_id.split("/abs/")[-1].strip()
        # Handle other URL patterns
        if "arxiv.org/" in raw_id:
            return raw_id.split("arxiv.org/")[-1].strip()
        return raw_id.strip()

    def _extract_doi(self, entry: ET.Element) -> str | None:
        """Extract DOI from an arXiv entry if available.

        arXiv uses the arxiv namespace for DOI: <arxiv:doi>.

        Args:
            entry: XML Element representing an arXiv entry.

        Returns:
            DOI string or None if not present.
        """
        # Try arxiv:doi element
        arxiv_ns = "http://arxiv.org/schemas/atom"
        doi_elem = entry.find(f"{{{arxiv_ns}}}doi")
        if doi_elem is not None and doi_elem.text:
            return doi_elem.text.strip()
        return None

    def _extract_url(self, entry: ET.Element, fallback_id: str) -> str:
        """Extract the best URL for an arXiv paper.

        Prefers the abstract page link; falls back to the raw ID if it's a URL.

        Args:
            entry: XML Element representing an arXiv entry.
            fallback_id: The raw <id> text as fallback.

        Returns:
            URL string for the paper.
        """
        # Look for link with rel="alternate" (abstract page)
        for link_elem in entry.findall(f"{{{ATOM_NS}}}link"):
            rel = link_elem.get("rel", "")
            href = link_elem.get("href", "")
            if rel == "alternate" and href:
                return href

        # Fall back to the <id> element (which is typically the abstract URL)
        if fallback_id.startswith("http"):
            return fallback_id

        return f"https://arxiv.org/abs/{fallback_id}"

    def _extract_journal_ref(self, entry: ET.Element) -> str:
        """Extract journal reference from an arXiv entry if available.

        Args:
            entry: XML Element representing an arXiv entry.

        Returns:
            Journal reference string, or empty string if not present.
        """
        arxiv_ns = "http://arxiv.org/schemas/atom"
        journal_elem = entry.find(f"{{{arxiv_ns}}}journal_ref")
        if journal_elem is not None and journal_elem.text:
            return journal_elem.text.strip()
        return ""

    def _parse_date(
        self, date_str: str | None
    ) -> tuple[date, DatePrecision]:
        """Parse an arXiv publication date string.

        arXiv dates are full ISO 8601 datetime strings (e.g., "2023-01-15T12:00:00Z"),
        so they always have day precision. Handles edge cases where partial dates
        may appear.

        Args:
            date_str: ISO 8601 date string from the arXiv response.

        Returns:
            Tuple of (normalized date, date precision).
        """
        if not date_str:
            # Default to today if no date is provided
            return date.today(), DatePrecision.DAY

        date_str = date_str.strip()

        # Full ISO 8601 datetime (most common arXiv format: 2023-01-15T12:00:00Z)
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.date(), DatePrecision.DAY
        except ValueError:
            pass

        # Year-month format (e.g., "2023-03")
        if len(date_str) == 7 and date_str[4] == "-":
            try:
                year = int(date_str[:4])
                month = int(date_str[5:7])
                return date(year, month, 1), DatePrecision.MONTH
            except (ValueError, IndexError):
                pass

        # Year-only format (e.g., "2023")
        if len(date_str) == 4:
            try:
                year = int(date_str)
                return date(year, 1, 1), DatePrecision.YEAR
            except ValueError:
                pass

        # Full date without time (e.g., "2023-01-15")
        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
            try:
                return date.fromisoformat(date_str), DatePrecision.DAY
            except ValueError:
                pass

        # If all parsing fails, default to today
        logger.warning("Could not parse arXiv date: %s, defaulting to today", date_str)
        return date.today(), DatePrecision.DAY

    @staticmethod
    def _clean_text(text: str | None) -> str:
        """Clean whitespace from text extracted from XML.

        arXiv entries often have excessive whitespace and newlines in titles
        and abstracts.

        Args:
            text: Raw text from XML element.

        Returns:
            Cleaned text with normalized whitespace.
        """
        if not text:
            return ""
        # Collapse all whitespace (including newlines) into single spaces
        return " ".join(text.split())
