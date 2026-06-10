"""Unit tests for ingestion configuration schemas.

Tests:
    - Default values applied when no explicit config exists
    - Email validation: required when full_text_retrieval_enabled=True
    - max_concurrent_downloads range (1–20)
    - storage_quota_mb minimum (100)
    - retention_days minimum (0)

Requirements: 8.1, 8.2, 8.6, 8.8
"""

import pytest
from pydantic import ValidationError

from alcoabase.literature.ingestion.schemas.configuration import (
    IngestionConfigurationCreate,
    IngestionConfigurationUpdate,
)


# ─── Default Values Tests ─────────────────────────────────────────────────────


class TestDefaultValues:
    """Test that defaults are applied when no explicit config provided."""

    def test_defaults_with_email(self) -> None:
        """All defaults apply when only email is provided (required for enabled)."""
        config = IngestionConfigurationCreate(unpaywall_email="test@example.com")

        assert config.full_text_retrieval_enabled is True
        assert config.storage_quota_mb == 10240
        assert config.retention_days == 365
        assert config.unpaywall_email == "test@example.com"
        assert config.dual_uuid_integration_enabled is False
        assert config.max_concurrent_downloads == 5

    def test_defaults_with_retrieval_disabled(self) -> None:
        """When full_text_retrieval_enabled=False, email is not required."""
        config = IngestionConfigurationCreate(full_text_retrieval_enabled=False)

        assert config.full_text_retrieval_enabled is False
        assert config.storage_quota_mb == 10240
        assert config.retention_days == 365
        assert config.unpaywall_email is None
        assert config.max_concurrent_downloads == 5


# ─── Email Validation Tests ──────────────────────────────────────────────────


class TestEmailValidation:
    """Test email validation when full_text_retrieval_enabled=True."""

    def test_email_required_when_enabled(self) -> None:
        """Missing email when enabled=True raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfigurationCreate(
                full_text_retrieval_enabled=True, unpaywall_email=None
            )

        errors = exc_info.value.errors()
        assert any(
            "unpaywall_email is required" in str(e["msg"]) for e in errors
        )

    def test_empty_email_when_enabled_rejected(self) -> None:
        """Empty string email when enabled=True is rejected."""
        with pytest.raises(ValidationError):
            IngestionConfigurationCreate(
                full_text_retrieval_enabled=True, unpaywall_email=""
            )

    def test_email_without_at_sign_rejected(self) -> None:
        """Email missing '@' is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IngestionConfigurationCreate(
                full_text_retrieval_enabled=True, unpaywall_email="invalid-email"
            )

        errors = exc_info.value.errors()
        assert any("@" in str(e["msg"]) for e in errors)

    def test_valid_email_accepted(self) -> None:
        """Valid email is accepted."""
        config = IngestionConfigurationCreate(
            full_text_retrieval_enabled=True, unpaywall_email="user@example.com"
        )
        assert config.unpaywall_email == "user@example.com"

    def test_email_not_required_when_disabled(self) -> None:
        """When enabled=False, null email is accepted."""
        config = IngestionConfigurationCreate(
            full_text_retrieval_enabled=False, unpaywall_email=None
        )
        assert config.unpaywall_email is None


# ─── max_concurrent_downloads Range Tests ────────────────────────────────────


class TestMaxConcurrentDownloads:
    """Test max_concurrent_downloads range (1–20)."""

    def test_minimum_value_1(self) -> None:
        """Value of 1 is accepted."""
        config = IngestionConfigurationCreate(
            unpaywall_email="a@b.com", max_concurrent_downloads=1
        )
        assert config.max_concurrent_downloads == 1

    def test_maximum_value_20(self) -> None:
        """Value of 20 is accepted."""
        config = IngestionConfigurationCreate(
            unpaywall_email="a@b.com", max_concurrent_downloads=20
        )
        assert config.max_concurrent_downloads == 20

    def test_below_minimum_rejected(self) -> None:
        """Value below 1 is rejected."""
        with pytest.raises(ValidationError):
            IngestionConfigurationCreate(
                unpaywall_email="a@b.com", max_concurrent_downloads=0
            )

    def test_above_maximum_rejected(self) -> None:
        """Value above 20 is rejected."""
        with pytest.raises(ValidationError):
            IngestionConfigurationCreate(
                unpaywall_email="a@b.com", max_concurrent_downloads=21
            )

    def test_update_schema_range(self) -> None:
        """Update schema also enforces range 1–20."""
        with pytest.raises(ValidationError):
            IngestionConfigurationUpdate(max_concurrent_downloads=0)
        with pytest.raises(ValidationError):
            IngestionConfigurationUpdate(max_concurrent_downloads=21)

        valid = IngestionConfigurationUpdate(max_concurrent_downloads=10)
        assert valid.max_concurrent_downloads == 10


# ─── storage_quota_mb Minimum Tests ──────────────────────────────────────────


class TestStorageQuotaMb:
    """Test storage_quota_mb minimum (100)."""

    def test_minimum_100_accepted(self) -> None:
        """Value of 100 is accepted."""
        config = IngestionConfigurationCreate(
            unpaywall_email="a@b.com", storage_quota_mb=100
        )
        assert config.storage_quota_mb == 100

    def test_below_minimum_rejected(self) -> None:
        """Value below 100 is rejected."""
        with pytest.raises(ValidationError):
            IngestionConfigurationCreate(
                unpaywall_email="a@b.com", storage_quota_mb=99
            )

    def test_large_value_accepted(self) -> None:
        """Large values are accepted."""
        config = IngestionConfigurationCreate(
            unpaywall_email="a@b.com", storage_quota_mb=100000
        )
        assert config.storage_quota_mb == 100000

    def test_update_schema_minimum(self) -> None:
        """Update schema also enforces minimum 100."""
        with pytest.raises(ValidationError):
            IngestionConfigurationUpdate(storage_quota_mb=50)


# ─── retention_days Minimum Tests ────────────────────────────────────────────


class TestRetentionDays:
    """Test retention_days minimum (0 = indefinite)."""

    def test_zero_accepted_as_indefinite(self) -> None:
        """Value of 0 means indefinite retention."""
        config = IngestionConfigurationCreate(
            unpaywall_email="a@b.com", retention_days=0
        )
        assert config.retention_days == 0

    def test_positive_value_accepted(self) -> None:
        """Positive values are accepted."""
        config = IngestionConfigurationCreate(
            unpaywall_email="a@b.com", retention_days=365
        )
        assert config.retention_days == 365

    def test_negative_value_rejected(self) -> None:
        """Negative values are rejected."""
        with pytest.raises(ValidationError):
            IngestionConfigurationCreate(
                unpaywall_email="a@b.com", retention_days=-1
            )

    def test_update_schema_minimum(self) -> None:
        """Update schema also enforces minimum 0."""
        with pytest.raises(ValidationError):
            IngestionConfigurationUpdate(retention_days=-5)

        valid = IngestionConfigurationUpdate(retention_days=0)
        assert valid.retention_days == 0
