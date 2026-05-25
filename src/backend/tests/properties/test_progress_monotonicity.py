"""Property-based tests for generation job progress monotonicity.

Tests Property 13 from the AI Document Generator (Template-Based) design document,
validating that generation job progress updates are monotonically non-decreasing.

Progress follows the pipeline phases:
    0 → 10 → 20 → (20-90 proportional to sections) → 95 → 100

Each update must be >= the previous value.

**Validates: Requirements 7.2**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md (Property 13)
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md (7.2)
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure logic: progress calculation functions (mirrors pipeline logic)
# ---------------------------------------------------------------------------


def compute_pipeline_progress_sequence(total_sections: int) -> list[int]:
    """Compute the full progress sequence for a generation pipeline.

    Mirrors the logic in TemplateDocumentGeneratorService.execute_generation_pipeline():
    - 0%: initial job creation
    - 10%: after template loading
    - 20%: after knowledge retrieval
    - 20-90%: proportional across sections (20 + int((idx+1)/total * 70))
    - 95%: after DOCX assembly
    - 100%: after storage & records

    Args:
        total_sections: Number of sections in the template (>= 1).

    Returns:
        Ordered list of progress percentages for the full pipeline.
    """
    progress_values: list[int] = []

    # Phase 0: Initial
    progress_values.append(0)

    # Phase 1: Template loading complete
    progress_values.append(10)

    # Phase 2: Knowledge retrieval complete
    progress_values.append(20)

    # Phase 3: Section-by-section generation (20% to 90%)
    for idx in range(total_sections):
        section_progress = 20 + int((idx + 1) / total_sections * 70)
        progress_values.append(section_progress)

    # Phase 4: DOCX assembly complete
    progress_values.append(95)

    # Phase 5: Storage & records complete
    progress_values.append(100)

    return progress_values


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_section_count(draw: st.DrawFn) -> int:
    """Generate a valid section count for a template.

    Templates can have 1 to 100 sections (practical upper bound).

    Returns:
        Integer section count between 1 and 100.
    """
    return draw(st.integers(min_value=1, max_value=100))


@st.composite
def st_partial_progress_scenario(draw: st.DrawFn) -> dict:
    """Generate a scenario where progress is updated at arbitrary pipeline phases.

    Simulates a pipeline that may stop at any phase (e.g., due to failure),
    producing a prefix of the full progress sequence.

    Returns:
        Dictionary with:
        - total_sections: number of template sections
        - stop_after_phase: how many progress updates to include (1 to full)
        - progress_sequence: the resulting progress values
    """
    total_sections = draw(st.integers(min_value=1, max_value=50))
    full_sequence = compute_pipeline_progress_sequence(total_sections)
    # Stop at any point in the sequence (at least 1 update)
    stop_after = draw(st.integers(min_value=1, max_value=len(full_sequence)))
    partial_sequence = full_sequence[:stop_after]

    return {
        "total_sections": total_sections,
        "stop_after_phase": stop_after,
        "progress_sequence": partial_sequence,
    }


# ---------------------------------------------------------------------------
# Property 13: Progress Monotonicity
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(total_sections=st_section_count())
def test_progress_sequence_is_monotonically_non_decreasing(
    total_sections: int,
) -> None:
    """For any number of template sections, the full progress sequence
    SHALL be monotonically non-decreasing (each value >= previous).

    **Validates: Requirements 7.2**
    """
    progress_sequence = compute_pipeline_progress_sequence(total_sections)

    for i in range(1, len(progress_sequence)):
        assert progress_sequence[i] >= progress_sequence[i - 1], (
            f"Progress decreased at index {i}: "
            f"{progress_sequence[i - 1]} → {progress_sequence[i]} "
            f"(total_sections={total_sections})"
        )


@settings(max_examples=25)
@given(total_sections=st_section_count())
def test_progress_starts_at_zero_and_ends_at_100(
    total_sections: int,
) -> None:
    """The progress sequence SHALL always start at 0 and end at 100.

    **Validates: Requirements 7.2**
    """
    progress_sequence = compute_pipeline_progress_sequence(total_sections)

    assert progress_sequence[0] == 0, (
        f"Progress does not start at 0: starts at {progress_sequence[0]}"
    )
    assert progress_sequence[-1] == 100, (
        f"Progress does not end at 100: ends at {progress_sequence[-1]}"
    )


@settings(max_examples=25)
@given(total_sections=st_section_count())
def test_progress_values_within_bounds(
    total_sections: int,
) -> None:
    """All progress values SHALL be within [0, 100].

    **Validates: Requirements 7.2**
    """
    progress_sequence = compute_pipeline_progress_sequence(total_sections)

    for i, value in enumerate(progress_sequence):
        assert 0 <= value <= 100, (
            f"Progress value {value} at index {i} is out of bounds [0, 100] "
            f"(total_sections={total_sections})"
        )


@settings(max_examples=25)
@given(scenario=st_partial_progress_scenario())
def test_partial_progress_is_monotonically_non_decreasing(
    scenario: dict,
) -> None:
    """Even when a pipeline stops early (e.g., failure), the partial
    progress sequence SHALL be monotonically non-decreasing.

    **Validates: Requirements 7.2**
    """
    progress_sequence = scenario["progress_sequence"]

    for i in range(1, len(progress_sequence)):
        assert progress_sequence[i] >= progress_sequence[i - 1], (
            f"Progress decreased at index {i}: "
            f"{progress_sequence[i - 1]} → {progress_sequence[i]} "
            f"(total_sections={scenario['total_sections']}, "
            f"stopped after {scenario['stop_after_phase']} updates)"
        )


@settings(max_examples=25)
@given(total_sections=st_section_count())
def test_section_progress_stays_within_20_to_90_range(
    total_sections: int,
) -> None:
    """Section-level progress updates (phase 3) SHALL produce values
    in the range [20, 90], maintaining monotonicity with the preceding
    knowledge retrieval phase (20%) and not exceeding the DOCX assembly
    phase (95%).

    **Validates: Requirements 7.2**
    """
    progress_sequence = compute_pipeline_progress_sequence(total_sections)

    # Section progress values are at indices 3 through 3+total_sections-1
    # (after 0, 10, 20 and before 95, 100)
    section_progress_values = progress_sequence[3 : 3 + total_sections]

    for i, value in enumerate(section_progress_values):
        # Section progress = 20 + int((idx+1)/total * 70)
        # Minimum: 20 + int(1/total * 70) >= 20 (for large total, floor → 0)
        # Maximum: 20 + int(total/total * 70) = 90
        assert value >= 20, (
            f"Section progress value {value} at section {i} is below 20 "
            f"(total_sections={total_sections})"
        )
        assert value <= 90, (
            f"Section progress value {value} at section {i} exceeds 90 "
            f"(total_sections={total_sections})"
        )


@settings(max_examples=25)
@given(total_sections=st_section_count())
def test_last_section_progress_is_exactly_90(
    total_sections: int,
) -> None:
    """The last section's progress SHALL be exactly 90%, ensuring a clean
    transition to the DOCX assembly phase at 95%.

    **Validates: Requirements 7.2**
    """
    progress_sequence = compute_pipeline_progress_sequence(total_sections)

    # The last section progress is at index 2 + total_sections
    # (indices: 0=0%, 1=10%, 2=20%, 3..2+total_sections=sections, then 95, 100)
    last_section_index = 2 + total_sections
    last_section_progress = progress_sequence[last_section_index]

    assert last_section_progress == 90, (
        f"Last section progress is {last_section_progress}, expected 90 "
        f"(total_sections={total_sections})"
    )
