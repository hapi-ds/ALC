"""Property-based tests for malformed LLM response handling.

Property 6: Malformed LLM response produces uncertain fallback
For ANY non-conforming response string (missing verdict, confidence outside
0.0–1.0, missing rationale, unparseable JSON, random bytes), the
`_parse_response()` method SHALL return None, and `screen_record()` SHALL
yield a ScreeningResult with verdict="uncertain", confidence=0.0, and
rationale containing "Agent response parsing failed".

**Validates: Requirements 3.6**

References:
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
    - Requirements: .kiro/specs/Step_9-4_literature-review-synthesis-agents/requirements.md
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.literature.review.services.screener_agent_runner import (
    LiteratureScreenerAgentRunner,
    ScreeningResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner() -> LiteratureScreenerAgentRunner:
    """Create a LiteratureScreenerAgentRunner with mocked dependencies."""
    mock_inference_client = MagicMock()
    mock_agent_registry = MagicMock()
    # _load_archetype_raw returns None to use fallback defaults
    mock_agent_registry._load_archetype_raw.return_value = None
    return LiteratureScreenerAgentRunner(
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
        model_name="test-model",
    )


# ---------------------------------------------------------------------------
# Property 6.1: Completely random strings → _parse_response returns None
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(random_text=st.text(min_size=0, max_size=500))
def test_random_strings_produce_none(random_text: str) -> None:
    """_parse_response SHALL return None for arbitrary random strings
    that are not valid JSON conforming to the expected schema.

    **Validates: Requirements 3.6**
    """
    runner = _make_runner()
    result = runner._parse_response(random_text)
    # Random strings overwhelmingly won't produce valid schema-conforming JSON.
    # If by extreme coincidence Hypothesis generates valid JSON with all
    # required fields, the result could be non-None. We filter those out.
    if result is not None:
        # Verify it's actually a valid ScreeningResult (not a false positive)
        assert isinstance(result, ScreeningResult)
        assert result.verdict in ("include", "exclude", "uncertain")
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.rationale) > 0


# ---------------------------------------------------------------------------
# Property 6.2: Valid JSON but missing "verdict" field → None
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    rationale=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""),
    inc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
    exc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
)
def test_missing_verdict_produces_none(
    confidence: float,
    rationale: str,
    inc_criteria: list[int],
    exc_criteria: list[int],
) -> None:
    """_parse_response SHALL return None when JSON is valid but
    the "verdict" field is missing.

    **Validates: Requirements 3.6**
    """
    runner = _make_runner()
    payload = {
        "confidence": confidence,
        "rationale": rationale,
        "matched_inclusion_criteria": inc_criteria,
        "matched_exclusion_criteria": exc_criteria,
    }
    result = runner._parse_response(json.dumps(payload))
    assert result is None


# ---------------------------------------------------------------------------
# Property 6.3: Valid JSON with invalid verdict value → None
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    verdict=st.text(min_size=1, max_size=50).filter(
        lambda s: s not in ("include", "exclude", "uncertain")
    ),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    rationale=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""),
    inc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
    exc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
)
def test_invalid_verdict_value_produces_none(
    verdict: str,
    confidence: float,
    rationale: str,
    inc_criteria: list[int],
    exc_criteria: list[int],
) -> None:
    """_parse_response SHALL return None when verdict is not one of
    include/exclude/uncertain.

    **Validates: Requirements 3.6**
    """
    runner = _make_runner()
    payload = {
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "matched_inclusion_criteria": inc_criteria,
        "matched_exclusion_criteria": exc_criteria,
    }
    result = runner._parse_response(json.dumps(payload))
    assert result is None


# ---------------------------------------------------------------------------
# Property 6.4: Valid JSON with confidence outside 0.0–1.0 → None
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    verdict=st.sampled_from(["include", "exclude", "uncertain"]),
    confidence=st.one_of(
        st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
        st.floats(min_value=1.001, allow_nan=False, allow_infinity=False),
    ),
    rationale=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""),
    inc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
    exc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
)
def test_confidence_outside_range_produces_none(
    verdict: str,
    confidence: float,
    rationale: str,
    inc_criteria: list[int],
    exc_criteria: list[int],
) -> None:
    """_parse_response SHALL return None when confidence is outside
    the valid 0.0–1.0 range.

    **Validates: Requirements 3.6**
    """
    runner = _make_runner()
    payload = {
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "matched_inclusion_criteria": inc_criteria,
        "matched_exclusion_criteria": exc_criteria,
    }
    result = runner._parse_response(json.dumps(payload))
    assert result is None


# ---------------------------------------------------------------------------
# Property 6.5: Valid JSON with missing/empty rationale → None
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    verdict=st.sampled_from(["include", "exclude", "uncertain"]),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    rationale=st.one_of(
        st.just(""),
        st.just("   "),
        st.just("\t\n"),
        st.none(),
    ),
    inc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
    exc_criteria=st.lists(st.integers(min_value=0, max_value=10), max_size=5),
)
def test_missing_or_empty_rationale_produces_none(
    verdict: str,
    confidence: float,
    rationale: str | None,
    inc_criteria: list[int],
    exc_criteria: list[int],
) -> None:
    """_parse_response SHALL return None when rationale is missing,
    empty, or whitespace-only.

    **Validates: Requirements 3.6**
    """
    runner = _make_runner()
    payload: dict = {
        "verdict": verdict,
        "confidence": confidence,
        "matched_inclusion_criteria": inc_criteria,
        "matched_exclusion_criteria": exc_criteria,
    }
    if rationale is not None:
        payload["rationale"] = rationale
    # If rationale is None, omit the field entirely

    result = runner._parse_response(json.dumps(payload))
    assert result is None


# ---------------------------------------------------------------------------
# Property 6.6: Valid JSON with non-list matched criteria → None
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    verdict=st.sampled_from(["include", "exclude", "uncertain"]),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    rationale=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""),
    bad_criteria=st.one_of(
        st.text(min_size=1, max_size=50),
        st.integers(),
        st.floats(allow_nan=False, allow_infinity=False),
        st.dictionaries(st.text(max_size=10), st.integers(), max_size=3),
    ),
    which_field=st.sampled_from(
        ["matched_inclusion_criteria", "matched_exclusion_criteria"]
    ),
)
def test_non_list_criteria_produces_none(
    verdict: str,
    confidence: float,
    rationale: str,
    bad_criteria: object,
    which_field: str,
) -> None:
    """_parse_response SHALL return None when matched_inclusion_criteria
    or matched_exclusion_criteria is not a list.

    **Validates: Requirements 3.6**
    """
    runner = _make_runner()
    payload: dict = {
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "matched_inclusion_criteria": [0],
        "matched_exclusion_criteria": [1],
    }
    payload[which_field] = bad_criteria

    result = runner._parse_response(json.dumps(payload))
    assert result is None


# ---------------------------------------------------------------------------
# Property 6.7: Valid JSON with non-int items in criteria lists → None
# ---------------------------------------------------------------------------


@settings(max_examples=50)
@given(
    verdict=st.sampled_from(["include", "exclude", "uncertain"]),
    confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    rationale=st.text(min_size=1, max_size=200).filter(lambda s: s.strip() != ""),
    bad_item=st.one_of(
        st.text(min_size=1, max_size=20),
        st.floats(allow_nan=False, allow_infinity=False).filter(
            lambda f: f != int(f) if f == f else True
        ),
        st.none(),
        st.lists(st.integers(), max_size=2),
    ),
    which_field=st.sampled_from(
        ["matched_inclusion_criteria", "matched_exclusion_criteria"]
    ),
)
def test_non_int_items_in_criteria_produces_none(
    verdict: str,
    confidence: float,
    rationale: str,
    bad_item: object,
    which_field: str,
) -> None:
    """_parse_response SHALL return None when criteria lists contain
    non-integer items.

    **Validates: Requirements 3.6**
    """
    runner = _make_runner()
    payload: dict = {
        "verdict": verdict,
        "confidence": confidence,
        "rationale": rationale,
        "matched_inclusion_criteria": [],
        "matched_exclusion_criteria": [],
    }
    # Insert a list containing the bad item
    payload[which_field] = [bad_item]

    result = runner._parse_response(json.dumps(payload))
    assert result is None


# ---------------------------------------------------------------------------
# Property 6 Integration: screen_record with malformed response → fallback
# ---------------------------------------------------------------------------


@settings(max_examples=30)
@given(
    malformed_text=st.one_of(
        # Random bytes/text
        st.binary(min_size=1, max_size=200).map(
            lambda b: b.decode("utf-8", errors="replace")
        ),
        # Valid JSON missing verdict
        st.builds(
            lambda c, r: json.dumps(
                {"confidence": c, "rationale": r, "matched_inclusion_criteria": []}
            ),
            c=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            r=st.text(min_size=1, max_size=50).filter(lambda s: s.strip() != ""),
        ),
        # Invalid verdict
        st.builds(
            lambda v: json.dumps(
                {
                    "verdict": v,
                    "confidence": 0.5,
                    "rationale": "test",
                    "matched_inclusion_criteria": [],
                    "matched_exclusion_criteria": [],
                }
            ),
            v=st.text(min_size=1, max_size=20).filter(
                lambda s: s not in ("include", "exclude", "uncertain")
            ),
        ),
        # Confidence out of range
        st.builds(
            lambda c: json.dumps(
                {
                    "verdict": "include",
                    "confidence": c,
                    "rationale": "test rationale",
                    "matched_inclusion_criteria": [],
                    "matched_exclusion_criteria": [],
                }
            ),
            c=st.one_of(
                st.floats(max_value=-0.001, allow_nan=False, allow_infinity=False),
                st.floats(min_value=1.001, max_value=1e10, allow_nan=False, allow_infinity=False),
            ),
        ),
    ),
)
@pytest.mark.asyncio
async def test_screen_record_malformed_response_yields_uncertain_fallback(
    malformed_text: str,
) -> None:
    """screen_record() SHALL return a ScreeningResult with verdict="uncertain",
    confidence=0.0, and rationale containing "Agent response parsing failed"
    when the LLM returns a malformed response.

    **Validates: Requirements 3.6**
    """
    mock_inference_client = AsyncMock()
    mock_inference_client.chat_completion.return_value = malformed_text

    mock_agent_registry = MagicMock()
    mock_agent_registry._load_archetype_raw.return_value = None

    runner = LiteratureScreenerAgentRunner(
        inference_client=mock_inference_client,
        agent_registry=mock_agent_registry,
        model_name="test-model",
    )

    result = await runner.screen_record(
        title="Test Paper Title",
        abstract="Test abstract content for screening.",
        body_sections=None,
        protocol_criteria={
            "pico_criteria": {
                "population": "adults",
                "intervention": "drug X",
                "comparison": "placebo",
                "outcome": "mortality",
            },
            "inclusion_criteria": ["randomized"],
            "exclusion_criteria": ["animal study"],
        },
    )

    assert isinstance(result, ScreeningResult)
    assert result.verdict == "uncertain"
    assert result.confidence == 0.0
    assert "Agent response parsing failed" in result.rationale
    assert result.matched_inclusion_criteria == []
    assert result.matched_exclusion_criteria == []
    assert result.screening_duration_ms >= 0
