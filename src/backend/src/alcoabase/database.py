"""SQLAlchemy 2.0 async database engine, session factory, and Continuum setup.

This module provides:
- Async engine creation with asyncpg driver and connection pooling
- Async session factory for FastAPI dependency injection
- DeclarativeBase for all ORM models
- SQLAlchemy-Continuum plugin initialization for automatic audit versioning
- Lifespan management functions (init_db / close_db)

Usage:
    from alcoabase.database import get_db_session, Base, init_db, close_db

    # In FastAPI lifespan:
    async with lifespan(app):
        await init_db()
        yield
        await close_db()

    # In route handlers:
    @router.get("/items")
    async def list_items(session: AsyncSession = Depends(get_db_session)):
        ...

References:
    - SQLAlchemy 2.0 async: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
    - SQLAlchemy-Continuum: https://sqlalchemy-continuum.readthedocs.io/
"""

from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from alcoabase.config import get_settings

# ---------------------------------------------------------------------------
# Naming convention for constraints (Alembic auto-generation friendly)
# ---------------------------------------------------------------------------

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# ---------------------------------------------------------------------------
# Declarative Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    All models should inherit from this class. Models requiring audit
    versioning should also inherit from AuditMixin (defined in
    alcoabase.models.audit).

    Attributes:
        metadata: SQLAlchemy MetaData with consistent naming conventions
            for constraints, enabling reliable Alembic auto-generation.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------------------------------------------------------------------------
# SQLAlchemy-Continuum Plugin Initialization
# ---------------------------------------------------------------------------
# Continuum hooks into SQLAlchemy mapper events at the sync level.
# It must be initialized via make_versioned() BEFORE models are imported.
# The actual database operations still use the async engine.
#
# Note: make_versioned() is called here so that any model importing Base
# after this module is loaded will have Continuum's mapper listeners active.
# Models opt-in to versioning by setting __versioned__ = {} (via AuditMixin).

try:
    from sqlalchemy_continuum import make_versioned
    from sqlalchemy_continuum.plugins import PropertyModTrackerPlugin

    # PropertyModTrackerPlugin tracks which columns were modified per transaction.
    # We avoid FlaskPlugin since we use FastAPI; instead we'll inject user info
    # via the transaction context in audit middleware.
    make_versioned(
        plugins=[PropertyModTrackerPlugin()],
        user_cls=None,  # User tracking handled via audit middleware, not Continuum's built-in
    )
    _continuum_initialized = True
except ImportError:
    # Graceful degradation if sqlalchemy-continuum is not installed
    # (e.g., during minimal test environments)
    _continuum_initialized = False


# ---------------------------------------------------------------------------
# Engine and Session Factory (module-level singletons, initialized lazily)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _create_engine() -> AsyncEngine:
    """Create the async SQLAlchemy engine with connection pool configuration.

    Returns:
        AsyncEngine: Configured async engine using asyncpg driver.

    The connection pool is configured for production workloads:
        - pool_size: Number of persistent connections (default 10)
        - max_overflow: Additional connections allowed beyond pool_size (default 20)
        - pool_pre_ping: Verify connections are alive before use (handles DB restarts)
        - pool_recycle: Recycle connections after 1 hour to avoid stale connections
    """
    settings = get_settings()

    engine = create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,
    )
    return engine


def _create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the async session factory bound to the given engine.

    Args:
        engine: The async SQLAlchemy engine to bind sessions to.

    Returns:
        async_sessionmaker: Factory for creating AsyncSession instances.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


# ---------------------------------------------------------------------------
# Lifespan Management
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Initialize the database engine and session factory.

    Call this during application startup (FastAPI lifespan). Creates the
    async engine and session factory as module-level singletons.

    Raises:
        RuntimeError: If init_db() has already been called without a
            corresponding close_db().
    """
    global _engine, _session_factory

    if _engine is not None:
        raise RuntimeError(
            "Database already initialized. Call close_db() before re-initializing."
        )

    _engine = _create_engine()
    _session_factory = _create_session_factory(_engine)


async def close_db() -> None:
    """Close the database engine and release all pooled connections.

    Call this during application shutdown (FastAPI lifespan). Disposes
    the engine and resets module-level singletons.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


# ---------------------------------------------------------------------------
# FastAPI Dependency
# ---------------------------------------------------------------------------


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session as a FastAPI dependency.

    Yields an AsyncSession that is automatically committed on success
    or rolled back on exception. The session is closed after the request.

    Yields:
        AsyncSession: An active database session for the request lifecycle.

    Raises:
        RuntimeError: If the database has not been initialized via init_db().

    Example:
        @router.get("/items")
        async def list_items(
            session: AsyncSession = Depends(get_db_session),
        ) -> list[Item]:
            result = await session.execute(select(Item))
            return result.scalars().all()
    """
    if _session_factory is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Utility accessors
# ---------------------------------------------------------------------------


def get_engine() -> AsyncEngine:
    """Return the current async engine instance.

    Returns:
        AsyncEngine: The active database engine.

    Raises:
        RuntimeError: If the database has not been initialized.
    """
    if _engine is None:
        raise RuntimeError(
            "Database not initialized. Call init_db() during application startup."
        )
    return _engine


def is_continuum_initialized() -> bool:
    """Check whether SQLAlchemy-Continuum was successfully initialized.

    Returns:
        bool: True if make_versioned() was called successfully.
    """
    return _continuum_initialized
