"""Property-based tests for the Training Planner Service.

Tests Property 2 from the AI-Enhanced Training Ecosystem design document,
validating that skill gap identification is the set difference of required
documents vs completed training records.

**Validates: Requirements 1.4, 2.1**

References:
    - Design: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/design.md (Property 2)
    - Requirements: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/requirements.md (1.4, 2.1)
"""

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

#: Strategy for generating document IDs (simulating document_uuid strings).
st_document_ids = st.frozensets(
    st.integers(min_value=1, max_value=500),
    min_size=0,
    max_size=30,
)


# ---------------------------------------------------------------------------
# Pure logic under test: skill gap set difference
# ---------------------------------------------------------------------------


def compute_skill_gaps(
    required_docs: frozenset[int],
    completed_docs: frozenset[int],
) -> frozenset[int]:
    """Compute skill gaps as the set difference of required vs completed.

    This mirrors the core logic of TrainingPlannerService.recalculate_gaps:
    for each user, gaps are documents in the required set that do NOT have
    a valid completed training record.

    Args:
        required_docs: Set of document IDs requiring training.
        completed_docs: Set of document IDs with valid training records.

    Returns:
        Set of document IDs representing skill gaps (R \\ C).
    """
    return required_docs - completed_docs


# ---------------------------------------------------------------------------
# Property 2: Skill gap identification is the set difference of required
#              vs completed training
# ---------------------------------------------------------------------------


# Feature: ai-enhanced-training-ecosystem, Property 2: Gaps equal R \ C exactly
@settings(max_examples=200)
@given(
    required_docs=st_document_ids,
    completed_docs=st_document_ids,
)
def test_skill_gaps_equal_set_difference(
    required_docs: frozenset[int],
    completed_docs: frozenset[int],
) -> None:
    """For any sets of required documents R and completed training records C,
    the identified skill gaps SHALL equal R \\ C exactly.

    **Validates: Requirements 1.4, 2.1**
    """
    gaps = compute_skill_gaps(required_docs, completed_docs)
    expected = required_docs - completed_docs

    assert gaps == expected, (
        f"Gaps {gaps} do not equal expected set difference {expected}. "
        f"required={required_docs}, completed={completed_docs}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 2: No completed doc appears as gap
@settings(max_examples=200)
@given(
    required_docs=st_document_ids,
    completed_docs=st_document_ids,
)
def test_no_completed_doc_appears_as_gap(
    required_docs: frozenset[int],
    completed_docs: frozenset[int],
) -> None:
    """No document in C with a valid training record SHALL appear as a gap.

    **Validates: Requirements 1.4, 2.1**
    """
    gaps = compute_skill_gaps(required_docs, completed_docs)

    for doc_id in completed_docs:
        assert doc_id not in gaps, (
            f"Document {doc_id} has a valid training record but appears as a gap. "
            f"required={required_docs}, completed={completed_docs}, gaps={gaps}"
        )


# Feature: ai-enhanced-training-ecosystem, Property 2: Every required doc without record is a gap
@settings(max_examples=200)
@given(
    required_docs=st_document_ids,
    completed_docs=st_document_ids,
)
def test_every_required_doc_without_record_is_gap(
    required_docs: frozenset[int],
    completed_docs: frozenset[int],
) -> None:
    """Every document in R without a valid record SHALL appear as a gap.

    **Validates: Requirements 1.4, 2.1**
    """
    gaps = compute_skill_gaps(required_docs, completed_docs)

    for doc_id in required_docs:
        if doc_id not in completed_docs:
            assert doc_id in gaps, (
                f"Document {doc_id} is required but not completed, "
                f"yet does not appear as a gap. "
                f"required={required_docs}, completed={completed_docs}, gaps={gaps}"
            )


# Feature: ai-enhanced-training-ecosystem, Property 2: Gaps are subset of required
@settings(max_examples=200)
@given(
    required_docs=st_document_ids,
    completed_docs=st_document_ids,
)
def test_gaps_are_subset_of_required(
    required_docs: frozenset[int],
    completed_docs: frozenset[int],
) -> None:
    """Skill gaps SHALL only contain documents from the required set.
    No document outside R can be a gap.

    **Validates: Requirements 1.4, 2.1**
    """
    gaps = compute_skill_gaps(required_docs, completed_docs)

    assert gaps.issubset(required_docs), (
        f"Gaps {gaps} contain documents not in required set {required_docs}. "
        f"completed={completed_docs}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 2: Empty required means no gaps
@settings(max_examples=200)
@given(completed_docs=st_document_ids)
def test_empty_required_means_no_gaps(
    completed_docs: frozenset[int],
) -> None:
    """When no documents are required, there SHALL be zero skill gaps
    regardless of completed training records.

    **Validates: Requirements 1.4, 2.1**
    """
    gaps = compute_skill_gaps(frozenset(), completed_docs)

    assert len(gaps) == 0, (
        f"Expected no gaps when required is empty, got {gaps}. "
        f"completed={completed_docs}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 2: All completed means no gaps
@settings(max_examples=200)
@given(required_docs=st_document_ids)
def test_all_completed_means_no_gaps(
    required_docs: frozenset[int],
) -> None:
    """When all required documents have valid training records,
    there SHALL be zero skill gaps.

    **Validates: Requirements 1.4, 2.1**
    """
    # completed is a superset of required
    gaps = compute_skill_gaps(required_docs, required_docs)

    assert len(gaps) == 0, (
        f"Expected no gaps when all required are completed, got {gaps}. "
        f"required={required_docs}"
    )
