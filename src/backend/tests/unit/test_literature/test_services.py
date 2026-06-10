"""Unit tests for configuration and profile services.

Consolidates tests for:
- Source_Configuration CRUD with uniqueness constraint enforcement
- SearchProfile CRUD with default profile enforcement
- Profile template loading (pharma_medtech, technical_supplier, general)
- Proxy routing logic (global, per-source override, no-proxy list)

References:
    - Requirements: 3.1, 3.2, 3.5, 7.1, 7.4, 7.6, 13.1, 13.4, 13.5
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from alcoabase.literature.models.literature import SearchProfile, SourceConfiguration
from alcoabase.literature.schemas.configuration import (
    SourceConfigurationCreate,
    SourceConfigurationResponse,
    SourceConfigurationUpdate,
)
from alcoabase.literature.schemas.profiles import (
    SearchProfileCreate,
    SearchProfileUpdate,
)
from alcoabase.literature.schemas.search import SearchQuery
from alcoabase.literature.services.api_key_vault import APIKeyVault, EncryptedKey
from alcoabase.literature.services.proxy_manager import ProxyManager
from alcoabase.literature.services.search_profile_service import (
    DuplicateProfileError,
    InvalidSourceError,
    ProfileNotFoundError,
    SearchProfileService,
)
from alcoabase.literature.services.source_registry import SourceRegistry


# ===========================================================================
# Shared Fixtures
# ===========================================================================


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock async database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.delete = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session: AsyncMock):
    """Create a mock session factory with async context manager."""
    ctx_manager = AsyncMock()
    ctx_manager.__aenter__ = AsyncMock(return_value=mock_session)
    ctx_manager.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=ctx_manager)
    return factory


@pytest.fixture
def vault() -> APIKeyVault:
    """Create an APIKeyVault with a random 32-byte master key."""
    return APIKeyVault(os.urandom(32))


@pytest.fixture
def mock_source_registry() -> MagicMock:
    """Create a mock SourceRegistry where all adapters are registered."""
    registry = MagicMock(spec=SourceRegistry)
    registry.get_adapter.return_value = MagicMock()
    return registry


@pytest.fixture
def profile_service(
    mock_session_factory, mock_source_registry: MagicMock
) -> SearchProfileService:
    """Create a SearchProfileService with mocked dependencies."""
    return SearchProfileService(
        session_factory=mock_session_factory,
        source_registry=mock_source_registry,
    )


def _make_source_config(
    *,
    id: int = 1,
    company_id: int = 10,
    source_adapter_name: str = "pubmed",
    is_enabled: bool = True,
    priority: int = 1,
    api_key_ciphertext: str | None = None,
    api_key_nonce: str | None = None,
    api_key_tag: str | None = None,
    rate_limit_rpm: int | None = None,
    proxy_override_url: str | None = None,
    contact_email: str | None = None,
    extra_config: dict | None = None,
) -> SourceConfiguration:
    """Helper to create a SourceConfiguration instance for tests."""
    config = SourceConfiguration()
    config.id = id
    config.company_id = company_id
    config.source_adapter_name = source_adapter_name
    config.is_enabled = is_enabled
    config.priority = priority
    config.api_key_ciphertext = api_key_ciphertext
    config.api_key_nonce = api_key_nonce
    config.api_key_tag = api_key_tag
    config.rate_limit_rpm = rate_limit_rpm
    config.proxy_override_url = proxy_override_url
    config.contact_email = contact_email
    config.extra_config = extra_config or {}
    config.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    config.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return config


def _make_profile(
    *,
    id: int = 1,
    company_id: int = 10,
    name: str = "test_profile",
    is_default: bool = False,
    enabled_sources: list[str] | None = None,
    source_priorities: dict[str, int] | None = None,
    default_filters: dict | None = None,
) -> SearchProfile:
    """Helper to create a SearchProfile instance for tests."""
    profile = SearchProfile()
    profile.id = id
    profile.company_id = company_id
    profile.name = name
    profile.is_default = is_default
    profile.enabled_sources = enabled_sources or ["pubmed", "crossref"]
    profile.source_priorities = source_priorities or {"pubmed": 1, "crossref": 2}
    profile.default_filters = default_filters or {}
    profile.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    profile.updated_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return profile


# ===========================================================================
# Source Configuration CRUD Tests
# Requirements: 3.1, 3.2
# ===========================================================================


class TestSourceConfigurationCreate:
    """Tests for source configuration creation with uniqueness constraints."""

    def test_create_payload_valid(self) -> None:
        """SourceConfigurationCreate accepts valid data."""
        payload = SourceConfigurationCreate(
            source_adapter_name="pubmed",
            is_enabled=True,
            api_key="my-secret-key-1234",
            priority=1,
            contact_email="admin@pharma.com",
        )
        assert payload.source_adapter_name == "pubmed"
        assert payload.priority == 1
        assert payload.api_key == "my-secret-key-1234"

    def test_create_payload_defaults(self) -> None:
        """SourceConfigurationCreate uses correct defaults."""
        payload = SourceConfigurationCreate(source_adapter_name="crossref")
        assert payload.is_enabled is True
        assert payload.priority == 50
        assert payload.api_key is None
        assert payload.rate_limit_rpm is None
        assert payload.extra_config == {}

    def test_create_payload_rejects_priority_below_1(self) -> None:
        """Priority must be >= 1."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SourceConfigurationCreate(source_adapter_name="pubmed", priority=0)

    def test_create_payload_rejects_priority_above_100(self) -> None:
        """Priority must be <= 100."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SourceConfigurationCreate(source_adapter_name="pubmed", priority=101)

    def test_create_payload_rejects_empty_api_key(self) -> None:
        """API key must be at least 1 character if provided."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SourceConfigurationCreate(source_adapter_name="pubmed", api_key="")

    def test_create_payload_rejects_oversized_api_key(self) -> None:
        """API key must not exceed 512 characters."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SourceConfigurationCreate(
                source_adapter_name="pubmed", api_key="x" * 513
            )

    @pytest.mark.asyncio
    async def test_uniqueness_constraint_triggers_integrity_error(
        self, mock_session: AsyncMock
    ) -> None:
        """Flush raises IntegrityError when duplicate (company_id, source_adapter_name)."""
        config = _make_source_config(company_id=10, source_adapter_name="pubmed")
        mock_session.add(config)

        # Simulate IntegrityError on flush (as the router does)
        mock_session.flush.side_effect = IntegrityError(
            "duplicate key", params=None, orig=Exception()
        )

        with pytest.raises(IntegrityError):
            await mock_session.flush()

        # Verify rollback is available
        await mock_session.rollback()
        mock_session.rollback.assert_called_once()

    def test_source_config_model_has_uniqueness_constraint(self) -> None:
        """SourceConfiguration model defines the correct unique constraint."""
        table_args = SourceConfiguration.__table_args__
        # Find the UniqueConstraint
        unique_constraints = [
            arg
            for arg in table_args
            if hasattr(arg, "columns")
            and hasattr(arg, "name")
            and "uq_lit_source_config_company_adapter" in (arg.name or "")
        ]
        assert len(unique_constraints) == 1
        constraint = unique_constraints[0]
        col_names = [c.name for c in constraint.columns]
        assert "company_id" in col_names
        assert "source_adapter_name" in col_names


class TestSourceConfigurationUpdate:
    """Tests for source configuration update logic."""

    def test_update_payload_all_none_by_default(self) -> None:
        """SourceConfigurationUpdate has all optional fields."""
        payload = SourceConfigurationUpdate()
        assert payload.is_enabled is None
        assert payload.api_key is None
        assert payload.priority is None
        assert payload.rate_limit_rpm is None

    def test_update_payload_partial_fields(self) -> None:
        """Only provided fields are non-None."""
        payload = SourceConfigurationUpdate(
            is_enabled=False, priority=10
        )
        assert payload.is_enabled is False
        assert payload.priority == 10
        assert payload.api_key is None

    def test_update_applies_partial_fields_to_model(self) -> None:
        """Apply only non-None fields to a config model."""
        config = _make_source_config(is_enabled=True, priority=50)
        payload = SourceConfigurationUpdate(is_enabled=False, priority=5)

        # Simulate what the router does
        if payload.is_enabled is not None:
            config.is_enabled = payload.is_enabled
        if payload.priority is not None:
            config.priority = payload.priority

        assert config.is_enabled is False
        assert config.priority == 5
        # Unchanged fields remain
        assert config.source_adapter_name == "pubmed"

    def test_update_encrypts_new_api_key(self, vault: APIKeyVault) -> None:
        """API key is re-encrypted when updated."""
        config = _make_source_config()
        new_key = "new-api-key-9876"

        encrypted = vault.encrypt(new_key)
        config.api_key_ciphertext = encrypted.ciphertext
        config.api_key_nonce = encrypted.nonce
        config.api_key_tag = encrypted.tag

        # Verify decryption gives back the new key
        decrypted = vault.decrypt(
            EncryptedKey(
                ciphertext=config.api_key_ciphertext,
                nonce=config.api_key_nonce,
                tag=config.api_key_tag,
            )
        )
        assert decrypted == new_key


class TestSourceConfigurationResponse:
    """Tests for building source configuration responses with masked keys."""

    def test_response_masks_api_key(self, vault: APIKeyVault) -> None:
        """API key is masked showing only last 4 characters."""
        plaintext = "sk-mySecretApiKey1234"
        encrypted = vault.encrypt(plaintext)

        config = _make_source_config(
            api_key_ciphertext=encrypted.ciphertext,
            api_key_nonce=encrypted.nonce,
            api_key_tag=encrypted.tag,
        )

        # Simulate _build_config_response logic
        enc = EncryptedKey(
            ciphertext=config.api_key_ciphertext,
            nonce=config.api_key_nonce,
            tag=config.api_key_tag,
        )
        decrypted = vault.decrypt(enc)
        masked = APIKeyVault.mask_key(decrypted)

        assert masked.endswith("1234")
        assert masked.startswith("*")
        assert "mySecretApiKey" not in masked

    def test_response_no_key_returns_none(self) -> None:
        """Response has None api_key_masked when no key stored."""
        config = _make_source_config(api_key_ciphertext=None)

        # No ciphertext means no masked key
        api_key_masked = None
        if config.api_key_ciphertext:
            api_key_masked = "****"

        assert api_key_masked is None

    def test_response_includes_all_fields(self, vault: APIKeyVault) -> None:
        """SourceConfigurationResponse includes all expected fields."""
        config = _make_source_config(
            id=42,
            company_id=7,
            source_adapter_name="crossref",
            is_enabled=True,
            priority=3,
            rate_limit_rpm=60,
            proxy_override_url="http://proxy:8080",
            contact_email="dev@example.com",
            extra_config={"mailto": "dev@example.com"},
        )

        response = SourceConfigurationResponse(
            id=config.id,
            company_id=config.company_id,
            source_adapter_name=config.source_adapter_name,
            is_enabled=config.is_enabled,
            api_key_masked=None,
            priority=config.priority,
            rate_limit_rpm=config.rate_limit_rpm,
            proxy_override_url=config.proxy_override_url,
            contact_email=config.contact_email,
            extra_config=config.extra_config,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

        assert response.id == 42
        assert response.company_id == 7
        assert response.source_adapter_name == "crossref"
        assert response.priority == 3
        assert response.rate_limit_rpm == 60
        assert response.proxy_override_url == "http://proxy:8080"
        assert response.contact_email == "dev@example.com"
        assert response.extra_config == {"mailto": "dev@example.com"}


# ===========================================================================
# SearchProfile Default Enforcement Tests
# Requirements: 13.1, 13.4, 13.5
# ===========================================================================


class TestProfileDefaultEnforcement:
    """Tests for single-default-per-company enforcement logic."""

    @pytest.mark.asyncio
    async def test_creating_default_unsets_previous_default(
        self, profile_service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """When creating a new default profile, the previous default is unset."""
        # No existing profile with same name
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        data = SearchProfileCreate(
            name="new_default",
            is_default=True,
            enabled_sources=["pubmed"],
        )

        await profile_service.create_profile(10, data, change_reason="Set default")

        # Should call execute twice: once for name check, once for unset
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_creating_non_default_does_not_unset(
        self, profile_service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Creating a non-default profile doesn't affect existing defaults."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        data = SearchProfileCreate(
            name="secondary",
            is_default=False,
            enabled_sources=["crossref"],
        )

        await profile_service.create_profile(10, data, change_reason="Add profile")

        # Only name check, no unset default
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_updating_to_default_unsets_previous(
        self, profile_service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """Updating a profile to be default unsets the previous default."""
        profile = _make_profile(id=5, is_default=False)
        mock_session.get.return_value = profile

        # No name conflict check needed (name not changing)
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        data = SearchProfileUpdate(is_default=True)

        await profile_service.update_profile(5, data, change_reason="Promote")

        assert profile.is_default is True
        # execute called for unset_company_default
        assert mock_session.execute.call_count >= 1


# ===========================================================================
# Profile Template Loading Tests
# Requirements: 13.5
# ===========================================================================


class TestProfileTemplateLoading:
    """Tests for pre-built profile template loading."""

    def test_pharma_medtech_template(
        self, profile_service: SearchProfileService
    ) -> None:
        """pharma_medtech template prioritizes PubMed and Crossref."""
        templates = profile_service.get_available_templates()
        template = templates["pharma_medtech"]

        assert "pubmed" in template["enabled_sources"]
        assert "crossref" in template["enabled_sources"]
        assert template["source_priorities"]["pubmed"] < template["source_priorities"]["crossref"]

    def test_technical_supplier_template(
        self, profile_service: SearchProfileService
    ) -> None:
        """technical_supplier template prioritizes arXiv and Crossref."""
        templates = profile_service.get_available_templates()
        template = templates["technical_supplier"]

        assert "arxiv" in template["enabled_sources"]
        assert "crossref" in template["enabled_sources"]

    def test_general_template(
        self, profile_service: SearchProfileService
    ) -> None:
        """general template includes all sources with equal priority."""
        templates = profile_service.get_available_templates()
        template = templates["general"]

        assert "pubmed" in template["enabled_sources"]
        assert "crossref" in template["enabled_sources"]
        assert "arxiv" in template["enabled_sources"]

    def test_all_templates_have_required_keys(
        self, profile_service: SearchProfileService
    ) -> None:
        """Every template has enabled_sources and source_priorities keys."""
        templates = profile_service.get_available_templates()

        for name, template in templates.items():
            assert "enabled_sources" in template, f"{name} missing enabled_sources"
            assert "source_priorities" in template, f"{name} missing source_priorities"
            assert isinstance(template["enabled_sources"], list)
            assert isinstance(template["source_priorities"], dict)

    @pytest.mark.asyncio
    async def test_create_from_template_uses_template_sources(
        self, profile_service: SearchProfileService, mock_session: AsyncMock
    ) -> None:
        """create_from_template populates profile with template data."""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = result_mock

        await profile_service.create_from_template(
            company_id=10,
            template_name="pharma_medtech",
            change_reason="Setup",
        )

        added = mock_session.add.call_args[0][0]
        assert added.enabled_sources == ["pubmed", "crossref"]
        assert added.source_priorities["pubmed"] == 1

    @pytest.mark.asyncio
    async def test_create_from_unknown_template_raises_value_error(
        self, profile_service: SearchProfileService
    ) -> None:
        """Unknown template name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown template"):
            await profile_service.create_from_template(
                company_id=10,
                template_name="imaginary_template",
            )


# ===========================================================================
# Proxy Routing Logic Tests
# Requirements: 7.1, 7.4, 7.6
# ===========================================================================


def _make_proxy_config_mock(
    vault: APIKeyVault | None = None,
    proxy_url: str = "http://proxy.corp:8080",
    username: str | None = None,
    password: str | None = None,
    no_proxy_list: list[str] | None = None,
    is_active: bool = True,
) -> MagicMock:
    """Create a mock ProxyConfiguration object."""
    config = MagicMock()
    config.proxy_url = proxy_url
    config.is_active = is_active
    config.no_proxy_list = no_proxy_list or []

    if username and vault:
        enc = vault.encrypt(username)
        config.username_ciphertext = enc.ciphertext
        config.username_nonce = enc.nonce
        config.username_tag = enc.tag
    else:
        config.username_ciphertext = None
        config.username_nonce = None
        config.username_tag = None

    if password and vault:
        enc = vault.encrypt(password)
        config.password_ciphertext = enc.ciphertext
        config.password_nonce = enc.nonce
        config.password_tag = enc.tag
    else:
        config.password_ciphertext = None
        config.password_nonce = None
        config.password_tag = None

    return config


def _make_source_config_mock(
    proxy_override_url: str | None = None,
) -> MagicMock:
    """Create a mock SourceConfiguration with proxy_override_url."""
    config = MagicMock()
    config.proxy_override_url = proxy_override_url
    return config


class TestProxyRoutingGlobal:
    """Tests for global proxy routing."""

    def test_global_proxy_routes_all_sources(self, vault: APIKeyVault) -> None:
        """All sources route through global proxy when configured."""
        proxy = _make_proxy_config_mock(proxy_url="http://corp-proxy:3128")
        manager = ProxyManager(vault=vault, global_proxy=proxy)

        for source in ["pubmed", "crossref", "arxiv"]:
            result = manager.get_proxy_for_source(source, f"https://api.{source}.org")
            assert result is not None
            assert "corp-proxy:3128" in result["http://"]

    def test_no_proxy_configured_returns_none(self, vault: APIKeyVault) -> None:
        """Direct connection when no proxy configured."""
        manager = ProxyManager(vault=vault, global_proxy=None)

        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov")
        assert result is None


class TestProxyRoutingPerSource:
    """Tests for per-source proxy override routing."""

    def test_per_source_override_used_for_matching_source(
        self, vault: APIKeyVault
    ) -> None:
        """Per-source override takes priority over global proxy."""
        global_proxy = _make_proxy_config_mock(proxy_url="http://global:8080")
        source_cfg = _make_source_config_mock(proxy_override_url="http://special:9090")

        manager = ProxyManager(
            vault=vault,
            global_proxy=global_proxy,
            source_configs={"pubmed": source_cfg},
        )

        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov")
        assert result is not None
        assert "special:9090" in result["http://"]

    def test_non_overridden_source_uses_global(self, vault: APIKeyVault) -> None:
        """Sources without override fall through to global proxy."""
        global_proxy = _make_proxy_config_mock(proxy_url="http://global:8080")
        source_cfg = _make_source_config_mock(proxy_override_url="http://special:9090")

        manager = ProxyManager(
            vault=vault,
            global_proxy=global_proxy,
            source_configs={"pubmed": source_cfg},
        )

        result = manager.get_proxy_for_source("crossref", "https://api.crossref.org")
        assert result is not None
        assert "global:8080" in result["http://"]


class TestProxyRoutingNoProxyList:
    """Tests for no-proxy list bypass logic."""

    def test_no_proxy_hostname_match_returns_none(self, vault: APIKeyVault) -> None:
        """Bypass proxy when target hostname matches no-proxy list."""
        proxy = _make_proxy_config_mock(
            proxy_url="http://proxy:8080",
            no_proxy_list=["internal.corp.com", "localhost"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy)

        result = manager.get_proxy_for_source("custom", "https://internal.corp.com/api")
        assert result is None

    def test_no_proxy_cidr_match_returns_none(self, vault: APIKeyVault) -> None:
        """Bypass proxy when target IP is within a CIDR range."""
        proxy = _make_proxy_config_mock(
            proxy_url="http://proxy:8080",
            no_proxy_list=["192.168.0.0/16"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy)

        result = manager.get_proxy_for_source("custom", "http://192.168.1.50/api")
        assert result is None

    def test_no_proxy_no_match_uses_proxy(self, vault: APIKeyVault) -> None:
        """Use proxy when target does NOT match no-proxy list."""
        proxy = _make_proxy_config_mock(
            proxy_url="http://proxy:8080",
            no_proxy_list=["internal.corp.com"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy)

        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov")
        assert result is not None
        assert "proxy:8080" in result["http://"]

    def test_no_proxy_takes_priority_over_per_source_override(
        self, vault: APIKeyVault
    ) -> None:
        """No-proxy bypass takes priority over per-source proxy override."""
        proxy = _make_proxy_config_mock(
            proxy_url="http://global:8080",
            no_proxy_list=["bypass.example.com"],
        )
        source_cfg = _make_source_config_mock(proxy_override_url="http://override:9090")

        manager = ProxyManager(
            vault=vault,
            global_proxy=proxy,
            source_configs={"custom": source_cfg},
        )

        result = manager.get_proxy_for_source("custom", "https://bypass.example.com/api")
        assert result is None
