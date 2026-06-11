"""Property-based test: Screening Protocol serialization round-trip.

Property 1: Screening Protocol serialization round-trip
For any valid ScreeningProtocolResponseSchema object with random PICO criteria
(0–2000 chars each), inclusion criteria (0–20 patterns, 1–500 chars),
exclusion criteria (0–20 patterns), and metadata, serializing to JSON and
deserializing back via Pydantic produces identical field values.

This ensures no data loss during serialization/deserialization.

**Validates: Requirements 2.1, 2.7, 15.2**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.review.schemas.protocol import (
    PICOCriteriaSchema,
    ScreeningProtocolResponseSchema,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# PICO criteria: optional strings 0–2000 characters
PICO_TEXT = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Z"),
            min_codepoint=32,
            max_codepoint=126,
        ),
        min_size=0,
        max_size=2000,
    ),
)

# Inclusion/exclusion criterion strings: 1–500 chars each
CRITERION_TEXT = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=1,
    max_size=500,
).filter(lambda s: len(s.strip()) > 0)

# Criteria lists: 0–20 items
INCLUSION_CRITERIA = st.lists(CRITERION_TEXT, min_size=0, max_size=20)
EXCLUSION_CRITERIA = st.lists(CRITERION_TEXT, min_size=0, max_size=20)

# Protocol name: 1–200 chars
PROTOCOL_NAME = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "P", "S"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=1,
    max_size=200,
).filter(lambda s: len(s.strip()) > 0)

# Optional description: up to 5000 chars
PROTOCOL_DESCRIPTION = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S", "Z"),
            min_codepoint=32,
            max_codepoint=126,
        ),
        min_size=0,
        max_size=500,  # Keep smaller for speed; property still holds
    ),
)

# Status values
PROTOCOL_STATUS = st.sampled_from(["draft", "active", "archived"])

# ISO-8601 date strings (YYYY-MM-DD)
ISO_DATE = st.one_of(
    st.none(),
    st.dates().map(lambda d: d.isoformat()),
)

# Optional publication types
PUBLICATION_TYPES = st.one_of(
    st.none(),
    st.lists(
        st.sampled_from(["journal_article", "conference_paper", "review", "meta_analysis", "book_chapter"]),
        min_size=1,
        max_size=5,
    ),
)

# Optional language codes (ISO 639-1)
LANGUAGE_CODES = st.one_of(
    st.none(),
    st.lists(
        st.sampled_from(["en", "de", "fr", "es", "ja", "zh", "pt", "it"]),
        min_size=1,
        max_size=4,
    ),
)

# Timestamps with timezone
AWARE_DATETIME = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)


@st.composite
def pico_criteria_strategy(draw: st.DrawFn) -> PICOCriteriaSchema:
    """Generate a valid PICOCriteriaSchema with random field values."""
    return PICOCriteriaSchema(
        population=draw(PICO_TEXT),
        intervention=draw(PICO_TEXT),
        comparison=draw(PICO_TEXT),
        outcome=draw(PICO_TEXT),
    )


@st.composite
def screening_protocol_response_strategy(draw: st.DrawFn) -> dict:
    """Generate a valid ScreeningProtocolResponseSchema data dict.

    Returns the raw dict so we can construct the schema object from it,
    simulating how the response would be built from database data.
    """
    return {
        "id": draw(st.integers(min_value=1, max_value=2**31)),
        "company_id": draw(st.integers(min_value=1, max_value=2**31)),
        "name": draw(PROTOCOL_NAME),
        "description": draw(PROTOCOL_DESCRIPTION),
        "pico_criteria": draw(pico_criteria_strategy()),
        "inclusion_criteria": draw(INCLUSION_CRITERIA),
        "exclusion_criteria": draw(EXCLUSION_CRITERIA),
        "publication_date_from": draw(ISO_DATE),
        "publication_date_to": draw(ISO_DATE),
        "allowed_publication_types": draw(PUBLICATION_TYPES),
        "allowed_languages": draw(LANGUAGE_CODES),
        "version": draw(st.integers(min_value=1, max_value=1000)),
        "status": draw(PROTOCOL_STATUS),
        "created_by": draw(st.integers(min_value=1, max_value=2**31)),
        "created_at": draw(AWARE_DATETIME),
        "updated_at": draw(AWARE_DATETIME),
    }


# ---------------------------------------------------------------------------
# Property 1: Serialization round-trip preserves all fields
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(data=screening_protocol_response_strategy())
def test_screening_protocol_serialization_roundtrip(data: dict) -> None:
    """For any valid ScreeningProtocolResponseSchema, serializing to JSON and
    deserializing back SHALL produce identical field values.

    This property ensures no data loss during serialization/deserialization
    of screening protocol responses.

    **Validates: Requirements 2.1, 2.7, 15.2**
    """
    # Step 1: Construct the schema object from data
    original = ScreeningProtocolResponseSchema(**data)

    # Step 2: Serialize to JSON string
    json_str = original.model_dump_json()

    # Step 3: Deserialize back from JSON
    restored = ScreeningProtocolResponseSchema.model_validate_json(json_str)

    # Step 4: Assert all fields are identical
    assert restored.id == original.id
    assert restored.company_id == original.company_id
    assert restored.name == original.name
    assert restored.description == original.description
    assert restored.version == original.version
    assert restored.status == original.status
    assert restored.created_by == original.created_by
    assert restored.created_at == original.created_at
    assert restored.updated_at == original.updated_at

    # PICO criteria
    assert restored.pico_criteria.population == original.pico_criteria.population
    assert restored.pico_criteria.intervention == original.pico_criteria.intervention
    assert restored.pico_criteria.comparison == original.pico_criteria.comparison
    assert restored.pico_criteria.outcome == original.pico_criteria.outcome

    # Criteria lists
    assert restored.inclusion_criteria == original.inclusion_criteria
    assert restored.exclusion_criteria == original.exclusion_criteria

    # Optional filtering fields
    assert restored.publication_date_from == original.publication_date_from
    assert restored.publication_date_to == original.publication_date_to
    assert restored.allowed_publication_types == original.allowed_publication_types
    assert restored.allowed_languages == original.allowed_languages


@settings(max_examples=100)
@given(data=screening_protocol_response_strategy())
def test_screening_protocol_model_dump_roundtrip(data: dict) -> None:
    """For any valid ScreeningProtocolResponseSchema, model_dump() followed by
    model_validate() SHALL produce an equivalent object.

    This tests the dict-based serialization path (e.g., for JSON API responses
    via FastAPI's jsonable_encoder).

    **Validates: Requirements 2.1, 2.7, 15.2**
    """
    # Step 1: Construct the schema object
    original = ScreeningProtocolResponseSchema(**data)

    # Step 2: Serialize to dict (mode="json" ensures JSON-compatible types)
    dumped = original.model_dump(mode="json")

    # Step 3: Reconstruct from dict
    restored = ScreeningProtocolResponseSchema.model_validate(dumped)

    # Step 4: Full equality check via model_dump comparison
    assert restored.model_dump(mode="json") == original.model_dump(mode="json")
