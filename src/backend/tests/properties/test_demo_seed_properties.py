"""Property-based tests for Demo Data Tagging Invariant.

Tests Property 7 from the setup-wizard design document:
- Property 7: Demo Data Tagging Invariant

For any set of records created during demo data seeding, every record SHALL
have `is_demo_data=True`, and no record created outside of demo seeding SHALL
have this flag set.

**Validates: Requirements 6.4**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Property 7)
    - Requirements: .kiro/specs/setup-wizard/requirements.md
"""

import asyncio
from unittest.mock import patch

import bcrypt as _bcrypt_lib
import hypothesis.strategies as st
from hypothesis import given, settings
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import configure_mappers

from alcoabase.database import Base
from alcoabase.models.document import Document
from alcoabase.models.template import Template
from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.models.workflow import WorkflowDefinition
from alcoabase.schemas.setup import (
    AIModeConfig,
    CompanySetupCreate,
    RootAdminCreate,
)
from alcoabase.services.setup_service import SetupService

# Ensure sqlalchemy_continuum tables (transaction, *_version) are registered
# in Base.metadata before create_all is called. This is required because
# Document, Template use AuditMixin which triggers continuum's before_flush hook.
configure_mappers()


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
# Property 7: Demo Data Tagging Invariant
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 7: Demo Data Tagging Invariant
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_demo_data_tagging_invariant(data: st.DataObject) -> None:
    """For any set of records created during demo data seeding, every record
    SHALL have `is_demo_data=True`, and no record created outside of demo
    seeding SHALL have this flag set.

    **Validates: Requirements 6.4**
    """
    regulatory_framework = data.draw(st_regulatory_framework(), label="regulatory_framework")

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

                    # Step 1: Create root admin
                    admin_data = RootAdminCreate(
                        username="demoadmin",
                        email="demo@testcompany.com",
                        password="ValidP@ss1234!",
                        full_name="Demo Admin",
                    )
                    admin_result = await service.create_root_admin(admin_data)

                    # Step 2: Create company with random regulatory framework
                    company_data = CompanySetupCreate(
                        display_name="Demo Test Company",
                        slug="demo-test-company",
                        regulatory_framework=regulatory_framework,
                    )
                    await service.create_initial_company(
                        company_data, admin_result.user_id
                    )

                    # Step 3: Configure AI mode (required before complete_setup)
                    ai_data = AIModeConfig(mode="mock")
                    await service.configure_ai_mode(ai_data)

                    # Step 4: Complete setup with seed_demo=True
                    await service.complete_setup(
                        admin_id=admin_result.user_id, seed_demo=True
                    )
                    await session.commit()

            # Verify all demo data records have is_demo_data=True
            async with session_factory() as verify_session:
                # Check Documents
                docs_result = await verify_session.execute(select(Document))
                documents = docs_result.scalars().all()
                for doc in documents:
                    assert doc.is_demo_data is True, (
                        f"Document '{doc.title}' does not have is_demo_data=True"
                    )

                # Check Templates
                templates_result = await verify_session.execute(select(Template))
                templates = templates_result.scalars().all()
                for tmpl in templates:
                    assert tmpl.is_demo_data is True, (
                        f"Template '{tmpl.name}' does not have is_demo_data=True"
                    )

                # Check VirtualFolders
                folders_result = await verify_session.execute(select(VirtualFolder))
                folders = folders_result.scalars().all()
                for folder in folders:
                    assert folder.is_demo_data is True, (
                        f"VirtualFolder '{folder.name}' does not have is_demo_data=True"
                    )

                # Check WorkflowDefinitions
                workflows_result = await verify_session.execute(
                    select(WorkflowDefinition)
                )
                workflows = workflows_result.scalars().all()
                for wf in workflows:
                    assert wf.is_demo_data is True, (
                        f"WorkflowDefinition '{wf.name}' does not have is_demo_data=True"
                    )

                # Verify that at least some demo data was created
                assert len(documents) > 0, "No demo documents were created"
                assert len(templates) > 0, "No demo templates were created"
                assert len(folders) > 0, "No demo virtual folders were created"
                assert len(workflows) > 0, "No demo workflow definitions were created"

        finally:
            await engine.dispose()

    _run_async(_test())
