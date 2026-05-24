"""Property-based tests for deep merge utility.

Tests Property 3: Deep merge preserves non-overridden sibling fields from the
modular-agent-registry-personality-framework design document.

Property 3 validates that for any base dictionary and any overrides dictionary,
deep_merge(base, overrides) correctly:
- Preserves all keys from base that are not present in overrides with their original values
- All keys from overrides appear in result with their override values (for non-dict values)
- For keys present in both where both values are dicts, the result is the recursive deep merge
- The result does not mutate base or overrides

Feature: modular-agent-registry, Property 3: Deep merge preserves non-overridden sibling fields

**Validates: Requirements 2.4, 8.4**

References:
    - Design: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/design.md (Property 3)
    - Requirements: .kiro/specs/Step_5-1_modular-agent-registry-personality-framework/requirements.md
    - Implementation: src/backend/src/alcoabase/services/deep_merge.py
"""

from __future__ import annotations

import copy
from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.services.deep_merge import deep_merge


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for leaf values (non-dict): scalars and arrays
leaf_values: st.SearchStrategy[Any] = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.floats(min_value=-1000.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    st.text(min_size=0, max_size=20),
    st.booleans(),
    st.none(),
    st.lists(st.integers(min_value=-100, max_value=100), min_size=0, max_size=5),
    st.lists(st.text(min_size=1, max_size=10), min_size=0, max_size=5),
)

# Keys for dictionaries
dict_keys: st.SearchStrategy[str] = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
    min_size=1,
    max_size=10,
)


@st.composite
def nested_dict(
    draw: st.DrawFn,
    max_depth: int = 3,
    min_keys: int = 0,
    max_keys: int = 5,
) -> dict[str, Any]:
    """Generate a random nested dictionary.

    Produces dicts where values can be scalars, arrays, or nested dicts
    (up to max_depth levels deep).

    Args:
        max_depth: Maximum nesting depth for dict values.
        min_keys: Minimum number of keys at each level.
        max_keys: Maximum number of keys at each level.

    Returns:
        Strategy producing a nested dictionary.
    """
    num_keys = draw(st.integers(min_value=min_keys, max_value=max_keys))
    keys = draw(st.lists(dict_keys, min_size=num_keys, max_size=num_keys, unique=True))

    result: dict[str, Any] = {}
    for key in keys:
        if max_depth > 1:
            # Mix of leaf values and nested dicts
            value = draw(
                st.one_of(
                    leaf_values,
                    nested_dict(max_depth=max_depth - 1, min_keys=0, max_keys=3),
                )
            )
        else:
            value = draw(leaf_values)
        result[key] = value

    return result


@st.composite
def dict_pair_with_overlap(
    draw: st.DrawFn,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate a pair of dicts that share some keys (to test override behavior).

    Returns:
        Tuple of (base, overrides) where some keys overlap.
    """
    # Generate shared keys
    num_shared = draw(st.integers(min_value=1, max_value=4))
    shared_keys = draw(
        st.lists(dict_keys, min_size=num_shared, max_size=num_shared, unique=True)
    )

    # Generate base-only keys
    num_base_only = draw(st.integers(min_value=0, max_value=3))
    base_only_keys = draw(
        st.lists(
            dict_keys.filter(lambda k: k not in shared_keys),
            min_size=num_base_only,
            max_size=num_base_only,
            unique=True,
        )
    )

    # Generate override-only keys
    num_override_only = draw(st.integers(min_value=0, max_value=3))
    override_only_keys = draw(
        st.lists(
            dict_keys.filter(lambda k: k not in shared_keys and k not in base_only_keys),
            min_size=num_override_only,
            max_size=num_override_only,
            unique=True,
        )
    )

    base: dict[str, Any] = {}
    overrides: dict[str, Any] = {}

    # Populate shared keys with different values
    for key in shared_keys:
        base[key] = draw(nested_dict(max_depth=2, min_keys=1, max_keys=3))
        overrides[key] = draw(nested_dict(max_depth=2, min_keys=1, max_keys=3))

    # Populate base-only keys
    for key in base_only_keys:
        base[key] = draw(leaf_values)

    # Populate override-only keys
    for key in override_only_keys:
        overrides[key] = draw(leaf_values)

    return base, overrides


# ---------------------------------------------------------------------------
# Property 3: Deep merge preserves non-overridden sibling fields
# ---------------------------------------------------------------------------


class TestDeepMergeProperties:
    """Property tests for deep merge utility.

    For any base dictionary and any overrides dictionary, deep_merge(base, overrides)
    SHALL contain all keys from base not present in overrides with their original values,
    all keys from overrides with their override values, and for any key present in both
    where both values are dicts, the result SHALL be the recursive deep merge.

    Feature: modular-agent-registry, Property 3: Deep merge preserves non-overridden sibling fields

    **Validates: Requirements 2.4, 8.4**
    """

    @given(base=nested_dict(max_depth=3, min_keys=1, max_keys=5), overrides=nested_dict(max_depth=3, min_keys=0, max_keys=5))
    @settings(max_examples=100)
    def test_base_keys_not_in_overrides_are_preserved(
        self,
        base: dict[str, Any],
        overrides: dict[str, Any],
    ) -> None:
        """All keys from base that are NOT in overrides appear in result
        with their original values.

        **Validates: Requirements 2.4, 8.4**
        """
        result = deep_merge(base, overrides)

        for key in base:
            if key not in overrides:
                assert key in result, (
                    f"Base key '{key}' not in overrides should be in result"
                )
                assert result[key] == base[key], (
                    f"Base key '{key}' should have original value {base[key]!r}, "
                    f"got {result[key]!r}"
                )

    @given(base=nested_dict(max_depth=3, min_keys=0, max_keys=5), overrides=nested_dict(max_depth=3, min_keys=1, max_keys=5))
    @settings(max_examples=100)
    def test_override_keys_take_precedence(
        self,
        base: dict[str, Any],
        overrides: dict[str, Any],
    ) -> None:
        """All keys from overrides appear in result with their override values
        (for non-dict values or when base value is not a dict).

        **Validates: Requirements 2.4, 8.4**
        """
        result = deep_merge(base, overrides)

        for key in overrides:
            assert key in result, (
                f"Override key '{key}' should be in result"
            )
            base_val = base.get(key)
            override_val = overrides[key]

            if isinstance(base_val, dict) and isinstance(override_val, dict):
                # Recursive case — tested separately
                pass
            else:
                # Scalar/array override replaces entirely
                assert result[key] == override_val, (
                    f"Override key '{key}' should have value {override_val!r}, "
                    f"got {result[key]!r}"
                )

    @given(data=st.data())
    @settings(max_examples=100)
    def test_nested_dicts_are_recursively_merged(
        self,
        data: st.DataObject,
    ) -> None:
        """For keys present in both where both values are dicts, the result
        is the recursive deep merge of those nested dicts.

        **Validates: Requirements 2.4, 8.4**
        """
        base, overrides = data.draw(dict_pair_with_overlap())
        result = deep_merge(base, overrides)

        for key in base:
            if key in overrides:
                base_val = base[key]
                override_val = overrides[key]

                if isinstance(base_val, dict) and isinstance(override_val, dict):
                    # Result should be the recursive deep merge
                    expected = deep_merge(base_val, override_val)
                    assert result[key] == expected, (
                        f"Nested dict at key '{key}' should be recursively merged. "
                        f"Expected {expected!r}, got {result[key]!r}"
                    )

    @given(base=nested_dict(max_depth=3, min_keys=1, max_keys=5), overrides=nested_dict(max_depth=3, min_keys=1, max_keys=5))
    @settings(max_examples=100)
    def test_does_not_mutate_inputs(
        self,
        base: dict[str, Any],
        overrides: dict[str, Any],
    ) -> None:
        """deep_merge does not mutate the base or overrides dictionaries.

        **Validates: Requirements 2.4, 8.4**
        """
        base_copy = copy.deepcopy(base)
        overrides_copy = copy.deepcopy(overrides)

        deep_merge(base, overrides)

        assert base == base_copy, (
            f"base was mutated: original={base_copy!r}, after={base!r}"
        )
        assert overrides == overrides_copy, (
            f"overrides was mutated: original={overrides_copy!r}, after={overrides!r}"
        )
