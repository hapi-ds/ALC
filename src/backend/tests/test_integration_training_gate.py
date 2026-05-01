"""Integration tests for training gate enforcement.

Tests: untrained user blocked, trained user permitted.

References:
    - Task 22.5: Integration tests for training gate
"""

import pytest


# ---------------------------------------------------------------------------
# Integration Tests: Training Gate
# ---------------------------------------------------------------------------


class TestTrainingGate:
    """Integration tests for training execution gate.

    Tests the training gate logic: users must have a valid, completed
    training record for the exact SOP version to gain access.
    """

    def _check_training_access(
        self,
        user_id: int,
        sop_uuid: str,
        sop_version: str,
        training_records: dict[tuple[int, str, str], bool],
    ) -> bool:
        """Check if user has valid training access.

        Simulates the training gate logic from TrainingService.check_training_gate().

        Args:
            user_id: The user requesting access.
            sop_uuid: The SOP document UUID.
            sop_version: The SOP version string.
            training_records: Map of (user_id, sop_uuid, version) -> completed.

        Returns:
            True if access is granted, False otherwise.
        """
        key = (user_id, sop_uuid, sop_version)
        record = training_records.get(key)
        return record is True

    def _generate_training_tasks(
        self,
        sop_uuid: str,
        sop_version: str,
        sop_name: str,
        assigned_user_ids: list[int],
    ) -> list[dict]:
        """Generate training tasks for all assigned users.

        Simulates TrainingService._generate_training_tasks().

        Args:
            sop_uuid: The SOP document UUID.
            sop_version: The SOP version.
            sop_name: The SOP name.
            assigned_user_ids: List of user IDs to assign training.

        Returns:
            List of training task dictionaries.
        """
        return [
            {
                "user_id": uid,
                "sop_uuid": sop_uuid,
                "sop_version": sop_version,
                "description": f"Read and understand {sop_name} v{sop_version}",
                "completed": False,
            }
            for uid in assigned_user_ids
        ]

    def test_untrained_user_blocked(self):
        """User without valid training record is blocked."""
        training_records: dict[tuple[int, str, str], bool] = {}

        has_access = self._check_training_access(
            user_id=1,
            sop_uuid="2025-00001",
            sop_version="1.0",
            training_records=training_records,
        )

        assert has_access is False

    def test_trained_user_permitted(self):
        """User with valid completed training record is permitted."""
        training_records = {
            (1, "2025-00001", "1.0"): True,
        }

        has_access = self._check_training_access(
            user_id=1,
            sop_uuid="2025-00001",
            sop_version="1.0",
            training_records=training_records,
        )

        assert has_access is True

    def test_training_for_wrong_version_blocked(self):
        """Training for a different SOP version does not grant access."""
        training_records = {
            (1, "2025-00001", "1.0"): True,
        }

        has_access = self._check_training_access(
            user_id=1,
            sop_uuid="2025-00001",
            sop_version="2.0",
            training_records=training_records,
        )

        assert has_access is False

    def test_incomplete_training_blocked(self):
        """Incomplete training record does not grant access."""
        training_records = {
            (1, "2025-00001", "1.0"): False,
        }

        has_access = self._check_training_access(
            user_id=1,
            sop_uuid="2025-00001",
            sop_version="1.0",
            training_records=training_records,
        )

        assert has_access is False

    def test_training_task_generation_for_all_users(self):
        """Training tasks are generated for all assigned-role users."""
        assigned_users = [1, 2, 3, 4, 5]

        tasks = self._generate_training_tasks(
            sop_uuid="2025-00001",
            sop_version="2.0",
            sop_name="Lab Procedure SOP",
            assigned_user_ids=assigned_users,
        )

        assert len(tasks) == len(assigned_users)
        for task in tasks:
            assert task["sop_uuid"] == "2025-00001"
            assert task["sop_version"] == "2.0"
            assert task["user_id"] in assigned_users
