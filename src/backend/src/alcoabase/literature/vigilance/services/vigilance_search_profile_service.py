"""CRUD and scheduling for Vigilance Search Profiles.

Manages profile creation with cron validation, status lifecycle transitions,
dynamic Celery beat registration/deregistration, and manual execution dispatch.

References:
    - Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from alcoabase.literature.vigilance.exceptions import (
    InvalidCronExpressionError,
    ProductNotFoundError,
    ProfileNotFoundError,
)
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_search_profile import (
    VigilanceSearchProfile,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

# Dedicated audit logger for vigilance operations — separate from application
# loggers for independent routing/filtering in production log infrastructure.
audit_logger = logging.getLogger("alcoabase.audit.vigilance")

# ---------------------------------------------------------------------------
# Cron validation constants
# ---------------------------------------------------------------------------

# Valid ranges for each of the 5 cron fields
_CRON_FIELD_RANGES = (
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 7),    # day of week (0 and 7 both represent Sunday)
)

# Regex pattern for a single cron field value (number, range, step, wildcard, list)
_CRON_FIELD_PATTERN = re.compile(
    r"^(\*|(\d+(-\d+)?)(,\d+(-\d+)?)*)(\/\d+)?$"
)


class VigilanceSearchProfileService:
    """Manages Vigilance Search Profile lifecycle and scheduling.

    Responsibilities:
        - Create profiles with validated cron expressions and required arrays
        - Register/deregister profiles with Celery beat scheduler
        - Manage status transitions (active → paused → archived)
        - Auto-pause profiles for discontinued/recalled products
        - Support manual (on-demand) execution regardless of status
        - Load all active profiles on startup for dynamic beat registration
    """

    VALID_STATUSES = ("active", "paused", "archived")
    _INACTIVE_PRODUCT_STATUSES = ("discontinued", "recalled")

    def __init__(
        self,
        session_factory: "async_sessionmaker",
    ) -> None:
        """Initialize with async session factory.

        Args:
            session_factory: Async session factory for DB operations.
        """
        self._session_factory = session_factory

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    async def create_profile(
        self,
        session: "AsyncSession",
        *,
        company_id: int,
        user_id: int,
        product_id: int,
        name: str,
        search_terms: list[str],
        adverse_event_keywords: list[str],
        mesh_terms: list[str] | None = None,
        device_identifiers: list[str] | None = None,
        exclusion_terms: list[str] | None = None,
        source_ids: list[str] | None = None,
        schedule_cron: str = "0 6 * * 1",
    ) -> dict[str, Any]:
        """Create a new Vigilance Search Profile.

        Validates cron expression, required arrays, product existence.
        If product is discontinued/recalled, sets status to 'paused'.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            user_id: Creating user (must have document_admin or system_admin role).
            product_id: FK to MedicalProduct.
            name: Profile name (1–200 chars).
            search_terms: Product names/synonyms (1–50, each 1–500 chars).
            adverse_event_keywords: AE descriptors (1–50, each 1–500 chars).
            mesh_terms: Optional MeSH terms (0–30, each 1–200 chars).
            device_identifiers: Optional UDIs/catalog numbers (0–20, each 1–200 chars).
            exclusion_terms: Optional exclusion terms (0–30, each 1–500 chars).
            source_ids: Optional source adapter IDs (empty = all).
            schedule_cron: 5-field cron expression.

        Returns:
            Dict with created profile fields + id.

        Raises:
            InvalidCronExpressionError: If cron expression is invalid.
            ProductNotFoundError: If product_id not found in company.
            ValueError: If required arrays are empty or exceed limits.
        """
        # Step 1: Validate cron expression
        self.validate_cron_expression(schedule_cron)

        # Step 2: Validate required arrays
        self._validate_arrays(
            search_terms=search_terms,
            adverse_event_keywords=adverse_event_keywords,
            mesh_terms=mesh_terms,
            device_identifiers=device_identifiers,
            exclusion_terms=exclusion_terms,
        )

        # Step 3: Verify product exists in company
        product = await self._get_product(session, product_id=product_id, company_id=company_id)

        # Step 4: Determine initial status — auto-pause if product inactive
        initial_status = "active"
        if product.status in self._INACTIVE_PRODUCT_STATUSES:
            initial_status = "paused"
            logger.info(
                "Auto-pausing profile for discontinued/recalled product: "
                "product_id=%d, company_id=%d, product_status=%s",
                product_id,
                company_id,
                product.status,
            )

        # Step 5: Persist profile
        profile = VigilanceSearchProfile(
            company_id=company_id,
            product_id=product_id,
            name=name,
            search_terms=search_terms,
            adverse_event_keywords=adverse_event_keywords,
            mesh_terms=mesh_terms,
            device_identifiers=device_identifiers,
            exclusion_terms=exclusion_terms,
            source_ids=source_ids,
            schedule_cron=schedule_cron,
            status=initial_status,
            created_by=user_id,
        )
        session.add(profile)
        await session.flush()

        # Step 6: Register with Celery beat if active
        if initial_status == "active":
            self._register_beat_schedule(profile)

        # Step 7: Audit trail
        audit_logger.info(
            "Vigilance search profile created",
            extra={
                "event_type": "vigilance.profile_created",
                "profile_id": profile.id,
                "product_id": product_id,
                "company_id": company_id,
                "user_id": user_id,
                "status": initial_status,
                "schedule_cron": schedule_cron,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return self._profile_to_dict(profile)

    async def update_profile(
        self,
        session: "AsyncSession",
        *,
        profile_id: int,
        company_id: int,
        user_id: int,
        name: str | None = None,
        search_terms: list[str] | None = None,
        adverse_event_keywords: list[str] | None = None,
        mesh_terms: list[str] | None = None,
        device_identifiers: list[str] | None = None,
        exclusion_terms: list[str] | None = None,
        source_ids: list[str] | None = None,
        schedule_cron: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing Vigilance Search Profile.

        Validates same constraints as creation. Re-registers Celery beat
        if schedule_cron changes and profile is active.

        Args:
            session: Active async DB session.
            profile_id: Target profile.
            company_id: Tenant scope.
            user_id: Updating user.
            name: Updated name (1–200 chars).
            search_terms: Updated search terms (1–50, each 1–500 chars).
            adverse_event_keywords: Updated AE keywords (1–50, each 1–500 chars).
            mesh_terms: Updated MeSH terms (0–30, each 1–200 chars).
            device_identifiers: Updated identifiers (0–20, each 1–200 chars).
            exclusion_terms: Updated exclusion terms (0–30, each 1–500 chars).
            source_ids: Updated source adapter IDs.
            schedule_cron: Updated 5-field cron expression.

        Returns:
            Updated profile dict.

        Raises:
            ProfileNotFoundError: If profile not found in company.
            InvalidCronExpressionError: If new cron expression is invalid.
            ValueError: If arrays violate constraints.
        """
        profile = await self._get_profile(session, profile_id=profile_id, company_id=company_id)

        changed_fields: dict[str, Any] = {}

        # Validate and apply cron if changed
        if schedule_cron is not None:
            self.validate_cron_expression(schedule_cron)
            profile.schedule_cron = schedule_cron
            changed_fields["schedule_cron"] = schedule_cron

        # Validate arrays if provided
        effective_search_terms = search_terms if search_terms is not None else profile.search_terms
        effective_ae_keywords = (
            adverse_event_keywords
            if adverse_event_keywords is not None
            else profile.adverse_event_keywords
        )
        self._validate_arrays(
            search_terms=effective_search_terms,
            adverse_event_keywords=effective_ae_keywords,
            mesh_terms=mesh_terms if mesh_terms is not None else profile.mesh_terms,
            device_identifiers=(
                device_identifiers if device_identifiers is not None else profile.device_identifiers
            ),
            exclusion_terms=(
                exclusion_terms if exclusion_terms is not None else profile.exclusion_terms
            ),
        )

        # Apply field updates
        if name is not None:
            profile.name = name
            changed_fields["name"] = name
        if search_terms is not None:
            profile.search_terms = search_terms
            changed_fields["search_terms"] = search_terms
        if adverse_event_keywords is not None:
            profile.adverse_event_keywords = adverse_event_keywords
            changed_fields["adverse_event_keywords"] = adverse_event_keywords
        if mesh_terms is not None:
            profile.mesh_terms = mesh_terms
            changed_fields["mesh_terms"] = mesh_terms
        if device_identifiers is not None:
            profile.device_identifiers = device_identifiers
            changed_fields["device_identifiers"] = device_identifiers
        if exclusion_terms is not None:
            profile.exclusion_terms = exclusion_terms
            changed_fields["exclusion_terms"] = exclusion_terms
        if source_ids is not None:
            profile.source_ids = source_ids
            changed_fields["source_ids"] = source_ids

        await session.flush()

        # Re-register with Celery beat if cron changed and profile is active
        if "schedule_cron" in changed_fields and profile.status == "active":
            self._deregister_beat_schedule(profile.id)
            self._register_beat_schedule(profile)

        # Audit trail
        audit_logger.info(
            "Vigilance search profile updated",
            extra={
                "event_type": "vigilance.profile_updated",
                "profile_id": profile_id,
                "company_id": company_id,
                "user_id": user_id,
                "changed_fields": list(changed_fields.keys()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return self._profile_to_dict(profile)

    async def activate_profile(
        self,
        session: "AsyncSession",
        *,
        profile_id: int,
        company_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """Activate a profile and register with Celery beat.

        Transitions profile to active status and registers its cron schedule
        with the Celery beat scheduler. Enforces that the associated product
        must not be discontinued or recalled.

        Args:
            session: Active async DB session.
            profile_id: Target profile.
            company_id: Tenant scope.
            user_id: Activating user.

        Returns:
            Updated profile dict.

        Raises:
            ProfileNotFoundError: If profile not found in company.
            ValueError: If product is discontinued/recalled.
        """
        profile = await self._get_profile(session, profile_id=profile_id, company_id=company_id)

        # Enforce product status constraint
        product = await self._get_product(
            session, product_id=profile.product_id, company_id=company_id
        )
        if product.status in self._INACTIVE_PRODUCT_STATUSES:
            raise ValueError(
                f"Cannot activate profile: associated product '{product.name}' "
                f"has status '{product.status}'. Product must be active."
            )

        previous_status = profile.status
        profile.status = "active"
        await session.flush()

        # Register with Celery beat
        self._register_beat_schedule(profile)

        # Audit trail
        audit_logger.info(
            "Vigilance search profile activated",
            extra={
                "event_type": "vigilance.profile_status_change",
                "profile_id": profile_id,
                "company_id": company_id,
                "user_id": user_id,
                "previous_status": previous_status,
                "new_status": "active",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return self._profile_to_dict(profile)

    async def pause_profile(
        self,
        session: "AsyncSession",
        *,
        profile_id: int,
        company_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """Pause a profile and remove from Celery beat.

        Transitions profile to paused status and removes its schedule from
        the Celery beat scheduler. All historical execution records are preserved.

        Args:
            session: Active async DB session.
            profile_id: Target profile.
            company_id: Tenant scope.
            user_id: Pausing user.

        Returns:
            Updated profile dict.

        Raises:
            ProfileNotFoundError: If profile not found in company.
        """
        profile = await self._get_profile(session, profile_id=profile_id, company_id=company_id)

        previous_status = profile.status
        profile.status = "paused"
        await session.flush()

        # Remove from Celery beat
        self._deregister_beat_schedule(profile.id)

        # Audit trail
        audit_logger.info(
            "Vigilance search profile paused",
            extra={
                "event_type": "vigilance.profile_status_change",
                "profile_id": profile_id,
                "company_id": company_id,
                "user_id": user_id,
                "previous_status": previous_status,
                "new_status": "paused",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return self._profile_to_dict(profile)

    async def archive_profile(
        self,
        session: "AsyncSession",
        *,
        profile_id: int,
        company_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """Archive a profile and remove from Celery beat.

        Transitions profile to archived status and removes its schedule from
        the Celery beat scheduler. Archived profiles cannot be reactivated.

        Args:
            session: Active async DB session.
            profile_id: Target profile.
            company_id: Tenant scope.
            user_id: Archiving user.

        Returns:
            Updated profile dict.

        Raises:
            ProfileNotFoundError: If profile not found in company.
        """
        profile = await self._get_profile(session, profile_id=profile_id, company_id=company_id)

        previous_status = profile.status
        profile.status = "archived"
        await session.flush()

        # Remove from Celery beat
        self._deregister_beat_schedule(profile.id)

        # Audit trail
        audit_logger.info(
            "Vigilance search profile archived",
            extra={
                "event_type": "vigilance.profile_status_change",
                "profile_id": profile_id,
                "company_id": company_id,
                "user_id": user_id,
                "previous_status": previous_status,
                "new_status": "archived",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return self._profile_to_dict(profile)

    async def trigger_manual_execution(
        self,
        session: "AsyncSession",
        *,
        profile_id: int,
        company_id: int,
        user_id: int,
    ) -> str:
        """Trigger immediate execution regardless of profile status.

        Dispatches a Celery task for immediate search execution and returns
        the task_id for progress tracking. Works regardless of whether the
        profile is active, paused, or archived.

        Args:
            session: Active async DB session.
            profile_id: Target profile.
            company_id: Tenant scope.
            user_id: Triggering user.

        Returns:
            task_id (string) for progress tracking.

        Raises:
            ProfileNotFoundError: If profile not found in company.
        """
        # Verify profile exists in company
        profile = await self._get_profile(session, profile_id=profile_id, company_id=company_id)

        # Dispatch Celery task
        from alcoabase.tasks.celery_app import celery_app

        result = celery_app.send_task(
            "alcoabase.tasks.vigilance_tasks.execute_vigilance_search",
            kwargs={
                "profile_id": profile.id,
                "company_id": company_id,
            },
            queue="literature_ingestion",
        )

        task_id = str(result.id)

        # Audit trail
        audit_logger.info(
            "Vigilance search manual execution triggered",
            extra={
                "event_type": "vigilance.manual_execution_triggered",
                "profile_id": profile_id,
                "company_id": company_id,
                "user_id": user_id,
                "task_id": task_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return task_id

    async def register_all_active_schedules(self) -> int:
        """Load all active profiles and register with Celery beat.

        Called on application/worker startup and scheduler restart.
        Loads all profiles with status 'active' from the database and
        registers their cron schedules with the Celery beat scheduler.

        Returns:
            Number of profiles registered.
        """
        async with self._session_factory() as session:
            stmt = select(VigilanceSearchProfile).where(
                VigilanceSearchProfile.status == "active"
            )
            result = await session.execute(stmt)
            active_profiles = result.scalars().all()

            registered_count = 0
            for profile in active_profiles:
                try:
                    self._register_beat_schedule(profile)
                    registered_count += 1
                except Exception:
                    logger.exception(
                        "Failed to register beat schedule for profile_id=%d",
                        profile.id,
                    )

            logger.info(
                "Registered %d active vigilance schedules on startup",
                registered_count,
            )

            return registered_count

    def validate_cron_expression(self, expression: str) -> bool:
        """Validate a 5-field cron expression.

        Checks syntax for minute, hour, day-of-month, month, day-of-week.
        Each field supports: numbers, ranges (1-5), steps (*/2), lists (1,3,5),
        and wildcards (*).

        Args:
            expression: Cron expression string to validate.

        Returns:
            True if valid.

        Raises:
            InvalidCronExpressionError: If the expression is invalid.
        """
        expression = expression.strip()
        fields = expression.split()

        if len(fields) != 5:
            raise InvalidCronExpressionError(
                f"Cron expression must have exactly 5 fields (minute hour "
                f"day_of_month month day_of_week), got {len(fields)}: '{expression}'",
                expression=expression,
            )

        field_names = ("minute", "hour", "day_of_month", "month", "day_of_week")

        for i, (field, (min_val, max_val)) in enumerate(
            zip(fields, _CRON_FIELD_RANGES)
        ):
            self._validate_cron_field(
                field, field_names[i], min_val, max_val, expression
            )

        return True

    # -----------------------------------------------------------------------
    # Internal: Celery Beat Registration
    # -----------------------------------------------------------------------

    def _register_beat_schedule(self, profile: VigilanceSearchProfile) -> None:
        """Register a profile's cron schedule with Celery beat.

        Creates a dynamic beat_schedule entry keyed by the profile ID.

        Args:
            profile: The active profile to register.
        """
        from celery.schedules import crontab

        from alcoabase.tasks.celery_app import celery_app

        schedule_key = f"vigilance-search-profile-{profile.id}"
        parts = profile.schedule_cron.strip().split()

        celery_app.conf.beat_schedule[schedule_key] = {
            "task": "alcoabase.tasks.vigilance_tasks.execute_vigilance_search",
            "schedule": crontab(
                minute=parts[0],
                hour=parts[1],
                day_of_month=parts[2],
                month_of_year=parts[3],
                day_of_week=parts[4],
            ),
            "kwargs": {
                "profile_id": profile.id,
                "company_id": profile.company_id,
            },
            "options": {"queue": "literature_ingestion"},
        }

        logger.debug(
            "Registered Celery beat schedule: key=%s, cron=%s, profile_id=%d",
            schedule_key,
            profile.schedule_cron,
            profile.id,
        )

    def _deregister_beat_schedule(self, profile_id: int) -> None:
        """Remove a profile's schedule from Celery beat.

        Args:
            profile_id: The profile whose schedule should be removed.
        """
        from alcoabase.tasks.celery_app import celery_app

        schedule_key = f"vigilance-search-profile-{profile_id}"
        celery_app.conf.beat_schedule.pop(schedule_key, None)

        logger.debug(
            "Deregistered Celery beat schedule: key=%s, profile_id=%d",
            schedule_key,
            profile_id,
        )

    # -----------------------------------------------------------------------
    # Internal: Helpers
    # -----------------------------------------------------------------------

    async def _get_profile(
        self,
        session: "AsyncSession",
        *,
        profile_id: int,
        company_id: int,
    ) -> VigilanceSearchProfile:
        """Load a profile by ID scoped to company.

        Args:
            session: Active DB session.
            profile_id: Target profile ID.
            company_id: Tenant scope.

        Returns:
            VigilanceSearchProfile instance.

        Raises:
            ProfileNotFoundError: If not found within the company.
        """
        stmt = select(VigilanceSearchProfile).where(
            VigilanceSearchProfile.id == profile_id,
            VigilanceSearchProfile.company_id == company_id,
        )
        result = await session.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile is None:
            raise ProfileNotFoundError(
                f"Vigilance search profile {profile_id} not found in company {company_id}",
                profile_id=profile_id,
                company_id=company_id,
            )

        return profile

    async def _get_product(
        self,
        session: "AsyncSession",
        *,
        product_id: int,
        company_id: int,
    ) -> MedicalProduct:
        """Load a product by ID scoped to company.

        Args:
            session: Active DB session.
            product_id: Target product ID.
            company_id: Tenant scope.

        Returns:
            MedicalProduct instance.

        Raises:
            ProductNotFoundError: If not found within the company.
        """
        stmt = select(MedicalProduct).where(
            MedicalProduct.id == product_id,
            MedicalProduct.company_id == company_id,
        )
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()

        if product is None:
            raise ProductNotFoundError(
                f"Medical product {product_id} not found in company {company_id}",
                product_id=product_id,
                company_id=company_id,
            )

        return product

    def _validate_arrays(
        self,
        *,
        search_terms: list[str],
        adverse_event_keywords: list[str],
        mesh_terms: list[str] | None,
        device_identifiers: list[str] | None,
        exclusion_terms: list[str] | None,
    ) -> None:
        """Validate array field constraints.

        Args:
            search_terms: Must have 1–50 entries, each 1–500 chars.
            adverse_event_keywords: Must have 1–50 entries, each 1–500 chars.
            mesh_terms: 0–30 entries, each 1–200 chars.
            device_identifiers: 0–20 entries, each 1–200 chars.
            exclusion_terms: 0–30 entries, each 1–500 chars.

        Raises:
            ValueError: If any constraint is violated.
        """
        # search_terms: required, 1–50 entries
        if not search_terms:
            raise ValueError("search_terms must contain at least one entry")
        if len(search_terms) > 50:
            raise ValueError(
                f"search_terms cannot exceed 50 entries, got {len(search_terms)}"
            )
        for i, term in enumerate(search_terms):
            if not term or len(term) > 500:
                raise ValueError(
                    f"search_terms[{i}] must be 1–500 characters, "
                    f"got {len(term) if term else 0}"
                )

        # adverse_event_keywords: required, 1–50 entries
        if not adverse_event_keywords:
            raise ValueError(
                "adverse_event_keywords must contain at least one entry"
            )
        if len(adverse_event_keywords) > 50:
            raise ValueError(
                f"adverse_event_keywords cannot exceed 50 entries, "
                f"got {len(adverse_event_keywords)}"
            )
        for i, kw in enumerate(adverse_event_keywords):
            if not kw or len(kw) > 500:
                raise ValueError(
                    f"adverse_event_keywords[{i}] must be 1–500 characters, "
                    f"got {len(kw) if kw else 0}"
                )

        # mesh_terms: optional, 0–30 entries
        if mesh_terms:
            if len(mesh_terms) > 30:
                raise ValueError(
                    f"mesh_terms cannot exceed 30 entries, got {len(mesh_terms)}"
                )
            for i, term in enumerate(mesh_terms):
                if not term or len(term) > 200:
                    raise ValueError(
                        f"mesh_terms[{i}] must be 1–200 characters, "
                        f"got {len(term) if term else 0}"
                    )

        # device_identifiers: optional, 0–20 entries
        if device_identifiers:
            if len(device_identifiers) > 20:
                raise ValueError(
                    f"device_identifiers cannot exceed 20 entries, "
                    f"got {len(device_identifiers)}"
                )
            for i, ident in enumerate(device_identifiers):
                if not ident or len(ident) > 200:
                    raise ValueError(
                        f"device_identifiers[{i}] must be 1–200 characters, "
                        f"got {len(ident) if ident else 0}"
                    )

        # exclusion_terms: optional, 0–30 entries
        if exclusion_terms:
            if len(exclusion_terms) > 30:
                raise ValueError(
                    f"exclusion_terms cannot exceed 30 entries, "
                    f"got {len(exclusion_terms)}"
                )
            for i, term in enumerate(exclusion_terms):
                if not term or len(term) > 500:
                    raise ValueError(
                        f"exclusion_terms[{i}] must be 1–500 characters, "
                        f"got {len(term) if term else 0}"
                    )

    def _validate_cron_field(
        self,
        field: str,
        field_name: str,
        min_val: int,
        max_val: int,
        full_expression: str,
    ) -> None:
        """Validate a single cron field.

        Handles: wildcard (*), step (*/n), ranges (a-b), lists (a,b,c),
        and combinations (a-b/n).

        Args:
            field: The cron field value to validate.
            field_name: Name of the field (for error messages).
            min_val: Minimum allowed value.
            max_val: Maximum allowed value.
            full_expression: The complete cron expression (for error messages).

        Raises:
            InvalidCronExpressionError: If the field is invalid.
        """
        # Handle step suffix (e.g., "*/5" or "1-10/2")
        parts = field.split("/")
        if len(parts) > 2:
            raise InvalidCronExpressionError(
                f"Invalid {field_name} field '{field}': too many '/' characters",
                expression=full_expression,
            )

        base = parts[0]
        step = parts[1] if len(parts) == 2 else None

        # Validate step value
        if step is not None:
            if not step.isdigit() or int(step) == 0:
                raise InvalidCronExpressionError(
                    f"Invalid {field_name} field '{field}': "
                    f"step value must be a positive integer",
                    expression=full_expression,
                )

        # Wildcard
        if base == "*":
            return

        # Parse list items (comma-separated)
        list_items = base.split(",")
        for item in list_items:
            # Range (e.g., "1-5")
            if "-" in item:
                range_parts = item.split("-")
                if len(range_parts) != 2:
                    raise InvalidCronExpressionError(
                        f"Invalid {field_name} field '{field}': "
                        f"malformed range '{item}'",
                        expression=full_expression,
                    )
                for rp in range_parts:
                    if not rp.isdigit():
                        raise InvalidCronExpressionError(
                            f"Invalid {field_name} field '{field}': "
                            f"non-numeric range value '{rp}'",
                            expression=full_expression,
                        )
                start, end = int(range_parts[0]), int(range_parts[1])
                if start > end:
                    raise InvalidCronExpressionError(
                        f"Invalid {field_name} field '{field}': "
                        f"range start ({start}) > end ({end})",
                        expression=full_expression,
                    )
                if start < min_val or end > max_val:
                    raise InvalidCronExpressionError(
                        f"Invalid {field_name} field '{field}': "
                        f"range {start}-{end} outside allowed {min_val}-{max_val}",
                        expression=full_expression,
                    )
            else:
                # Single number
                if not item.isdigit():
                    raise InvalidCronExpressionError(
                        f"Invalid {field_name} field '{field}': "
                        f"non-numeric value '{item}'",
                        expression=full_expression,
                    )
                val = int(item)
                if val < min_val or val > max_val:
                    raise InvalidCronExpressionError(
                        f"Invalid {field_name} field '{field}': "
                        f"value {val} outside allowed range {min_val}-{max_val}",
                        expression=full_expression,
                    )

    def _profile_to_dict(self, profile: VigilanceSearchProfile) -> dict[str, Any]:
        """Convert a VigilanceSearchProfile to a response dict.

        Args:
            profile: The profile model instance.

        Returns:
            Dict representation with all fields.
        """
        return {
            "id": profile.id,
            "product_id": profile.product_id,
            "company_id": profile.company_id,
            "name": profile.name,
            "search_terms": profile.search_terms,
            "mesh_terms": profile.mesh_terms,
            "adverse_event_keywords": profile.adverse_event_keywords,
            "device_identifiers": profile.device_identifiers,
            "exclusion_terms": profile.exclusion_terms,
            "source_ids": profile.source_ids,
            "schedule_cron": profile.schedule_cron,
            "status": profile.status,
            "created_by": profile.created_by,
            "created_at": (
                profile.created_at.isoformat() if profile.created_at else None
            ),
            "updated_at": (
                profile.updated_at.isoformat() if profile.updated_at else None
            ),
        }
