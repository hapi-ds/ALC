"""Property-based tests for Setup Step Idempotency.

Tests Property 9 from the setup-wizard design document:
- Property 9: Setup Step Idempotency

For any valid setup step input, submitting the same request twice with
identical parameters SHALL NOT create duplicate database records — the total
count of the relevant entity (users, companies) SHALL remain the same after
the second submission.

**Validates: Requirements 8.4**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Property 9)
    - Requirements: .kiro/specs/setup-wizard/requirements.md
"""

import asyncio
import string
from unittest.mock import patch

import bcrypt as _bcrypt_lib
import hypothesis.strategies as st
from fastapi import HTTPException
from hypothesis import given, settings
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.user import User
from alcoabase.schemas.setup import CompanySetupCreate, RootAdminCreate
from alcoabase.services.setup_service import SetupService


# ---------------------------------------------------------------------------
# Compatibility fix: bcrypt 5.x raises ValueError for passwords > 72 bytes,
# which breaks passlib 1.7.4's internal wrap-bug detection. We patch bcrypt
# to truncate at 72 bytes (bcrypt's inherent limit) before hashing/checking.
# ---------------------------------------------------------------------------

_original_hashpw = _bcrypt_lib.hashpw
_original_checkpw = _bcrypt_lib.checkpw


def _safe_hashpw(password: bytes, salt: bytes) -> bytes:
    """Wrap bcrypt.hashpw to truncate passwords at 72 bytes."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_hashpw(password[:72], salt)


def _safe_checkpw(password: bytes, hashed_password: bytes) -> bool:
    """Wrap bcrypt.checkpw to truncate passwords at 72 bytes."""
    if isinstance(password, str):
        password = password.encode("utf-8")
    return _original_checkpw(password[:72], hashed_password)


# Apply patches at module level so passlib's backend initialization succeeds
_bcrypt_lib.hashpw = _safe_hashpw
_bcrypt_lib.checkpw = _safe_checkpw


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine synchronously for use within hypothesis tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

UPPERCASE = string.ascii_uppercase
LOWERCASE = string.ascii_lowercase
DIGITS = string.digits
SPECIAL = "!@#$%^&*()-_=+[]{}|;:',.<>?/~`"
USERNAME_CHARS = string.ascii_lowercase + string.digits + "_"


@st.composite
def st_valid_password(draw: st.DrawFn) -> str:
    """Generate a random password satisfying the GxP password policy."""
    upper_char = draw(st.sampled_from(list(UPPERCASE)))
    lower_char = draw(st.sampled_from(list(LOWERCASE)))
    digit_char = draw(st.sampled_from(list(DIGITS)))
    special_char = draw(st.sampled_from(list(SPECIAL)))

    all_chars = UPPERCASE + LOWERCASE + DIGITS + SPECIAL
    remaining_length = draw(st.integers(min_value=8, max_value=46))
    remaining = draw(
        st.lists(
            st.sampled_from(list(all_chars)),
            min_size=remaining_length,
            max_size=remaining_length,
        )
    )

    chars = [upper_char, lower_char, digit_char, special_char] + remaining
    shuffled = draw(st.permutations(chars))
    return "".join(shuffled)


@st.composite
def st_valid_username(draw: st.DrawFn) -> str:
    """Generate a valid username: 3-50 chars, alphanumeric + underscore."""
    length = draw(st.integers(min_value=3, max_value=50))
    chars = draw(
        st.lists(
            st.sampled_from(list(USERNAME_CHARS)),
            min_size=length,
            max_size=length,
        )
    )
    return "".join(chars)


@st.composite
def st_valid_email(draw: st.DrawFn) -> str:
    """Generate a valid email address for testing."""
    local_length = draw(st.integers(min_value=3, max_value=20))
    local_chars = string.ascii_lowercase + string.digits
    local = draw(
        st.lists(
            st.sampled_from(list(local_chars)),
            min_size=local_length,
            max_size=local_length,
        )
    )
    domain_length = draw(st.integers(min_value=3, max_value=10))
    domain = draw(
        st.lists(
            st.sampled_from(list(string.ascii_lowercase)),
            min_size=domain_length,
            max_size=domain_length,
        )
    )
    tld = draw(st.sampled_from(["com", "org", "net", "io", "dev"]))
    return f"{''.join(local)}@{''.join(domain)}.{tld}"


@st.composite
def st_valid_full_name(draw: st.DrawFn) -> str:
    """Generate a valid full name: letters and spaces."""
    first_length = draw(st.integers(min_value=2, max_value=30))
    last_length = draw(st.integers(min_value=2, max_value=30))
    first = draw(
        st.lists(
            st.sampled_from(list(string.ascii_letters)),
            min_size=first_length,
            max_size=first_length,
        )
    )
    last = draw(
        st.lists(
            st.sampled_from(list(string.ascii_letters)),
            min_size=last_length,
            max_size=last_length,
        )
    )
    return f"{''.join(first)} {''.join(last)}"


@st.composite
def st_valid_display_name(draw: st.DrawFn) -> str:
    """Generate a valid company display name: 1-100 chars."""
    length = draw(st.integers(min_value=3, max_value=100))
    chars = string.ascii_letters + string.digits + " -&."
    name = draw(
        st.lists(
            st.sampled_from(list(chars)),
            min_size=length,
            max_size=length,
        )
    )
    result = "".join(name).strip()
    if not result:
        return "TestCompany"
    return result


@st.composite
def st_valid_slug(draw: st.DrawFn) -> str:
    """Generate a valid slug: lowercase letters, digits, hyphens."""
    num_segments = draw(st.integers(min_value=1, max_value=4))
    segments = []
    for _ in range(num_segments):
        seg_length = draw(st.integers(min_value=1, max_value=15))
        seg_chars = string.ascii_lowercase + string.digits
        seg = draw(
            st.lists(
                st.sampled_from(list(seg_chars)),
                min_size=seg_length,
                max_size=seg_length,
            )
        )
        segments.append("".join(seg))
    return "-".join(segments)


@st.composite
def st_regulatory_framework(draw: st.DrawFn) -> str:
    """Generate a valid regulatory framework string."""
    return draw(
        st.sampled_from([
            "ISO_13485",
            "GMP",
            "FDA_21CFR11",
            "ISO_9001",
            "EU_GMP_Annex11",
            "ICH_Q10",
        ])
    )


# ---------------------------------------------------------------------------
# Database setup helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Property 9: Setup Step Idempotency
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 9: Setup Step Idempotency
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_setup_step_idempotency(data: st.DataObject) -> None:
    """For any valid setup step input, submitting the same request twice with
    identical parameters SHALL NOT create duplicate database records — the
    total count of the relevant entity (users, companies) SHALL remain the
    same after the second submission.

    **Validates: Requirements 8.4**
    """
    username = data.draw(st_valid_username(), label="username")
    email = data.draw(st_valid_email(), label="email")
    password = data.draw(st_valid_password(), label="password")
    full_name = data.draw(st_valid_full_name(), label="full_name")
    display_name = data.draw(st_valid_display_name(), label="display_name")
    slug = data.draw(st_valid_slug(), label="slug")
    regulatory_framework = data.draw(
        st_regulatory_framework(), label="regulatory_framework"
    )

    test_secret_key = "test-secret-key-for-property-tests"

    async def _test():
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = test_secret_key
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    service = SetupService(session)

                    # --- Test root admin idempotency ---
                    admin_data = RootAdminCreate(
                        username=username,
                        email=email,
                        password=password,
                        full_name=full_name,
                    )

                    # First creation should succeed
                    admin_result = await service.create_root_admin(admin_data)
                    await session.flush()

                    # Count users after first creation
                    user_count_result = await session.execute(
                        select(func.count()).select_from(User)
                    )
                    user_count_after_first = user_count_result.scalar()

                    # Second creation should raise 409
                    try:
                        await service.create_root_admin(admin_data)
                        assert False, "Expected HTTPException 409 for duplicate admin"
                    except HTTPException as exc:
                        assert exc.status_code == 409, (
                            f"Expected 409, got {exc.status_code}"
                        )

                    # Count users after second attempt - should be unchanged
                    user_count_result = await session.execute(
                        select(func.count()).select_from(User)
                    )
                    user_count_after_second = user_count_result.scalar()

                    assert user_count_after_first == user_count_after_second, (
                        f"User count changed from {user_count_after_first} "
                        f"to {user_count_after_second} after duplicate admin creation"
                    )
                    assert user_count_after_first == 1, (
                        f"Expected exactly 1 user, got {user_count_after_first}"
                    )

                    # --- Test company idempotency ---
                    company_data = CompanySetupCreate(
                        display_name=display_name,
                        slug=slug,
                        regulatory_framework=regulatory_framework,
                    )

                    # First creation should succeed
                    await service.create_initial_company(
                        company_data, admin_result.user_id
                    )
                    await session.flush()

                    # Count companies after first creation
                    company_count_result = await session.execute(
                        select(func.count()).select_from(Company)
                    )
                    company_count_after_first = company_count_result.scalar()

                    # Second creation should raise 409
                    try:
                        await service.create_initial_company(
                            company_data, admin_result.user_id
                        )
                        assert False, "Expected HTTPException 409 for duplicate company"
                    except HTTPException as exc:
                        assert exc.status_code == 409, (
                            f"Expected 409, got {exc.status_code}"
                        )

                    # Count companies after second attempt - should be unchanged
                    company_count_result = await session.execute(
                        select(func.count()).select_from(Company)
                    )
                    company_count_after_second = company_count_result.scalar()

                    assert company_count_after_first == company_count_after_second, (
                        f"Company count changed from {company_count_after_first} "
                        f"to {company_count_after_second} after duplicate company creation"
                    )
                    assert company_count_after_first == 1, (
                        f"Expected exactly 1 company, got {company_count_after_first}"
                    )

        finally:
            await engine.dispose()

    _run_async(_test())
