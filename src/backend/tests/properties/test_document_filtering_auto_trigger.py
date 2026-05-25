"""Property-based tests for document filtering in auto-trigger logic.

Property 5: Document Filtering for Auto-Trigger

For any DocumentVersion creation event where the associated document has
current_status "Draft" or is_csv_validation_record is true, the
Impact_Analysis_Engine SHALL NOT enqueue an impact analysis task. For all
other statuses and non-CSV documents, a task SHALL be enqueued.

**Validates: Requirements 2.3**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/impact_analysis_trigger.py (planned)
"""

from __future__ import annotations

from dataclasses import dataclass

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Domain model for auto-trigger filtering (pure logic under test)
# ---------------------------------------------------------------------------

# All valid document statuses in the system
ALL_STATUSES = ["Draft", "Active", "InReview", "Approved", "InTraining", "Retired"]

# Statuses that should be excluded from auto-trigger
EXCLUDED_STATUSES = frozenset({"Draft"})

# Statuses that should trigger impact analysis (all except Draft)
TRIGGERABLE_STATUSES = frozenset(ALL_STATUSES) - EXCLUDED_STATUSES


@dataclass(frozen=True)
class DocumentContext:
    """Context about a document when a new version is created.

    Attributes:
        current_status: The document's workflow status at version creation time.
        is_csv_validation_record: Whether the document is a CSV validation record.
    """

    current_status: str
    is_csv_validation_record: bool


def should_enqueue_impact_analysis(context: DocumentContext) -> bool:
    """Determine whether to enqueue an impact analysis task for a version event.

    Implements the filtering logic from Requirement 2.3:
    - Documents with current_status "Draft" SHALL NOT trigger analysis.
    - Documents with is_csv_validation_record=True SHALL NOT trigger analysis.
    - All other documents SHALL trigger analysis.

    Args:
        context: The document context at the time of version creation.

    Returns:
        True if an impact analysis task should be enqueued, False otherwise.
    """
    if context.current_status in EXCLUDED_STATUSES:
        return False
    if context.is_csv_validation_record:
        return False
    return True


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_status() -> st.SearchStrategy[str]:
    """Generate a random valid document status."""
    return st.sampled_from(ALL_STATUSES)


def st_excluded_status() -> st.SearchStrategy[str]:
    """Generate a status that should block auto-trigger (Draft)."""
    return st.just("Draft")


def st_triggerable_status() -> st.SearchStrategy[str]:
    """Generate a status that should allow auto-trigger."""
    return st.sampled_from(sorted(TRIGGERABLE_STATUSES))


@st.composite
def st_document_context(
    draw: st.DrawFn,
    status: st.SearchStrategy[str] | None = None,
    is_csv: st.SearchStrategy[bool] | None = None,
) -> DocumentContext:
    """Generate a DocumentContext with configurable status and CSV flag.

    Args:
        draw: Hypothesis draw function.
        status: Strategy for status value. Defaults to any valid status.
        is_csv: Strategy for is_csv_validation_record. Defaults to random bool.

    Returns:
        A DocumentContext instance.
    """
    if status is None:
        status = st_status()
    if is_csv is None:
        is_csv = st.booleans()

    return DocumentContext(
        current_status=draw(status),
        is_csv_validation_record=draw(is_csv),
    )


# ---------------------------------------------------------------------------
# Property 5: Draft documents never trigger analysis
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(context=st_document_context(status=st_excluded_status()))
def test_draft_documents_never_trigger_analysis(context: DocumentContext) -> None:
    """For any DocumentVersion creation event where the associated document
    has current_status "Draft", the Impact_Analysis_Engine SHALL NOT enqueue
    an impact analysis task, regardless of the is_csv_validation_record flag.

    **Validates: Requirements 2.3**
    """
    result = should_enqueue_impact_analysis(context)
    assert result is False, (
        f"Draft document should NOT trigger analysis, "
        f"but got trigger=True (is_csv={context.is_csv_validation_record})"
    )


# ---------------------------------------------------------------------------
# Property 5: CSV validation records never trigger analysis
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(context=st_document_context(is_csv=st.just(True)))
def test_csv_validation_records_never_trigger_analysis(context: DocumentContext) -> None:
    """For any DocumentVersion creation event where the associated document
    has is_csv_validation_record=True, the Impact_Analysis_Engine SHALL NOT
    enqueue an impact analysis task, regardless of the current_status.

    **Validates: Requirements 2.3**
    """
    result = should_enqueue_impact_analysis(context)
    assert result is False, (
        f"CSV validation record should NOT trigger analysis, "
        f"but got trigger=True (status={context.current_status!r})"
    )


# ---------------------------------------------------------------------------
# Property 5: Non-Draft, non-CSV documents always trigger analysis
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(context=st_document_context(status=st_triggerable_status(), is_csv=st.just(False)))
def test_non_draft_non_csv_documents_always_trigger(context: DocumentContext) -> None:
    """For any DocumentVersion creation event where the associated document
    has a status other than "Draft" AND is_csv_validation_record is False,
    the Impact_Analysis_Engine SHALL enqueue an impact analysis task.

    **Validates: Requirements 2.3**
    """
    result = should_enqueue_impact_analysis(context)
    assert result is True, (
        f"Non-Draft, non-CSV document should trigger analysis, "
        f"but got trigger=False (status={context.current_status!r})"
    )


# ---------------------------------------------------------------------------
# Property 5: Filtering is a complete partition
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(context=st_document_context())
def test_filtering_is_deterministic_and_complete(context: DocumentContext) -> None:
    """For any document context, the filtering decision SHALL be deterministic:
    the result is always True or False, and calling the function multiple times
    with the same input produces the same result.

    **Validates: Requirements 2.3**
    """
    result1 = should_enqueue_impact_analysis(context)
    result2 = should_enqueue_impact_analysis(context)

    assert result1 is result2, "Filtering must be deterministic"
    assert isinstance(result1, bool), "Result must be a boolean"


# ---------------------------------------------------------------------------
# Property 5: Exclusion conditions are independent (either blocks)
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    status=st_status(),
    is_csv=st.booleans(),
)
def test_either_exclusion_condition_blocks_trigger(status: str, is_csv: bool) -> None:
    """For any document, if EITHER the status is "Draft" OR
    is_csv_validation_record is True, the trigger SHALL be blocked.
    Only when BOTH conditions are non-blocking (status != Draft AND
    is_csv == False) SHALL the trigger proceed.

    **Validates: Requirements 2.3**
    """
    context = DocumentContext(current_status=status, is_csv_validation_record=is_csv)
    result = should_enqueue_impact_analysis(context)

    is_draft = status in EXCLUDED_STATUSES
    should_block = is_draft or is_csv
    expected = not should_block

    assert result == expected, (
        f"Expected trigger={expected} for status={status!r}, is_csv={is_csv}, "
        f"but got trigger={result}"
    )


# ---------------------------------------------------------------------------
# Property 5: All triggerable statuses are non-Draft
# ---------------------------------------------------------------------------


def test_triggerable_statuses_exclude_draft() -> None:
    """The set of triggerable statuses SHALL NOT contain "Draft".

    **Validates: Requirements 2.3**
    """
    assert "Draft" not in TRIGGERABLE_STATUSES
    assert TRIGGERABLE_STATUSES == {"Active", "InReview", "Approved", "InTraining", "Retired"}


def test_excluded_statuses_contains_only_draft() -> None:
    """The set of excluded statuses SHALL contain exactly "Draft".

    **Validates: Requirements 2.3**
    """
    assert EXCLUDED_STATUSES == frozenset({"Draft"})


# ---------------------------------------------------------------------------
# Property 5: Batch filtering preserves correct counts
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(contexts=st.lists(st_document_context(), min_size=1, max_size=30))
def test_batch_filtering_count_matches_individual(contexts: list[DocumentContext]) -> None:
    """For any batch of document version events, the count of triggered
    analyses SHALL equal the count of documents that are both non-Draft
    and non-CSV.

    **Validates: Requirements 2.3**
    """
    triggered = [ctx for ctx in contexts if should_enqueue_impact_analysis(ctx)]

    expected_count = sum(
        1
        for ctx in contexts
        if ctx.current_status not in EXCLUDED_STATUSES
        and not ctx.is_csv_validation_record
    )

    assert len(triggered) == expected_count
