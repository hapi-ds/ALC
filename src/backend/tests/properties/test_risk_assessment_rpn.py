"""Property-based tests for Risk Assessment RPN (Risk Priority Number) correctness.

Property 17: Risk Assessment RPN Correctness
For any LLM-generated risk assessment output parsed by _format_risk_assessment_table(),
the RPN column SHALL always equal Severity × Likelihood, where both Severity and
Likelihood are clamped to the range 1-5 by _clamp_score().

**Validates: Requirements 10.5**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

import re

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.placeholder_processor import PlaceholderProcessor


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for risk IDs (e.g., RISK-001 to RISK-999)
st_risk_ids = st.from_regex(r"RISK-[0-9]{3}", fullmatch=True)

# Strategy for risk descriptions (printable ASCII, no pipes to avoid parsing issues)
st_risk_descriptions = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Z"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=5,
    max_size=80,
).map(lambda s: s.replace("|", " ").strip() or "Risk description")

# Strategy for severity/likelihood values as strings (including edge cases)
# These represent what the LLM might output - integers, possibly with extra text
st_score_values = st.one_of(
    # Clean integers
    st.integers(min_value=-10, max_value=20).map(str),
    # Integers with surrounding text
    st.integers(min_value=1, max_value=5).map(lambda n: f"{n}/5"),
    st.integers(min_value=1, max_value=5).map(lambda n: f"Score: {n}"),
    # Just digits
    st.integers(min_value=0, max_value=9).map(str),
)

# Strategy for mitigation text
st_mitigations = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Z", "P"),
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=5,
    max_size=60,
).map(lambda s: s.replace("|", " ").strip() or "Mitigation strategy")

# Strategy for number of risk rows (2-25 per requirement)
st_num_risks = st.integers(min_value=1, max_value=30)


def build_raw_risk_response(
    risk_ids: list[str],
    descriptions: list[str],
    severities: list[str],
    likelihoods: list[str],
    mitigations: list[str],
) -> str:
    """Build a raw LLM response in the expected pipe-delimited format.

    Format: RISK-NNN | Description | Severity | Likelihood | Mitigation
    """
    lines: list[str] = []
    for i in range(len(risk_ids)):
        line = (
            f"{risk_ids[i]} | {descriptions[i]} | "
            f"{severities[i]} | {likelihoods[i]} | {mitigations[i]}"
        )
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Property 17: Risk Assessment RPN Correctness
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    severity_str=st_score_values,
)
def test_clamp_score_always_returns_1_to_5(
    severity_str: str,
) -> None:
    """_clamp_score SHALL always return an integer in the range [1, 5]
    regardless of the input string value.

    **Validates: Requirements 10.5**
    """
    result = PlaceholderProcessor._clamp_score(severity_str)

    assert isinstance(result, int), (
        f"_clamp_score should return int, got {type(result)}"
    )
    assert 1 <= result <= 5, (
        f"_clamp_score({severity_str!r}) returned {result}, expected 1-5"
    )


@settings(max_examples=25)
@given(
    num_risks=st.integers(min_value=1, max_value=25),
    risk_ids=st.lists(st_risk_ids, min_size=25, max_size=25, unique=True),
    descriptions=st.lists(st_risk_descriptions, min_size=25, max_size=25),
    severities=st.lists(
        st.integers(min_value=1, max_value=5).map(str),
        min_size=25,
        max_size=25,
    ),
    likelihoods=st.lists(
        st.integers(min_value=1, max_value=5).map(str),
        min_size=25,
        max_size=25,
    ),
    mitigations=st.lists(st_mitigations, min_size=25, max_size=25),
)
def test_rpn_equals_severity_times_likelihood(
    num_risks: int,
    risk_ids: list[str],
    descriptions: list[str],
    severities: list[str],
    likelihoods: list[str],
    mitigations: list[str],
) -> None:
    """For every row in the formatted risk assessment table, the RPN column
    SHALL equal Severity × Likelihood, where both are clamped to 1-5.

    **Validates: Requirements 10.5**
    """
    # Use only num_risks items
    raw_response = build_raw_risk_response(
        risk_ids[:num_risks],
        descriptions[:num_risks],
        severities[:num_risks],
        likelihoods[:num_risks],
        mitigations[:num_risks],
    )

    processor = PlaceholderProcessor.__new__(PlaceholderProcessor)
    result = processor._format_risk_assessment_table(raw_response)

    # Parse the output table rows (skip header and separator)
    lines = result.strip().split("\n")
    assert len(lines) >= 3, f"Expected at least header + separator + 1 row, got {len(lines)}"

    # Skip header (line 0) and separator (line 1)
    data_rows = lines[2:]

    for row in data_rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        assert len(cells) == 6, (
            f"Expected 6 columns in risk row, got {len(cells)}: {row}"
        )

        # Columns: Risk ID, Description, Severity, Likelihood, RPN, Mitigation
        severity_val = int(cells[2])
        likelihood_val = int(cells[3])
        rpn_val = int(cells[4])

        # Verify clamping
        assert 1 <= severity_val <= 5, (
            f"Severity {severity_val} not in range 1-5 in row: {row}"
        )
        assert 1 <= likelihood_val <= 5, (
            f"Likelihood {likelihood_val} not in range 1-5 in row: {row}"
        )

        # Verify RPN = Severity × Likelihood
        expected_rpn = severity_val * likelihood_val
        assert rpn_val == expected_rpn, (
            f"RPN should be {severity_val} × {likelihood_val} = {expected_rpn}, "
            f"got {rpn_val} in row: {row}"
        )


@settings(max_examples=25)
@given(
    num_risks=st.integers(min_value=1, max_value=25),
    risk_ids=st.lists(st_risk_ids, min_size=25, max_size=25, unique=True),
    descriptions=st.lists(st_risk_descriptions, min_size=25, max_size=25),
    severities=st.lists(st_score_values, min_size=25, max_size=25),
    likelihoods=st.lists(st_score_values, min_size=25, max_size=25),
    mitigations=st.lists(st_mitigations, min_size=25, max_size=25),
)
def test_rpn_correctness_with_arbitrary_score_strings(
    num_risks: int,
    risk_ids: list[str],
    descriptions: list[str],
    severities: list[str],
    likelihoods: list[str],
    mitigations: list[str],
) -> None:
    """For any arbitrary string values in the severity/likelihood fields,
    _format_risk_assessment_table SHALL clamp them to 1-5 and compute
    RPN = clamped_severity × clamped_likelihood.

    This tests the full pipeline: arbitrary LLM output → clamping → RPN calculation.

    **Validates: Requirements 10.5**
    """
    raw_response = build_raw_risk_response(
        risk_ids[:num_risks],
        descriptions[:num_risks],
        severities[:num_risks],
        likelihoods[:num_risks],
        mitigations[:num_risks],
    )

    processor = PlaceholderProcessor.__new__(PlaceholderProcessor)
    result = processor._format_risk_assessment_table(raw_response)

    # Parse the output table
    lines = result.strip().split("\n")
    assert len(lines) >= 3, f"Expected at least header + separator + 1 row, got {len(lines)}"

    # Skip header and separator
    data_rows = lines[2:]

    for row in data_rows:
        cells = [c.strip() for c in row.split("|") if c.strip()]
        if len(cells) < 6:
            continue  # Skip malformed rows (placeholder rows)

        severity_val = int(cells[2])
        likelihood_val = int(cells[3])
        rpn_val = int(cells[4])

        # Severity and Likelihood must be clamped to 1-5
        assert 1 <= severity_val <= 5, (
            f"Severity {severity_val} not clamped to 1-5 in row: {row}"
        )
        assert 1 <= likelihood_val <= 5, (
            f"Likelihood {likelihood_val} not clamped to 1-5 in row: {row}"
        )

        # RPN must equal Severity × Likelihood
        expected_rpn = severity_val * likelihood_val
        assert rpn_val == expected_rpn, (
            f"RPN should be {severity_val} × {likelihood_val} = {expected_rpn}, "
            f"got {rpn_val} in row: {row}"
        )


@settings(max_examples=25)
@given(
    num_risks=st.integers(min_value=2, max_value=25),
    risk_ids=st.lists(st_risk_ids, min_size=25, max_size=25, unique=True),
    descriptions=st.lists(st_risk_descriptions, min_size=25, max_size=25),
    severities=st.lists(
        st.integers(min_value=1, max_value=5).map(str),
        min_size=25,
        max_size=25,
    ),
    likelihoods=st.lists(
        st.integers(min_value=1, max_value=5).map(str),
        min_size=25,
        max_size=25,
    ),
    mitigations=st.lists(st_mitigations, min_size=25, max_size=25),
)
def test_risk_table_has_between_2_and_25_rows(
    num_risks: int,
    risk_ids: list[str],
    descriptions: list[str],
    severities: list[str],
    likelihoods: list[str],
    mitigations: list[str],
) -> None:
    """The formatted risk assessment table SHALL contain between 2 and 25
    data rows (excluding header and separator).

    **Validates: Requirements 10.5**
    """
    raw_response = build_raw_risk_response(
        risk_ids[:num_risks],
        descriptions[:num_risks],
        severities[:num_risks],
        likelihoods[:num_risks],
        mitigations[:num_risks],
    )

    processor = PlaceholderProcessor.__new__(PlaceholderProcessor)
    result = processor._format_risk_assessment_table(raw_response)

    # Parse the output table
    lines = result.strip().split("\n")
    # Skip header and separator
    data_rows = lines[2:]

    assert 2 <= len(data_rows) <= 25, (
        f"Expected 2-25 data rows, got {len(data_rows)}"
    )
