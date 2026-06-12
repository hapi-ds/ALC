"""Custom exception hierarchy for the Vigilance & Post-Market Surveillance module.

All exceptions raised by the vigilance subsystem inherit from
``VigilanceError``.  Domain-specific errors use dedicated subclasses
grouped by concern: product management, profile/schedule management,
search execution, signal processing, infrastructure, and configuration.

References:
    - Requirements 2.2, 3.2, 6.4, 8.6, 13.1, 13.3, 13.4, 13.6, 14.9
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Base Exception
# ─────────────────────────────────────────────────────────────────────────────


class VigilanceError(Exception):
    """Base exception for all vigilance module errors.

    Attributes:
        message: Human-readable error description.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Product Management Errors
# ─────────────────────────────────────────────────────────────────────────────


class DuplicateUDIError(VigilanceError):
    """Raised when a Medical Product is created or updated with a UDI that
    already exists within the same company.

    Maps to HTTP 409 Conflict.

    Attributes:
        message: Human-readable error description.
        udi: The duplicate UDI value.
        company_id: The company in which the conflict occurred.
    """

    def __init__(
        self,
        message: str,
        *,
        udi: str,
        company_id: int,
    ) -> None:
        self.udi = udi
        self.company_id = company_id
        super().__init__(message)


class ProductNotFoundError(VigilanceError):
    """Raised when a Medical Product cannot be found by ID within a company.

    Maps to HTTP 404 Not Found.

    Attributes:
        message: Human-readable error description.
        product_id: The requested product ID.
        company_id: The company scope of the lookup.
    """

    def __init__(
        self,
        message: str,
        *,
        product_id: int,
        company_id: int,
    ) -> None:
        self.product_id = product_id
        self.company_id = company_id
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Profile & Schedule Errors
# ─────────────────────────────────────────────────────────────────────────────


class ProfileNotFoundError(VigilanceError):
    """Raised when a Vigilance Search Profile cannot be found by ID within
    a company.

    Maps to HTTP 404 Not Found.

    Attributes:
        message: Human-readable error description.
        profile_id: The requested profile ID.
        company_id: The company scope of the lookup.
    """

    def __init__(
        self,
        message: str,
        *,
        profile_id: int,
        company_id: int,
    ) -> None:
        self.profile_id = profile_id
        self.company_id = company_id
        super().__init__(message)


class InvalidCronExpressionError(VigilanceError):
    """Raised when a Vigilance Search Profile's schedule_cron field does not
    conform to valid 5-field cron expression syntax.

    Maps to HTTP 422 Unprocessable Entity.

    Attributes:
        message: Human-readable error description.
        expression: The invalid cron expression that was provided.
    """

    def __init__(
        self,
        message: str,
        *,
        expression: str,
    ) -> None:
        self.expression = expression
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Signal Processing Errors
# ─────────────────────────────────────────────────────────────────────────────


class SignalNotFoundError(VigilanceError):
    """Raised when a Vigilance Signal cannot be found by ID within a company.

    Maps to HTTP 404 Not Found.

    Attributes:
        message: Human-readable error description.
        signal_id: The requested signal ID.
        company_id: The company scope of the lookup.
    """

    def __init__(
        self,
        message: str,
        *,
        signal_id: int,
        company_id: int,
    ) -> None:
        self.signal_id = signal_id
        self.company_id = company_id
        super().__init__(message)


class InvalidDispositionTransitionError(VigilanceError):
    """Raised when a disposition change on a Vigilance Signal violates the
    allowed state machine transitions.

    Valid transitions:
        under_review → confirmed | dismissed | escalated
        confirmed → escalated

    Maps to HTTP 422 Unprocessable Entity.

    Attributes:
        message: Human-readable error description.
        signal_id: The signal whose transition was rejected.
        current_disposition: The signal's current disposition state.
        requested_disposition: The invalid target disposition.
    """

    def __init__(
        self,
        message: str,
        *,
        signal_id: int,
        current_disposition: str,
        requested_disposition: str,
    ) -> None:
        self.signal_id = signal_id
        self.current_disposition = current_disposition
        self.requested_disposition = requested_disposition
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Report Errors
# ─────────────────────────────────────────────────────────────────────────────


class ReportNotFoundError(VigilanceError):
    """Raised when a Periodic Safety Report cannot be found by ID within
    a company.

    Maps to HTTP 404 Not Found.

    Attributes:
        message: Human-readable error description.
        report_id: The requested report ID.
        company_id: The company scope of the lookup.
    """

    def __init__(
        self,
        message: str,
        *,
        report_id: int,
        company_id: int,
    ) -> None:
        self.report_id = report_id
        self.company_id = company_id
        super().__init__(message)


class InvalidReportStatusTransitionError(VigilanceError):
    """Raised when a status change on a Periodic Safety Report violates the
    allowed lifecycle transitions.

    Valid transitions:
        generated → reviewed → approved → submitted

    Maps to HTTP 422 Unprocessable Entity.

    Attributes:
        message: Human-readable error description.
        report_id: The report whose transition was rejected.
        current_status: The report's current status.
        requested_status: The invalid target status.
    """

    def __init__(
        self,
        message: str,
        *,
        report_id: int,
        current_status: str,
        requested_status: str,
    ) -> None:
        self.report_id = report_id
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Execution & Infrastructure Errors
# ─────────────────────────────────────────────────────────────────────────────


class DuplicateExecutionError(VigilanceError):
    """Raised when a vigilance search execution is triggered while a previous
    execution for the same profile is still in progress.

    The system enforces idempotent execution: overlapping runs are skipped
    to prevent duplicate work from Celery beat clock skew or restart overlap.

    Attributes:
        message: Human-readable error description.
        profile_id: The profile that already has a running execution.
        existing_execution_id: The ID of the in-progress execution.
    """

    def __init__(
        self,
        message: str,
        *,
        profile_id: int,
        existing_execution_id: int,
    ) -> None:
        self.profile_id = profile_id
        self.existing_execution_id = existing_execution_id
        super().__init__(message)


class ExecutionTimeoutError(VigilanceError):
    """Raised when a vigilance search execution exceeds the configured maximum
    execution time (default: 60 minutes).

    The execution is marked as ``partial_failure`` and all results obtained
    prior to the timeout are persisted.

    Attributes:
        message: Human-readable error description.
        execution_id: The execution that timed out.
        timeout_seconds: The timeout threshold that was exceeded.
        elapsed_seconds: Actual elapsed time before timeout was triggered.
    """

    def __init__(
        self,
        message: str,
        *,
        execution_id: int,
        timeout_seconds: int,
        elapsed_seconds: int,
    ) -> None:
        self.execution_id = execution_id
        self.timeout_seconds = timeout_seconds
        self.elapsed_seconds = elapsed_seconds
        super().__init__(message)


class GatewayUnavailableError(VigilanceError):
    """Raised when the Literature Gateway Service is unavailable and all retry
    attempts have been exhausted during a vigilance search execution.

    The execution is marked as ``failed`` and the failure is recorded in
    the audit trail.

    Attributes:
        message: Human-readable error description.
        profile_id: The profile whose search could not be executed.
        retry_attempts: Number of retries attempted before giving up.
    """

    def __init__(
        self,
        message: str,
        *,
        profile_id: int,
        retry_attempts: int = 3,
    ) -> None:
        self.profile_id = profile_id
        self.retry_attempts = retry_attempts
        super().__init__(message)


class InferenceConnectionError(VigilanceError):
    """Raised when the vLLM inference service is unreachable during signal
    detection analysis and all retry attempts have been exhausted.

    The affected Ingestion Record is flagged for manual review without
    blocking other pending detections in the same batch.

    Attributes:
        message: Human-readable error description.
        record_id: The ingestion record whose analysis failed.
        retry_attempts: Number of retries attempted before giving up.
    """

    def __init__(
        self,
        message: str,
        *,
        record_id: int,
        retry_attempts: int = 3,
    ) -> None:
        self.record_id = record_id
        self.retry_attempts = retry_attempts
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Configuration Errors
# ─────────────────────────────────────────────────────────────────────────────


class ConfigurationRangeError(VigilanceError):
    """Raised when a vigilance configuration environment variable contains
    a non-numeric value or a value outside its accepted range.

    The application refuses to start when this error is raised during
    settings validation.

    Attributes:
        message: Human-readable error description.
        variable_name: The environment variable that failed validation.
        provided_value: The invalid value that was provided.
        accepted_range: Description of the valid range (e.g., "0.1–1.0").
    """

    def __init__(
        self,
        message: str,
        *,
        variable_name: str,
        provided_value: str,
        accepted_range: str,
    ) -> None:
        self.variable_name = variable_name
        self.provided_value = provided_value
        self.accepted_range = accepted_range
        super().__init__(message)
