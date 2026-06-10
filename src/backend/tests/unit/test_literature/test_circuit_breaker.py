"""Unit tests for the CircuitBreaker service.

Tests the circuit breaker state machine transitions and Redis-backed
state persistence using a mocked Redis client.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from alcoabase.literature.services.circuit_breaker import CircuitBreaker, CircuitState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Create a mock async Redis client with in-memory dict storage."""
    redis_mock = AsyncMock()
    storage: dict[str, str] = {}

    async def mock_get(key: str) -> str | None:
        return storage.get(key)

    async def mock_set(key: str, value: str, *args, **kwargs) -> None:
        storage[key] = str(value)

    async def mock_delete(*keys: str) -> None:
        for key in keys:
            storage.pop(key, None)

    async def mock_incr(key: str) -> int:
        current = int(storage.get(key, "0"))
        new_val = current + 1
        storage[key] = str(new_val)
        return new_val

    async def mock_expire(key: str, seconds: int) -> None:
        pass  # No-op for unit tests

    redis_mock.get = AsyncMock(side_effect=mock_get)
    redis_mock.set = AsyncMock(side_effect=mock_set)
    redis_mock.delete = AsyncMock(side_effect=mock_delete)
    redis_mock.incr = AsyncMock(side_effect=mock_incr)
    redis_mock.expire = AsyncMock(side_effect=mock_expire)

    # Mock pipeline
    def create_pipeline():
        pipe = MagicMock()
        pipe_ops: list[tuple[str, ...]] = []

        def pipe_set(key: str, value: str) -> None:
            pipe_ops.append(("set", key, str(value)))

        def pipe_delete(*keys: str) -> None:
            for key in keys:
                pipe_ops.append(("delete", key))

        async def pipe_execute() -> list:
            for op in pipe_ops:
                if op[0] == "set":
                    storage[op[1]] = op[2]
                elif op[0] == "delete":
                    storage.pop(op[1], None)
            pipe_ops.clear()
            return []

        pipe.set = MagicMock(side_effect=pipe_set)
        pipe.delete = MagicMock(side_effect=pipe_delete)
        pipe.execute = AsyncMock(side_effect=pipe_execute)
        return pipe

    redis_mock.pipeline = MagicMock(side_effect=create_pipeline)
    redis_mock._storage = storage  # Expose for assertions

    return redis_mock


@pytest.fixture
def circuit_breaker(mock_redis: AsyncMock) -> CircuitBreaker:
    """Create a CircuitBreaker with mocked Redis."""
    with patch("redis.asyncio.from_url", return_value=mock_redis):
        cb = CircuitBreaker(
            redis_url="redis://localhost:6379/0",
            failure_threshold=5,
            failure_window_seconds=300,
            recovery_timeout_seconds=300,
        )
    cb._redis = mock_redis
    return cb


# ---------------------------------------------------------------------------
# Tests: Initial State
# ---------------------------------------------------------------------------


class TestCircuitBreakerInitialState:
    """Tests for the circuit breaker's default state."""

    @pytest.mark.asyncio
    async def test_default_state_is_closed(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """A source with no prior state defaults to CLOSED."""
        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_can_execute_when_closed(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Requests are allowed when circuit is CLOSED."""
        assert await circuit_breaker.can_execute("pubmed") is True

    @pytest.mark.asyncio
    async def test_recovery_time_none_when_closed(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Estimated recovery time is None when circuit is not OPEN."""
        result = await circuit_breaker.get_estimated_recovery_time("pubmed")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: CLOSED → OPEN Transition
# ---------------------------------------------------------------------------


class TestClosedToOpenTransition:
    """Tests for the CLOSED → OPEN state transition."""

    @pytest.mark.asyncio
    async def test_single_failure_stays_closed(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """A single failure does not open the circuit."""
        await circuit_breaker.record_failure("pubmed")
        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_four_failures_stays_closed(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Four failures (below threshold=5) keeps circuit CLOSED."""
        for _ in range(4):
            await circuit_breaker.record_failure("pubmed")
        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_five_failures_opens_circuit(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Five consecutive failures opens the circuit."""
        for _ in range(5):
            await circuit_breaker.record_failure("pubmed")
        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_cannot_execute_when_open(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Requests are blocked when circuit is OPEN and recovery hasn't elapsed."""
        for _ in range(5):
            await circuit_breaker.record_failure("pubmed")

        # Set opened_at to now (so recovery timeout hasn't passed)
        mock_redis = circuit_breaker._redis
        mock_redis._storage["lit:circuit:pubmed:opened_at"] = str(time.time())

        assert await circuit_breaker.can_execute("pubmed") is False


# ---------------------------------------------------------------------------
# Tests: OPEN → HALF_OPEN Transition
# ---------------------------------------------------------------------------


class TestOpenToHalfOpenTransition:
    """Tests for the OPEN → HALF_OPEN state transition."""

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_recovery_timeout(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Circuit transitions OPEN → HALF_OPEN when recovery timeout elapses."""
        mock_redis = circuit_breaker._redis

        # Manually set state to OPEN with opened_at in the past
        mock_redis._storage["lit:circuit:pubmed:state"] = CircuitState.OPEN
        mock_redis._storage["lit:circuit:pubmed:opened_at"] = str(
            time.time() - 301  # 301s > 300s recovery timeout
        )

        can = await circuit_breaker.can_execute("pubmed")
        assert can is True

        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_stays_open_before_recovery_timeout(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Circuit stays OPEN when recovery timeout hasn't elapsed."""
        mock_redis = circuit_breaker._redis

        mock_redis._storage["lit:circuit:pubmed:state"] = CircuitState.OPEN
        mock_redis._storage["lit:circuit:pubmed:opened_at"] = str(
            time.time() - 100  # Only 100s elapsed, need 300s
        )

        can = await circuit_breaker.can_execute("pubmed")
        assert can is False

    @pytest.mark.asyncio
    async def test_estimated_recovery_time_when_open(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Returns positive recovery time when circuit is OPEN."""
        mock_redis = circuit_breaker._redis

        mock_redis._storage["lit:circuit:pubmed:state"] = CircuitState.OPEN
        mock_redis._storage["lit:circuit:pubmed:opened_at"] = str(
            time.time() - 100  # 100s elapsed, 200s remaining
        )

        recovery = await circuit_breaker.get_estimated_recovery_time("pubmed")
        assert recovery is not None
        assert 198.0 <= recovery <= 201.0  # ~200s remaining (allow timing jitter)


# ---------------------------------------------------------------------------
# Tests: HALF_OPEN → CLOSED Transition
# ---------------------------------------------------------------------------


class TestHalfOpenToClosedTransition:
    """Tests for the HALF_OPEN → CLOSED state transition."""

    @pytest.mark.asyncio
    async def test_success_in_half_open_closes_circuit(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """A successful request in HALF_OPEN closes the circuit."""
        mock_redis = circuit_breaker._redis

        mock_redis._storage["lit:circuit:pubmed:state"] = CircuitState.HALF_OPEN
        mock_redis._storage["lit:circuit:pubmed:failures"] = "3"
        mock_redis._storage["lit:circuit:pubmed:opened_at"] = str(time.time() - 400)

        await circuit_breaker.record_success("pubmed")

        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.CLOSED

        # Failure count should be reset
        assert mock_redis._storage.get("lit:circuit:pubmed:failures") == "0"

        # opened_at should be removed
        assert "lit:circuit:pubmed:opened_at" not in mock_redis._storage

    @pytest.mark.asyncio
    async def test_can_execute_when_half_open(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Probe request is allowed when circuit is HALF_OPEN."""
        mock_redis = circuit_breaker._redis
        mock_redis._storage["lit:circuit:pubmed:state"] = CircuitState.HALF_OPEN

        assert await circuit_breaker.can_execute("pubmed") is True


# ---------------------------------------------------------------------------
# Tests: HALF_OPEN → OPEN Transition
# ---------------------------------------------------------------------------


class TestHalfOpenToOpenTransition:
    """Tests for the HALF_OPEN → OPEN state transition."""

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens_circuit(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """A failed request in HALF_OPEN immediately reopens the circuit."""
        mock_redis = circuit_breaker._redis
        mock_redis._storage["lit:circuit:pubmed:state"] = CircuitState.HALF_OPEN

        await circuit_breaker.record_failure("pubmed")

        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.OPEN

        # Should have set opened_at
        assert "lit:circuit:pubmed:opened_at" in mock_redis._storage


# ---------------------------------------------------------------------------
# Tests: Success in CLOSED state
# ---------------------------------------------------------------------------


class TestSuccessInClosedState:
    """Tests for recording success when circuit is CLOSED."""

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """A success in CLOSED state resets failure counter."""
        mock_redis = circuit_breaker._redis
        mock_redis._storage["lit:circuit:pubmed:failures"] = "3"

        await circuit_breaker.record_success("pubmed")

        assert mock_redis._storage.get("lit:circuit:pubmed:failures") == "0"


# ---------------------------------------------------------------------------
# Tests: Multi-Source Isolation
# ---------------------------------------------------------------------------


class TestMultiSourceIsolation:
    """Tests that circuit breakers are independent per source."""

    @pytest.mark.asyncio
    async def test_sources_are_independent(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Opening the circuit for one source doesn't affect another."""
        # Open pubmed circuit
        for _ in range(5):
            await circuit_breaker.record_failure("pubmed")

        mock_redis = circuit_breaker._redis
        mock_redis._storage["lit:circuit:pubmed:opened_at"] = str(time.time())

        # pubmed should be blocked
        assert await circuit_breaker.can_execute("pubmed") is False
        # crossref should still be open
        assert await circuit_breaker.can_execute("crossref") is True

    @pytest.mark.asyncio
    async def test_state_uses_correct_redis_keys(
        self, circuit_breaker: CircuitBreaker
    ) -> None:
        """Each source uses its own namespaced Redis keys."""
        mock_redis = circuit_breaker._redis
        mock_redis._storage["lit:circuit:arxiv:state"] = CircuitState.OPEN

        state = await circuit_breaker.get_state("arxiv")
        assert state == CircuitState.OPEN

        # Different source should be CLOSED (default)
        state = await circuit_breaker.get_state("pubmed")
        assert state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Tests: CircuitState Enum
# ---------------------------------------------------------------------------


class TestCircuitStateEnum:
    """Tests for the CircuitState StrEnum."""

    def test_enum_values(self) -> None:
        """CircuitState has the expected string values."""
        assert CircuitState.CLOSED == "closed"
        assert CircuitState.OPEN == "open"
        assert CircuitState.HALF_OPEN == "half_open"

    def test_enum_is_str(self) -> None:
        """CircuitState members are strings."""
        assert isinstance(CircuitState.CLOSED, str)
        assert isinstance(CircuitState.OPEN, str)
        assert isinstance(CircuitState.HALF_OPEN, str)

    def test_enum_round_trip(self) -> None:
        """CircuitState can be reconstructed from its string value."""
        for state in CircuitState:
            assert CircuitState(state.value) == state
