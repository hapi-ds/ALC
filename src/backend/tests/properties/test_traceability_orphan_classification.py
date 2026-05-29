"""Property-based tests for orphan classification by keyword analysis.

Property 6: Orphan Classification by Keyword Analysis

Generate requirement/test case texts with random keyword combinations from
each category, verify severity/risk_level follows precedence rules:
- critical > major > minor (for severity)
- high > medium > low (for risk_level)

**Validates: Requirements 2.4, 3.4**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
    - Module: src/backend/src/alcoabase/services/orphan_detection.py
"""

from __future__ import annotations

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.orphan_detection import (
    OrphanDetectionService,
    _RISK_LEVEL_KEYWORDS,
    _SEVERITY_KEYWORDS,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# All severity keywords by category
CRITICAL_KEYWORDS = _SEVERITY_KEYWORDS["critical"]
MAJOR_KEYWORDS = _SEVERITY_KEYWORDS["major"]
MINOR_KEYWORDS = _SEVERITY_KEYWORDS["minor"]

# All risk level keywords by category
HIGH_KEYWORDS = _RISK_LEVEL_KEYWORDS["high"]
MEDIUM_KEYWORDS = _RISK_LEVEL_KEYWORDS["medium"]
LOW_KEYWORDS = _RISK_LEVEL_KEYWORDS["low"]

# Filler text that does NOT contain any classification keywords
FILLER_TEXT = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
    min_size=3,
    max_size=30,
).filter(
    lambda t: not any(
        kw in t.lower()
        for kw in (
            CRITICAL_KEYWORDS
            + MAJOR_KEYWORDS
            + MINOR_KEYWORDS
            + HIGH_KEYWORDS
            + MEDIUM_KEYWORDS
            + LOW_KEYWORDS
        )
    )
)

# Strategy to pick a random keyword from a given category
st_critical_keyword = st.sampled_from(CRITICAL_KEYWORDS)
st_major_keyword = st.sampled_from(MAJOR_KEYWORDS)
st_minor_keyword = st.sampled_from(MINOR_KEYWORDS)
st_high_keyword = st.sampled_from(HIGH_KEYWORDS)
st_medium_keyword = st.sampled_from(MEDIUM_KEYWORDS)
st_low_keyword = st.sampled_from(LOW_KEYWORDS)


@st.composite
def text_with_keywords(
    draw: st.DrawFn, keyword_strategy: st.SearchStrategy[str]
) -> str:
    """Generate text containing at least one keyword from the given strategy."""
    prefix = draw(FILLER_TEXT)
    keyword = draw(keyword_strategy)
    suffix = draw(FILLER_TEXT)
    return f"{prefix} {keyword} {suffix}"


@st.composite
def text_with_multiple_severity_keywords(
    draw: st.DrawFn,
    categories: list[st.SearchStrategy[str]],
) -> str:
    """Generate text containing keywords from multiple severity categories."""
    parts = [draw(FILLER_TEXT)]
    for cat_strategy in categories:
        parts.append(draw(cat_strategy))
        parts.append(draw(FILLER_TEXT))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Property 6a: Critical severity takes precedence over major and minor
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    critical_kw=st_critical_keyword,
    major_kw=st_major_keyword,
    minor_kw=st_minor_keyword,
    filler=FILLER_TEXT,
)
def test_severity_critical_takes_precedence_over_major_and_minor(
    critical_kw: str,
    major_kw: str,
    minor_kw: str,
    filler: str,
) -> None:
    """When a requirement text contains keywords from critical, major, AND
    minor categories, the severity SHALL be classified as "critical"
    (highest precedence).

    **Validates: Requirements 2.4**
    """
    text = f"{filler} {critical_kw} {filler} {major_kw} {filler} {minor_kw}"
    result = OrphanDetectionService._classify_severity_by_keywords(text)
    assert result == "critical"


# ---------------------------------------------------------------------------
# Property 6b: Critical severity takes precedence over major alone
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    critical_kw=st_critical_keyword,
    major_kw=st_major_keyword,
    filler=FILLER_TEXT,
)
def test_severity_critical_takes_precedence_over_major(
    critical_kw: str,
    major_kw: str,
    filler: str,
) -> None:
    """When a requirement text contains keywords from both critical and major
    categories, the severity SHALL be classified as "critical".

    **Validates: Requirements 2.4**
    """
    text = f"{filler} {critical_kw} {filler} {major_kw}"
    result = OrphanDetectionService._classify_severity_by_keywords(text)
    assert result == "critical"


# ---------------------------------------------------------------------------
# Property 6c: Critical severity takes precedence over minor alone
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    critical_kw=st_critical_keyword,
    minor_kw=st_minor_keyword,
    filler=FILLER_TEXT,
)
def test_severity_critical_takes_precedence_over_minor(
    critical_kw: str,
    minor_kw: str,
    filler: str,
) -> None:
    """When a requirement text contains keywords from both critical and minor
    categories, the severity SHALL be classified as "critical".

    **Validates: Requirements 2.4**
    """
    text = f"{filler} {critical_kw} {filler} {minor_kw}"
    result = OrphanDetectionService._classify_severity_by_keywords(text)
    assert result == "critical"


# ---------------------------------------------------------------------------
# Property 6d: Major severity takes precedence over minor
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    major_kw=st_major_keyword,
    minor_kw=st_minor_keyword,
    filler=FILLER_TEXT,
)
def test_severity_major_takes_precedence_over_minor(
    major_kw: str,
    minor_kw: str,
    filler: str,
) -> None:
    """When a requirement text contains keywords from both major and minor
    categories (but NOT critical), the severity SHALL be classified as "major".

    **Validates: Requirements 2.4**
    """
    text = f"{filler} {major_kw} {filler} {minor_kw}"
    # Ensure no critical keywords are accidentally present
    text_lower = text.lower()
    has_critical = any(kw in text_lower for kw in CRITICAL_KEYWORDS)
    if has_critical:
        return  # Skip this example — filler accidentally contains critical kw

    result = OrphanDetectionService._classify_severity_by_keywords(text)
    assert result == "major"


# ---------------------------------------------------------------------------
# Property 6e: Single-category severity classification is correct
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(text=text_with_keywords(st_critical_keyword))
def test_severity_critical_keyword_alone_classifies_critical(text: str) -> None:
    """When a requirement text contains only a critical keyword (no major/minor),
    the severity SHALL be classified as "critical".

    **Validates: Requirements 2.4**
    """
    result = OrphanDetectionService._classify_severity_by_keywords(text)
    assert result == "critical"


@settings(max_examples=10)
@given(text=text_with_keywords(st_major_keyword))
def test_severity_major_keyword_alone_classifies_major(text: str) -> None:
    """When a requirement text contains only a major keyword (no critical),
    the severity SHALL be classified as "major" (or "critical" if filler
    accidentally contains a critical keyword — which is filtered out).

    **Validates: Requirements 2.4**
    """
    text_lower = text.lower()
    has_critical = any(kw in text_lower for kw in CRITICAL_KEYWORDS)
    if has_critical:
        return  # Skip — filler accidentally contains critical keyword

    result = OrphanDetectionService._classify_severity_by_keywords(text)
    assert result == "major"


@settings(max_examples=10)
@given(text=text_with_keywords(st_minor_keyword))
def test_severity_minor_keyword_alone_classifies_minor(text: str) -> None:
    """When a requirement text contains only a minor keyword (no critical/major),
    the severity SHALL be classified as "minor".

    **Validates: Requirements 2.4**
    """
    text_lower = text.lower()
    has_critical = any(kw in text_lower for kw in CRITICAL_KEYWORDS)
    has_major = any(kw in text_lower for kw in MAJOR_KEYWORDS)
    if has_critical or has_major:
        return  # Skip — filler accidentally contains higher-precedence keyword

    result = OrphanDetectionService._classify_severity_by_keywords(text)
    assert result == "minor"


# ---------------------------------------------------------------------------
# Property 6f: High risk_level takes precedence over medium and low
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    high_kw=st_high_keyword,
    medium_kw=st_medium_keyword,
    low_kw=st_low_keyword,
    filler=FILLER_TEXT,
)
def test_risk_level_high_takes_precedence_over_medium_and_low(
    high_kw: str,
    medium_kw: str,
    low_kw: str,
    filler: str,
) -> None:
    """When a test case text contains keywords from high, medium, AND low
    categories, the risk_level SHALL be classified as "high"
    (highest precedence).

    **Validates: Requirements 3.4**
    """
    text = f"{filler} {high_kw} {filler} {medium_kw} {filler} {low_kw}"
    result = OrphanDetectionService._classify_risk_level_by_keywords(text)
    assert result == "high"


# ---------------------------------------------------------------------------
# Property 6g: High risk_level takes precedence over medium alone
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    high_kw=st_high_keyword,
    medium_kw=st_medium_keyword,
    filler=FILLER_TEXT,
)
def test_risk_level_high_takes_precedence_over_medium(
    high_kw: str,
    medium_kw: str,
    filler: str,
) -> None:
    """When a test case text contains keywords from both high and medium
    categories, the risk_level SHALL be classified as "high".

    **Validates: Requirements 3.4**
    """
    text = f"{filler} {high_kw} {filler} {medium_kw}"
    result = OrphanDetectionService._classify_risk_level_by_keywords(text)
    assert result == "high"


# ---------------------------------------------------------------------------
# Property 6h: High risk_level takes precedence over low alone
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    high_kw=st_high_keyword,
    low_kw=st_low_keyword,
    filler=FILLER_TEXT,
)
def test_risk_level_high_takes_precedence_over_low(
    high_kw: str,
    low_kw: str,
    filler: str,
) -> None:
    """When a test case text contains keywords from both high and low
    categories, the risk_level SHALL be classified as "high".

    **Validates: Requirements 3.4**
    """
    text = f"{filler} {high_kw} {filler} {low_kw}"
    result = OrphanDetectionService._classify_risk_level_by_keywords(text)
    assert result == "high"


# ---------------------------------------------------------------------------
# Property 6i: Medium risk_level takes precedence over low
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(
    medium_kw=st_medium_keyword,
    low_kw=st_low_keyword,
    filler=FILLER_TEXT,
)
def test_risk_level_medium_takes_precedence_over_low(
    medium_kw: str,
    low_kw: str,
    filler: str,
) -> None:
    """When a test case text contains keywords from both medium and low
    categories (but NOT high), the risk_level SHALL be classified as "medium".

    **Validates: Requirements 3.4**
    """
    text = f"{filler} {medium_kw} {filler} {low_kw}"
    text_lower = text.lower()
    has_high = any(kw in text_lower for kw in HIGH_KEYWORDS)
    if has_high:
        return  # Skip — filler accidentally contains high keyword

    result = OrphanDetectionService._classify_risk_level_by_keywords(text)
    assert result == "medium"


# ---------------------------------------------------------------------------
# Property 6j: Single-category risk_level classification is correct
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(text=text_with_keywords(st_high_keyword))
def test_risk_level_high_keyword_alone_classifies_high(text: str) -> None:
    """When a test case text contains only a high keyword, the risk_level
    SHALL be classified as "high".

    **Validates: Requirements 3.4**
    """
    result = OrphanDetectionService._classify_risk_level_by_keywords(text)
    assert result == "high"


@settings(max_examples=10)
@given(text=text_with_keywords(st_medium_keyword))
def test_risk_level_medium_keyword_alone_classifies_medium(text: str) -> None:
    """When a test case text contains only a medium keyword (no high),
    the risk_level SHALL be classified as "medium".

    **Validates: Requirements 3.4**
    """
    text_lower = text.lower()
    has_high = any(kw in text_lower for kw in HIGH_KEYWORDS)
    if has_high:
        return  # Skip — filler accidentally contains high keyword

    result = OrphanDetectionService._classify_risk_level_by_keywords(text)
    assert result == "medium"


@settings(max_examples=10)
@given(text=text_with_keywords(st_low_keyword))
def test_risk_level_low_keyword_alone_classifies_low(text: str) -> None:
    """When a test case text contains only a low keyword (no high/medium),
    the risk_level SHALL be classified as "low".

    **Validates: Requirements 3.4**
    """
    text_lower = text.lower()
    has_high = any(kw in text_lower for kw in HIGH_KEYWORDS)
    has_medium = any(kw in text_lower for kw in MEDIUM_KEYWORDS)
    if has_high or has_medium:
        return  # Skip — filler accidentally contains higher-precedence keyword

    result = OrphanDetectionService._classify_risk_level_by_keywords(text)
    assert result == "low"


# ---------------------------------------------------------------------------
# Property 6k: Default severity when no keywords match
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(filler=FILLER_TEXT)
def test_severity_defaults_to_major_when_no_keywords(filler: str) -> None:
    """When a requirement text contains NO keywords from any severity category,
    the severity SHALL default to "major" (per Requirement 2.5 fallback).

    **Validates: Requirements 2.4**
    """
    result = OrphanDetectionService._classify_severity_by_keywords(filler)
    assert result == "major"


# ---------------------------------------------------------------------------
# Property 6l: Default risk_level when no keywords match
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(filler=FILLER_TEXT)
def test_risk_level_defaults_to_medium_when_no_keywords(filler: str) -> None:
    """When a test case text contains NO keywords from any risk_level category,
    the risk_level SHALL default to "medium" (per Requirement 3.5 fallback).

    **Validates: Requirements 3.4**
    """
    result = OrphanDetectionService._classify_risk_level_by_keywords(filler)
    assert result == "medium"
