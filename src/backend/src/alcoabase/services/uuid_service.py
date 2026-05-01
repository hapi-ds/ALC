"""UUID generation service for Document-UUIDs and Field-UUIDs.

Provides two UUID formats used throughout AlcoaBase:
- Document-UUID: YYYY-NNNNN format using PostgreSQL year-based sequences
- Field-UUID: FLD-XXXXXXXX format using Python uuid4 hex prefix

References:
    - Design doc Section 2: UUID Generation Service
    - Requirements 1.1, 3.2: Document-UUID and Field-UUID assignment
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class UUIDService:
    """Service for generating unique identifiers for documents and fields.

    Document-UUIDs use a PostgreSQL sequence per year to guarantee
    uniqueness and sequential ordering within each calendar year.

    Field-UUIDs use Python's uuid4 for random hex identifiers that
    are unique within a template context.
    """

    async def generate_document_uuid(self, session: AsyncSession) -> str:
        """Generate a Document-UUID in YYYY-NNNNN format.

        Uses a PostgreSQL sequence named `doc_uuid_seq_{year}` to produce
        monotonically increasing, gap-free identifiers per calendar year.
        Creates the sequence if it does not already exist.

        Args:
            session: An active SQLAlchemy async session for executing
                the sequence query.

        Returns:
            A string in the format "YYYY-NNNNN" (e.g., "2026-00001").

        Raises:
            SQLAlchemyError: If the database query fails.
        """
        year = datetime.now(UTC).year
        seq_name = f"doc_uuid_seq_{year}"

        # Create the sequence if it doesn't exist (idempotent)
        await session.execute(
            text(f"CREATE SEQUENCE IF NOT EXISTS {seq_name} START WITH 1 INCREMENT BY 1")
        )

        # Get the next value from the year-specific sequence
        result = await session.execute(text(f"SELECT nextval('{seq_name}')"))
        seq = result.scalar_one()

        return f"{year}-{seq:05d}"

    def generate_field_uuid(self) -> str:
        """Generate a Field-UUID in FLD-XXXXXXXX format.

        Uses the first 8 hex characters of a uuid4, uppercased,
        prefixed with "FLD-". This method is pure Python and does
        not require a database session.

        Returns:
            A string in the format "FLD-XXXXXXXX" (e.g., "FLD-A1B2C3D4").
        """
        return f"FLD-{uuid4().hex[:8].upper()}"
