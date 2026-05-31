"""ALC Corporate Environment Seed Script.

Initializes the dedicated "ALC" company tenant within AlcoaBase's
multi-tenancy framework. Creates company entity, user pool, regulatory
configuration, governance folder structure, AI risk profile, agent
activations, and a governance workflow definition.

All operations execute within a single database transaction. On success
the transaction is committed and the SeedReport is printed to stdout as
JSON. On failure the transaction is rolled back and error details are
printed to stderr.

Usage:
    uv run python -m alcoabase.scripts.seed_alc_corporate

Exit codes:
    0 — Success (Seed_Report printed to stdout as JSON)
    1 — Failure (error details printed to stderr)

References:
    - Design doc: .kiro/specs/Step_8-2_alc-corporate-environment-setup/design.md
    - Requirements: 6.1, 6.5
"""

import asyncio
import sys

from alcoabase.database import init_db
from alcoabase.services.alc_seed_service import ALCSeedService


async def main() -> None:
    """Execute the ALC corporate environment seeding sequence.

    Creates an async database session, runs the full seed service within
    a single transaction, and handles commit/rollback based on outcome.
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
            service = ALCSeedService(session)
            report = await service.execute()
            await session.commit()

            # Print SeedReport as JSON to stdout
            print(report.model_dump_json(indent=2))

        except Exception as exc:
            await session.rollback()
            print(f"ALC corporate seed failed: {exc}", file=sys.stderr)
            sys.exit(1)

    # Dispose the engine to cleanly close connections
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
