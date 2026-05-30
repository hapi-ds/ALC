"""Application-layer immutability enforcement for GxP audit trail models.

This module provides SQLAlchemy event listeners that prevent UPDATE and DELETE
operations on immutable models (GenerationProvenance, CrossReferenceEntry,
ImpactReport, GapAnalysisResult, TraceabilityMatrix, CoverageSnapshot).
These models are append-only to satisfy GxP audit trail requirements — once
a record is created, it must never be modified or removed.

TraceabilityMatrix has a special soft-delete allowance: the before_update
listener permits mutations only to the deleted_at column, raising
ImmutableRecordError for any other column change.

The enforcement is at the application layer (ORM events) rather than the
database layer, providing clear error messages and preventing accidental
mutations through the ORM. Database-level triggers could provide additional
defense-in-depth but are not required for this implementation.

References:
    - Requirements: 5.4, 5.7, 5.8, 8.2, 8.3, 10.1, 10.2
    - Design: Immutable provenance records (Design Decision #6)
    - Design: Immutable matrix records (Design Decision #2, Phase 5.6)
"""

import logging

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class ImmutableRecordError(Exception):
    """Raised when an UPDATE or DELETE is attempted on an immutable record.

    Immutable records (GenerationProvenance, CrossReferenceEntry) are
    append-only to satisfy GxP audit trail requirements. Once created,
    these records must never be modified or deleted.

    Attributes:
        model_name: Name of the model class that was targeted.
        operation: The prohibited operation ("update" or "delete").
        record_id: The primary key of the targeted record, if available.
    """

    def __init__(
        self,
        model_name: str,
        operation: str,
        record_id: int | None = None,
    ) -> None:
        self.model_name = model_name
        self.operation = operation
        self.record_id = record_id
        id_info = f" (id={record_id})" if record_id is not None else ""
        super().__init__(
            f"Cannot {operation} immutable record: {model_name}{id_info}. "
            f"GxP audit trail records are append-only and must never be "
            f"modified or deleted."
        )


def _prevent_update(mapper, connection, target) -> None:  # noqa: ANN001
    """SQLAlchemy before_update event handler that raises ImmutableRecordError.

    This listener is attached to immutable models to prevent any UPDATE
    operations through the ORM.

    Args:
        mapper: The SQLAlchemy mapper for the target class.
        connection: The database connection.
        target: The model instance being updated.

    Raises:
        ImmutableRecordError: Always raised to prevent the update.
    """
    model_name = type(target).__name__
    record_id = getattr(target, "id", None)
    logger.error(
        "Attempted UPDATE on immutable record %s (id=%s). "
        "This violates GxP audit trail requirements.",
        model_name,
        record_id,
    )
    raise ImmutableRecordError(
        model_name=model_name,
        operation="update",
        record_id=record_id,
    )


def _prevent_delete(mapper, connection, target) -> None:  # noqa: ANN001
    """SQLAlchemy before_delete event handler that raises ImmutableRecordError.

    This listener is attached to immutable models to prevent any DELETE
    operations through the ORM.

    Args:
        mapper: The SQLAlchemy mapper for the target class.
        connection: The database connection.
        target: The model instance being deleted.

    Raises:
        ImmutableRecordError: Always raised to prevent the deletion.
    """
    model_name = type(target).__name__
    record_id = getattr(target, "id", None)
    logger.error(
        "Attempted DELETE on immutable record %s (id=%s). "
        "This violates GxP audit trail requirements.",
        model_name,
        record_id,
    )
    raise ImmutableRecordError(
        model_name=model_name,
        operation="delete",
        record_id=record_id,
    )


def _prevent_update_except_deleted_at(mapper, connection, target) -> None:  # noqa: ANN001
    """SQLAlchemy before_update event handler that permits only deleted_at mutation.

    This listener is attached to TraceabilityMatrix to allow soft-delete
    (setting deleted_at) while preventing any other column mutation.

    Args:
        mapper: The SQLAlchemy mapper for the target class.
        connection: The database connection.
        target: The model instance being updated.

    Raises:
        ImmutableRecordError: If any column other than deleted_at is modified.
    """
    model_name = type(target).__name__
    record_id = getattr(target, "id", None)
    insp = inspect(target)

    for attr in insp.attrs:
        if attr.key == "deleted_at":
            continue
        history = attr.history
        if history.has_changes():
            logger.error(
                "Attempted UPDATE on immutable column '%s' of %s (id=%s). "
                "Only deleted_at mutation is permitted for soft-delete.",
                attr.key,
                model_name,
                record_id,
            )
            raise ImmutableRecordError(
                model_name=model_name,
                operation="update",
                record_id=record_id,
            )


def register_immutability_listeners() -> None:
    """Register SQLAlchemy event listeners for immutable models.

    Attaches before_update and before_delete listeners to
    GenerationProvenance, CrossReferenceEntry, ImpactReport,
    GapAnalysisResult, TraceabilityMatrix, CoverageSnapshot,
    RiskAssessmentRecord, AIOperationLog, and ControlEnforcementLog models,
    preventing modification or deletion of these append-only audit records.

    TraceabilityMatrix uses a special listener that permits only deleted_at
    mutation (soft-delete) while blocking all other column changes.

    This function should be called once during application startup,
    after all models have been imported.
    """
    from alcoabase.models.document_generation import (
        CrossReferenceEntry,
        GenerationProvenance,
    )
    from alcoabase.models.impact_analysis import GapAnalysisResult, ImpactReport
    from alcoabase.models.risk_framework import (
        AIOperationLog,
        ControlEnforcementLog,
        RiskAssessmentRecord,
    )
    from alcoabase.models.traceability import CoverageSnapshot, TraceabilityMatrix

    # Prevent UPDATE on fully immutable models
    event.listen(GenerationProvenance, "before_update", _prevent_update)
    event.listen(CrossReferenceEntry, "before_update", _prevent_update)
    event.listen(ImpactReport, "before_update", _prevent_update)
    event.listen(GapAnalysisResult, "before_update", _prevent_update)
    event.listen(CoverageSnapshot, "before_update", _prevent_update)
    event.listen(RiskAssessmentRecord, "before_update", _prevent_update)
    event.listen(AIOperationLog, "before_update", _prevent_update)
    event.listen(ControlEnforcementLog, "before_update", _prevent_update)

    # TraceabilityMatrix: permit only deleted_at mutation (soft-delete)
    event.listen(
        TraceabilityMatrix, "before_update", _prevent_update_except_deleted_at
    )

    # Prevent DELETE on all immutable models
    event.listen(GenerationProvenance, "before_delete", _prevent_delete)
    event.listen(CrossReferenceEntry, "before_delete", _prevent_delete)
    event.listen(ImpactReport, "before_delete", _prevent_delete)
    event.listen(GapAnalysisResult, "before_delete", _prevent_delete)
    event.listen(TraceabilityMatrix, "before_delete", _prevent_delete)
    event.listen(CoverageSnapshot, "before_delete", _prevent_delete)
    event.listen(RiskAssessmentRecord, "before_delete", _prevent_delete)
    event.listen(AIOperationLog, "before_delete", _prevent_delete)
    event.listen(ControlEnforcementLog, "before_delete", _prevent_delete)

    logger.info(
        "Registered immutability listeners for GenerationProvenance, "
        "CrossReferenceEntry, ImpactReport, GapAnalysisResult, "
        "TraceabilityMatrix, CoverageSnapshot, RiskAssessmentRecord, "
        "AIOperationLog, and ControlEnforcementLog "
        "(GxP audit trail enforcement)."
    )
