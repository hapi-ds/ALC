"""Unit tests for the ProxyManager service.

Tests cover:
- Global proxy resolution with and without credentials
- Per-source proxy override
- No-proxy list matching (hostname, IP, CIDR)
- Inactive proxy returns None
- Direct connection when no proxy configured
- Credential decryption via APIKeyVault

References:
    - Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest

from alcoabase.literature.services.api_key_vault import APIKeyVault
from alcoabase.literature.services.proxy_manager import ProxyManager


@pytest.fixture
def vault() -> APIKeyVault:
    """Create an APIKeyVault with a random master key."""
    return APIKeyVault(os.urandom(32))


def _make_proxy_config(
    vault: APIKeyVault | None = None,
    proxy_url: str = "http://proxy.corp.example.com:8080",
    username: str | None = None,
    password: str | None = None,
    no_proxy_list: list[str] | None = None,
    is_active: bool = True,
) -> MagicMock:
    """Create a mock ProxyConfiguration object.

    Args:
        vault: APIKeyVault for encrypting credentials (required if username/password set).
        proxy_url: The proxy URL.
        username: Plaintext username to encrypt.
        password: Plaintext password to encrypt.
        no_proxy_list: Hostnames/IPs to bypass.
        is_active: Whether proxy is enabled.

    Returns:
        Mock ProxyConfiguration with expected attributes.
    """
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


def _make_source_config(
    proxy_override_url: str | None = None,
) -> MagicMock:
    """Create a mock SourceConfiguration with proxy_override_url."""
    config = MagicMock()
    config.proxy_override_url = proxy_override_url
    return config


class TestNoProxyConfigured:
    """Tests when no proxy is configured at all."""

    def test_returns_none_when_no_global_proxy(self, vault: APIKeyVault) -> None:
        """Return None (direct) when no global proxy and no per-source override."""
        manager = ProxyManager(vault=vault, global_proxy=None)
        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov/entrez")
        assert result is None

    def test_returns_none_when_global_proxy_inactive(self, vault: APIKeyVault) -> None:
        """Return None when global proxy exists but is_active=False."""
        proxy_config = _make_proxy_config(is_active=False)
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)
        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov/entrez")
        assert result is None


class TestGlobalProxy:
    """Tests for global proxy resolution."""

    def test_returns_proxy_dict_without_credentials(self, vault: APIKeyVault) -> None:
        """Return httpx proxy dict when global proxy is active (no creds)."""
        proxy_config = _make_proxy_config(proxy_url="http://proxy.example.com:3128")
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("crossref", "https://api.crossref.org/works")
        assert result == {
            "http://": "http://proxy.example.com:3128",
            "https://": "http://proxy.example.com:3128",
        }

    def test_returns_proxy_dict_with_credentials(self, vault: APIKeyVault) -> None:
        """Return proxy URL with embedded credentials when configured."""
        proxy_config = _make_proxy_config(
            vault=vault,
            proxy_url="http://proxy.example.com:8080",
            username="proxyuser",
            password="s3cretP@ss",
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov")
        assert result is not None
        assert "proxyuser:s3cretP@ss@proxy.example.com:8080" in result["http://"]
        assert "proxyuser:s3cretP@ss@proxy.example.com:8080" in result["https://"]

    def test_proxy_url_preserves_scheme(self, vault: APIKeyVault) -> None:
        """Proxy URL preserves the original scheme."""
        proxy_config = _make_proxy_config(
            vault=vault,
            proxy_url="https://secure-proxy.example.com:443",
            username="user",
            password="pass",
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("arxiv", "https://arxiv.org/api")
        assert result is not None
        assert result["http://"].startswith("https://")


class TestPerSourceOverride:
    """Tests for per-source proxy overrides."""

    def test_per_source_override_takes_priority(self, vault: APIKeyVault) -> None:
        """Per-source override URL takes priority over global proxy."""
        global_proxy = _make_proxy_config(proxy_url="http://global-proxy:8080")
        source_config = _make_source_config(proxy_override_url="http://special-proxy:9090")

        manager = ProxyManager(
            vault=vault,
            global_proxy=global_proxy,
            source_configs={"pubmed": source_config},
        )

        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov")
        assert result == {
            "http://": "http://special-proxy:9090",
            "https://": "http://special-proxy:9090",
        }

    def test_other_sources_use_global(self, vault: APIKeyVault) -> None:
        """Sources without override use global proxy."""
        global_proxy = _make_proxy_config(proxy_url="http://global-proxy:8080")
        source_config = _make_source_config(proxy_override_url="http://special-proxy:9090")

        manager = ProxyManager(
            vault=vault,
            global_proxy=global_proxy,
            source_configs={"pubmed": source_config},
        )

        result = manager.get_proxy_for_source("crossref", "https://api.crossref.org")
        assert result == {
            "http://": "http://global-proxy:8080",
            "https://": "http://global-proxy:8080",
        }

    def test_per_source_override_none_uses_global(self, vault: APIKeyVault) -> None:
        """Source config without proxy_override_url falls through to global."""
        global_proxy = _make_proxy_config(proxy_url="http://global-proxy:8080")
        source_config = _make_source_config(proxy_override_url=None)

        manager = ProxyManager(
            vault=vault,
            global_proxy=global_proxy,
            source_configs={"pubmed": source_config},
        )

        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov")
        assert result == {
            "http://": "http://global-proxy:8080",
            "https://": "http://global-proxy:8080",
        }


class TestNoProxyList:
    """Tests for no-proxy list matching."""

    def test_exact_hostname_match(self, vault: APIKeyVault) -> None:
        """Return None when target hostname exactly matches no-proxy entry."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=["localhost", "internal.corp.com"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("custom", "http://internal.corp.com/api")
        assert result is None

    def test_domain_suffix_match_with_dot(self, vault: APIKeyVault) -> None:
        """Return None when target hostname matches .domain.com pattern."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=[".example.com"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("custom", "https://api.example.com/v1")
        assert result is None

    def test_domain_suffix_match_without_dot(self, vault: APIKeyVault) -> None:
        """Return None when target is a subdomain of a no-proxy entry."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=["example.com"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("custom", "https://api.example.com/v1")
        assert result is None

    def test_ip_address_exact_match(self, vault: APIKeyVault) -> None:
        """Return None when target IP matches no-proxy entry."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=["192.168.1.100"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("custom", "http://192.168.1.100:8080/api")
        assert result is None

    def test_cidr_range_match(self, vault: APIKeyVault) -> None:
        """Return None when target IP is within a CIDR range in no-proxy list."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=["10.0.0.0/8"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("custom", "http://10.1.2.3/api")
        assert result is None

    def test_cidr_range_no_match(self, vault: APIKeyVault) -> None:
        """Use proxy when target IP is outside the CIDR range."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=["10.0.0.0/8"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("custom", "http://172.16.0.1/api")
        assert result is not None
        assert result["http://"] == "http://proxy:8080"

    def test_no_proxy_case_insensitive(self, vault: APIKeyVault) -> None:
        """No-proxy matching is case-insensitive."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=["Internal.Corp.COM"],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("custom", "https://internal.corp.com/api")
        assert result is None

    def test_no_proxy_list_empty(self, vault: APIKeyVault) -> None:
        """Empty no-proxy list does not bypass proxy."""
        proxy_config = _make_proxy_config(
            proxy_url="http://proxy:8080",
            no_proxy_list=[],
        )
        manager = ProxyManager(vault=vault, global_proxy=proxy_config)

        result = manager.get_proxy_for_source("pubmed", "https://eutils.ncbi.nlm.nih.gov")
        assert result is not None

    def test_no_proxy_bypasses_before_per_source_check(self, vault: APIKeyVault) -> None:
        """No-proxy match takes priority over per-source override."""
        proxy_config = _make_proxy_config(
            proxy_url="http://global:8080",
            no_proxy_list=["internal.example.com"],
        )
        source_config = _make_source_config(proxy_override_url="http://source-proxy:9090")

        manager = ProxyManager(
            vault=vault,
            global_proxy=proxy_config,
            source_configs={"custom": source_config},
        )

        result = manager.get_proxy_for_source("custom", "https://internal.example.com/api")
        assert result is None


class TestUpdateMethods:
    """Tests for dynamic configuration updates."""

    def test_update_global_proxy(self, vault: APIKeyVault) -> None:
        """update_global_proxy changes behavior."""
        manager = ProxyManager(vault=vault, global_proxy=None)
        assert manager.get_proxy_for_source("pubmed", "https://example.com") is None

        new_proxy = _make_proxy_config(proxy_url="http://new-proxy:3128")
        manager.update_global_proxy(new_proxy)

        result = manager.get_proxy_for_source("pubmed", "https://example.com")
        assert result is not None
        assert result["http://"] == "http://new-proxy:3128"

    def test_update_source_config(self, vault: APIKeyVault) -> None:
        """update_source_config adds per-source override."""
        global_proxy = _make_proxy_config(proxy_url="http://global:8080")
        manager = ProxyManager(vault=vault, global_proxy=global_proxy)

        # Initially uses global
        result = manager.get_proxy_for_source("pubmed", "https://example.com")
        assert result["http://"] == "http://global:8080"

        # Add per-source override
        source_config = _make_source_config(proxy_override_url="http://special:9090")
        manager.update_source_config("pubmed", source_config)

        result = manager.get_proxy_for_source("pubmed", "https://example.com")
        assert result["http://"] == "http://special:9090"

    def test_remove_source_config(self, vault: APIKeyVault) -> None:
        """update_source_config with None removes override."""
        global_proxy = _make_proxy_config(proxy_url="http://global:8080")
        source_config = _make_source_config(proxy_override_url="http://special:9090")

        manager = ProxyManager(
            vault=vault,
            global_proxy=global_proxy,
            source_configs={"pubmed": source_config},
        )

        manager.update_source_config("pubmed", None)
        result = manager.get_proxy_for_source("pubmed", "https://example.com")
        assert result["http://"] == "http://global:8080"
