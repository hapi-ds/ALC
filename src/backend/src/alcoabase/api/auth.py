"""FastAPI router for authentication endpoints.

Provides login, token refresh, logout, re-authentication for electronic
signatures, and user profile retrieval. All token management uses JWT
with httpOnly cookies for refresh tokens and Bearer tokens for access.

Endpoints:
    POST /login           - Authenticate user, issue tokens
    POST /refresh         - Rotate refresh token, issue new access token
    POST /logout          - Revoke refresh token, clear cookie
    POST /re-authenticate - Verify password, issue short-lived signature token
    GET  /me              - Return current user profile with memberships

References:
    - Requirements: 1.3, 1.5, 2.2, 2.5, 6.2, 7.1, 7.3, 7.4
    - Design doc: .kiro/specs/auth-session-frontend/design.md
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.database import get_db_session
from alcoabase.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    MeResponse,
    ReAuthRequest,
    ReAuthResponse,
    RefreshResponse,
    UserInfo,
)
from alcoabase.services.auth_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    AuthService,
)

auth_router = APIRouter(tags=["Auth"])
_security = HTTPBearer()

# Cookie configuration constants
REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"

# Signature token expiry
SIGNATURE_TOKEN_EXPIRE_SECONDS = 120


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> int:
    """Extract and validate the user ID from the JWT Bearer token.

    Decodes the access token using the application secret key and returns
    the user_id from the 'sub' claim.

    Args:
        credentials: The HTTP Bearer token credentials extracted from
            the Authorization header.

    Returns:
        The authenticated user's ID as an integer.

    Raises:
        HTTPException: 401 if the token is missing, invalid, expired,
            or does not contain a valid subject claim.
    """
    auth_service = AuthService()
    payload = auth_service.decode_access_token(credentials.credentials)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired access token",
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token: missing subject claim",
        )

    try:
        return int(sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid token: malformed subject claim",
        )


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an httpOnly secure cookie.

    Args:
        response: The FastAPI response object to set the cookie on.
        token: The refresh token JWT string.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Clear the refresh token cookie from the client.

    Args:
        response: The FastAPI response object to clear the cookie on.
    """
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=True,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


@auth_router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """Authenticate user credentials and issue tokens.

    Validates the username and password against the database. On success,
    returns an access token in the response body and sets a refresh token
    as an httpOnly cookie.

    Args:
        data: Login request with username and password.
        response: FastAPI response for setting cookies.
        session: Async database session.

    Returns:
        LoginResponse with access_token, token_type, expires_in, and user info.

    Raises:
        HTTPException: 401 if credentials are invalid.
    """
    auth_service = AuthService()

    user = await auth_service.authenticate_user(session, data.username, data.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    # Issue tokens
    access_token = auth_service.create_access_token(user.id, user.username)
    refresh_token = await auth_service.create_refresh_token(session, user.id)

    # Set refresh token cookie
    _set_refresh_cookie(response, refresh_token)

    # Build user info from the authenticated user
    # Load roles for the user info response
    profile = await auth_service.get_user_profile(session, user.id)
    user_info = UserInfo(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        roles=profile["roles"] if profile else [],
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_info,
    )


@auth_router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
) -> RefreshResponse:
    """Rotate the refresh token and issue a new access token.

    Reads the refresh token from the httpOnly cookie, validates it,
    revokes the old token, issues a new refresh token (rotation), and
    returns a new access token.

    Args:
        response: FastAPI response for setting the new cookie.
        session: Async database session.
        refresh_token: The refresh token from the httpOnly cookie.

    Returns:
        RefreshResponse with new access_token, token_type, and expires_in.

    Raises:
        HTTPException: 401 if the refresh token is missing, invalid, or expired.
    """
    if refresh_token is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    auth_service = AuthService()

    # Decode the refresh token to get the JTI
    payload = auth_service.decode_refresh_token(refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    jti = payload.get("jti")
    user_id_str = payload.get("sub")
    if jti is None or user_id_str is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    # Validate and get new access token
    result = await auth_service.refresh_access_token(session, jti)
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired refresh token",
        )

    new_access_token, _username = result

    # Revoke the old refresh token (rotation)
    await auth_service.revoke_refresh_token(session, jti)

    # Issue a new refresh token
    user_id = int(user_id_str)
    new_refresh_token = await auth_service.create_refresh_token(session, user_id)
    _set_refresh_cookie(response, new_refresh_token)

    return RefreshResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@auth_router.post("/logout", response_model=LogoutResponse)
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
    refresh_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
) -> LogoutResponse:
    """Revoke the refresh token and clear the cookie.

    Reads the refresh token from the httpOnly cookie, revokes it in the
    database, and clears the cookie from the client.

    Args:
        response: FastAPI response for clearing the cookie.
        session: Async database session.
        refresh_token: The refresh token from the httpOnly cookie.

    Returns:
        LogoutResponse with a success message.
    """
    auth_service = AuthService()

    if refresh_token is not None:
        payload = auth_service.decode_refresh_token(refresh_token)
        if payload is not None:
            jti = payload.get("jti")
            if jti is not None:
                await auth_service.revoke_refresh_token(session, jti)

    # Always clear the cookie regardless of token validity
    _clear_refresh_cookie(response)

    return LogoutResponse(message="Logged out successfully")


@auth_router.post("/re-authenticate", response_model=ReAuthResponse)
async def re_authenticate(
    data: ReAuthRequest,
    session: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
) -> ReAuthResponse:
    """Re-authenticate the user and issue a short-lived signature token.

    Requires an existing Bearer token. Validates the user's password and,
    on success, returns a short-lived signature token (120s expiry) for
    authorizing electronic signature operations per CFR 21 Part 11.

    Args:
        data: Re-authentication request with the user's password.
        session: Async database session.
        user_id: The authenticated user's ID from the Bearer token.

    Returns:
        ReAuthResponse with verified=True, signature_token, and expires_in.

    Raises:
        HTTPException: 401 if the password is invalid or user not found.
    """
    auth_service = AuthService()

    # Fetch the user to verify password
    from sqlalchemy import select

    from alcoabase.models.user import User

    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    if not auth_service.verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    # Create a short-lived signature token
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=SIGNATURE_TOKEN_EXPIRE_SECONDS)

    signature_payload = {
        "sub": str(user_id),
        "username": user.username,
        "exp": expire,
        "iat": now,
        "type": "signature",
    }

    signature_token = jwt.encode(
        signature_payload, settings.secret_key, algorithm=ALGORITHM
    )

    return ReAuthResponse(
        verified=True,
        signature_token=signature_token,
        expires_in=SIGNATURE_TOKEN_EXPIRE_SECONDS,
    )


@auth_router.get("/me", response_model=MeResponse)
async def get_me(
    session: AsyncSession = Depends(get_db_session),
    user_id: int = Depends(get_current_user),
) -> MeResponse:
    """Return the current user's profile with company memberships.

    Requires a valid Bearer token. Returns the user's profile information
    including roles and active company memberships.

    Args:
        session: Async database session.
        user_id: The authenticated user's ID from the Bearer token.

    Returns:
        MeResponse with user profile and company memberships.

    Raises:
        HTTPException: 401 if the user is not found (token valid but user deleted).
    """
    auth_service = AuthService()
    profile = await auth_service.get_user_profile(session, user_id)

    if profile is None:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return MeResponse(
        id=profile["id"],
        username=profile["username"],
        email=profile["email"],
        full_name=profile["full_name"],
        roles=profile["roles"],
        companies=profile["companies"],
    )
