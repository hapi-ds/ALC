"""Schema Validator for agent definitions.

Validates agent definition dictionaries against v1.0 or v2.0 JSON Schema,
dispatching to the correct schema based on the `schema_version` field.

References:
    - Requirements: 1.1, 1.6, 1.7, 1.10
    - Design doc Section 1: Schema Validator
"""

import json
import logging
from pathlib import Path
from typing import Any

import jsonschema

logger = logging.getLogger(__name__)

# Supported schema versions
SUPPORTED_VERSIONS = {"1.0", "2.0"}


class SchemaValidator:
    """Validates agent definitions against v1.0 or v2.0 JSON Schema.

    Loads both schema files on initialization and dispatches validation
    to the correct schema based on the `schema_version` field in the data.

    Attributes:
        _schemas: Mapping of version string to loaded JSON Schema dict.
    """

    def __init__(self, schema_dir: Path) -> None:
        """Initialize the SchemaValidator by loading schema files.

        Args:
            schema_dir: Path to the directory containing JSON Schema files.
                Expected files: agent-definition-v1.json, agent-definition-v2.json
        """
        self._schemas: dict[str, dict[str, Any]] = {}
        self._schema_dir = schema_dir

        self._load_schema("1.0", schema_dir / "agent-definition-v1.json")
        self._load_schema("2.0", schema_dir / "agent-definition-v2.json")

    def _load_schema(self, version: str, schema_path: Path) -> None:
        """Load a JSON Schema file for a specific version.

        Args:
            version: The schema version identifier (e.g., "1.0", "2.0").
            schema_path: Path to the JSON Schema file.
        """
        if not schema_path.exists():
            logger.warning(
                "Schema file not found for version %s at %s", version, schema_path
            )
            return

        with open(schema_path) as f:
            self._schemas[version] = json.load(f)

        logger.info("Loaded schema v%s from %s", version, schema_path)

    def validate(self, data: dict[str, Any]) -> list[str]:
        """Validate an agent definition against the appropriate schema.

        Extracts the schema_version from data, checks if it's supported,
        and validates against the corresponding JSON Schema.

        Args:
            data: Agent definition dictionary to validate.

        Returns:
            List of validation error strings. Empty list means valid.
            Each error includes the field path and error message.
        """
        version = self.get_schema_version(data)

        if not self.is_supported_version(version):
            supported = ", ".join(sorted(SUPPORTED_VERSIONS))
            return [
                f"Unsupported schema version '{version}'. "
                f"Supported versions: {supported}"
            ]

        schema = self._schemas.get(version)
        if schema is None:
            return [f"Schema definition not loaded for version '{version}'"]

        errors: list[str] = []
        validator = jsonschema.Draft7Validator(schema)

        for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
            path = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
            errors.append(f"{path}: {error.message}")

        return errors

    def get_schema_version(self, data: dict[str, Any]) -> str:
        """Extract the schema version from an agent definition.

        Args:
            data: Agent definition dictionary.

        Returns:
            The schema_version string, or empty string if not present.
        """
        return data.get("schema_version", "")

    def is_supported_version(self, version: str) -> bool:
        """Check if a schema version is supported.

        Args:
            version: Schema version string to check.

        Returns:
            True if the version is "1.0" or "2.0", False otherwise.
        """
        return version in SUPPORTED_VERSIONS
