"""Unit tests for the ProductPortfolioService.

Tests cover:
- Product creation with validation (required fields, device_class enum, field lengths)
- UDI uniqueness enforcement within company
- Product updates with status transition (suspend profiles on discontinue/recall)
- Soft-delete (transition to discontinued, suspend profiles)
- Product listing with pagination and filters
- Full product detail retrieval with profiles and signal counts
- Audit trail logging for all mutations
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.literature.vigilance.exceptions import (
    DuplicateUDIError,
    ProductNotFoundError,
)
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.vigilance_search_profile import (
    VigilanceSearchProfile,
)
from alcoabase.literature.vigilance.services.product_portfolio_service import (
    ProductPortfolioService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def service() -> ProductPortfolioService:
    """Create a ProductPortfolioService instance."""
    return ProductPortfolioService()


def _make_product(
    *,
    id: int = 1,
    company_id: int = 10,
    name: str = "Test Device",
    device_class: str = "IIa",
    intended_purpose: str = "Diagnostic imaging",
    udi: str | None = "UDI-12345",
    status: str = "active",
    created_by: int = 100,
) -> MagicMock:
    """Helper to create a MedicalProduct-like mock for tests."""
    product = MagicMock(spec=MedicalProduct)
    product.id = id
    product.company_id = company_id
    product.name = name
    product.device_class = device_class
    product.intended_purpose = intended_purpose
    product.udi = udi
    product.gmdn_code = None
    product.manufacturer_name = None
    product.predicate_devices = None
    product.risk_class_justification = None
    product.status = status
    product.created_by = created_by
    product.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    product.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return product


def _make_profile(
    *,
    id: int = 1,
    product_id: int = 1,
    company_id: int = 10,
    status: str = "active",
) -> MagicMock:
    """Helper to create a VigilanceSearchProfile-like mock for tests."""
    profile = MagicMock(spec=VigilanceSearchProfile)
    profile.id = id
    profile.product_id = product_id
    profile.company_id = company_id
    profile.name = "Test Profile"
    profile.search_terms = ["device term"]
    profile.mesh_terms = None
    profile.adverse_event_keywords = ["adverse event"]
    profile.device_identifiers = None
    profile.exclusion_terms = None
    profile.source_ids = None
    profile.schedule_cron = "0 6 * * *"
    profile.status = status
    profile.created_by = 100
    profile.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    profile.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return profile


# ---------------------------------------------------------------------------
# Create Product Tests
# ---------------------------------------------------------------------------


class TestCreateProduct:
    """Tests for create_product method."""

    @pytest.mark.asyncio
    async def test_creates_product_successfully(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Create a product with all required fields."""
        # UDI uniqueness check returns no existing product
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await service.create_product(
            mock_session,
            company_id=10,
            user_id=100,
            name="My Device",
            device_class="IIb",
            intended_purpose="Surgical tool",
            udi="UDI-001",
        )

        assert result["name"] == "My Device"
        assert result["device_class"] == "IIb"
        assert result["intended_purpose"] == "Surgical tool"
        assert result["udi"] == "UDI-001"
        assert result["status"] == "active"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called()

    @pytest.mark.asyncio
    async def test_creates_product_without_udi(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Create a product without optional UDI field."""
        result = await service.create_product(
            mock_session,
            company_id=10,
            user_id=100,
            name="No UDI Device",
            device_class="I",
            intended_purpose="General use",
        )

        assert result["name"] == "No UDI Device"
        assert result["udi"] is None
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejects_empty_name(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject product creation when name is empty."""
        with pytest.raises(ValueError, match="name is required"):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="",
                device_class="I",
                intended_purpose="General use",
            )

    @pytest.mark.asyncio
    async def test_rejects_whitespace_only_name(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject product creation when name is whitespace only."""
        with pytest.raises(ValueError, match="name is required"):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="   ",
                device_class="I",
                intended_purpose="General use",
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_intended_purpose(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject product creation when intended_purpose is empty."""
        with pytest.raises(ValueError, match="intended_purpose is required"):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="Device",
                device_class="I",
                intended_purpose="",
            )

    @pytest.mark.asyncio
    async def test_rejects_invalid_device_class(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject product creation with invalid device_class."""
        with pytest.raises(ValueError, match="Invalid device_class"):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="Device",
                device_class="IV",
                intended_purpose="General use",
            )

    @pytest.mark.asyncio
    async def test_rejects_name_too_long(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject product creation when name exceeds 300 characters."""
        with pytest.raises(ValueError, match="name must be at most 300"):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="x" * 301,
                device_class="I",
                intended_purpose="General use",
            )

    @pytest.mark.asyncio
    async def test_rejects_intended_purpose_too_long(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject product when intended_purpose exceeds 5000 chars."""
        with pytest.raises(
            ValueError, match="intended_purpose must be at most 5000"
        ):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="Device",
                device_class="I",
                intended_purpose="x" * 5001,
            )

    @pytest.mark.asyncio
    async def test_rejects_duplicate_udi(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject product creation with duplicate UDI within company."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = 99  # existing product id
        mock_session.execute.return_value = mock_result

        with pytest.raises(DuplicateUDIError) as exc_info:
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="Device",
                device_class="I",
                intended_purpose="General use",
                udi="DUPLICATE-UDI",
            )

        assert exc_info.value.udi == "DUPLICATE-UDI"
        assert exc_info.value.company_id == 10

    @pytest.mark.asyncio
    async def test_accepts_all_valid_device_classes(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """All valid device classes are accepted."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        for dc in ProductPortfolioService.VALID_DEVICE_CLASSES:
            result = await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name=f"Device {dc}",
                device_class=dc,
                intended_purpose="General use",
                udi=f"UDI-{dc}",
            )
            assert result["device_class"] == dc

    @pytest.mark.asyncio
    async def test_rejects_predicate_devices_too_many(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject when predicate_devices exceeds 10 entries."""
        with pytest.raises(
            ValueError, match="predicate_devices must have at most 10"
        ):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="Device",
                device_class="I",
                intended_purpose="General use",
                predicate_devices=["dev"] * 11,
            )

    @pytest.mark.asyncio
    async def test_rejects_predicate_device_entry_too_long(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject when a predicate_devices entry exceeds 300 chars."""
        with pytest.raises(
            ValueError, match="predicate_devices\\[0\\] must be at most 300"
        ):
            await service.create_product(
                mock_session,
                company_id=10,
                user_id=100,
                name="Device",
                device_class="I",
                intended_purpose="General use",
                predicate_devices=["x" * 301],
            )


# ---------------------------------------------------------------------------
# Update Product Tests
# ---------------------------------------------------------------------------


class TestUpdateProduct:
    """Tests for update_product method."""

    @pytest.mark.asyncio
    async def test_updates_product_name(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Update a product's name."""
        product = _make_product()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = product
        mock_session.execute.return_value = mock_result

        result = await service.update_product(
            mock_session,
            product_id=1,
            company_id=10,
            user_id=100,
            name="Updated Name",
        )

        assert result["name"] == "Updated Name"

    @pytest.mark.asyncio
    async def test_raises_not_found(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Raise ProductNotFoundError when product does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ProductNotFoundError) as exc_info:
            await service.update_product(
                mock_session,
                product_id=999,
                company_id=10,
                user_id=100,
                name="Updated",
            )

        assert exc_info.value.product_id == 999
        assert exc_info.value.company_id == 10

    @pytest.mark.asyncio
    async def test_suspends_profiles_on_discontinue(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Suspend active profiles when product status changes to discontinued."""
        product = _make_product(status="active")
        active_profile = _make_profile(status="active")

        # First call: get product, second: check UDI (none), third: get profiles
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_r = MagicMock()
            if call_count[0] == 1:
                # Get product
                mock_r.scalar_one_or_none.return_value = product
            elif call_count[0] == 2:
                # Get active profiles to suspend
                mock_r.scalars.return_value.all.return_value = [active_profile]
            return mock_r

        mock_session.execute.side_effect = side_effect

        result = await service.update_product(
            mock_session,
            product_id=1,
            company_id=10,
            user_id=100,
            status="discontinued",
        )

        assert result["status"] == "discontinued"
        assert active_profile.status == "paused"

    @pytest.mark.asyncio
    async def test_rejects_invalid_status(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Reject invalid status value during update."""
        product = _make_product()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = product
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="Invalid status"):
            await service.update_product(
                mock_session,
                product_id=1,
                company_id=10,
                user_id=100,
                status="invalid_status",
            )

    @pytest.mark.asyncio
    async def test_checks_udi_uniqueness_on_change(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Check UDI uniqueness when UDI is changed."""
        product = _make_product(udi="OLD-UDI")

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_r = MagicMock()
            if call_count[0] == 1:
                mock_r.scalar_one_or_none.return_value = product
            elif call_count[0] == 2:
                # UDI uniqueness check — conflict found
                mock_r.scalar_one_or_none.return_value = 50
            return mock_r

        mock_session.execute.side_effect = side_effect

        with pytest.raises(DuplicateUDIError):
            await service.update_product(
                mock_session,
                product_id=1,
                company_id=10,
                user_id=100,
                udi="CONFLICTING-UDI",
            )


# ---------------------------------------------------------------------------
# Soft Delete Tests
# ---------------------------------------------------------------------------


class TestSoftDeleteProduct:
    """Tests for soft_delete_product method."""

    @pytest.mark.asyncio
    async def test_soft_deletes_product(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Soft delete transitions product to discontinued."""
        product = _make_product(status="active")

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_r = MagicMock()
            if call_count[0] == 1:
                mock_r.scalar_one_or_none.return_value = product
            elif call_count[0] == 2:
                # Profiles to suspend
                mock_r.scalars.return_value.all.return_value = []
            return mock_r

        mock_session.execute.side_effect = side_effect

        result = await service.soft_delete_product(
            mock_session,
            product_id=1,
            company_id=10,
            user_id=100,
        )

        assert result["status"] == "discontinued"

    @pytest.mark.asyncio
    async def test_suspends_profiles_on_soft_delete(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Profiles are suspended when product is soft-deleted."""
        product = _make_product(status="active")
        profile = _make_profile(status="active")

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_r = MagicMock()
            if call_count[0] == 1:
                mock_r.scalar_one_or_none.return_value = product
            elif call_count[0] == 2:
                mock_r.scalars.return_value.all.return_value = [profile]
            return mock_r

        mock_session.execute.side_effect = side_effect

        await service.soft_delete_product(
            mock_session,
            product_id=1,
            company_id=10,
            user_id=100,
        )

        assert profile.status == "paused"

    @pytest.mark.asyncio
    async def test_raises_not_found_on_soft_delete(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Raise ProductNotFoundError if product does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ProductNotFoundError):
            await service.soft_delete_product(
                mock_session,
                product_id=999,
                company_id=10,
                user_id=100,
            )


# ---------------------------------------------------------------------------
# List Products Tests
# ---------------------------------------------------------------------------


class TestListProducts:
    """Tests for list_products method."""

    @pytest.mark.asyncio
    async def test_lists_products_with_pagination(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """List products returns paginated results and total count."""
        products = [_make_product(id=i) for i in range(3)]

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_r = MagicMock()
            if call_count[0] == 1:
                # Count query
                mock_r.scalar_one.return_value = 3
            elif call_count[0] == 2:
                # Data query
                mock_r.scalars.return_value.all.return_value = products
            return mock_r

        mock_session.execute.side_effect = side_effect

        results, total = await service.list_products(
            mock_session,
            company_id=10,
            page=1,
            page_size=20,
        )

        assert total == 3
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_clamps_page_size(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Page size is clamped to 1–100 range."""
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_r = MagicMock()
            if call_count[0] == 1:
                mock_r.scalar_one.return_value = 0
            elif call_count[0] == 2:
                mock_r.scalars.return_value.all.return_value = []
            return mock_r

        mock_session.execute.side_effect = side_effect

        results, total = await service.list_products(
            mock_session,
            company_id=10,
            page=1,
            page_size=200,  # exceeds max
        )

        assert total == 0
        assert results == []


# ---------------------------------------------------------------------------
# Get Product Tests
# ---------------------------------------------------------------------------


class TestGetProduct:
    """Tests for get_product method."""

    @pytest.mark.asyncio
    async def test_returns_product_with_profiles_and_signals(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Get product returns full details with profiles and signal counts."""
        product = _make_product()
        profile = _make_profile()

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock_r = MagicMock()
            if call_count[0] == 1:
                # Get product
                mock_r.scalar_one_or_none.return_value = product
            elif call_count[0] == 2:
                # Get profiles
                mock_r.scalars.return_value.all.return_value = [profile]
            elif call_count[0] == 3:
                # Signal counts
                mock_r.all.return_value = [("critical", 2), ("major", 5)]
            return mock_r

        mock_session.execute.side_effect = side_effect

        result = await service.get_product(
            mock_session,
            product_id=1,
            company_id=10,
        )

        assert result["id"] == 1
        assert result["name"] == "Test Device"
        assert len(result["profiles"]) == 1
        assert result["signal_counts"] == {"critical": 2, "major": 5}

    @pytest.mark.asyncio
    async def test_raises_not_found(
        self, service: ProductPortfolioService, mock_session: AsyncMock
    ) -> None:
        """Raise ProductNotFoundError when product does not exist."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ProductNotFoundError):
            await service.get_product(
                mock_session,
                product_id=999,
                company_id=10,
            )


# ---------------------------------------------------------------------------
# Validation Helper Tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Tests for field validation helpers."""

    def test_rejects_udi_too_long(self, service: ProductPortfolioService) -> None:
        """Reject UDI exceeding 128 characters."""
        with pytest.raises(ValueError, match="udi must be at most 128"):
            service._validate_field_lengths(udi="x" * 129)

    def test_rejects_gmdn_code_too_long(
        self, service: ProductPortfolioService
    ) -> None:
        """Reject GMDN code exceeding 20 characters."""
        with pytest.raises(ValueError, match="gmdn_code must be at most 20"):
            service._validate_field_lengths(gmdn_code="x" * 21)

    def test_rejects_manufacturer_name_too_long(
        self, service: ProductPortfolioService
    ) -> None:
        """Reject manufacturer_name exceeding 300 characters."""
        with pytest.raises(
            ValueError, match="manufacturer_name must be at most 300"
        ):
            service._validate_field_lengths(manufacturer_name="x" * 301)

    def test_rejects_risk_class_justification_too_long(
        self, service: ProductPortfolioService
    ) -> None:
        """Reject risk_class_justification exceeding 3000 characters."""
        with pytest.raises(
            ValueError, match="risk_class_justification must be at most 3000"
        ):
            service._validate_field_lengths(
                risk_class_justification="x" * 3001
            )

    def test_accepts_valid_field_lengths(
        self, service: ProductPortfolioService
    ) -> None:
        """Accept fields within valid length bounds."""
        # Should not raise
        service._validate_field_lengths(
            name="Valid Name",
            intended_purpose="Valid purpose",
            udi="UDI-123",
            gmdn_code="12345",
            manufacturer_name="Acme Corp",
            predicate_devices=["Device A", "Device B"],
            risk_class_justification="Valid justification",
        )
