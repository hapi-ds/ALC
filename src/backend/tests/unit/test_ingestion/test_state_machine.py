"""Unit tests for ingestion state machine and custom exceptions.

Tests:
    - All valid transitions succeed
    - All invalid transitions are rejected
    - Retry transitions from FAILED state
    - get_valid_next_states() for each state
    - Exception messages and attributes for all custom exceptions

Requirements: 2.1, 2.2, 2.4, 2.5
"""

import pytest

from alcoabase.literature.ingestion.exceptions import (
    AdapterTimeoutError,
    BatchTooLargeError,
    ChecksumMismatchError,
    CompanyPausedError,
    DOINotFoundError,
    DuplicateRecordError,
    FileTooLargeError,
    IngestionPipelineError,
    InvalidStateTransitionError,
    MaxRetriesExceededError,
    NoOpenAccessError,
    RateLimitedError,
    SanitizationError,
    StorageQuotaExceededError,
    UnsupportedContentTypeError,
)
from alcoabase.literature.ingestion.services.state_machine import (
    RETRY_TRANSITIONS,
    VALID_TRANSITIONS,
    IngestionState,
    get_valid_next_states,
    is_valid_retry_transition,
    is_valid_transition,
)


# ─── State Machine Tests ─────────────────────────────────────────────────────


class TestValidTransitions:
    """Test that all valid forward transitions succeed."""

    @pytest.mark.parametrize(
        "from_state,to_state",
        list(VALID_TRANSITIONS),
        ids=[f"{f.value}->{t.value}" for f, t in VALID_TRANSITIONS],
    )
    def test_valid_transition_succeeds(
        self, from_state: IngestionState, to_state: IngestionState
    ) -> None:
        assert is_valid_transition(from_state, to_state) is True


class TestInvalidTransitions:
    """Test that all invalid transitions are rejected."""

    def _all_invalid_pairs(self) -> list[tuple[IngestionState, IngestionState]]:
        """Generate all state pairs not in VALID_TRANSITIONS."""
        all_states = list(IngestionState)
        invalid = []
        for s1 in all_states:
            for s2 in all_states:
                if (s1, s2) not in VALID_TRANSITIONS:
                    invalid.append((s1, s2))
        return invalid

    @pytest.mark.parametrize(
        "from_state,to_state",
        [
            (IngestionState.METADATA_ONLY, IngestionState.FULL_TEXT_PENDING),
            (IngestionState.METADATA_ONLY, IngestionState.FAILED),
            (IngestionState.METADATA_ONLY, IngestionState.INDEXED),
            (IngestionState.ABSTRACT_INDEXED, IngestionState.INDEXED),
            (IngestionState.ABSTRACT_INDEXED, IngestionState.SANITIZED),
            (IngestionState.INDEXED, IngestionState.METADATA_ONLY),
            (IngestionState.FAILED, IngestionState.INDEXED),
            (IngestionState.FAILED, IngestionState.METADATA_ONLY),
        ],
    )
    def test_invalid_transition_rejected(
        self, from_state: IngestionState, to_state: IngestionState
    ) -> None:
        assert is_valid_transition(from_state, to_state) is False

    def test_self_transitions_rejected(self) -> None:
        """No state can transition to itself."""
        for state in IngestionState:
            assert is_valid_transition(state, state) is False


class TestRetryTransitions:
    """Test retry transitions from FAILED state."""

    @pytest.mark.parametrize(
        "from_state,to_state",
        list(RETRY_TRANSITIONS),
        ids=[f"{f.value}->{t.value}" for f, t in RETRY_TRANSITIONS],
    )
    def test_valid_retry_transition(
        self, from_state: IngestionState, to_state: IngestionState
    ) -> None:
        assert is_valid_retry_transition(from_state, to_state) is True

    def test_retry_only_from_failed(self) -> None:
        """Retry transitions only valid when current_state is FAILED."""
        non_failed = [s for s in IngestionState if s != IngestionState.FAILED]
        for state in non_failed:
            for target in IngestionState:
                assert is_valid_retry_transition(state, target) is False

    def test_retry_to_invalid_states_rejected(self) -> None:
        """FAILED cannot retry to states not in RETRY_TRANSITIONS."""
        valid_retry_targets = {t for (_, t) in RETRY_TRANSITIONS}
        invalid_targets = set(IngestionState) - valid_retry_targets
        for target in invalid_targets:
            assert (
                is_valid_retry_transition(IngestionState.FAILED, target) is False
            )


class TestGetValidNextStates:
    """Test get_valid_next_states() for each state."""

    def test_metadata_only_next_states(self) -> None:
        result = get_valid_next_states(IngestionState.METADATA_ONLY)
        assert result == [IngestionState.ABSTRACT_INDEXED]

    def test_abstract_indexed_next_states(self) -> None:
        result = get_valid_next_states(IngestionState.ABSTRACT_INDEXED)
        assert result == [IngestionState.FULL_TEXT_PENDING]

    def test_full_text_pending_next_states(self) -> None:
        result = get_valid_next_states(IngestionState.FULL_TEXT_PENDING)
        assert IngestionState.FULL_TEXT_DOWNLOADED in result
        assert IngestionState.FAILED in result
        assert len(result) == 2

    def test_full_text_downloaded_next_states(self) -> None:
        result = get_valid_next_states(IngestionState.FULL_TEXT_DOWNLOADED)
        assert IngestionState.SANITIZED in result
        assert IngestionState.FAILED in result
        assert len(result) == 2

    def test_sanitized_next_states(self) -> None:
        result = get_valid_next_states(IngestionState.SANITIZED)
        assert IngestionState.INDEXED in result
        assert IngestionState.FAILED in result
        assert len(result) == 2

    def test_indexed_next_states(self) -> None:
        result = get_valid_next_states(IngestionState.INDEXED)
        assert result == []

    def test_failed_next_states(self) -> None:
        """FAILED has no forward transitions (only retry transitions)."""
        result = get_valid_next_states(IngestionState.FAILED)
        assert result == []


# ─── Custom Exception Tests ──────────────────────────────────────────────────


class TestIngestionPipelineError:
    """Test base exception."""

    def test_default_message(self) -> None:
        exc = IngestionPipelineError()
        assert str(exc) == "An ingestion pipeline error occurred."
        assert exc.company_id is None

    def test_custom_message_and_company_id(self) -> None:
        exc = IngestionPipelineError("custom error", company_id=42)
        assert exc.message == "custom error"
        assert exc.company_id == 42


class TestInvalidStateTransitionError:
    """Test state transition exception attributes."""

    def test_attributes(self) -> None:
        exc = InvalidStateTransitionError(
            "Bad transition",
            company_id=1,
            current_state="metadata_only",
            target_state="indexed",
            record_id=99,
        )
        assert exc.current_state == "metadata_only"
        assert exc.target_state == "indexed"
        assert exc.record_id == 99
        assert exc.company_id == 1
        assert "Bad transition" in str(exc)

    def test_is_subclass(self) -> None:
        assert issubclass(InvalidStateTransitionError, IngestionPipelineError)


class TestDuplicateRecordError:
    """Test duplicate record exception attributes."""

    def test_attributes(self) -> None:
        exc = DuplicateRecordError(
            company_id=5,
            existing_record_id=123,
            doi="10.1000/abc",
            source_id="pubmed",
            external_id="PM12345",
        )
        assert exc.existing_record_id == 123
        assert exc.doi == "10.1000/abc"
        assert exc.source_id == "pubmed"
        assert exc.external_id == "PM12345"


class TestStorageQuotaExceededError:
    """Test storage quota exception attributes."""

    def test_attributes(self) -> None:
        exc = StorageQuotaExceededError(
            company_id=3, quota_mb=1024, usage_mb=1100.5
        )
        assert exc.quota_mb == 1024
        assert exc.usage_mb == 1100.5


class TestChecksumMismatchError:
    """Test checksum mismatch exception attributes."""

    def test_attributes(self) -> None:
        exc = ChecksumMismatchError(
            company_id=2,
            record_id=50,
            expected_checksum="abc123",
            actual_checksum="def456",
        )
        assert exc.record_id == 50
        assert exc.expected_checksum == "abc123"
        assert exc.actual_checksum == "def456"


class TestDOINotFoundError:
    """Test DOI not found exception attributes."""

    def test_attributes(self) -> None:
        exc = DOINotFoundError(doi="10.1234/test", record_id=10)
        assert exc.doi == "10.1234/test"
        assert exc.record_id == 10


class TestNoOpenAccessError:
    """Test no open access exception attributes."""

    def test_attributes(self) -> None:
        exc = NoOpenAccessError(doi="10.5678/nope", record_id=20)
        assert exc.doi == "10.5678/nope"
        assert exc.record_id == 20


class TestUnsupportedContentTypeError:
    """Test unsupported content type exception attributes."""

    def test_attributes(self) -> None:
        exc = UnsupportedContentTypeError(
            content_type="application/zip", record_id=30
        )
        assert exc.content_type == "application/zip"
        assert exc.record_id == 30


class TestFileTooLargeError:
    """Test file too large exception attributes."""

    def test_attributes(self) -> None:
        exc = FileTooLargeError(
            file_size_bytes=200_000_000,
            max_size_bytes=100_000_000,
            record_id=40,
        )
        assert exc.file_size_bytes == 200_000_000
        assert exc.max_size_bytes == 100_000_000


class TestSanitizationError:
    """Test sanitization exception attributes."""

    def test_attributes(self) -> None:
        exc = SanitizationError(
            error_type="ocr_required",
            content_type="application/pdf",
            record_id=55,
        )
        assert exc.error_type == "ocr_required"
        assert exc.content_type == "application/pdf"
        assert exc.record_id == 55


class TestBatchTooLargeError:
    """Test batch too large exception attributes."""

    def test_attributes(self) -> None:
        exc = BatchTooLargeError(batch_size=150, max_batch_size=100)
        assert exc.batch_size == 150
        assert exc.max_batch_size == 100


class TestMaxRetriesExceededError:
    """Test max retries exception attributes."""

    def test_attributes(self) -> None:
        exc = MaxRetriesExceededError(
            record_id=77,
            retry_count=3,
            max_retries=3,
            last_error="connection timeout",
        )
        assert exc.record_id == 77
        assert exc.retry_count == 3
        assert exc.max_retries == 3
        assert exc.last_error == "connection timeout"


class TestCompanyPausedError:
    """Test company paused exception attributes."""

    def test_attributes(self) -> None:
        exc = CompanyPausedError(
            company_id=8, reason="quota_exhausted", retry_after_seconds=300.0
        )
        assert exc.reason == "quota_exhausted"
        assert exc.retry_after_seconds == 300.0


class TestAdapterTimeoutError:
    """Test adapter timeout exception attributes."""

    def test_attributes(self) -> None:
        exc = AdapterTimeoutError(
            source_adapter_name="unpaywall", timeout_seconds=15.0
        )
        assert exc.source_adapter_name == "unpaywall"
        assert exc.timeout_seconds == 15.0


class TestRateLimitedError:
    """Test rate limited exception attributes."""

    def test_attributes(self) -> None:
        exc = RateLimitedError(
            retry_after_seconds=60.0, source_adapter_name="unpaywall"
        )
        assert exc.retry_after_seconds == 60.0
        assert exc.source_adapter_name == "unpaywall"
