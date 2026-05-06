"""Ensure all tables exist (including SQLAlchemy-Continuum tables).

Alembic migrations don't always create Continuum's internal tables
(transaction, *_version). This script runs metadata.create_all after
configure_mappers() to fill in any gaps.

Usage:
    python -m scripts.ensure_tables
"""

import asyncio

from sqlalchemy.orm import configure_mappers

from alcoabase.database import Base, init_db, get_engine
from alcoabase.models import *  # noqa: F401, F403 — registers all models


async def main() -> None:
    """Create any missing tables in the database."""
    configure_mappers()
    await init_db()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("All tables ensured.")


if __name__ == "__main__":
    asyncio.run(main())
