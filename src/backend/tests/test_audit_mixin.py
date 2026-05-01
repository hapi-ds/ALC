"""Tests for the AuditMixin class."""

from alcoabase.models.audit import AuditMixin


class TestAuditMixin:
    """Tests for AuditMixin Continuum configuration."""

    def test_versioned_attribute_exists(self) -> None:
        """AuditMixin defines __versioned__ for Continuum."""
        assert hasattr(AuditMixin, "__versioned__")

    def test_versioned_excludes_csv_validation_record(self) -> None:
        """is_csv_validation_record is excluded from versioning."""
        assert "exclude" in AuditMixin.__versioned__
        assert "is_csv_validation_record" in AuditMixin.__versioned__["exclude"]

    def test_versioned_exclude_contains_only_expected_fields(self) -> None:
        """Only is_csv_validation_record is excluded."""
        assert AuditMixin.__versioned__["exclude"] == ["is_csv_validation_record"]

    def test_mixin_usable_with_inheritance(self) -> None:
        """AuditMixin can be used as a mixin in multiple inheritance."""

        class FakeModel(AuditMixin):
            __tablename__ = "fake_table"

        assert FakeModel.__versioned__ == {"exclude": ["is_csv_validation_record"]}

    def test_mixin_does_not_define_tablename(self) -> None:
        """AuditMixin does not set __tablename__ (it's a mixin, not a model)."""
        assert not hasattr(AuditMixin, "__tablename__")

    def test_package_level_export(self) -> None:
        """AuditMixin is importable from the models package."""
        from alcoabase.models import AuditMixin as PackageAuditMixin

        assert PackageAuditMixin is AuditMixin
