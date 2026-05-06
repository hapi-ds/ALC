"""Authentication service with JWT token management.

This module provides the AuthService class that handles user authentication,
JWT access/refresh token creation and validation, password verification,
and user profile retrieval with company memberships.

Token specifications:
    - Access tokens: 15-min expiry, HS256, payload with sub, username, exp, iat, type="access"
    - Refresh tokens: 7-day expiry, HS256, payload with sub, exp, iat, jti (uuid4), type="refresh"

References:
    - Requirements 2.1: JWT access token issued on login
    - Requirements 2.2: Refresh token stored server-side for revocation
    - Requirements 2.5: Logout invalidates refresh tokens
    - Requirements 5.1: Proactive token refresh before expiry
    - Requirements 5.2: Session expiry handling
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from alcoabase.config import get_settings
from alcoabase.models.company import CompanyMembership
from alcoabase.models.refresh_token import RefreshToken
from alcoabase.models.user import User

# Password hashing context using bcrypt
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Token expiry constants
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7

# JWT algorithm
ALGORITHM = "HS256"


class AuthService:
    """Service for authentication and JWT token management.

    Provides methods for user credential validation, token creation
    and refresh, token revocation, password verification, and user
    profile retrieval including roles and company memberships.
    """

    def __init__(self) -> None:
        """Initialize the AuthService with settings."""
        self._settings = get_settings()

    @property
    def _secret_key(self) -> str:
        """Return the JWT signing secret key from settings."""
        return self._settings.secret_key

    async def authenticate_user(
        self, session: AsyncSession, username: str, password: str
    ) -> User | None:
        """Validate user credentials against the database.

        Args:
            session: Active async database session.
            username: The username to authenticate.
            password: The plaintext password to verify.

        Returns:
            The User instance if credentials are valid, None otherwise.
        """
        stmt = select(User).where(User.username == username)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            return None

        if not user.is_active:
            return None

        if not self.verify_password(password, user.hashed_password):
            return None

        return user

    def create_access_token(self, user_id: int, username: str) -> str:
        """Create a short-lived JWT access token.

        Args:
            user_id: The user's database ID.
            username: The user's username for the token payload.

        Returns:
            Encoded JWT access token string.
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": str(user_id),
            "username": username,
            "exp": expire,
            "iat": now,
            "type": "access",
        }

        return jwt.encode(payload, self._secret_key, algorithm=ALGORITHM)

    async def create_refresh_token(
        self, session: AsyncSession, user_id: int
    ) -> str:
        """Create a long-lived JWT refresh token and store it in the database.

        The refresh token is stored server-side to enable revocation on
        logout and session management.

        Args:
            session: Active async database session.
            user_id: The user's database ID.

        Returns:
            Encoded JWT refresh token string.
        """
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        jti = str(uuid4())

        payload = {
            "sub": str(user_id),
            "exp": expire,
            "iat": now,
            "jti": jti,
            "type": "refresh",
        }

        # Store the refresh token record in the database
        db_token = RefreshToken(
            jti=jti,
            user_id=user_id,
            expires_at=expire,
        )
        session.add(db_token)
        await session.flush()

        return jwt.encode(payload, self._secret_key, algorithm=ALGORITHM)

    async def refresh_access_token(
        self, session: AsyncSession, refresh_jti: str
    ) -> tuple[str, str] | None:
        """Validate a refresh token and issue a new access token.

        Checks that the refresh token exists in the database, has not been
        revoked, and has not expired. If valid, issues a new access token.

        Args:
            session: Active async database session.
            refresh_jti: The JTI claim from the refresh token to validate.

        Returns:
            A tuple of (new_access_token, username) if the refresh token is
            valid, None otherwise.
        """
        stmt = select(RefreshToken).where(RefreshToken.jti == refresh_jti)
        result = await session.execute(stmt)
        db_token = result.scalar_one_or_none()

        if db_token is None:
            return None

        # Check if token has been revoked
        if db_token.revoked_at is not None:
            return None

        # Check if token has expired
        now = datetime.now(timezone.utc)
        if db_token.expires_at.replace(tzinfo=timezone.utc) < now:
            return None

        # Fetch the user to get username for the access token
        user_stmt = select(User).where(User.id == db_token.user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.scalar_one_or_none()

        if user is None or not user.is_active:
            return None

        access_token = self.create_access_token(user.id, user.username)
        return access_token, user.username

    async def revoke_refresh_token(
        self, session: AsyncSession, jti: str
    ) -> bool:
        """Mark a refresh token as revoked in the database.

        Args:
            session: Active async database session.
            jti: The JTI claim of the refresh token to revoke.

        Returns:
            True if the token was found and revoked, False if not found.
        """
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        result = await session.execute(stmt)
        db_token = result.scalar_one_or_none()

        if db_token is None:
            return False

        db_token.revoked_at = datetime.now(timezone.utc)
        await session.flush()
        return True

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against a bcrypt hash.

        Args:
            plain_password: The plaintext password to verify.
            hashed_password: The bcrypt-hashed password to compare against.

        Returns:
            True if the password matches, False otherwise.
        """
        return _pwd_context.verify(plain_password, hashed_password)

    async def get_user_profile(
        self, session: AsyncSession, user_id: int
    ) -> dict | None:
        """Fetch user profile with roles and company memberships.

        Args:
            session: Active async database session.
            user_id: The user's database ID.

        Returns:
            Dictionary with user profile data including roles and companies,
            or None if the user is not found.
        """
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(User.id == user_id)
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user is None:
            return None

        # Fetch active company memberships
        membership_stmt = (
            select(CompanyMembership)
            .options(selectinload(CompanyMembership.company))
            .where(
                CompanyMembership.user_id == user_id,
                CompanyMembership.revoked_at.is_(None),
            )
        )
        membership_result = await session.execute(membership_stmt)
        memberships = membership_result.scalars().all()

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "roles": [role.name for role in user.roles],
            "companies": [
                {
                    "company_id": m.company_id,
                    "company_slug": m.company.slug,
                    "role": m.role,
                }
                for m in memberships
            ],
        }

    def decode_access_token(self, token: str) -> dict | None:
        """Decode and validate a JWT access token.

        Args:
            token: The encoded JWT access token string.

        Returns:
            The decoded token payload if valid, None otherwise.
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[ALGORITHM])
            if payload.get("type") != "access":
                return None
            return payload
        except JWTError:
            return None

    def decode_refresh_token(self, token: str) -> dict | None:
        """Decode and validate a JWT refresh token.

        Args:
            token: The encoded JWT refresh token string.

        Returns:
            The decoded token payload if valid, None otherwise.
        """
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[ALGORITHM])
            if payload.get("type") != "refresh":
                return None
            return payload
        except JWTError:
            return None

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Hash a plaintext password using bcrypt.

        Args:
            plain_password: The plaintext password to hash.

        Returns:
            The bcrypt-hashed password string.
        """
        return _pwd_context.hash(plain_password)
