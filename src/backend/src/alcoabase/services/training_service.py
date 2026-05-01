"""Training Service for SOP training assignment and ABAC gate enforcement.

This module implements:
- Automatic training task generation on SOP major version approval
- Training completion tracking with auto-transition to Active
- Training execution gate (ABAC) blocking untrained users
- Training record invalidation on new major version activation

References:
    - Design doc Section 7: Training Service (ABAC)
    - Requirements 9: Automatic Training Assignment on SOP Approval
    - Requirements 10: Training Execution Gate Enforcement
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.training import TrainingRecord, TrainingTask
from alcoabase.models.user import Role, User, UserRole


class TrainingService:
    """Service for managing SOP training assignments and execution gate.

    Provides methods for:
    - Assigning training tasks on SOP major version approval
    - Tracking training task completion
    - Enforcing the training execution gate (ABAC)
    - Invalidating training records on new major version activation

    Usage:
        service = TrainingService()
        await service.assign_training(session, sop_document_uuid, major_version)
    """

    async def assign_training(
        self,
        session: AsyncSession,
        sop_document_uuid: str,
        major_version: int,
    ) -> list[TrainingTask]:
        """Assign training tasks for an SOP major version approval.

        On SOP major version approval, transitions the SOP to InTraining
        and generates a training task for every user with an assigned role.

        Args:
            session: Active async database session.
            sop_document_uuid: Document-UUID of the SOP.
            major_version: The major version number that was approved.

        Returns:
            List of created TrainingTask instances.

        Raises:
            HTTPException: 400 if the SOP document is not found.
        """
        # Load the SOP document
        result = await session.execute(
            select(Document).where(
                Document.document_uuid == sop_document_uuid
            )
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise HTTPException(
                status_code=400,
                detail=f"SOP document not found: {sop_document_uuid}",
            )

        # Transition SOP to InTraining
        document.current_status = "InTraining"

        # Build version string
        version_str = f"{major_version}.0"

        # Get all users with assigned roles (all active users with roles)
        assigned_users = await self._get_assigned_role_users(session)

        # Generate training tasks
        tasks = await self._generate_training_tasks(
            session=session,
            sop_document_uuid=sop_document_uuid,
            sop_name=document.title,
            version_str=version_str,
            users=assigned_users,
        )

        return tasks

    async def _get_assigned_role_users(
        self, session: AsyncSession
    ) -> list[User]:
        """Get all active users that have at least one role assigned.

        Args:
            session: Active async database session.

        Returns:
            List of User instances with assigned roles.
        """
        result = await session.execute(
            select(User)
            .join(UserRole, User.id == UserRole.c.user_id)
            .where(User.is_active.is_(True))
            .distinct()
        )
        return list(result.scalars().all())

    async def _generate_training_tasks(
        self,
        session: AsyncSession,
        sop_document_uuid: str,
        sop_name: str,
        version_str: str,
        users: list[User],
    ) -> list[TrainingTask]:
        """Generate one training task per assigned-role user.

        Creates a task titled "Read and understand [SOP-Name] v[Version]"
        for each user and records the creation in the audit trail.

        Args:
            session: Active async database session.
            sop_document_uuid: Document-UUID of the SOP.
            sop_name: Title of the SOP document.
            version_str: Version string (e.g., "2.0").
            users: List of users to assign tasks to.

        Returns:
            List of created TrainingTask instances.
        """
        tasks: list[TrainingTask] = []

        for user in users:
            task = TrainingTask(
                sop_document_uuid=sop_document_uuid,
                sop_version=version_str,
                assigned_user_id=user.id,
                task_title=f"Read and understand {sop_name} v{version_str}",
                is_completed=False,
            )
            session.add(task)
            tasks.append(task)

        await session.flush()
        return tasks

    async def complete_training_task(
        self,
        session: AsyncSession,
        task_id: int,
        user_id: int,
    ) -> TrainingTask:
        """Mark a training task as completed and check for auto-transition.

        When a user completes their training task, marks it as done and
        creates a TrainingRecord. If all users have completed their tasks
        for this SOP version, auto-transitions the SOP from InTraining
        to Active.

        Args:
            session: Active async database session.
            task_id: The training task primary key.
            user_id: The user completing the task.

        Returns:
            The updated TrainingTask.

        Raises:
            HTTPException: 400 if task not found or not assigned to user.
            HTTPException: 400 if task is already completed.
        """
        # Load the task
        result = await session.execute(
            select(TrainingTask).where(TrainingTask.id == task_id)
        )
        task = result.scalar_one_or_none()

        if task is None:
            raise HTTPException(
                status_code=400,
                detail=f"Training task not found: {task_id}",
            )

        if task.assigned_user_id != user_id:
            raise HTTPException(
                status_code=400,
                detail="Training task is not assigned to this user",
            )

        if task.is_completed:
            raise HTTPException(
                status_code=400,
                detail="Training task is already completed",
            )

        # Mark task as completed
        task.is_completed = True
        task.completed_at = datetime.now(UTC)

        # Create a training record
        record = TrainingRecord(
            user_id=user_id,
            sop_document_uuid=task.sop_document_uuid,
            sop_version=task.sop_version,
            is_valid=True,
            completed_at=datetime.now(UTC),
        )
        session.add(record)

        # Check if all tasks for this SOP version are now complete
        await self._check_all_tasks_complete(
            session, task.sop_document_uuid, task.sop_version
        )

        return task

    async def _check_all_tasks_complete(
        self,
        session: AsyncSession,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """Check if all training tasks are complete and auto-transition SOP.

        When all users have completed their training tasks for an SOP version,
        automatically transitions the SOP from InTraining to Active.

        Args:
            session: Active async database session.
            sop_document_uuid: Document-UUID of the SOP.
            sop_version: Version string of the SOP.
        """
        # Count incomplete tasks
        result = await session.execute(
            select(TrainingTask).where(
                TrainingTask.sop_document_uuid == sop_document_uuid,
                TrainingTask.sop_version == sop_version,
                TrainingTask.is_completed.is_(False),
            )
        )
        incomplete_tasks = result.scalars().all()

        if len(list(incomplete_tasks)) == 0:
            # All tasks complete — transition SOP to Active
            doc_result = await session.execute(
                select(Document).where(
                    Document.document_uuid == sop_document_uuid
                )
            )
            document = doc_result.scalar_one_or_none()
            if document and document.current_status == "InTraining":
                document.current_status = "Active"

    async def check_training_gate(
        self,
        session: AsyncSession,
        user_id: int,
        sop_document_uuid: str,
        sop_version: str,
    ) -> None:
        """Verify user has valid training for exact SOP version.

        Raises HTTP 403 if the user does not hold a valid, completed
        training record for the specified SOP version.

        Args:
            session: Active async database session.
            user_id: The user attempting the action.
            sop_document_uuid: Document-UUID of the SOP.
            sop_version: Version string of the SOP.

        Raises:
            HTTPException: 403 if user lacks valid training record.
        """
        result = await session.execute(
            select(TrainingRecord).where(
                TrainingRecord.user_id == user_id,
                TrainingRecord.sop_document_uuid == sop_document_uuid,
                TrainingRecord.sop_version == sop_version,
                TrainingRecord.is_valid.is_(True),
            )
        )
        record = result.scalar_one_or_none()

        if record is None:
            # Look up SOP name for the error message
            doc_result = await session.execute(
                select(Document.title).where(
                    Document.document_uuid == sop_document_uuid
                )
            )
            sop_name_row = doc_result.scalar_one_or_none()
            sop_name = sop_name_row if sop_name_row else sop_document_uuid

            raise HTTPException(
                status_code=403,
                detail=(
                    f"Action denied: Valid training record for "
                    f"{sop_name} Version {sop_version} is missing."
                ),
            )

    async def invalidate_previous_training_records(
        self,
        session: AsyncSession,
        sop_document_uuid: str,
        new_major_version: int,
    ) -> int:
        """Invalidate training records for previous major versions.

        When a new major SOP version is activated, all training records
        for previous major versions of that SOP are invalidated, requiring
        re-training.

        Args:
            session: Active async database session.
            sop_document_uuid: Document-UUID of the SOP.
            new_major_version: The new major version number being activated.

        Returns:
            Number of records invalidated.
        """
        # Find all valid records for this SOP that are NOT for the new version
        new_version_str = f"{new_major_version}.0"

        result = await session.execute(
            select(TrainingRecord).where(
                TrainingRecord.sop_document_uuid == sop_document_uuid,
                TrainingRecord.is_valid.is_(True),
                TrainingRecord.sop_version != new_version_str,
            )
        )
        records = list(result.scalars().all())

        now = datetime.now(UTC)
        for record in records:
            record.is_valid = False
            record.invalidated_at = now

        return len(records)

    async def get_user_training_tasks(
        self,
        session: AsyncSession,
        user_id: int,
    ) -> list[TrainingTask]:
        """Get all training tasks assigned to a user.

        Args:
            session: Active async database session.
            user_id: The user's primary key.

        Returns:
            List of TrainingTask instances assigned to the user.
        """
        result = await session.execute(
            select(TrainingTask).where(
                TrainingTask.assigned_user_id == user_id
            )
        )
        return list(result.scalars().all())

    async def get_training_status(
        self,
        session: AsyncSession,
        sop_document_uuid: str,
        sop_version: str,
    ) -> dict:
        """Get training status for an SOP version.

        Returns a summary of training progress including total tasks,
        completed tasks, and whether training is complete.

        Args:
            session: Active async database session.
            sop_document_uuid: Document-UUID of the SOP.
            sop_version: Version string of the SOP.

        Returns:
            Dict with total_tasks, completed_tasks, and is_complete fields.
        """
        result = await session.execute(
            select(TrainingTask).where(
                TrainingTask.sop_document_uuid == sop_document_uuid,
                TrainingTask.sop_version == sop_version,
            )
        )
        tasks = list(result.scalars().all())

        total = len(tasks)
        completed = sum(1 for t in tasks if t.is_completed)

        return {
            "sop_document_uuid": sop_document_uuid,
            "sop_version": sop_version,
            "total_tasks": total,
            "completed_tasks": completed,
            "is_complete": total > 0 and completed == total,
        }
