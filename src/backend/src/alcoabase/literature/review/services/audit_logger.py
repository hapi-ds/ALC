"""Structured audit logger for literature review operations.

Provides typed helper functions that emit structured, append-only audit
log entries for all literature review events: screening decisions, human
overrides, contradiction alerts, novelty flags, SLR review state transitions,
and retry attempts.

All entries use Python's logging module with structured data in the `extra`
field. This enables integration with centralized log aggregation (ELK, etc.)
while maintaining ALCOA+ Original and Enduring principles.

IMPORTANT: This module NEVER logs full paper content, internal document content,
or LLM prompt/response text. Only metadata identifiers, verdicts, metrics, and
timestamps are recorded.

References:
    - Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 13.8
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

# Dedicated audit logger — separate from application loggers to allow
# independent routing/filtering in production log infrastructure.
audit_logger = logging.getLogger("alcoabase.audit.literature_review")

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

EVENT_SCREENING_DECISION = "literature_review.screening_decision"
EVENT_HUMAN_OVERRIDE = "literature_review.human_override"
EVENT_CONTRADICTION_ALERT_CREATED = "literature_review.contradiction_alert_created"
EVENT_CONTRADICTION_ALERT_STATUS_CHANGE = (
    "literature_review.contradiction_alert_status_change"
)
EVENT_NOVELTY_FLAG_CREATED = "literature_review.novelty_flag_created"
EVENT_SLR_REVIEW_STATE_TRANSITION = "literature_review.slr_review_state_transition"
EVENT_RETRY_ATTEMPT = "literature_review.retry_attempt"


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def log_screening_decision(
    *,
    screening_run_id: int,
    ingestion_record_id: int,
    protocol_id: int,
    company_id: int,
    verdict: str,
    confidence: float,
    agent_model_name: str,
    screening_duration_ms: int,
    timestamp: datetime | None = None,
) -> None:
    """Log a screening decision event.

    Emits a structured audit entry when the Literature Screener Agent
    produces a screening decision for an ingestion record.

    Args:
        screening_run_id: ID of the screening run.
        ingestion_record_id: ID of the ingestion record screened.
        protocol_id: ID of the screening protocol used.
        company_id: Tenant company ID.
        verdict: Screening verdict (include, exclude, uncertain).
        confidence: Confidence score (0.0–1.0).
        agent_model_name: Name of the LLM model used for screening.
        screening_duration_ms: Duration of the screening in milliseconds.
        timestamp: Event timestamp. Defaults to current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    audit_logger.info(
        "Screening decision recorded: run_id=%d, record_id=%d, "
        "protocol_id=%d, company_id=%d, verdict=%s, confidence=%.4f",
        screening_run_id,
        ingestion_record_id,
        protocol_id,
        company_id,
        verdict,
        confidence,
        extra={
            "event_type": EVENT_SCREENING_DECISION,
            "screening_run_id": screening_run_id,
            "ingestion_record_id": ingestion_record_id,
            "protocol_id": protocol_id,
            "company_id": company_id,
            "verdict": verdict,
            "confidence": confidence,
            "agent_model_name": agent_model_name,
            "screening_duration_ms": screening_duration_ms,
            "timestamp": timestamp.isoformat(),
        },
    )


def log_human_override(
    *,
    decision_id: int,
    review_id: int,
    company_id: int,
    original_verdict: str,
    human_verdict: str,
    reviewer_user_id: int,
    timestamp: datetime | None = None,
) -> None:
    """Log a human override event for a screening decision.

    Emits a structured audit entry when a human reviewer overrides
    an AI screening decision.

    Args:
        decision_id: ID of the screening decision being overridden.
        review_id: ID of the SLR review.
        company_id: Tenant company ID.
        original_verdict: The AI's original verdict.
        human_verdict: The human reviewer's verdict.
        reviewer_user_id: ID of the human reviewer.
        timestamp: Event timestamp. Defaults to current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    audit_logger.info(
        "Human override recorded: decision_id=%d, review_id=%d, "
        "company_id=%d, original=%s, human=%s, reviewer=%d",
        decision_id,
        review_id,
        company_id,
        original_verdict,
        human_verdict,
        reviewer_user_id,
        extra={
            "event_type": EVENT_HUMAN_OVERRIDE,
            "decision_id": decision_id,
            "review_id": review_id,
            "company_id": company_id,
            "original_verdict": original_verdict,
            "human_verdict": human_verdict,
            "reviewer_user_id": reviewer_user_id,
            "timestamp": timestamp.isoformat(),
        },
    )


def log_contradiction_alert_created(
    *,
    alert_id: int,
    ingestion_record_id: int,
    internal_document_id: str,
    company_id: int,
    severity: str,
    confidence: float,
    detection_duration_ms: int,
    timestamp: datetime | None = None,
) -> None:
    """Log a contradiction alert creation event.

    Emits a structured audit entry when the Contradiction Detection Service
    creates a new contradiction alert.

    Args:
        alert_id: ID of the created contradiction alert.
        ingestion_record_id: ID of the ingestion record that triggered detection.
        internal_document_id: Identifier of the internal document contradicted.
        company_id: Tenant company ID.
        severity: Contradiction severity (critical, major, minor).
        confidence: Detection confidence (0.0–1.0).
        detection_duration_ms: Duration of the detection analysis in milliseconds.
        timestamp: Event timestamp. Defaults to current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    audit_logger.info(
        "Contradiction alert created: alert_id=%d, record_id=%d, "
        "internal_doc=%s, company_id=%d, severity=%s, confidence=%.4f",
        alert_id,
        ingestion_record_id,
        internal_document_id,
        company_id,
        severity,
        confidence,
        extra={
            "event_type": EVENT_CONTRADICTION_ALERT_CREATED,
            "alert_id": alert_id,
            "ingestion_record_id": ingestion_record_id,
            "internal_document_id": internal_document_id,
            "company_id": company_id,
            "severity": severity,
            "confidence": confidence,
            "detection_duration_ms": detection_duration_ms,
            "timestamp": timestamp.isoformat(),
        },
    )


def log_contradiction_alert_status_change(
    *,
    alert_id: int,
    company_id: int,
    previous_status: str,
    new_status: str,
    acting_user_id: int,
    resolution_note: str | None = None,
    dismissal_reason: str | None = None,
    timestamp: datetime | None = None,
) -> None:
    """Log a contradiction alert status change event.

    Emits a structured audit entry when a contradiction alert's status
    is updated (e.g., new → acknowledged → resolved/dismissed).

    Args:
        alert_id: ID of the contradiction alert.
        company_id: Tenant company ID.
        previous_status: The alert's status before the change.
        new_status: The alert's new status.
        acting_user_id: ID of the user who changed the status.
        resolution_note: Optional note when resolving (max 3000 chars).
        dismissal_reason: Optional reason when dismissing (max 2000 chars).
        timestamp: Event timestamp. Defaults to current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    extra_data: dict[str, object] = {
        "event_type": EVENT_CONTRADICTION_ALERT_STATUS_CHANGE,
        "alert_id": alert_id,
        "company_id": company_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "acting_user_id": acting_user_id,
        "timestamp": timestamp.isoformat(),
    }

    if resolution_note is not None:
        # Truncate to prevent oversized log entries
        extra_data["resolution_note"] = resolution_note[:3000]
    if dismissal_reason is not None:
        extra_data["dismissal_reason"] = dismissal_reason[:2000]

    audit_logger.info(
        "Contradiction alert status changed: alert_id=%d, company_id=%d, "
        "%s -> %s, user_id=%d",
        alert_id,
        company_id,
        previous_status,
        new_status,
        acting_user_id,
        extra=extra_data,
    )


def log_novelty_flag_created(
    *,
    flag_id: int,
    ingestion_record_id: int,
    company_id: int,
    relevance_score: float,
    high_priority: bool,
    timestamp: datetime | None = None,
) -> None:
    """Log a novelty flag creation event.

    Emits a structured audit entry when the Contradiction Detection Service
    creates a novelty flag for a paper with no matching internal documents.

    Args:
        flag_id: ID of the created novelty flag.
        ingestion_record_id: ID of the ingestion record flagged as novel.
        company_id: Tenant company ID.
        relevance_score: Relevance score (0.0–1.0).
        high_priority: Whether the flag is high priority (score >= 0.8).
        timestamp: Event timestamp. Defaults to current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    audit_logger.info(
        "Novelty flag created: flag_id=%d, record_id=%d, company_id=%d, "
        "relevance_score=%.4f, high_priority=%s",
        flag_id,
        ingestion_record_id,
        company_id,
        relevance_score,
        high_priority,
        extra={
            "event_type": EVENT_NOVELTY_FLAG_CREATED,
            "flag_id": flag_id,
            "ingestion_record_id": ingestion_record_id,
            "company_id": company_id,
            "relevance_score": relevance_score,
            "high_priority": high_priority,
            "timestamp": timestamp.isoformat(),
        },
    )


def log_slr_review_state_transition(
    *,
    review_id: int,
    company_id: int,
    previous_state: str,
    new_state: str,
    acting_user_id: int,
    timestamp: datetime | None = None,
) -> None:
    """Log an SLR review state transition event.

    Emits a structured audit entry when an SLR review transitions
    between lifecycle states.

    Args:
        review_id: ID of the SLR review.
        company_id: Tenant company ID.
        previous_state: The review's state before the transition.
        new_state: The review's new state.
        acting_user_id: ID of the user who triggered the transition.
        timestamp: Event timestamp. Defaults to current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    audit_logger.info(
        "SLR review state transition: review_id=%d, company_id=%d, "
        "%s -> %s, user_id=%d",
        review_id,
        company_id,
        previous_state,
        new_state,
        acting_user_id,
        extra={
            "event_type": EVENT_SLR_REVIEW_STATE_TRANSITION,
            "review_id": review_id,
            "company_id": company_id,
            "previous_state": previous_state,
            "new_state": new_state,
            "acting_user_id": acting_user_id,
            "timestamp": timestamp.isoformat(),
        },
    )


def log_retry_attempt(
    *,
    task_type: str,
    attempt_number: int,
    error_message: str,
    backoff_duration_s: float,
    timestamp: datetime | None = None,
) -> None:
    """Log a retry attempt event for screening or contradiction detection.

    Emits a structured audit entry when a task retries after a failure.
    The error_message is truncated to prevent oversized entries and to
    avoid leaking LLM prompt/response content.

    Args:
        task_type: Type of task being retried (e.g., "screening_batch",
            "cross_reference", "contradiction_analysis").
        attempt_number: Which retry attempt this is (1-indexed).
        error_message: Brief description of the error that triggered retry.
            Must NOT contain LLM prompts/responses or paper content.
        backoff_duration_s: Backoff wait time in seconds before retry.
        timestamp: Event timestamp. Defaults to current UTC time.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    # Truncate error message to prevent oversized log entries
    safe_error = error_message[:500] if len(error_message) > 500 else error_message

    audit_logger.info(
        "Retry attempt: task_type=%s, attempt=%d, backoff=%.1fs, error=%s",
        task_type,
        attempt_number,
        backoff_duration_s,
        safe_error,
        extra={
            "event_type": EVENT_RETRY_ATTEMPT,
            "task_type": task_type,
            "attempt_number": attempt_number,
            "error_message": safe_error,
            "backoff_duration_s": backoff_duration_s,
            "timestamp": timestamp.isoformat(),
        },
    )
