"""System configuration service for Admin Dashboard Phase 6.2.

Central service for reading, updating, and persisting system configuration
settings with full audit trail support. Manages configuration snapshots
and rollback, vLLM service restart, and model path validation.

The service follows the pattern: .env provides bootstrap defaults, database
values override at runtime. All mutations create pre-change snapshots for
rollback support.

References:
    - Design: .kiro/specs/Step_6-2_admin-system-configuration/design.md
    - Requirements: 1.3, 1.4, 2.1–2.7, 3.1–3.6, 4.1–4.5, 14.1–14.7
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.models.system_config import (
    ConfigurationSnapshot,
    SystemConfiguration,
)
from alcoabase.models.user import User
from alcoabase.schemas.system_config import (
    AIHardwareConfigUpdate,
    ConfigDiffItem,
    HealthCheckConfigUpdate,
)

logger = logging.getLogger(__name__)

# Configuration categories managed by this service
CATEGORIES = ["ai_hardware", "backup_schedule", "backup_retention", "health_check"]

# Fields that require a vLLM restart when changed
RESTART_REQUIRED_FIELDS = {
    "model_chat_name",
    "model_chat_path",
    "model_chat_max_gpu_memory_gb",
    "model_embedding_name",
    "model_embedding_path",
    "model_embedding_dimension",
    "model_ocr_name",
    "model_ocr_path",
    "inference_mode",
    "gpu_device_id",
}


@dataclass
class ConfigUpdateResult:
    """Result of a configuration update operation.

    Attributes:
        category: The configuration category that was updated.
        updated_values: The new configuration values after the update.
        restart_required: Whether a service restart is needed for changes to take effect.
        snapshot_id: ID of the pre-change snapshot created before the update.
    """

    category: str
    updated_values: dict[str, Any]
    restart_required: bool
    snapshot_id: int


@dataclass
class RollbackResult:
    """Result of a configuration rollback operation.

    Attributes:
        snapshot_id: ID of the snapshot that was restored.
        snapshot_timestamp: ISO timestamp of the restored snapshot.
        acting_user: Username of the user who performed the rollback.
        changed_categories: List of configuration categories that were changed.
        diff: List of configuration differences applied during rollback.
        services_requiring_restart: Services that need restart for changes to take effect.
        new_snapshot_id: ID of the new snapshot recording the rollback action.
    """

    snapshot_id: int
    snapshot_timestamp: str
    acting_user: str
    changed_categories: list[str] = field(default_factory=list)
    diff: list[ConfigDiffItem] = field(default_factory=list)
    services_requiring_restart: list[str] = field(default_factory=list)
    new_snapshot_id: int = 0


@dataclass
class PaginatedSnapshots:
    """Paginated list of configuration snapshots.

    Attributes:
        items: List of snapshot response data.
        total: Total number of snapshots.
        page: Current page number.
        page_size: Number of items per page.
        total_pages: Total number of pages.
    """

    items: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


@dataclass
class ServiceRestartResult:
    """Result of a vLLM service restart operation.

    Attributes:
        success: Whether the restart completed successfully.
        message: Human-readable status message.
        error: Error message if the restart failed.
    """

    success: bool
    message: str
    error: str | None = None


class SystemConfigurationService:
    """Central service for reading and writing system configuration.

    Manages configuration persistence (DB overrides .env), snapshots,
    rollback, vLLM restart, and model path validation.

    All configuration is stored as category-keyed JSON rows in the
    system_configurations table. The .env file provides bootstrap defaults;
    database values take precedence at runtime.
    """

    def _get_env_defaults(self, category: str) -> dict[str, Any]:
        """Get default configuration values from .env/settings for a category.

        Args:
            category: The configuration category to get defaults for.

        Returns:
            Dictionary of default values from environment/settings.
        """
        settings = get_settings()

        if category == "ai_hardware":
            return {
                "model_chat_name": settings.model_chat_name,
                "model_chat_path": settings.model_chat_path,
                "model_chat_max_gpu_memory_gb": settings.model_chat_max_gpu_memory_gb,
                "model_embedding_name": settings.model_embedding_name,
                "model_embedding_path": settings.model_embedding_path,
                "model_embedding_dimension": settings.model_embedding_dimension,
                "model_ocr_name": settings.model_ocr_name,
                "model_ocr_path": settings.model_ocr_path,
                "inference_mode": settings.model_manager_mode,
                "gpu_device_id": settings.gpu_device_id,
                "vllm_chat_url": settings.vllm_base_url,
                "vllm_embedding_url": settings.vllm_embedding_url,
            }
        elif category == "backup_schedule":
            return {
                "cron_expression": "0 2 * * *",  # Daily at 02:00 UTC
            }
        elif category == "backup_retention":
            return {
                "retention_days": 30,
            }
        elif category == "health_check":
            return {
                "polling_interval_seconds": 30,
                "degraded_threshold_seconds": 5,
                "unreachable_timeout_seconds": 10,
            }
        return {}

    async def get_config(
        self, category: str, session: AsyncSession
    ) -> dict[str, Any]:
        """Query SystemConfiguration by category, merge with .env defaults.

        Database values override .env defaults. If no DB row exists for the
        category, returns only the .env defaults.

        Args:
            category: Configuration category (e.g., "ai_hardware").
            session: Active async database session.

        Returns:
            Merged configuration dictionary (DB overrides .env).
        """
        # Start with .env defaults
        defaults = self._get_env_defaults(category)

        # Query DB for overrides
        stmt = select(SystemConfiguration).where(
            SystemConfiguration.category == category
        )
        result = await session.execute(stmt)
        config_row = result.scalar_one_or_none()

        if config_row is not None and config_row.config_values:
            # DB values override .env defaults
            defaults.update(config_row.config_values)

        return defaults

    async def update_config(
        self,
        category: str,
        data: dict[str, Any],
        user_id: int,
        reason: str,
        session: AsyncSession,
    ) -> ConfigUpdateResult:
        """Validate fields per category, create snapshot, update configuration.

        Creates a ConfigurationSnapshot (pre-change) before applying the update.
        Returns a ConfigUpdateResult indicating whether a restart is required.

        Args:
            category: Configuration category to update.
            data: Dictionary of field values to update (only non-None fields).
            user_id: ID of the user performing the update.
            reason: X-Change-Reason for audit trail.
            session: Active async database session.

        Returns:
            ConfigUpdateResult with updated values and restart_required flag.

        Raises:
            ValueError: If validation fails for any field.
        """
        # Validate fields per category
        self._validate_category_fields(category, data)

        # Create pre-change snapshot
        snapshot = await self.create_snapshot(session, user_id=user_id, reason=reason)

        # Get current config row or create one
        stmt = select(SystemConfiguration).where(
            SystemConfiguration.category == category
        )
        result = await session.execute(stmt)
        config_row = result.scalar_one_or_none()

        if config_row is None:
            # Create new row with defaults merged with update
            current_values = self._get_env_defaults(category)
            current_values.update(data)
            config_row = SystemConfiguration(
                category=category,
                config_values=current_values,
                updated_by=user_id,
            )
            session.add(config_row)
        else:
            # Merge update into existing values
            current_values = dict(config_row.config_values) if config_row.config_values else {}
            current_values.update(data)
            config_row.config_values = current_values
            config_row.updated_by = user_id

        await session.flush()

        # Determine if restart is required
        restart_required = any(key in RESTART_REQUIRED_FIELDS for key in data)

        return ConfigUpdateResult(
            category=category,
            updated_values=config_row.config_values,
            restart_required=restart_required,
            snapshot_id=snapshot.id,
        )

    async def create_snapshot(
        self,
        session: AsyncSession,
        user_id: int | None = None,
        reason: str = "Configuration snapshot",
        is_rollback: bool = False,
        rollback_target_id: int | None = None,
    ) -> ConfigurationSnapshot:
        """Capture all configuration categories into a single snapshot.

        Records changed_keys by diffing against the previous snapshot.

        Args:
            session: Active async database session.
            user_id: ID of the user creating the snapshot (optional for system snapshots).
            reason: Reason for the snapshot creation.
            is_rollback: Whether this snapshot is recording a rollback action.
            rollback_target_id: ID of the target snapshot if this is a rollback.

        Returns:
            The created ConfigurationSnapshot instance.
        """
        # Capture all categories
        snapshot_data: dict[str, Any] = {}
        for category in CATEGORIES:
            snapshot_data[category] = await self.get_config(category, session)

        # Compute changed_keys by diffing against previous snapshot
        changed_keys = await self._compute_changed_keys(snapshot_data, session)

        snapshot = ConfigurationSnapshot(
            snapshot_data=snapshot_data,
            created_by=user_id or 0,
            change_reason=reason,
            is_rollback=is_rollback,
            rollback_target_id=rollback_target_id,
            changed_keys=changed_keys,
        )
        session.add(snapshot)
        await session.flush()

        return snapshot

    async def rollback_to_snapshot(
        self,
        snapshot_id: int,
        user_id: int,
        reason: str,
        session: AsyncSession,
    ) -> RollbackResult:
        """Load target snapshot, validate, and restore all categories atomically.

        Validates all values against current validation rules. Rejects entirely
        if any value fails (atomic). Restores all categories and creates a new
        snapshot recording the rollback action.

        Args:
            snapshot_id: ID of the snapshot to restore.
            user_id: ID of the user performing the rollback.
            reason: X-Change-Reason for audit trail.
            session: Active async database session.

        Returns:
            RollbackResult with details of the rollback operation.

        Raises:
            ValueError: If the snapshot is not found or validation fails.
        """
        # Load target snapshot
        stmt = select(ConfigurationSnapshot).where(
            ConfigurationSnapshot.id == snapshot_id
        )
        result = await session.execute(stmt)
        target_snapshot = result.scalar_one_or_none()

        if target_snapshot is None:
            raise ValueError(f"Configuration snapshot not found: {snapshot_id}")

        # Validate all values against current validation rules
        # Reject entirely if any value fails (atomic)
        validation_errors = self._validate_snapshot_values(
            target_snapshot.snapshot_data
        )
        if validation_errors:
            error_details = "; ".join(
                f"{key} failed validation: {msg}"
                for key, msg in validation_errors.items()
            )
            raise ValueError(f"Rollback rejected: {error_details}")

        # Get current state for diff computation
        current_state: dict[str, Any] = {}
        for category in CATEGORIES:
            current_state[category] = await self.get_config(category, session)

        # Compute diff between current state and target snapshot
        diff_items = self._compute_diff(
            target_snapshot.snapshot_data, current_state
        )

        # Determine changed categories
        changed_categories: list[str] = []
        for category in CATEGORIES:
            target_cat = target_snapshot.snapshot_data.get(category, {})
            current_cat = current_state.get(category, {})
            if target_cat != current_cat:
                changed_categories.append(category)

        # Determine services requiring restart
        services_requiring_restart: list[str] = []
        if "ai_hardware" in changed_categories:
            ai_target = target_snapshot.snapshot_data.get("ai_hardware", {})
            ai_current = current_state.get("ai_hardware", {})
            for key in RESTART_REQUIRED_FIELDS:
                if ai_target.get(key) != ai_current.get(key):
                    services_requiring_restart = ["vllm"]
                    break

        # Restore all categories from snapshot
        for category in CATEGORIES:
            target_values = target_snapshot.snapshot_data.get(category, {})
            stmt_config = select(SystemConfiguration).where(
                SystemConfiguration.category == category
            )
            config_result = await session.execute(stmt_config)
            config_row = config_result.scalar_one_or_none()

            if config_row is None:
                config_row = SystemConfiguration(
                    category=category,
                    config_values=target_values,
                    updated_by=user_id,
                )
                session.add(config_row)
            else:
                config_row.config_values = target_values
                config_row.updated_by = user_id

        await session.flush()

        # Create new snapshot recording the rollback action
        rollback_snapshot = await self.create_snapshot(
            session,
            user_id=user_id,
            reason=reason,
            is_rollback=True,
            rollback_target_id=snapshot_id,
        )

        # Get acting user name
        user_stmt = select(User.full_name).where(User.id == user_id)
        user_result = await session.execute(user_stmt)
        acting_user = user_result.scalar_one_or_none() or "Unknown"

        return RollbackResult(
            snapshot_id=snapshot_id,
            snapshot_timestamp=target_snapshot.created_at.isoformat(),
            acting_user=acting_user,
            changed_categories=changed_categories,
            diff=diff_items,
            services_requiring_restart=services_requiring_restart,
            new_snapshot_id=rollback_snapshot.id,
        )

    async def get_snapshot_history(
        self,
        page: int = 1,
        page_size: int = 20,
        session: AsyncSession | None = None,
    ) -> PaginatedSnapshots:
        """Paginated query for configuration snapshots with user names.

        Args:
            page: Page number (1-indexed).
            page_size: Number of items per page (default 20).
            session: Active async database session.

        Returns:
            PaginatedSnapshots with items, total count, and pagination metadata.
        """
        if session is None:
            raise ValueError("Session is required")

        # Count total snapshots
        count_stmt = select(func.count(ConfigurationSnapshot.id))
        count_result = await session.execute(count_stmt)
        total = count_result.scalar_one()

        # Query snapshots with user names
        offset = (page - 1) * page_size
        stmt = (
            select(ConfigurationSnapshot, User.full_name)
            .outerjoin(User, ConfigurationSnapshot.created_by == User.id)
            .order_by(desc(ConfigurationSnapshot.created_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(stmt)
        rows = result.all()

        items = []
        for snapshot, user_name in rows:
            items.append(
                {
                    "id": snapshot.id,
                    "created_at": snapshot.created_at.isoformat(),
                    "created_by_name": user_name or "System",
                    "change_reason": snapshot.change_reason,
                    "is_rollback": snapshot.is_rollback,
                    "changed_keys": snapshot.changed_keys or [],
                }
            )

        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return PaginatedSnapshots(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_snapshot_diff(
        self, snapshot_id: int, session: AsyncSession
    ) -> list[ConfigDiffItem]:
        """Compute diff between a snapshot and the current state.

        Args:
            snapshot_id: ID of the snapshot to compare against current state.
            session: Active async database session.

        Returns:
            List of ConfigDiffItem showing differences.

        Raises:
            ValueError: If the snapshot is not found.
        """
        # Load snapshot
        stmt = select(ConfigurationSnapshot).where(
            ConfigurationSnapshot.id == snapshot_id
        )
        result = await session.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot is None:
            raise ValueError(f"Configuration snapshot not found: {snapshot_id}")

        # Get current state
        current_state: dict[str, Any] = {}
        for category in CATEGORIES:
            current_state[category] = await self.get_config(category, session)

        return self._compute_diff(snapshot.snapshot_data, current_state)

    async def restart_vllm_service(
        self, user_id: int, reason: str
    ) -> ServiceRestartResult:
        """Use Docker SDK to restart vLLM container with 180s timeout.

        Records the restart event in the audit trail.

        Args:
            user_id: ID of the user triggering the restart.
            reason: X-Change-Reason for audit trail.

        Returns:
            ServiceRestartResult indicating success or failure.
        """
        try:
            import docker

            client = docker.DockerClient(
                base_url="unix:///var/run/docker.sock"
            )
            container = client.containers.get("alcoabase-vllm")
            container.restart(timeout=180)

            logger.info(
                "vLLM service restarted by user %d: %s", user_id, reason
            )

            return ServiceRestartResult(
                success=True,
                message="vLLM service restart initiated successfully.",
            )
        except ImportError:
            logger.error("Docker SDK not available")
            return ServiceRestartResult(
                success=False,
                message="Docker SDK not available.",
                error="The docker package is not installed.",
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Failed to restart vLLM service: %s", error_msg
            )
            return ServiceRestartResult(
                success=False,
                message="Failed to restart vLLM service.",
                error=error_msg,
            )

    @staticmethod
    def validate_model_path(path: str) -> bool:
        """Check filesystem existence of a model path.

        Args:
            path: Filesystem path to validate.

        Returns:
            True if the path exists, False otherwise.
        """
        return os.path.exists(path) or Path(path).exists()

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    def _validate_category_fields(
        self, category: str, data: dict[str, Any]
    ) -> None:
        """Validate field values for a specific category.

        Args:
            category: Configuration category being updated.
            data: Dictionary of field values to validate.

        Raises:
            ValueError: If any field fails validation.
        """
        if category == "ai_hardware":
            # Validate using Pydantic schema
            try:
                AIHardwareConfigUpdate(**data)
            except Exception as e:
                raise ValueError(f"AI hardware validation failed: {e}") from e

            # Validate model paths exist on filesystem
            path_fields = [
                "model_chat_path",
                "model_embedding_path",
                "model_ocr_path",
            ]
            for field_name in path_fields:
                if field_name in data and data[field_name] is not None:
                    if not self.validate_model_path(data[field_name]):
                        raise ValueError(
                            f"Model path does not exist: {data[field_name]}"
                        )

        elif category == "backup_schedule":
            # Cron expression validation is handled by BackupService
            cron = data.get("cron_expression")
            if cron is not None and not isinstance(cron, str):
                raise ValueError("cron_expression must be a string")

        elif category == "backup_retention":
            days = data.get("retention_days")
            if days is not None:
                if not isinstance(days, int) or days < 1 or days > 365:
                    raise ValueError(
                        "retention_days must be between 1 and 365"
                    )

        elif category == "health_check":
            try:
                HealthCheckConfigUpdate(**data)
            except Exception as e:
                raise ValueError(
                    f"Health check config validation failed: {e}"
                ) from e

    def _validate_snapshot_values(
        self, snapshot_data: dict[str, Any]
    ) -> dict[str, str]:
        """Validate all values in a snapshot against current validation rules.

        Args:
            snapshot_data: Full snapshot data with all categories.

        Returns:
            Dictionary of validation errors (empty if all valid).
            Keys are dotted paths (e.g., "ai_hardware.gpu_device_id"),
            values are error messages.
        """
        errors: dict[str, str] = {}

        for category, values in snapshot_data.items():
            if category not in CATEGORIES:
                continue

            if category == "ai_hardware":
                # Validate range constraints
                gpu_mem = values.get("model_chat_max_gpu_memory_gb")
                if gpu_mem is not None and (
                    not isinstance(gpu_mem, int) or gpu_mem <= 0
                ):
                    errors["ai_hardware.model_chat_max_gpu_memory_gb"] = (
                        "Must be a positive integer"
                    )

                embed_dim = values.get("model_embedding_dimension")
                if embed_dim is not None and (
                    not isinstance(embed_dim, int) or embed_dim <= 0
                ):
                    errors["ai_hardware.model_embedding_dimension"] = (
                        "Must be a positive integer"
                    )

                gpu_id = values.get("gpu_device_id")
                if gpu_id is not None and (
                    not isinstance(gpu_id, int) or gpu_id < 0
                ):
                    errors["ai_hardware.gpu_device_id"] = (
                        "Must be a non-negative integer"
                    )

                mode = values.get("inference_mode")
                if mode is not None and mode not in ("gpu", "cpu", "mock"):
                    errors["ai_hardware.inference_mode"] = (
                        "Must be one of: gpu, cpu, mock"
                    )

            elif category == "backup_retention":
                days = values.get("retention_days")
                if days is not None and (
                    not isinstance(days, int) or days < 1 or days > 365
                ):
                    errors["backup_retention.retention_days"] = (
                        "Must be between 1 and 365"
                    )

            elif category == "health_check":
                polling = values.get("polling_interval_seconds")
                if polling is not None and (
                    not isinstance(polling, int)
                    or polling < 10
                    or polling > 300
                ):
                    errors["health_check.polling_interval_seconds"] = (
                        "Must be between 10 and 300"
                    )

                degraded = values.get("degraded_threshold_seconds")
                if degraded is not None and (
                    not isinstance(degraded, int)
                    or degraded < 1
                    or degraded > 30
                ):
                    errors["health_check.degraded_threshold_seconds"] = (
                        "Must be between 1 and 30"
                    )

                unreachable = values.get("unreachable_timeout_seconds")
                if unreachable is not None and (
                    not isinstance(unreachable, int)
                    or unreachable < 5
                    or unreachable > 60
                ):
                    errors["health_check.unreachable_timeout_seconds"] = (
                        "Must be between 5 and 60"
                    )

        return errors

    async def _compute_changed_keys(
        self, current_data: dict[str, Any], session: AsyncSession
    ) -> list[str]:
        """Compute changed keys by diffing against the previous snapshot.

        Args:
            current_data: Current configuration state (all categories).
            session: Active async database session.

        Returns:
            List of dotted key paths that differ from the previous snapshot.
        """
        # Get the most recent snapshot
        stmt = (
            select(ConfigurationSnapshot)
            .order_by(desc(ConfigurationSnapshot.created_at))
            .limit(1)
        )
        result = await session.execute(stmt)
        previous_snapshot = result.scalar_one_or_none()

        if previous_snapshot is None:
            # No previous snapshot — all keys are "changed"
            changed: list[str] = []
            for category, values in current_data.items():
                for key in values:
                    changed.append(f"{category}.{key}")
            return changed

        # Diff against previous snapshot
        diff_items = self._compute_diff(
            previous_snapshot.snapshot_data, current_data
        )
        return [item.key for item in diff_items]

    @staticmethod
    def _compute_diff(
        snapshot_data: dict[str, Any], current_data: dict[str, Any]
    ) -> list[ConfigDiffItem]:
        """Compute diff between snapshot state and current state.

        Returns exactly the set of keys whose values differ. Keys present
        in one but not the other are included. Keys with identical values
        are excluded.

        Args:
            snapshot_data: Configuration state from the snapshot.
            current_data: Current configuration state.

        Returns:
            List of ConfigDiffItem for each differing key.
        """
        diff_items: list[ConfigDiffItem] = []

        # Collect all categories from both states
        all_categories = set(list(snapshot_data.keys()) + list(current_data.keys()))

        for category in all_categories:
            snapshot_cat = snapshot_data.get(category, {})
            current_cat = current_data.get(category, {})

            # Collect all keys from both category dicts
            all_keys = set(
                list(snapshot_cat.keys()) + list(current_cat.keys())
            )

            for key in sorted(all_keys):
                old_value = snapshot_cat.get(key)
                new_value = current_cat.get(key)

                if old_value != new_value:
                    diff_items.append(
                        ConfigDiffItem(
                            key=f"{category}.{key}",
                            old_value=old_value,
                            new_value=new_value,
                        )
                    )

        return diff_items
