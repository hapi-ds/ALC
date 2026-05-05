"""Unit tests for setup wizard components.

Tests cover:
- Task 11.1: PasswordValidator and SlugGenerator
- Task 11.2: SetupGuardMiddleware
- Task 11.3: SetupService

References:
    - Design: .kiro/specs/setup-wizard/design.md
    - Requirements: 1.2, 2.1–2.4, 3.2, 3.3, 3.5, 4.2–4.5, 5.4, 7.1–7.3, 8.2, 8.3
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base
from alcoabase.middleware.setup_guard import SetupGuardMiddleware
from alcoabase.services.password_validator import PasswordValidator
from alcoabase.services.slug_generator import SlugGenerator

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


# ===========================================================================
# Task 11.1: PasswordValidator and SlugGenerator Unit Tests
# ===========================================================================


class TestPasswordValidator:
    """Unit tests for PasswordValidator.

    Validates: Requirements 3.2, 3.3
    """

    def setup_method(self):
        self.validator = PasswordValidator()

    def test_valid_password_passes(self):
        """A password meeting all policy rules returns no errors."""
        errors = self.validator.validate("SecureP@ss123")
        assert errors == []

    def test_valid_password_with_various_special_chars(self):
        """Valid passwords with different special characters pass."""
        passwords = [
            "Abcdefgh1!@#",
            "P@ssw0rd!234",
            "Hello$World9x",
        ]
        for pw in passwords:
            errors = self.validator.validate(pw)
            assert errors == [], f"Expected no errors for '{pw}', got {errors}"

    def test_too_short_detected(self):
        """Password shorter than 12 characters is rejected."""
        errors = self.validator.validate("Ab1!short")
        assert any("12 characters" in e for e in errors)

    def test_missing_uppercase_detected(self):
        """Password without uppercase letter is rejected."""
        errors = self.validator.validate("nouppercase1!")
        assert any("uppercase" in e for e in errors)

    def test_missing_lowercase_detected(self):
        """Password without lowercase letter is rejected."""
        errors = self.validator.validate("NOLOWERCASE1!")
        assert any("lowercase" in e for e in errors)

    def test_missing_digit_detected(self):
        """Password without a digit is rejected."""
        errors = self.validator.validate("NoDigitsHere!!")
        assert any("digit" in e for e in errors)

    def test_missing_special_char_detected(self):
        """Password without a special character is rejected."""
        errors = self.validator.validate("NoSpecialChar1")
        assert any("special" in e for e in errors)

    def test_multiple_violations_reported_together(self):
        """All violated rules are reported in a single call."""
        # Empty string violates all rules
        errors = self.validator.validate("")
        assert len(errors) == 5  # length, upper, lower, digit, special

    def test_exactly_12_chars_passes_length(self):
        """A password of exactly 12 characters passes the length check."""
        errors = self.validator.validate("Abcdefgh1!23")
        assert not any("12 characters" in e for e in errors)

    def test_11_chars_fails_length(self):
        """A password of 11 characters fails the length check."""
        errors = self.validator.validate("Abcdefg1!23")
        assert any("12 characters" in e for e in errors)


class TestSlugGenerator:
    """Unit tests for SlugGenerator.

    Validates: Requirements 4.2, 4.3
    """

    def setup_method(self):
        self.generator = SlugGenerator()

    def test_basic_name_generates_slug(self):
        """Simple display name produces a lowercase hyphenated slug."""
        slug = self.generator.generate("Acme Corporation")
        assert slug == "acme-corporation"

    def test_unicode_handling(self):
        """Unicode characters are normalized to ASCII equivalents."""
        slug = self.generator.generate("Café Résumé")
        assert slug == "cafe-resume"

    def test_whitespace_collapsing(self):
        """Multiple spaces collapse into a single hyphen."""
        slug = self.generator.generate("Hello    World")
        assert slug == "hello-world"

    def test_special_characters_removed(self):
        """Non-alphanumeric characters become hyphens (collapsed)."""
        slug = self.generator.generate("Test & Co. (Ltd)")
        assert slug == "test-co-ltd"

    def test_empty_string_returns_untitled(self):
        """Empty input returns 'untitled' fallback."""
        slug = self.generator.generate("")
        assert slug == "untitled"

    def test_only_special_chars_returns_untitled(self):
        """Input with only special characters returns 'untitled'."""
        slug = self.generator.generate("@#$%^&*()")
        assert slug == "untitled"

    def test_leading_trailing_hyphens_stripped(self):
        """Leading and trailing hyphens are removed."""
        slug = self.generator.generate("  Hello World  ")
        assert slug == "hello-world"

    def test_numbers_preserved(self):
        """Digits in the name are preserved in the slug."""
        slug = self.generator.generate("Lab 42 Solutions")
        assert slug == "lab-42-solutions"

    def test_mixed_unicode_and_ascii(self):
        """Mixed unicode and ASCII produces a valid slug."""
        slug = self.generator.generate("München Lab")
        assert slug == "munchen-lab"


class TestSlugValidator:
    """Unit tests for SlugGenerator.validate().

    Validates: Requirements 4.3
    """

    def setup_method(self):
        self.generator = SlugGenerator()

    def test_valid_simple_slug(self):
        """Simple lowercase slug is accepted."""
        assert self.generator.validate("acme") is True

    def test_valid_hyphenated_slug(self):
        """Hyphenated slug is accepted."""
        assert self.generator.validate("acme-corp") is True

    def test_valid_slug_with_numbers(self):
        """Slug with numbers is accepted."""
        assert self.generator.validate("lab42") is True

    def test_valid_multi_segment_slug(self):
        """Multi-segment slug is accepted."""
        assert self.generator.validate("my-cool-company-123") is True

    def test_invalid_uppercase_rejected(self):
        """Slug with uppercase letters is rejected."""
        assert self.generator.validate("Acme") is False

    def test_invalid_spaces_rejected(self):
        """Slug with spaces is rejected."""
        assert self.generator.validate("acme corp") is False

    def test_invalid_special_chars_rejected(self):
        """Slug with special characters is rejected."""
        assert self.generator.validate("acme@corp") is False

    def test_invalid_leading_hyphen_rejected(self):
        """Slug starting with a hyphen is rejected."""
        assert self.generator.validate("-acme") is False

    def test_invalid_trailing_hyphen_rejected(self):
        """Slug ending with a hyphen is rejected."""
        assert self.generator.validate("acme-") is False

    def test_invalid_consecutive_hyphens_rejected(self):
        """Slug with consecutive hyphens is rejected."""
        assert self.generator.validate("acme--corp") is False

    def test_empty_slug_rejected(self):
        """Empty string is rejected."""
        assert self.generator.validate("") is False


# ===========================================================================
# Task 11.2: SetupGuardMiddleware Unit Tests
# ===========================================================================


class TestSetupGuardMiddleware:
    """Unit tests for SetupGuardMiddleware.

    Validates: Requirements 1.2, 2.1, 2.2, 2.3, 2.4, 7.3
    """

    def setup_method(self):
        """Reset middleware state before each test."""
        SetupGuardMiddleware._is_initialized = None

    def teardown_method(self):
        """Restore middleware state after each test."""
        SetupGuardMiddleware._is_initialized = True

    @pytest.mark.asyncio
    async def test_allows_health_when_uninitialized(self):
        """Health endpoint is accessible when system is uninitialized."""
        SetupGuardMiddleware._is_initialized = False

        request = MagicMock()
        request.url.path = "/health"

        call_next = AsyncMock(return_value=MagicMock(status_code=200))

        app = MagicMock()
        middleware = SetupGuardMiddleware(app)
        response = await middleware.dispatch(request, call_next)

        call_next.assert_called_once_with(request)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_allows_setup_paths_when_uninitialized(self):
        """Setup endpoints are accessible when system is uninitialized."""
        SetupGuardMiddleware._is_initialized = False

        setup_paths = [
            "/api/v1/setup/status",
            "/api/v1/setup/admin",
            "/api/v1/setup/company",
            "/api/v1/setup/ai-mode",
            "/api/v1/setup/complete",
        ]

        for path in setup_paths:
            request = MagicMock()
            request.url.path = path

            call_next = AsyncMock(return_value=MagicMock(status_code=200))

            app = MagicMock()
            middleware = SetupGuardMiddleware(app)
            response = await middleware.dispatch(request, call_next)

            call_next.assert_called_once_with(request)
            assert response.status_code == 200, (
                f"Expected 200 for {path}, got {response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_returns_503_for_other_paths_when_uninitialized(self):
        """Non-setup, non-exempt paths return 503 when uninitialized."""
        SetupGuardMiddleware._is_initialized = False

        blocked_paths = [
            "/api/v1/documents",
            "/api/v1/users",
            "/api/v1/companies",
            "/some/random/path",
        ]

        for path in blocked_paths:
            request = MagicMock()
            request.url.path = path

            call_next = AsyncMock()

            app = MagicMock()
            middleware = SetupGuardMiddleware(app)
            response = await middleware.dispatch(request, call_next)

            call_next.assert_not_called()
            assert response.status_code == 503, (
                f"Expected 503 for {path}, got {response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_returns_403_for_setup_paths_when_initialized(self):
        """Setup endpoints return 403 when system is already initialized."""
        SetupGuardMiddleware._is_initialized = True

        setup_paths = [
            "/api/v1/setup/status",
            "/api/v1/setup/admin",
            "/api/v1/setup/company",
            "/api/v1/setup/ai-mode",
            "/api/v1/setup/complete",
        ]

        for path in setup_paths:
            request = MagicMock()
            request.url.path = path

            call_next = AsyncMock()

            app = MagicMock()
            middleware = SetupGuardMiddleware(app)
            response = await middleware.dispatch(request, call_next)

            call_next.assert_not_called()
            assert response.status_code == 403, (
                f"Expected 403 for {path}, got {response.status_code}"
            )

    @pytest.mark.asyncio
    async def test_allows_other_paths_when_initialized(self):
        """Non-setup paths pass through when system is initialized."""
        SetupGuardMiddleware._is_initialized = True

        allowed_paths = [
            "/api/v1/documents",
            "/api/v1/users",
            "/health",
            "/docs",
        ]

        for path in allowed_paths:
            request = MagicMock()
            request.url.path = path

            call_next = AsyncMock(return_value=MagicMock(status_code=200))

            app = MagicMock()
            middleware = SetupGuardMiddleware(app)
            response = await middleware.dispatch(request, call_next)

            call_next.assert_called_once_with(request)
            assert response.status_code == 200, (
                f"Expected 200 for {path}, got {response.status_code}"
            )

    def test_cache_invalidation_triggers_state_transition(self):
        """invalidate_cache() resets the cached state to None."""
        SetupGuardMiddleware._is_initialized = True

        SetupGuardMiddleware.invalidate_cache()

        assert SetupGuardMiddleware._is_initialized is None


# ===========================================================================
# Task 11.3: SetupService Unit Tests
# ===========================================================================


async def _create_test_db():
    """Create an in-memory SQLite database with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_factory


class TestSetupService:
    """Unit tests for SetupService.

    Validates: Requirements 3.5, 4.4, 4.5, 5.4, 7.1, 7.2, 8.2, 8.3
    """

    @pytest.mark.asyncio
    async def test_root_admin_gets_system_administrator_role(self):
        """Root admin is assigned the system_administrator role."""
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = "test-secret"
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    from alcoabase.services.setup_service import SetupService
                    from alcoabase.schemas.setup import RootAdminCreate

                    service = SetupService(session)
                    data = RootAdminCreate(
                        username="rootadmin",
                        email="root@test.com",
                        password="SecureP@ss123",
                        full_name="Root Admin",
                    )
                    await service.create_root_admin(data)
                    await session.commit()

            # Verify role assignment
            async with session_factory() as session:
                from alcoabase.models.user import Role, User, UserRole

                result = await session.execute(
                    select(Role).where(Role.name == "system_administrator")
                )
                role = result.scalar_one()
                assert role is not None
                assert role.name == "system_administrator"

                # Verify user-role association exists
                result = await session.execute(
                    select(UserRole).where(UserRole.c.role_id == role.id)
                )
                user_role = result.first()
                assert user_role is not None
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_company_is_active_defaults_to_true(self):
        """Created company has is_active=True by default."""
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = "test-secret"
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    from alcoabase.services.setup_service import SetupService
                    from alcoabase.schemas.setup import (
                        CompanySetupCreate,
                        RootAdminCreate,
                    )

                    service = SetupService(session)

                    # Create admin first
                    admin_data = RootAdminCreate(
                        username="admin",
                        email="admin@test.com",
                        password="SecureP@ss123",
                        full_name="Admin User",
                    )
                    admin_result = await service.create_root_admin(admin_data)

                    # Create company
                    company_data = CompanySetupCreate(
                        display_name="Test Company",
                        slug="test-company",
                        regulatory_framework="GMP",
                    )
                    await service.create_initial_company(
                        company_data, admin_result.user_id
                    )
                    await session.commit()

            # Verify is_active
            async with session_factory() as session:
                from alcoabase.models.company import Company

                result = await session.execute(select(Company))
                company = result.scalar_one()
                assert company.is_active is True
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_root_admin_gets_company_admin_membership(self):
        """Root admin is assigned 'admin' role in the company membership."""
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = "test-secret"
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    from alcoabase.services.setup_service import SetupService
                    from alcoabase.schemas.setup import (
                        CompanySetupCreate,
                        RootAdminCreate,
                    )

                    service = SetupService(session)

                    admin_data = RootAdminCreate(
                        username="admin",
                        email="admin@test.com",
                        password="SecureP@ss123",
                        full_name="Admin User",
                    )
                    admin_result = await service.create_root_admin(admin_data)

                    company_data = CompanySetupCreate(
                        display_name="Test Corp",
                        slug="test-corp",
                        regulatory_framework="ISO_13485",
                    )
                    company_result = await service.create_initial_company(
                        company_data, admin_result.user_id
                    )
                    await session.commit()

            # Verify membership
            async with session_factory() as session:
                from alcoabase.models.company import CompanyMembership

                result = await session.execute(
                    select(CompanyMembership).where(
                        CompanyMembership.user_id == admin_result.user_id,
                        CompanyMembership.company_id == company_result.company_id,
                    )
                )
                membership = result.scalar_one()
                assert membership.role == "admin"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_ai_mode_mock_skips_connectivity_check(self):
        """AI mode 'mock' does not perform connectivity check."""
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = "test-secret"
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    from alcoabase.services.setup_service import SetupService
                    from alcoabase.schemas.setup import AIModeConfig

                    service = SetupService(session)

                    with patch(
                        "alcoabase.services.setup_service.httpx.AsyncClient"
                    ) as mock_client:
                        data = AIModeConfig(mode="mock")
                        result = await service.configure_ai_mode(data)

                        # httpx client should NOT have been used
                        mock_client.assert_not_called()

                    assert result.mode == "mock"
                    assert result.connectivity_warning is None
                    await session.commit()
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_each_ai_mode_persists_correctly(self):
        """Each AI mode ('gpu', 'cpu', 'mock') is persisted in setup_status."""
        for mode in ("gpu", "cpu", "mock"):
            engine, session_factory = await _create_test_db()
            try:
                async with session_factory() as session:
                    with patch(
                        "alcoabase.services.setup_service.get_settings"
                    ) as mock_settings:
                        mock_settings.return_value.secret_key = "test-secret"
                        mock_settings.return_value.vllm_base_url = (
                            "http://localhost:8000"
                        )

                        from alcoabase.services.setup_service import SetupService
                        from alcoabase.schemas.setup import AIModeConfig
                        from alcoabase.models.setup_status import SetupStatus

                        service = SetupService(session)

                        with patch(
                            "alcoabase.services.setup_service.httpx.AsyncClient"
                        ) as mock_client:
                            # Mock the connectivity check for gpu/cpu
                            mock_response = MagicMock()
                            mock_response.status_code = 200
                            mock_http_client = AsyncMock()
                            mock_http_client.get = AsyncMock(
                                return_value=mock_response
                            )
                            mock_http_client.__aenter__ = AsyncMock(
                                return_value=mock_http_client
                            )
                            mock_http_client.__aexit__ = AsyncMock(
                                return_value=False
                            )
                            mock_client.return_value = mock_http_client

                            data = AIModeConfig(mode=mode)
                            result = await service.configure_ai_mode(data)

                        assert result.mode == mode
                        await session.commit()

                # Verify persistence
                async with session_factory() as session:
                    from alcoabase.models.setup_status import SetupStatus

                    db_result = await session.execute(select(SetupStatus))
                    status = db_result.scalar_one()
                    assert status.ai_hardware_mode == mode
                    assert status.ai_mode_configured is True
            finally:
                await engine.dispose()

    @pytest.mark.asyncio
    async def test_409_on_duplicate_admin(self):
        """Creating root admin twice raises 409 conflict."""
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = "test-secret"
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    from alcoabase.services.setup_service import SetupService
                    from alcoabase.schemas.setup import RootAdminCreate

                    service = SetupService(session)
                    data = RootAdminCreate(
                        username="admin",
                        email="admin@test.com",
                        password="SecureP@ss123",
                        full_name="Admin User",
                    )

                    # First call succeeds
                    await service.create_root_admin(data)
                    await session.commit()

                    # Second call raises 409
                    with pytest.raises(HTTPException) as exc_info:
                        await service.create_root_admin(data)

                    assert exc_info.value.status_code == 409
                    assert "already exists" in exc_info.value.detail
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_409_on_duplicate_company(self):
        """Creating company twice raises 409 conflict."""
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = "test-secret"
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    from alcoabase.services.setup_service import SetupService
                    from alcoabase.schemas.setup import (
                        CompanySetupCreate,
                        RootAdminCreate,
                    )

                    service = SetupService(session)

                    # Create admin
                    admin_data = RootAdminCreate(
                        username="admin",
                        email="admin@test.com",
                        password="SecureP@ss123",
                        full_name="Admin User",
                    )
                    admin_result = await service.create_root_admin(admin_data)

                    # First company creation succeeds
                    company_data = CompanySetupCreate(
                        display_name="Test Corp",
                        slug="test-corp",
                        regulatory_framework="GMP",
                    )
                    await service.create_initial_company(
                        company_data, admin_result.user_id
                    )
                    await session.commit()

                    # Second call raises 409
                    with pytest.raises(HTTPException) as exc_info:
                        await service.create_initial_company(
                            company_data, admin_result.user_id
                        )

                    assert exc_info.value.status_code == 409
                    assert "already exists" in exc_info.value.detail
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_completion_records_timestamp_and_admin_id(self):
        """Setup completion records completed_at timestamp and root_admin_id."""
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = "test-secret"
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    from alcoabase.services.setup_service import SetupService
                    from alcoabase.schemas.setup import (
                        AIModeConfig,
                        CompanySetupCreate,
                        RootAdminCreate,
                    )

                    service = SetupService(session)

                    # Complete all required steps
                    admin_data = RootAdminCreate(
                        username="admin",
                        email="admin@test.com",
                        password="SecureP@ss123",
                        full_name="Admin User",
                    )
                    admin_result = await service.create_root_admin(admin_data)

                    company_data = CompanySetupCreate(
                        display_name="Test Corp",
                        slug="test-corp",
                        regulatory_framework="GMP",
                    )
                    await service.create_initial_company(
                        company_data, admin_result.user_id
                    )

                    with patch(
                        "alcoabase.services.setup_service.httpx.AsyncClient"
                    ) as mock_client:
                        mock_response = MagicMock()
                        mock_response.status_code = 200
                        mock_http_client = AsyncMock()
                        mock_http_client.get = AsyncMock(
                            return_value=mock_response
                        )
                        mock_http_client.__aenter__ = AsyncMock(
                            return_value=mock_http_client
                        )
                        mock_http_client.__aexit__ = AsyncMock(
                            return_value=False
                        )
                        mock_client.return_value = mock_http_client

                        ai_data = AIModeConfig(mode="mock")
                        await service.configure_ai_mode(ai_data)

                    # Complete setup
                    result = await service.complete_setup(
                        admin_id=admin_result.user_id, seed_demo=False
                    )
                    await session.commit()

            # Verify completion state
            async with session_factory() as session:
                from alcoabase.models.setup_status import SetupStatus

                db_result = await session.execute(select(SetupStatus))
                status = db_result.scalar_one()

                assert status.is_complete is True
                assert status.completed_at is not None
                assert status.root_admin_id == admin_result.user_id
        finally:
            await engine.dispose()
