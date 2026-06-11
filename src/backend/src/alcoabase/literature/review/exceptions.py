"""Custom exception hierarchy for the Literature Review & Synthesis subsystem.

All exceptions raised by the literature review components inherit from
``LiteratureReviewError``.  State machine violations, entity lookups,
screening configuration issues, and operational constraints each have
dedicated exception classes.

References:
    - Requirements 4.1, 6.4, 7.4, 2.10, 11.6, 13.4
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Base Exception
# ─────────────────────────────────────────────────────────────────────────────


class LiteratureReviewError(Exception):
    """Base exception for all literature review errors.

    Attributes:
        message: Human-readable error description.
    """

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# State Machine Errors
# ─────────────────────────────────────────────────────────────────────────────


class InvalidStateTransitionError(LiteratureReviewError):
    """Raised when a state transition violates the allowed lifecycle transitions.

    For example, attempting to transition an SLR_Review from
    ``protocol_defined`` directly to ``completed`` without passing
    through intermediate states.

    Attributes:
        message: Human-readable error description.
        current_state: The entity's current lifecycle state.
        target_state: The disallowed target state that was requested.
    """

    def __init__(
        self,
        message: str,
        *,
        current_state: str,
        target_state: str,
    ) -> None:
        self.current_state = current_state
        self.target_state = target_state
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Entity Not Found Errors
# ─────────────────────────────────────────────────────────────────────────────


class ProtocolNotFoundError(LiteratureReviewError):
    """Raised when a Screening Protocol cannot be found.

    Typically occurs when a protocol_id does not exist within the
    requesting company's scope.

    Attributes:
        message: Human-readable error description.
        protocol_id: The protocol identifier that was not found.
        company_id: The company scope in which the lookup was performed.
    """

    def __init__(
        self,
        message: str,
        *,
        protocol_id: int,
        company_id: int,
    ) -> None:
        self.protocol_id = protocol_id
        self.company_id = company_id
        super().__init__(message)


class ReviewNotFoundError(LiteratureReviewError):
    """Raised when an SLR Review cannot be found.

    Typically occurs when a review_id does not exist within the
    requesting company's scope.

    Attributes:
        message: Human-readable error description.
        review_id: The review identifier that was not found.
        company_id: The company scope in which the lookup was performed.
    """

    def __init__(
        self,
        message: str,
        *,
        review_id: int,
        company_id: int,
    ) -> None:
        self.review_id = review_id
        self.company_id = company_id
        super().__init__(message)


class DecisionNotFoundError(LiteratureReviewError):
    """Raised when a Screening Decision cannot be found.

    Occurs when attempting to override or retrieve a decision that does
    not exist within the specified review and company scope.

    Attributes:
        message: Human-readable error description.
        decision_id: The decision identifier that was not found.
        review_id: The parent SLR Review identifier.
    """

    def __init__(
        self,
        message: str,
        *,
        decision_id: int,
        review_id: int,
    ) -> None:
        self.decision_id = decision_id
        self.review_id = review_id
        super().__init__(message)


class AlertNotFoundError(LiteratureReviewError):
    """Raised when a Contradiction Alert cannot be found.

    Occurs when attempting to update the status of an alert that does
    not exist within the requesting company's scope.

    Attributes:
        message: Human-readable error description.
        alert_id: The alert identifier that was not found.
        company_id: The company scope in which the lookup was performed.
    """

    def __init__(
        self,
        message: str,
        *,
        alert_id: int,
        company_id: int,
    ) -> None:
        self.alert_id = alert_id
        self.company_id = company_id
        super().__init__(message)


class FlagNotFoundError(LiteratureReviewError):
    """Raised when a Novelty Flag cannot be found.

    Occurs when attempting to update the status of a novelty flag that
    does not exist within the requesting company's scope.

    Attributes:
        message: Human-readable error description.
        flag_id: The flag identifier that was not found.
        company_id: The company scope in which the lookup was performed.
    """

    def __init__(
        self,
        message: str,
        *,
        flag_id: int,
        company_id: int,
    ) -> None:
        self.flag_id = flag_id
        self.company_id = company_id
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Validation / Configuration Errors
# ─────────────────────────────────────────────────────────────────────────────


class NoCriteriaDefinedError(LiteratureReviewError):
    """Raised when a Screening Protocol has no criteria defined.

    A valid protocol must have at least one of: a PICO field populated,
    at least one inclusion criterion, or at least one exclusion criterion.

    Attributes:
        message: Human-readable error description.
        protocol_id: The protocol that failed validation, if updating.
    """

    def __init__(
        self,
        message: str = "At least one screening criterion must be defined.",
        *,
        protocol_id: int | None = None,
    ) -> None:
        self.protocol_id = protocol_id
        super().__init__(message)


class ConfigurationRangeError(LiteratureReviewError):
    """Raised when a screening configuration value is outside its allowed range.

    For example, batch_size outside 1–100 or confidence thresholds
    outside 0.0–1.0.

    Attributes:
        message: Human-readable error description.
        field_name: The configuration field that is out of range.
        value: The invalid value that was provided.
        min_value: The minimum allowed value (inclusive).
        max_value: The maximum allowed value (inclusive).
    """

    def __init__(
        self,
        message: str,
        *,
        field_name: str,
        value: float | int,
        min_value: float | int,
        max_value: float | int,
    ) -> None:
        self.field_name = field_name
        self.value = value
        self.min_value = min_value
        self.max_value = max_value
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Operational Errors
# ─────────────────────────────────────────────────────────────────────────────


class ScreeningRunActiveError(LiteratureReviewError):
    """Raised when an operation is blocked by an active Screening Run.

    For example, attempting to start a new screening run while one is
    already in progress for the same SLR Review.

    Attributes:
        message: Human-readable error description.
        review_id: The SLR Review with an active run.
        active_run_id: The currently active Screening Run identifier.
    """

    def __init__(
        self,
        message: str,
        *,
        review_id: int,
        active_run_id: int,
    ) -> None:
        self.review_id = review_id
        self.active_run_id = active_run_id
        super().__init__(message)
