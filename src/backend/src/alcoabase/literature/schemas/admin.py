"""Pydantic v2 schemas for literature gateway admin endpoints.

Provides validated request/response schemas for system-level rate limit
management, proxy configuration, source health monitoring, and
per-company usage metrics.

References:
    - Design doc: .kiro/specs/Step_9-1_literature-search-engine/design.md
    - Requirements: 5.7, 7.1, 11.4, 14.3, 14.4
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field


# ─── Rate Limit Schemas ───────────────────────────────────────────────────


class SystemRateLimitResponse(BaseModel):
    """Response schema for system-level rate limit configuration.

    Returned from GET /api/literature/admin/rate-limits and
    GET /api/literature/admin/rate-limits/{source_name}.

    Attributes:
        source_adapter_name: Name of the registered source adapter.
        requests_per_second: Current maximum RPS at system level.
        max_queue_size: Maximum queued requests before rejection.
        updated_at: Timestamp of last configuration change.
    """

    source_adapter_name: str
    requests_per_second: int
    max_queue_size: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SystemRateLimitUpdate(BaseModel):
    """Request schema for updating system-level rate limits.

    Used with PUT /api/literature/admin/rate-limits/{source_name}.

    Attributes:
        requests_per_second: New maximum RPS (1–1000).
        max_queue_size: New maximum queue size (optional).
    """

    requests_per_second: int = Field(..., ge=1, le=1000)
    max_queue_size: int | None = Field(None, ge=1)


# ─── Proxy Configuration Schemas ─────────────────────────────────────────


class ProxyConfigurationResponse(BaseModel):
    """Response schema for global proxy configuration.

    Returned from GET /api/literature/admin/proxy. Credentials are never
    exposed in plaintext; only the presence of a username is indicated.

    Attributes:
        proxy_url: Configured HTTP/HTTPS proxy URL.
        has_credentials: Whether proxy authentication credentials are set.
        no_proxy_list: List of hostnames/IPs that bypass the proxy.
        is_active: Whether the proxy is currently enabled.
        updated_at: Timestamp of last configuration change.
    """

    proxy_url: str
    username_ciphertext: str | None = Field(default=None, exclude=True)
    no_proxy_list: list[str] = Field(default_factory=list)
    is_active: bool
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_credentials(self) -> bool:
        """Indicate whether proxy credentials are configured."""
        return self.username_ciphertext is not None

    model_config = ConfigDict(from_attributes=True)


class ProxyConfigurationUpdate(BaseModel):
    """Request schema for updating global proxy configuration.

    Used with PUT /api/literature/admin/proxy. All fields are optional;
    only provided fields are updated.

    Attributes:
        proxy_url: New proxy URL.
        username: Proxy authentication username (stored encrypted).
        password: Proxy authentication password (stored encrypted).
        no_proxy_list: Updated list of hostnames/IPs to bypass proxy.
        is_active: Whether to enable or disable the proxy.
    """

    proxy_url: str | None = None
    username: str | None = None
    password: str | None = None
    no_proxy_list: list[str] | None = None
    is_active: bool | None = None


# ─── Health Monitoring Schemas ────────────────────────────────────────────


class SourceHealthResponse(BaseModel):
    """Response schema for source adapter health status.

    Returned from GET /api/literature/health showing per-source
    availability and performance metrics.

    Attributes:
        source_adapter_name: Name of the registered source adapter.
        status: Current health classification (available, degraded, unreachable).
        last_check_timestamp: When the last health check was performed.
        avg_response_time_ms: Average response time over the last hour.
        consecutive_failure_count: Number of consecutive health check failures.
        flagged_for_attention: Whether the source has been unreachable >30 min.
    """

    source_adapter_name: str
    status: str
    last_check_timestamp: datetime | None = None
    avg_response_time_ms: float | None = None
    consecutive_failure_count: int = 0
    flagged_for_attention: bool = False

    model_config = ConfigDict(from_attributes=True)


# ─── Company Usage Schemas ────────────────────────────────────────────────


class CompanyUsageResponse(BaseModel):
    """Response schema for per-company usage metrics.

    Returned from GET /api/literature/usage/{company_id} showing
    request counts and rate limiting activity for a billing period.

    Attributes:
        company_id: The company these metrics belong to.
        requests_made: Total requests dispatched in the period.
        requests_queued: Requests that were queued due to rate limits.
        requests_rate_limited: Requests rejected by rate limiting.
        period_start: Start of the metrics reporting period.
        period_end: End of the metrics reporting period.
    """

    company_id: int
    requests_made: int = 0
    requests_queued: int = 0
    requests_rate_limited: int = 0
    period_start: datetime
    period_end: datetime

    model_config = ConfigDict(from_attributes=True)
