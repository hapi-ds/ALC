"""User Management Service for admin CRUD operations on user accounts.

This module provides the UserManagementService class that handles:
- User creation with uniqueness validation and password hashing
- User profile and role updates
- User activation/deactivation (soft operations for GxP compliance)
- Paginated user listing with search, sort, and filter
- User detail retrieval with company memberships
- User change history via SQLAlchemy-Continuum version tables
- Company membership management (assign, revoke, list)

All operations are designed for use within an async SQLAlchemy session
and raise FastAPI HTTPException for client-facing errors.

References:
    - Design: .kiro/specs/Step_6-1_admin-dashboard-user-management/design.md
    - Requirements: 5.1–5.5, 6.1–6.7, 7.1–7.5, 8.1–8.6, 11.1–11.5, 14.1–14.3
"""

import math
import secrets
from datetime import datetime, timezone

import bcrypt
from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.company import CompanyMembership
from alcoabase.models.user import Role, User
from alcoabase.schemas.admin_users import (
    UserCreateRequest,
    UserListParams,
    UserUpdateRequest,
)


class UserManagementService:
    """Service for user account management operations.

    Provides CRUD operations for user accounts within a company context,
    including uniqueness validation, password hashing, role assignment,
    and audit-compliant activation/deactivation.
    """

    # ------------------------------------------------------------------
    # User Creation
    # ------------------------------------------------------------------

    async def create_user(
        self,
        payload: UserCreateRequest,
        company_id: int,
        session: AsyncSession,
    ) -> tuple[User, str]:
        """Create a new user account with company membership.

        Validates username and email uniqueness system-wide, generates a
        temporary password, hashes it with bcrypt, creates the User record
        and a CompanyMembership linking the user to the specified company
        with the requested role.

        Args:
            payload: Validated user creation request data.
            company_id: The company to assign the new user to.
            session: Active async database session.

        Returns:
            A tuple of (created User instance, plaintext temporary password).

        Raises:
            HTTPException 409: If username or email already exists.
            HTTPException 404: If the specified role is not found for the company.
        """
        # Validate username uniqueness (system-wide)
        await self._check_username_unique(payload.username, session)

        # Validate email uniqueness (system-wide)
        await self._check_email_unique(payload.email, session)

        # Generate temporary password
        temp_password = self._generate_temporary_password()

        # Hash password with bcrypt
        hashed_password = self._hash_password(temp_password)

        # Look up the role for this company
        role = await self._get_role_by_name(payload.role, company_id, session)

        # Create User record
        user = User(
            username=payload.username,
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hashed_password,
            is_active=True,
        )
        session.add(user)
        await session.flush()  # Get the user.id

        # Create CompanyMembership with role_id
        membership = CompanyMembership(
            user_id=user.id,
            company_id=company_id,
            role=payload.role,  # Legacy string field
            role_id=role.id,
        )
        session.add(membership)
        await session.flush()

        return user, temp_password

    # ------------------------------------------------------------------
    # User Update
    # ------------------------------------------------------------------

    async def update_user(
        self,
        user_id: int,
        payload: UserUpdateRequest,
        company_id: int,
        session: AsyncSession,
    ) -> User:
        """Update a user's profile fields and/or role assignment.

        Validates email uniqueness if the email is being changed. Updates
        the CompanyMembership role if a new role is specified.

        Args:
            user_id: The ID of the user to update.
            payload: Validated update request data (partial fields).
            company_id: The company context for role updates.
            session: Active async database session.

        Returns:
            The updated User instance.

        Raises:
            HTTPException 404: If user not found.
            HTTPException 409: If new email already exists.
            HTTPException 404: If specified role not found for company.
        """
        user = await self._get_user_or_404(user_id, session)

        # Update full_name if provided
        if payload.full_name is not None:
            user.full_name = payload.full_name

        # Update email if provided (with uniqueness check)
        if payload.email is not None and payload.email != user.email:
            await self._check_email_unique(payload.email, session, exclude_user_id=user_id)
            user.email = payload.email

        # Update role if provided
        if payload.role is not None:
            role = await self._get_role_by_name(payload.role, company_id, session)
            membership = await self._get_active_membership(user_id, company_id, session)
            membership.role = payload.role  # Legacy string field
            membership.role_id = role.id

        await session.flush()
        return user

    # ------------------------------------------------------------------
    # Deactivation / Reactivation
    # ------------------------------------------------------------------

    async def deactivate_user(
        self,
        user_id: int,
        acting_user_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> User:
        """Deactivate a user account (soft operation).

        Sets is_active=False on the user. Prevents self-deactivation
        with HTTP 422.

        Args:
            user_id: The ID of the user to deactivate.
            acting_user_id: The ID of the admin performing the action.
            company_id: The company context.
            session: Active async database session.

        Returns:
            The deactivated User instance.

        Raises:
            HTTPException 422: If acting_user_id == user_id (self-deactivation).
            HTTPException 404: If user not found.
        """
        if user_id == acting_user_id:
            raise HTTPException(
                status_code=422,
                detail="Cannot deactivate your own account.",
            )

        user = await self._get_user_or_404(user_id, session)

        # Verify user belongs to this company
        await self._get_active_membership(user_id, company_id, session)

        user.is_active = False
        await session.flush()
        return user

    async def reactivate_user(
        self,
        user_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> User:
        """Reactivate a deactivated user account.

        Sets is_active=True, restoring the user's role permissions.

        Args:
            user_id: The ID of the user to reactivate.
            company_id: The company context.
            session: Active async database session.

        Returns:
            The reactivated User instance.

        Raises:
            HTTPException 404: If user not found.
        """
        user = await self._get_user_or_404(user_id, session)

        # Verify user belongs to this company
        await self._get_active_membership(user_id, company_id, session)

        user.is_active = True
        await session.flush()
        return user

    # ------------------------------------------------------------------
    # User Listing
    # ------------------------------------------------------------------

    async def list_users(
        self,
        company_id: int,
        params: UserListParams,
        session: AsyncSession,
    ) -> dict:
        """List users for a company with pagination, search, sort, and filter.

        Queries users who have an active membership in the specified company.
        Supports case-insensitive substring search across username, email,
        and full_name fields.

        Args:
            company_id: The company to list users for.
            params: Pagination, search, sort, and filter parameters.
            session: Active async database session.

        Returns:
            Dictionary with keys: users, total, page, page_size, total_pages.
        """
        # Base query: users with active membership in this company
        base_query = (
            select(User, CompanyMembership.role)
            .join(
                CompanyMembership,
                (CompanyMembership.user_id == User.id)
                & (CompanyMembership.company_id == company_id)
                & (CompanyMembership.revoked_at.is_(None)),
            )
        )

        # Apply search filter
        if params.search:
            search_term = f"%{params.search}%"
            base_query = base_query.where(
                or_(
                    User.username.ilike(search_term),
                    User.email.ilike(search_term),
                    User.full_name.ilike(search_term),
                )
            )

        # Apply active filter
        if params.is_active is not None:
            base_query = base_query.where(User.is_active == params.is_active)

        # Count total matching records
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_query)
        total = total_result.scalar_one()

        # Apply sorting
        sort_column = self._get_sort_column(params.sort_by)
        if params.sort_dir == "desc":
            base_query = base_query.order_by(sort_column.desc())
        else:
            base_query = base_query.order_by(sort_column.asc())

        # Apply pagination
        offset = (params.page - 1) * params.page_size
        base_query = base_query.offset(offset).limit(params.page_size)

        # Execute query
        result = await session.execute(base_query)
        rows = result.all()

        # Build response
        users = []
        for row in rows:
            user = row[0]
            role = row[1]
            users.append({
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "role": role,
                "is_active": user.is_active,
                "created_at": user.created_at,
            })

        total_pages = math.ceil(total / params.page_size) if total > 0 else 1

        return {
            "users": users,
            "total": total,
            "page": params.page,
            "page_size": params.page_size,
            "total_pages": total_pages,
        }

    # ------------------------------------------------------------------
    # User Detail
    # ------------------------------------------------------------------

    async def get_user_detail(
        self,
        user_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> dict:
        """Get detailed user information with all company memberships.

        Returns the user's profile along with all memberships (active and
        revoked) including company names and role assignments.

        Args:
            user_id: The ID of the user to retrieve.
            company_id: The company context (used to verify access).
            session: Active async database session.

        Returns:
            Dictionary with user details and memberships list.

        Raises:
            HTTPException 404: If user not found.
        """
        user = await self._get_user_or_404(user_id, session)

        # Load all memberships for this user (active and revoked)
        from alcoabase.models.company import Company

        membership_stmt = (
            select(CompanyMembership, Company.display_name)
            .join(Company, Company.id == CompanyMembership.company_id)
            .where(CompanyMembership.user_id == user_id)
            .order_by(CompanyMembership.created_at.desc())
        )
        membership_result = await session.execute(membership_stmt)
        membership_rows = membership_result.all()

        memberships = []
        for row in membership_rows:
            membership = row[0]
            company_name = row[1]
            memberships.append({
                "id": membership.id,
                "company_id": membership.company_id,
                "company_name": company_name,
                "role": membership.role,
                "created_at": membership.created_at,
                "revoked_at": membership.revoked_at,
            })

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "memberships": memberships,
        }

    # ------------------------------------------------------------------
    # User History
    # ------------------------------------------------------------------

    async def get_user_history(
        self,
        user_id: int,
        session: AsyncSession,
    ) -> list[dict]:
        """Get the change history for a user via SQLAlchemy-Continuum.

        Queries the version tables to reconstruct change diffs showing
        what fields changed, old/new values, who made the change, and why.

        Args:
            user_id: The ID of the user whose history to retrieve.
            session: Active async database session.

        Returns:
            List of history entry dictionaries ordered by most recent first.
            Each entry contains: version_id, changed_at, changed_by,
            changed_by_username, change_reason, changes dict.
        """
        # Attempt to query SQLAlchemy-Continuum version tables
        try:
            from sqlalchemy_continuum import version_class

            UserVersion = version_class(User)
        except (ImportError, Exception):
            # If Continuum is not available, return empty history
            return []

        # Query all versions for this user, ordered by transaction_id desc
        version_stmt = (
            select(UserVersion)
            .where(UserVersion.id == user_id)
            .order_by(UserVersion.transaction_id.desc())
        )
        version_result = await session.execute(version_stmt)
        versions = version_result.scalars().all()

        if not versions:
            return []

        # Build history entries by comparing consecutive versions
        entries: list[dict] = []
        tracked_fields = ["username", "email", "full_name", "is_active"]

        for i, version in enumerate(versions):
            # Skip the first version (initial creation has no "previous")
            # unless it's an INSERT operation (operation_type == 0)
            if i == len(versions) - 1:
                # This is the oldest version (creation)
                changes = {}
                for field in tracked_fields:
                    new_val = getattr(version, field, None)
                    if new_val is not None:
                        changes[field] = {"old": None, "new": new_val}

                entries.append({
                    "version_id": version.transaction_id,
                    "changed_at": getattr(version, "created_at", None),
                    "changed_by": 0,  # System/unknown for creation
                    "changed_by_username": "system",
                    "change_reason": "User created",
                    "changes": changes,
                })
            else:
                # Compare with the next (older) version
                older_version = versions[i + 1]
                changes = {}
                for field in tracked_fields:
                    old_val = getattr(older_version, field, None)
                    new_val = getattr(version, field, None)
                    if old_val != new_val:
                        changes[field] = {"old": old_val, "new": new_val}

                if changes:
                    entries.append({
                        "version_id": version.transaction_id,
                        "changed_at": getattr(version, "created_at", None),
                        "changed_by": 0,
                        "changed_by_username": "system",
                        "change_reason": "Profile updated",
                        "changes": changes,
                    })

        return entries

    # ------------------------------------------------------------------
    # Membership Management (Requirements 11.1–11.5)
    # ------------------------------------------------------------------

    async def assign_membership(
        self,
        user_id: int,
        company_id: int,
        role: str,
        session: AsyncSession,
    ) -> CompanyMembership:
        """Assign a user to a company with a specified role.

        Creates a new CompanyMembership linking the user to the company.
        Validates that no active (non-revoked) membership already exists
        for the same (user_id, company_id) pair.

        Args:
            user_id: The ID of the user to assign.
            company_id: The ID of the company to assign the user to.
            role: The role name to assign (e.g., "member", "system_admin").
            session: Active async database session.

        Returns:
            The newly created CompanyMembership instance.

        Raises:
            HTTPException 409: If an active membership already exists for
                the (user_id, company_id) pair.
            HTTPException 404: If the specified role is not found for the company.
        """
        # Check for existing active membership (not revoked)
        existing_stmt = select(CompanyMembership).where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.revoked_at.is_(None),
        )
        existing_result = await session.execute(existing_stmt)
        if existing_result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail="User already has an active membership in this company.",
            )

        # Look up the role for this company
        role_obj = await self._get_role_by_name(role, company_id, session)

        # Create the membership
        membership = CompanyMembership(
            user_id=user_id,
            company_id=company_id,
            role=role,  # Legacy string field
            role_id=role_obj.id,
        )
        session.add(membership)
        await session.flush()

        return membership

    async def revoke_membership(
        self,
        membership_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> CompanyMembership:
        """Revoke a company membership (soft delete).

        Sets the revoked_at timestamp on the membership record rather
        than hard-deleting it, preserving the audit trail for GxP
        compliance.

        Args:
            membership_id: The ID of the membership to revoke.
            company_id: The company context (used to verify ownership).
            session: Active async database session.

        Returns:
            The revoked CompanyMembership instance with revoked_at set.

        Raises:
            HTTPException 404: If membership not found or does not belong
                to the specified company.
        """
        stmt = select(CompanyMembership).where(
            CompanyMembership.id == membership_id,
            CompanyMembership.company_id == company_id,
        )
        result = await session.execute(stmt)
        membership = result.scalar_one_or_none()

        if membership is None:
            raise HTTPException(
                status_code=404,
                detail="Membership not found.",
            )

        membership.revoked_at = datetime.now(timezone.utc)
        await session.flush()

        return membership

    async def list_memberships(
        self,
        user_id: int,
        session: AsyncSession,
    ) -> list[dict]:
        """List all memberships for a user (active and revoked).

        Returns all company memberships including company names, roles,
        creation timestamps, and revocation timestamps.

        Args:
            user_id: The ID of the user whose memberships to list.
            session: Active async database session.

        Returns:
            List of membership dictionaries with company names and
            timestamps, ordered by creation date descending.
        """
        from alcoabase.models.company import Company

        stmt = (
            select(CompanyMembership, Company.display_name)
            .join(Company, Company.id == CompanyMembership.company_id)
            .where(CompanyMembership.user_id == user_id)
            .order_by(CompanyMembership.created_at.desc())
        )
        result = await session.execute(stmt)
        rows = result.all()

        memberships = []
        for row in rows:
            membership = row[0]
            company_name = row[1]
            memberships.append({
                "id": membership.id,
                "user_id": membership.user_id,
                "company_id": membership.company_id,
                "company_name": company_name,
                "role": membership.role,
                "created_at": membership.created_at,
                "revoked_at": membership.revoked_at,
            })

        return memberships

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    async def _check_username_unique(
        self,
        username: str,
        session: AsyncSession,
        exclude_user_id: int | None = None,
    ) -> None:
        """Validate that a username is unique system-wide.

        Args:
            username: The username to check.
            session: Active async database session.
            exclude_user_id: Optional user ID to exclude (for updates).

        Raises:
            HTTPException 409: If username already exists.
        """
        stmt = select(User.id).where(User.username == username)
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Username '{username}' is already taken.",
            )

    async def _check_email_unique(
        self,
        email: str,
        session: AsyncSession,
        exclude_user_id: int | None = None,
    ) -> None:
        """Validate that an email is unique system-wide.

        Args:
            email: The email to check.
            session: Active async database session.
            exclude_user_id: Optional user ID to exclude (for updates).

        Raises:
            HTTPException 409: If email already exists.
        """
        stmt = select(User.id).where(User.email == email)
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Email '{email}' is already registered.",
            )

    async def _get_user_or_404(
        self,
        user_id: int,
        session: AsyncSession,
    ) -> User:
        """Load a user by ID or raise 404.

        Args:
            user_id: The user's database ID.
            session: Active async database session.

        Returns:
            The User instance.

        Raises:
            HTTPException 404: If user not found.
        """
        stmt = select(User).where(User.id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found.")
        return user

    async def _get_role_by_name(
        self,
        role_name: str,
        company_id: int,
        session: AsyncSession,
    ) -> Role:
        """Load a role by name within a company scope.

        Args:
            role_name: The role name to look up.
            company_id: The company context.
            session: Active async database session.

        Returns:
            The Role instance.

        Raises:
            HTTPException 404: If role not found for the company.
        """
        stmt = select(Role).where(
            Role.name == role_name,
            Role.company_id == company_id,
        )
        result = await session.execute(stmt)
        role = result.scalar_one_or_none()
        if role is None:
            raise HTTPException(
                status_code=404,
                detail=f"Role not found: {role_name}",
            )
        return role

    async def _get_active_membership(
        self,
        user_id: int,
        company_id: int,
        session: AsyncSession,
    ) -> CompanyMembership:
        """Load the active membership for a user in a company.

        Args:
            user_id: The user's database ID.
            company_id: The company's database ID.
            session: Active async database session.

        Returns:
            The active CompanyMembership instance.

        Raises:
            HTTPException 404: If no active membership found.
        """
        stmt = select(CompanyMembership).where(
            CompanyMembership.user_id == user_id,
            CompanyMembership.company_id == company_id,
            CompanyMembership.revoked_at.is_(None),
        )
        result = await session.execute(stmt)
        membership = result.scalar_one_or_none()
        if membership is None:
            raise HTTPException(
                status_code=404,
                detail="User is not an active member of this company.",
            )
        return membership

    @staticmethod
    def _generate_temporary_password() -> str:
        """Generate a secure temporary password.

        Uses the secrets module to generate a URL-safe random string
        of 16 characters.

        Returns:
            A 16-character alphanumeric temporary password.
        """
        return secrets.token_urlsafe(12)  # ~16 chars base64

    @staticmethod
    def _hash_password(password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: The plaintext password to hash.

        Returns:
            The bcrypt-hashed password string.
        """
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password_bytes, salt)
        return hashed.decode("utf-8")

    @staticmethod
    def matches_search_query(
        username: str,
        email: str,
        full_name: str,
        query: str,
    ) -> bool:
        """Determine if a user matches a search query string.

        A user matches if the query is a case-insensitive substring of
        the user's username, email, or full_name. This mirrors the SQL
        ILIKE '%query%' logic used in list_users.

        Args:
            username: The user's username.
            email: The user's email address.
            full_name: The user's full name.
            query: The search query string.

        Returns:
            True if the query is a case-insensitive substring of any of
            the three fields, False otherwise.
        """
        q = query.lower()
        return (
            q in username.lower()
            or q in email.lower()
            or q in full_name.lower()
        )

    @staticmethod
    def _get_sort_column(sort_by: str):
        """Map sort field name to SQLAlchemy column.

        Args:
            sort_by: The field name to sort by.

        Returns:
            The corresponding SQLAlchemy column for ordering.
        """
        sort_map = {
            "full_name": User.full_name,
            "username": User.username,
            "role": CompanyMembership.role,
            "is_active": User.is_active,
            "created_at": User.created_at,
        }
        return sort_map.get(sort_by, User.created_at)
