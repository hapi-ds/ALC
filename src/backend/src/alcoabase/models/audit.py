"""Audit mixin for SQLAlchemy-Continuum versioning.

This module provides the AuditMixin class that enables automatic audit trail
versioning on any SQLAlchemy model that inherits from it. When combined with
the `make_versioned()` call in `alcoabase.database`, Continuum automatically
creates `{table}_version` tables that record:
    - transaction_id: Links all changes in a single request
    - operation_type: INSERT (0), UPDATE (1), DELETE (2)
    - All column snapshots at the time of the change

Usage:
    from alcoabase.database import Base
    from alcoabase.models.audit import AuditMixin

    class Document(Base, AuditMixin):
        __tablename__ = "documents"
        ...

References:
    - SQLAlchemy-Continuum: https://sqlalchemy-continuum.readthedocs.io/
    - ALCOA+ data integrity: attributable, legible, contemporaneous, original, accurate
"""

from typing import ClassVar


class AuditMixin:
    """Mixin that enables SQLAlchemy-Continuum versioning on any model.

    Models inheriting this mixin automatically get audit trail versioning
    via SQLAlchemy-Continuum. A corresponding `{table}_version` table is
    created that stores historical snapshots of every INSERT, UPDATE, and
    DELETE operation.

    The `is_csv_validation_record` column is excluded from versioning to
    prevent CSV Runner test data from polluting the GxP audit trail.

    Attributes:
        __versioned__: Continuum configuration dict controlling versioning
            behavior for the model.
    """

    __versioned__: ClassVar[dict[str, list[str]]] = {
        "exclude": ["is_csv_validation_record"],
    }
