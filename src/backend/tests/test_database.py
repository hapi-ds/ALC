"""Unit tests for alcoabase.database module."""

import pytest
import pytest_asyncio

import alcoabase.database as db_module
from alcoabase.database import (
    Base,
    close_db,
    get_db_session,
    get_engine,
    init_db,
    is_continuum_initialized,
)


class TestBase:
    """Tests for the DeclarativeBase class."""

    def test_base_has_naming_convention(self) -> None:
        """Base metadata should have constraint naming conventions for Alembic."""
        nc = Base.metadata.naming_convention
        assert "ix" in nc
        assert "uq" in nc
        assert "ck" in nc
        assert "fk" in nc
        assert "pk" in nc

    def test_base_is_declarative_base(self) -> None:
        """Base should be a proper DeclarativeBase subclass."""
        from sqlalchemy.orm import DeclarativeBase

        assert issubclass(Base, DeclarativeBase)


class TestContinuumInitialization:
    """Tests for SQLAlchemy-Continuum plugin initialization."""

    def test_continuum_is_initialized(self) -> None:
        """Continuum should be initialized when the package is available."""
        assert is_continuum_initialized() is True


class TestLifespanManagement:
    """Tests for init_db() and close_db() lifecycle functions."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_db(self) -> None:
        """Ensure database state is clean before and after each test."""
        db_module._engine = None
        db_module._session_factory = None
        yield
        if db_module._engine is not None:
            await db_module._engine.dispose()
        db_module._engine = None
        db_module._session_factory = None

    @pytest.mark.asyncio
    async def test_init_db_creates_engine_and_factory(self) -> None:
        """init_db() should create engine and session factory."""
        await init_db()

        assert db_module._engine is not None
        assert db_module._session_factory is not None

    @pytest.mark.asyncio
    async def test_init_db_raises_if_already_initialized(self) -> None:
        """init_db() should raise RuntimeError if called twice."""
        await init_db()

        with pytest.raises(RuntimeError, match="already initialized"):
            await init_db()

    @pytest.mark.asyncio
    async def test_close_db_disposes_engine(self) -> None:
        """close_db() should dispose engine and reset singletons."""
        await init_db()
        assert db_module._engine is not None

        await close_db()

        assert db_module._engine is None
        assert db_module._session_factory is None

    @pytest.mark.asyncio
    async def test_close_db_noop_when_not_initialized(self) -> None:
        """close_db() should be safe to call when not initialized."""
        assert db_module._engine is None
        await close_db()  # Should not raise
        assert db_module._engine is None


class TestGetEngine:
    """Tests for get_engine() accessor."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_db(self) -> None:
        """Ensure database state is clean."""
        db_module._engine = None
        db_module._session_factory = None
        yield
        if db_module._engine is not None:
            await db_module._engine.dispose()
        db_module._engine = None
        db_module._session_factory = None

    @pytest.mark.asyncio
    async def test_get_engine_returns_engine_after_init(self) -> None:
        """get_engine() should return the engine after init_db()."""
        await init_db()
        engine = get_engine()
        assert engine is not None

    def test_get_engine_raises_before_init(self) -> None:
        """get_engine() should raise RuntimeError before init_db()."""
        with pytest.raises(RuntimeError, match="not initialized"):
            get_engine()


class TestGetDbSession:
    """Tests for get_db_session() FastAPI dependency."""

    @pytest_asyncio.fixture(autouse=True)
    async def cleanup_db(self) -> None:
        """Ensure database state is clean."""
        db_module._engine = None
        db_module._session_factory = None
        yield
        if db_module._engine is not None:
            await db_module._engine.dispose()
        db_module._engine = None
        db_module._session_factory = None

    @pytest.mark.asyncio
    async def test_get_db_session_raises_before_init(self) -> None:
        """get_db_session() should raise RuntimeError if DB not initialized."""
        with pytest.raises(RuntimeError, match="not initialized"):
            async for _ in get_db_session():
                pass

    @pytest.mark.asyncio
    async def test_get_db_session_yields_session_after_init(self) -> None:
        """get_db_session() should yield an AsyncSession after init_db()."""
        from sqlalchemy.ext.asyncio import AsyncSession

        await init_db()

        gen = get_db_session()
        session = await gen.__anext__()

        assert session is not None
        assert isinstance(session, AsyncSession)

        # Clean up the generator (triggers rollback since no real DB)
        try:
            await gen.__anext__()
        except StopAsyncIteration:
            pass
