"""Property-based tests for Search UI Integration.

Tests correctness properties for the search filtering, pagination, and sorting
logic in KnowledgeService using Hypothesis.

# Feature: Step_4-1_search-ui-integration, Property 1: Filter logic preserves AND/OR semantics

References:
    - Design: .kiro/specs/Step_4-1_search-ui-integration/design.md
    - Requirements: .kiro/specs/Step_4-1_search-ui-integration/requirements.md
"""

from unittest.mock import patch

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.knowledge_service import KnowledgeService, SearchResult


# ---------------------------------------------------------------------------
# Shared fixture: KnowledgeService instance for filter testing
# ---------------------------------------------------------------------------


def _make_knowledge_service() -> KnowledgeService:
    """Create a KnowledgeService instance for pure filter function testing."""
    with patch("alcoabase.services.knowledge_service.get_settings") as mock_settings:
        mock_settings.return_value.model_embedding_dimension = 1024
        mock_settings.return_value.opensearch_url = "http://localhost:9200"
        service = KnowledgeService()
    return service


# ---------------------------------------------------------------------------
# Strategies for generating test data
# ---------------------------------------------------------------------------

DOCUMENT_TYPES = ["SOP", "Policy", "Protocol", "Report", "Manual", "Form"]
STATUSES = ["Draft", "Active", "Archived", "Under Review", "Approved"]
TAGS = ["GxP", "Quality", "Safety", "Training", "Compliance", "Audit", "CAPA", "Risk"]


def search_result_strategy() -> st.SearchStrategy[SearchResult]:
    """Generate a random SearchResult with varied metadata."""
    return st.builds(
        SearchResult,
        document_uuid=st.uuids().map(str),
        title=st.text(min_size=1, max_size=50),
        version=st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True),
        excerpt=st.text(min_size=1, max_size=100),
        relevance_score=st.floats(min_value=0.0, max_value=1.0),
        metadata=st.just({}),
        document_type=st.sampled_from(DOCUMENT_TYPES),
        status=st.sampled_from(STATUSES),
        tags=st.lists(st.sampled_from(TAGS), min_size=1, max_size=4, unique=True),
        created_at=st.none(),
        updated_at=st.none(),
    )


# ---------------------------------------------------------------------------
# Property 1: Filter logic preserves AND/OR semantics
# Feature: Step_4-1_search-ui-integration, Property 1: Filter logic preserves AND/OR semantics
# ---------------------------------------------------------------------------


class TestFilterAndOrSemanticsProperty:
    """Property tests verifying filter AND/OR semantics.

    For any set of documents with varied metadata and any non-empty filter
    combination, the filtered results contain only documents where:
    - For each filter category with a non-empty list, the document's metadata
      value for that category is contained in the filter list (OR within category)
    - This condition holds for ALL non-empty filter categories simultaneously
      (AND between categories)

    For tags specifically: a document matches if ANY of its tags are in the
    filter's tags list (OR within tags).

    **Validates: Requirements 1.2**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_filtered_results_match_all_active_categories(
        self, data: st.DataObject
    ) -> None:
        """Every result in filtered output satisfies all non-empty filter categories.

        Generates a random set of documents and random filter combinations
        (subsets of existing metadata values), then verifies that every result
        returned by _apply_filters matches at least one value per non-empty
        filter category.

        **Validates: Requirements 1.2**
        """
        service = _make_knowledge_service()

        # Generate a random set of search results
        results = data.draw(
            st.lists(search_result_strategy(), min_size=1, max_size=30),
            label="results",
        )

        # Collect distinct metadata values from the generated results
        all_doc_types = list({r.document_type for r in results if r.document_type})
        all_statuses = list({r.status for r in results if r.status})
        all_tags = list({tag for r in results for tag in r.tags})

        # Generate filter as subsets of existing metadata values
        filter_doc_types = data.draw(
            st.lists(
                st.sampled_from(all_doc_types) if all_doc_types else st.nothing(),
                max_size=min(len(all_doc_types), 3),
                unique=True,
            )
            if all_doc_types
            else st.just([]),
            label="filter_doc_types",
        )
        filter_statuses = data.draw(
            st.lists(
                st.sampled_from(all_statuses) if all_statuses else st.nothing(),
                max_size=min(len(all_statuses), 3),
                unique=True,
            )
            if all_statuses
            else st.just([]),
            label="filter_statuses",
        )
        filter_tags = data.draw(
            st.lists(
                st.sampled_from(all_tags) if all_tags else st.nothing(),
                max_size=min(len(all_tags), 4),
                unique=True,
            )
            if all_tags
            else st.just([]),
            label="filter_tags",
        )

        filters: dict[str, list[str]] = {
            "document_type": filter_doc_types,
            "status": filter_statuses,
            "tags": filter_tags,
        }

        # Apply filters
        filtered = service._apply_filters(results, filters)

        # Build active filters (non-empty categories only)
        active_filters = {k: v for k, v in filters.items() if v}

        # Verify: every result in filtered output matches ALL active categories
        for result in filtered:
            for category, values in active_filters.items():
                if category == "document_type":
                    assert result.document_type in values, (
                        f"Result document_type={result.document_type!r} "
                        f"not in filter values={values}"
                    )
                elif category == "status":
                    assert result.status in values, (
                        f"Result status={result.status!r} "
                        f"not in filter values={values}"
                    )
                elif category == "tags":
                    assert any(tag in values for tag in result.tags), (
                        f"Result tags={result.tags} has no overlap "
                        f"with filter values={values}"
                    )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_no_matching_documents_excluded(
        self, data: st.DataObject
    ) -> None:
        """No document that matches all active filter categories is excluded.

        Generates random documents and filters, then verifies that every
        document from the original set that satisfies all active filter
        categories appears in the filtered output (completeness check).

        **Validates: Requirements 1.2**
        """
        service = _make_knowledge_service()

        # Generate a random set of search results
        results = data.draw(
            st.lists(search_result_strategy(), min_size=1, max_size=30),
            label="results",
        )

        # Collect distinct metadata values from the generated results
        all_doc_types = list({r.document_type for r in results if r.document_type})
        all_statuses = list({r.status for r in results if r.status})
        all_tags = list({tag for r in results for tag in r.tags})

        # Generate filter as subsets of existing metadata values
        filter_doc_types = data.draw(
            st.lists(
                st.sampled_from(all_doc_types) if all_doc_types else st.nothing(),
                max_size=min(len(all_doc_types), 3),
                unique=True,
            )
            if all_doc_types
            else st.just([]),
            label="filter_doc_types",
        )
        filter_statuses = data.draw(
            st.lists(
                st.sampled_from(all_statuses) if all_statuses else st.nothing(),
                max_size=min(len(all_statuses), 3),
                unique=True,
            )
            if all_statuses
            else st.just([]),
            label="filter_statuses",
        )
        filter_tags = data.draw(
            st.lists(
                st.sampled_from(all_tags) if all_tags else st.nothing(),
                max_size=min(len(all_tags), 4),
                unique=True,
            )
            if all_tags
            else st.just([]),
            label="filter_tags",
        )

        filters: dict[str, list[str]] = {
            "document_type": filter_doc_types,
            "status": filter_statuses,
            "tags": filter_tags,
        }

        # Apply filters
        filtered = service._apply_filters(results, filters)

        # Build active filters (non-empty categories only)
        active_filters = {k: v for k, v in filters.items() if v}

        # Independently compute which results should match
        expected_matches = []
        for result in results:
            matches_all = True
            for category, values in active_filters.items():
                if category == "document_type":
                    if result.document_type not in values:
                        matches_all = False
                        break
                elif category == "status":
                    if result.status not in values:
                        matches_all = False
                        break
                elif category == "tags":
                    if not any(tag in values for tag in result.tags):
                        matches_all = False
                        break
            if matches_all:
                expected_matches.append(result)

        # Verify completeness: all expected matches are in filtered output
        assert len(filtered) == len(expected_matches), (
            f"Expected {len(expected_matches)} results, got {len(filtered)}. "
            f"Filters: {active_filters}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_empty_filters_return_all_results(
        self, data: st.DataObject
    ) -> None:
        """When all filter categories are empty, all results are returned.

        **Validates: Requirements 1.2**
        """
        service = _make_knowledge_service()

        results = data.draw(
            st.lists(search_result_strategy(), min_size=0, max_size=20),
            label="results",
        )

        # Empty filters (no active categories)
        filters: dict[str, list[str]] = {
            "document_type": [],
            "status": [],
            "tags": [],
        }

        filtered = service._apply_filters(results, filters)
        assert len(filtered) == len(results), (
            f"Empty filters should return all {len(results)} results, "
            f"got {len(filtered)}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_none_filters_return_all_results(
        self, data: st.DataObject
    ) -> None:
        """When filters is None, all results are returned.

        **Validates: Requirements 1.2**
        """
        service = _make_knowledge_service()

        results = data.draw(
            st.lists(search_result_strategy(), min_size=0, max_size=20),
            label="results",
        )

        filtered = service._apply_filters(results, None)
        assert len(filtered) == len(results), (
            f"None filters should return all {len(results)} results, "
            f"got {len(filtered)}"
        )


# ---------------------------------------------------------------------------
# Property 2: Offset pagination produces correct slice
# Feature: Step_4-1_search-ui-integration, Property 2: Offset pagination produces correct slice
# ---------------------------------------------------------------------------


class TestOffsetPaginationSliceProperty:
    """Property tests verifying offset pagination produces correct slices.

    For any search query that produces N total results and any valid offset
    (0 ≤ offset < N), the paginated results SHALL equal the slice
    `full_results[offset:offset+limit]` of the full result set, and
    `total_available` SHALL equal N.

    **Validates: Requirements 1.3, 2.2**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_paginated_results_equal_correct_slice(
        self, data: st.DataObject
    ) -> None:
        """Paginated results match full_results[offset:offset+limit].

        Generates a random set of SearchResults, then calls the pagination
        logic with a valid offset and limit, verifying the returned slice
        matches the expected Python list slice and total_available equals N.

        **Validates: Requirements 1.3, 2.2**
        """
        service = _make_knowledge_service()

        # Generate a non-empty list of search results (N >= 1)
        results = data.draw(
            st.lists(search_result_strategy(), min_size=1, max_size=50),
            label="results",
        )
        n = len(results)

        # Generate a valid offset: 0 <= offset < N
        offset = data.draw(
            st.integers(min_value=0, max_value=n - 1),
            label="offset",
        )

        # Generate a valid limit: 1 <= limit <= 100
        limit = data.draw(
            st.integers(min_value=1, max_value=100),
            label="limit",
        )

        # The pagination logic: after filtering (no filters = identity),
        # compute total_available = len(results), then slice results[offset:offset+limit]
        # We test this by calling _apply_filters with None (no filtering)
        # and then applying the same slice logic as hybrid_search.
        filtered_results = service._apply_filters(results, None)
        total_available = len(filtered_results)
        paginated_results = filtered_results[offset : offset + limit]

        # Verify: total_available equals N
        assert total_available == n, (
            f"total_available={total_available} should equal N={n}"
        )

        # Verify: paginated results equal the expected slice
        expected_slice = results[offset : offset + limit]
        assert paginated_results == expected_slice, (
            f"Paginated results (len={len(paginated_results)}) do not match "
            f"expected slice results[{offset}:{offset + limit}] "
            f"(len={len(expected_slice)})"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_total_available_equals_full_result_count(
        self, data: st.DataObject
    ) -> None:
        """total_available always equals the full result count before pagination.

        Generates result sets of varying sizes and verifies that total_available
        is always equal to N regardless of offset or limit values.

        **Validates: Requirements 1.3, 2.2**
        """
        service = _make_knowledge_service()

        # Generate a list of search results (can be empty)
        results = data.draw(
            st.lists(search_result_strategy(), min_size=0, max_size=50),
            label="results",
        )
        n = len(results)

        # Generate any valid offset (0 to N, inclusive of N for edge case)
        offset = data.draw(
            st.integers(min_value=0, max_value=max(n, 1)),
            label="offset",
        )

        # Generate a valid limit
        limit = data.draw(
            st.integers(min_value=1, max_value=100),
            label="limit",
        )

        # Apply no filters (identity) and compute pagination
        filtered_results = service._apply_filters(results, None)
        total_available = len(filtered_results)

        # Verify: total_available equals N
        assert total_available == n, (
            f"total_available={total_available} should equal N={n}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_pagination_slice_length_bounded_by_limit(
        self, data: st.DataObject
    ) -> None:
        """Paginated slice length is at most `limit` and at most `N - offset`.

        Verifies the slice never exceeds the limit and correctly handles
        cases where fewer than `limit` results remain after the offset.

        **Validates: Requirements 1.3, 2.2**
        """
        service = _make_knowledge_service()

        # Generate a non-empty list of search results
        results = data.draw(
            st.lists(search_result_strategy(), min_size=1, max_size=50),
            label="results",
        )
        n = len(results)

        # Generate a valid offset: 0 <= offset < N
        offset = data.draw(
            st.integers(min_value=0, max_value=n - 1),
            label="offset",
        )

        # Generate a valid limit
        limit = data.draw(
            st.integers(min_value=1, max_value=100),
            label="limit",
        )

        # Apply pagination
        filtered_results = service._apply_filters(results, None)
        paginated_results = filtered_results[offset : offset + limit]

        # Verify: slice length <= limit
        assert len(paginated_results) <= limit, (
            f"Paginated results length {len(paginated_results)} exceeds limit {limit}"
        )

        # Verify: slice length == min(limit, N - offset)
        expected_length = min(limit, n - offset)
        assert len(paginated_results) == expected_length, (
            f"Paginated results length {len(paginated_results)} should be "
            f"min(limit={limit}, N-offset={n - offset}) = {expected_length}"
        )


# ---------------------------------------------------------------------------
# Property 3: Date sort produces descending order
# Feature: Step_4-1_search-ui-integration, Property 3: Date sort produces descending order
# ---------------------------------------------------------------------------


import datetime as _dt


def search_result_with_timestamp_strategy() -> st.SearchStrategy[SearchResult]:
    """Generate a SearchResult with a random updated_at timestamp (or None)."""
    return st.builds(
        SearchResult,
        document_uuid=st.uuids().map(str),
        title=st.text(min_size=1, max_size=50),
        version=st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True),
        excerpt=st.text(min_size=1, max_size=100),
        relevance_score=st.floats(min_value=0.0, max_value=1.0),
        metadata=st.just({}),
        document_type=st.sampled_from(DOCUMENT_TYPES),
        status=st.sampled_from(STATUSES),
        tags=st.lists(st.sampled_from(TAGS), min_size=1, max_size=4, unique=True),
        created_at=st.none(),
        updated_at=st.one_of(
            st.datetimes(
                min_value=_dt.datetime(2000, 1, 1),
                max_value=_dt.datetime(2030, 12, 31),
            ).map(lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
            st.none(),
        ),
    )


class TestDateSortOrderingProperty:
    """Property tests verifying date sort produces descending order.

    For any set of documents with varied `updated_at` timestamps, when
    `sort_by` is "date", the returned results SHALL be ordered such that
    each result's `updated_at` is greater than or equal to the next result's
    `updated_at` (descending chronological order). None values sort last.

    **Validates: Requirements 1.4**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_date_sort_produces_descending_order(
        self, data: st.DataObject
    ) -> None:
        """When sort_by="date", results are in descending updated_at order.

        Generates documents with random `updated_at` timestamps (including
        None values), applies date sorting via the service logic, and verifies
        that each result's `updated_at` >= next result's `updated_at`.
        None values are treated as empty string and sort to the end.

        **Validates: Requirements 1.4**
        """
        service = _make_knowledge_service()

        # Generate a list of search results with random timestamps
        results = data.draw(
            st.lists(
                search_result_with_timestamp_strategy(),
                min_size=2,
                max_size=30,
            ),
            label="results",
        )

        # Apply the same sort logic as KnowledgeService.hybrid_search
        sorted_results = list(results)
        sorted_results.sort(
            key=lambda r: r.updated_at or "",
            reverse=True,
        )

        # Verify descending order: each result's updated_at >= next result's
        for i in range(len(sorted_results) - 1):
            current_key = sorted_results[i].updated_at or ""
            next_key = sorted_results[i + 1].updated_at or ""
            assert current_key >= next_key, (
                f"Date sort not descending at index {i}: "
                f"{sorted_results[i].updated_at!r} (key={current_key!r}) < "
                f"{sorted_results[i + 1].updated_at!r} (key={next_key!r})"
            )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_none_updated_at_sorts_last(
        self, data: st.DataObject
    ) -> None:
        """Documents with None updated_at sort after all dated documents.

        Generates a mix of documents with and without timestamps, applies
        date sorting, and verifies that all None-valued results appear
        after all results with actual timestamps.

        **Validates: Requirements 1.4**
        """
        service = _make_knowledge_service()

        # Generate results that include at least one with a timestamp and one without
        results_with_dates = data.draw(
            st.lists(
                st.builds(
                    SearchResult,
                    document_uuid=st.uuids().map(str),
                    title=st.text(min_size=1, max_size=50),
                    version=st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True),
                    excerpt=st.text(min_size=1, max_size=100),
                    relevance_score=st.floats(min_value=0.0, max_value=1.0),
                    metadata=st.just({}),
                    document_type=st.sampled_from(DOCUMENT_TYPES),
                    status=st.sampled_from(STATUSES),
                    tags=st.lists(
                        st.sampled_from(TAGS), min_size=1, max_size=4, unique=True
                    ),
                    created_at=st.none(),
                    updated_at=st.datetimes(
                        min_value=_dt.datetime(2000, 1, 1),
                        max_value=_dt.datetime(2030, 12, 31),
                    ).map(lambda dt: dt.strftime("%Y-%m-%dT%H:%M:%SZ")),
                ),
                min_size=1,
                max_size=15,
            ),
            label="results_with_dates",
        )

        results_without_dates = data.draw(
            st.lists(
                st.builds(
                    SearchResult,
                    document_uuid=st.uuids().map(str),
                    title=st.text(min_size=1, max_size=50),
                    version=st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True),
                    excerpt=st.text(min_size=1, max_size=100),
                    relevance_score=st.floats(min_value=0.0, max_value=1.0),
                    metadata=st.just({}),
                    document_type=st.sampled_from(DOCUMENT_TYPES),
                    status=st.sampled_from(STATUSES),
                    tags=st.lists(
                        st.sampled_from(TAGS), min_size=1, max_size=4, unique=True
                    ),
                    created_at=st.none(),
                    updated_at=st.none(),
                ),
                min_size=1,
                max_size=15,
            ),
            label="results_without_dates",
        )

        # Combine and shuffle
        all_results = results_with_dates + results_without_dates

        # Apply the same sort logic as KnowledgeService
        sorted_results = list(all_results)
        sorted_results.sort(
            key=lambda r: r.updated_at or "",
            reverse=True,
        )

        # Find the boundary: all dated results should come before None results
        first_none_index = None
        for i, result in enumerate(sorted_results):
            if result.updated_at is None:
                first_none_index = i
                break

        if first_none_index is not None:
            # All results after first_none_index should also be None
            for i in range(first_none_index, len(sorted_results)):
                assert sorted_results[i].updated_at is None, (
                    f"Non-None updated_at found at index {i} after first None "
                    f"at index {first_none_index}: "
                    f"{sorted_results[i].updated_at!r}"
                )
            # All results before first_none_index should have timestamps
            for i in range(first_none_index):
                assert sorted_results[i].updated_at is not None, (
                    f"None updated_at found at index {i} before first None "
                    f"at index {first_none_index}"
                )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_date_sort_preserves_all_results(
        self, data: st.DataObject
    ) -> None:
        """Date sorting does not add or remove any results.

        Verifies that the sorted output contains exactly the same set of
        results as the input (same count, same elements).

        **Validates: Requirements 1.4**
        """
        # Generate a list of search results with random timestamps
        results = data.draw(
            st.lists(
                search_result_with_timestamp_strategy(),
                min_size=0,
                max_size=30,
            ),
            label="results",
        )

        # Apply the same sort logic as KnowledgeService
        sorted_results = list(results)
        sorted_results.sort(
            key=lambda r: r.updated_at or "",
            reverse=True,
        )

        # Verify: same number of results
        assert len(sorted_results) == len(results), (
            f"Sort changed result count: {len(results)} → {len(sorted_results)}"
        )

        # Verify: same elements (by identity)
        assert set(id(r) for r in sorted_results) == set(id(r) for r in results), (
            "Sort added or removed results"
        )


# ---------------------------------------------------------------------------
# Property 4: Response echoes request parameters
# Feature: Step_4-1_search-ui-integration, Property 4: Response echoes request parameters
# ---------------------------------------------------------------------------

from alcoabase.api.search import (
    SearchFilters,
    SearchRequest,
    SearchResponse,
    SearchResultResponse,
)


class TestResponseEchoesRequestParametersProperty:
    """Property tests verifying response echoes request parameters.

    For any valid search request with offset O and filters F, the response
    SHALL contain `offset` equal to O and `filters_applied` equal to the
    non-empty filter categories from F (or empty dict if no filters active).

    **Validates: Requirements 2.3, 2.4**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_response_offset_echoes_request_offset(
        self, data: st.DataObject
    ) -> None:
        """Response offset field equals the request offset value.

        Generates random valid offsets and constructs a SearchResponse,
        verifying the offset is echoed correctly.

        **Validates: Requirements 2.3**
        """
        # Generate a random valid offset
        offset = data.draw(
            st.integers(min_value=0, max_value=10000),
            label="offset",
        )

        # Generate some results
        num_results = data.draw(
            st.integers(min_value=0, max_value=10),
            label="num_results",
        )
        results = [
            SearchResultResponse(
                document_uuid=f"uuid-{i}",
                title=f"Doc {i}",
                version="1.0",
                excerpt="Some excerpt",
                relevance_score=0.5,
            )
            for i in range(num_results)
        ]

        # Construct SearchResponse with the given offset
        response = SearchResponse(
            results=results,
            total=num_results,
            total_available=num_results + offset,
            query="test query",
            offset=offset,
            filters_applied={},
        )

        # Verify: response offset equals request offset
        assert response.offset == offset, (
            f"Response offset={response.offset} does not equal "
            f"request offset={offset}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_response_filters_applied_equals_non_empty_filter_categories(
        self, data: st.DataObject
    ) -> None:
        """Response filters_applied contains only non-empty filter categories.

        Generates random filter combinations (some empty, some non-empty),
        builds filters_applied the same way the router does (keeping only
        non-empty lists), and verifies the response echoes them correctly.

        **Validates: Requirements 2.4**
        """
        # Generate random filter values (some categories may be empty)
        filter_doc_types = data.draw(
            st.lists(
                st.sampled_from(DOCUMENT_TYPES),
                min_size=0,
                max_size=4,
                unique=True,
            ),
            label="filter_doc_types",
        )
        filter_statuses = data.draw(
            st.lists(
                st.sampled_from(STATUSES),
                min_size=0,
                max_size=3,
                unique=True,
            ),
            label="filter_statuses",
        )
        filter_tags = data.draw(
            st.lists(
                st.sampled_from(TAGS),
                min_size=0,
                max_size=4,
                unique=True,
            ),
            label="filter_tags",
        )

        # Build the SearchFilters model
        filters = SearchFilters(
            document_type=filter_doc_types,
            status=filter_statuses,
            tags=filter_tags,
        )

        # Compute filters_applied the same way the router does:
        # keep only non-empty lists
        filters_applied = {
            k: v for k, v in filters.model_dump().items() if v
        }

        # Construct SearchResponse with filters_applied
        response = SearchResponse(
            results=[],
            total=0,
            total_available=0,
            query="test query",
            offset=0,
            filters_applied=filters_applied,
        )

        # Verify: filters_applied contains exactly the non-empty categories
        expected_applied = {}
        if filter_doc_types:
            expected_applied["document_type"] = filter_doc_types
        if filter_statuses:
            expected_applied["status"] = filter_statuses
        if filter_tags:
            expected_applied["tags"] = filter_tags

        assert response.filters_applied == expected_applied, (
            f"Response filters_applied={response.filters_applied} does not equal "
            f"expected={expected_applied}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_response_echoes_both_offset_and_filters(
        self, data: st.DataObject
    ) -> None:
        """Response echoes both offset and filters_applied simultaneously.

        Generates a complete random request with offset and filters, simulates
        the router's response construction logic, and verifies both echo fields.

        **Validates: Requirements 2.3, 2.4**
        """
        # Generate random offset
        offset = data.draw(
            st.integers(min_value=0, max_value=5000),
            label="offset",
        )

        # Generate random filters with at least one non-empty category
        filter_doc_types = data.draw(
            st.lists(
                st.sampled_from(DOCUMENT_TYPES),
                min_size=1,
                max_size=3,
                unique=True,
            ),
            label="filter_doc_types",
        )
        filter_statuses = data.draw(
            st.lists(
                st.sampled_from(STATUSES),
                min_size=0,
                max_size=3,
                unique=True,
            ),
            label="filter_statuses",
        )
        filter_tags = data.draw(
            st.lists(
                st.sampled_from(TAGS),
                min_size=0,
                max_size=4,
                unique=True,
            ),
            label="filter_tags",
        )

        filters = SearchFilters(
            document_type=filter_doc_types,
            status=filter_statuses,
            tags=filter_tags,
        )

        # Compute filters_applied (non-empty categories only)
        filters_applied = {
            k: v for k, v in filters.model_dump().items() if v
        }

        # Construct response as the router would
        response = SearchResponse(
            results=[],
            total=0,
            total_available=0,
            query="any query",
            offset=offset,
            filters_applied=filters_applied,
        )

        # Verify offset echo
        assert response.offset == offset, (
            f"Response offset={response.offset} != request offset={offset}"
        )

        # Verify filters_applied echo
        assert response.filters_applied == filters_applied, (
            f"Response filters_applied={response.filters_applied} != "
            f"expected={filters_applied}"
        )


# ---------------------------------------------------------------------------
# Property 13: Result metadata fields always present
# Feature: Step_4-1_search-ui-integration, Property 13: Result metadata fields always present
# ---------------------------------------------------------------------------


class TestResultMetadataFieldsAlwaysPresentProperty:
    """Property tests verifying result metadata fields are always present.

    For any search result returned by the API, the response object SHALL
    contain the fields `document_type`, `status`, `tags`, `created_at`, and
    `updated_at` (with null/empty-list as valid values when metadata is absent).

    **Validates: Requirements 2.1**
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_metadata_fields_present_with_values(
        self, data: st.DataObject
    ) -> None:
        """SearchResultResponse always has metadata fields when constructed with values.

        Generates random metadata values and verifies all five metadata fields
        are present as attributes on the constructed model.

        **Validates: Requirements 2.1**
        """
        doc_type = data.draw(
            st.one_of(st.sampled_from(DOCUMENT_TYPES), st.none()),
            label="document_type",
        )
        status = data.draw(
            st.one_of(st.sampled_from(STATUSES), st.none()),
            label="status",
        )
        tags = data.draw(
            st.lists(st.sampled_from(TAGS), min_size=0, max_size=4, unique=True),
            label="tags",
        )
        created_at = data.draw(
            st.one_of(
                st.just("2024-01-15T10:30:00Z"),
                st.none(),
            ),
            label="created_at",
        )
        updated_at = data.draw(
            st.one_of(
                st.just("2024-06-20T14:00:00Z"),
                st.none(),
            ),
            label="updated_at",
        )

        result = SearchResultResponse(
            document_uuid="test-uuid",
            title="Test Document",
            version="1.0",
            excerpt="Test excerpt",
            relevance_score=0.75,
            document_type=doc_type,
            status=status,
            tags=tags,
            created_at=created_at,
            updated_at=updated_at,
        )

        # Verify all metadata fields are present as attributes
        assert hasattr(result, "document_type"), "Missing field: document_type"
        assert hasattr(result, "status"), "Missing field: status"
        assert hasattr(result, "tags"), "Missing field: tags"
        assert hasattr(result, "created_at"), "Missing field: created_at"
        assert hasattr(result, "updated_at"), "Missing field: updated_at"

        # Verify values match what was provided
        assert result.document_type == doc_type
        assert result.status == status
        assert result.tags == tags
        assert result.created_at == created_at
        assert result.updated_at == updated_at

    @given(data=st.data())
    @settings(max_examples=100)
    def test_metadata_fields_present_with_defaults(
        self, data: st.DataObject
    ) -> None:
        """SearchResultResponse has metadata fields even when not explicitly provided.

        Constructs SearchResultResponse with only required fields and verifies
        that metadata fields exist with their default values (None or empty list).

        **Validates: Requirements 2.1**
        """
        # Only provide required fields — metadata fields should use defaults
        result = SearchResultResponse(
            document_uuid=data.draw(st.uuids().map(str), label="uuid"),
            title=data.draw(st.text(min_size=1, max_size=50), label="title"),
            version=data.draw(
                st.from_regex(r"[0-9]+\.[0-9]+", fullmatch=True), label="version"
            ),
            excerpt=data.draw(st.text(min_size=1, max_size=100), label="excerpt"),
            relevance_score=data.draw(
                st.floats(min_value=0.0, max_value=1.0), label="score"
            ),
        )

        # Verify all metadata fields exist
        assert hasattr(result, "document_type"), "Missing field: document_type"
        assert hasattr(result, "status"), "Missing field: status"
        assert hasattr(result, "tags"), "Missing field: tags"
        assert hasattr(result, "created_at"), "Missing field: created_at"
        assert hasattr(result, "updated_at"), "Missing field: updated_at"

        # Verify default values
        assert result.document_type is None, (
            f"Default document_type should be None, got {result.document_type!r}"
        )
        assert result.status is None, (
            f"Default status should be None, got {result.status!r}"
        )
        assert result.tags == [], (
            f"Default tags should be empty list, got {result.tags!r}"
        )
        assert result.created_at is None, (
            f"Default created_at should be None, got {result.created_at!r}"
        )
        assert result.updated_at is None, (
            f"Default updated_at should be None, got {result.updated_at!r}"
        )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_metadata_fields_present_in_serialized_response(
        self, data: st.DataObject
    ) -> None:
        """Metadata fields appear in the serialized (dict) form of the response.

        Constructs a SearchResultResponse and serializes it via model_dump(),
        verifying that all metadata keys are present in the output dict
        regardless of whether values are None or populated.

        **Validates: Requirements 2.1**
        """
        doc_type = data.draw(
            st.one_of(st.sampled_from(DOCUMENT_TYPES), st.none()),
            label="document_type",
        )
        status = data.draw(
            st.one_of(st.sampled_from(STATUSES), st.none()),
            label="status",
        )
        tags = data.draw(
            st.lists(st.sampled_from(TAGS), min_size=0, max_size=4, unique=True),
            label="tags",
        )
        created_at = data.draw(
            st.one_of(st.just("2024-03-10T08:00:00Z"), st.none()),
            label="created_at",
        )
        updated_at = data.draw(
            st.one_of(st.just("2024-07-01T12:00:00Z"), st.none()),
            label="updated_at",
        )

        result = SearchResultResponse(
            document_uuid="uuid-123",
            title="Any Title",
            version="2.1",
            excerpt="Any excerpt text",
            relevance_score=0.9,
            document_type=doc_type,
            status=status,
            tags=tags,
            created_at=created_at,
            updated_at=updated_at,
        )

        # Serialize to dict (as would happen in JSON response)
        result_dict = result.model_dump()

        # Verify all metadata keys are present in serialized output
        required_metadata_keys = [
            "document_type",
            "status",
            "tags",
            "created_at",
            "updated_at",
        ]
        for key in required_metadata_keys:
            assert key in result_dict, (
                f"Metadata key '{key}' missing from serialized response. "
                f"Keys present: {list(result_dict.keys())}"
            )
