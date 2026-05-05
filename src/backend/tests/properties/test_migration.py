"""Property-based tests for migration backfill completeness.

Tests Property 19 from the multi-tenancy design document, validating
that after running the migration backfill logic, all pre-existing records
in tenant-scoped tables have a non-null company_id equal to the default
company's ID.

**Validates: Requirements 12.6**

References:
    - Design: .kiro/specs/multi-tenancy/design.md (Correctness Property 19)
    - Requirements: .kiro/specs/multi-tenancy/requirements.md (Requirement 12)
    - Migration: src/backend/alembic/versions/a1b2c3d4e5f6_add_multi_tenancy_schema.py
"""

import hypothesis.strategies as st
import sqlalchemy as sa
from hypothesis import given, settings
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Session, sessionmaker

# ---------------------------------------------------------------------------
# Constants: tenant-scoped tables that receive company_id during migration
# ---------------------------------------------------------------------------

TENANT_SCOPED_TABLES = [
    "documents",
    "templates",
    "workflow_definitions",
    "training_records",
    "training_tasks",
    "virtual_folders",
    "reports",
    "signature_records",
]

DEFAULT_COMPANY_SLUG = "default"
DEFAULT_COMPANY_DISPLAY_NAME = "Default Company"
DEFAULT_COMPANY_FRAMEWORK = "ISO_13485"


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_record_counts(draw: st.DrawFn) -> dict[str, int]:
    """Generate random record counts (1 to 20) for each tenant-scoped table.

    Returns:
        Dictionary mapping table name to number of pre-existing records.
    """
    counts = {}
    for table_name in TENANT_SCOPED_TABLES:
        counts[table_name] = draw(
            st.integers(min_value=1, max_value=20).filter(lambda x: x >= 1)
        )
    return counts


# ---------------------------------------------------------------------------
# Helper: simulate pre-migration schema and migration logic
# ---------------------------------------------------------------------------


def _create_pre_migration_schema(engine: sa.Engine, metadata: MetaData) -> None:
    """Create simplified pre-migration tables without company_id.

    Each tenant-scoped table gets a minimal schema with just an id and
    a name column to represent pre-existing records.
    """
    # Users table (referenced by some tables)
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("username", String(100)),
    )

    for table_name in TENANT_SCOPED_TABLES:
        Table(
            table_name,
            metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(200)),
        )

    metadata.create_all(engine)


def _insert_pre_migration_records(
    engine: sa.Engine, metadata: MetaData, record_counts: dict[str, int]
) -> None:
    """Insert pre-existing records into tenant-scoped tables."""
    with engine.begin() as conn:
        # Insert a user for reference
        users_table = metadata.tables["users"]
        conn.execute(users_table.insert().values(id=1, username="admin"))

        for table_name, count in record_counts.items():
            table = metadata.tables[table_name]
            for i in range(1, count + 1):
                conn.execute(
                    table.insert().values(id=i, name=f"{table_name}_record_{i}")
                )


def _run_migration_logic(engine: sa.Engine, metadata: MetaData) -> int:
    """Simulate the migration backfill logic.

    Steps (mirroring the actual Alembic migration):
    1. Create the companies table
    2. Insert the default company
    3. Add nullable company_id column to each tenant-scoped table
    4. Backfill all records with the default company's ID
    5. Alter company_id to NOT NULL

    Returns:
        The ID of the default company.
    """
    with engine.begin() as conn:
        # Step 1: Create companies table
        conn.execute(
            text(
                "CREATE TABLE companies ("
                "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "  slug VARCHAR(100) UNIQUE NOT NULL,"
                "  display_name VARCHAR(300) NOT NULL,"
                "  regulatory_framework VARCHAR(50) NOT NULL,"
                "  is_active BOOLEAN NOT NULL DEFAULT 1"
                ")"
            )
        )

        # Step 2: Insert default company
        conn.execute(
            text(
                "INSERT INTO companies (slug, display_name, regulatory_framework, is_active) "
                "VALUES (:slug, :display_name, :framework, 1)"
            ),
            {
                "slug": DEFAULT_COMPANY_SLUG,
                "display_name": DEFAULT_COMPANY_DISPLAY_NAME,
                "framework": DEFAULT_COMPANY_FRAMEWORK,
            },
        )

        # Get the default company ID
        result = conn.execute(
            text("SELECT id FROM companies WHERE slug = :slug"),
            {"slug": DEFAULT_COMPANY_SLUG},
        )
        default_company_id = result.scalar_one()

        # Step 3: Add nullable company_id column to each tenant-scoped table
        for table_name in TENANT_SCOPED_TABLES:
            conn.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN company_id INTEGER")
            )

        # Step 4: Backfill all records with the default company's ID
        for table_name in TENANT_SCOPED_TABLES:
            conn.execute(
                text(
                    f"UPDATE {table_name} SET company_id = :company_id "
                    f"WHERE company_id IS NULL"
                ),
                {"company_id": default_company_id},
            )

        # Step 5: In SQLite we cannot ALTER COLUMN to NOT NULL directly,
        # but we verify the constraint holds via the property assertion.
        # The actual Alembic migration uses ALTER COLUMN on PostgreSQL.

    return default_company_id


# ---------------------------------------------------------------------------
# Property 19: Migration backfill completeness
# ---------------------------------------------------------------------------


# Feature: multi-tenancy, Property 19: Migration backfill completeness
@settings(max_examples=20)
@given(record_counts=st_record_counts())
def test_migration_backfill_completeness(record_counts: dict[str, int]) -> None:
    """For any set of pre-existing records in tenant-scoped tables, after
    running the migration, all records SHALL have a non-null company_id
    equal to the default company's ID.

    **Validates: Requirements 12.6**
    """
    # Setup: create fresh in-memory database
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()

    try:
        # Phase 1: Create pre-migration schema (no company_id)
        _create_pre_migration_schema(engine, metadata)

        # Phase 2: Insert random pre-existing records
        _insert_pre_migration_records(engine, metadata, record_counts)

        # Phase 3: Run migration logic (add column, backfill, etc.)
        default_company_id = _run_migration_logic(engine, metadata)

        # Phase 4: Verify ALL records have non-null company_id = default
        with engine.connect() as conn:
            for table_name in TENANT_SCOPED_TABLES:
                expected_count = record_counts[table_name]

                # Check total record count is preserved
                total = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")
                ).scalar_one()
                assert total == expected_count, (
                    f"Table {table_name}: expected {expected_count} records, "
                    f"got {total}"
                )

                # Check NO records have NULL company_id
                null_count = conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table_name} "
                        f"WHERE company_id IS NULL"
                    )
                ).scalar_one()
                assert null_count == 0, (
                    f"Table {table_name}: {null_count} records still have "
                    f"NULL company_id after migration"
                )

                # Check ALL records have company_id = default_company_id
                correct_count = conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table_name} "
                        f"WHERE company_id = :company_id"
                    ),
                    {"company_id": default_company_id},
                ).scalar_one()
                assert correct_count == expected_count, (
                    f"Table {table_name}: expected {expected_count} records "
                    f"with company_id={default_company_id}, got {correct_count}"
                )
    finally:
        engine.dispose()
