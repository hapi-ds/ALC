"""Property-based tests for configuration diff computation.

Property 15: Configuration Diff Computation

For any two configuration state dictionaries (current and snapshot), the diff
function SHALL return exactly the set of keys whose values differ between the
two states. Keys present in one but not the other SHALL be included. Keys with
identical values SHALL not be included.

**Validates: Requirements 14.2**

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: .kiro/specs/Step_6-2_admin-system-configuration/requirements.md
    - Module: src/backend/src/alcoabase/services/system_config.py
"""

from __future__ import annotations

from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.schemas.system_config import ConfigDiffItem
from alcoabase.services.system_config import SystemConfigurationService


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Configuration category names (realistic category identifiers)
CATEGORY_NAMES = st.sampled_from([
    "ai_hardware",
    "backup_schedule",
    "backup_retention",
    "health_check",
    "storage_quotas",
    "notifications",
])

# Configuration key names (realistic config key identifiers)
CONFIG_KEYS = st.from_regex(r"[a-z][a-z_]{2,20}", fullmatch=True)

# Configuration values: simple JSON-serializable values
CONFIG_VALUES = st.one_of(
    st.integers(min_value=0, max_value=10000),
    st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
    st.booleans(),
    st.floats(min_value=0.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
)

# A single category dict: maps config keys to values
CATEGORY_DICT = st.dictionaries(
    keys=CONFIG_KEYS,
    values=CONFIG_VALUES,
    min_size=0,
    max_size=8,
)

# A full configuration state: maps category names to category dicts
CONFIG_STATE = st.dictionaries(
    keys=CATEGORY_NAMES,
    values=CATEGORY_DICT,
    min_size=0,
    max_size=4,
)


@st.composite
def st_config_state_pairs(draw: st.DrawFn) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate two independent configuration state dicts."""
    snapshot_data = draw(CONFIG_STATE)
    current_data = draw(CONFIG_STATE)
    return snapshot_data, current_data


@st.composite
def st_config_state_pairs_with_overlap(
    draw: st.DrawFn,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate config state pairs with guaranteed shared categories and keys.

    Ensures we test the case where some keys have identical values and
    some have differing values within the same category.
    """
    # Pick shared categories
    shared_categories = draw(
        st.lists(CATEGORY_NAMES, min_size=1, max_size=3, unique=True)
    )

    snapshot_data: dict[str, Any] = {}
    current_data: dict[str, Any] = {}

    for category in shared_categories:
        # Generate shared keys for this category
        shared_keys = draw(
            st.lists(CONFIG_KEYS, min_size=1, max_size=4, unique=True)
        )

        snapshot_cat: dict[str, Any] = {}
        current_cat: dict[str, Any] = {}

        for key in shared_keys:
            snapshot_cat[key] = draw(CONFIG_VALUES)
            # Sometimes use the same value, sometimes different
            if draw(st.booleans()):
                current_cat[key] = snapshot_cat[key]
            else:
                current_cat[key] = draw(CONFIG_VALUES)

        # Add some keys only in snapshot
        for _ in range(draw(st.integers(min_value=0, max_value=2))):
            key = draw(CONFIG_KEYS.filter(lambda k: k not in snapshot_cat))
            snapshot_cat[key] = draw(CONFIG_VALUES)

        # Add some keys only in current
        for _ in range(draw(st.integers(min_value=0, max_value=2))):
            key = draw(CONFIG_KEYS.filter(lambda k: k not in current_cat and k not in snapshot_cat))
            current_cat[key] = draw(CONFIG_VALUES)

        snapshot_data[category] = snapshot_cat
        current_data[category] = current_cat

    # Optionally add categories only in one state
    if draw(st.booleans()):
        extra_cat = draw(CATEGORY_NAMES.filter(lambda c: c not in snapshot_data))
        snapshot_data[extra_cat] = draw(CATEGORY_DICT)

    if draw(st.booleans()):
        extra_cat = draw(CATEGORY_NAMES.filter(lambda c: c not in current_data))
        current_data[extra_cat] = draw(CATEGORY_DICT)

    return snapshot_data, current_data


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def compute_diff(
    snapshot_data: dict[str, Any], current_data: dict[str, Any]
) -> list[ConfigDiffItem]:
    """Call _compute_diff on SystemConfigurationService.

    _compute_diff is a static/pure function that does not require DB access.
    """
    return SystemConfigurationService._compute_diff(snapshot_data, current_data)


def expected_diff_keys(
    snapshot_data: dict[str, Any], current_data: dict[str, Any]
) -> set[str]:
    """Compute the expected set of dotted keys that should appear in the diff.

    A key "category.key" should appear if and only if the value differs
    between snapshot and current (including presence in one but not the other).
    """
    all_categories = set(list(snapshot_data.keys()) + list(current_data.keys()))
    expected: set[str] = set()

    for category in all_categories:
        snapshot_cat = snapshot_data.get(category, {})
        current_cat = current_data.get(category, {})
        all_keys = set(list(snapshot_cat.keys()) + list(current_cat.keys()))

        for key in all_keys:
            old_value = snapshot_cat.get(key)
            new_value = current_cat.get(key)
            if old_value != new_value:
                expected.add(f"{category}.{key}")

    return expected


# ---------------------------------------------------------------------------
# Property 15: Configuration Diff Computation
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(states=st_config_state_pairs())
def test_diff_returns_exactly_differing_keys(
    states: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The diff SHALL return exactly the set of keys whose values differ
    between the two states.

    **Validates: Requirements 14.2**
    """
    snapshot_data, current_data = states
    diff_items = compute_diff(snapshot_data, current_data)

    actual_keys = {item.key for item in diff_items}
    expected = expected_diff_keys(snapshot_data, current_data)

    assert actual_keys == expected, (
        f"Diff keys mismatch.\n"
        f"  Extra in actual: {actual_keys - expected}\n"
        f"  Missing from actual: {expected - actual_keys}"
    )


@settings(max_examples=100)
@given(states=st_config_state_pairs())
def test_keys_present_in_one_but_not_other_included(
    states: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Keys present in one state but not the other SHALL be included in
    the diff result.

    **Validates: Requirements 14.2**
    """
    snapshot_data, current_data = states
    diff_items = compute_diff(snapshot_data, current_data)
    actual_keys = {item.key for item in diff_items}

    all_categories = set(list(snapshot_data.keys()) + list(current_data.keys()))

    for category in all_categories:
        snapshot_cat = snapshot_data.get(category, {})
        current_cat = current_data.get(category, {})

        # Keys only in snapshot (deleted in current)
        only_in_snapshot = set(snapshot_cat.keys()) - set(current_cat.keys())
        for key in only_in_snapshot:
            dotted_key = f"{category}.{key}"
            assert dotted_key in actual_keys, (
                f"Key '{dotted_key}' present only in snapshot should be in diff"
            )

        # Keys only in current (added since snapshot)
        only_in_current = set(current_cat.keys()) - set(snapshot_cat.keys())
        for key in only_in_current:
            dotted_key = f"{category}.{key}"
            assert dotted_key in actual_keys, (
                f"Key '{dotted_key}' present only in current should be in diff"
            )


@settings(max_examples=100)
@given(states=st_config_state_pairs_with_overlap())
def test_identical_values_excluded_from_diff(
    states: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Keys with identical values in both states SHALL NOT be included
    in the diff result.

    **Validates: Requirements 14.2**
    """
    snapshot_data, current_data = states
    diff_items = compute_diff(snapshot_data, current_data)
    actual_keys = {item.key for item in diff_items}

    all_categories = set(list(snapshot_data.keys()) + list(current_data.keys()))

    for category in all_categories:
        snapshot_cat = snapshot_data.get(category, {})
        current_cat = current_data.get(category, {})

        # Keys present in both with identical values
        common_keys = set(snapshot_cat.keys()) & set(current_cat.keys())
        for key in common_keys:
            if snapshot_cat[key] == current_cat[key]:
                dotted_key = f"{category}.{key}"
                assert dotted_key not in actual_keys, (
                    f"Key '{dotted_key}' with identical value "
                    f"({snapshot_cat[key]!r}) should NOT be in diff"
                )


@settings(max_examples=100)
@given(states=st_config_state_pairs())
def test_diff_items_have_correct_old_and_new_values(
    states: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """Each diff item SHALL report the correct old_value (from snapshot)
    and new_value (from current state).

    **Validates: Requirements 14.2**
    """
    snapshot_data, current_data = states
    diff_items = compute_diff(snapshot_data, current_data)

    for item in diff_items:
        # Parse the dotted key back to category.key
        parts = item.key.split(".", 1)
        assert len(parts) == 2, f"Expected dotted key format, got: {item.key}"
        category, key = parts

        expected_old = snapshot_data.get(category, {}).get(key)
        expected_new = current_data.get(category, {}).get(key)

        assert item.old_value == expected_old, (
            f"Key '{item.key}': expected old_value={expected_old!r}, "
            f"got {item.old_value!r}"
        )
        assert item.new_value == expected_new, (
            f"Key '{item.key}': expected new_value={expected_new!r}, "
            f"got {item.new_value!r}"
        )


@settings(max_examples=100)
@given(states=st_config_state_pairs())
def test_diff_keys_are_unique(
    states: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    """The diff SHALL not contain duplicate keys — each differing key
    appears exactly once.

    **Validates: Requirements 14.2**
    """
    snapshot_data, current_data = states
    diff_items = compute_diff(snapshot_data, current_data)

    keys = [item.key for item in diff_items]
    assert len(keys) == len(set(keys)), (
        f"Duplicate keys found in diff: "
        f"{[k for k in keys if keys.count(k) > 1]}"
    )


@settings(max_examples=100)
@given(state=CONFIG_STATE)
def test_diff_of_identical_states_is_empty(
    state: dict[str, Any],
) -> None:
    """When both states are identical, the diff SHALL return an empty list.

    **Validates: Requirements 14.2**
    """
    import copy

    snapshot_data = copy.deepcopy(state)
    current_data = copy.deepcopy(state)

    diff_items = compute_diff(snapshot_data, current_data)

    assert diff_items == [], (
        f"Diff of identical states should be empty, got {len(diff_items)} items: "
        f"{[item.key for item in diff_items]}"
    )
