"""Property-based tests for UUIDService.

Tests Document-UUID and Field-UUID generation for format compliance
and uniqueness guarantees using Hypothesis.

**Validates: Requirements 1.1, 3.2**
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from alcoabase.services.uuid_service import UUIDService


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

DOCUMENT_UUID_PATTERN = re.compile(r"^\d{4}-\d{5}$")
FIELD_UUID_PATTERN = re.compile(r"^FLD-[A-F0-9]{8}$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(seq_value: int) -> AsyncMock:
    """Create a mock AsyncSession that returns a given sequence value.

    Args:
        seq_value: The integer value to return from nextval().

    Returns:
        An AsyncMock configured to simulate PostgreSQL sequence calls.
    """
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one.return_value = seq_value
    session.execute.return_value = result_mock
    return session


# ---------------------------------------------------------------------------
# Task 3.4: Document-UUID property-based tests
# ---------------------------------------------------------------------------


class TestDocumentUUIDFormatCompliance:
    """Property tests for Document-UUID format compliance.

    **Validates: Requirements 1.1**
    """

    @given(seq_value=st.integers(min_value=1, max_value=99999))
    @settings(max_examples=1000)
    @pytest.mark.asyncio
    async def test_document_uuid_matches_pattern(self, seq_value: int) -> None:
        """All generated Document-UUIDs match the YYYY-NNNNN pattern.

        **Validates: Requirements 1.1**
        """
        service = UUIDService()
        session = _make_mock_session(seq_value)

        uuid = await service.generate_document_uuid(session)

        assert DOCUMENT_UUID_PATTERN.match(uuid), (
            f"Document-UUID '{uuid}' does not match YYYY-NNNNN pattern"
        )

    @given(seq_value=st.integers(min_value=1, max_value=99999))
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_document_uuid_year_is_four_digits(self, seq_value: int) -> None:
        """The year portion of Document-UUID is exactly 4 digits.

        **Validates: Requirements 1.1**
        """
        service = UUIDService()
        session = _make_mock_session(seq_value)

        uuid = await service.generate_document_uuid(session)
        year_part = uuid.split("-")[0]

        assert len(year_part) == 4
        assert year_part.isdigit()

    @given(seq_value=st.integers(min_value=1, max_value=99999))
    @settings(max_examples=200)
    @pytest.mark.asyncio
    async def test_document_uuid_sequence_is_five_digits(self, seq_value: int) -> None:
        """The sequence portion of Document-UUID is exactly 5 zero-padded digits.

        **Validates: Requirements 1.1**
        """
        service = UUIDService()
        session = _make_mock_session(seq_value)

        uuid = await service.generate_document_uuid(session)
        seq_part = uuid.split("-")[1]

        assert len(seq_part) == 5
        assert seq_part.isdigit()


class TestDocumentUUIDUniqueness:
    """Property tests for Document-UUID uniqueness across generations.

    **Validates: Requirements 1.1**
    """

    @pytest.mark.asyncio
    async def test_document_uuid_uniqueness_across_1000_generations(self) -> None:
        """1000 sequential Document-UUIDs are all unique.

        **Validates: Requirements 1.1**
        """
        service = UUIDService()
        uuids: list[str] = []

        for seq_value in range(1, 1001):
            session = _make_mock_session(seq_value)
            uuid = await service.generate_document_uuid(session)
            uuids.append(uuid)

        assert len(uuids) == 1000
        assert len(set(uuids)) == 1000, "Duplicate Document-UUIDs detected"


# ---------------------------------------------------------------------------
# Task 3.5: Field-UUID property-based tests
# ---------------------------------------------------------------------------


class TestFieldUUIDFormatCompliance:
    """Property tests for Field-UUID format compliance.

    **Validates: Requirements 3.2**
    """

    @given(st.integers(min_value=1, max_value=1000))
    @settings(max_examples=1000)
    def test_field_uuid_matches_pattern(self, _: int) -> None:
        """All generated Field-UUIDs match the FLD-XXXXXXXX pattern.

        **Validates: Requirements 3.2**
        """
        service = UUIDService()
        uuid = service.generate_field_uuid()

        assert FIELD_UUID_PATTERN.match(uuid), (
            f"Field-UUID '{uuid}' does not match FLD-XXXXXXXX pattern"
        )

    @given(st.integers(min_value=1, max_value=500))
    @settings(max_examples=500)
    def test_field_uuid_prefix_is_fld(self, _: int) -> None:
        """All generated Field-UUIDs start with 'FLD-' prefix.

        **Validates: Requirements 3.2**
        """
        service = UUIDService()
        uuid = service.generate_field_uuid()

        assert uuid.startswith("FLD-")

    @given(st.integers(min_value=1, max_value=500))
    @settings(max_examples=500)
    def test_field_uuid_hex_portion_is_uppercase(self, _: int) -> None:
        """The hex portion of Field-UUID contains only uppercase A-F and digits.

        **Validates: Requirements 3.2**
        """
        service = UUIDService()
        uuid = service.generate_field_uuid()
        hex_part = uuid[4:]  # Strip "FLD-" prefix

        assert len(hex_part) == 8
        assert all(c in "0123456789ABCDEF" for c in hex_part)


class TestFieldUUIDUniqueness:
    """Property tests for Field-UUID uniqueness within generated batches.

    **Validates: Requirements 3.2**
    """

    @given(batch_size=st.integers(min_value=2, max_value=200))
    @settings(max_examples=100)
    def test_field_uuid_uniqueness_within_batch(self, batch_size: int) -> None:
        """All Field-UUIDs within a batch of various sizes are unique.

        **Validates: Requirements 3.2**
        """
        service = UUIDService()
        uuids = [service.generate_field_uuid() for _ in range(batch_size)]

        assert len(set(uuids)) == len(uuids), (
            f"Duplicate Field-UUIDs detected in batch of {batch_size}"
        )
