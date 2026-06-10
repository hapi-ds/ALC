"""Main orchestrator for literature search operations.

Coordinates adapters, rate limiting, circuit breaking, deduplication,
normalization, and audit logging. Dispatches queries to enabled source
adapters in parallel, handles partial failures gracefully, and enforces
a 30-second overall search timeout.

References:
    - Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
    - Requirements 9.1, 9.2, 9.3, 12.1, 12.4
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from alcoabase.literature.exceptions import (
    AdapterError,
    AdapterTimeoutError,
    AllSourcesUnavailableError,
    RateLimitExceededError,
)
from alcoabase.literature.models.literature import SourceConfiguration
from alcoabase.literature.schemas.search import (
    LiteratureSearchResult,
    PartialResultInfo,
    SearchQuery,
    SearchResponse,
)
from alcoabase.literature.services.api_key_vault import APIKeyVault, EncryptedKey
from alcoabase.literature.services.audit_logger import AuditLogger
from alcoabase.literature.services.circuit_breaker import CircuitBreaker
from alcoabase.literature.services.proxy_manager import ProxyManager
from alcoabase.literature.services.rate_limiter import RateLimiter
from alcoabase.literature.services.source_registry import SourceRegistry

logger = logging.getLogger(__name__)

# Overall search timeout in seconds (Requirement 8.8).
SEARCH_TIMEOUT_SECONDS: float = 30.0

# Per-source request timeout in seconds (Requirement 8.6).
PER_SOURCE_TIMEOUT_SECONDS: float = 15.0


class LiteratureGatewayService:
    """Orchestrates multi-source literature searches.

    Responsibilities:
        - Dispatch queries to enabled adapters in parallel
        - Enforce rate limits and circuit breaker policies
        - Normalize and deduplicate results
        - Handle partial failures gracefully
        - Determine when to delegate long-running searches to Celery

    Example:
        >>> gateway = LiteratureGatewayService(
        ...     source_registry=registry,
        ...     rate_limiter=limiter,
        ...     circuit_breaker=breaker,
        ...     api_key_vault=vault,
        ...     audit_logger=audit,
        ...     proxy_manager=proxy,
        ... )
        >>> response = await gateway.search(query, company_id=1, user_id=42)
    """

    def __init__(
        self,
        source_registry: SourceRegistry,
        rate_limiter: RateLimiter,
        circuit_breaker: CircuitBreaker,
        api_key_vault: APIKeyVault,
        audit_logger: AuditLogger,
        proxy_manager: ProxyManager,
    ) -> None:
        """Initialize with all required service dependencies.

        Args:
            source_registry: For adapter lookup and health status.
            rate_limiter: For request throttling.
            circuit_breaker: For failure isolation.
            api_key_vault: For decrypting API keys at request time.
            audit_logger: For recording all external interactions.
            proxy_manager: For proxy configuration.
        """
        self._source_registry = source_registry
        self._rate_limiter = rate_limiter
        self._circuit_breaker = circuit_breaker
        self._api_key_vault = api_key_vault
        self._audit_logger = audit_logger
        self._proxy_manager = proxy_manager

    async def search(
        self,
        query: SearchQuery,
        company_id: int,
        user_id: int,
        source_configs: list[SourceConfiguration] | None = None,
    ) -> SearchResponse:
        """Execute a literature search across enabled sources.

        Dispatches to all enabled sources in parallel, deduplicates by DOI,
        and returns normalized results ordered by source priority.

        Flow:
            1. Determine which sources to query (company enabled sources,
               filtered by query.sources if specified).
            2. For each source: check circuit breaker → check rate limit →
               decrypt API key → call adapter.search().
            3. Collect results, catch timeouts/errors per source.
            4. Deduplicate by DOI, order by priority.
            5. Return SearchResponse with partial_results info.

        Args:
            query: Structured search query.
            company_id: Requesting company (for config and rate limits).
            user_id: Requesting user (for audit trail).
            source_configs: Pre-loaded source configurations for the company.
                If None, the service assumes no sources are configured.

        Returns:
            SearchResponse with results, metadata, and partial_results info.

        Raises:
            AllSourcesUnavailableError: If no sources can be reached (HTTP 503).
            RateLimitExceededError: If company rate limit hit (HTTP 429).
        """
        query_id = str(uuid.uuid4())

        # Step 1: Determine targeted sources
        targeted_sources, warnings = self._resolve_targeted_sources(
            query=query,
            source_configs=source_configs or [],
        )

        if not targeted_sources:
            raise AllSourcesUnavailableError(
                "No literature sources are currently reachable for this company.",
                unavailable_sources=warnings,
            )

        # Build source priority map
        source_priorities = {
            config.source_adapter_name: config.priority
            for config in targeted_sources
        }

        # Step 2 & 3: Dispatch to all targeted sources in parallel with timeout
        try:
            results, partial_info = await asyncio.wait_for(
                self._dispatch_parallel(
                    query=query,
                    query_id=query_id,
                    company_id=company_id,
                    user_id=user_id,
                    targeted_sources=targeted_sources,
                ),
                timeout=SEARCH_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # Overall 30-second timeout exceeded — return empty with all
            # sources marked as timed out
            logger.warning(
                "Overall search timeout (%.0fs) exceeded for query %s.",
                SEARCH_TIMEOUT_SECONDS,
                query_id,
            )
            timed_out_names = [
                config.source_adapter_name for config in targeted_sources
            ]
            return SearchResponse(
                results=[],
                total_count=0,
                partial_results=PartialResultInfo(
                    timed_out_sources=timed_out_names,
                ),
                query_id=query_id,
            )

        # Add warnings for unavailable requested sources
        if warnings:
            if partial_info is None:
                partial_info = PartialResultInfo()
            partial_info.unavailable_sources.extend(warnings)

        # Check if all sources failed
        all_source_names = [
            config.source_adapter_name for config in targeted_sources
        ]
        failed_sources = set()
        if partial_info:
            failed_sources = set(
                partial_info.timed_out_sources
                + partial_info.errored_sources
                + partial_info.unavailable_sources
            )
        if failed_sources >= set(all_source_names) and not results:
            # Estimate recovery based on circuit breaker state
            recovery_times: list[float] = []
            for source_name in all_source_names:
                rt = await self._circuit_breaker.get_estimated_recovery_time(
                    source_name
                )
                if rt is not None:
                    recovery_times.append(rt)
            estimated_recovery = (
                min(recovery_times) if recovery_times else None
            )
            raise AllSourcesUnavailableError(
                "No literature sources are currently reachable.",
                estimated_recovery_time=estimated_recovery,
                unavailable_sources=list(failed_sources),
            )

        # Step 4: Deduplicate and order results
        deduplicated = self.deduplicate_results(results, source_priorities)
        ordered = self.order_results_by_priority(deduplicated, source_priorities)

        return SearchResponse(
            results=ordered,
            total_count=len(ordered),
            partial_results=partial_info,
            query_id=query_id,
        )

    def deduplicate_results(
        self,
        results: list[LiteratureSearchResult],
        source_priorities: dict[str, int],
    ) -> list[LiteratureSearchResult]:
        """Deduplicate results by DOI, keeping highest-priority source.

        Results with null DOI are never deduplicated and always kept.

        Args:
            results: Combined results from all sources.
            source_priorities: Mapping of source_name → priority (1=highest).

        Returns:
            Deduplicated list of results.
        """
        # Separate null-DOI results (always kept)
        null_doi_results: list[LiteratureSearchResult] = []
        doi_results: dict[str, LiteratureSearchResult] = {}

        for result in results:
            if result.doi is None:
                null_doi_results.append(result)
            else:
                existing = doi_results.get(result.doi)
                if existing is None:
                    doi_results[result.doi] = result
                else:
                    # Keep the result from the higher-priority source
                    # (lower priority number = higher priority)
                    existing_priority = source_priorities.get(
                        existing.source_id, 100
                    )
                    new_priority = source_priorities.get(result.source_id, 100)
                    if new_priority < existing_priority:
                        doi_results[result.doi] = result

        return list(doi_results.values()) + null_doi_results

    def order_results_by_priority(
        self,
        results: list[LiteratureSearchResult],
        source_priorities: dict[str, int],
    ) -> list[LiteratureSearchResult]:
        """Order results by source priority (lowest number first).

        Tie-breaking: alphabetical by source adapter name (source_id).

        Args:
            results: Results to order.
            source_priorities: Priority mapping (source_name → priority int).

        Returns:
            Ordered results list.
        """
        return sorted(
            results,
            key=lambda r: (
                source_priorities.get(r.source_id, 100),
                r.source_id,
            ),
        )

    def should_dispatch_async(
        self,
        query: SearchQuery,
        company_id: int,
        source_configs: list[SourceConfiguration] | None = None,
    ) -> bool:
        """Determine if a search should be dispatched as a Celery task.

        Criteria: > 3 sources targeted OR > 50 results requested (page_size).

        Args:
            query: The search query to evaluate.
            company_id: Company context for source count.
            source_configs: Pre-loaded source configurations for the company.

        Returns:
            True if the search should be dispatched asynchronously.
        """
        # Count targeted sources
        targeted_sources, _ = self._resolve_targeted_sources(
            query=query,
            source_configs=source_configs or [],
        )
        num_sources = len(targeted_sources)

        return num_sources > 3 or query.page_size > 50

    # ─────────────────────────────────────────────────────────────────────
    # Private Helpers
    # ─────────────────────────────────────────────────────────────────────

    def _resolve_targeted_sources(
        self,
        query: SearchQuery,
        source_configs: list[SourceConfiguration],
    ) -> tuple[list[SourceConfiguration], list[str]]:
        """Determine which sources to dispatch the query to.

        Returns the list of SourceConfigurations to target and a list of
        warning strings for requested sources that are unavailable.

        Args:
            query: The search query (may include a source filter).
            source_configs: Company's source configurations.

        Returns:
            Tuple of (targeted_configs, unavailable_warnings).
        """
        # Filter to only enabled sources that are registered
        enabled_configs: list[SourceConfiguration] = []
        for config in source_configs:
            if not config.is_enabled:
                continue
            adapter = self._source_registry.get_adapter(
                config.source_adapter_name
            )
            if adapter is not None:
                enabled_configs.append(config)

        warnings: list[str] = []

        # If query specifies source filter, narrow down
        if query.sources:
            filtered_configs: list[SourceConfiguration] = []
            enabled_names = {c.source_adapter_name for c in enabled_configs}

            for requested_source in query.sources:
                if requested_source in enabled_names:
                    # Find the matching config
                    for config in enabled_configs:
                        if config.source_adapter_name == requested_source:
                            filtered_configs.append(config)
                            break
                else:
                    warnings.append(requested_source)

            return filtered_configs, warnings

        return enabled_configs, warnings

    async def _dispatch_parallel(
        self,
        query: SearchQuery,
        query_id: str,
        company_id: int,
        user_id: int,
        targeted_sources: list[SourceConfiguration],
    ) -> tuple[list[LiteratureSearchResult], PartialResultInfo | None]:
        """Dispatch search to all targeted sources in parallel.

        Uses asyncio.gather with return_exceptions=True to collect
        results from all sources, handling individual failures.

        Args:
            query: The search query to dispatch.
            query_id: Unique identifier for this search operation.
            company_id: Requesting company ID.
            user_id: Requesting user ID.
            targeted_sources: List of source configurations to query.

        Returns:
            Tuple of (all_results, partial_result_info_or_None).
        """
        tasks = [
            self._query_single_source(
                query=query,
                query_id=query_id,
                company_id=company_id,
                user_id=user_id,
                source_config=config,
            )
            for config in targeted_sources
        ]

        # Use return_exceptions=True so individual failures don't cancel others
        outcomes: list[Any] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        all_results: list[LiteratureSearchResult] = []
        timed_out_sources: list[str] = []
        errored_sources: list[str] = []
        unavailable_sources: list[str] = []

        for config, outcome in zip(targeted_sources, outcomes):
            source_name = config.source_adapter_name

            if isinstance(outcome, asyncio.TimeoutError) or isinstance(
                outcome, AdapterTimeoutError
            ):
                timed_out_sources.append(source_name)
                logger.warning(
                    "Source '%s' timed out during search (query %s).",
                    source_name,
                    query_id,
                )
            elif isinstance(outcome, RateLimitExceededError):
                # Re-raise company-level rate limits to the caller
                raise outcome
            elif isinstance(outcome, _CircuitBreakerOpenMarker):
                unavailable_sources.append(source_name)
                logger.info(
                    "Source '%s' skipped — circuit breaker open (query %s).",
                    source_name,
                    query_id,
                )
            elif isinstance(outcome, Exception):
                errored_sources.append(source_name)
                logger.warning(
                    "Source '%s' returned error during search (query %s): %s",
                    source_name,
                    query_id,
                    outcome,
                )
            elif isinstance(outcome, list):
                all_results.extend(outcome)
            else:
                # Unexpected outcome type — treat as error
                errored_sources.append(source_name)
                logger.error(
                    "Unexpected outcome type from source '%s': %s",
                    source_name,
                    type(outcome),
                )

        # Build partial_results info if any source had issues
        partial_info: PartialResultInfo | None = None
        if timed_out_sources or errored_sources or unavailable_sources:
            partial_info = PartialResultInfo(
                timed_out_sources=timed_out_sources,
                errored_sources=errored_sources,
                unavailable_sources=unavailable_sources,
            )

        return all_results, partial_info

    async def _query_single_source(
        self,
        query: SearchQuery,
        query_id: str,
        company_id: int,
        user_id: int,
        source_config: SourceConfiguration,
    ) -> list[LiteratureSearchResult]:
        """Query a single source adapter with rate limit and circuit breaker checks.

        Flow:
            1. Check circuit breaker — skip if open.
            2. Check rate limit — raise if company limit exceeded.
            3. Decrypt API key (if configured).
            4. Call adapter.search() with per-source timeout.
            5. Record success/failure for circuit breaker.
            6. Log to audit trail.

        Args:
            query: The search query.
            query_id: ID for audit trail correlation.
            company_id: Company context.
            user_id: User context.
            source_config: Configuration for this source.

        Returns:
            List of LiteratureSearchResult from this source.

        Raises:
            _CircuitBreakerOpenMarker: If circuit breaker is open.
            RateLimitExceededError: If company rate limit exceeded.
            AdapterTimeoutError: If the source times out.
            AdapterError: On other adapter failures.
        """
        source_name = source_config.source_adapter_name

        # Step 1: Check circuit breaker
        can_execute = await self._circuit_breaker.can_execute(source_name)
        if not can_execute:
            return _raise_circuit_open(source_name)

        # Step 2: Check rate limit
        rate_result = await self._rate_limiter.check_and_consume(
            source_name, company_id
        )
        if not rate_result.allowed and not rate_result.queued:
            raise RateLimitExceededError(
                f"Rate limit exceeded for source '{source_name}'.",
                source_adapter_name=source_name,
                retry_after_seconds=rate_result.retry_after_seconds or 60.0,
                company_id=company_id,
            )

        # Step 3: Decrypt API key (if configured)
        api_key: str | None = None
        if (
            source_config.api_key_ciphertext is not None
            and source_config.api_key_nonce is not None
            and source_config.api_key_tag is not None
        ):
            encrypted = EncryptedKey(
                ciphertext=source_config.api_key_ciphertext,
                nonce=source_config.api_key_nonce,
                tag=source_config.api_key_tag,
            )
            api_key = self._api_key_vault.decrypt(encrypted)

        # Step 4: Call adapter.search() with per-source timeout
        adapter = self._source_registry.get_adapter(source_name)
        if adapter is None:
            raise AdapterError(
                f"Adapter '{source_name}' not found in registry.",
                source_adapter_name=source_name,
            )

        # Log the request to audit trail
        request_timestamp = datetime.now(timezone.utc)
        start_time = time.perf_counter()

        try:
            results = await asyncio.wait_for(
                adapter.search(query, api_key=api_key, timeout=PER_SOURCE_TIMEOUT_SECONDS),
                timeout=PER_SOURCE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            # Record failure in circuit breaker
            await self._circuit_breaker.record_failure(source_name)
            # Log failure to audit
            try:
                audit_id = await self._audit_logger.log_request(
                    source_adapter_name=source_name,
                    request_url=f"[{source_name}] search",
                    user_id=user_id,
                    company_id=company_id,
                    query_id=query_id,
                    request_timestamp=request_timestamp,
                )
                await self._audit_logger.log_failure(
                    audit_log_id=audit_id,
                    error_type="timeout",
                    error_message=(
                        f"Source '{source_name}' timed out after "
                        f"{PER_SOURCE_TIMEOUT_SECONDS}s."
                    ),
                )
            except Exception as log_err:
                logger.debug(
                    "Failed to log audit for timeout on '%s': %s",
                    source_name,
                    log_err,
                )
            raise AdapterTimeoutError(
                f"Source '{source_name}' timed out after "
                f"{PER_SOURCE_TIMEOUT_SECONDS}s.",
                source_adapter_name=source_name,
                timeout_seconds=PER_SOURCE_TIMEOUT_SECONDS,
            )
        except RateLimitExceededError:
            # Re-raise rate limit errors directly
            raise
        except AdapterError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            # Record failure in circuit breaker
            await self._circuit_breaker.record_failure(source_name)
            # Log failure to audit
            try:
                audit_id = await self._audit_logger.log_request(
                    source_adapter_name=source_name,
                    request_url=f"[{source_name}] search",
                    user_id=user_id,
                    company_id=company_id,
                    query_id=query_id,
                    request_timestamp=request_timestamp,
                )
                await self._audit_logger.log_failure(
                    audit_log_id=audit_id,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )
            except Exception as log_err:
                logger.debug(
                    "Failed to log audit for error on '%s': %s",
                    source_name,
                    log_err,
                )
            raise
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            await self._circuit_breaker.record_failure(source_name)
            try:
                audit_id = await self._audit_logger.log_request(
                    source_adapter_name=source_name,
                    request_url=f"[{source_name}] search",
                    user_id=user_id,
                    company_id=company_id,
                    query_id=query_id,
                    request_timestamp=request_timestamp,
                )
                await self._audit_logger.log_failure(
                    audit_log_id=audit_id,
                    error_type="unexpected_error",
                    error_message=str(e),
                )
            except Exception as log_err:
                logger.debug(
                    "Failed to log audit for unexpected error on '%s': %s",
                    source_name,
                    log_err,
                )
            raise AdapterError(
                f"Unexpected error from source '{source_name}': {e}",
                source_adapter_name=source_name,
            )

        # Step 5: Record success in circuit breaker
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        await self._circuit_breaker.record_success(source_name)

        # Step 6: Log successful request to audit trail
        try:
            audit_id = await self._audit_logger.log_request(
                source_adapter_name=source_name,
                request_url=f"[{source_name}] search",
                user_id=user_id,
                company_id=company_id,
                query_id=query_id,
                request_timestamp=request_timestamp,
            )
            await self._audit_logger.log_response(
                audit_log_id=audit_id,
                http_status_code=200,
                result_count=len(results),
                response_time_ms=elapsed_ms,
            )
        except Exception as log_err:
            logger.debug(
                "Failed to log audit for success on '%s': %s",
                source_name,
                log_err,
            )

        return results


# ─────────────────────────────────────────────────────────────────────────────
# Internal Sentinel
# ─────────────────────────────────────────────────────────────────────────────


class _CircuitBreakerOpenMarker(Exception):
    """Internal marker exception for circuit breaker open state.

    Not raised externally — used to signal in asyncio.gather outcomes that
    a source was skipped due to an open circuit breaker.
    """

    def __init__(self, source_name: str) -> None:
        self.source_name = source_name
        super().__init__(f"Circuit breaker open for '{source_name}'.")


def _raise_circuit_open(source_name: str) -> list[LiteratureSearchResult]:
    """Raise _CircuitBreakerOpenMarker to signal skipped source.

    This is used as a non-local exit from _query_single_source when the
    circuit breaker is open. asyncio.gather with return_exceptions=True
    will capture it.

    Args:
        source_name: Name of the source that was skipped.

    Raises:
        _CircuitBreakerOpenMarker: Always raised.
    """
    raise _CircuitBreakerOpenMarker(source_name)
