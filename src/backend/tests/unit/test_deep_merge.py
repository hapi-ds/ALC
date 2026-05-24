"""Unit tests for the deep merge utility."""

import pytest

from alcoabase.services.deep_merge import deep_merge


class TestDeepMerge:
    """Tests for deep_merge function."""

    def test_empty_base_returns_overrides(self) -> None:
        base: dict = {}
        overrides = {"a": 1, "b": 2}
        assert deep_merge(base, overrides) == {"a": 1, "b": 2}

    def test_empty_overrides_returns_base(self) -> None:
        base = {"a": 1, "b": 2}
        overrides: dict = {}
        assert deep_merge(base, overrides) == {"a": 1, "b": 2}

    def test_both_empty_returns_empty(self) -> None:
        assert deep_merge({}, {}) == {}

    def test_scalar_override_replaces_value(self) -> None:
        base = {"x": 1, "y": 2}
        overrides = {"x": 99}
        result = deep_merge(base, overrides)
        assert result == {"x": 99, "y": 2}

    def test_non_overridden_siblings_preserved(self) -> None:
        base = {"a": 1, "b": 2, "c": 3}
        overrides = {"b": 20}
        result = deep_merge(base, overrides)
        assert result["a"] == 1
        assert result["b"] == 20
        assert result["c"] == 3

    def test_array_replaced_entirely(self) -> None:
        base = {"tags": ["alpha", "beta", "gamma"]}
        overrides = {"tags": ["delta"]}
        result = deep_merge(base, overrides)
        assert result["tags"] == ["delta"]

    def test_nested_dict_merged_recursively(self) -> None:
        base = {
            "personality_profile": {
                "tone": "formal",
                "verbosity": "detailed",
                "strictness": 0.9,
                "domain_focus": ["regulatory"],
            }
        }
        overrides = {
            "personality_profile": {
                "strictness": 0.7,
                "domain_focus": ["environmental", "regulatory"],
            }
        }
        result = deep_merge(base, overrides)
        assert result == {
            "personality_profile": {
                "tone": "formal",
                "verbosity": "detailed",
                "strictness": 0.7,
                "domain_focus": ["environmental", "regulatory"],
            }
        }

    def test_override_adds_new_keys(self) -> None:
        base = {"a": 1}
        overrides = {"b": 2}
        result = deep_merge(base, overrides)
        assert result == {"a": 1, "b": 2}

    def test_override_adds_new_nested_keys(self) -> None:
        base = {"config": {"x": 1}}
        overrides = {"config": {"y": 2}}
        result = deep_merge(base, overrides)
        assert result == {"config": {"x": 1, "y": 2}}

    def test_override_dict_replaces_scalar(self) -> None:
        """When override is a dict but base is a scalar, override wins."""
        base = {"x": "scalar"}
        overrides = {"x": {"nested": True}}
        result = deep_merge(base, overrides)
        assert result == {"x": {"nested": True}}

    def test_override_scalar_replaces_dict(self) -> None:
        """When override is a scalar but base is a dict, override wins."""
        base = {"x": {"nested": True}}
        overrides = {"x": "scalar"}
        result = deep_merge(base, overrides)
        assert result == {"x": "scalar"}

    def test_deeply_nested_merge(self) -> None:
        base = {"a": {"b": {"c": {"d": 1, "e": 2}}}}
        overrides = {"a": {"b": {"c": {"d": 99}}}}
        result = deep_merge(base, overrides)
        assert result == {"a": {"b": {"c": {"d": 99, "e": 2}}}}

    def test_does_not_mutate_base(self) -> None:
        base = {"a": {"b": 1}}
        overrides = {"a": {"b": 2}}
        deep_merge(base, overrides)
        assert base == {"a": {"b": 1}}

    def test_does_not_mutate_overrides(self) -> None:
        base = {"a": {"b": 1}}
        overrides = {"a": {"c": 3}}
        deep_merge(base, overrides)
        assert overrides == {"a": {"c": 3}}

    def test_none_value_in_override_replaces(self) -> None:
        base = {"x": 42}
        overrides = {"x": None}
        result = deep_merge(base, overrides)
        assert result == {"x": None}

    def test_design_doc_example(self) -> None:
        """Verify the exact example from the design document."""
        base = {
            "personality_profile": {
                "tone": "formal",
                "verbosity": "detailed",
                "strictness": 0.9,
                "domain_focus": ["regulatory"],
            }
        }
        overrides = {
            "personality_profile": {
                "strictness": 0.7,
                "domain_focus": ["environmental", "regulatory"],
            }
        }
        result = deep_merge(base, overrides)
        expected = {
            "personality_profile": {
                "tone": "formal",
                "verbosity": "detailed",
                "strictness": 0.7,
                "domain_focus": ["environmental", "regulatory"],
            }
        }
        assert result == expected
