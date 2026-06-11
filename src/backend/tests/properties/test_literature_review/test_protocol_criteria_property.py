"""Property-based tests for Screening Protocol at-least-one-criterion validation.

Property 16: Protocol requires at least one criterion
For any protocol creation payload, the system SHALL reject the payload with a
ValidationError when ALL PICO fields are empty/None AND both inclusion and
exclusion criteria lists are empty. Conversely, payloads with at least one
non-empty PICO field OR at least one criterion SHALL be accepted.

**Validates: Requirements 2.10**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from pydantic import ValidationError

from alcoabase.literature.review.schemas.protocol import (
    PICOCriteriaSchema,
    ScreeningProtocolCreateSchema,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for valid criterion strings (1–500 chars)
_criterion_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=100,
)

# Strategy for non-empty PICO field values (1–2000 chars, non-whitespace-only)
_pico_field_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip() != "")

# Strategy for valid protocol names (1–200 chars)
_name_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")


# ---------------------------------------------------------------------------
# Property 16: Rejection — All empty PICO + empty criteria lists
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    name=_name_strategy,
    population=st.just(None) | st.just("") | st.just("   "),
    intervention=st.just(None) | st.just("") | st.just("   "),
    comparison=st.just(None) | st.just("") | st.just("   "),
    outcome=st.just(None) | st.just("") | st.just("   "),
)
def test_rejects_payload_with_no_criteria(
    name: str,
    population: str | None,
    intervention: str | None,
    comparison: str | None,
    outcome: str | None,
) -> None:
    """ScreeningProtocolCreateSchema SHALL reject payloads where all PICO
    fields are empty/None/whitespace AND both criteria lists are empty.

    **Validates: Requirements 2.10**
    """
    with pytest.raises(ValidationError) as exc_info:
        ScreeningProtocolCreateSchema(
            name=name,
            pico_criteria=PICOCriteriaSchema(
                population=population,
                intervention=intervention,
                comparison=comparison,
                outcome=outcome,
            ),
            inclusion_criteria=[],
            exclusion_criteria=[],
        )
    # Verify the error message references the criterion requirement
    errors = exc_info.value.errors()
    error_messages = " ".join(str(e.get("msg", "")) for e in errors)
    assert "criterion" in error_messages.lower()


# ---------------------------------------------------------------------------
# Property 16: Acceptance — At least one non-empty PICO field
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    name=_name_strategy,
    pico_field=_pico_field_strategy,
    field_index=st.integers(min_value=0, max_value=3),
)
def test_accepts_payload_with_one_pico_field(
    name: str,
    pico_field: str,
    field_index: int,
) -> None:
    """ScreeningProtocolCreateSchema SHALL accept payloads with at least one
    non-empty PICO field, even when both criteria lists are empty.

    **Validates: Requirements 2.10**
    """
    pico_fields = [None, None, None, None]
    pico_fields[field_index] = pico_field

    schema = ScreeningProtocolCreateSchema(
        name=name,
        pico_criteria=PICOCriteriaSchema(
            population=pico_fields[0],
            intervention=pico_fields[1],
            comparison=pico_fields[2],
            outcome=pico_fields[3],
        ),
        inclusion_criteria=[],
        exclusion_criteria=[],
    )
    assert schema.name == name


# ---------------------------------------------------------------------------
# Property 16: Acceptance — At least one inclusion criterion
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    name=_name_strategy,
    criteria=st.lists(_criterion_strategy, min_size=1, max_size=5),
)
def test_accepts_payload_with_inclusion_criteria(
    name: str,
    criteria: list[str],
) -> None:
    """ScreeningProtocolCreateSchema SHALL accept payloads with at least one
    inclusion criterion, even when all PICO fields are None.

    **Validates: Requirements 2.10**
    """
    schema = ScreeningProtocolCreateSchema(
        name=name,
        pico_criteria=PICOCriteriaSchema(
            population=None,
            intervention=None,
            comparison=None,
            outcome=None,
        ),
        inclusion_criteria=criteria,
        exclusion_criteria=[],
    )
    assert len(schema.inclusion_criteria) == len(criteria)


# ---------------------------------------------------------------------------
# Property 16: Acceptance — At least one exclusion criterion
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    name=_name_strategy,
    criteria=st.lists(_criterion_strategy, min_size=1, max_size=5),
)
def test_accepts_payload_with_exclusion_criteria(
    name: str,
    criteria: list[str],
) -> None:
    """ScreeningProtocolCreateSchema SHALL accept payloads with at least one
    exclusion criterion, even when all PICO fields are None and inclusion
    criteria are empty.

    **Validates: Requirements 2.10**
    """
    schema = ScreeningProtocolCreateSchema(
        name=name,
        pico_criteria=PICOCriteriaSchema(
            population=None,
            intervention=None,
            comparison=None,
            outcome=None,
        ),
        inclusion_criteria=[],
        exclusion_criteria=criteria,
    )
    assert len(schema.exclusion_criteria) == len(criteria)


# ---------------------------------------------------------------------------
# Property 16: Acceptance — Combined: any criterion present suffices
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    name=_name_strategy,
    population=st.none() | _pico_field_strategy,
    intervention=st.none() | _pico_field_strategy,
    comparison=st.none() | _pico_field_strategy,
    outcome=st.none() | _pico_field_strategy,
    inclusion=st.lists(_criterion_strategy, min_size=0, max_size=3),
    exclusion=st.lists(_criterion_strategy, min_size=0, max_size=3),
)
def test_accepts_payload_with_any_criterion_present(
    name: str,
    population: str | None,
    intervention: str | None,
    comparison: str | None,
    outcome: str | None,
    inclusion: list[str],
    exclusion: list[str],
) -> None:
    """ScreeningProtocolCreateSchema SHALL accept any payload that has at least
    one non-empty PICO field OR at least one inclusion/exclusion criterion.

    **Validates: Requirements 2.10**
    """
    # Check if at least one criterion is present
    pico_has_value = any(
        v is not None and v.strip() != ""
        for v in (population, intervention, comparison, outcome)
    )
    has_inclusion = len(inclusion) > 0
    has_exclusion = len(exclusion) > 0

    has_any_criterion = pico_has_value or has_inclusion or has_exclusion

    if has_any_criterion:
        # Should succeed
        schema = ScreeningProtocolCreateSchema(
            name=name,
            pico_criteria=PICOCriteriaSchema(
                population=population,
                intervention=intervention,
                comparison=comparison,
                outcome=outcome,
            ),
            inclusion_criteria=inclusion,
            exclusion_criteria=exclusion,
        )
        assert schema.name == name
    else:
        # Should fail
        with pytest.raises(ValidationError):
            ScreeningProtocolCreateSchema(
                name=name,
                pico_criteria=PICOCriteriaSchema(
                    population=population,
                    intervention=intervention,
                    comparison=comparison,
                    outcome=outcome,
                ),
                inclusion_criteria=inclusion,
                exclusion_criteria=exclusion,
            )
