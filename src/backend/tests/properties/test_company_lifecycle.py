"""Property-based tests for company lifecycle operations.

Tests Property 16 from the multi-tenancy design document, validating that
audit trail entries (represented as tenant-scoped documents with AuditMixin)
retain their company_id and content after company deactivation.

**Validates: Requirements 13.3**

References:
    - Design: .kiro/specs/multi-tenancy/design.md (Correctness Property 16)
    - Requirements: .kiro/specs/multi-tenancy/requirements.md (Requirement 13)
"""

import hypothesis.strategies as st
from hypothesis import given, settings
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, configure_mappers, sessionmaker

from alcoabase.database import Base
from alcoabase.models.company import Company
from alcoabase.models.document import Document
from alcoabase.models.user import User

# Ensure sqlalchemy_continuum tables are registered in Base.metadata
configure_mappers()


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_company_slug(draw: st.DrawFn) -> str:
    """Generate a valid company slug matching ^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$.

    Returns:
        A URL-safe slug string between 3 and 100 characters.
    """
    start = draw(st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789")))
    end = draw(st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789")))
    middle_len = draw(st.integers(min_value=1, max_value=20))
    middle = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=middle_len,
            max_size=middle_len,
        )
    )
    return start + middle + end


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session() -> tuple[Session, "Engine"]:
    """Create a fresh SQLite in-memory database session with all tables.

    Returns:
        Tuple of (session, engine) for cleanup.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


def _create_user(session: Session, user_id: int) -> User:
    """Create and persist a test user.

    Args:
        session: Active database session.
        user_id: The user ID to assign.

    Returns:
        The persisted User instance.
    """
    user = User(
        id=user_id,
        username=f"user_{user_id}",
        email=f"user_{user_id}@test.local",
        hashed_password="hashed",
        full_name=f"Test User {user_id}",
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_company(
    session: Session, company_id: int, slug: str, is_active: bool = True
) -> Company:
    """Create and persist a test company.

    Args:
        session: Active database session.
        company_id: The company ID to assign.
        slug: Unique slug for the company.
        is_active: Whether the company is active.

    Returns:
        The persisted Company instance.
    """
    company = Company(
        id=company_id,
        slug=slug,
        display_name=f"Company {slug}",
        regulatory_framework="ISO_13485",
        is_active=is_active,
    )
    session.add(company)
    session.flush()
    return company


# ---------------------------------------------------------------------------
# Property 16: Audit trail entries retain company_id after deactivation
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 16: Audit trail entries retain company_id after deactivation
@settings(max_examples=20)
@given(
    slug=st_company_slug(),
    num_entries=st.integers(min_value=1, max_value=10),
)
def test_audit_trail_entries_retain_company_id_after_deactivation(
    slug: str,
    num_entries: int,
) -> None:
    """For any company with audit trail entries, after deactivation, the count
    and content of audit entries for that company SHALL remain unchanged.

    Audit trail entries are represented as Documents (which use AuditMixin).
    This test creates documents for a company, records their count and content,
    deactivates the company, and verifies the entries are unchanged.

    **Validates: Requirements 13.3**
    """
    session, engine = _make_session()
    try:
        user = _create_user(session, user_id=1)
        company = _create_company(session, company_id=1, slug=slug)

        # Create N documents (audit trail entries) for the company
        for i in range(1, num_entries + 1):
            doc = Document(
                id=i,
                document_uuid=f"2024-{i:05d}",
                title=f"Audit Entry {i}",
                folder_path="/audit",
                document_type="SOP",
                current_status="Approved",
                created_by=user.id,
                company_id=company.id,
            )
            session.add(doc)

        session.commit()

        # Record the count and content BEFORE deactivation
        entries_before = (
            session.execute(
                select(Document)
                .where(Document.company_id == company.id)
                .order_by(Document.id)
            )
            .scalars()
            .all()
        )
        count_before = len(entries_before)
        content_before = [
            (e.id, e.document_uuid, e.title, e.folder_path, e.document_type,
             e.current_status, e.created_by, e.company_id)
            for e in entries_before
        ]

        assert count_before == num_entries, (
            f"Expected {num_entries} entries before deactivation, "
            f"got {count_before}"
        )

        # Deactivate the company (set is_active=False)
        company.is_active = False
        session.commit()

        # Verify the company is deactivated
        refreshed_company = session.execute(
            select(Company).where(Company.id == company.id)
        ).scalar_one()
        assert refreshed_company.is_active is False

        # Query audit entries AFTER deactivation
        entries_after = (
            session.execute(
                select(Document)
                .where(Document.company_id == company.id)
                .order_by(Document.id)
            )
            .scalars()
            .all()
        )
        count_after = len(entries_after)
        content_after = [
            (e.id, e.document_uuid, e.title, e.folder_path, e.document_type,
             e.current_status, e.created_by, e.company_id)
            for e in entries_after
        ]

        # Count SHALL remain unchanged
        assert count_after == count_before, (
            f"Audit entry count changed after deactivation: "
            f"before={count_before}, after={count_after}"
        )

        # Content SHALL remain unchanged
        assert content_after == content_before, (
            "Audit entry content changed after company deactivation"
        )

        # Every entry still retains the original company_id
        for entry in entries_after:
            assert entry.company_id == company.id, (
                f"Entry {entry.id} lost company_id after deactivation: "
                f"expected {company.id}, got {entry.company_id}"
            )
    finally:
        session.close()
        engine.dispose()
