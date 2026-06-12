"""Product Portfolio Service for medical device CRUD and lifecycle management.

Manages registration, updates, soft-deletion, listing, and detail retrieval
of medical products within a company's portfolio. Enforces UDI uniqueness,
field validation, role-based access control, and audit trail logging.

References:
    - Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6
    - Design: ProductPortfolioService interface
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.literature.vigilance.exceptions import (
    DuplicateUDIError,
    ProductNotFoundError,
)
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_search_profile import (
    VigilanceSearchProfile,
)
from alcoabase.literature.vigilance.models.vigilance_signal import VigilanceSignal

logger = logging.getLogger(__name__)

# Dedicated audit logger for vigilance product operations.
audit_logger = logging.getLogger("alcoabase.audit.vigilance_product")

# ---------------------------------------------------------------------------
# Audit event type constants
# ---------------------------------------------------------------------------

EVENT_PRODUCT_CREATED = "vigilance.product_created"
EVENT_PRODUCT_UPDATED = "vigilance.product_updated"
EVENT_PRODUCT_SOFT_DELETED = "vigilance.product_soft_deleted"
EVENT_PROFILES_SUSPENDED = "vigilance.profiles_suspended"


class ProductPortfolioService:
    """Manages Medical Product lifecycle within a company portfolio.

    Responsibilities:
        - Create products with validated fields (name, device_class, intended_purpose required)
        - Enforce UDI uniqueness within company
        - Manage status transitions (active → discontinued/recalled)
        - Suspend associated profiles when product discontinued/recalled
        - List products with pagination and filtering
        - Expose signal counts per product
    """

    VALID_DEVICE_CLASSES = (
        "I",
        "IIa",
        "IIb",
        "III",
        "IVDR_A",
        "IVDR_B",
        "IVDR_C",
        "IVDR_D",
    )
    VALID_STATUSES = ("active", "discontinued", "recalled")

    async def create_product(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        user_id: int,
        name: str,
        device_class: str,
        intended_purpose: str,
        udi: str | None = None,
        gmdn_code: str | None = None,
        manufacturer_name: str | None = None,
        predicate_devices: list[str] | None = None,
        risk_class_justification: str | None = None,
    ) -> dict[str, Any]:
        """Create a new Medical Product.

        Validates required fields, device_class enum, field lengths,
        UDI uniqueness within the company, persists the record, and
        records an audit trail entry.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            user_id: Creating user (must have document_admin or system_admin role).
            name: Product name (1–300 chars).
            device_class: One of VALID_DEVICE_CLASSES.
            intended_purpose: Text (max 5000 chars).
            udi: Optional unique device identifier (1–128 chars, unique per company).
            gmdn_code: Optional GMDN code (1–20 chars).
            manufacturer_name: Optional (1–300 chars).
            predicate_devices: Optional array (max 10, each 1–300 chars).
            risk_class_justification: Optional (max 3000 chars).

        Returns:
            Dict with created product fields + id.

        Raises:
            ValueError: If required fields missing or invalid.
            DuplicateUDIError: If UDI exists within company.
        """
        # Validate required fields
        self._validate_required_fields(name, device_class, intended_purpose)

        # Validate field lengths
        self._validate_field_lengths(
            name=name,
            intended_purpose=intended_purpose,
            udi=udi,
            gmdn_code=gmdn_code,
            manufacturer_name=manufacturer_name,
            predicate_devices=predicate_devices,
            risk_class_justification=risk_class_justification,
        )

        # Validate device_class enum
        self._validate_device_class(device_class)

        # Check UDI uniqueness within company
        if udi is not None:
            await self._check_udi_uniqueness(
                session, company_id=company_id, udi=udi, exclude_product_id=None
            )

        # Persist
        product = MedicalProduct(
            company_id=company_id,
            name=name,
            device_class=device_class,
            intended_purpose=intended_purpose,
            udi=udi,
            gmdn_code=gmdn_code,
            manufacturer_name=manufacturer_name,
            predicate_devices=predicate_devices,
            risk_class_justification=risk_class_justification,
            status="active",
            created_by=user_id,
        )
        session.add(product)
        await session.flush()

        # Record audit trail
        self._log_audit(
            event_type=EVENT_PRODUCT_CREATED,
            entity_id=product.id,
            company_id=company_id,
            user_id=user_id,
            details={
                "name": name,
                "device_class": device_class,
                "udi": udi,
                "status": "active",
            },
        )

        return self._product_to_dict(product)

    async def update_product(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
        user_id: int,
        **fields: Any,
    ) -> dict[str, Any]:
        """Update a Medical Product.

        On status change to discontinued/recalled: suspends associated profiles.
        Validates field lengths and UDI uniqueness on change.

        Args:
            product_id: Target product.
            company_id: Tenant scope.
            user_id: Updating user.
            **fields: Fields to update.

        Returns:
            Updated product dict.

        Raises:
            ProductNotFoundError: If product not found in this company.
            DuplicateUDIError: If new UDI conflicts.
            ValueError: If field validation fails.
        """
        product = await self._get_product_or_raise(
            session, product_id=product_id, company_id=company_id
        )

        # Validate field lengths for provided fields
        self._validate_field_lengths(
            name=fields.get("name"),
            intended_purpose=fields.get("intended_purpose"),
            udi=fields.get("udi"),
            gmdn_code=fields.get("gmdn_code"),
            manufacturer_name=fields.get("manufacturer_name"),
            predicate_devices=fields.get("predicate_devices"),
            risk_class_justification=fields.get("risk_class_justification"),
        )

        # Validate device_class if provided
        if "device_class" in fields and fields["device_class"] is not None:
            self._validate_device_class(fields["device_class"])

        # Validate status if provided
        if "status" in fields and fields["status"] is not None:
            if fields["status"] not in self.VALID_STATUSES:
                msg = (
                    f"Invalid status '{fields['status']}'. "
                    f"Must be one of: {', '.join(self.VALID_STATUSES)}"
                )
                raise ValueError(msg)

        # Check UDI uniqueness on change
        new_udi = fields.get("udi")
        if new_udi is not None and new_udi != product.udi:
            await self._check_udi_uniqueness(
                session,
                company_id=company_id,
                udi=new_udi,
                exclude_product_id=product_id,
            )

        # Track status change for profile suspension
        old_status = product.status
        new_status = fields.get("status")

        # Apply updates
        changed_fields: list[str] = []
        for field_name, value in fields.items():
            if value is not None and hasattr(product, field_name):
                setattr(product, field_name, value)
                changed_fields.append(field_name)

        await session.flush()

        # Suspend associated profiles on status change to discontinued/recalled
        if (
            new_status is not None
            and new_status != old_status
            and new_status in ("discontinued", "recalled")
        ):
            suspended_count = await self._suspend_profiles(
                session, product_id=product_id
            )
            self._log_audit(
                event_type=EVENT_PROFILES_SUSPENDED,
                entity_id=product_id,
                company_id=company_id,
                user_id=user_id,
                details={
                    "reason": f"product status changed to {new_status}",
                    "suspended_count": suspended_count,
                },
            )

        # Record audit trail
        self._log_audit(
            event_type=EVENT_PRODUCT_UPDATED,
            entity_id=product_id,
            company_id=company_id,
            user_id=user_id,
            details={"changed_fields": changed_fields},
        )

        return self._product_to_dict(product)

    async def soft_delete_product(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
        user_id: int,
    ) -> dict[str, Any]:
        """Soft-delete product by transitioning to 'discontinued'.

        Suspends all associated vigilance search profiles.

        Args:
            product_id: Target product.
            company_id: Tenant scope.
            user_id: Deleting user.

        Returns:
            Updated product dict with status='discontinued'.

        Raises:
            ProductNotFoundError: If product not found in this company.
        """
        product = await self._get_product_or_raise(
            session, product_id=product_id, company_id=company_id
        )

        old_status = product.status
        product.status = "discontinued"
        await session.flush()

        # Suspend associated profiles
        suspended_count = await self._suspend_profiles(
            session, product_id=product_id
        )

        # Record audit trail
        self._log_audit(
            event_type=EVENT_PRODUCT_SOFT_DELETED,
            entity_id=product_id,
            company_id=company_id,
            user_id=user_id,
            details={
                "previous_status": old_status,
                "new_status": "discontinued",
                "suspended_profiles": suspended_count,
            },
        )

        return self._product_to_dict(product)

    async def list_products(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        device_class: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """List products with pagination and filters.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            page: Page number (1-indexed).
            page_size: Items per page (1–100).
            status: Optional status filter.
            device_class: Optional device class filter.

        Returns:
            Tuple of (products_list, total_count).
        """
        # Clamp page_size
        page_size = max(1, min(page_size, 100))
        page = max(1, page)

        # Build base query
        base_filter = [MedicalProduct.company_id == company_id]
        if status is not None:
            base_filter.append(MedicalProduct.status == status)
        if device_class is not None:
            base_filter.append(MedicalProduct.device_class == device_class)

        # Count total
        count_stmt = select(func.count(MedicalProduct.id)).where(*base_filter)
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Paginated query
        offset = (page - 1) * page_size
        query = (
            select(MedicalProduct)
            .where(*base_filter)
            .order_by(MedicalProduct.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(query)
        products = list(result.scalars().all())

        return [self._product_to_dict(p) for p in products], total

    async def get_product(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Get full product details with associated profiles and signal counts.

        Args:
            session: Active async DB session.
            product_id: Target product.
            company_id: Tenant scope.

        Returns:
            Product dict with 'profiles' and 'signal_counts' fields.

        Raises:
            ProductNotFoundError: If not found in this company.
        """
        product = await self._get_product_or_raise(
            session, product_id=product_id, company_id=company_id
        )

        # Fetch associated profiles
        profiles_stmt = (
            select(VigilanceSearchProfile)
            .where(
                VigilanceSearchProfile.product_id == product_id,
                VigilanceSearchProfile.company_id == company_id,
            )
            .order_by(VigilanceSearchProfile.created_at.desc())
        )
        profiles_result = await session.execute(profiles_stmt)
        profiles = list(profiles_result.scalars().all())

        # Fetch signal counts by severity
        signal_counts_stmt = (
            select(
                VigilanceSignal.severity,
                func.count(VigilanceSignal.id),
            )
            .where(
                VigilanceSignal.product_id == product_id,
                VigilanceSignal.company_id == company_id,
            )
            .group_by(VigilanceSignal.severity)
        )
        signal_counts_result = await session.execute(signal_counts_stmt)
        signal_counts = {
            row[0]: row[1] for row in signal_counts_result.all()
        }

        product_dict = self._product_to_dict(product)
        product_dict["profiles"] = [
            self._profile_to_dict(p) for p in profiles
        ]
        product_dict["signal_counts"] = signal_counts

        return product_dict

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    def _validate_required_fields(
        self,
        name: str,
        device_class: str,
        intended_purpose: str,
    ) -> None:
        """Validate that required fields are present and non-empty.

        Raises:
            ValueError: If any required field is missing or empty.
        """
        if not name or not name.strip():
            raise ValueError("name is required and cannot be empty")
        if not device_class or not device_class.strip():
            raise ValueError("device_class is required and cannot be empty")
        if not intended_purpose or not intended_purpose.strip():
            raise ValueError("intended_purpose is required and cannot be empty")

    def _validate_device_class(self, device_class: str) -> None:
        """Validate device_class is in the allowed enum set.

        Raises:
            ValueError: If device_class is not valid.
        """
        if device_class not in self.VALID_DEVICE_CLASSES:
            msg = (
                f"Invalid device_class '{device_class}'. "
                f"Must be one of: {', '.join(self.VALID_DEVICE_CLASSES)}"
            )
            raise ValueError(msg)

    def _validate_field_lengths(
        self,
        *,
        name: str | None = None,
        intended_purpose: str | None = None,
        udi: str | None = None,
        gmdn_code: str | None = None,
        manufacturer_name: str | None = None,
        predicate_devices: list[str] | None = None,
        risk_class_justification: str | None = None,
    ) -> None:
        """Validate field lengths for provided values.

        Raises:
            ValueError: If any field exceeds its maximum length.
        """
        if name is not None and len(name) > 300:
            raise ValueError("name must be at most 300 characters")
        if intended_purpose is not None and len(intended_purpose) > 5000:
            raise ValueError(
                "intended_purpose must be at most 5000 characters"
            )
        if udi is not None and len(udi) > 128:
            raise ValueError("udi must be at most 128 characters")
        if gmdn_code is not None and len(gmdn_code) > 20:
            raise ValueError("gmdn_code must be at most 20 characters")
        if manufacturer_name is not None and len(manufacturer_name) > 300:
            raise ValueError(
                "manufacturer_name must be at most 300 characters"
            )
        if risk_class_justification is not None and len(risk_class_justification) > 3000:
            raise ValueError(
                "risk_class_justification must be at most 3000 characters"
            )
        if predicate_devices is not None:
            if len(predicate_devices) > 10:
                raise ValueError(
                    "predicate_devices must have at most 10 entries"
                )
            for i, entry in enumerate(predicate_devices):
                if len(entry) > 300:
                    raise ValueError(
                        f"predicate_devices[{i}] must be at most 300 characters"
                    )

    async def _check_udi_uniqueness(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        udi: str,
        exclude_product_id: int | None,
    ) -> None:
        """Check that a UDI is unique within the company.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            udi: UDI value to check.
            exclude_product_id: Product ID to exclude (for updates).

        Raises:
            DuplicateUDIError: If UDI already exists for another product.
        """
        stmt = select(MedicalProduct.id).where(
            MedicalProduct.company_id == company_id,
            MedicalProduct.udi == udi,
        )
        if exclude_product_id is not None:
            stmt = stmt.where(MedicalProduct.id != exclude_product_id)

        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing is not None:
            raise DuplicateUDIError(
                f"A product with UDI '{udi}' already exists in this company",
                udi=udi,
                company_id=company_id,
            )

    async def _get_product_or_raise(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
    ) -> MedicalProduct:
        """Load a product by ID within company scope.

        Raises:
            ProductNotFoundError: If not found.
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

    async def _suspend_profiles(
        self,
        session: AsyncSession,
        *,
        product_id: int,
    ) -> int:
        """Suspend all active profiles associated with a product.

        Sets status to 'paused' for any profile that is currently 'active'.

        Returns:
            Number of profiles suspended.
        """
        stmt = select(VigilanceSearchProfile).where(
            VigilanceSearchProfile.product_id == product_id,
            VigilanceSearchProfile.status == "active",
        )
        result = await session.execute(stmt)
        profiles = list(result.scalars().all())

        for profile in profiles:
            profile.status = "paused"

        await session.flush()
        return len(profiles)

    def _log_audit(
        self,
        *,
        event_type: str,
        entity_id: int,
        company_id: int,
        user_id: int,
        details: dict[str, Any],
    ) -> None:
        """Emit a structured audit log entry for a product operation.

        Uses Python logging with structured extras for ALCOA+ compliance.
        Never logs full document content.

        Args:
            event_type: Event type constant.
            entity_id: Product ID.
            company_id: Tenant company ID.
            user_id: Acting user ID.
            details: Additional event details.
        """
        timestamp = datetime.now(timezone.utc)
        audit_logger.info(
            "Product operation: event=%s, product_id=%d, company_id=%d, user_id=%d",
            event_type,
            entity_id,
            company_id,
            user_id,
            extra={
                "event_type": event_type,
                "entity_type": "medical_product",
                "entity_id": entity_id,
                "company_id": company_id,
                "acting_user_id": user_id,
                "timestamp": timestamp.isoformat(),
                **details,
            },
        )

    def _product_to_dict(self, product: MedicalProduct) -> dict[str, Any]:
        """Convert a MedicalProduct model to a plain dict.

        Args:
            product: MedicalProduct ORM instance.

        Returns:
            Dict representation of the product.
        """
        return {
            "id": product.id,
            "company_id": product.company_id,
            "name": product.name,
            "device_class": product.device_class,
            "intended_purpose": product.intended_purpose,
            "udi": product.udi,
            "gmdn_code": product.gmdn_code,
            "manufacturer_name": product.manufacturer_name,
            "predicate_devices": product.predicate_devices,
            "risk_class_justification": product.risk_class_justification,
            "status": product.status,
            "created_by": product.created_by,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }

    def _profile_to_dict(
        self, profile: VigilanceSearchProfile
    ) -> dict[str, Any]:
        """Convert a VigilanceSearchProfile model to a plain dict.

        Args:
            profile: VigilanceSearchProfile ORM instance.

        Returns:
            Dict representation of the profile.
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
            "created_at": profile.created_at,
            "updated_at": profile.updated_at,
        }
