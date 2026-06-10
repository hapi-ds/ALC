"""SQLAlchemy models for the Literature Search Engine.

All models follow existing project patterns:
- Inherit from Base (alcoabase.database)
- Use AuditMixin for versioned models (SQLAlchemy-Continuum)
- Use mapped_column with type annotations (SQLAlchemy 2.0 style)
- Include proper indexes and constraints

References:
    - Requirements 3, 4, 5, 6, 10, 11, 13
    - Design: .kiro/specs/Step_9-1_literature-search-engine/design.md
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin

if TYPE_CHECKING:
    from alcoabase.models.company import Company


class SourceConfiguration(Base, AuditMixin):
    """Per-company configuration for a literature source adapter.

    Stores enabled state, encrypted API key, rate limit overrides,
    priority ranking, and proxy settings for a specific company+source.

    Attributes:
        id: Primary key.
        company_id: FK to companies table.
        source_adapter_name: Name of the registered adapter.
        is_enabled: Whether this source is active for the company.
        api_key_ciphertext: AES-256-GCM encrypted API key (base64).
        api_key_nonce: GCM nonce for decryption (base64).
        api_key_tag: GCM authentication tag (base64).
        priority: Search priority ranking (1=highest, 100=lowest).
        rate_limit_rpm: Custom per-company rate limit (requests/minute).
        proxy_override_url: Optional per-source proxy URL.
        contact_email: Contact email for polite-pool APIs (e.g., Crossref).
        extra_config: JSON blob for adapter-specific settings.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_source_configurations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    source_adapter_name: Mapped[str] = mapped_column(String(100), index=True)
    is_enabled: Mapped[bool] = mapped_column(default=True)

    # Encrypted API key components (all nullable — some sources don't need keys)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_nonce: Mapped[str | None] = mapped_column(String(32), nullable=True)
    api_key_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)

    priority: Mapped[int] = mapped_column(Integer, default=50)
    rate_limit_rpm: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proxy_override_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    extra_config: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "source_adapter_name",
            name="uq_lit_source_config_company_adapter",
        ),
        Index(
            "ix_lit_source_config_company_enabled",
            "company_id",
            "is_enabled",
        ),
    )


class SearchProfile(Base, AuditMixin):
    """Named search profile for a company defining default search behavior.

    Each profile defines a set of enabled sources, priority ordering,
    and default query filters (e.g., publication date range, publication types).

    Attributes:
        id: Primary key.
        company_id: FK to companies table.
        name: Profile name (unique per company).
        is_default: Whether this is the company's default profile.
        enabled_sources: JSON list of source adapter names to include.
        source_priorities: JSON dict of source_name → priority overrides.
        default_filters: JSON dict of default query filters.
        created_at: Creation timestamp.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_search_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    is_default: Mapped[bool] = mapped_column(default=False)
    enabled_sources: Mapped[list] = mapped_column(JSONB, default=list)
    source_priorities: Mapped[dict] = mapped_column(JSONB, default=dict)
    default_filters: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "company_id", "name", name="uq_lit_search_profile_company_name"
        ),
        Index(
            "ix_lit_search_profile_company_default",
            "company_id",
            "is_default",
        ),
    )


class SystemRateLimitConfig(Base, AuditMixin):
    """System-level rate limit configuration per source adapter.

    Defines the maximum requests-per-second and queue size at the system
    level for each registered source adapter.

    Attributes:
        id: Primary key.
        source_adapter_name: Adapter this limit applies to (unique).
        requests_per_second: Maximum RPS at system level.
        max_queue_size: Maximum queued requests before rejection.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_system_rate_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_adapter_name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True
    )
    requests_per_second: Mapped[int] = mapped_column(Integer, default=10)
    max_queue_size: Mapped[int] = mapped_column(Integer, default=500)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProxyConfiguration(Base, AuditMixin):
    """Global proxy configuration for outbound literature API requests.

    Stores the proxy URL, encrypted authentication credentials, and
    a no-proxy list for hostnames/IPs that bypass the proxy.

    Attributes:
        id: Primary key.
        proxy_url: HTTP/HTTPS proxy URL.
        username_ciphertext: Encrypted proxy username (base64).
        username_nonce: Nonce for username decryption (base64).
        username_tag: Auth tag for username verification (base64).
        password_ciphertext: Encrypted proxy password (base64).
        password_nonce: Nonce for password decryption (base64).
        password_tag: Auth tag for password verification (base64).
        no_proxy_list: JSON list of hostnames/IPs to bypass proxy.
        is_active: Whether proxy is currently enabled.
        updated_at: Last modification timestamp.
    """

    __tablename__ = "literature_proxy_configuration"

    id: Mapped[int] = mapped_column(primary_key=True)
    proxy_url: Mapped[str] = mapped_column(String(500))
    username_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    username_nonce: Mapped[str | None] = mapped_column(String(32), nullable=True)
    username_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_nonce: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)
    no_proxy_list: Mapped[list] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExternalAPIAuditLog(Base):
    """Immutable audit record for external API interactions.

    NOT versioned via Continuum — these are append-only audit records.
    Each record captures a single outbound API request and its response,
    linked to the originating search query for full traceability.

    Attributes:
        id: Primary key.
        query_id: UUID linking to the originating search query.
        company_id: Company that initiated the request.
        user_id: User that initiated the request.
        source_adapter_name: Which adapter made the call.
        request_url: Target URL (API keys redacted from query params).
        request_timestamp: When the request was sent.
        response_timestamp: When the response was received.
        http_status_code: Response status code (null if connection failed).
        result_count: Number of results returned.
        response_time_ms: Response time in milliseconds.
        error_type: Type of error if failed (null on success).
        error_message: Error details (never contains secrets).
        retry_attempt: Which retry attempt this was (0 = first try).
    """

    __tablename__ = "literature_external_api_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_id: Mapped[str] = mapped_column(String(36), index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source_adapter_name: Mapped[str] = mapped_column(String(100), index=True)
    request_url: Mapped[str] = mapped_column(Text)
    request_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    response_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_attempt: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        Index(
            "ix_lit_audit_log_company_timestamp",
            "company_id",
            "request_timestamp",
        ),
    )


class SourceHealthCheck(Base):
    """Health check result record for trend analysis.

    Stores the last 50 results per source (managed by application logic).
    Used for monitoring source availability and response time trends.

    Attributes:
        id: Primary key.
        source_adapter_name: Adapter that was checked.
        status: Result status (available, degraded, unreachable).
        response_time_ms: Response time in milliseconds (null if unreachable).
        checked_at: When the check was performed.
        error_message: Error details if check failed.
    """

    __tablename__ = "literature_source_health_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_adapter_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20))
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_lit_health_check_source_time",
            "source_adapter_name",
            "checked_at",
        ),
    )
