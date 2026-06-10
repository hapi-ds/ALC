"""Circuit breaker for external API resilience.

Implements the standard closed → open → half-open state machine with
Redis-backed state storage for cross-worker consistency.

State transitions:
    - CLOSED → OPEN: After ``failure_threshold`` consecutive failures
      within ``failure_window_seconds``.
    - OPEN → HALF_OPEN: After ``recovery_timeout_seconds`` elapsed since
      the circuit was opened.
    - HALF_OPEN → CLOSED: On a successful request (probe passes).
    - HALF_OPEN → OPEN: On a failed request (probe fails).

References:
    - Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
"""

from __future__ import annotations

import time
from enum import StrEnum

import redis.asyncio as aioredis


class CircuitState(StrEnum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Per-source circuit breaker with Redis-backed state.

    All state (current state, failure count, and opened_at timestamp)
    is stored in Redis to ensure consistency across multiple backend
    worker processes.

    Configuration:
        - failure_threshold: 5 consecutive failures to open circuit.
        - failure_window_seconds: 300 (5 minutes) for counting failures.
        - recovery_timeout_seconds: 300 (5 minutes) open → half-open.

    Redis key patterns:
        - ``lit:circuit:{source}:state`` — Current CircuitState value.
        - ``lit:circuit:{source}:failures`` — Consecutive failure count.
        - ``lit:circuit:{source}:opened_at`` — Unix timestamp when circuit opened.

    Example:
        >>> cb = CircuitBreaker("redis://localhost:6379/0")
        >>> await cb.can_execute("pubmed")
        True
        >>> for _ in range(5):
        ...     await cb.record_failure("pubmed")
        >>> await cb.can_execute("pubmed")
        False
    """

    def __init__(
        self,
        redis_url: str,
        failure_threshold: int = 5,
        failure_window_seconds: int = 300,
        recovery_timeout_seconds: int = 300,
    ) -> None:
        """Initialize circuit breaker.

        Args:
            redis_url: Redis connection URL for state storage.
            failure_threshold: Consecutive failures to open circuit.
            failure_window_seconds: Window for counting failures.
            recovery_timeout_seconds: Time before half-open probe.
        """
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url, decode_responses=True
        )
        self._failure_threshold = failure_threshold
        self._failure_window_seconds = failure_window_seconds
        self._recovery_timeout_seconds = recovery_timeout_seconds

    # ─────────────────────────────────────────────────────────────────────
    # Redis key helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _state_key(source_name: str) -> str:
        """Return the Redis key for circuit state."""
        return f"lit:circuit:{source_name}:state"

    @staticmethod
    def _failures_key(source_name: str) -> str:
        """Return the Redis key for failure count."""
        return f"lit:circuit:{source_name}:failures"

    @staticmethod
    def _opened_at_key(source_name: str) -> str:
        """Return the Redis key for circuit-opened timestamp."""
        return f"lit:circuit:{source_name}:opened_at"

    # ─────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────

    async def can_execute(self, source_name: str) -> bool:
        """Check if a request to the source is allowed.

        Returns True if the circuit is CLOSED (normal operation) or
        HALF_OPEN (probe request allowed). If the circuit is OPEN,
        checks whether the recovery timeout has elapsed and transitions
        to HALF_OPEN if so.

        Args:
            source_name: Adapter name to check.

        Returns:
            True if the request is allowed, False if blocked.
        """
        state = await self.get_state(source_name)

        if state == CircuitState.CLOSED:
            return True

        if state == CircuitState.HALF_OPEN:
            return True

        # State is OPEN — check if recovery timeout has elapsed
        opened_at_raw = await self._redis.get(self._opened_at_key(source_name))
        if opened_at_raw is not None:
            opened_at = float(opened_at_raw)
            elapsed = time.time() - opened_at
            if elapsed >= self._recovery_timeout_seconds:
                # Transition OPEN → HALF_OPEN
                await self._redis.set(
                    self._state_key(source_name), CircuitState.HALF_OPEN
                )
                return True

        return False

    async def record_success(self, source_name: str) -> None:
        """Record a successful request, potentially closing the circuit.

        If the circuit is HALF_OPEN, transitions to CLOSED and resets
        the failure count. If CLOSED, this is a no-op.

        Args:
            source_name: Adapter that succeeded.
        """
        state = await self.get_state(source_name)

        if state == CircuitState.HALF_OPEN:
            # Probe succeeded → close circuit
            pipe = self._redis.pipeline()
            pipe.set(self._state_key(source_name), CircuitState.CLOSED)
            pipe.set(self._failures_key(source_name), 0)
            pipe.delete(self._opened_at_key(source_name))
            await pipe.execute()
        elif state == CircuitState.CLOSED:
            # Reset failure count on success in closed state
            await self._redis.set(self._failures_key(source_name), 0)

    async def record_failure(self, source_name: str) -> None:
        """Record a failed request, potentially opening the circuit.

        In CLOSED state: increments the failure counter. If the counter
        reaches the threshold within the failure window, opens the circuit.

        In HALF_OPEN state: immediately re-opens the circuit (probe failed).

        Args:
            source_name: Adapter that failed.
        """
        state = await self.get_state(source_name)

        if state == CircuitState.HALF_OPEN:
            # Probe failed → re-open circuit
            pipe = self._redis.pipeline()
            pipe.set(self._state_key(source_name), CircuitState.OPEN)
            pipe.set(self._opened_at_key(source_name), str(time.time()))
            await pipe.execute()
            return

        if state == CircuitState.CLOSED:
            # Increment failure count with TTL matching the failure window
            failures_key = self._failures_key(source_name)
            new_count = await self._redis.incr(failures_key)

            # Set expiry on the failure counter so it resets after the window
            # Only set TTL if this is the first failure (count == 1)
            if new_count == 1:
                await self._redis.expire(
                    failures_key, self._failure_window_seconds
                )

            # Check if threshold reached
            if new_count >= self._failure_threshold:
                pipe = self._redis.pipeline()
                pipe.set(self._state_key(source_name), CircuitState.OPEN)
                pipe.set(self._opened_at_key(source_name), str(time.time()))
                pipe.set(self._failures_key(source_name), 0)
                await pipe.execute()

    async def get_state(self, source_name: str) -> CircuitState:
        """Get the current circuit state for a source.

        If no state is stored in Redis (first access), defaults to CLOSED.

        Args:
            source_name: Adapter name.

        Returns:
            Current CircuitState.
        """
        state_raw = await self._redis.get(self._state_key(source_name))
        if state_raw is None:
            return CircuitState.CLOSED
        return CircuitState(state_raw)

    async def get_estimated_recovery_time(self, source_name: str) -> float | None:
        """Get estimated seconds until circuit transitions to half-open.

        Only meaningful when the circuit is OPEN. Returns None if the
        circuit is CLOSED or HALF_OPEN.

        Args:
            source_name: Adapter name.

        Returns:
            Seconds remaining until HALF_OPEN transition, or None if
            the circuit is not OPEN.
        """
        state = await self.get_state(source_name)
        if state != CircuitState.OPEN:
            return None

        opened_at_raw = await self._redis.get(self._opened_at_key(source_name))
        if opened_at_raw is None:
            return None

        opened_at = float(opened_at_raw)
        elapsed = time.time() - opened_at
        remaining = self._recovery_timeout_seconds - elapsed

        return max(0.0, remaining)
