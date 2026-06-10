"""PubMed / MEDLINE source adapter using NCBI E-utilities.

Queries the NCBI Entrez Programming Utilities (E-utilities) API via
eSearch (to find PMIDs) and eFetch (to retrieve article details).
Supports both authenticated (API key for higher rate limits) and
unauthenticated access modes.

E-utilities documentation: https://www.ncbi.nlm.nih.gov/books/NBK25501/

References:
    - Requirements 2.1, 2.4, 2.5, 2.8, 2.9, 12.1, 12.2, 12.3, 12.5
"""

from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from typing import Any

import httpx

from alcoabase.literature.adapters.base import AdapterMetadata, BaseSourceAdapter
from alcoabase.literature.exceptions import (
    AdapterAuthError,
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

# ─── Constants ────────────────────────────────────────────────────────────────

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EINFO_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi"

_ADAPTER_NAME = "pubmed"
_DEFAULT_TIMEOUT = 15.0


# ─── Publication type mapping ─────────────────────────────────────────────────

_PUBTYPE_MAP: dict[str, PublicationType] = {
    "journal article": PublicationType.JOURNAL_ARTICLE,
    "review": PublicationType.REVIEW,
    "preprint": PublicationType.PREPRINT,
    "congress": PublicationType.CONFERENCE_PAPER,
    "conference paper": PublicationType.CONFERENCE_PAPER,
    "meeting abstract": PublicationType.CONFERENCE_PAPER,
}


# ─── Adapter Implementation ──────────────────────────────────────────────────


class PubMedAdapter(BaseSourceAdapter):
    """PubMed / MEDLINE adapter querying NCBI E-utilities.

    Uses a two-step process:
    1. eSearch to find PMIDs matching the query
    2. eFetch to retrieve full article metadata for found PMIDs

    Supports authenticated mode (API key provides 10 req/s vs 3 req/s)
    and unauthenticated mode.

    Attributes:
        _proxy_url: Optional HTTP/HTTPS proxy URL for outbound requests.
        _default_timeout: Default per-request timeout in seconds.
    """

    def __init__(
        self,
        *,
        proxy_url: str | None = None,
        default_timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize PubMed adapter.

        Args:
            proxy_url: Optional proxy URL for outbound requests.
            default_timeout: Default request timeout in seconds.
        """
        self._proxy_url = proxy_url
        self._default_timeout = default_timeout

    def get_adapter_metadata(self) -> AdapterMetadata:
        """Return immutable metadata about this adapter.

        Returns:
            AdapterMetadata with PubMed-specific identifiers.
        """
        return AdapterMetadata(
            name=_ADAPTER_NAME,
            version="1.0.0",
            display_name="PubMed / MEDLINE",
            requires_api_key=False,
        )

    def get_capabilities(self) -> AdapterCapabilities:
        """Declare PubMed query capabilities.

        Returns:
            AdapterCapabilities indicating keyword, author, date_range,
            and publication_type support. DOI lookup not supported via
            E-utilities search.
        """
        return AdapterCapabilities(
            supports_keyword=True,
            supports_author=True,
            supports_date_range=True,
            supports_publication_type=True,
            supports_doi=False,
        )

    async def search(
        self,
        query: SearchQuery,
        api_key: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> list[LiteratureSearchResult]:
        """Execute a PubMed search via eSearch + eFetch.

        Args:
            query: Structured search query with terms and filters.
            api_key: NCBI API key for higher rate limits (optional).
            timeout: Per-request timeout in seconds.

        Returns:
            List of normalized LiteratureSearchResult objects.

        Raises:
            AdapterAuthError: On HTTP 401/403 from NCBI.
            AdapterTimeoutError: On request timeout.
            AdapterParseError: On unparseable XML response.
            AdapterConnectionError: On network failure.
        """
        # Step 1: eSearch to get PMIDs
        pmids = await self._esearch(query, api_key=api_key, timeout=timeout)
        if not pmids:
            return []

        # Step 2: eFetch to get article details
        articles_xml = await self._efetch(pmids, api_key=api_key, timeout=timeout)

        # Step 3: Parse and normalize results
        return self._parse_efetch_response(articles_xml, query_id=query.terms)

    async def get_metadata(self, external_id: str) -> dict[str, Any]:
        """Retrieve detailed metadata for a specific PMID.

        Args:
            external_id: PubMed ID (PMID) to look up.

        Returns:
            Dict of metadata fields from PubMed.
        """
        xml_content = await self._efetch(
            [external_id], api_key=None, timeout=self._default_timeout
        )
        results = self._parse_efetch_response(xml_content, query_id="metadata_lookup")
        if results:
            return results[0].model_dump()
        return {}

    async def health_check(self) -> float:
        """Check PubMed E-utilities availability via einfo endpoint.

        Returns:
            Response time in seconds.

        Raises:
            AdapterConnectionError: If NCBI is unreachable.
        """
        start = time.monotonic()
        try:
            async with self._get_client(timeout=self._default_timeout) as client:
                response = await client.get(EINFO_URL)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise AdapterConnectionError(
                f"Failed to connect to PubMed E-utilities: {exc}",
                source_adapter_name=_ADAPTER_NAME,
                target_url=EINFO_URL,
            ) from exc
        except httpx.TimeoutException as exc:
            raise AdapterConnectionError(
                f"Timeout connecting to PubMed E-utilities: {exc}",
                source_adapter_name=_ADAPTER_NAME,
                target_url=EINFO_URL,
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise AdapterConnectionError(
                f"PubMed E-utilities returned HTTP {exc.response.status_code}",
                source_adapter_name=_ADAPTER_NAME,
                target_url=EINFO_URL,
            ) from exc

        return time.monotonic() - start

    # ─── Private Methods ──────────────────────────────────────────────────

    def _get_client(self, timeout: float) -> httpx.AsyncClient:
        """Create an httpx.AsyncClient with proxy and timeout configuration.

        Args:
            timeout: Request timeout in seconds.

        Returns:
            Configured httpx.AsyncClient context manager.
        """
        return httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            proxy=self._proxy_url,
        )

    def _build_esearch_params(
        self,
        query: SearchQuery,
        api_key: str | None,
    ) -> dict[str, str]:
        """Build E-utilities eSearch query parameters from SearchQuery.

        Translates SearchQuery fields to NCBI E-utilities parameters:
        - terms → term (with field qualifiers for author, publication type)
        - date_from → mindate
        - date_to → maxdate
        - page/page_size → retstart/retmax

        Args:
            query: Structured search query.
            api_key: Optional NCBI API key.

        Returns:
            Dict of query parameters for eSearch.
        """
        # Build the term parameter
        term_parts: list[str] = [query.terms]

        # Add publication type filters if specified
        if query.publication_types:
            pub_type_terms = []
            for pt in query.publication_types:
                mesh_term = self._publication_type_to_mesh(pt)
                if mesh_term:
                    pub_type_terms.append(f"{mesh_term}[pt]")
            if pub_type_terms:
                term_parts.append(f"({' OR '.join(pub_type_terms)})")

        params: dict[str, str] = {
            "db": "pubmed",
            "term": " AND ".join(term_parts),
            "retmode": "xml",
            "retmax": str(query.page_size),
            "retstart": str((query.page - 1) * query.page_size),
        }

        # Date range filters
        if query.date_from:
            params["mindate"] = query.date_from.strftime("%Y/%m/%d")
            params["datetype"] = "pdat"
        if query.date_to:
            params["maxdate"] = query.date_to.strftime("%Y/%m/%d")
            params["datetype"] = "pdat"

        # API key for authenticated mode
        if api_key:
            params["api_key"] = api_key

        return params

    @staticmethod
    def _publication_type_to_mesh(pub_type: PublicationType) -> str | None:
        """Map a normalized PublicationType to PubMed MeSH publication type.

        Args:
            pub_type: Normalized publication type.

        Returns:
            PubMed publication type filter string, or None if no mapping.
        """
        mapping: dict[PublicationType, str] = {
            PublicationType.JOURNAL_ARTICLE: "Journal Article",
            PublicationType.REVIEW: "Review",
            PublicationType.CONFERENCE_PAPER: "Congress",
        }
        return mapping.get(pub_type)

    async def _esearch(
        self,
        query: SearchQuery,
        *,
        api_key: str | None,
        timeout: float,
    ) -> list[str]:
        """Execute eSearch to find PMIDs matching the query.

        Args:
            query: Structured search query.
            api_key: Optional NCBI API key.
            timeout: Request timeout in seconds.

        Returns:
            List of PMID strings.

        Raises:
            AdapterAuthError: On HTTP 401/403.
            AdapterTimeoutError: On request timeout.
            AdapterParseError: On unparseable response.
            AdapterConnectionError: On network failure.
        """
        params = self._build_esearch_params(query, api_key)

        try:
            async with self._get_client(timeout=timeout) as client:
                response = await client.get(ESEARCH_URL, params=params)
        except httpx.TimeoutException as exc:
            raise AdapterTimeoutError(
                f"PubMed eSearch request timed out after {timeout}s",
                source_adapter_name=_ADAPTER_NAME,
                timeout_seconds=timeout,
            ) from exc
        except httpx.ConnectError as exc:
            raise AdapterConnectionError(
                f"Failed to connect to PubMed eSearch: {exc}",
                source_adapter_name=_ADAPTER_NAME,
                target_url=ESEARCH_URL,
            ) from exc

        self._check_http_status(response)

        # Parse eSearch XML response
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise AdapterParseError(
                f"Failed to parse PubMed eSearch XML response: {exc}",
                source_adapter_name=_ADAPTER_NAME,
                content_type=response.headers.get("content-type"),
                response_size_bytes=len(response.content),
            ) from exc

        id_list = root.find("IdList")
        if id_list is None:
            return []

        return [id_elem.text for id_elem in id_list.findall("Id") if id_elem.text]

    async def _efetch(
        self,
        pmids: list[str],
        *,
        api_key: str | None,
        timeout: float,
    ) -> str:
        """Execute eFetch to retrieve article details for given PMIDs.

        Args:
            pmids: List of PubMed IDs to fetch.
            api_key: Optional NCBI API key.
            timeout: Request timeout in seconds.

        Returns:
            Raw XML response string.

        Raises:
            AdapterAuthError: On HTTP 401/403.
            AdapterTimeoutError: On request timeout.
            AdapterParseError: On unparseable response.
            AdapterConnectionError: On network failure.
        """
        params: dict[str, str] = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }

        if api_key:
            params["api_key"] = api_key

        try:
            async with self._get_client(timeout=timeout) as client:
                response = await client.get(EFETCH_URL, params=params)
        except httpx.TimeoutException as exc:
            raise AdapterTimeoutError(
                f"PubMed eFetch request timed out after {timeout}s",
                source_adapter_name=_ADAPTER_NAME,
                timeout_seconds=timeout,
            ) from exc
        except httpx.ConnectError as exc:
            raise AdapterConnectionError(
                f"Failed to connect to PubMed eFetch: {exc}",
                source_adapter_name=_ADAPTER_NAME,
                target_url=EFETCH_URL,
            ) from exc

        self._check_http_status(response)

        return response.text

    def _check_http_status(self, response: httpx.Response) -> None:
        """Check HTTP response status and raise appropriate errors.

        Args:
            response: The httpx response to check.

        Raises:
            AdapterAuthError: On HTTP 401 or 403.
            AdapterParseError: On other HTTP errors (treated as unexpected).
        """
        if response.status_code in (401, 403):
            raise AdapterAuthError(
                f"PubMed returned HTTP {response.status_code}: "
                "invalid or expired API key",
                source_adapter_name=_ADAPTER_NAME,
                status_code=response.status_code,
            )

        if response.status_code >= 400:
            raise AdapterParseError(
                f"PubMed returned unexpected HTTP {response.status_code}",
                source_adapter_name=_ADAPTER_NAME,
                content_type=response.headers.get("content-type"),
                response_size_bytes=len(response.content),
            )

    def _parse_efetch_response(
        self,
        xml_content: str,
        query_id: str,
    ) -> list[LiteratureSearchResult]:
        """Parse eFetch XML response into normalized LiteratureSearchResult list.

        Skips articles missing required fields (title, PMID).
        Logs warnings for excluded articles and debug messages for
        discarded unmapped fields.

        Args:
            xml_content: Raw XML string from eFetch.
            query_id: Query identifier for provenance tracking.

        Returns:
            List of normalized results.

        Raises:
            AdapterParseError: If the XML cannot be parsed at all.
        """
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            raise AdapterParseError(
                f"Failed to parse PubMed eFetch XML: {exc}",
                source_adapter_name=_ADAPTER_NAME,
                content_type="text/xml",
                response_size_bytes=len(xml_content.encode()),
            ) from exc

        results: list[LiteratureSearchResult] = []
        retrieval_timestamp = datetime.now(UTC)

        for article_elem in root.iter("PubmedArticle"):
            result = self._parse_single_article(
                article_elem, query_id, retrieval_timestamp
            )
            if result is not None:
                results.append(result)

        return results

    def _parse_single_article(
        self,
        article_elem: ET.Element,
        query_id: str,
        retrieval_timestamp: datetime,
    ) -> LiteratureSearchResult | None:
        """Parse a single PubmedArticle XML element into a search result.

        Args:
            article_elem: XML element for a single PubMed article.
            query_id: Query identifier for provenance.
            retrieval_timestamp: When the data was retrieved.

        Returns:
            LiteratureSearchResult or None if required fields are missing.
        """
        # Extract PMID (required field: external_id)
        pmid_elem = article_elem.find(".//PMID")
        pmid = pmid_elem.text if pmid_elem is not None and pmid_elem.text else None

        # Extract title (required field)
        title_elem = article_elem.find(".//ArticleTitle")
        title = self._get_element_text(title_elem)

        # Validate required fields
        if not pmid:
            logger.warning(
                "PubMed article missing PMID (title=%s), excluding from results",
                title or "<unknown>",
            )
            return None

        if not title:
            logger.warning(
                "PubMed article PMID=%s missing title, excluding from results",
                pmid,
            )
            return None

        # Truncate title to schema maximum
        title = title[:2000]

        # Extract authors
        authors = self._extract_authors(article_elem)

        # Extract abstract
        abstract = self._extract_abstract(article_elem)

        # Extract DOI
        doi = self._extract_doi(article_elem)

        # Extract publication date
        pub_date, date_precision = self._extract_publication_date(article_elem)

        # Extract journal name
        journal = self._extract_journal(article_elem)

        # Extract publication type
        publication_type = self._extract_publication_type(article_elem)

        # Build URL
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

        return LiteratureSearchResult(
            title=title,
            authors=authors[:500],  # Schema max 500 authors
            abstract=abstract[:50000],  # Schema max 50000 chars
            doi=doi,
            publication_date=pub_date,
            source_id=_ADAPTER_NAME,
            external_id=pmid,
            journal_or_venue=journal,
            publication_type=publication_type,
            url=url,
            date_precision=date_precision,
            retrieval_timestamp=retrieval_timestamp,
            query_id=query_id,
        )

    @staticmethod
    def _get_element_text(elem: ET.Element | None) -> str:
        """Extract all text content from an XML element, including children.

        PubMed titles and abstracts may contain inline markup (e.g., <i>, <b>).
        This method concatenates all text.

        Args:
            elem: XML element or None.

        Returns:
            Concatenated text content, or empty string if None.
        """
        if elem is None:
            return ""
        # itertext() yields all text within the element and its children
        return "".join(elem.itertext()).strip()

    @staticmethod
    def _extract_authors(article_elem: ET.Element) -> list[str]:
        """Extract author names from a PubmedArticle element.

        Combines LastName + ForeName. Falls back to CollectiveName
        for group authors.

        Args:
            article_elem: PubmedArticle XML element.

        Returns:
            List of author name strings.
        """
        authors: list[str] = []
        author_list = article_elem.find(".//AuthorList")
        if author_list is None:
            return authors

        for author_elem in author_list.findall("Author"):
            last_name = author_elem.findtext("LastName", "")
            fore_name = author_elem.findtext("ForeName", "")

            if last_name:
                name = f"{last_name} {fore_name}".strip() if fore_name else last_name
                authors.append(name)
            else:
                # Try CollectiveName for group authors
                collective = author_elem.findtext("CollectiveName", "")
                if collective:
                    authors.append(collective)

        return authors

    @staticmethod
    def _extract_abstract(article_elem: ET.Element) -> str:
        """Extract abstract text from a PubmedArticle element.

        Handles structured abstracts (multiple AbstractText elements with
        labels) by concatenating them with labels.

        Args:
            article_elem: PubmedArticle XML element.

        Returns:
            Abstract text string (empty if no abstract).
        """
        abstract_elem = article_elem.find(".//Abstract")
        if abstract_elem is None:
            return ""

        parts: list[str] = []
        for text_elem in abstract_elem.findall("AbstractText"):
            label = text_elem.get("Label")
            text = "".join(text_elem.itertext()).strip()
            if text:
                if label:
                    parts.append(f"{label}: {text}")
                else:
                    parts.append(text)

        return "\n".join(parts)

    @staticmethod
    def _extract_doi(article_elem: ET.Element) -> str | None:
        """Extract DOI from article ID list.

        Args:
            article_elem: PubmedArticle XML element.

        Returns:
            DOI string or None if not found.
        """
        # Check ArticleIdList first (most common location)
        for article_id in article_elem.iter("ArticleId"):
            if article_id.get("IdType") == "doi" and article_id.text:
                return article_id.text.strip()

        # Also check ELocationID
        for elocation in article_elem.iter("ELocationID"):
            if elocation.get("EIdType") == "doi" and elocation.text:
                return elocation.text.strip()

        return None

    @staticmethod
    def _extract_publication_date(
        article_elem: ET.Element,
    ) -> tuple[date, DatePrecision]:
        """Extract and normalize publication date from a PubmedArticle.

        Handles multiple date formats:
        - Full date: year + month + day → DatePrecision.DAY
        - Year + month only → first day of month, DatePrecision.MONTH
        - Year only → January 1st, DatePrecision.YEAR

        Tries PubDate first, then ArticleDate, then MedlineDate.

        Args:
            article_elem: PubmedArticle XML element.

        Returns:
            Tuple of (normalized date, precision).
        """
        # Try PubDate (most common)
        pub_date_elem = article_elem.find(".//PubDate")
        if pub_date_elem is not None:
            result = PubMedAdapter._parse_pubmed_date_element(pub_date_elem)
            if result is not None:
                return result

        # Try ArticleDate
        article_date_elem = article_elem.find(".//ArticleDate")
        if article_date_elem is not None:
            result = PubMedAdapter._parse_pubmed_date_element(article_date_elem)
            if result is not None:
                return result

        # Try MedlineDate (free text)
        medline_date = article_elem.findtext(".//MedlineDate")
        if medline_date:
            result = PubMedAdapter._parse_medline_date(medline_date)
            if result is not None:
                return result

        # Fallback: use today's date with YEAR precision
        return date.today(), DatePrecision.YEAR

    @staticmethod
    def _parse_pubmed_date_element(
        date_elem: ET.Element,
    ) -> tuple[date, DatePrecision] | None:
        """Parse a PubMed date element (Year/Month/Day children).

        Args:
            date_elem: XML element with Year, Month, Day children.

        Returns:
            Tuple of (date, precision) or None if no year found.
        """
        year_text = date_elem.findtext("Year")
        if not year_text:
            return None

        try:
            year = int(year_text)
        except ValueError:
            return None

        month_text = date_elem.findtext("Month")
        day_text = date_elem.findtext("Day")

        month = PubMedAdapter._parse_month(month_text)
        if month is None:
            return date(year, 1, 1), DatePrecision.YEAR

        if day_text:
            try:
                day = int(day_text)
                return date(year, month, day), DatePrecision.DAY
            except (ValueError, OverflowError):
                return date(year, month, 1), DatePrecision.MONTH

        return date(year, month, 1), DatePrecision.MONTH

    @staticmethod
    def _parse_month(month_text: str | None) -> int | None:
        """Parse a month value (numeric or abbreviated name).

        Args:
            month_text: Month string (e.g., "3", "Mar", "March").

        Returns:
            Month number (1-12) or None.
        """
        if not month_text:
            return None

        # Try numeric first
        try:
            month = int(month_text)
            if 1 <= month <= 12:
                return month
            return None
        except ValueError:
            pass

        # Try abbreviated month names
        month_map: dict[str, int] = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4,
            "may": 5, "jun": 6, "jul": 7, "aug": 8,
            "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        return month_map.get(month_text[:3].lower())

    @staticmethod
    def _parse_medline_date(medline_date: str) -> tuple[date, DatePrecision] | None:
        """Parse a MedlineDate free-text string (e.g., "2023 Mar-Apr").

        Args:
            medline_date: Free-text date string.

        Returns:
            Tuple of (date, precision) or None if unparseable.
        """
        parts = medline_date.strip().split()
        if not parts:
            return None

        try:
            year = int(parts[0])
        except ValueError:
            return None

        if len(parts) > 1:
            # Try to parse month from second part (may be "Mar-Apr" → take "Mar")
            month_str = parts[1].split("-")[0]
            month = PubMedAdapter._parse_month(month_str)
            if month:
                return date(year, month, 1), DatePrecision.MONTH

        return date(year, 1, 1), DatePrecision.YEAR

    @staticmethod
    def _extract_journal(article_elem: ET.Element) -> str:
        """Extract journal name from a PubmedArticle element.

        Prefers Title over ISOAbbreviation.

        Args:
            article_elem: PubmedArticle XML element.

        Returns:
            Journal name or empty string.
        """
        title = article_elem.findtext(".//Journal/Title")
        if title:
            return title.strip()

        iso_abbrev = article_elem.findtext(".//Journal/ISOAbbreviation")
        if iso_abbrev:
            return iso_abbrev.strip()

        return ""

    @staticmethod
    def _extract_publication_type(article_elem: ET.Element) -> PublicationType:
        """Extract and normalize publication type from a PubmedArticle.

        Maps PubMed's publication type list to normalized PublicationType.
        Uses the first recognized type.

        Args:
            article_elem: PubmedArticle XML element.

        Returns:
            Normalized PublicationType (defaults to OTHER).
        """
        pub_type_list = article_elem.find(".//PublicationTypeList")
        if pub_type_list is None:
            return PublicationType.OTHER

        for pub_type_elem in pub_type_list.findall("PublicationType"):
            if pub_type_elem.text:
                normalized = pub_type_elem.text.strip().lower()
                mapped = _PUBTYPE_MAP.get(normalized)
                if mapped is not None:
                    return mapped

        return PublicationType.OTHER
