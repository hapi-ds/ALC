"""Property-based tests for Setup Progress Accuracy.

Tests Property 8 from the setup-wizard design document:
- Property 8: Setup Progress Accuracy

For any combination of completed setup steps, the progress endpoint SHALL
return a response where each boolean field matches the actual database state.

**Validates: Requirements 8.1**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Property 8)
    - Requirements: .kiro/specs/setup-wizard/requirements.md
"""

import asyncio
from unittest.mock import patch

import bcrypt as _bcrypt_lib
import hypothesis.strategies as st
from hypothesis import given, settings
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alcoabase.database import Base
from alcoabase.models.setup_status import SetupStatus
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
# Property 8: Setup Progress Accuracy
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 8: Setup Progress Accuracy
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_setup_progress_accuracy(data: st.DataObject) -> None:
    """For any combination of completed setup steps (admin_created,
    company_created, ai_mode_configured, demo_data_seeded), the progress
    endpoint SHALL return a response where each boolean field matches the
    actual database state.

    **Validates: Requirements 8.1**
    """
    admin_created = data.draw(st.booleans(), label="admin_created")
    company_created = data.draw(st.booleans(), label="company_created")
    ai_mode_configured = data.draw(st.booleans(), label="ai_mode_configured")
    demo_data_seeded = data.draw(st.booleans(), label="demo_data_seeded")
    is_complete = data.draw(st.booleans(), label="is_complete")

    test_secret_key = "test-secret-key-for-property-tests"

    async def _test():
        engine, session_factory = await _create_test_db()
        try:
            # Directly create a SetupStatus record with random boolean values
            async with session_factory() as session:
                status = SetupStatus(
                    admin_created=admin_created,
                    company_created=company_created,
                    ai_mode_configured=ai_mode_configured,
                    demo_data_seeded=demo_data_seeded,
                    is_complete=is_complete,
                )
                session.add(status)
                await session.commit()

            # Now call service.get_status() and verify each field matches
            async with session_factory() as session:
                with patch(
                    "alcoabase.services.setup_service.get_settings"
                ) as mock_settings:
                    mock_settings.return_value.secret_key = test_secret_key
                    mock_settings.return_value.vllm_base_url = "http://localhost:8000"

                    service = SetupService(session)
                    progress = await service.get_status()

                # Verify each field matches the DB state
                assert progress.admin_created == admin_created, (
                    f"Expected admin_created={admin_created}, "
                    f"got {progress.admin_created}"
                )
                assert progress.company_created == company_created, (
                    f"Expected company_created={company_created}, "
                    f"got {progress.company_created}"
                )
                assert progress.ai_mode_configured == ai_mode_configured, (
                    f"Expected ai_mode_configured={ai_mode_configured}, "
                    f"got {progress.ai_mode_configured}"
                )
                assert progress.demo_data_seeded == demo_data_seeded, (
                    f"Expected demo_data_seeded={demo_data_seeded}, "
                    f"got {progress.demo_data_seeded}"
                )
                assert progress.is_complete == is_complete, (
                    f"Expected is_complete={is_complete}, "
                    f"got {progress.is_complete}"
                )

        finally:
            await engine.dispose()

    _run_async(_test())
