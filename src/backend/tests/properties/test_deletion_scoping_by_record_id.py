"""Property-based tests for deletion scoping by record_id.

Property 12: Deletion scoping by record_id
- Generate sets of indexed records with different record_ids
- Assert deleting one record_id removes only that record's chunks
- Mock OpenSearch to verify delete-by-query filter

References:
    - Design: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/design.md
    - Requirements: .kiro/specs/Step_9-3_high-dimensional-embedding-hybrid-indexing/requirements.md
"""

# Feature: Step_9-3_high-dimensional-embedding-hybrid-indexing

from unittest.mock import AsyncMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.embedding.services.index_manager import (
    LiteratureIndexManager,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Generate positive integer IDs for record_ids and company_ids
st_record_id = st.integers(min_value=1, max_value=1_000_000)
st_company_id = st.integers(min_value=1, max_value=10_000)


@st.composite
def st_distinct_record_ids(draw: st.DrawFn) -> list[int]:
    """Generate a list of 2-10 distinct record_ids."""
    ids = draw(
        st.lists(
            st_record_id,
            min_size=2,
            max_size=10,
            unique=True,
        )
    )
    return ids


# ---------------------------------------------------------------------------
# Property 12: Deletion scoping by record_id
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    company_id=st_company_id,
    record_ids=st_distinct_record_ids(),
    target_index=st.data(),
)
@pytest.mark.asyncio
async def test_deletion_scoping_by_record_id(
    company_id: int,
    record_ids: list[int],
    target_index: st.DataObject,
) -> None:
    """Deleting one record_id via delete_record_chunks issues a delete-by-query
    that filters on ONLY that specific ingestion_record_id AND the company_id,
    ensuring other records' chunks are not affected.

    The delete-by-query body MUST contain a bool query with:
      - term filter for ingestion_record_id matching the target record
      - term filter for company_id matching the company scope

    This guarantees that deletion is scoped exclusively to one record's
    chunks within one company's index.

    **Validates: Requirements 12.5**
    """
    # Pick one record_id to delete from the generated set
    target_record_id = target_index.draw(st.sampled_from(record_ids))

    # Create a mock OpenSearch client
    mock_client = AsyncMock()

    # Mock delete_by_query to return a response indicating chunks were deleted
    deleted_count = target_index.draw(st.integers(min_value=0, max_value=50))
    mock_client.delete_by_query = AsyncMock(
        return_value={"deleted": deleted_count}
    )

    # Create the LiteratureIndexManager with the mock client
    manager = LiteratureIndexManager(
        opensearch_client=mock_client,
        embedding_dimension=1024,
    )

    # Call delete_record_chunks for the target record
    result = await manager.delete_record_chunks(
        company_id=company_id,
        ingestion_record_id=target_record_id,
    )

    # Assert the returned count matches what OpenSearch reported
    assert result == deleted_count, (
        f"Expected delete_record_chunks to return {deleted_count}, "
        f"got {result}."
    )

    # Verify delete_by_query was called exactly once
    mock_client.delete_by_query.assert_called_once()

    # Extract the actual call arguments
    call_kwargs = mock_client.delete_by_query.call_args
    actual_index = call_kwargs.kwargs.get("index") or call_kwargs[1].get("index")
    actual_body = call_kwargs.kwargs.get("body") or call_kwargs[1].get("body")

    # If positional args were used, check those too
    if actual_index is None and call_kwargs.args:
        actual_index = call_kwargs.kwargs.get("index")
    if actual_body is None and call_kwargs.args:
        actual_body = call_kwargs.kwargs.get("body")

    # Re-extract using the standard call pattern
    _, kwargs = mock_client.delete_by_query.call_args
    actual_index = kwargs["index"]
    actual_body = kwargs["body"]

    # Verify the index targets the correct company
    expected_index = f"literature-embeddings-{company_id}"
    assert actual_index == expected_index, (
        f"delete_by_query targeted index '{actual_index}', "
        f"expected '{expected_index}'."
    )

    # Verify the query body contains the correct filters
    query = actual_body["query"]
    assert "bool" in query, (
        f"Expected a bool query for delete_by_query, got: {query}"
    )

    must_clauses = query["bool"]["must"]
    assert isinstance(must_clauses, list), (
        f"Expected 'must' to be a list, got: {type(must_clauses)}"
    )

    # Extract term filters from the must clauses
    term_filters = {}
    for clause in must_clauses:
        if "term" in clause:
            for field, value in clause["term"].items():
                term_filters[field] = value

    # Verify ingestion_record_id filter matches the TARGET record only
    assert "ingestion_record_id" in term_filters, (
        f"delete_by_query missing ingestion_record_id filter. "
        f"Clauses: {must_clauses}"
    )
    assert term_filters["ingestion_record_id"] == target_record_id, (
        f"delete_by_query filter has ingestion_record_id="
        f"{term_filters['ingestion_record_id']}, expected {target_record_id}."
    )

    # Verify company_id filter is present (defense-in-depth)
    assert "company_id" in term_filters, (
        f"delete_by_query missing company_id filter. "
        f"Clauses: {must_clauses}"
    )
    assert term_filters["company_id"] == company_id, (
        f"delete_by_query filter has company_id="
        f"{term_filters['company_id']}, expected {company_id}."
    )

    # Verify refresh=True is passed (ensures consistency after delete)
    assert kwargs.get("refresh") is True, (
        f"delete_by_query should use refresh=True, got: {kwargs.get('refresh')}"
    )


@settings(max_examples=100)
@given(
    company_id=st_company_id,
    record_ids=st_distinct_record_ids(),
)
@pytest.mark.asyncio
async def test_deletion_does_not_affect_other_records(
    company_id: int,
    record_ids: list[int],
) -> None:
    """When delete_record_chunks is called for one record_id, the query body
    references ONLY that record_id. Other record_ids in the same index are
    never mentioned in the delete filter, guaranteeing isolation.

    For each record_id in the set, calling delete_record_chunks produces a
    query that mentions exactly that record_id and no other.

    **Validates: Requirements 12.5**
    """
    mock_client = AsyncMock()
    mock_client.delete_by_query = AsyncMock(return_value={"deleted": 5})

    manager = LiteratureIndexManager(
        opensearch_client=mock_client,
        embedding_dimension=1024,
    )

    # Delete each record individually and verify isolation
    for target_record_id in record_ids:
        mock_client.delete_by_query.reset_mock()

        await manager.delete_record_chunks(
            company_id=company_id,
            ingestion_record_id=target_record_id,
        )

        # Extract the query body
        _, kwargs = mock_client.delete_by_query.call_args
        body = kwargs["body"]
        must_clauses = body["query"]["bool"]["must"]

        # Collect all ingestion_record_id values referenced in the query
        referenced_record_ids = []
        for clause in must_clauses:
            if "term" in clause and "ingestion_record_id" in clause["term"]:
                referenced_record_ids.append(clause["term"]["ingestion_record_id"])

        # Only the target record_id should appear
        assert referenced_record_ids == [target_record_id], (
            f"Expected only record_id {target_record_id} in delete query, "
            f"but found: {referenced_record_ids}. "
            f"Other records in set: {[r for r in record_ids if r != target_record_id]}"
        )
