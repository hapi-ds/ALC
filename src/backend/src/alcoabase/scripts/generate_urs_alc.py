"""ALC URS Generation Script.

Generates the Enhanced User Requirement Specifications (URS) document,
uploads it into the ALC corporate governance environment, applies tags
and the governance workflow, and supports versioning on re-execution.

All operations execute within a single database transaction. On success
the transaction is committed and the URSGenerationReport is printed to
stdout as JSON. On failure the transaction is rolled back and error
details are printed to stderr.

Usage:
    uv run python -m alcoabase.scripts.generate_urs_alc

Exit codes:
    0 — Success (URSGenerationReport printed to stdout as JSON)
    1 — Failure (error details printed to stderr)

References:
    - Design doc: .kiro/specs/Step_8-3_urs-alc-corporate/design.md
    - Requirements: 6.1, 6.5
"""

import asyncio
import sys

from alcoabase.database import init_db
from alcoabase.services.urs_generator_service import URSGeneratorService


async def main() -> None:
    """Execute the ALC URS generation sequence.

    Creates an async database session, runs the full URS generator service
    within a single transaction, and handles commit/rollback based on outcome.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from alcoabase.database import get_engine

    # Initialize the database engine
    await init_db()
    engine = get_engine()

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        try:
            service = URSGeneratorService(session)
            report = await service.execute()
            await session.commit()

            # Print URSGenerationReport as JSON to stdout
            print(report.model_dump_json(indent=2))

        except Exception as exc:
            await session.rollback()
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

    # Dispose the engine to cleanly close connections
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
