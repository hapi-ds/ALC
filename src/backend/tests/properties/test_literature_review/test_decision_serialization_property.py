"""Property-based test: Screening Decision persistence round-trip.

Property 2: Screening Decision persistence round-trip
For any valid ScreeningDecisionResponseSchema object with random verdict,
confidence, rationale, matched criteria arrays, human override fields, and
timestamps, serializing to JSON via model_dump_json() and deserializing back
via model_validate_json() SHALL produce identical field values.

This ensures no data loss during serialization/deserialization of screening
decision responses.

**Validates: Requirements 3.2**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.review.schemas.decision import (
    ScreeningDecisionResponseSchema,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Verdict values: include, exclude, uncertain
VERDICT = st.sampled_from(["include", "exclude", "uncertain"])

# Confidence: float 0.0–1.0
CONFIDENCE = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Rationale: 0–2000 chars (printable ASCII to avoid encoding edge cases)
RATIONALE = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=0,
    max_size=2000,
)

# Matched criteria arrays: 0–20 non-negative integers (criterion indices)
MATCHED_CRITERIA = st.lists(
    st.integers(min_value=0, max_value=19),
    min_size=0,
    max_size=20,
)

# Human verdict: optional include/exclude
HUMAN_VERDICT = st.one_of(
    st.none(),
    st.sampled_from(["include", "exclude"]),
)

# Human rationale: optional text up to 2000 chars
HUMAN_RATIONALE = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Z"),
            min_codepoint=32,
            max_codepoint=126,
        ),
        min_size=1,
        max_size=2000,
    ),
)

# Reviewer user ID: optional positive integer
REVIEWER_USER_ID = st.one_of(
    st.none(),
    st.integers(min_value=1, max_value=2**31),
)

# Timestamps with timezone
AWARE_DATETIME = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

# Optional override timestamp
OPTIONAL_DATETIME = st.one_of(st.none(), AWARE_DATETIME)


@st.composite
def screening_decision_response_strategy(draw: st.DrawFn) -> dict:
    """Generate a valid ScreeningDecisionResponseSchema data dict.

    Returns the raw dict so we can construct the schema object from it,
    simulating how the response would be built from database data.
    """
    # Draw human override fields together so they're logically consistent:
    # if human_verdict is set, human_rationale and reviewer should also be set
    human_verdict = draw(HUMAN_VERDICT)
    if human_verdict is not None:
        human_rationale = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N", "P", "S", "Z"),
                    min_codepoint=32,
                    max_codepoint=126,
                ),
                min_size=1,
                max_size=2000,
            )
        )
        reviewer_user_id = draw(st.integers(min_value=1, max_value=2**31))
        override_timestamp = draw(AWARE_DATETIME)
    else:
        human_rationale = draw(HUMAN_RATIONALE)
        reviewer_user_id = draw(REVIEWER_USER_ID)
        override_timestamp = draw(OPTIONAL_DATETIME)

    return {
        "id": draw(st.integers(min_value=1, max_value=2**31)),
        "screening_run_id": draw(st.integers(min_value=1, max_value=2**31)),
        "ingestion_record_id": draw(st.integers(min_value=1, max_value=2**31)),
        "verdict": draw(VERDICT),
        "confidence": draw(CONFIDENCE),
        "rationale": draw(RATIONALE),
        "matched_inclusion_criteria": draw(MATCHED_CRITERIA),
        "matched_exclusion_criteria": draw(MATCHED_CRITERIA),
        "human_verdict": human_verdict,
        "human_rationale": human_rationale,
        "reviewer_user_id": reviewer_user_id,
        "override_timestamp": override_timestamp,
        "created_at": draw(AWARE_DATETIME),
    }


# ---------------------------------------------------------------------------
# Property 2: Serialization round-trip preserves all fields
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=screening_decision_response_strategy())
def test_screening_decision_serialization_roundtrip(data: dict) -> None:
    """For any valid ScreeningDecisionResponseSchema, serializing to JSON via
    model_dump_json() and deserializing back via model_validate_json() SHALL
    produce identical field values.

    This property ensures no data loss during serialization/deserialization
    of screening decision responses.

    **Validates: Requirements 3.2**
    """
    # Step 1: Construct the schema object from data
    original = ScreeningDecisionResponseSchema(**data)

    # Step 2: Serialize to JSON string
    json_str = original.model_dump_json()

    # Step 3: Deserialize back from JSON
    restored = ScreeningDecisionResponseSchema.model_validate_json(json_str)

    # Step 4: Assert all fields are identical
    assert restored.id == original.id
    assert restored.screening_run_id == original.screening_run_id
    assert restored.ingestion_record_id == original.ingestion_record_id
    assert restored.verdict == original.verdict
    # Confidence within floating-point tolerance
    assert abs(restored.confidence - original.confidence) < 1e-6
    assert restored.rationale == original.rationale
    assert restored.matched_inclusion_criteria == original.matched_inclusion_criteria
    assert restored.matched_exclusion_criteria == original.matched_exclusion_criteria
    assert restored.human_verdict == original.human_verdict
    assert restored.human_rationale == original.human_rationale
    assert restored.reviewer_user_id == original.reviewer_user_id
    assert restored.override_timestamp == original.override_timestamp
    assert restored.created_at == original.created_at


@settings(max_examples=100)
@given(data=screening_decision_response_strategy())
def test_screening_decision_model_dump_roundtrip(data: dict) -> None:
    """For any valid ScreeningDecisionResponseSchema, model_dump() followed by
    model_validate() SHALL produce an equivalent object.

    This tests the dict-based serialization path (e.g., for JSON API responses
    via FastAPI's jsonable_encoder).

    **Validates: Requirements 3.2**
    """
    # Step 1: Construct the schema object
    original = ScreeningDecisionResponseSchema(**data)

    # Step 2: Serialize to dict (mode="json" ensures JSON-compatible types)
    dumped = original.model_dump(mode="json")

    # Step 3: Reconstruct from dict
    restored = ScreeningDecisionResponseSchema.model_validate(dumped)

    # Step 4: Full equality check via model_dump comparison
    assert restored.model_dump(mode="json") == original.model_dump(mode="json")
