"""Abstract base class for all literature source adapters.

All adapters (built-in and custom) must implement this interface.
The Source_Registry validates compliance at registration time.

References:
    - Requirements 1.1, 1.4, 2.4
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from alcoabase.literature.schemas.search import (
        AdapterCapabilities,
        LiteratureSearchResult,
        SearchQuery,
    )


@dataclass(frozen=True)
class AdapterMetadata:
    """Immutable metadata describing a source adapter.

    Attributes:
        name: Unique identifier for the adapter (e.g., "pubmed").
        version: Semantic version string (e.g., "1.0.0").
        display_name: Human-readable name (e.g., "PubMed / MEDLINE").
        requires_api_key: Whether this source requires an API key.
    """

    name: str
    version: str
    display_name: str
    requires_api_key: bool


class BaseSourceAdapter(ABC):
    """Abstract interface for literature source adapters.

    Implementations must provide all abstract methods. The Source_Registry
    validates this at startup via hasattr checks on the required methods.
    """

    @abstractmethod
    async def search(
        self,
        query: SearchQuery,
        api_key: str | None = None,
        timeout: float = 15.0,
    ) -> list[LiteratureSearchResult]:
        """Execute a search against the external API.

        Args:
            query: Structured search query with terms and filters.
            api_key: Decrypted API key (None for unauthenticated sources).
            timeout: Per-request timeout in seconds.

        Returns:
            List of normalized search results.

        Raises:
            AdapterAuthError: On HTTP 401/403 from external API.
            AdapterTimeoutError: On request timeout.
            AdapterParseError: On unparseable response.
            AdapterConnectionError: On network failure.
        """
        ...

    @abstractmethod
    async def get_metadata(self, external_id: str) -> dict[str, Any]:
        """Retrieve detailed metadata for a specific record.

        Args:
            external_id: Source-specific identifier (PMID, DOI, arXiv ID).

        Returns:
            Dict of metadata fields from the source.
        """
        ...

    @abstractmethod
    async def health_check(self) -> float:
        """Perform a lightweight health check against the external API.

        Returns:
            Response time in seconds. Raises on failure.

        Raises:
            AdapterConnectionError: If the source is unreachable.
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> AdapterCapabilities:
        """Declare the query capabilities supported by this adapter.

        Returns:
            AdapterCapabilities describing supported fields and filters.
        """
        ...

    @abstractmethod
    def get_adapter_metadata(self) -> AdapterMetadata:
        """Return immutable metadata about this adapter.

        Returns:
            AdapterMetadata with name, version, display_name, requires_api_key.
        """
        ...
