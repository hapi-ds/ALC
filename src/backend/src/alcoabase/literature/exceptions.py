"""Custom exception hierarchy for the Literature Search Engine.

All exceptions raised by the literature gateway subsystem inherit from
``LiteratureGatewayError``.  Adapter-specific failures use the
``AdapterError`` subtree, while operational/infrastructure errors
(rate limiting, circuit breaking, encryption) use dedicated classes
directly under the base.

References:
    - Requirements 2.8, 2.9, 9.1–9.6
"""

from __future__ import annotations


# ─────────────────────────────────────────────────────────────────────────────
# Base Exception
# ─────────────────────────────────────────────────────────────────────────────


class LiteratureGatewayError(Exception):
    """Base exception for all literature gateway errors.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter that raised the error, if applicable.
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
    ) -> None:
        self.message = message
        self.source_adapter_name = source_adapter_name
        super().__init__(message)


# ─────────────────────────────────────────────────────────────────────────────
# Adapter Errors
# ─────────────────────────────────────────────────────────────────────────────


class AdapterError(LiteratureGatewayError):
    """Base exception for adapter-specific failures.

    Raised when a source adapter encounters an error communicating with
    its external API.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter that raised the error.
        status_code: HTTP status code from the external API, if available.
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.status_code = status_code
        super().__init__(message, source_adapter_name=source_adapter_name)


class AdapterAuthError(AdapterError):
    """Raised when an external API returns HTTP 401 or 403.

    Indicates invalid or expired credentials for the source.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter that raised the error.
        status_code: HTTP status code (401 or 403).
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
        status_code: int = 401,
    ) -> None:
        super().__init__(
            message,
            source_adapter_name=source_adapter_name,
            status_code=status_code,
        )


class AdapterTimeoutError(AdapterError):
    """Raised when a request to an external API exceeds the timeout.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter that raised the error.
        timeout_seconds: The timeout threshold that was exceeded.
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        super().__init__(message, source_adapter_name=source_adapter_name)


class AdapterParseError(AdapterError):
    """Raised when an external API response cannot be parsed.

    Indicates a malformed or unexpected response format from the source.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter that raised the error.
        content_type: Content-Type header of the unparseable response.
        response_size_bytes: Size of the raw response body in bytes.
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
        content_type: str | None = None,
        response_size_bytes: int | None = None,
    ) -> None:
        self.content_type = content_type
        self.response_size_bytes = response_size_bytes
        super().__init__(message, source_adapter_name=source_adapter_name)


class AdapterConnectionError(AdapterError):
    """Raised when a network failure prevents reaching the external API.

    Covers DNS resolution failures, TCP connection refused, TLS errors,
    and proxy connectivity issues.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter that raised the error.
        target_url: The URL that could not be reached.
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
        target_url: str | None = None,
    ) -> None:
        self.target_url = target_url
        super().__init__(message, source_adapter_name=source_adapter_name)


# ─────────────────────────────────────────────────────────────────────────────
# Operational Errors
# ─────────────────────────────────────────────────────────────────────────────


class RateLimitExceededError(LiteratureGatewayError):
    """Raised when a company's rate limit has been exceeded.

    Maps to HTTP 429 with a Retry-After header.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter, if limit is per-source.
        retry_after_seconds: Seconds until the next request window opens.
        company_id: The company that hit the limit.
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
        retry_after_seconds: float,
        company_id: int | None = None,
    ) -> None:
        self.retry_after_seconds = retry_after_seconds
        self.company_id = company_id
        super().__init__(message, source_adapter_name=source_adapter_name)


class AllSourcesUnavailableError(LiteratureGatewayError):
    """Raised when all enabled sources for a company are unavailable.

    Maps to HTTP 503 with an estimated recovery time.

    Attributes:
        message: Human-readable error description.
        estimated_recovery_time: Estimated seconds until at least one source
            may recover, based on circuit breaker state. None if unknown.
        unavailable_sources: List of source adapter names that are unavailable.
    """

    def __init__(
        self,
        message: str,
        *,
        estimated_recovery_time: float | None = None,
        unavailable_sources: list[str] | None = None,
    ) -> None:
        self.estimated_recovery_time = estimated_recovery_time
        self.unavailable_sources = unavailable_sources or []
        super().__init__(message)


class EncryptionKeyMissingError(LiteratureGatewayError):
    """Raised when the master encryption key environment variable is not set.

    The application should refuse to start when this error is raised
    and ``literature_enabled`` is True.

    Attributes:
        message: Human-readable error description.
        env_var_name: Name of the missing environment variable.
    """

    def __init__(
        self,
        message: str = "Master encryption key environment variable is not set.",
        *,
        env_var_name: str = "ALC_LITERATURE_ENCRYPTION_KEY",
    ) -> None:
        self.env_var_name = env_var_name
        super().__init__(message)


class QueueFullError(LiteratureGatewayError):
    """Raised when a per-source request queue is at maximum capacity.

    Indicates that the system-level rate limit queue (500 requests) for
    a specific source is full and no more requests can be accepted.

    Attributes:
        message: Human-readable error description.
        source_adapter_name: Name of the adapter whose queue is full.
        queue_size: Current queue capacity.
        estimated_wait_seconds: Estimated seconds until a queue slot opens,
            based on the current drain rate. None if unknown.
    """

    def __init__(
        self,
        message: str,
        *,
        source_adapter_name: str | None = None,
        queue_size: int = 500,
        estimated_wait_seconds: float | None = None,
    ) -> None:
        self.queue_size = queue_size
        self.estimated_wait_seconds = estimated_wait_seconds
        super().__init__(message, source_adapter_name=source_adapter_name)
