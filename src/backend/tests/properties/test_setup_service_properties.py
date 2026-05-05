"""Property-based tests for SetupService: Root Admin Creation and Company Creation.

Tests Properties 4 and 5 from the setup-wizard design document:
- Property 4: Root Admin Creation Preserves Identity
- Property 5: Company Creation Preserves Fields

These tests use a real in-memory SQLite database to validate the service layer
behavior across many randomly generated inputs.

**Validates: Requirements 3.1, 3.6, 4.1**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Properties 4, 5)
    - Requirements: .kiro/specs/setup-wizard/requirements.md
"""

import asyncio
import re
import string
from unittest.mock import patch

import bcrypt as _bcrypt_lib
import hypothesis.strategies as st
from hypothesis import given, settings
from jose import jwt
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base
from alcoabase.schemas.setup import CompanySetupCreate, RootAdminCreate
from alcoabase.services.setup_service import JWT_ALGORITHM, SetupService


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

# Character pools for generating valid passwords
UPPERCASE = string.ascii_uppercase
LOWERCASE = string.ascii_lowercase
DIGITS = string.digits
SPECIAL = "!@#$%^&*()-_=+[]{}|;:',.<>?/~`"

# Valid username characters (alphanumeric + underscore)
USERNAME_CHARS = string.ascii_lowercase + string.digits + "_"


@st.composite
def st_valid_password(draw: st.DrawFn) -> str:
    """Generate a random password satisfying the GxP password policy.

    Policy: min 12 chars, at least one uppercase, one lowercase,
    one digit, one special character. Max 50 chars to keep tests fast.
    """
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
    """Generate a valid full name: 1-100 chars, letters and spaces."""
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
    # Ensure it doesn't start/end with whitespace
    result = "".join(name).strip()
    if not result:
        return "TestCompany"
    return result


@st.composite
def st_valid_slug(draw: st.DrawFn) -> str:
    """Generate a valid slug: lowercase letters, digits, hyphens."""
    # Generate 1-3 segments separated by hyphens
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
# Property 4: Root Admin Creation Preserves Identity
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 4: Root Admin Creation Preserves Identity
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_root_admin_creation_preserves_identity(data: st.DataObject) -> None:
    """For any valid root admin creation input, the created user record SHALL
    have matching username, email, and full_name fields, and the returned JWT
    access token SHALL decode to a payload whose subject identifies the
    created user.

    **Validates: Requirements 3.1, 3.6**
    """
    username = data.draw(st_valid_username(), label="username")
    email = data.draw(st_valid_email(), label="email")
    password = data.draw(st_valid_password(), label="password")
    full_name = data.draw(st_valid_full_name(), label="full_name")

    test_secret_key = "test-secret-key-for-property-tests"

    async def _test():
        engine, session_factory = await _create_test_db()
        try:
            async with session_factory() as session:
                # Mock get_settings to provide a test secret key
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = test_secret_key
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    service = SetupService(session)
                    admin_data = RootAdminCreate(
                        username=username,
                        email=email,
                        password=password,
                        full_name=full_name,
                    )

                    result = await service.create_root_admin(admin_data)
                    await session.commit()

                # Verify result fields match input
                assert result.username == username, (
                    f"Expected username '{username}', got '{result.username}'"
                )

                # Verify user in DB has matching email and full_name
                from sqlalchemy import select

                from alcoabase.models.user import User

                async with session_factory() as verify_session:
                    stmt = select(User).where(User.id == result.user_id)
                    db_result = await verify_session.execute(stmt)
                    user = db_result.scalar_one()

                    assert user.email == email, (
                        f"Expected email '{email}', got '{user.email}'"
                    )
                    assert user.full_name == full_name, (
                        f"Expected full_name '{full_name}', got '{user.full_name}'"
                    )
                    assert user.username == username, (
                        f"Expected username '{username}', got '{user.username}'"
                    )

                # Verify JWT decodes to correct subject
                decoded = jwt.decode(
                    result.access_token,
                    test_secret_key,
                    algorithms=[JWT_ALGORITHM],
                )
                assert decoded["sub"] == str(result.user_id), (
                    f"JWT sub '{decoded['sub']}' does not match "
                    f"user_id '{result.user_id}'"
                )
        finally:
            await engine.dispose()

    _run_async(_test())


# ---------------------------------------------------------------------------
# Property 5: Company Creation Preserves Fields
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 5: Company Creation Preserves Fields
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_company_creation_preserves_fields(data: st.DataObject) -> None:
    """For any valid company creation input, the created company record SHALL
    have matching display_name, slug, and regulatory_framework fields.

    **Validates: Requirements 4.1**
    """
    display_name = data.draw(st_valid_display_name(), label="display_name")
    # Decide whether to provide an explicit slug or let it be auto-generated
    use_explicit_slug = data.draw(st.booleans(), label="use_explicit_slug")
    slug = data.draw(st_valid_slug(), label="slug") if use_explicit_slug else None
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

                    # First create a root admin (needed for admin_id)
                    admin_data = RootAdminCreate(
                        username="setupadmin",
                        email="admin@testcompany.com",
                        password="ValidP@ss1234!",
                        full_name="Setup Admin",
                    )
                    admin_result = await service.create_root_admin(admin_data)

                    # Now create the company
                    company_data = CompanySetupCreate(
                        display_name=display_name,
                        slug=slug,
                        regulatory_framework=regulatory_framework,
                    )
                    result = await service.create_initial_company(
                        company_data, admin_result.user_id
                    )
                    await session.commit()

                # Verify result fields match input
                assert result.display_name == display_name, (
                    f"Expected display_name '{display_name}', "
                    f"got '{result.display_name}'"
                )

                # Verify slug: if explicit slug provided, it should match;
                # if auto-generated, it should be a valid slug
                if use_explicit_slug:
                    assert result.slug == slug, (
                        f"Expected slug '{slug}', got '{result.slug}'"
                    )
                else:
                    # Auto-generated slug should be valid
                    slug_pattern = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                    assert slug_pattern.match(result.slug), (
                        f"Auto-generated slug '{result.slug}' is not valid"
                    )

                # Verify company in DB has matching fields
                from sqlalchemy import select

                from alcoabase.models.company import Company

                async with session_factory() as verify_session:
                    stmt = select(Company).where(
                        Company.id == result.company_id
                    )
                    db_result = await verify_session.execute(stmt)
                    company = db_result.scalar_one()

                    assert company.display_name == display_name, (
                        f"DB display_name '{company.display_name}' "
                        f"does not match input '{display_name}'"
                    )
                    assert company.regulatory_framework == regulatory_framework, (
                        f"DB regulatory_framework "
                        f"'{company.regulatory_framework}' does not match "
                        f"input '{regulatory_framework}'"
                    )
                    if use_explicit_slug:
                        assert company.slug == slug, (
                            f"DB slug '{company.slug}' does not match "
                            f"input '{slug}'"
                        )
                    else:
                        assert slug_pattern.match(company.slug), (
                            f"DB auto-generated slug '{company.slug}' "
                            f"is not valid"
                        )
        finally:
            await engine.dispose()

    _run_async(_test())
