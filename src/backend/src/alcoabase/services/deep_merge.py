"""Deep merge utility for recursively merging override dictionaries into base dictionaries."""

from typing import Any


def deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overrides into a base dictionary.

    Produces a new dictionary where override values at any nesting level
    replace corresponding base values. Non-overridden sibling fields are
    preserved from the base. Only dict values are recursively merged;
    scalars and arrays are replaced entirely.

    Args:
        base: The base dictionary providing default values.
        overrides: The dictionary whose values take precedence over base.

    Returns:
        A new merged dictionary. Neither base nor overrides is mutated.
    """
    result: dict[str, Any] = {}

    for key in base:
        if key in overrides:
            base_val = base[key]
            override_val = overrides[key]

            if isinstance(base_val, dict) and isinstance(override_val, dict):
                result[key] = deep_merge(base_val, override_val)
            else:
                result[key] = override_val
        else:
            result[key] = base[key]

    for key in overrides:
        if key not in base:
            result[key] = overrides[key]

    return result
