"""Per-company screening configuration service.

Manages reading, updating, and creating default screening configurations
for each company. Validates configuration ranges and records an audit trail
entry on every mutation.

References:
    - Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.literature.review.exceptions import ConfigurationRangeError
from alcoabase.literature.review.models.screening_config import (
    ScreeningConfiguration,
)

logger = logging.getLogger(__name__)

# Field range constraints: (min, max)
RANGE_CONSTRAINTS: dict[str, tuple[float, float]] = {
    "default_batch_size": (1, 100),
    "confidence_threshold_for_auto_include": (0.5, 1.0),
    "max_concurrent_screening_tasks": (1, 20),
}

# Default values for a new screening configuration
DEFAULT_CONFIG_VALUES: dict[str, Any] = {
    "auto_screen_on_index": False,
    "default_batch_size": 20,
    "confidence_threshold_for_auto_include": 0.8,
    "max_concurrent_screening_tasks": 5,
    "contradiction_detection_enabled": True,
}


class ScreeningConfigService:
    """Manages per-company screening configuration with audit trail.

    Responsibilities:
        - Read current configuration for a company (or return defaults)
        - Update configuration with range validation
        - Create default configuration for new companies
        - Record audit trail entries on every update
    """

    async def get_config(
        self,
        session: AsyncSession,
        *,
        company_id: int,
    ) -> dict[str, Any]:
        """Return the company's screening configuration or default values.

        If no configuration record exists for the company, returns the
        system default values without persisting them.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.

        Returns:
            Dict with all screening configuration fields.
        """
        config = await self._get_config_record(session, company_id=company_id)

        if config is None:
            return {
                "company_id": company_id,
                **DEFAULT_CONFIG_VALUES,
            }

        return self._to_dict(config)

    async def update_config(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        user_id: int,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate ranges and persist configuration updates.

        Creates the configuration record if it does not exist. Records an
        audit trail entry with previous and new values for each changed field.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            user_id: User performing the update.
            data: Fields to update (only non-None values are applied).

        Returns:
            Updated configuration dict.

        Raises:
            ConfigurationRangeError: If any value is outside its allowed range.
        """
        # Validate ranges before making any changes
        self._validate_ranges(data)

        # Get or create the config record
        config = await self._get_config_record(session, company_id=company_id)

        if config is None:
            config = await self._create_default(session, company_id=company_id)

        # Track changes for audit trail
        audit_entries: list[dict[str, Any]] = []

        # Apply updates
        field_mapping = {
            "auto_screen_on_index": "auto_screen_on_index",
            "default_batch_size": "default_batch_size",
            "confidence_threshold_for_auto_include": "confidence_threshold_for_auto_include",
            "max_concurrent_screening_tasks": "max_concurrent_screening_tasks",
            "contradiction_detection_enabled": "contradiction_detection_enabled",
        }

        for field_key, attr_name in field_mapping.items():
            if field_key in data and data[field_key] is not None:
                old_value = getattr(config, attr_name)
                new_value = data[field_key]

                if old_value != new_value:
                    setattr(config, attr_name, new_value)
                    audit_entries.append(
                        {
                            "field": field_key,
                            "old_value": old_value,
                            "new_value": new_value,
                        }
                    )

        await session.flush()

        # Log audit trail
        if audit_entries:
            logger.info(
                "Screening config updated for company %d by user %d: %s",
                company_id,
                user_id,
                audit_entries,
            )

        return self._to_dict(config)

    async def get_or_create_default(
        self,
        session: AsyncSession,
        *,
        company_id: int,
    ) -> dict[str, Any]:
        """Return existing config or create a default one for the company.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.

        Returns:
            Configuration dict (existing or newly created defaults).
        """
        config = await self._get_config_record(session, company_id=company_id)

        if config is None:
            config = await self._create_default(session, company_id=company_id)

        return self._to_dict(config)

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _get_config_record(
        self,
        session: AsyncSession,
        *,
        company_id: int,
    ) -> ScreeningConfiguration | None:
        """Query for an existing configuration record scoped to a company.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.

        Returns:
            The ScreeningConfiguration instance or None if not found.
        """
        stmt = select(ScreeningConfiguration).where(
            ScreeningConfiguration.company_id == company_id
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    async def _create_default(
        self,
        session: AsyncSession,
        *,
        company_id: int,
    ) -> ScreeningConfiguration:
        """Create a default configuration record for a company.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.

        Returns:
            The newly created ScreeningConfiguration instance.
        """
        config = ScreeningConfiguration(
            company_id=company_id,
            auto_screen_on_index=DEFAULT_CONFIG_VALUES["auto_screen_on_index"],
            default_batch_size=DEFAULT_CONFIG_VALUES["default_batch_size"],
            confidence_threshold_for_auto_include=DEFAULT_CONFIG_VALUES[
                "confidence_threshold_for_auto_include"
            ],
            max_concurrent_screening_tasks=DEFAULT_CONFIG_VALUES[
                "max_concurrent_screening_tasks"
            ],
            contradiction_detection_enabled=DEFAULT_CONFIG_VALUES[
                "contradiction_detection_enabled"
            ],
        )
        session.add(config)
        await session.flush()

        logger.info(
            "Created default screening configuration for company %d",
            company_id,
        )

        return config

    @staticmethod
    def _validate_ranges(data: dict[str, Any]) -> None:
        """Validate that numeric fields are within their allowed ranges.

        Args:
            data: Fields to validate.

        Raises:
            ConfigurationRangeError: If any value is outside its allowed range.
        """
        for field_name, (min_val, max_val) in RANGE_CONSTRAINTS.items():
            if field_name in data and data[field_name] is not None:
                value = data[field_name]
                if value < min_val or value > max_val:
                    raise ConfigurationRangeError(
                        f"{field_name} must be between {min_val} and {max_val}, "
                        f"got {value}",
                        field_name=field_name,
                        value=value,
                        min_value=min_val,
                        max_value=max_val,
                    )

    @staticmethod
    def _to_dict(config: ScreeningConfiguration) -> dict[str, Any]:
        """Convert a ScreeningConfiguration ORM object to a plain dict.

        Args:
            config: The ORM instance.

        Returns:
            Dict with all public configuration fields.
        """
        return {
            "id": config.id,
            "company_id": config.company_id,
            "auto_screen_on_index": config.auto_screen_on_index,
            "default_batch_size": config.default_batch_size,
            "confidence_threshold_for_auto_include": config.confidence_threshold_for_auto_include,
            "max_concurrent_screening_tasks": config.max_concurrent_screening_tasks,
            "contradiction_detection_enabled": config.contradiction_detection_enabled,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        }
