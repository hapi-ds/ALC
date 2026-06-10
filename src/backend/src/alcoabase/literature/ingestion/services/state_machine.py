"""Ingestion lifecycle state machine with enforced transitions.

The state machine is a pure function module — no side effects, no database access.
Transition validation is called by the service layer before persisting state changes.

References:
    - Requirement 2.1: Valid state transitions
    - Requirement 2.2: Invalid transition rejection
    - Requirement 2.4: Retry from FAILED state
    - Requirement 2.5: Maximum retry limits with exponential backoff
"""

from enum import StrEnum


class IngestionState(StrEnum):
    """Lifecycle states for an Ingestion_Record.

    Each state represents a phase in the dual-stage ingestion pipeline:
        - METADATA_ONLY: Initial state after record creation (no abstract).
        - ABSTRACT_INDEXED: Metadata and abstract have been stored and indexed.
        - FULL_TEXT_PENDING: Full-text retrieval task has been dispatched.
        - FULL_TEXT_DOWNLOADED: Full-text file downloaded and stored in MinIO.
        - SANITIZED: Content sanitized into StructuredContent format.
        - INDEXED: Fully processed and available for search/extraction.
        - FAILED: Processing failed at some stage; eligible for retry.
    """

    METADATA_ONLY = "metadata_only"
    ABSTRACT_INDEXED = "abstract_indexed"
    FULL_TEXT_PENDING = "full_text_pending"
    FULL_TEXT_DOWNLOADED = "full_text_downloaded"
    SANITIZED = "sanitized"
    INDEXED = "indexed"
    FAILED = "failed"


# Valid forward transitions as a frozenset of (from_state, to_state) tuples.
# Represents all allowed state moves in the ingestion pipeline lifecycle.
VALID_TRANSITIONS: frozenset[tuple[IngestionState, IngestionState]] = frozenset({
    (IngestionState.METADATA_ONLY, IngestionState.ABSTRACT_INDEXED),
    (IngestionState.ABSTRACT_INDEXED, IngestionState.FULL_TEXT_PENDING),
    (IngestionState.FULL_TEXT_PENDING, IngestionState.FULL_TEXT_DOWNLOADED),
    (IngestionState.FULL_TEXT_PENDING, IngestionState.FAILED),
    (IngestionState.FULL_TEXT_DOWNLOADED, IngestionState.SANITIZED),
    (IngestionState.FULL_TEXT_DOWNLOADED, IngestionState.FAILED),
    (IngestionState.SANITIZED, IngestionState.INDEXED),
    (IngestionState.SANITIZED, IngestionState.FAILED),
})

# Retry transitions: allowed moves from FAILED back to a retryable state.
# These represent the states from which failure could have occurred.
RETRY_TRANSITIONS: frozenset[tuple[IngestionState, IngestionState]] = frozenset({
    (IngestionState.FAILED, IngestionState.FULL_TEXT_PENDING),
    (IngestionState.FAILED, IngestionState.FULL_TEXT_DOWNLOADED),
    (IngestionState.FAILED, IngestionState.SANITIZED),
})


def is_valid_transition(
    current_state: IngestionState,
    target_state: IngestionState,
) -> bool:
    """Check if a forward state transition is valid.

    Args:
        current_state: The current state of the Ingestion_Record.
        target_state: The desired next state.

    Returns:
        True if the transition is allowed by VALID_TRANSITIONS, False otherwise.
    """
    return (current_state, target_state) in VALID_TRANSITIONS


def is_valid_retry_transition(
    current_state: IngestionState,
    target_state: IngestionState,
) -> bool:
    """Check if a retry transition from FAILED is valid.

    Args:
        current_state: Must be FAILED for a retry transition to be valid.
        target_state: The state to retry from (must be a retryable state).

    Returns:
        True if the retry transition is allowed by RETRY_TRANSITIONS,
        False otherwise.
    """
    return (current_state, target_state) in RETRY_TRANSITIONS


def get_valid_next_states(current_state: IngestionState) -> list[IngestionState]:
    """Get all valid target states reachable from the current state.

    This includes only forward transitions from VALID_TRANSITIONS.
    Retry transitions from FAILED are not included; use
    ``is_valid_retry_transition`` for that purpose.

    Args:
        current_state: The current state of the Ingestion_Record.

    Returns:
        Sorted list of valid target states reachable from current_state.
    """
    return sorted(
        target
        for (source, target) in VALID_TRANSITIONS
        if source == current_state
    )
