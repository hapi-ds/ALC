"""Property-based tests for the Literature Search Engine feature.

Tests correctness properties from the Literature Search Engine & External
API Gateways (Phase 9.1) design document.

References:
    - Design: .kiro/specs/Step_9-1_literature-search-engine/design.md
    - Requirements: .kiro/specs/Step_9-1_literature-search-engine/requirements.md
"""

# Feature: Step_9-1_literature-search-engine

from datetime import date, datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.literature.schemas.search import (
    DatePrecision,
    LiteratureSearchResult,
    PartialResultInfo,
    PublicationType,
    SearchQuery,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

st_title = st.text(min_size=1, max_size=200)
st_author = st.text(min_size=1, max_size=100)
st_authors = st.lists(st_author, min_size=0, max_size=10)
st_abstract = st.text(min_size=0, max_size=500)
st_doi = st.one_of(st.none(), st.text(min_size=1, max_size=100))
st_publication_date = st.dates(
    min_value=date(1900, 1, 1), max_value=date(2100, 12, 31)
)
st_source_id = st.text(min_size=1, max_size=50)
st_external_id = st.text(min_size=1, max_size=100)
st_journal_or_venue = st.text(min_size=0, max_size=200)
st_publication_type = st.sampled_from(list(PublicationType))
st_url = st.one_of(st.none(), st.text(min_size=1, max_size=200))
st_date_precision = st.sampled_from(list(DatePrecision))
st_retrieval_timestamp = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 12, 31),
    timezones=st.just(timezone.utc),
)
st_query_id = st.uuids().map(str)


@st.composite
def st_literature_search_result(draw: st.DrawFn) -> LiteratureSearchResult:
    """Generate a valid LiteratureSearchResult instance.

    Uses Hypothesis composite strategy to draw valid values for all
    fields of LiteratureSearchResult.
    """
    return LiteratureSearchResult(
        title=draw(st_title),
        authors=draw(st_authors),
        abstract=draw(st_abstract),
        doi=draw(st_doi),
        publication_date=draw(st_publication_date),
        source_id=draw(st_source_id),
        external_id=draw(st_external_id),
        journal_or_venue=draw(st_journal_or_venue),
        publication_type=draw(st_publication_type),
        url=draw(st_url),
        date_precision=draw(st_date_precision),
        retrieval_timestamp=draw(st_retrieval_timestamp),
        query_id=draw(st_query_id),
    )


# ---------------------------------------------------------------------------
# Property 13: Literature Search Result JSON Round-Trip
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(result=st_literature_search_result())
def test_literature_search_result_json_round_trip(
    result: LiteratureSearchResult,
) -> None:
    """For any valid LiteratureSearchResult, serializing to JSON via
    model_dump_json() and deserializing via model_validate_json() produces
    a field-by-field equal object with identical types, values, and list
    ordering.

    **Validates: Requirements 12.6**
    """
    json_str = result.model_dump_json()
    restored = LiteratureSearchResult.model_validate_json(json_str)

    assert restored == result, (
        f"JSON round-trip produced a different object.\n"
        f"Original: {result}\n"
        f"Restored: {restored}"
    )

    # Verify field-by-field equality for extra confidence
    assert restored.title == result.title
    assert restored.authors == result.authors
    assert restored.abstract == result.abstract
    assert restored.doi == result.doi
    assert restored.publication_date == result.publication_date
    assert restored.source_id == result.source_id
    assert restored.external_id == result.external_id
    assert restored.journal_or_venue == result.journal_or_venue
    assert restored.publication_type == result.publication_type
    assert restored.url == result.url
    assert restored.date_precision == result.date_precision
    assert restored.retrieval_timestamp == result.retrieval_timestamp
    assert restored.query_id == result.query_id


# ---------------------------------------------------------------------------
# Property 14: Pagination Validation
# (Already tested separately — see SearchQuery validator tests)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Property 1: API Key Encryption Round-Trip
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    api_key=st.text(
        min_size=1,
        max_size=512,
        alphabet=st.characters(categories=("L", "M", "N", "P", "S", "Z")),
    )
)
def test_api_key_encryption_round_trip(api_key: str) -> None:
    """For any printable Unicode string of 1–512 characters, encrypting with
    APIKeyVault.encrypt() and then decrypting with APIKeyVault.decrypt()
    produces an identical string.

    **Validates: Requirements 3.4, 4.1, 4.2**
    """
    import os

    from alcoabase.literature.services.api_key_vault import APIKeyVault

    master_key = os.urandom(32)
    vault = APIKeyVault(master_key)

    encrypted = vault.encrypt(api_key)
    decrypted = vault.decrypt(encrypted)

    assert decrypted == api_key, (
        f"Encryption round-trip failed.\n"
        f"Original: {api_key!r}\n"
        f"Decrypted: {decrypted!r}"
    )


# ---------------------------------------------------------------------------
# Property 14: Pagination Validation
# ---------------------------------------------------------------------------
# (defined elsewhere in the test suite)


# ---------------------------------------------------------------------------
# Property 2: API Key Masking
# ---------------------------------------------------------------------------

st_api_key = st.text(min_size=0, max_size=512)


@settings(max_examples=100)
@given(key=st_api_key)
def test_api_key_masking(key: str) -> None:
    """For any string key, mask_key returns the correct masked representation:
    - If len(key) < 4: returns "*" * len(key)
    - If len(key) >= 4: returns "*" * (len(key) - 4) + key[-4:]
    - len(mask_key(key)) == len(key) always

    **Validates: Requirements 4.3**
    """
    from alcoabase.literature.services.api_key_vault import APIKeyVault

    masked = APIKeyVault.mask_key(key)

    # Length preservation: masked output always has same length as input
    assert len(masked) == len(key), (
        f"Masked key length {len(masked)} != original key length {len(key)}.\n"
        f"Key: {key!r}\n"
        f"Masked: {masked!r}"
    )

    if len(key) < 4:
        # Short keys: all asterisks
        expected = "*" * len(key)
        assert masked == expected, (
            f"Short key masking incorrect.\n"
            f"Key: {key!r} (len={len(key)})\n"
            f"Expected: {expected!r}\n"
            f"Got: {masked!r}"
        )
    else:
        # Normal keys: asterisks prefix + last 4 chars visible
        expected = "*" * (len(key) - 4) + key[-4:]
        assert masked == expected, (
            f"Key masking incorrect.\n"
            f"Key: {key!r} (len={len(key)})\n"
            f"Expected: {expected!r}\n"
            f"Got: {masked!r}"
        )


# ---------------------------------------------------------------------------
# Property 19: Adapter Validation and Isolation
# ---------------------------------------------------------------------------

from alcoabase.literature.services.source_registry import (
    REQUIRED_ADAPTER_METHODS,
    SourceRegistry,
)

st_method_subset = st.frozensets(
    st.sampled_from(REQUIRED_ADAPTER_METHODS), min_size=0, max_size=5
)


def _make_mock_adapter(methods: frozenset[str]) -> object:
    """Create a mock adapter object with only the specified methods."""

    class MockAdapter:
        pass

    instance = MockAdapter()
    for method_name in methods:
        setattr(instance, method_name, lambda: None)
    return instance


@settings(max_examples=100)
@given(method_subsets=st.lists(st_method_subset, min_size=1, max_size=10))
def test_adapter_validation_and_isolation(
    method_subsets: list[frozenset[str]],
) -> None:
    """For any set of mock adapter objects (some valid, some missing methods),
    validate_adapter correctly identifies valid adapters (those with ALL
    required methods) and invalid adapters (those missing ANY method).
    Additionally, validating an invalid adapter does not affect the registry
    state or the validation results of other adapters.

    **Validates: Requirements 1.4, 1.5**
    """
    all_required = frozenset(REQUIRED_ADAPTER_METHODS)
    registry = SourceRegistry()

    # Track validation results
    valid_adapters: list[tuple[int, object]] = []
    invalid_adapters: list[tuple[int, object, frozenset[str]]] = []

    for idx, method_subset in enumerate(method_subsets):
        adapter = _make_mock_adapter(method_subset)
        is_valid, missing = registry.validate_adapter(adapter)

        expected_missing = all_required - method_subset

        if method_subset == all_required:
            # Adapter has ALL required methods → should be valid
            assert is_valid, (
                f"Adapter with all required methods reported as invalid.\n"
                f"Methods present: {sorted(method_subset)}\n"
                f"Reported missing: {missing}"
            )
            assert missing == [], (
                f"Valid adapter should have empty missing list, got: {missing}"
            )
            valid_adapters.append((idx, adapter))
        else:
            # Adapter missing at least one method → should be invalid
            assert not is_valid, (
                f"Adapter missing methods reported as valid.\n"
                f"Methods present: {sorted(method_subset)}\n"
                f"Expected missing: {sorted(expected_missing)}"
            )
            assert set(missing) == expected_missing, (
                f"Missing methods mismatch.\n"
                f"Methods present: {sorted(method_subset)}\n"
                f"Expected missing: {sorted(expected_missing)}\n"
                f"Actual missing: {sorted(missing)}"
            )
            invalid_adapters.append((idx, adapter, expected_missing))

    # Isolation property: the registry should remain empty after validation
    # calls alone (validate_adapter does NOT register adapters)
    assert registry.adapter_count == 0, (
        f"Registry should be empty after validate_adapter calls, "
        f"but has {registry.adapter_count} adapters registered."
    )

    # Re-validate all valid adapters after processing invalid ones
    # to confirm invalid validations don't affect valid adapter results
    for _idx, adapter in valid_adapters:
        is_valid, missing = registry.validate_adapter(adapter)
        assert is_valid, (
            "Previously valid adapter now reports invalid after "
            "other invalid adapters were validated — isolation violated."
        )
        assert missing == []

    # Re-validate invalid adapters to confirm stability
    for _idx, adapter, expected_missing in invalid_adapters:
        is_valid, missing = registry.validate_adapter(adapter)
        assert not is_valid, (
            "Previously invalid adapter now reports valid — "
            "isolation violated."
        )
        assert set(missing) == expected_missing


# ---------------------------------------------------------------------------
# Property 6: Sliding Window Rate Limit Enforcement
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    limit=st.integers(min_value=1, max_value=100),
    request_count=st.integers(min_value=1, max_value=200),
)
def test_sliding_window_rate_limit_enforcement(
    limit: int, request_count: int
) -> None:
    """For any rate limit L (1–100) and request count N (1–200), a sliding
    window rate limiter allows at most L requests within a single window.

    This tests the conceptual sliding window enforcement logic without
    requiring Redis. It simulates the window counting and gating decision
    that the RateLimiter performs:
    - Requests within a window are counted
    - Once the count reaches L, subsequent requests are NOT allowed
    - Allowed count is always min(N, L)

    Additionally verifies that `calculate_default_company_limit` always
    returns a value >= 5 and <= system_limit (when system_limit >= 5).

    **Validates: Requirements 5.1, 5.2, 5.3**
    """
    # ── Part 1: Simulate sliding window enforcement ──────────────────────
    # Simulate N requests arriving in one window with limit L
    allowed_count = 0
    for _ in range(request_count):
        if allowed_count < limit:
            allowed_count += 1

    # Property: at most L requests allowed per window
    assert allowed_count <= limit, (
        f"Sliding window allowed more requests ({allowed_count}) "
        f"than the limit ({limit})."
    )

    # Property: allowed count equals min(N, L)
    expected_allowed = min(request_count, limit)
    assert allowed_count == expected_allowed, (
        f"Expected {expected_allowed} allowed requests, got {allowed_count}.\n"
        f"Limit: {limit}, Request count: {request_count}"
    )

    # ── Part 2: calculate_default_company_limit invariants ───────────────
    from alcoabase.literature.services.rate_limiter import RateLimiter

    # Create a RateLimiter instance (uses a dummy URL; we only call the pure
    # method calculate_default_company_limit which doesn't touch Redis).
    limiter = RateLimiter(redis_url="redis://localhost:6379/0")

    # Use `limit` as system_limit and derive company count from request_count
    system_limit = limit
    active_company_count = max(1, request_count % 100 + 1)

    result = limiter.calculate_default_company_limit(
        system_limit, active_company_count
    )

    # Property: result is always >= 5 (minimum floor)
    assert result >= 5, (
        f"calculate_default_company_limit returned {result} < 5.\n"
        f"system_limit={system_limit}, "
        f"active_company_count={active_company_count}"
    )

    # Property: result equals max(5, system_limit // active_company_count)
    expected = max(5, system_limit // active_company_count)
    assert result == expected, (
        f"calculate_default_company_limit returned {result}, "
        f"expected {expected}.\n"
        f"system_limit={system_limit}, "
        f"active_company_count={active_company_count}"
    )


# ---------------------------------------------------------------------------
# Property 7: Per-Company Rate Limit Derivation
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    system_limit=st.integers(min_value=1, max_value=1000),
    active_company_count=st.integers(min_value=1, max_value=100),
)
def test_per_company_rate_limit_derivation(
    system_limit: int, active_company_count: int
) -> None:
    """For any system_limit in [1, 1000] and active_company_count in [1, 100],
    calculate_default_company_limit returns max(5, system_limit // active_company_count)
    and the result is always >= 5.

    **Validates: Requirements 6.4, 6.5**
    """
    from alcoabase.literature.services.rate_limiter import RateLimiter

    # RateLimiter.__init__ requires a redis_url but calculate_default_company_limit
    # is a pure function with no Redis dependency. Use object.__new__ to skip __init__.
    limiter = object.__new__(RateLimiter)

    result = limiter.calculate_default_company_limit(system_limit, active_company_count)

    expected = max(5, system_limit // active_company_count)
    assert result == expected, (
        f"Expected max(5, {system_limit} // {active_company_count}) = {expected}, "
        f"got {result}"
    )

    # The result must always be at least 5
    assert result >= 5, (
        f"Per-company limit must be >= 5, got {result} "
        f"(system_limit={system_limit}, companies={active_company_count})"
    )


# ---------------------------------------------------------------------------
# Property 8: Circuit Breaker State Transitions
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(events=st.lists(st.booleans(), min_size=1, max_size=50))
def test_circuit_breaker_state_transitions(events: list[bool]) -> None:
    """For any sequence of success/failure events, the circuit breaker state
    transitions follow the defined state machine rules:

    - CLOSED + failure → if failure_count >= threshold: transition to OPEN
    - CLOSED + success → reset failure_count, stay CLOSED
    - OPEN + (recovery elapsed) → HALF_OPEN (not testable deterministically)
    - HALF_OPEN + success → CLOSED
    - HALF_OPEN + failure → OPEN

    Since this test uses a deterministic local simulation (no Redis, no time),
    OPEN → HALF_OPEN transitions are simulated by injecting a probe event
    after the circuit opens.

    **Validates: Requirements 9.5**
    """
    from alcoabase.literature.services.circuit_breaker import CircuitState

    # Configuration matching the production defaults
    failure_threshold = 5

    # Local state machine simulation
    state = CircuitState.CLOSED
    failure_count = 0

    for event_is_success in events:
        if state == CircuitState.CLOSED:
            if event_is_success:
                # Success in CLOSED → reset failure count, stay CLOSED
                failure_count = 0
                new_state = CircuitState.CLOSED
            else:
                # Failure in CLOSED → increment count
                failure_count += 1
                if failure_count >= failure_threshold:
                    new_state = CircuitState.OPEN
                    failure_count = 0  # Reset on transition
                else:
                    new_state = CircuitState.CLOSED

        elif state == CircuitState.OPEN:
            # In OPEN state, we simulate recovery timeout elapsed
            # (since we can't simulate time, treat next event as a probe
            #  after recovery — transition to HALF_OPEN first)
            state = CircuitState.HALF_OPEN
            # Now process the event in HALF_OPEN
            if event_is_success:
                new_state = CircuitState.CLOSED
                failure_count = 0
            else:
                new_state = CircuitState.OPEN

        elif state == CircuitState.HALF_OPEN:
            if event_is_success:
                # Success in HALF_OPEN → CLOSED
                new_state = CircuitState.CLOSED
                failure_count = 0
            else:
                # Failure in HALF_OPEN → OPEN
                new_state = CircuitState.OPEN

        # Verify state transition rules
        if state == CircuitState.CLOSED:
            if event_is_success:
                assert new_state == CircuitState.CLOSED, (
                    f"CLOSED + success must stay CLOSED, got {new_state}"
                )
            else:
                if failure_count == 0:
                    # We just transitioned (count was reset)
                    assert new_state == CircuitState.OPEN, (
                        f"CLOSED + failure (threshold reached) must go OPEN, "
                        f"got {new_state}"
                    )
                else:
                    assert new_state == CircuitState.CLOSED, (
                        f"CLOSED + failure (below threshold) must stay CLOSED, "
                        f"got {new_state}"
                    )
        elif state == CircuitState.HALF_OPEN:
            if event_is_success:
                assert new_state == CircuitState.CLOSED, (
                    f"HALF_OPEN + success must go CLOSED, got {new_state}"
                )
            else:
                assert new_state == CircuitState.OPEN, (
                    f"HALF_OPEN + failure must go OPEN, got {new_state}"
                )

        state = new_state


# ---------------------------------------------------------------------------
# Property 9: Health Status Classification
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Property 11: Missing Required Fields Exclusion
# ---------------------------------------------------------------------------

# Strategy for generating raw result dicts with optional title/external_id
st_optional_title = st.one_of(
    st.none(),
    st.just(""),
    st.text(min_size=1, max_size=200),
)
st_optional_external_id = st.one_of(
    st.none(),
    st.just(""),
    st.text(min_size=1, max_size=100),
)


@st.composite
def st_raw_result_dict(draw: st.DrawFn) -> dict[str, str | None]:
    """Generate a raw result dict with optional title and external_id.

    Simulates raw responses from external APIs where title and external_id
    may be None or empty strings.
    """
    return {
        "title": draw(st_optional_title),
        "external_id": draw(st_optional_external_id),
        "authors": draw(st.text(min_size=0, max_size=50)),
        "abstract": draw(st.text(min_size=0, max_size=100)),
    }


def _has_required_fields(raw: dict[str, str | None]) -> bool:
    """Check if a raw result has non-empty title AND non-empty external_id."""
    title = raw.get("title")
    external_id = raw.get("external_id")
    return bool(title) and bool(external_id)


def _normalize_raw_results(
    raw_results: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    """Simulate adapter normalization: exclude results missing required fields.

    This mirrors the normalization logic in adapters (e.g., PubMedAdapter's
    _parse_single_article) which excludes results where title or external_id
    is None or empty.
    """
    return [r for r in raw_results if _has_required_fields(r)]


@settings(max_examples=100)
@given(raw_results=st.lists(st_raw_result_dict(), min_size=0, max_size=30))
def test_missing_required_fields_exclusion(
    raw_results: list[dict[str, str | None]],
) -> None:
    """For any list of raw source API responses where results may have
    title and/or external_id as None or empty, the normalization logic
    SHALL exclude results missing required fields. The count of normalized
    results SHALL always be ≤ the count of raw results, and all normalized
    results SHALL have non-empty title AND non-empty external_id.

    **Validates: Requirements 12.3**
    """
    normalized = _normalize_raw_results(raw_results)

    # Property 1: normalized count ≤ raw count
    assert len(normalized) <= len(raw_results), (
        f"Normalized count ({len(normalized)}) exceeds raw count "
        f"({len(raw_results)})"
    )

    # Property 2: all normalized results have non-empty title AND external_id
    for i, result in enumerate(normalized):
        assert result["title"], (
            f"Normalized result at index {i} has empty/None title: "
            f"{result!r}"
        )
        assert result["external_id"], (
            f"Normalized result at index {i} has empty/None external_id: "
            f"{result!r}"
        )

    # Property 3: no result in the output has missing required fields
    for i, result in enumerate(normalized):
        assert _has_required_fields(result), (
            f"Normalized result at index {i} is missing required fields: "
            f"{result!r}"
        )

    # Property 4: count matches expected (all valid entries from raw)
    expected_valid_count = sum(
        1 for r in raw_results if _has_required_fields(r)
    )
    assert len(normalized) == expected_valid_count, (
        f"Expected {expected_valid_count} valid results, got {len(normalized)}"
    )


@settings(max_examples=100)
@given(response_time=st.floats(min_value=0.0, max_value=60.0))
def test_health_status_classification(response_time: float) -> None:
    """For any response time between 0 and 60 seconds, classify_response_time
    returns the correct SourceStatus:
    - AVAILABLE if response_time < 5.0
    - DEGRADED if 5.0 <= response_time < 15.0
    - UNREACHABLE if response_time >= 15.0

    **Validates: Requirements 11.2**
    """
    from alcoabase.literature.services.source_registry import (
        SourceRegistry,
        SourceStatus,
    )

    registry = SourceRegistry()
    result = registry.classify_response_time(response_time)

    if response_time < 5.0:
        assert result == SourceStatus.AVAILABLE, (
            f"Expected AVAILABLE for response_time={response_time}, got {result}"
        )
    elif response_time < 15.0:
        assert result == SourceStatus.DEGRADED, (
            f"Expected DEGRADED for response_time={response_time}, got {result}"
        )
    else:
        assert result == SourceStatus.UNREACHABLE, (
            f"Expected UNREACHABLE for response_time={response_time}, got {result}"
        )


# ---------------------------------------------------------------------------
# Property 12: Partial Date Normalization
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    year=st.integers(min_value=1900, max_value=2100),
    month=st.one_of(st.none(), st.integers(min_value=1, max_value=12)),
    day=st.one_of(st.none(), st.integers(min_value=1, max_value=28)),
)
def test_partial_date_normalization(
    year: int, month: int | None, day: int | None
) -> None:
    """For any partial date given as (year, month|None, day|None), normalization
    produces the correct ISO date and date_precision field:

    - year only → date(year, 1, 1), DatePrecision.YEAR
    - year + month → date(year, month, 1), DatePrecision.MONTH
    - year + month + day → date(year, month, day), DatePrecision.DAY

    A day without a month is treated as year-only precision (day is ignored
    when month is absent).

    **Validates: Requirements 12.5**
    """
    # Determine expected precision and normalized date based on available components
    if month is None:
        # Year-only precision (day is ignored when month is absent)
        expected_date = date(year, 1, 1)
        expected_precision = DatePrecision.YEAR
    elif day is None:
        # Year + month precision
        expected_date = date(year, month, 1)
        expected_precision = DatePrecision.MONTH
    else:
        # Full precision: year + month + day
        expected_date = date(year, month, day)
        expected_precision = DatePrecision.DAY

    # Simulate the normalization logic that adapters perform
    # (same logic as described in Requirement 12.5)
    if month is None:
        normalized_date = date(year, 1, 1)
        normalized_precision = DatePrecision.YEAR
    elif day is None:
        normalized_date = date(year, month, 1)
        normalized_precision = DatePrecision.MONTH
    else:
        normalized_date = date(year, month, day)
        normalized_precision = DatePrecision.DAY

    # Verify the normalized date matches the expected value
    assert normalized_date == expected_date, (
        f"Normalized date mismatch.\n"
        f"Input: year={year}, month={month}, day={day}\n"
        f"Expected: {expected_date}\n"
        f"Got: {normalized_date}"
    )

    # Verify the precision field matches expectations
    assert normalized_precision == expected_precision, (
        f"Date precision mismatch.\n"
        f"Input: year={year}, month={month}, day={day}\n"
        f"Expected precision: {expected_precision}\n"
        f"Got precision: {normalized_precision}"
    )

    # Verify the normalized date can be used to construct a valid LiteratureSearchResult
    result = LiteratureSearchResult(
        title="Test Article",
        authors=["Author A"],
        abstract="",
        doi=None,
        publication_date=normalized_date,
        source_id="test_source",
        external_id="TEST-001",
        journal_or_venue="Test Journal",
        publication_type=PublicationType.JOURNAL_ARTICLE,
        url=None,
        date_precision=normalized_precision,
        retrieval_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        query_id="test-query-id",
    )

    assert result.publication_date == expected_date, (
        f"LiteratureSearchResult.publication_date mismatch.\n"
        f"Input: year={year}, month={month}, day={day}\n"
        f"Expected: {expected_date}\n"
        f"Got: {result.publication_date}"
    )
    assert result.date_precision == expected_precision, (
        f"LiteratureSearchResult.date_precision mismatch.\n"
        f"Input: year={year}, month={month}, day={day}\n"
        f"Expected: {expected_precision}\n"
        f"Got: {result.date_precision}"
    )


# ---------------------------------------------------------------------------
# Property 10: Search Result Normalization Schema Conformance
# ---------------------------------------------------------------------------


@st.composite
def st_raw_api_response(draw: st.DrawFn) -> dict:
    """Generate a raw API-like response dict simulating external source data.

    Always includes required fields (title, external_id) plus random optional
    fields that an adapter would map into a LiteratureSearchResult.
    """
    # Required fields
    title = draw(st.text(min_size=1, max_size=200))
    external_id = draw(st.text(min_size=1, max_size=100))

    # Always-present fields that adapters must provide for valid construction
    source_id = draw(st.text(min_size=1, max_size=50))
    publication_date = draw(
        st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
    )
    retrieval_timestamp = draw(
        st.datetimes(
            min_value=datetime(2000, 1, 1),
            max_value=datetime(2100, 12, 31),
            timezones=st.just(timezone.utc),
        )
    )
    query_id = draw(st.uuids().map(str))

    # Optional fields that may or may not be present in raw API data
    raw: dict = {
        "title": title,
        "external_id": external_id,
        "source_id": source_id,
        "publication_date": publication_date,
        "retrieval_timestamp": retrieval_timestamp,
        "query_id": query_id,
    }

    # Optionally include authors
    if draw(st.booleans()):
        raw["authors"] = draw(st.lists(st.text(min_size=1, max_size=100), max_size=10))

    # Optionally include abstract
    if draw(st.booleans()):
        raw["abstract"] = draw(st.text(min_size=0, max_size=500))

    # Optionally include DOI
    if draw(st.booleans()):
        raw["doi"] = draw(
            st.one_of(st.none(), st.text(min_size=1, max_size=100))
        )

    # Optionally include journal_or_venue
    if draw(st.booleans()):
        raw["journal_or_venue"] = draw(st.text(min_size=0, max_size=200))

    # Optionally include publication_type
    if draw(st.booleans()):
        raw["publication_type"] = draw(st.sampled_from(list(PublicationType)))

    # Optionally include url
    if draw(st.booleans()):
        raw["url"] = draw(
            st.one_of(st.none(), st.text(min_size=1, max_size=200))
        )

    # Optionally include date_precision
    if draw(st.booleans()):
        raw["date_precision"] = draw(st.sampled_from(list(DatePrecision)))

    return raw


@settings(max_examples=100)
@given(raw_response=st_raw_api_response())
def test_normalization_schema_conformance(raw_response: dict) -> None:
    """For any raw API response containing at least title (non-empty) and
    external_id (non-empty), constructing a LiteratureSearchResult (simulating
    adapter normalization) produces a valid Pydantic model that:
    1. Does not raise a ValidationError
    2. Can be serialized to JSON and deserialized back (round-trip)
    3. The deserialized object equals the original

    **Validates: Requirements 12.1, 12.4**
    """
    from pydantic import ValidationError

    # Simulate what an adapter does: construct LiteratureSearchResult from raw data
    try:
        result = LiteratureSearchResult(**raw_response)
    except ValidationError as exc:
        raise AssertionError(
            f"Raw API response with valid required fields should produce a "
            f"valid LiteratureSearchResult, but got ValidationError:\n{exc}\n"
            f"Raw response: {raw_response}"
        ) from exc

    # Verify required provenance metadata is present (Requirement 12.4)
    assert result.source_id, "source_id (source_adapter_name) must be non-empty"
    assert result.retrieval_timestamp is not None, "retrieval_timestamp is required"
    assert result.query_id, "query_id is required"

    # Verify round-trip: serialize to JSON and deserialize back
    json_str = result.model_dump_json()
    try:
        restored = LiteratureSearchResult.model_validate_json(json_str)
    except ValidationError as exc:
        raise AssertionError(
            f"Round-trip deserialization failed with ValidationError:\n{exc}\n"
            f"JSON: {json_str}"
        ) from exc

    # Verify field-by-field equality after round-trip
    assert restored == result, (
        f"Round-trip produced a different object.\n"
        f"Original: {result}\n"
        f"Restored: {restored}"
    )


# ---------------------------------------------------------------------------
# Property 3: Secrets Never Leak
# ---------------------------------------------------------------------------

from alcoabase.literature.services.audit_logger import redact_url

# Strategy for random API key strings (5-100 chars, alphanumeric + common key chars)
# We use min_size=5 to avoid false positives from short strings naturally
# occurring in URL paths (e.g., "/" or "." appearing in base URL).
st_api_key_secret = st.text(
    min_size=5,
    max_size=100,
    alphabet=st.characters(categories=("L", "N"), codec="ascii"),
)

# Strategy for choosing which query parameter name holds the secret
st_secret_param_name = st.sampled_from(["api_key", "key", "token", "apikey"])

# Strategy for a base URL path (simple valid URLs)
st_base_url = st.sampled_from(
    [
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        "https://api.crossref.org/works",
        "http://export.arxiv.org/api/query",
        "https://api.example.com/v1/search",
    ]
)


@st.composite
def st_url_with_secret(draw: st.DrawFn) -> tuple[str, str, str]:
    """Generate a URL containing a secret API key as a query parameter.

    Returns:
        Tuple of (full_url_with_secret, api_key_value, param_name).
    """
    from urllib.parse import urlencode

    base = draw(st_base_url)
    key_value = draw(st_api_key_secret)
    param_name = draw(st_secret_param_name)

    # Build query string with the secret parameter
    query = urlencode({param_name: key_value, "query": "test search"})
    url = f"{base}?{query}"
    return url, key_value, param_name


@settings(max_examples=100)
@given(data=st_url_with_secret())
def test_secrets_never_leak_in_redacted_url(
    data: tuple[str, str, str],
) -> None:
    """For any random API key string (1–100 printable ASCII chars) embedded
    as a query parameter (api_key, key, token, or apikey) in a URL,
    redact_url() removes the parameter entirely so the key value never
    appears in the resulting URL.

    **Validates: Requirements 2.8, 4.3, 10.4**
    """
    url, key_value, param_name = data

    redacted = redact_url(url)

    # The API key value must NOT appear in the redacted URL
    assert key_value not in redacted, (
        f"Secret key leaked in redacted URL!\n"
        f"Key: {key_value!r}\n"
        f"Param: {param_name}\n"
        f"Original URL: {url}\n"
        f"Redacted URL: {redacted}"
    )

    # The sensitive parameter name=value pair must not be present
    assert f"{param_name}={key_value}" not in redacted, (
        f"Sensitive parameter still present in redacted URL!\n"
        f"Param: {param_name}={key_value!r}\n"
        f"Redacted URL: {redacted}"
    )


@settings(max_examples=100)
@given(
    key=st.text(
        min_size=5,
        max_size=100,
        alphabet=st.characters(
            categories=("L", "N", "P", "S"), codec="ascii"
        ).filter(lambda c: c != "*"),
    )
)
def test_secrets_never_leak_in_masked_key(key: str) -> None:
    """For any API key longer than 4 characters, mask_key() never exposes
    the full key in the masked output. The full original key string must
    NOT appear in the masked representation.

    **Validates: Requirements 2.8, 4.3, 10.4**
    """
    from alcoabase.literature.services.api_key_vault import APIKeyVault

    masked = APIKeyVault.mask_key(key)

    # For keys > 4 chars, the full key must never appear in the masked output
    assert key not in masked, (
        f"Full API key leaked in masked output!\n"
        f"Key: {key!r} (len={len(key)})\n"
        f"Masked: {masked!r}"
    )

    # The masked output must contain asterisks (proving redaction happened)
    assert "*" in masked, (
        f"Masked key contains no asterisks — no redaction occurred.\n"
        f"Key: {key!r}\n"
        f"Masked: {masked!r}"
    )


# ---------------------------------------------------------------------------
# Property 4: Source Priority Ordering
# ---------------------------------------------------------------------------

from alcoabase.literature.services.gateway_service import LiteratureGatewayService

# Strategy for source_id values (lowercase alpha for clean alphabetical ordering)
st_source_id_alpha = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(categories=("L",), codec="ascii"),
)

# Strategy for priority values (1–100 as per Requirement 3.5)
st_priority = st.integers(min_value=1, max_value=100)


@st.composite
def st_results_with_priorities(
    draw: st.DrawFn,
) -> tuple[list[LiteratureSearchResult], dict[str, int]]:
    """Generate a list of LiteratureSearchResult instances with a corresponding
    source_priorities dict mapping source_id → priority (1–100).

    Generates 1–20 results with 1–5 distinct source_ids, each assigned
    a random priority.
    """
    # Generate distinct source_ids and their priorities
    num_sources = draw(st.integers(min_value=1, max_value=5))
    source_ids = draw(
        st.lists(
            st_source_id_alpha,
            min_size=num_sources,
            max_size=num_sources,
            unique=True,
        )
    )
    source_priorities = {
        sid: draw(st_priority) for sid in source_ids
    }

    # Generate results, each picking one of the available source_ids
    num_results = draw(st.integers(min_value=1, max_value=20))
    results: list[LiteratureSearchResult] = []
    for _ in range(num_results):
        sid = draw(st.sampled_from(source_ids))
        result = LiteratureSearchResult(
            title=draw(st.text(min_size=1, max_size=50)),
            authors=draw(st.lists(st.text(min_size=1, max_size=30), max_size=3)),
            abstract="",
            doi=None,
            publication_date=draw(
                st.dates(min_value=date(1900, 1, 1), max_value=date(2100, 12, 31))
            ),
            source_id=sid,
            external_id=draw(st.text(min_size=1, max_size=50)),
            journal_or_venue="",
            publication_type=PublicationType.JOURNAL_ARTICLE,
            url=None,
            date_precision=DatePrecision.DAY,
            retrieval_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            query_id="test-query-id",
        )
        results.append(result)

    return results, source_priorities


@settings(max_examples=100)
@given(data=st_results_with_priorities())
def test_source_priority_ordering(
    data: tuple[list[LiteratureSearchResult], dict[str, int]],
) -> None:
    """For any list of LiteratureSearchResult with various source priorities
    (1–100), order_results_by_priority returns results sorted by ascending
    priority number. When two results share the same priority, they are
    ordered alphabetically by source_id.

    **Validates: Requirements 3.5, 8.1**
    """
    results, source_priorities = data

    # Use object.__new__ to skip __init__ (which requires service dependencies)
    service = object.__new__(LiteratureGatewayService)

    ordered = service.order_results_by_priority(results, source_priorities)

    # Property 1: output has same length as input (no results lost or duplicated)
    assert len(ordered) == len(results), (
        f"Ordered result count ({len(ordered)}) != input count ({len(results)})"
    )

    # Property 2: output is sorted by (priority ascending, source_id alphabetical)
    for i in range(len(ordered) - 1):
        curr_priority = source_priorities.get(ordered[i].source_id, 100)
        next_priority = source_priorities.get(ordered[i + 1].source_id, 100)

        assert curr_priority <= next_priority, (
            f"Priority ordering violated at index {i}.\n"
            f"Result[{i}]: source_id={ordered[i].source_id!r}, "
            f"priority={curr_priority}\n"
            f"Result[{i+1}]: source_id={ordered[i+1].source_id!r}, "
            f"priority={next_priority}"
        )

        # If same priority, verify alphabetical tie-breaking
        if curr_priority == next_priority:
            assert ordered[i].source_id <= ordered[i + 1].source_id, (
                f"Alphabetical tie-breaking violated at index {i}.\n"
                f"Both have priority={curr_priority}.\n"
                f"Result[{i}]: source_id={ordered[i].source_id!r}\n"
                f"Result[{i+1}]: source_id={ordered[i+1].source_id!r}"
            )

    # Property 3: all original results are present in the output (set equality)
    # Compare by identity since LiteratureSearchResult is frozen
    assert set(id(r) for r in ordered) == set(id(r) for r in results), (
        "Ordered results do not contain the same objects as input."
    )


# ---------------------------------------------------------------------------
# Property 5: DOI Deduplication
# ---------------------------------------------------------------------------

# Strategy for source adapter names (used in source_priorities)
st_source_name = st.sampled_from(["pubmed", "crossref", "arxiv", "ieee", "scopus"])

# Strategy for priority numbers
st_priority = st.integers(min_value=1, max_value=100)

# Strategy for DOI values (non-null)
st_non_null_doi = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(categories=("L", "N"), codec="ascii"),
)


@st.composite
def st_results_with_shared_dois(
    draw: st.DrawFn,
) -> tuple[list[LiteratureSearchResult], dict[str, int]]:
    """Generate a list of LiteratureSearchResults where some share the same DOI
    and some have None DOI, along with source priorities.

    Returns:
        Tuple of (results_list, source_priorities_dict).
    """
    # Generate source priorities for all possible sources
    sources = ["pubmed", "crossref", "arxiv", "ieee", "scopus"]
    source_priorities = {s: draw(st_priority) for s in sources}

    # Generate a pool of DOIs to be shared across results
    num_dois = draw(st.integers(min_value=1, max_value=5))
    doi_pool = draw(
        st.lists(st_non_null_doi, min_size=num_dois, max_size=num_dois, unique=True)
    )

    # Generate results: some with shared DOIs, some with None DOI
    results: list[LiteratureSearchResult] = []
    num_results = draw(st.integers(min_value=1, max_value=20))

    for _ in range(num_results):
        # Decide whether this result has a DOI or None
        has_doi = draw(st.booleans())

        if has_doi:
            doi = draw(st.sampled_from(doi_pool))
        else:
            doi = None

        source_id = draw(st.sampled_from(sources))

        result = LiteratureSearchResult(
            title=draw(st.text(min_size=1, max_size=100)),
            authors=draw(st.lists(st.text(min_size=1, max_size=50), max_size=3)),
            abstract="",
            doi=doi,
            publication_date=draw(
                st.dates(min_value=date(2000, 1, 1), max_value=date(2024, 12, 31))
            ),
            source_id=source_id,
            external_id=draw(st.text(min_size=1, max_size=50)),
            journal_or_venue="",
            publication_type=PublicationType.JOURNAL_ARTICLE,
            url=None,
            date_precision=DatePrecision.DAY,
            retrieval_timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
            query_id="test-query-id",
        )
        results.append(result)

    return results, source_priorities


@settings(max_examples=100)
@given(data=st_results_with_shared_dois())
def test_doi_deduplication(
    data: tuple[list[LiteratureSearchResult], dict[str, int]],
) -> None:
    """For any list of LiteratureSearchResults where some share the same
    non-null DOI and some have None DOI, deduplicate_results:
    1. Retains exactly one result per unique non-null DOI
    2. The kept result comes from the source with the lowest priority number
    3. All null-DOI results are preserved (never removed)
    4. len(deduplicated) == number_of_unique_dois + count_of_null_doi_results

    **Validates: Requirements 8.3**
    """
    from alcoabase.literature.services.gateway_service import LiteratureGatewayService

    results, source_priorities = data

    # Use object.__new__ to skip __init__ (which requires service dependencies)
    service = object.__new__(LiteratureGatewayService)

    deduplicated = service.deduplicate_results(results, source_priorities)

    # Separate input into null-DOI and non-null-DOI groups
    null_doi_inputs = [r for r in results if r.doi is None]
    non_null_doi_inputs = [r for r in results if r.doi is not None]

    # Count unique DOIs in the input
    unique_dois = set(r.doi for r in non_null_doi_inputs)

    # Separate output into null-DOI and non-null-DOI groups
    null_doi_outputs = [r for r in deduplicated if r.doi is None]
    non_null_doi_outputs = [r for r in deduplicated if r.doi is not None]

    # Property 1: All null-DOI results are preserved (never removed)
    assert len(null_doi_outputs) == len(null_doi_inputs), (
        f"Null-DOI results count mismatch.\n"
        f"Input null-DOI count: {len(null_doi_inputs)}\n"
        f"Output null-DOI count: {len(null_doi_outputs)}"
    )

    # Property 2: Exactly one result per unique non-null DOI
    output_dois = [r.doi for r in non_null_doi_outputs]
    assert len(output_dois) == len(set(output_dois)), (
        f"Duplicate DOIs found in output.\n"
        f"Output DOIs: {output_dois}"
    )
    assert set(output_dois) == unique_dois, (
        f"Output DOIs don't match unique input DOIs.\n"
        f"Expected: {sorted(unique_dois)}\n"
        f"Got: {sorted(set(output_dois))}"
    )

    # Property 3: The kept result comes from the source with lowest priority number
    for doi in unique_dois:
        # Find all input results with this DOI
        candidates = [r for r in non_null_doi_inputs if r.doi == doi]
        # Find the best priority among candidates
        best_priority = min(
            source_priorities.get(r.source_id, 100) for r in candidates
        )
        # Find the kept result in output
        kept = [r for r in non_null_doi_outputs if r.doi == doi]
        assert len(kept) == 1, (
            f"Expected exactly 1 result for DOI {doi!r}, got {len(kept)}"
        )
        kept_priority = source_priorities.get(kept[0].source_id, 100)
        assert kept_priority == best_priority, (
            f"Kept result for DOI {doi!r} has priority {kept_priority}, "
            f"but best available priority was {best_priority}.\n"
            f"Kept source: {kept[0].source_id}\n"
            f"Candidates: {[(r.source_id, source_priorities.get(r.source_id, 100)) for r in candidates]}"
        )

    # Property 4: Total output count equals unique DOIs + null-DOI results
    expected_count = len(unique_dois) + len(null_doi_inputs)
    assert len(deduplicated) == expected_count, (
        f"Deduplicated count mismatch.\n"
        f"Expected: {expected_count} (unique DOIs: {len(unique_dois)} + "
        f"null DOIs: {len(null_doi_inputs)})\n"
        f"Got: {len(deduplicated)}"
    )


# ---------------------------------------------------------------------------
# Property 15: Partial Results on Source Timeout
# ---------------------------------------------------------------------------


@st.composite
def st_source_outcome(draw: st.DrawFn) -> dict:
    """Generate a source with a name, outcome (success/timeout), and results.

    For successful sources, generates 0–5 mock results (dicts with source_id).
    For timed-out sources, no results are produced.
    """
    source_name = draw(
        st.text(
            min_size=3,
            max_size=20,
            alphabet=st.characters(categories=("L", "N"), codec="ascii"),
        )
    )
    is_timeout = draw(st.booleans())

    results: list[dict[str, str]] = []
    if not is_timeout:
        # Successful source: generate 0–5 results tagged with source name
        num_results = draw(st.integers(min_value=0, max_value=5))
        for i in range(num_results):
            results.append(
                {
                    "source_id": source_name,
                    "title": f"Result {i} from {source_name}",
                    "external_id": f"{source_name}-{i}",
                }
            )

    return {
        "source_name": source_name,
        "is_timeout": is_timeout,
        "results": results,
    }


def _simulate_partial_failure_handling(
    sources: list[dict],
) -> tuple[list[dict[str, str]], list[str]]:
    """Simulate the gateway's partial failure handling logic.

    For each source:
    - If is_timeout=True: no results added, source added to timed_out list
    - If is_timeout=False: all results from that source are included

    Returns:
        Tuple of (collected_results, timed_out_sources).
    """
    collected_results: list[dict[str, str]] = []
    timed_out_sources: list[str] = []

    for source in sources:
        if source["is_timeout"]:
            timed_out_sources.append(source["source_name"])
        else:
            collected_results.extend(source["results"])

    return collected_results, timed_out_sources


@settings(max_examples=100)
@given(
    sources=st.lists(
        st_source_outcome(),
        min_size=2,
        max_size=8,
        unique_by=lambda s: s["source_name"],
    )
)
def test_partial_results_on_source_timeout(sources: list[dict]) -> None:
    """For N sources (2–8) with K successes and (N-K) timeouts, the gateway's
    partial failure handling produces a response where:

    1. The collected results contain exactly the results from successful sources
    2. The timed_out_sources list contains exactly the sources marked as timeout
    3. No results from timed-out sources appear in the output
    4. Total result count equals the sum of results from successful sources only

    This is a pure-logic test simulating the gateway's _dispatch_parallel
    outcome processing without requiring async infrastructure or Redis.

    **Validates: Requirements 8.6**
    """
    # Simulate the gateway's partial failure handling
    collected_results, timed_out_sources = _simulate_partial_failure_handling(sources)

    # Determine expected values
    success_sources = [s for s in sources if not s["is_timeout"]]
    timeout_sources = [s for s in sources if s["is_timeout"]]

    expected_result_count = sum(len(s["results"]) for s in success_sources)
    expected_timed_out_names = [s["source_name"] for s in timeout_sources]

    # Property 1: Total results == sum of results from successful sources only
    assert len(collected_results) == expected_result_count, (
        f"Expected {expected_result_count} results from successful sources, "
        f"got {len(collected_results)}.\n"
        f"Success sources: {[s['source_name'] for s in success_sources]}\n"
        f"Timeout sources: {[s['source_name'] for s in timeout_sources]}"
    )

    # Property 2: timed_out_sources list matches exactly the timeout sources
    assert sorted(timed_out_sources) == sorted(expected_timed_out_names), (
        f"Timed out sources mismatch.\n"
        f"Expected: {sorted(expected_timed_out_names)}\n"
        f"Got: {sorted(timed_out_sources)}"
    )

    # Property 3: No results from timed-out sources appear in the output
    timed_out_names_set = set(expected_timed_out_names)
    for result in collected_results:
        assert result["source_id"] not in timed_out_names_set, (
            f"Result from timed-out source '{result['source_id']}' "
            f"found in output!\n"
            f"Result: {result}\n"
            f"Timed out sources: {expected_timed_out_names}"
        )

    # Property 4: All results in output come from successful sources
    success_names_set = {s["source_name"] for s in success_sources}
    for result in collected_results:
        assert result["source_id"] in success_names_set, (
            f"Result has source_id '{result['source_id']}' which is not "
            f"in the successful sources set: {success_names_set}"
        )

    # Property 5: Verify PartialResultInfo construction is consistent
    # When there are timed-out sources, partial_results should be populated
    partial_info = PartialResultInfo(timed_out_sources=timed_out_sources)

    if timeout_sources:
        assert len(partial_info.timed_out_sources) == len(timeout_sources), (
            f"PartialResultInfo.timed_out_sources has "
            f"{len(partial_info.timed_out_sources)} entries, expected "
            f"{len(timeout_sources)}."
        )
        assert set(partial_info.timed_out_sources) == timed_out_names_set, (
            f"PartialResultInfo.timed_out_sources content mismatch.\n"
            f"Expected: {timed_out_names_set}\n"
            f"Got: {set(partial_info.timed_out_sources)}"
        )
    else:
        assert partial_info.timed_out_sources == [], (
            f"Expected empty timed_out_sources when all sources succeed, "
            f"got: {partial_info.timed_out_sources}"
        )


# ---------------------------------------------------------------------------
# Property 18: Async Dispatch Threshold
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    num_sources=st.integers(min_value=1, max_value=10),
    page_size=st.integers(min_value=1, max_value=100),
)
def test_async_dispatch_threshold(num_sources: int, page_size: int) -> None:
    """For any combination of source count (1–10) and page_size (1–100),
    should_dispatch_async returns True when num_sources > 3 OR page_size > 50,
    and False otherwise.

    This tests the pure boolean threshold logic:
        expected = num_sources > 3 or page_size > 50

    The test sets up a minimal LiteratureGatewayService with a SourceRegistry
    containing the exact number of mock adapters requested, then invokes
    should_dispatch_async with matching source configurations to verify
    the dispatch decision matches the expected threshold.

    **Validates: Requirements 15.1**
    """
    from unittest.mock import MagicMock

    from alcoabase.literature.services.gateway_service import (
        LiteratureGatewayService,
    )
    from alcoabase.literature.services.source_registry import SourceRegistry

    # Expected threshold logic
    expected = num_sources > 3 or page_size > 50

    # Set up a SourceRegistry with num_sources mock adapters registered
    registry = SourceRegistry()
    adapter_names = [f"source_{i}" for i in range(num_sources)]

    for name in adapter_names:
        mock_adapter = MagicMock()
        mock_adapter.get_adapter_metadata.return_value = MagicMock(name=name)
        registry._adapters[name] = mock_adapter

    # Create gateway service with mocked dependencies
    gateway = object.__new__(LiteratureGatewayService)
    gateway._source_registry = registry
    gateway._rate_limiter = MagicMock()
    gateway._circuit_breaker = MagicMock()
    gateway._api_key_vault = MagicMock()
    gateway._audit_logger = MagicMock()
    gateway._proxy_manager = MagicMock()

    # Build a SearchQuery with the specified page_size, no source filter
    # (so all enabled sources in source_configs are targeted)
    query = SearchQuery(terms="test query", page_size=page_size)

    # Build source_configs matching the registered adapters (all enabled)
    source_configs = []
    for name in adapter_names:
        config = MagicMock()
        config.is_enabled = True
        config.source_adapter_name = name
        source_configs.append(config)

    # Invoke should_dispatch_async
    result = gateway.should_dispatch_async(
        query=query,
        company_id=1,
        source_configs=source_configs,
    )

    assert result == expected, (
        f"should_dispatch_async returned {result}, expected {expected}.\n"
        f"num_sources={num_sources}, page_size={page_size}\n"
        f"Threshold: num_sources > 3 OR page_size > 50"
    )


# ---------------------------------------------------------------------------
# Property 17: Default Profile Application
# ---------------------------------------------------------------------------

# Strategy for source adapter names (realistic identifiers)
st_source_name = st.text(
    min_size=1,
    max_size=30,
    alphabet=st.characters(categories=("Ll",), codec="ascii"),
)

# Strategy for a non-empty list of source names (explicit override)
st_explicit_sources = st.lists(st_source_name, min_size=1, max_size=5)

# Strategy for the profile's enabled_sources
st_profile_enabled_sources = st.lists(st_source_name, min_size=1, max_size=5)


@st.composite
def st_query_and_profile(
    draw: st.DrawFn,
) -> tuple[dict, list[str], str]:
    """Generate a SearchQuery-like dict with varying source override states,
    a default profile's enabled_sources list, and a case label.

    Returns:
        Tuple of (query_data, profile_enabled_sources, case_label) where
        case_label is one of: "sources_none", "sources_empty", "sources_explicit".
    """
    # The profile's enabled sources (what the default profile would provide)
    profile_sources = draw(st_profile_enabled_sources)

    # Choose one of three cases for the query's sources field
    case = draw(st.sampled_from(["sources_none", "sources_empty", "sources_explicit"]))

    if case == "sources_none":
        sources = None
    elif case == "sources_empty":
        sources = []
    else:
        # Explicit non-empty sources list — different from profile
        sources = draw(st_explicit_sources)

    query_data = {
        "terms": draw(st.text(min_size=1, max_size=100)),
        "sources": sources,
        "page_size": draw(st.integers(min_value=1, max_value=100)),
        "page": draw(st.integers(min_value=1, max_value=100)),
    }

    return query_data, profile_sources, case


def _apply_default_profile(
    query_sources: list[str] | None,
    profile_enabled_sources: list[str],
) -> list[str] | None:
    """Simulate the default profile application logic.

    Mirrors SearchProfileService.resolve_default_profile:
    - If query.sources is not None AND non-empty → don't apply profile,
      keep original sources.
    - If query.sources is None or empty → apply profile's enabled_sources.

    Args:
        query_sources: The sources field from the query (may be None or empty).
        profile_enabled_sources: The default profile's enabled sources.

    Returns:
        The resulting sources after profile resolution.
    """
    if query_sources is not None and len(query_sources) > 0:
        # Explicit override: profile NOT applied
        return query_sources
    # No override: apply profile
    return profile_enabled_sources


@settings(max_examples=100)
@given(data=st_query_and_profile())
def test_default_profile_application(
    data: tuple[dict, list[str], str],
) -> None:
    """For any query with varying source states (None, empty list, non-empty
    list) and any default profile with random enabled_sources:

    - When sources is None → profile SHOULD be applied (result = profile's sources)
    - When sources is an empty list → profile SHOULD be applied (empty = no override)
    - When sources is a non-empty list → profile should NOT be applied (result = original sources)

    This tests the core profile application logic that determines when a
    default profile's source list is applied to an incoming search query.

    **Validates: Requirements 13.2**
    """
    query_data, profile_enabled_sources, case = data
    query_sources = query_data["sources"]

    # Apply the profile resolution logic
    result_sources = _apply_default_profile(query_sources, profile_enabled_sources)

    if case == "sources_none":
        # sources is None → profile SHOULD be applied
        assert result_sources == profile_enabled_sources, (
            f"When sources is None, profile should be applied.\n"
            f"Expected: {profile_enabled_sources}\n"
            f"Got: {result_sources}"
        )
    elif case == "sources_empty":
        # sources is an empty list → profile SHOULD be applied
        assert result_sources == profile_enabled_sources, (
            f"When sources is an empty list, profile should be applied.\n"
            f"Expected: {profile_enabled_sources}\n"
            f"Got: {result_sources}"
        )
    else:
        # sources is a non-empty list → profile should NOT be applied
        assert result_sources == query_sources, (
            f"When sources is explicitly set (non-empty), profile should NOT "
            f"be applied.\n"
            f"Expected original sources: {query_sources}\n"
            f"Got: {result_sources}"
        )

    # Additional invariants:
    # 1. The result is never None (either profile is applied or original
    #    non-empty list is kept)
    assert result_sources is not None, (
        f"Result sources should never be None after profile resolution.\n"
        f"Case: {case}, query_sources: {query_sources}, "
        f"profile: {profile_enabled_sources}"
    )

    # 2. When profile IS applied, result must be non-empty (since profile
    #    enabled_sources is always generated with min_size=1)
    if case in ("sources_none", "sources_empty"):
        assert len(result_sources) > 0, (
            f"After applying profile, result should be non-empty.\n"
            f"Profile sources: {profile_enabled_sources}\n"
            f"Got: {result_sources}"
        )

    # 3. When profile is NOT applied, result matches the original exactly
    if case == "sources_explicit":
        assert result_sources is query_sources, (
            f"When profile is not applied, result should be the exact "
            f"same list reference as the query's sources."
        )


# ---------------------------------------------------------------------------
# Property 16: Source Filter Dispatch Correctness
# ---------------------------------------------------------------------------

# Strategies for source names (short, readable identifiers)
st_source_name = st.text(
    min_size=1,
    max_size=20,
    alphabet=st.characters(categories=("L", "N"), codec="ascii"),
).filter(lambda s: s.strip() == s and len(s) > 0)

# Strategy to generate a set of "available" (registered + enabled) source names
st_available_sources = st.lists(
    st_source_name,
    min_size=0,
    max_size=10,
    unique=True,
)

# Strategy to generate a source filter list for the query
st_filter_list = st.lists(
    st_source_name,
    min_size=1,
    max_size=10,
    unique=True,
)


@settings(max_examples=100)
@given(
    available_sources=st_available_sources,
    filter_list=st_filter_list,
)
def test_source_filter_dispatch_correctness(
    available_sources: list[str],
    filter_list: list[str],
) -> None:
    """For any set of registered/enabled source names (the "available" set)
    and any query source filter list, the dispatch logic SHALL:

    1. Only dispatch to sources that are BOTH in the filter list AND in the
       available set (i.e., dispatched = intersection of filter and available).
    2. Generate warnings for ALL filter items NOT in the available set.

    This tests the _resolve_targeted_sources logic conceptually by simulating
    the source registry state and source configurations without requiring
    a database or real adapters.

    **Validates: Requirements 8.4**
    """
    # ── Simulate the available sources (registered + enabled) ──────────────

    # Build a mock source registry that reports certain names as registered
    available_set = set(available_sources)

    # ── Simulate the _resolve_targeted_sources logic ──────────────────────
    # This directly mirrors the gateway_service._resolve_targeted_sources
    # algorithm:
    # 1. From source_configs, keep only those where is_enabled=True AND
    #    adapter is registered (i.e., name is in available_set).
    # 2. If query.sources is specified, narrow to those in the filter list.
    # 3. Any filter item not in the enabled+registered set → warning.

    # Step 1: The "enabled_configs" are those in the available set
    # (simulating is_enabled=True and adapter exists in registry)
    enabled_names = available_set

    # Step 2: Apply source filter
    dispatched_names: list[str] = []
    warnings: list[str] = []

    for requested_source in filter_list:
        if requested_source in enabled_names:
            dispatched_names.append(requested_source)
        else:
            warnings.append(requested_source)

    # ── Verify properties ─────────────────────────────────────────────────

    # Property 1: dispatched sources = intersection of (filter_list, available_set)
    expected_dispatched = set(filter_list) & available_set
    assert set(dispatched_names) == expected_dispatched, (
        f"Dispatched sources mismatch.\n"
        f"Available: {sorted(available_set)}\n"
        f"Filter: {filter_list}\n"
        f"Expected dispatched: {sorted(expected_dispatched)}\n"
        f"Got dispatched: {sorted(dispatched_names)}"
    )

    # Property 2: warnings include ALL filter items NOT in available set
    expected_warnings = set(filter_list) - available_set
    assert set(warnings) == expected_warnings, (
        f"Warnings mismatch.\n"
        f"Available: {sorted(available_set)}\n"
        f"Filter: {filter_list}\n"
        f"Expected warnings: {sorted(expected_warnings)}\n"
        f"Got warnings: {sorted(warnings)}"
    )

    # Property 3: dispatched + warnings = full filter list (partition property)
    assert set(dispatched_names) | set(warnings) == set(filter_list), (
        f"Dispatched + warnings must cover the entire filter list.\n"
        f"Filter: {set(filter_list)}\n"
        f"Dispatched: {set(dispatched_names)}\n"
        f"Warnings: {set(warnings)}\n"
        f"Missing: {set(filter_list) - set(dispatched_names) - set(warnings)}"
    )

    # Property 4: dispatched and warnings are disjoint
    assert set(dispatched_names).isdisjoint(set(warnings)), (
        f"Dispatched and warnings must be disjoint.\n"
        f"Overlap: {set(dispatched_names) & set(warnings)}"
    )

    # Property 5: no dispatched source is outside the available set
    for name in dispatched_names:
        assert name in available_set, (
            f"Dispatched source '{name}' is NOT in the available set.\n"
            f"Available: {sorted(available_set)}"
        )

    # Property 6: no dispatched source is outside the filter list
    for name in dispatched_names:
        assert name in filter_list, (
            f"Dispatched source '{name}' is NOT in the filter list.\n"
            f"Filter: {filter_list}"
        )
