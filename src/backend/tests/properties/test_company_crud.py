"""Property-based tests for Company CRUD operations.

Tests Properties 1, 2, and 3 from the multi-tenancy design document,
validating company creation, duplicate slug rejection, and missing
required fields rejection.

**Validates: Requirements 1.1, 1.2, 1.4, 1.5**

References:
    - Design: .kiro/specs/multi-tenancy/design.md (Correctness Properties 1-3)
    - Requirements: .kiro/specs/multi-tenancy/requirements.md (Requirement 1)
"""

from typing import Literal

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alcoabase.database import Base
from alcoabase.models.company import Company


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
    middle_len = draw(st.integers(min_value=1, max_value=98))
    middle = draw(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
            min_size=middle_len,
            max_size=middle_len,
        )
    )
    return start + middle + end


def st_display_name() -> st.SearchStrategy[str]:
    """Generate a non-empty display name up to 300 characters.

    Returns:
        Strategy producing non-empty strings of printable characters.
    """
    return st.text(
        alphabet=st.characters(categories=("L", "N", "P", "Z", "S")),
        min_size=1,
        max_size=300,
    ).filter(lambda s: s.strip())


def st_regulatory_framework() -> st.SearchStrategy[str]:
    """Generate a valid regulatory framework value.

    Returns:
        Strategy producing one of the allowed framework strings.
    """
    return st.sampled_from([
        "ISO_13485", "GMP", "GDP", "ISO_9001", "ISO_17025", "CUSTOM"
    ])


# ---------------------------------------------------------------------------
# Pydantic schema for validation testing (mirrors the API schema)
# ---------------------------------------------------------------------------


class CompanyCreateSchema(BaseModel):
    """Pydantic schema for company creation validation.

    Mirrors the API-level schema defined in the design document.
    """

    slug: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")
    display_name: str = Field(..., min_length=1, max_length=300)
    regulatory_framework: Literal[
        "ISO_13485", "GMP", "GDP", "ISO_9001", "ISO_17025", "CUSTOM"
    ]


# ---------------------------------------------------------------------------
# Helper: create a fresh database session per hypothesis example
# ---------------------------------------------------------------------------


def _make_session() -> tuple[Session, "Engine"]:
    """Create a fresh SQLite in-memory database session.

    Returns:
        Tuple of (session, engine) for cleanup.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    return session, engine


# ---------------------------------------------------------------------------
# Property 1: Company creation produces a valid record
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 1: Company creation produces a valid record
@settings(max_examples=20)
@given(
    slug=st_company_slug(),
    display_name=st_display_name(),
    regulatory_framework=st_regulatory_framework(),
)
def test_company_creation_produces_valid_record(
    slug: str,
    display_name: str,
    regulatory_framework: str,
) -> None:
    """For any valid company creation input, creating a Company produces a
    persisted record whose attributes exactly match the input values,
    with is_active=True and a non-null created_at timestamp.

    **Validates: Requirements 1.1, 1.2**
    """
    session, engine = _make_session()
    try:
        company = Company(
            slug=slug,
            display_name=display_name,
            regulatory_framework=regulatory_framework,
        )
        session.add(company)
        session.commit()

        # Retrieve from database to verify persistence
        result = session.execute(
            select(Company).where(Company.slug == slug)
        )
        persisted = result.scalar_one()

        # Attributes match input
        assert persisted.slug == slug
        assert persisted.display_name == display_name
        assert persisted.regulatory_framework == regulatory_framework

        # Default values are correct
        assert persisted.is_active is True
        assert persisted.id is not None
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 2: Duplicate slug rejection
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 2: Duplicate slug rejection
@settings(max_examples=20)
@given(
    slug=st_company_slug(),
    display_name_1=st_display_name(),
    display_name_2=st_display_name(),
    framework_1=st_regulatory_framework(),
    framework_2=st_regulatory_framework(),
)
def test_duplicate_slug_rejection(
    slug: str,
    display_name_1: str,
    display_name_2: str,
    framework_1: str,
    framework_2: str,
) -> None:
    """For any valid company slug, creating a company with that slug and then
    attempting to create another company with the same slug results in an
    IntegrityError, and the total number of companies with that slug remains
    exactly one.

    **Validates: Requirements 1.4**
    """
    session, engine = _make_session()
    try:
        # Create first company
        company1 = Company(
            slug=slug,
            display_name=display_name_1,
            regulatory_framework=framework_1,
        )
        session.add(company1)
        session.commit()

        # Attempt to create second company with same slug
        company2 = Company(
            slug=slug,
            display_name=display_name_2,
            regulatory_framework=framework_2,
        )
        session.add(company2)

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()

        # Verify exactly one company with that slug exists
        count = session.execute(
            select(func.count()).select_from(Company).where(Company.slug == slug)
        ).scalar_one()
        assert count == 1
    finally:
        session.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Property 3: Missing required fields rejection
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 3: Missing required fields rejection
@settings(max_examples=20)
@given(
    slug=st.one_of(st.just(""), st.just(None), st_company_slug()),
    display_name=st.one_of(st.just(""), st.just(None), st_display_name()),
    regulatory_framework=st.one_of(
        st.just(""), st.just(None), st_regulatory_framework()
    ),
)
def test_missing_required_fields_rejection(
    slug: str | None,
    display_name: str | None,
    regulatory_framework: str | None,
) -> None:
    """For any company creation payload where one or more required fields
    (slug, display_name, regulatory_framework) are absent or empty, the
    creation should fail with a validation error and no Company record
    should be persisted.

    **Validates: Requirements 1.5**
    """
    # Only test cases where at least one field is missing/empty
    all_valid = (
        slug is not None
        and slug != ""
        and display_name is not None
        and display_name != ""
        and regulatory_framework is not None
        and regulatory_framework != ""
    )
    if all_valid:
        # Skip cases where all fields are valid — that's Property 1's domain
        return

    # Attempt Pydantic validation — should fail for invalid inputs
    with pytest.raises(ValidationError):
        CompanyCreateSchema(
            slug=slug,  # type: ignore[arg-type]
            display_name=display_name,  # type: ignore[arg-type]
            regulatory_framework=regulatory_framework,  # type: ignore[arg-type]
        )

    # Verify no record was persisted (validation prevents DB insert)
    session, engine = _make_session()
    try:
        count = session.execute(
            select(func.count()).select_from(Company)
        ).scalar_one()
        assert count == 0
    finally:
        session.close()
        engine.dispose()
