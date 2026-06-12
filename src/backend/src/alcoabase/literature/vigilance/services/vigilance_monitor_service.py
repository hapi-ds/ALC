"""Vigilance Monitor Service — orchestrates scheduled vigilance searches.

Responsible for constructing Boolean search queries from profile configurations,
dispatching searches via LiteratureGatewayService, filtering exclusion terms,
deduplicating against existing records, and triggering ingestion via
IngestionPipelineService. Enforces idempotent execution, timeout handling,
and retry logic with exponential backoff.

References:
    - Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
    - Requirements 13.1, 13.2, 13.4, 13.5, 13.6
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from alcoabase.literature.ingestion.models.ingestion import IngestionRecord
from alcoabase.literature.schemas.search import (
    LiteratureSearchResult,
    SearchQuery,
)
from alcoabase.literature.vigilance.audit import log_search_execution
from alcoabase.literature.vigilance.exceptions import (
    DuplicateExecutionError,
    ExecutionTimeoutError,
    GatewayUnavailableError,
)
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_search_execution import (
    VigilanceSearchExecution,
)
from alcoabase.literature.vigilance.models.vigilance_search_profile import (
    VigilanceSearchProfile,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from alcoabase.literature.ingestion.services.ingestion_service import (
        IngestionPipelineService,
    )
    from alcoabase.literature.services.gateway_service import (
        LiteratureGatewayService,
    )

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchExecutionResult:
    """Result of a single vigilance search execution.

    Attributes:
        execution_id: ID of the created VigilanceSearchExecution record.
        total_results_found: Total raw results from all sources.
        results_after_exclusion: Results remaining after exclusion filtering.
        results_ingested: Results successfully ingested.
        results_duplicate: Results matching existing records (skipped).
        execution_duration_ms: Total execution time in milliseconds.
        status: Execution status — "completed", "partial_failure", or "failed".
    """

    execution_id: int
    total_results_found: int
    results_after_exclusion: int
    results_ingested: int
    results_duplicate: int
    execution_duration_ms: int
    status: str


class VigilanceMonitorService:
    """Orchestrates vigilance search execution lifecycle.

    Responsibilities:
        - Construct Boolean search queries from profile configuration
        - Execute queries via LiteratureGatewayService
        - Filter results against exclusion terms (case-insensitive substring)
        - Deduplicate against existing IngestionRecords (DOI or source+external_id)
        - Dispatch non-duplicate results to IngestionPipelineService
        - Create VigilanceSearchExecution audit records
        - Handle retries with exponential backoff (5min, 15min, 60min)
        - Enforce idempotent execution (skip if already running)
        - Enforce 60-minute execution timeout
    """

    MAX_RETRIES: int = 3
    BACKOFF_INTERVALS: tuple[int, ...] = (300, 900, 3600)  # 5min, 15min, 60min
    EXECUTION_TIMEOUT_S: int = 3600  # 60 minutes

    def __init__(
        self,
        session_factory: "async_sessionmaker",
        literature_gateway: "LiteratureGatewayService",
        ingestion_pipeline: "IngestionPipelineService",
        search_queue: str = "literature_ingestion",
        execution_timeout: int = 3600,
    ) -> None:
        """Initialize with all dependencies.

        Args:
            session_factory: Async session factory for DB operations.
            literature_gateway: Service for executing literature searches.
            ingestion_pipeline: Service for ingesting search results.
            search_queue: Celery queue name for search tasks.
            execution_timeout: Max execution time in seconds (default 3600).
        """
        self._session_factory = session_factory
        self._literature_gateway = literature_gateway
        self._ingestion_pipeline = ingestion_pipeline
        self._search_queue = search_queue
        self._execution_timeout = execution_timeout

    async def execute_search(
        self,
        profile_id: int,
        company_id: int,
    ) -> SearchExecutionResult:
        """Execute a vigilance search for the given profile.

        Steps:
            1. Check idempotency (skip if already running for this profile)
            2. Load profile + product metadata
            3. Construct Boolean query
            4. Execute via LiteratureGatewayService with retry logic
            5. Filter exclusion terms
            6. Deduplicate against existing records
            7. Ingest non-duplicates via IngestionPipelineService
            8. Create VigilanceSearchExecution record
            9. Log to audit trail

        Args:
            profile_id: VigilanceSearchProfile to execute.
            company_id: Tenant scope.

        Returns:
            SearchExecutionResult with counts and status.

        Raises:
            DuplicateExecutionError: If same profile already running.
            ExecutionTimeoutError: If execution exceeds timeout.
            GatewayUnavailableError: After all retries exhausted.
        """
        start_time = time.monotonic()

        async with self._session_factory() as session:
            # Step 1: Idempotency check
            is_safe = await self._check_idempotency(session, profile_id)
            if not is_safe:
                # Find the existing running execution for error context
                stmt = select(VigilanceSearchExecution).where(
                    VigilanceSearchExecution.profile_id == profile_id,
                    VigilanceSearchExecution.status == "running",
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                existing_id = existing.id if existing else 0
                raise DuplicateExecutionError(
                    f"Profile {profile_id} already has a running execution.",
                    profile_id=profile_id,
                    existing_execution_id=existing_id,
                )

            # Step 2: Load profile and product
            profile = await session.get(VigilanceSearchProfile, profile_id)
            if profile is None or profile.company_id != company_id:
                raise ValueError(
                    f"VigilanceSearchProfile {profile_id} not found "
                    f"for company {company_id}."
                )

            product = await session.get(MedicalProduct, profile.product_id)
            if product is None:
                raise ValueError(
                    f"MedicalProduct {profile.product_id} not found."
                )

            # Step 3: Construct query
            search_query_dict = self.construct_search_query(
                search_terms=profile.search_terms or [],
                mesh_terms=profile.mesh_terms or [],
                adverse_event_keywords=profile.adverse_event_keywords or [],
                device_identifiers=profile.device_identifiers or [],
            )

            # Determine sources to query
            sources = profile.source_ids if profile.source_ids else None

            # Step 4: Execute search with retry logic
            raw_results: list[dict[str, Any]] = []
            status = "completed"
            last_error: Exception | None = None

            for attempt in range(self.MAX_RETRIES + 1):
                # Check timeout before each attempt
                elapsed_s = int(time.monotonic() - start_time)
                if elapsed_s >= self._execution_timeout:
                    raise ExecutionTimeoutError(
                        f"Execution timed out after {elapsed_s}s "
                        f"(limit: {self._execution_timeout}s).",
                        execution_id=0,
                        timeout_seconds=self._execution_timeout,
                        elapsed_seconds=elapsed_s,
                    )

                try:
                    search_response = await self._literature_gateway.search(
                        query=SearchQuery(
                            terms=search_query_dict["query_string"],
                            sources=sources,
                        ),
                        company_id=company_id,
                        user_id=0,  # System-initiated search
                    )
                    # Convert results to dicts for processing
                    raw_results = [
                        self._result_to_dict(r)
                        for r in search_response.results
                    ]
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Vigilance search attempt %d/%d failed for profile %d: %s",
                        attempt + 1,
                        self.MAX_RETRIES + 1,
                        profile_id,
                        str(exc),
                    )
                    if attempt < self.MAX_RETRIES:
                        backoff = self.BACKOFF_INTERVALS[attempt]
                        # Check if waiting would exceed timeout
                        projected_elapsed = (
                            int(time.monotonic() - start_time) + backoff
                        )
                        if projected_elapsed >= self._execution_timeout:
                            status = "partial_failure"
                            break
                        await asyncio.sleep(backoff)
                    else:
                        # All retries exhausted
                        raise GatewayUnavailableError(
                            f"Literature gateway unavailable after "
                            f"{self.MAX_RETRIES} retries for profile {profile_id}.",
                            profile_id=profile_id,
                            retry_attempts=self.MAX_RETRIES,
                        ) from exc

            # If we broke out of the loop due to timeout projection
            if last_error is not None and status == "partial_failure":
                raw_results = []

            total_results_found = len(raw_results)

            # Step 5: Filter exclusion terms
            exclusion_terms = profile.exclusion_terms or []
            filtered_results = self.filter_exclusion_terms(
                raw_results, exclusion_terms
            )
            results_after_exclusion = len(filtered_results)

            # Step 6: Deduplicate
            non_duplicates, duplicate_count = await self.deduplicate_results(
                session, filtered_results, company_id
            )

            # Step 7: Ingest non-duplicates
            results_ingested = 0
            if non_duplicates:
                try:
                    ingestion_inputs = [
                        self._dict_to_ingestion_input(r) for r in non_duplicates
                    ]
                    batch_response = await self._ingestion_pipeline.submit_batch(
                        results=ingestion_inputs,
                        company_id=company_id,
                        user_id=0,  # System-initiated ingestion
                    )
                    results_ingested = len(batch_response.created_ids)
                except Exception as exc:
                    logger.error(
                        "Ingestion failed for profile %d: %s",
                        profile_id,
                        str(exc),
                    )
                    status = "partial_failure"

            # Step 8: Create execution record
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            execution = VigilanceSearchExecution(
                profile_id=profile_id,
                company_id=company_id,
                search_parameters=search_query_dict,
                sources_queried=sources or [],
                total_results_found=total_results_found,
                results_after_exclusion=results_after_exclusion,
                results_ingested=results_ingested,
                results_duplicate=duplicate_count,
                execution_duration_ms=elapsed_ms,
                status=status,
            )
            session.add(execution)
            await session.commit()
            await session.refresh(execution)

            # Step 9: Audit log (structured, ALCOA+ compliant)
            log_search_execution(
                execution_id=execution.id,
                profile_id=profile_id,
                product_id=profile.product_id,
                company_id=company_id,
                sources_queried=sources or [],
                total_results_found=total_results_found,
                results_ingested=results_ingested,
                execution_duration_ms=elapsed_ms,
                status=status,
            )

            return SearchExecutionResult(
                execution_id=execution.id,
                total_results_found=total_results_found,
                results_after_exclusion=results_after_exclusion,
                results_ingested=results_ingested,
                results_duplicate=duplicate_count,
                execution_duration_ms=elapsed_ms,
                status=status,
            )

    def construct_search_query(
        self,
        search_terms: list[str],
        mesh_terms: list[str],
        adverse_event_keywords: list[str],
        device_identifiers: list[str],
    ) -> dict[str, Any]:
        """Construct a Boolean search query from profile fields.

        Logic:
            - Terms within each category are ORed together
            - Categories are ANDed with adverse_event_keywords
            - Final query: (search_terms OR mesh_terms OR device_identifiers)
              AND adverse_event_keywords

        Args:
            search_terms: Product names, brand names, synonyms.
            mesh_terms: MeSH descriptors.
            adverse_event_keywords: Adverse event descriptors.
            device_identifiers: UDIs, catalog numbers, model numbers.

        Returns:
            Structured query dict for LiteratureGatewayService containing:
                - query_string: The fully constructed Boolean query string.
                - product_clause: The OR-joined product terms clause.
                - adverse_event_clause: The OR-joined adverse event clause.
                - components: Dict of original term lists for audit.
        """
        # Build the product/device identification clause (OR logic)
        product_terms: list[str] = []
        product_terms.extend(search_terms)
        product_terms.extend(mesh_terms)
        product_terms.extend(device_identifiers)

        # Escape terms that contain special Boolean characters
        product_clause = " OR ".join(
            f'"{term}"' if " " in term else term
            for term in product_terms
            if term.strip()
        )

        # Build the adverse event clause (OR logic within)
        adverse_clause = " OR ".join(
            f'"{kw}"' if " " in kw else kw
            for kw in adverse_event_keywords
            if kw.strip()
        )

        # Combine with AND logic
        if product_clause and adverse_clause:
            query_string = f"({product_clause}) AND ({adverse_clause})"
        elif product_clause:
            query_string = product_clause
        elif adverse_clause:
            query_string = adverse_clause
        else:
            query_string = ""

        return {
            "query_string": query_string,
            "product_clause": product_clause,
            "adverse_event_clause": adverse_clause,
            "components": {
                "search_terms": search_terms,
                "mesh_terms": mesh_terms,
                "adverse_event_keywords": adverse_event_keywords,
                "device_identifiers": device_identifiers,
            },
        }

    def filter_exclusion_terms(
        self,
        results: list[dict[str, Any]],
        exclusion_terms: list[str],
    ) -> list[dict[str, Any]]:
        """Filter out results matching exclusion terms.

        Performs case-insensitive substring match against title and abstract.
        A result is excluded if any exclusion term appears as a substring
        in either its title or abstract.

        Args:
            results: Raw search results with 'title' and 'abstract' fields.
            exclusion_terms: Terms to exclude (case-insensitive).

        Returns:
            Filtered results with exclusion matches removed.
        """
        if not exclusion_terms:
            return results

        # Pre-lowercase exclusion terms for efficient comparison
        lowered_exclusions = [term.lower() for term in exclusion_terms if term.strip()]

        if not lowered_exclusions:
            return results

        filtered: list[dict[str, Any]] = []
        for result in results:
            title = (result.get("title") or "").lower()
            abstract = (result.get("abstract") or "").lower()
            combined_text = f"{title} {abstract}"

            excluded = any(
                term in combined_text for term in lowered_exclusions
            )
            if not excluded:
                filtered.append(result)

        return filtered

    async def deduplicate_results(
        self,
        session: "AsyncSession",
        results: list[dict[str, Any]],
        company_id: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Deduplicate results against existing IngestionRecords.

        Match on (company_id, DOI) or (company_id, source_id, external_id).
        A result is considered a duplicate if either match condition is met.

        Args:
            session: Active DB session.
            results: Results after exclusion filtering.
            company_id: Tenant scope.

        Returns:
            Tuple of (non_duplicate_results, duplicate_count).
        """
        if not results:
            return [], 0

        non_duplicates: list[dict[str, Any]] = []
        duplicate_count = 0

        for result in results:
            doi = result.get("doi")
            source_id = result.get("source_id")
            external_id = result.get("external_id")

            is_duplicate = False

            # Check DOI-based deduplication
            if doi:
                stmt = select(IngestionRecord.id).where(
                    IngestionRecord.company_id == company_id,
                    IngestionRecord.doi == doi,
                )
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none() is not None:
                    is_duplicate = True

            # Check source_id + external_id deduplication
            if not is_duplicate and source_id and external_id:
                stmt = select(IngestionRecord.id).where(
                    IngestionRecord.company_id == company_id,
                    IngestionRecord.source_id == source_id,
                    IngestionRecord.external_id == external_id,
                )
                existing = await session.execute(stmt)
                if existing.scalar_one_or_none() is not None:
                    is_duplicate = True

            if is_duplicate:
                duplicate_count += 1
            else:
                non_duplicates.append(result)

        return non_duplicates, duplicate_count

    async def _check_idempotency(
        self,
        session: "AsyncSession",
        profile_id: int,
    ) -> bool:
        """Check if an execution is already in progress for this profile.

        Verifies no VigilanceSearchExecution with status "running" exists
        for the given profile_id. This prevents duplicate work from Celery
        beat clock skew or restart overlap.

        Args:
            session: Active DB session.
            profile_id: Profile to check.

        Returns:
            True if safe to proceed (no running execution), False otherwise.
        """
        stmt = select(VigilanceSearchExecution.id).where(
            VigilanceSearchExecution.profile_id == profile_id,
            VigilanceSearchExecution.status == "running",
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        return existing is None

    @staticmethod
    def _result_to_dict(result: LiteratureSearchResult) -> dict[str, Any]:
        """Convert a LiteratureSearchResult Pydantic model to a plain dict.

        Args:
            result: Normalized search result from gateway.

        Returns:
            Dict with all relevant fields for filtering and deduplication.
        """
        return {
            "title": result.title,
            "authors": result.authors,
            "abstract": result.abstract,
            "doi": result.doi,
            "publication_date": result.publication_date,
            "source_id": result.source_id,
            "external_id": result.external_id,
            "journal_or_venue": result.journal_or_venue,
            "publication_type": (
                result.publication_type.value
                if hasattr(result.publication_type, "value")
                else str(result.publication_type)
            ),
            "url": result.url,
        }

    @staticmethod
    def _dict_to_ingestion_input(result_dict: dict[str, Any]) -> Any:
        """Convert a result dict to a format accepted by IngestionPipelineService.

        Uses the LiteratureSearchResultInput schema expected by
        IngestionPipelineService.submit_batch().

        Args:
            result_dict: Result dict from _result_to_dict.

        Returns:
            Object compatible with IngestionPipelineService.submit_batch input.
        """
        from datetime import date as date_type
        from datetime import datetime as dt
        from datetime import timezone

        from alcoabase.literature.ingestion.schemas.ingestion import (
            LiteratureSearchResultInput,
        )

        # Convert date to datetime if needed (ingestion expects datetime | None)
        pub_date = result_dict.get("publication_date")
        if pub_date is not None and not isinstance(pub_date, dt):
            if isinstance(pub_date, date_type):
                pub_date = dt(
                    pub_date.year,
                    pub_date.month,
                    pub_date.day,
                    tzinfo=timezone.utc,
                )
            else:
                pub_date = None

        return LiteratureSearchResultInput(
            title=result_dict["title"],
            authors=result_dict.get("authors") or [],
            abstract=result_dict.get("abstract"),
            doi=result_dict.get("doi"),
            publication_date=pub_date,
            source_id=result_dict.get("source_id", "unknown"),
            external_id=result_dict.get("external_id", "unknown"),
            journal_or_venue=result_dict.get("journal_or_venue", ""),
            publication_type=result_dict.get("publication_type", "other"),
            url=result_dict.get("url") or "",
        )
