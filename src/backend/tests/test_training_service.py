"""Tests for the Training Service.

Includes property-based tests for:
- Training gate permits access if and only if valid training record exists
- Training task generation creates exactly one task per assigned-role user

**Validates: Requirements 9.1, 9.2, 9.3, 9.4, 10.1, 10.2, 10.3, 10.4**
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from alcoabase.services.training_service import TrainingService


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

# Strategy for generating valid SOP document UUIDs (YYYY-NNNNN format)
sop_uuid_strategy = st.builds(
    lambda year, seq: f"{year}-{seq:05d}",
    year=st.integers(min_value=2020, max_value=2030),
    seq=st.integers(min_value=1, max_value=99999),
)

# Strategy for generating version strings (major.minor format)
version_strategy = st.builds(
    lambda major: f"{major}.0",
    major=st.integers(min_value=1, max_value=20),
)

# Strategy for generating user IDs
user_id_strategy = st.integers(min_value=1, max_value=10000)

# Strategy for generating a list of unique user IDs (simulating assigned-role users)
user_ids_strategy = st.lists(
    st.integers(min_value=1, max_value=10000),
    min_size=1,
    max_size=50,
    unique=True,
)


# ---------------------------------------------------------------------------
# Helper: Create mock users
# ---------------------------------------------------------------------------


def make_mock_user(user_id: int) -> MagicMock:
    """Create a mock User object with the given ID.

    Args:
        user_id: The user's primary key.

    Returns:
        MagicMock configured as a User instance.
    """
    user = MagicMock()
    user.id = user_id
    user.is_active = True
    user.username = f"user_{user_id}"
    return user


# ---------------------------------------------------------------------------
# Task 10.7: Property-based tests - training gate enforcement
# ---------------------------------------------------------------------------


class TestTrainingGateProperty:
    """Property tests verifying training gate permits access if and only if
    a valid training record exists for the exact SOP version.

    **Validates: Requirements 10.1, 10.2, 10.3**
    """

    @given(
        user_id=user_id_strategy,
        sop_uuid=sop_uuid_strategy,
        sop_version=version_strategy,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_gate_blocks_without_valid_record(
        self, user_id: int, sop_uuid: str, sop_version: str
    ) -> None:
        """Training gate blocks access when no valid training record exists.

        For any user/SOP/version combination, if no valid training record
        exists, the gate raises HTTP 403.

        **Validates: Requirements 10.1, 10.2**
        """
        from fastapi import HTTPException

        service = TrainingService()
        session = AsyncMock()

        # Mock: no training record found
        record_result = MagicMock()
        record_result.scalar_one_or_none.return_value = None

        # Mock: SOP name lookup
        name_result = MagicMock()
        name_result.scalar_one_or_none.return_value = "Test SOP"

        session.execute.side_effect = [record_result, name_result]

        with pytest.raises(HTTPException) as exc_info:
            await service.check_training_gate(
                session, user_id, sop_uuid, sop_version
            )

        assert exc_info.value.status_code == 403
        assert "Action denied" in exc_info.value.detail
        assert sop_version in exc_info.value.detail

    @given(
        user_id=user_id_strategy,
        sop_uuid=sop_uuid_strategy,
        sop_version=version_strategy,
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_gate_permits_with_valid_record(
        self, user_id: int, sop_uuid: str, sop_version: str
    ) -> None:
        """Training gate permits access when a valid training record exists.

        For any user/SOP/version combination, if a valid training record
        exists, the gate does not raise an exception.

        **Validates: Requirements 10.3**
        """
        service = TrainingService()
        session = AsyncMock()

        # Mock: valid training record found
        mock_record = MagicMock()
        mock_record.user_id = user_id
        mock_record.sop_document_uuid = sop_uuid
        mock_record.sop_version = sop_version
        mock_record.is_valid = True

        record_result = MagicMock()
        record_result.scalar_one_or_none.return_value = mock_record

        session.execute.return_value = record_result

        # Should not raise
        await service.check_training_gate(
            session, user_id, sop_uuid, sop_version
        )

    @given(
        user_id=user_id_strategy,
        sop_uuid=sop_uuid_strategy,
        correct_version=st.integers(min_value=1, max_value=10),
        wrong_version=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_gate_blocks_wrong_version(
        self,
        user_id: int,
        sop_uuid: str,
        correct_version: int,
        wrong_version: int,
    ) -> None:
        """Training gate blocks access when record is for a different version.

        Even if a user has a valid training record for one version, they
        are blocked from accessing a different version.

        **Validates: Requirements 10.1**
        """
        from fastapi import HTTPException

        assume(correct_version != wrong_version)

        service = TrainingService()
        session = AsyncMock()

        # The user has training for correct_version but requests wrong_version
        # Mock: no record found for wrong_version
        record_result = MagicMock()
        record_result.scalar_one_or_none.return_value = None

        name_result = MagicMock()
        name_result.scalar_one_or_none.return_value = "Test SOP"

        session.execute.side_effect = [record_result, name_result]

        wrong_version_str = f"{wrong_version}.0"

        with pytest.raises(HTTPException) as exc_info:
            await service.check_training_gate(
                session, user_id, sop_uuid, wrong_version_str
            )

        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Task 10.8: Property-based tests - training task generation
# ---------------------------------------------------------------------------


class TestTrainingTaskGenerationProperty:
    """Property tests verifying training task generation creates exactly
    one task per assigned-role user with no duplicates or omissions.

    **Validates: Requirements 9.2, 9.3**
    """

    @given(user_ids=user_ids_strategy)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_exactly_one_task_per_user(
        self, user_ids: list[int]
    ) -> None:
        """Training task generation creates exactly one task per user.

        For any set of assigned-role users, the service generates exactly
        one training task per user — no duplicates, no omissions.

        **Validates: Requirements 9.2**
        """
        service = TrainingService()
        session = AsyncMock()

        # Mock users
        mock_users = [make_mock_user(uid) for uid in user_ids]

        # Call the internal method directly to test task generation logic
        tasks = await service._generate_training_tasks(
            session=session,
            sop_document_uuid="2024-00001",
            sop_name="Test SOP",
            version_str="2.0",
            users=mock_users,
        )

        # Verify exactly one task per user
        assert len(tasks) == len(user_ids)

        # Verify no duplicate user assignments
        assigned_user_ids = [t.assigned_user_id for t in tasks]
        assert len(set(assigned_user_ids)) == len(assigned_user_ids)

        # Verify all users got a task
        assert set(assigned_user_ids) == set(user_ids)

    @given(user_ids=user_ids_strategy)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_task_titles_contain_sop_info(
        self, user_ids: list[int]
    ) -> None:
        """All generated tasks have correct title format.

        Each task title follows the format:
        "Read and understand [SOP-Name] v[Version]"

        **Validates: Requirements 9.2**
        """
        service = TrainingService()
        session = AsyncMock()

        mock_users = [make_mock_user(uid) for uid in user_ids]
        sop_name = "Chemical Handling Procedure"
        version_str = "3.0"

        tasks = await service._generate_training_tasks(
            session=session,
            sop_document_uuid="2024-00005",
            sop_name=sop_name,
            version_str=version_str,
            users=mock_users,
        )

        for task in tasks:
            assert task.task_title == f"Read and understand {sop_name} v{version_str}"

    @given(user_ids=user_ids_strategy)
    @settings(max_examples=100)
    @pytest.mark.asyncio
    async def test_all_tasks_initially_incomplete(
        self, user_ids: list[int]
    ) -> None:
        """All generated tasks start as incomplete.

        **Validates: Requirements 9.2**
        """
        service = TrainingService()
        session = AsyncMock()

        mock_users = [make_mock_user(uid) for uid in user_ids]

        tasks = await service._generate_training_tasks(
            session=session,
            sop_document_uuid="2024-00010",
            sop_name="Lab Safety SOP",
            version_str="1.0",
            users=mock_users,
        )

        for task in tasks:
            assert task.is_completed is False
            assert task.completed_at is None

    @given(user_ids=user_ids_strategy)
    @settings(max_examples=50)
    @pytest.mark.asyncio
    async def test_tasks_reference_correct_sop_version(
        self, user_ids: list[int]
    ) -> None:
        """All generated tasks reference the correct SOP UUID and version.

        **Validates: Requirements 9.3**
        """
        service = TrainingService()
        session = AsyncMock()

        mock_users = [make_mock_user(uid) for uid in user_ids]
        sop_uuid = "2024-00042"
        version_str = "5.0"

        tasks = await service._generate_training_tasks(
            session=session,
            sop_document_uuid=sop_uuid,
            sop_name="Quality Control SOP",
            version_str=version_str,
            users=mock_users,
        )

        for task in tasks:
            assert task.sop_document_uuid == sop_uuid
            assert task.sop_version == version_str


# ---------------------------------------------------------------------------
# Unit tests for training service
# ---------------------------------------------------------------------------


class TestTrainingServiceUnit:
    """Unit tests for TrainingService methods.

    **Validates: Requirements 9.1, 9.4, 10.4**
    """

    @pytest.mark.asyncio
    async def test_assign_training_transitions_to_in_training(self) -> None:
        """assign_training transitions the SOP to InTraining status.

        **Validates: Requirements 9.1**
        """
        service = TrainingService()
        session = AsyncMock()

        # Mock document
        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_doc.document_uuid = "2024-00001"
        mock_doc.title = "Test SOP"
        mock_doc.current_status = "Approved"

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = mock_doc

        # Mock users query
        mock_user = make_mock_user(1)
        users_result = MagicMock()
        users_result.scalars.return_value.all.return_value = [mock_user]

        session.execute.side_effect = [doc_result, users_result]

        await service.assign_training(session, "2024-00001", 2)

        assert mock_doc.current_status == "InTraining"

    @pytest.mark.asyncio
    async def test_assign_training_raises_for_unknown_sop(self) -> None:
        """assign_training raises HTTP 400 for unknown SOP document.

        **Validates: Requirements 9.1**
        """
        from fastapi import HTTPException

        service = TrainingService()
        session = AsyncMock()

        doc_result = MagicMock()
        doc_result.scalar_one_or_none.return_value = None
        session.execute.return_value = doc_result

        with pytest.raises(HTTPException) as exc_info:
            await service.assign_training(session, "9999-99999", 1)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_complete_task_raises_for_wrong_user(self) -> None:
        """complete_training_task raises HTTP 400 if task not assigned to user.

        **Validates: Requirements 9.4**
        """
        from fastapi import HTTPException

        service = TrainingService()
        session = AsyncMock()

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.assigned_user_id = 10
        mock_task.is_completed = False

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task
        session.execute.return_value = task_result

        with pytest.raises(HTTPException) as exc_info:
            await service.complete_training_task(session, task_id=1, user_id=99)

        assert exc_info.value.status_code == 400
        assert "not assigned" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_complete_task_raises_for_already_completed(self) -> None:
        """complete_training_task raises HTTP 400 if task already completed.

        **Validates: Requirements 9.4**
        """
        from fastapi import HTTPException

        service = TrainingService()
        session = AsyncMock()

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.assigned_user_id = 10
        mock_task.is_completed = True

        task_result = MagicMock()
        task_result.scalar_one_or_none.return_value = mock_task
        session.execute.return_value = task_result

        with pytest.raises(HTTPException) as exc_info:
            await service.complete_training_task(session, task_id=1, user_id=10)

        assert exc_info.value.status_code == 400
        assert "already completed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalidate_previous_records(self) -> None:
        """invalidate_previous_training_records invalidates old records.

        **Validates: Requirements 10.4**
        """
        service = TrainingService()
        session = AsyncMock()

        # Mock old records
        old_record = MagicMock()
        old_record.is_valid = True
        old_record.sop_version = "1.0"
        old_record.invalidated_at = None

        records_result = MagicMock()
        records_result.scalars.return_value.all.return_value = [old_record]
        session.execute.return_value = records_result

        count = await service.invalidate_previous_training_records(
            session, "2024-00001", new_major_version=2
        )

        assert count == 1
        assert old_record.is_valid is False
        assert old_record.invalidated_at is not None

    @pytest.mark.asyncio
    async def test_check_training_gate_error_message_format(self) -> None:
        """check_training_gate returns properly formatted error message.

        **Validates: Requirements 10.2**
        """
        from fastapi import HTTPException

        service = TrainingService()
        session = AsyncMock()

        # No record found
        record_result = MagicMock()
        record_result.scalar_one_or_none.return_value = None

        # SOP name lookup
        name_result = MagicMock()
        name_result.scalar_one_or_none.return_value = "Chemical Handling"

        session.execute.side_effect = [record_result, name_result]

        with pytest.raises(HTTPException) as exc_info:
            await service.check_training_gate(
                session, user_id=1, sop_document_uuid="2024-00001", sop_version="3.0"
            )

        expected_msg = (
            "Action denied: Valid training record for "
            "Chemical Handling Version 3.0 is missing."
        )
        assert exc_info.value.detail == expected_msg

    @pytest.mark.asyncio
    async def test_get_training_status(self) -> None:
        """get_training_status returns correct summary.

        **Validates: Requirements 9.4**
        """
        service = TrainingService()
        session = AsyncMock()

        # Mock tasks: 2 complete, 1 incomplete
        task1 = MagicMock()
        task1.is_completed = True
        task2 = MagicMock()
        task2.is_completed = True
        task3 = MagicMock()
        task3.is_completed = False

        tasks_result = MagicMock()
        tasks_result.scalars.return_value.all.return_value = [task1, task2, task3]
        session.execute.return_value = tasks_result

        status = await service.get_training_status(
            session, "2024-00001", "2.0"
        )

        assert status["total_tasks"] == 3
        assert status["completed_tasks"] == 2
        assert status["is_complete"] is False
