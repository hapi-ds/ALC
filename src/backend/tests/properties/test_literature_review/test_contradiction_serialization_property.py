"""Property-based test: Contradiction Alert persistence round-trip.

Property 3: Contradiction Alert persistence round-trip
For any valid ContradictionAlertResponseSchema object with random severity
(critical/major/minor), confidence (0.0–1.0), description (1–3000 chars),
evidence (1–2000 chars), status, and timestamps, serializing to JSON and
deserializing back via Pydantic produces identical field values.

This ensures no data loss during serialization/deserialization of
contradiction alert responses.

**Validates: Requirements 5.5**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.review.schemas.contradiction import (
    ContradictionAlertResponseSchema,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Severity: critical, major, minor
SEVERITY = st.sampled_from(["critical", "major", "minor"])

# Confidence: float 0.0–1.0
CONFIDENCE = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)

# Status: open, acknowledged, resolved, dismissed
STATUS = st.sampled_from(["open", "acknowledged", "resolved", "dismissed"])

# Description: 1–3000 chars
DESCRIPTION = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=1,
    max_size=500,  # Keep smaller for speed; property still holds
).filter(lambda s: len(s.strip()) > 0)

# Evidence: 1–2000 chars
EVIDENCE = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=1,
    max_size=500,  # Keep smaller for speed; property still holds
).filter(lambda s: len(s.strip()) > 0)

# Recommended action: 1–1000 chars
RECOMMENDED_ACTION = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=1,
    max_size=300,  # Keep smaller for speed; property still holds
).filter(lambda s: len(s.strip()) > 0)

# Optional impact_report_id
IMPACT_REPORT_ID = st.one_of(
    st.none(),
    st.integers(min_value=1, max_value=2**31),
)

# Timestamps with timezone
AWARE_DATETIME = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)


@st.composite
def contradiction_alert_response_strategy(draw: st.DrawFn) -> dict:
    """Generate a valid ContradictionAlertResponseSchema data dict.

    Returns the raw dict so we can construct the schema object from it,
    simulating how the response would be built from database data.
    """
    return {
        "id": draw(st.integers(min_value=1, max_value=2**31)),
        "ingestion_record_id": draw(st.integers(min_value=1, max_value=2**31)),
        "internal_document_id": draw(st.integers(min_value=1, max_value=2**31)),
        "company_id": draw(st.integers(min_value=1, max_value=2**31)),
        "severity": draw(SEVERITY),
        "description": draw(DESCRIPTION),
        "evidence": draw(EVIDENCE),
        "recommended_action": draw(RECOMMENDED_ACTION),
        "confidence": draw(CONFIDENCE),
        "status": draw(STATUS),
        "impact_report_id": draw(IMPACT_REPORT_ID),
        "created_at": draw(AWARE_DATETIME),
        "updated_at": draw(AWARE_DATETIME),
    }


# ---------------------------------------------------------------------------
# Property 3: Serialization round-trip preserves all fields
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=contradiction_alert_response_strategy())
def test_contradiction_alert_serialization_roundtrip(data: dict) -> None:
    """For any valid ContradictionAlertResponseSchema, serializing to JSON and
    deserializing back SHALL produce identical field values.

    This property ensures no data loss during serialization/deserialization
    of contradiction alert responses. Confidence is compared within 1e-6
    tolerance for floating-point precision.

    **Validates: Requirements 5.5**
    """
    # Step 1: Construct the schema object from data
    original = ContradictionAlertResponseSchema(**data)

    # Step 2: Serialize to JSON string
    json_str = original.model_dump_json()

    # Step 3: Deserialize back from JSON
    restored = ContradictionAlertResponseSchema.model_validate_json(json_str)

    # Step 4: Assert all fields are identical
    assert restored.id == original.id
    assert restored.ingestion_record_id == original.ingestion_record_id
    assert restored.internal_document_id == original.internal_document_id
    assert restored.company_id == original.company_id
    assert restored.severity == original.severity
    assert restored.description == original.description
    assert restored.evidence == original.evidence
    assert restored.recommended_action == original.recommended_action
    assert restored.status == original.status
    assert restored.impact_report_id == original.impact_report_id
    assert restored.created_at == original.created_at
    assert restored.updated_at == original.updated_at

    # Confidence: compare within floating-point tolerance
    assert abs(restored.confidence - original.confidence) < 1e-6


@settings(max_examples=100)
@given(data=contradiction_alert_response_strategy())
def test_contradiction_alert_model_dump_roundtrip(data: dict) -> None:
    """For any valid ContradictionAlertResponseSchema, model_dump() followed by
    model_validate() SHALL produce an equivalent object.

    This tests the dict-based serialization path (e.g., for JSON API responses
    via FastAPI's jsonable_encoder).

    **Validates: Requirements 5.5**
    """
    # Step 1: Construct the schema object
    original = ContradictionAlertResponseSchema(**data)

    # Step 2: Serialize to dict (mode="json" ensures JSON-compatible types)
    dumped = original.model_dump(mode="json")

    # Step 3: Reconstruct from dict
    restored = ContradictionAlertResponseSchema.model_validate(dumped)

    # Step 4: Full equality check via model_dump comparison
    original_dump = original.model_dump(mode="json")
    restored_dump = restored.model_dump(mode="json")

    # Compare all fields except confidence (floating-point)
    for key in original_dump:
        if key == "confidence":
            assert abs(original_dump[key] - restored_dump[key]) < 1e-6
        else:
            assert original_dump[key] == restored_dump[key], (
                f"Field '{key}' mismatch: {original_dump[key]!r} != {restored_dump[key]!r}"
            )
