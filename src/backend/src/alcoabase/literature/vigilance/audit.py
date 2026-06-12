"""Centralized audit logging for Medical Device Vigilance & PMS operations.

Provides structured, append-only audit event emission for all vigilance
operations. All entries are designed for ALCOA+ compliance (Attributable,
Legible, Contemporaneous, Original, Accurate + Complete, Consistent,
Enduring, Available).

Key design principles:
    - NEVER log full literature content, full document content, or LLM prompt/response text
    - All entries are append-only (Original and Enduring)
    - Structured extras enable log-based audit trail querying
    - Dedicated logger namespace ensures independent routing/filtering

Audit Event Schema:
    Every audit entry includes at minimum:
        - event_type: str — Identifies the operation category
        - timestamp: str — ISO-8601 UTC timestamp of the event
        - company_id: int — Tenant scope

    Event-specific fields are documented with each event type constant below.

References:
    - Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 13.7
    - Design: .kiro/specs/Step_9-5_regulatory-medical-device-vigilance-pms/design.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Dedicated audit logger — separate from application logs for independent
# routing/filtering in production log infrastructure.
# ---------------------------------------------------------------------------

audit_logger = logging.getLogger("alcoabase.audit.vigilance")

# ---------------------------------------------------------------------------
# Event Type Constants
# ---------------------------------------------------------------------------

# Search execution events (Requirement 12.1)
# Fields: execution_id, profile_id, product_id, company_id, sources_queried,
#          total_results_found, results_ingested, execution_duration_ms, status
EVENT_SEARCH_EXECUTION_COMPLETED = "vigilance.search_execution_completed"

# Signal creation events (Requirement 12.2)
# Fields: signal_id, ingestion_record_id, product_id, profile_id, company_id,
#          severity, confidence, detection_duration_ms
EVENT_SIGNAL_CREATED = "vigilance.signal_created"

# Signal disposition change events (Requirement 12.3)
# Fields: signal_id, company_id, previous_disposition, new_disposition,
#          acting_user_id, confirmation_note (if confirmed),
#          dismissal_reason (if dismissed)
EVENT_SIGNAL_DISPOSITION_CHANGED = "vigilance.signal_disposition_changed"

# Escalation events (Requirement 12.4)
# Fields: signal_id, company_id, escalation_type, target_service_invoked,
#          success
EVENT_ESCALATION_TRIGGERED = "vigilance.escalation_triggered"

# Report generation/status events (Requirement 12.5)
# Fields: report_id, product_id, company_id, period_start, period_end,
#          action (generated, status_change), new_status, acting_user_id
EVENT_REPORT_GENERATED = "vigilance.report_generated"
EVENT_REPORT_STATUS_CHANGED = "vigilance.report_status_changed"

# Product/profile creation/update/status events (Requirement 12.6)
# Fields: entity_type (product, profile), entity_id, company_id,
#          action (create, update, status_change), acting_user_id, changed_fields
EVENT_PRODUCT_CREATED = "vigilance.product_created"
EVENT_PRODUCT_UPDATED = "vigilance.product_updated"
EVENT_PRODUCT_STATUS_CHANGED = "vigilance.product_status_changed"
EVENT_PROFILE_CREATED = "vigilance.profile_created"
EVENT_PROFILE_UPDATED = "vigilance.profile_updated"
EVENT_PROFILE_STATUS_CHANGED = "vigilance.profile_status_changed"

# Retry attempt events (Requirement 13.7)
# Fields: task_type, attempt_number, error_message, backoff_duration_s,
#          entity_ids
EVENT_RETRY_ATTEMPT = "vigilance.retry_attempt"


# ---------------------------------------------------------------------------
# Helper Functions for Structured Audit Emission
# ---------------------------------------------------------------------------


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def log_search_execution(
    *,
    execution_id: int,
    profile_id: int,
    product_id: int,
    company_id: int,
    sources_queried: list[str],
    total_results_found: int,
    results_ingested: int,
    execution_duration_ms: int,
    status: str,
) -> None:
    """Log a vigilance search execution completion event (Requirement 12.1).

    Args:
        execution_id: ID of the VigilanceSearchExecution record.
        profile_id: ID of the VigilanceSearchProfile that was executed.
        product_id: ID of the associated MedicalProduct.
        company_id: Tenant scope.
        sources_queried: List of source adapter names queried.
        total_results_found: Total raw results from all sources.
        results_ingested: Results successfully ingested.
        execution_duration_ms: Total execution time in milliseconds.
        status: Final execution status (completed, partial_failure, failed).
    """
    audit_logger.info(
        "Search execution: execution_id=%d, profile_id=%d, product_id=%d, "
        "company_id=%d, status=%s, total_results=%d, ingested=%d, duration_ms=%d",
        execution_id,
        profile_id,
        product_id,
        company_id,
        status,
        total_results_found,
        results_ingested,
        execution_duration_ms,
        extra={
            "event_type": EVENT_SEARCH_EXECUTION_COMPLETED,
            "execution_id": execution_id,
            "profile_id": profile_id,
            "product_id": product_id,
            "company_id": company_id,
            "sources_queried": sources_queried,
            "total_results_found": total_results_found,
            "results_ingested": results_ingested,
            "execution_duration_ms": execution_duration_ms,
            "status": status,
            "timestamp": _utc_now_iso(),
        },
    )


def log_signal_created(
    *,
    signal_id: int,
    ingestion_record_id: int,
    product_id: int,
    profile_id: int,
    company_id: int,
    severity: str,
    confidence: float,
    detection_duration_ms: int,
) -> None:
    """Log a vigilance signal creation event (Requirement 12.2).

    Args:
        signal_id: ID of the created VigilanceSignal.
        ingestion_record_id: ID of the source IngestionRecord.
        product_id: ID of the associated MedicalProduct.
        profile_id: ID of the VigilanceSearchProfile.
        company_id: Tenant scope.
        severity: Signal severity (critical, major, minor).
        confidence: Detection confidence (0.0-1.0).
        detection_duration_ms: Time spent on LLM analysis.
    """
    audit_logger.info(
        "Signal created: signal_id=%d, record_id=%d, product_id=%d, "
        "severity=%s, confidence=%.3f, duration_ms=%d",
        signal_id,
        ingestion_record_id,
        product_id,
        severity,
        confidence,
        detection_duration_ms,
        extra={
            "event_type": EVENT_SIGNAL_CREATED,
            "signal_id": signal_id,
            "ingestion_record_id": ingestion_record_id,
            "product_id": product_id,
            "profile_id": profile_id,
            "company_id": company_id,
            "severity": severity,
            "confidence": confidence,
            "detection_duration_ms": detection_duration_ms,
            "timestamp": _utc_now_iso(),
        },
    )


def log_signal_disposition_changed(
    *,
    signal_id: int,
    company_id: int,
    previous_disposition: str,
    new_disposition: str,
    acting_user_id: int,
    confirmation_note: str | None = None,
    dismissal_reason: str | None = None,
) -> None:
    """Log a signal disposition change event (Requirement 12.3).

    Args:
        signal_id: ID of the VigilanceSignal.
        company_id: Tenant scope.
        previous_disposition: Previous disposition state.
        new_disposition: New disposition state.
        acting_user_id: User who performed the transition.
        confirmation_note: Confirmation note (if disposition is 'confirmed').
        dismissal_reason: Dismissal reason (if disposition is 'dismissed').
    """
    # Truncate notes to prevent logging excessive text
    truncated_note = (
        confirmation_note[:500] if confirmation_note else None
    )
    truncated_reason = (
        dismissal_reason[:500] if dismissal_reason else None
    )

    audit_logger.info(
        "Signal disposition changed: signal_id=%d, company_id=%d, "
        "%s → %s, user_id=%d",
        signal_id,
        company_id,
        previous_disposition,
        new_disposition,
        acting_user_id,
        extra={
            "event_type": EVENT_SIGNAL_DISPOSITION_CHANGED,
            "signal_id": signal_id,
            "company_id": company_id,
            "previous_disposition": previous_disposition,
            "new_disposition": new_disposition,
            "acting_user_id": acting_user_id,
            "confirmation_note": truncated_note,
            "dismissal_reason": truncated_reason,
            "timestamp": _utc_now_iso(),
        },
    )


def log_escalation(
    *,
    signal_id: int,
    company_id: int,
    escalation_type: str,
    target_service_invoked: str,
    success: bool,
) -> None:
    """Log an escalation event (Requirement 12.4).

    Args:
        signal_id: ID of the escalated VigilanceSignal.
        company_id: Tenant scope.
        escalation_type: Type of escalation (impact_analysis, contradiction_check,
                         notification, slr_inclusion).
        target_service_invoked: Name of the invoked service.
        success: Whether the escalation sub-task succeeded.
    """
    audit_logger.info(
        "Escalation: signal_id=%d, company_id=%d, type=%s, "
        "service=%s, success=%s",
        signal_id,
        company_id,
        escalation_type,
        target_service_invoked,
        success,
        extra={
            "event_type": EVENT_ESCALATION_TRIGGERED,
            "signal_id": signal_id,
            "company_id": company_id,
            "escalation_type": escalation_type,
            "target_service_invoked": target_service_invoked,
            "success": success,
            "timestamp": _utc_now_iso(),
        },
    )


def log_report_event(
    *,
    report_id: int,
    product_id: int,
    company_id: int,
    period_start: str,
    period_end: str,
    action: str,
    new_status: str,
    acting_user_id: int | None = None,
) -> None:
    """Log a report generation or status change event (Requirement 12.5).

    Args:
        report_id: ID of the PeriodicSafetyReport.
        product_id: ID of the associated MedicalProduct.
        company_id: Tenant scope.
        period_start: Report period start date (ISO-8601).
        period_end: Report period end date (ISO-8601).
        action: Action performed ('generated' or 'status_change').
        new_status: New report status.
        acting_user_id: User who triggered the action (None for auto-generation).
    """
    event_type = (
        EVENT_REPORT_GENERATED if action == "generated" else EVENT_REPORT_STATUS_CHANGED
    )
    audit_logger.info(
        "Report event: report_id=%d, product_id=%d, company_id=%d, "
        "action=%s, status=%s, user_id=%s",
        report_id,
        product_id,
        company_id,
        action,
        new_status,
        acting_user_id,
        extra={
            "event_type": event_type,
            "report_id": report_id,
            "product_id": product_id,
            "company_id": company_id,
            "period_start": period_start,
            "period_end": period_end,
            "action": action,
            "new_status": new_status,
            "acting_user_id": acting_user_id,
            "timestamp": _utc_now_iso(),
        },
    )


def log_entity_event(
    *,
    entity_type: str,
    entity_id: int,
    company_id: int,
    action: str,
    acting_user_id: int,
    changed_fields: list[str] | None = None,
) -> None:
    """Log a product or profile creation/update/status event (Requirement 12.6).

    Args:
        entity_type: Type of entity ('product' or 'profile').
        entity_id: ID of the entity.
        company_id: Tenant scope.
        action: Action performed ('create', 'update', 'status_change').
        acting_user_id: User who performed the action.
        changed_fields: List of field names that were changed (for updates).
    """
    event_type_map = {
        ("product", "create"): EVENT_PRODUCT_CREATED,
        ("product", "update"): EVENT_PRODUCT_UPDATED,
        ("product", "status_change"): EVENT_PRODUCT_STATUS_CHANGED,
        ("profile", "create"): EVENT_PROFILE_CREATED,
        ("profile", "update"): EVENT_PROFILE_UPDATED,
        ("profile", "status_change"): EVENT_PROFILE_STATUS_CHANGED,
    }
    event_type = event_type_map.get(
        (entity_type, action), f"vigilance.{entity_type}_{action}"
    )

    audit_logger.info(
        "Entity event: type=%s, id=%d, company_id=%d, action=%s, user_id=%d",
        entity_type,
        entity_id,
        company_id,
        action,
        acting_user_id,
        extra={
            "event_type": event_type,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "company_id": company_id,
            "action": action,
            "acting_user_id": acting_user_id,
            "changed_fields": changed_fields or [],
            "timestamp": _utc_now_iso(),
        },
    )


def log_retry_attempt(
    *,
    task_type: str,
    attempt_number: int,
    error_message: str,
    backoff_duration_s: int,
    entity_ids: dict[str, Any],
) -> None:
    """Log a retry attempt event for any vigilance task (Requirement 13.7).

    Never logs full error tracebacks — only the first 500 characters of
    the error message to avoid leaking sensitive content.

    Args:
        task_type: Type of Celery task being retried (e.g., 'search_execution',
                   'signal_detection', 'escalation', 'report_generation').
        attempt_number: Current attempt number (1-based).
        error_message: Description of the error that triggered the retry.
        backoff_duration_s: Duration in seconds before next retry.
        entity_ids: Dict of relevant entity IDs (e.g., {'profile_id': 42}).
    """
    # Truncate error message to prevent logging excessive content
    truncated_error = error_message[:500] if error_message else ""

    audit_logger.info(
        "Retry attempt: task=%s, attempt=%d, backoff=%ds, error=%s",
        task_type,
        attempt_number,
        backoff_duration_s,
        truncated_error,
        extra={
            "event_type": EVENT_RETRY_ATTEMPT,
            "task_type": task_type,
            "attempt_number": attempt_number,
            "error_message": truncated_error,
            "backoff_duration_s": backoff_duration_s,
            "entity_ids": entity_ids,
            "timestamp": _utc_now_iso(),
        },
    )
