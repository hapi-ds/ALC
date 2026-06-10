"""Crossref REST API adapter for literature search.

Queries the Crossref /works endpoint to search scholarly metadata.
Supports authenticated (Crossref Plus token) and unauthenticated
(polite pool with mailto) access modes.

References:
    - Requirements 2.2, 2.4, 2.6, 2.8, 2.9, 12.1, 12.2, 12.3, 12.5
"""

from __future__ import annotations

import logging
import time
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

CROSSREF_BASE_URL = "https://api.crossref.org"


class CrossrefAdapter(BaseSourceAdapter):
    """Adapter for the Crossref REST API (/works endpoint).

    Supports both authenticated (Crossref Plus token) and unauthenticated
    (polite pool with mailto contact email) access modes.

    Args:
        contact_email: Email for polite pool identification (used in
            User-Agent header when no API key is provided).
        proxy_url: Optional HTTP/HTTPS proxy URL for outbound requests.
    """

    def __init__(
        self,
        contact_email: str | None = None,
        proxy_url: str | None = None,
    ) -> None:
        """Initialize the Crossref adapter.

        Args:
            contact_email: Contact email for polite pool (unauthenticated mode).
            proxy_url: Optional proxy URL for outbound requests.
        """
        self._contact_email = contact_email
        self._proxy_url = proxy_url

    async def search(
        self,
        query: SearchQuery,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> list[LiteratureSearchResult]:
        """Execute a search against the Crossref /works endpoint.

        Args:
            query: Structured search query with terms and filters.
            api_key: Crossref Plus API token (None for polite pool).
            timeout: Per-request timeout in seconds.

        Returns:
            List of normalized search results.

        Raises:
            AdapterAuthError: On HTTP 401/403 from Crossref.
            AdapterTimeoutError: On request timeout.
            AdapterParseError: On unparseable response.
            AdapterConnectionError: On network failure.
        """
        params = self._build_query_params(query)
        headers = self._build_headers(api_key)

        try:
            async with httpx.AsyncClient(
                proxy=self._proxy_url,
                timeout=timeout,
            ) as client:
                response = await client.get(
                    f"{CROSSREF_BASE_URL}/works",
                    params=params,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise AdapterTimeoutError(
                f"Crossref request timed out after {timeout}s",
                source_adapter_name="crossref",
                timeout_seconds=timeout,
            ) from exc
        except httpx.ConnectError as exc:
            raise AdapterConnectionError(
                f"Failed to connect to Crossref API: {exc}",
                source_adapter_name="crossref",
                target_url=f"{CROSSREF_BASE_URL}/works",
            ) from exc

        if response.status_code in (401, 403):
            raise AdapterAuthError(
                f"Crossref authentication failed (HTTP {response.status_code})",
                source_adapter_name="crossref",
                status_code=response.status_code,
            )

        if response.status_code >= 400:
            raise AdapterConnectionError(
                f"Crossref returned HTTP {response.status_code}",
                source_adapter_name="crossref",
                target_url=f"{CROSSREF_BASE_URL}/works",
            )

        try:
            data = response.json()
        except Exception as exc:
            raise AdapterParseError(
                "Failed to parse Crossref JSON response",
                source_adapter_name="crossref",
                content_type=response.headers.get("content-type"),
                response_size_bytes=len(response.content),
            ) from exc

        return self._normalize_results(data, query)

    async def get_metadata(self, external_id: str) -> dict[str, Any]:
        """Retrieve detailed metadata for a specific DOI from Crossref.

        Args:
            external_id: DOI of the work to retrieve.

        Returns:
            Dict of metadata fields from Crossref.
        """
        try:
            async with httpx.AsyncClient(
                proxy=self._proxy_url,
                timeout=15.0,
            ) as client:
                response = await client.get(
                    f"{CROSSREF_BASE_URL}/works/{external_id}",
                    headers=self._build_headers(None),
                )
        except httpx.TimeoutException as exc:
            raise AdapterTimeoutError(
                "Crossref metadata request timed out",
                source_adapter_name="crossref",
            ) from exc
        except httpx.ConnectError as exc:
            raise AdapterConnectionError(
                f"Failed to connect to Crossref API: {exc}",
                source_adapter_name="crossref",
                target_url=f"{CROSSREF_BASE_URL}/works/{external_id}",
            ) from exc

        if response.status_code == 404:
            return {}

        if response.status_code >= 400:
            raise AdapterConnectionError(
                f"Crossref returned HTTP {response.status_code}",
                source_adapter_name="crossref",
                target_url=f"{CROSSREF_BASE_URL}/works/{external_id}",
            )

        try:
            data = response.json()
            return data.get("message", {})
        except Exception as exc:
            raise AdapterParseError(
                "Failed to parse Crossref metadata response",
                source_adapter_name="crossref",
                content_type=response.headers.get("content-type"),
                response_size_bytes=len(response.content),
            ) from exc

    async def health_check(self) -> float:
        """Perform a lightweight health check against Crossref /works?rows=0.

        Returns:
            Response time in seconds.

        Raises:
            AdapterConnectionError: If Crossref is unreachable.
        """
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                proxy=self._proxy_url,
                timeout=15.0,
            ) as client:
                response = await client.get(
                    f"{CROSSREF_BASE_URL}/works",
                    params={"rows": "0"},
                    headers=self._build_headers(None),
                )
                response.raise_for_status()
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
            raise AdapterConnectionError(
                f"Crossref health check failed: {exc}",
                source_adapter_name="crossref",
                target_url=f"{CROSSREF_BASE_URL}/works?rows=0",
            ) from exc

        return time.monotonic() - start

    def get_capabilities(self) -> AdapterCapabilities:
        """Declare the query capabilities supported by Crossref adapter.

        Returns:
            AdapterCapabilities indicating keyword, author, date_range,
            and DOI support.
        """
        return AdapterCapabilities(
            supports_keyword=True,
            supports_author=True,
            supports_date_range=True,
            supports_publication_type=False,
            supports_doi=True,
        )

    def get_adapter_metadata(self) -> AdapterMetadata:
        """Return immutable metadata about the Crossref adapter.

        Returns:
            AdapterMetadata with name, version, display_name, requires_api_key.
        """
        return AdapterMetadata(
            name="crossref",
            version="1.0.0",
            display_name="Crossref",
            requires_api_key=False,
        )

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _build_query_params(self, query: SearchQuery) -> dict[str, str]:
        """Translate a SearchQuery into Crossref query parameters.

        Args:
            query: The structured search query.

        Returns:
            Dict of query parameters for the /works endpoint.
        """
        params: dict[str, str] = {
            "query.bibliographic": query.terms,
            "rows": str(query.page_size),
            "offset": str((query.page - 1) * query.page_size),
        }

        # Date range filter using Crossref filter syntax
        if query.date_from:
            params.setdefault("filter", "")
            params["filter"] += f"from-pub-date:{query.date_from.isoformat()},"
        if query.date_to:
            params.setdefault("filter", "")
            params["filter"] += f"until-pub-date:{query.date_to.isoformat()},"

        # Clean trailing comma from filter
        if "filter" in params:
            params["filter"] = params["filter"].rstrip(",")

        return params

    def _build_headers(self, api_key: str | None) -> dict[str, str]:
        """Build request headers for Crossref API.

        In authenticated mode, includes the Crossref Plus token.
        In unauthenticated mode, uses polite pool with mailto header.

        Args:
            api_key: Crossref Plus API token, or None for polite pool.

        Returns:
            Dict of HTTP headers.
        """
        headers: dict[str, str] = {}

        if api_key:
            headers["Crossref-Plus-API-Token"] = f"Bearer {api_key}"
        elif self._contact_email:
            headers["User-Agent"] = (
                f"AlcoaBase/1.0 (mailto:{self._contact_email})"
            )

        return headers

    def _normalize_results(
        self,
        data: dict[str, Any],
        query: SearchQuery,
    ) -> list[LiteratureSearchResult]:
        """Normalize Crossref JSON response to LiteratureSearchResult list.

        Parses the items array from the message object. Skips results
        missing required fields (title, DOI as external_id).

        Args:
            data: Parsed JSON response from Crossref.
            query: Original search query (for query_id generation).

        Returns:
            List of normalized search results.
        """
        results: list[LiteratureSearchResult] = []
        now = datetime.now(UTC)

        message = data.get("message", {})
        items = message.get("items", [])

        for item in items:
            try:
                result = self._normalize_item(item, now)
                if result is not None:
                    results.append(result)
            except Exception:
                logger.debug(
                    "Crossref: skipping item due to normalization error",
                    exc_info=True,
                )

        return results

    def _normalize_item(
        self,
        item: dict[str, Any],
        retrieval_timestamp: datetime,
    ) -> LiteratureSearchResult | None:
        """Normalize a single Crossref work item.

        Args:
            item: A single work item from the Crossref response.
            retrieval_timestamp: Timestamp for the retrieval_timestamp field.

        Returns:
            Normalized result, or None if required fields are missing.
        """
        # Extract title — Crossref returns title as a list
        title_list = item.get("title", [])
        if not title_list or not title_list[0]:
            logger.warning(
                "Crossref: skipping result with missing title, DOI=%s",
                item.get("DOI"),
            )
            return None

        title = title_list[0][:2000]

        # External ID is the DOI
        doi = item.get("DOI")
        if not doi:
            logger.warning(
                "Crossref: skipping result with missing DOI, title=%s",
                title[:100],
            )
            return None

        # Extract authors
        authors = self._extract_authors(item.get("author", []))

        # Extract publication date with partial date handling
        pub_date, date_precision = self._parse_date_parts(item)

        # Extract journal/venue from container-title
        container_titles = item.get("container-title", [])
        journal = container_titles[0] if container_titles else ""

        # Extract abstract
        abstract = item.get("abstract", "")
        if abstract:
            # Crossref abstracts may contain JATS XML tags; strip basic tags
            abstract = self._strip_jats_tags(abstract)[:50000]

        # Map publication type
        pub_type = self._map_publication_type(item.get("type", ""))

        # Build URL
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else None)

        return LiteratureSearchResult(
            title=title,
            authors=authors,
            abstract=abstract,
            doi=doi,
            publication_date=pub_date,
            source_id="crossref",
            external_id=doi,
            journal_or_venue=journal,
            publication_type=pub_type,
            url=url,
            date_precision=date_precision,
            retrieval_timestamp=retrieval_timestamp,
            query_id="",  # Set by the gateway service
        )

    def _extract_authors(self, author_list: list[dict[str, Any]]) -> list[str]:
        """Extract author names from Crossref author objects.

        Combines given and family name fields. Handles cases where
        only one field is present.

        Args:
            author_list: List of author dicts with 'given' and 'family' keys.

        Returns:
            List of formatted author name strings.
        """
        authors: list[str] = []
        for author in author_list[:500]:
            given = author.get("given", "")
            family = author.get("family", "")
            if given and family:
                authors.append(f"{given} {family}")
            elif family:
                authors.append(family)
            elif given:
                authors.append(given)
            # Skip authors with neither given nor family name
        return authors

    def _parse_date_parts(
        self,
        item: dict[str, Any],
    ) -> tuple[date, DatePrecision]:
        """Parse Crossref date-parts into a date and precision.

        Handles partial dates:
        - [[2023]] → 2023-01-01, YEAR precision
        - [[2023, 3]] → 2023-03-01, MONTH precision
        - [[2023, 3, 15]] → 2023-03-15, DAY precision

        Falls back to 'created' date-parts if 'published' is absent.

        Args:
            item: A single Crossref work item.

        Returns:
            Tuple of (normalized date, date precision).
        """
        # Try published date first, then created
        for date_field in ("published", "published-print", "published-online", "created"):
            date_obj = item.get(date_field)
            if date_obj and "date-parts" in date_obj:
                parts_list = date_obj["date-parts"]
                if parts_list and parts_list[0]:
                    parts = parts_list[0]
                    return self._parts_to_date(parts)

        # Fallback: return epoch date with year precision
        return date(1970, 1, 1), DatePrecision.YEAR

    def _parts_to_date(self, parts: list[int | None]) -> tuple[date, DatePrecision]:
        """Convert a date-parts array to a date and precision.

        Args:
            parts: List of [year], [year, month], or [year, month, day].

        Returns:
            Tuple of (normalized date, date precision).
        """
        # Filter out None values
        parts = [p for p in parts if p is not None]

        if len(parts) >= 3:
            try:
                return date(int(parts[0]), int(parts[1]), int(parts[2])), DatePrecision.DAY
            except (ValueError, TypeError):
                pass

        if len(parts) >= 2:
            try:
                return date(int(parts[0]), int(parts[1]), 1), DatePrecision.MONTH
            except (ValueError, TypeError):
                pass

        if len(parts) >= 1:
            try:
                return date(int(parts[0]), 1, 1), DatePrecision.YEAR
            except (ValueError, TypeError):
                pass

        return date(1970, 1, 1), DatePrecision.YEAR

    def _map_publication_type(self, crossref_type: str) -> PublicationType:
        """Map Crossref work type to normalized PublicationType.

        Args:
            crossref_type: Crossref type string (e.g., "journal-article").

        Returns:
            Normalized PublicationType enum value.
        """
        type_mapping: dict[str, PublicationType] = {
            "journal-article": PublicationType.JOURNAL_ARTICLE,
            "posted-content": PublicationType.PREPRINT,
            "proceedings-article": PublicationType.CONFERENCE_PAPER,
            "peer-review": PublicationType.REVIEW,
            "book-chapter": PublicationType.OTHER,
            "monograph": PublicationType.OTHER,
            "edited-book": PublicationType.OTHER,
            "reference-entry": PublicationType.OTHER,
            "dataset": PublicationType.OTHER,
            "report": PublicationType.OTHER,
        }
        return type_mapping.get(crossref_type, PublicationType.OTHER)

    @staticmethod
    def _strip_jats_tags(text: str) -> str:
        """Strip JATS XML tags from Crossref abstract text.

        Crossref abstracts often contain JATS markup like
        <jats:p>, <jats:italic>, etc. This strips all XML-like tags.

        Args:
            text: Raw abstract text potentially containing JATS tags.

        Returns:
            Plain text with tags removed.
        """
        import re

        return re.sub(r"<[^>]+>", "", text).strip()
