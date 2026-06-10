"""Unpaywall API adapter for DOI-to-full-text resolution.

Resolves a single DOI to an open-access download URL using the Unpaywall API.
Unlike Phase 9.1 search adapters, this adapter does not implement
BaseSourceAdapter's search() method but reuses the same httpx/proxy/
circuit-breaker/rate-limiter infrastructure.

References:
    - Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

import httpx

from alcoabase.literature.ingestion.exceptions import (
    AdapterTimeoutError,
    DOINotFoundError,
    NoOpenAccessError,
    RateLimitedError,
)
from alcoabase.literature.services.audit_logger import AuditLogger
from alcoabase.literature.services.circuit_breaker import CircuitBreaker
from alcoabase.literature.services.proxy_manager import ProxyManager
from alcoabase.literature.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Enums and Data Classes
# ─────────────────────────────────────────────────────────────────────────────


class OALocationPriority(StrEnum):
    """Priority ranking for open-access location selection.

    Defines the order in which OA locations are evaluated when selecting
    the best available download URL from an Unpaywall response.
    """

    PUBLISHER_PDF_BEST = "publisher_pdf_best"
    REPOSITORY_PDF = "repository_pdf"
    PUBLISHER_HTML = "publisher_html"
    ANY_PDF = "any_pdf"
    ANY_HTML_XML = "any_html_xml"


@dataclass(frozen=True)
class UnpaywallResult:
    """Result of a DOI resolution via Unpaywall.

    Attributes:
        doi: The resolved DOI.
        is_oa: Whether an open-access version was found.
        best_url: The selected download URL (None if not OA).
        content_type: Expected content type hint (pdf, html, xml).
        host_type: Where the OA version is hosted (publisher, repository).
        version: Version of the article (publishedVersion, submittedVersion, etc.).
    """

    doi: str
    is_oa: bool
    best_url: str | None
    content_type: str | None
    host_type: str | None
    version: str | None


# ─────────────────────────────────────────────────────────────────────────────
# Unpaywall Adapter
# ─────────────────────────────────────────────────────────────────────────────


class UnpaywallAdapter:
    """Resolves DOIs to open-access full-text URLs via the Unpaywall API.

    Uses the existing Rate_Limiter, Circuit_Breaker, and Proxy_Manager
    from Phase 9.1 infrastructure. Enforces Unpaywall's fair-use policy
    (100,000 requests/day) via rate limiting and applies a circuit breaker
    that opens after 5 consecutive failures within a 5-minute window.

    Example:
        >>> adapter = UnpaywallAdapter(
        ...     base_url="https://api.unpaywall.org",
        ...     rate_limiter=rate_limiter,
        ...     circuit_breaker=circuit_breaker,
        ...     proxy_manager=proxy_manager,
        ...     audit_logger=audit_logger,
        ...     user_agent="AlcoaBase/1.0 (Literature Ingestion)",
        ... )
        >>> result = await adapter.resolve_doi("10.1000/xyz123", "user@example.com", company_id=1)
        >>> print(result.best_url)
    """

    def __init__(
        self,
        base_url: str,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreaker,
        proxy_manager: ProxyManager,
        audit_logger: AuditLogger,
        user_agent: str,
    ) -> None:
        """Initialize the Unpaywall adapter.

        Args:
            base_url: Unpaywall API base URL (from ALC_UNPAYWALL_API_URL setting).
            rate_limiter: Shared rate limiter instance for enforcing API quotas.
            circuit_breaker: Shared circuit breaker instance for resilience.
            proxy_manager: Shared proxy configuration for outbound requests.
            audit_logger: Shared audit logger for recording API interactions.
            user_agent: User-Agent header value (from ALC_LITERATURE_USER_AGENT setting).
        """
        self._base_url = base_url.rstrip("/")
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._proxy_manager = proxy_manager
        self._audit_logger = audit_logger
        self._user_agent = user_agent

    async def resolve_doi(
        self,
        doi: str,
        email: str,
        company_id: int,
        timeout: float = 15.0,
    ) -> UnpaywallResult:
        """Resolve a DOI to an open-access full-text URL.

        Queries Unpaywall API at ``GET /v2/{doi}?email={email}`` and selects
        the best available location using OALocationPriority ordering.

        Args:
            doi: The DOI to resolve (e.g., "10.1000/xyz123").
            email: Contact email required by Unpaywall fair use policy.
            company_id: For rate limiting and audit purposes.
            timeout: HTTP request timeout in seconds.

        Returns:
            UnpaywallResult with best_url populated if an OA version is found.

        Raises:
            DOINotFoundError: Unpaywall returned 404 for this DOI.
            NoOpenAccessError: DOI exists but no OA version is available.
            AdapterTimeoutError: Request timed out.
            RateLimitedError: Unpaywall returned HTTP 429.
        """
        # Acquire rate limiter token before making the request
        await self._rate_limiter.check_and_consume("unpaywall", company_id)

        # Verify circuit breaker allows the request
        can_execute = await self._circuit_breaker.can_execute("unpaywall")
        if not can_execute:
            raise AdapterTimeoutError(
                "Unpaywall circuit breaker is open; request blocked.",
                company_id=company_id,
                source_adapter_name="unpaywall",
                timeout_seconds=timeout,
            )

        url = f"{self._base_url}/v2/{doi}"
        params = {"email": email}
        headers = {"User-Agent": self._user_agent}

        # Resolve proxy configuration
        proxy_config = self._proxy_manager.get_proxy_for_source("unpaywall", url)
        proxy_url = proxy_config.get("https://") if proxy_config else None

        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=timeout,
            ) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            await self._circuit_breaker.record_failure("unpaywall")
            raise AdapterTimeoutError(
                f"Unpaywall request timed out after {timeout}s for DOI: {doi}",
                company_id=company_id,
                source_adapter_name="unpaywall",
                timeout_seconds=timeout,
            ) from exc
        except httpx.ConnectError as exc:
            await self._circuit_breaker.record_failure("unpaywall")
            raise AdapterTimeoutError(
                f"Failed to connect to Unpaywall API: {exc}",
                company_id=company_id,
                source_adapter_name="unpaywall",
                timeout_seconds=timeout,
            ) from exc

        # Handle HTTP error responses
        if response.status_code == 404:
            await self._circuit_breaker.record_success("unpaywall")
            raise DOINotFoundError(
                f"DOI not found in Unpaywall: {doi}",
                company_id=company_id,
                doi=doi,
            )

        if response.status_code == 429:
            await self._circuit_breaker.record_failure("unpaywall")
            retry_after = self._parse_retry_after(response)
            raise RateLimitedError(
                f"Unpaywall rate limit exceeded (HTTP 429) for DOI: {doi}",
                company_id=company_id,
                retry_after_seconds=retry_after,
                source_adapter_name="unpaywall",
            )

        if response.status_code >= 400:
            await self._circuit_breaker.record_failure("unpaywall")
            raise AdapterTimeoutError(
                f"Unpaywall returned HTTP {response.status_code} for DOI: {doi}",
                company_id=company_id,
                source_adapter_name="unpaywall",
                timeout_seconds=timeout,
            )

        # Success — record it with the circuit breaker
        await self._circuit_breaker.record_success("unpaywall")

        # Parse the response
        try:
            data = response.json()
        except Exception as exc:
            logger.warning(
                "Failed to parse Unpaywall JSON response for DOI %s: %s",
                doi,
                exc,
            )
            raise NoOpenAccessError(
                f"Failed to parse Unpaywall response for DOI: {doi}",
                company_id=company_id,
                doi=doi,
            ) from exc

        # Check if the DOI has open access
        is_oa = data.get("is_oa", False)
        oa_locations = data.get("oa_locations", []) or []

        if not is_oa or not oa_locations:
            raise NoOpenAccessError(
                f"No open-access version available for DOI: {doi}",
                company_id=company_id,
                doi=doi,
            )

        # Select the best location
        best_location = self.select_best_location(oa_locations)

        if best_location is None:
            raise NoOpenAccessError(
                f"No suitable open-access URL found for DOI: {doi}",
                company_id=company_id,
                doi=doi,
            )

        best_url, content_type_hint = best_location

        # Determine host_type and version from the matching location
        host_type: str | None = None
        version: str | None = None
        for loc in oa_locations:
            loc_url = loc.get("url_for_pdf") or loc.get("url_for_landing_page")
            if loc_url == best_url:
                host_type = loc.get("host_type")
                version = loc.get("version")
                break

        return UnpaywallResult(
            doi=doi,
            is_oa=True,
            best_url=best_url,
            content_type=content_type_hint,
            host_type=host_type,
            version=version,
        )

    def select_best_location(
        self,
        oa_locations: list[dict[str, object]],
    ) -> tuple[str, str] | None:
        """Select the best download URL from Unpaywall OA locations.

        Applies priority ordering to find the most suitable download URL:
            1. Publisher-hosted PDF with ``is_best=True`` and ``url_for_pdf`` set
            2. Repository PDF (``host_type="repository"``) with ``url_for_pdf`` set
            3. Publisher-hosted HTML (``host_type="publisher"``) with ``url_for_landing_page`` set
            4. Any entry with ``url_for_pdf`` set
            5. Any entry with ``url_for_landing_page`` set (HTML/XML)

        Args:
            oa_locations: List of OA location dicts from Unpaywall API response.
                Each dict may contain keys: host_type, url_for_pdf,
                url_for_landing_page, is_best, version.

        Returns:
            Tuple of (url, content_type_hint) where content_type_hint is
            "pdf" or "html", or None if no suitable location is found.
        """
        if not oa_locations:
            return None

        # Priority 1: Publisher PDF with is_best=True
        for loc in oa_locations:
            if (
                loc.get("host_type") == "publisher"
                and loc.get("is_best") is True
                and loc.get("url_for_pdf")
            ):
                return (str(loc["url_for_pdf"]), "pdf")

        # Priority 2: Repository PDF
        for loc in oa_locations:
            if loc.get("host_type") == "repository" and loc.get("url_for_pdf"):
                return (str(loc["url_for_pdf"]), "pdf")

        # Priority 3: Publisher HTML
        for loc in oa_locations:
            if (
                loc.get("host_type") == "publisher"
                and loc.get("url_for_landing_page")
            ):
                return (str(loc["url_for_landing_page"]), "html")

        # Priority 4: Any PDF
        for loc in oa_locations:
            if loc.get("url_for_pdf"):
                return (str(loc["url_for_pdf"]), "pdf")

        # Priority 5: Any HTML/XML
        for loc in oa_locations:
            if loc.get("url_for_landing_page"):
                return (str(loc["url_for_landing_page"]), "html")

        return None

    async def health_check(self) -> float:
        """Perform a lightweight connectivity check to the Unpaywall API.

        Sends a request for a well-known DOI (10.1371/journal.pone.0000000)
        to verify the API is reachable and responsive. Does not count against
        rate limits.

        Returns:
            Response time in seconds.

        Raises:
            AdapterTimeoutError: If the health check request fails.
        """
        start = time.monotonic()
        url = f"{self._base_url}/v2/10.1371/journal.pone.0000000"
        params = {"email": "healthcheck@alcoabase.local"}
        headers = {"User-Agent": self._user_agent}

        proxy_config = self._proxy_manager.get_proxy_for_source("unpaywall", url)
        proxy_url = proxy_config.get("https://") if proxy_config else None

        try:
            async with httpx.AsyncClient(
                proxy=proxy_url,
                timeout=10.0,
            ) as client:
                await client.get(url, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise AdapterTimeoutError(
                f"Unpaywall health check failed: {exc}",
                source_adapter_name="unpaywall",
                timeout_seconds=10.0,
            ) from exc

        elapsed = time.monotonic() - start
        logger.debug("Unpaywall health check completed in %.3fs", elapsed)
        return elapsed

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float:
        """Parse the Retry-After header from an HTTP 429 response.

        Args:
            response: The HTTP response with status 429.

        Returns:
            Seconds to wait before retrying. Defaults to 60.0 if the
            header is missing or unparseable.
        """
        retry_after_raw = response.headers.get("Retry-After")
        if retry_after_raw is None:
            return 60.0

        try:
            return float(retry_after_raw)
        except (ValueError, TypeError):
            return 60.0
