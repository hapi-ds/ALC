"""RefreshToken model for server-side token revocation support.

This module defines the RefreshToken model that stores issued refresh tokens
in the database, enabling server-side revocation on logout and session
management for the authentication system.

References:
    - Requirements 2.2: Refresh token stored as httpOnly cookie with server-side tracking
    - Requirements 2.5: Logout clears and invalidates refresh tokens
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class RefreshToken(Base):
    """Server-side record of an issued refresh token.

    Each refresh token is identified by a unique JTI (JWT ID) claim.
    Tokens can be revoked by setting the `revoked_at` timestamp, which
    is checked during token refresh to reject invalidated tokens.

    Attributes:
        id: Primary key.
        jti: Unique JWT ID claim (UUID4 string) for token identification.
        user_id: Foreign key referencing the user who owns this token.
        expires_at: When the refresh token expires (UTC with timezone).
        revoked_at: When the token was revoked (null if still valid).
        created_at: Server-side UTC timestamp of token creation.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    jti: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
