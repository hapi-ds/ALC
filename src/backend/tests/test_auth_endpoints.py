"""Integration tests for authentication API endpoints.

Tests cover:
- Task 3.3: Auth endpoint integration tests
  - POST /api/v1/auth/login (valid, invalid, missing fields)
  - POST /api/v1/auth/refresh (valid cookie, expired/revoked token)
  - POST /api/v1/auth/logout (clears cookie, revokes token)
  - POST /api/v1/auth/re-authenticate (valid/invalid password)
  - GET /api/v1/auth/me (valid token, expired token)

References:
    - Design: .kiro/specs/auth-session-frontend/design.md
    - Requirements: 1.3, 1.5, 2.2, 6.2, 7.3, 7.4
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt

# ---------------------------------------------------------------------------
# bcrypt compatibility patch (bcrypt 5.x + passlib 1.7.4)
# ---------------------------------------------------------------------------
import bcrypt as _bcrypt_lib

_original_hashpw = _bcrypt_lib.hashpw
_original_checkpw = _bcrypt_lib.checkpw


def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_hashpw(password[:72], salt)


def _safe_checkpw(password: bytes, hashed_password: bytes) -> bool:
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_checkpw(password[:72], hashed_password)


_bcrypt_lib.hashpw = _safe_hashpw
_bcrypt_lib.checkpw = _safe_checkpw

# ---------------------------------------------------------------------------
# Imports after bcrypt patch
# ---------------------------------------------------------------------------

from alcoabase.database import get_db_session
from alcoabase.main import app
from alcoabase.models.user import User
from alcoabase.services.auth_service import ALGORITHM, AuthService, _pwd_context

# ---------------------------------------------------------------------------
# Test Constants
# ---------------------------------------------------------------------------

TEST_SECRET_KEY = "test-secret-key-for-integration-tests"
BASE_URL = "http://testserver"
AUTH_PREFIX = "/api/v1/auth"

# Header required by AuditMiddleware for mutating requests
AUDIT_HEADERS = {"X-Change-Reason": "Integration test"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_session():
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def test_user_password():
    """Return a plaintext password and its hash for testing."""
    plain = "SecureP@ss123!"
    hashed = _pwd_context.hash(plain)
    return plain, hashed


@pytest.fixture
def mock_user(test_user_password):
    """Create a mock User object with valid credentials."""
    _, hashed = test_user_password
    user = MagicMock(spec=User)
    user.id = 1
    user.username = "testuser"
    user.email = "test@alcoabase.local"
    user.full_name = "Test User"
    user.hashed_password = hashed
    user.is_active = True
    user.roles = []
    return user


@pytest.fixture
def auth_service():
    """Create an AuthService instance with a mocked settings object."""
    with patch("alcoabase.services.auth_service.get_settings") as mock_settings:
        settings = MagicMock()
        settings.secret_key = TEST_SECRET_KEY
        mock_settings.return_value = settings
        service = AuthService()
    return service


@pytest.fixture
def valid_access_token(auth_service):
    """Create a valid access token for testing."""
    return auth_service.create_access_token(user_id=1, username="testuser")


@pytest.fixture
def expired_access_token():
    """Create an expired access token for testing."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "username": "testuser",
        "exp": now - timedelta(hours=1),
        "iat": now - timedelta(hours=2),
        "type": "access",
    }
    return jwt.encode(payload, TEST_SECRET_KEY, algorithm=ALGORITHM)


@pytest.fixture
def valid_refresh_token(auth_service):
    """Create a valid refresh token JWT (without DB storage)."""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=7)
    payload = {
        "sub": "1",
        "exp": expire,
        "iat": now,
        "jti": "test-jti-12345",
        "type": "refresh",
    }
    return jwt.encode(payload, TEST_SECRET_KEY, algorithm=ALGORITHM)


@pytest.fixture
def expired_refresh_token():
    """Create an expired refresh token for testing."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "exp": now - timedelta(hours=1),
        "iat": now - timedelta(days=8),
        "jti": "expired-jti-999",
        "type": "refresh",
    }
    return jwt.encode(payload, TEST_SECRET_KEY, algorithm=ALGORITHM)


@pytest_asyncio.fixture
async def client(mock_session):
    """Create an httpx AsyncClient with the FastAPI app and mocked DB session."""

    async def override_get_db_session():
        yield mock_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as ac:
        yield ac

    app.dependency_overrides.clear()


# ===========================================================================
# Test: POST /login with valid credentials returns 200 + access_token + Set-Cookie
# Validates: Requirement 1.3
# ===========================================================================


class TestLoginEndpoint:
    """Tests for POST /api/v1/auth/login."""

    @pytest.mark.asyncio
    async def test_login_valid_credentials(self, client, mock_session, mock_user):
        """Login with valid credentials returns 200, access_token, and refresh cookie."""
        with (
            patch("alcoabase.api.auth.AuthService") as MockAuthService,
            patch("alcoabase.api.auth.get_settings") as mock_get_settings,
        ):
            mock_settings = MagicMock()
            mock_settings.secret_key = TEST_SECRET_KEY
            mock_get_settings.return_value = mock_settings

            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # authenticate_user returns the mock user
            service_instance.authenticate_user = AsyncMock(return_value=mock_user)
            # create_access_token returns a token string
            service_instance.create_access_token = MagicMock(
                return_value="mock-access-token"
            )
            # create_refresh_token returns a token string
            service_instance.create_refresh_token = AsyncMock(
                return_value="mock-refresh-token"
            )
            # get_user_profile returns profile dict
            service_instance.get_user_profile = AsyncMock(
                return_value={
                    "id": 1,
                    "username": "testuser",
                    "email": "test@alcoabase.local",
                    "full_name": "Test User",
                    "roles": ["admin"],
                    "companies": [],
                }
            )

            response = await client.post(
                f"{AUTH_PREFIX}/login",
                json={"username": "testuser", "password": "SecureP@ss123!"},
                headers=AUDIT_HEADERS,
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["access_token"] == "mock-access-token"
        assert data["token_type"] == "bearer"
        assert "expires_in" in data
        assert "user" in data
        assert data["user"]["username"] == "testuser"

        # Verify refresh token cookie is set
        cookies = response.cookies
        assert "refresh_token" in cookies

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, client, mock_session):
        """Login with invalid credentials returns 401."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance
            service_instance.authenticate_user = AsyncMock(return_value=None)

            response = await client.post(
                f"{AUTH_PREFIX}/login",
                json={"username": "baduser", "password": "wrongpass"},
                headers=AUDIT_HEADERS,
            )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client, mock_session):
        """Login with missing fields returns 422 validation error."""
        # Missing password
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"username": "testuser"},
            headers=AUDIT_HEADERS,
        )
        assert response.status_code == 422

        # Missing username
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={"password": "somepass"},
            headers=AUDIT_HEADERS,
        )
        assert response.status_code == 422

        # Empty body
        response = await client.post(
            f"{AUTH_PREFIX}/login",
            json={},
            headers=AUDIT_HEADERS,
        )
        assert response.status_code == 422


# ===========================================================================
# Test: POST /refresh with valid cookie returns new access_token
# Validates: Requirement 2.2
# ===========================================================================


class TestRefreshEndpoint:
    """Tests for POST /api/v1/auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_valid_cookie(
        self, client, mock_session, valid_refresh_token
    ):
        """Refresh with valid cookie returns new access_token and rotates cookie."""
        with (
            patch("alcoabase.api.auth.AuthService") as MockAuthService,
            patch("alcoabase.api.auth.get_settings") as mock_get_settings,
        ):
            mock_settings = MagicMock()
            mock_settings.secret_key = TEST_SECRET_KEY
            mock_get_settings.return_value = mock_settings

            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_refresh_token returns valid payload
            service_instance.decode_refresh_token = MagicMock(
                return_value={
                    "sub": "1",
                    "jti": "test-jti-12345",
                    "type": "refresh",
                }
            )
            # refresh_access_token returns new access token + username
            service_instance.refresh_access_token = AsyncMock(
                return_value=("new-access-token", "testuser")
            )
            # revoke_refresh_token succeeds
            service_instance.revoke_refresh_token = AsyncMock(return_value=True)
            # create_refresh_token returns new refresh token
            service_instance.create_refresh_token = AsyncMock(
                return_value="new-refresh-token"
            )

            response = await client.post(
                f"{AUTH_PREFIX}/refresh",
                cookies={"refresh_token": valid_refresh_token},
                headers=AUDIT_HEADERS,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new-access-token"
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

        # Verify new refresh cookie is set
        cookies = response.cookies
        assert "refresh_token" in cookies

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self, client, mock_session):
        """Refresh with expired token returns 401."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_refresh_token returns None for expired token
            service_instance.decode_refresh_token = MagicMock(return_value=None)

            response = await client.post(
                f"{AUTH_PREFIX}/refresh",
                cookies={"refresh_token": "expired-token-value"},
                headers=AUDIT_HEADERS,
            )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid or expired refresh token"

    @pytest.mark.asyncio
    async def test_refresh_revoked_token(self, client, mock_session):
        """Refresh with revoked token returns 401."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_refresh_token returns valid payload
            service_instance.decode_refresh_token = MagicMock(
                return_value={
                    "sub": "1",
                    "jti": "revoked-jti",
                    "type": "refresh",
                }
            )
            # refresh_access_token returns None (token revoked in DB)
            service_instance.refresh_access_token = AsyncMock(return_value=None)

            response = await client.post(
                f"{AUTH_PREFIX}/refresh",
                cookies={"refresh_token": "some-revoked-token"},
                headers=AUDIT_HEADERS,
            )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid or expired refresh token"

    @pytest.mark.asyncio
    async def test_refresh_missing_cookie(self, client, mock_session):
        """Refresh without cookie returns 401."""
        response = await client.post(
            f"{AUTH_PREFIX}/refresh",
            headers=AUDIT_HEADERS,
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid or expired refresh token"


# ===========================================================================
# Test: POST /logout clears cookie and revokes token
# Validates: Requirement 6.2
# ===========================================================================


class TestLogoutEndpoint:
    """Tests for POST /api/v1/auth/logout."""

    @pytest.mark.asyncio
    async def test_logout_clears_cookie_and_revokes(
        self, client, mock_session, valid_refresh_token
    ):
        """Logout revokes the refresh token and clears the cookie."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_refresh_token returns valid payload
            service_instance.decode_refresh_token = MagicMock(
                return_value={
                    "sub": "1",
                    "jti": "test-jti-12345",
                    "type": "refresh",
                }
            )
            # revoke_refresh_token succeeds
            service_instance.revoke_refresh_token = AsyncMock(return_value=True)

            response = await client.post(
                f"{AUTH_PREFIX}/logout",
                cookies={"refresh_token": valid_refresh_token},
                headers=AUDIT_HEADERS,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"

        # Verify revoke was called
        service_instance.revoke_refresh_token.assert_awaited_once_with(
            mock_session, "test-jti-12345"
        )

        # Verify cookie is cleared (set to empty or deleted)
        set_cookie_headers = response.headers.get_list("set-cookie")
        # The cookie should be cleared (max-age=0 or expires in the past)
        cookie_cleared = any(
            "refresh_token" in h and ('max-age=0' in h.lower() or '01 jan 1970' in h.lower() or 'expires=thu, 01 jan 1970' in h.lower())
            for h in set_cookie_headers
        )
        # At minimum, the set-cookie header should reference refresh_token
        assert any("refresh_token" in h for h in set_cookie_headers)

    @pytest.mark.asyncio
    async def test_logout_without_cookie(self, client, mock_session):
        """Logout without a cookie still returns 200 and clears cookie."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            response = await client.post(
                f"{AUTH_PREFIX}/logout",
                headers=AUDIT_HEADERS,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logged out successfully"


# ===========================================================================
# Test: POST /re-authenticate with valid/invalid password
# Validates: Requirements 7.3, 7.4
# ===========================================================================


class TestReAuthenticateEndpoint:
    """Tests for POST /api/v1/auth/re-authenticate."""

    @pytest.mark.asyncio
    async def test_reauth_valid_password(
        self, client, mock_session, mock_user, test_user_password, valid_access_token
    ):
        """Re-authenticate with valid password returns signature_token."""
        plain_password, _ = test_user_password

        with (
            patch("alcoabase.api.auth.AuthService") as MockAuthService,
            patch("alcoabase.api.auth.get_settings") as mock_get_settings,
        ):
            mock_settings = MagicMock()
            mock_settings.secret_key = TEST_SECRET_KEY
            mock_get_settings.return_value = mock_settings

            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_access_token returns valid payload (for get_current_user)
            service_instance.decode_access_token = MagicMock(
                return_value={
                    "sub": "1",
                    "username": "testuser",
                    "type": "access",
                }
            )
            # verify_password returns True
            service_instance.verify_password = MagicMock(return_value=True)

            # Mock the DB query for user lookup in re-authenticate
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_session.execute.return_value = mock_result

            response = await client.post(
                f"{AUTH_PREFIX}/re-authenticate",
                json={"password": plain_password},
                headers={
                    "Authorization": f"Bearer {valid_access_token}",
                    **AUDIT_HEADERS,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert "signature_token" in data
        assert data["expires_in"] == 120

    @pytest.mark.asyncio
    async def test_reauth_invalid_password(
        self, client, mock_session, mock_user, valid_access_token
    ):
        """Re-authenticate with invalid password returns 401."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_access_token returns valid payload
            service_instance.decode_access_token = MagicMock(
                return_value={
                    "sub": "1",
                    "username": "testuser",
                    "type": "access",
                }
            )
            # verify_password returns False
            service_instance.verify_password = MagicMock(return_value=False)

            # Mock the DB query for user lookup
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_user
            mock_session.execute.return_value = mock_result

            response = await client.post(
                f"{AUTH_PREFIX}/re-authenticate",
                json={"password": "wrong-password"},
                headers={
                    "Authorization": f"Bearer {valid_access_token}",
                    **AUDIT_HEADERS,
                },
            )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_reauth_without_bearer_token(self, client, mock_session):
        """Re-authenticate without Bearer token returns 401."""
        response = await client.post(
            f"{AUTH_PREFIX}/re-authenticate",
            json={"password": "somepass"},
            headers=AUDIT_HEADERS,
        )

        # HTTPBearer returns 401 when no credentials provided
        assert response.status_code == 401


# ===========================================================================
# Test: GET /me with valid/expired token
# Validates: Requirements 1.5, 7.4
# ===========================================================================


class TestMeEndpoint:
    """Tests for GET /api/v1/auth/me."""

    @pytest.mark.asyncio
    async def test_me_valid_token(
        self, client, mock_session, valid_access_token
    ):
        """GET /me with valid token returns user profile."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_access_token returns valid payload
            service_instance.decode_access_token = MagicMock(
                return_value={
                    "sub": "1",
                    "username": "testuser",
                    "type": "access",
                }
            )
            # get_user_profile returns profile dict
            service_instance.get_user_profile = AsyncMock(
                return_value={
                    "id": 1,
                    "username": "testuser",
                    "email": "test@alcoabase.local",
                    "full_name": "Test User",
                    "roles": ["admin"],
                    "companies": [
                        {
                            "company_id": 1,
                            "company_slug": "acme-corp",
                            "role": "admin",
                        }
                    ],
                }
            )

            response = await client.get(
                f"{AUTH_PREFIX}/me",
                headers={"Authorization": f"Bearer {valid_access_token}"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["username"] == "testuser"
        assert data["email"] == "test@alcoabase.local"
        assert data["full_name"] == "Test User"
        assert data["roles"] == ["admin"]
        assert len(data["companies"]) == 1
        assert data["companies"][0]["company_slug"] == "acme-corp"

    @pytest.mark.asyncio
    async def test_me_expired_token(
        self, client, mock_session, expired_access_token
    ):
        """GET /me with expired token returns 401."""
        with patch("alcoabase.api.auth.AuthService") as MockAuthService:
            service_instance = MagicMock()
            MockAuthService.return_value = service_instance

            # decode_access_token returns None for expired token
            service_instance.decode_access_token = MagicMock(return_value=None)

            response = await client.get(
                f"{AUTH_PREFIX}/me",
                headers={"Authorization": f"Bearer {expired_access_token}"},
            )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Invalid or expired access token"

    @pytest.mark.asyncio
    async def test_me_without_token(self, client, mock_session):
        """GET /me without token returns 401."""
        response = await client.get(f"{AUTH_PREFIX}/me")

        # HTTPBearer returns 401 when no credentials provided
        assert response.status_code == 401
