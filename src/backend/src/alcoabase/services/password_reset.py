"""Password reset service for admin-initiated credential resets.

This module provides the PasswordResetService that generates secure
temporary passwords, hashes them with bcrypt, updates user credentials,
and invalidates all existing refresh tokens for the affected user.

References:
    - Requirement 9.1: Generate new temporary password on admin reset
    - Requirement 9.2: Hash temporary password with bcrypt
    - Requirement 9.3: Display temporary password to admin
    - Requirement 9.4: Record reset in audit trail without logging password
    - Requirement 9.5: Invalidate all refresh tokens on password reset
"""

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.refresh_token import RefreshToken
from alcoabase.models.user import User

logger = logging.getLogger(__name__)

# Password hashing context using bcrypt (matches auth_service pattern)
try:
    from passlib.context import CryptContext

    _pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    _pwd_context = None  # type: ignore[assignment]
    logger.error("passlib not available; password hashing will fail")


def generate_temporary_password() -> str:
    """Generate a 16-character URL-safe temporary password.

    Uses the secrets module for cryptographically secure random
    generation suitable for temporary credentials.

    Returns:
        A 16-character alphanumeric temporary password string.
    """
    # token_urlsafe(12) produces a 16-char base64url string
    return secrets.token_urlsafe(12)


async def reset_password(user_id: int, session: AsyncSession) -> str:
    """Reset a user's password and invalidate their refresh tokens.

    Generates a secure temporary password, hashes it with bcrypt,
    updates the user's stored password, and revokes all active
    refresh tokens for the user.

    Args:
        user_id: The ID of the user whose password is being reset.
        session: Active async database session.

    Returns:
        The plaintext temporary password for admin display only.

    Raises:
        ValueError: If the user is not found.
        RuntimeError: If password hashing fails.
    """
    # Fetch the user
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise ValueError(f"User with id {user_id} not found")

    # Generate temporary password
    temporary_password = generate_temporary_password()

    # Hash the temporary password with bcrypt
    try:
        hashed = _pwd_context.hash(temporary_password)
    except Exception:
        logger.exception("Failed to hash password for user_id=%d", user_id)
        raise RuntimeError("Password reset failed due to an internal error")

    # Update the user's stored password
    user.hashed_password = hashed
    await session.flush()

    # Invalidate all existing refresh tokens for the user
    now = datetime.now(timezone.utc)
    revoke_stmt = (
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(revoke_stmt)
    await session.flush()

    logger.info("Password reset completed for user_id=%d", user_id)

    return temporary_password
