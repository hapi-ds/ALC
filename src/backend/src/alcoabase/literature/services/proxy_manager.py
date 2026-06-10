"""Proxy configuration management for outbound literature API requests.

Resolves proxy settings for each source adapter based on the following
priority order:
    1. Per-source proxy override URL from SourceConfiguration
    2. Global proxy from ProxyConfiguration model
    3. No proxy (direct connection)

Handles no-proxy list matching (hostname and IP range), proxy credential
decryption via APIKeyVault, and returns httpx-compatible proxy config dicts.

References:
    - Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7
"""

from __future__ import annotations

import ipaddress
import logging
from urllib.parse import urlparse

from alcoabase.literature.models.literature import (
    ProxyConfiguration,
    SourceConfiguration,
)
from alcoabase.literature.services.api_key_vault import APIKeyVault, EncryptedKey

logger = logging.getLogger(__name__)


class ProxyManager:
    """Manages proxy configuration resolution for outbound requests.

    Resolves which proxy (if any) should be used for a given source adapter
    and target URL. Supports global proxy, per-source overrides, and a
    no-proxy list for direct connections.

    Attributes:
        _vault: APIKeyVault for decrypting proxy credentials.
        _global_proxy: Global ProxyConfiguration from the database.
        _source_configs: Mapping of source_adapter_name to SourceConfiguration.
    """

    def __init__(
        self,
        vault: APIKeyVault,
        global_proxy: ProxyConfiguration | None = None,
        source_configs: dict[str, SourceConfiguration] | None = None,
    ) -> None:
        """Initialize ProxyManager with dependencies.

        Args:
            vault: APIKeyVault instance for decrypting proxy credentials.
            global_proxy: Global proxy configuration (may be None if not set).
            source_configs: Mapping of source names to their configurations.
        """
        self._vault = vault
        self._global_proxy = global_proxy
        self._source_configs = source_configs or {}

    def update_global_proxy(self, proxy_config: ProxyConfiguration | None) -> None:
        """Update the global proxy configuration.

        Args:
            proxy_config: New global proxy configuration, or None to disable.
        """
        self._global_proxy = proxy_config

    def update_source_config(
        self, source_name: str, config: SourceConfiguration | None
    ) -> None:
        """Update or remove a source-specific configuration.

        Args:
            source_name: Name of the source adapter.
            config: New configuration, or None to remove.
        """
        if config is None:
            self._source_configs.pop(source_name, None)
        else:
            self._source_configs[source_name] = config

    def get_proxy_for_source(
        self, source_name: str, target_url: str
    ) -> dict[str, str] | None:
        """Resolve the proxy configuration for a given source and target.

        Resolution order:
            1. If target hostname/IP matches the no-proxy list → None (direct)
            2. Per-source proxy_override_url from SourceConfiguration
            3. Global proxy from ProxyConfiguration (if is_active=True)
            4. None (direct connection)

        Args:
            source_name: Name of the source adapter making the request.
            target_url: The target URL being requested.

        Returns:
            httpx proxy config dict like ``{"http://": url, "https://": url}``
            or None for direct connection.
        """
        # Step 1: Check if target matches no-proxy list (global config)
        if self._global_proxy is not None and self._global_proxy.is_active:
            if self._matches_no_proxy_list(
                target_url, self._global_proxy.no_proxy_list
            ):
                logger.debug(
                    "Target %s matches no-proxy list, using direct connection.",
                    target_url,
                )
                return None

        # Step 2: Check per-source proxy override
        source_config = self._source_configs.get(source_name)
        if source_config is not None and source_config.proxy_override_url:
            logger.debug(
                "Using per-source proxy override for %s: %s",
                source_name,
                source_config.proxy_override_url,
            )
            return self._build_proxy_dict(source_config.proxy_override_url)

        # Step 3: Use global proxy (if configured and active)
        if self._global_proxy is not None and self._global_proxy.is_active:
            proxy_url = self._resolve_global_proxy_url()
            logger.debug(
                "Using global proxy for %s: %s",
                source_name,
                self._global_proxy.proxy_url,
            )
            return self._build_proxy_dict(proxy_url)

        # Step 4: No proxy configured or proxy is inactive
        logger.debug(
            "No proxy configured for %s, using direct connection.", source_name
        )
        return None

    def _resolve_global_proxy_url(self) -> str:
        """Build the full proxy URL with decrypted credentials if present.

        Returns:
            Proxy URL, potentially with embedded credentials
            (e.g., ``http://user:pass@proxy_host:port``).
        """
        if self._global_proxy is None:
            return ""

        proxy_url = self._global_proxy.proxy_url

        # Check if credentials are configured
        has_username = (
            self._global_proxy.username_ciphertext is not None
            and self._global_proxy.username_nonce is not None
            and self._global_proxy.username_tag is not None
        )
        has_password = (
            self._global_proxy.password_ciphertext is not None
            and self._global_proxy.password_nonce is not None
            and self._global_proxy.password_tag is not None
        )

        if not has_username or not has_password:
            return proxy_url

        # Decrypt credentials
        username = self._vault.decrypt(
            EncryptedKey(
                ciphertext=self._global_proxy.username_ciphertext,
                nonce=self._global_proxy.username_nonce,
                tag=self._global_proxy.username_tag,
            )
        )
        password = self._vault.decrypt(
            EncryptedKey(
                ciphertext=self._global_proxy.password_ciphertext,
                nonce=self._global_proxy.password_nonce,
                tag=self._global_proxy.password_tag,
            )
        )

        # Insert credentials into the proxy URL
        return self._embed_credentials_in_url(proxy_url, username, password)

    @staticmethod
    def _embed_credentials_in_url(
        proxy_url: str, username: str, password: str
    ) -> str:
        """Embed username:password into a proxy URL.

        Args:
            proxy_url: Base proxy URL (e.g., ``http://proxy.example.com:8080``).
            username: Decrypted proxy username.
            password: Decrypted proxy password.

        Returns:
            URL with embedded credentials
            (e.g., ``http://user:pass@proxy.example.com:8080``).
        """
        parsed = urlparse(proxy_url)
        # Reconstruct with credentials
        netloc = f"{username}:{password}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return parsed._replace(netloc=netloc).geturl()

    @staticmethod
    def _build_proxy_dict(proxy_url: str) -> dict[str, str]:
        """Build an httpx-compatible proxy configuration dict.

        Args:
            proxy_url: The resolved proxy URL.

        Returns:
            Dict mapping protocol schemes to the proxy URL.
        """
        return {
            "http://": proxy_url,
            "https://": proxy_url,
        }

    @staticmethod
    def _matches_no_proxy_list(target_url: str, no_proxy_list: list[str]) -> bool:
        """Check if a target URL matches any entry in the no-proxy list.

        Supports:
            - Exact hostname matching (case-insensitive)
            - Suffix matching for domain names (e.g., ``.example.com``)
            - IP address matching
            - CIDR range matching (e.g., ``192.168.1.0/24``)

        Args:
            target_url: The URL being requested.
            no_proxy_list: List of hostnames, IPs, or CIDR ranges to bypass.

        Returns:
            True if the target matches any no-proxy entry (use direct connection).
        """
        if not no_proxy_list:
            return False

        parsed = urlparse(target_url)
        target_host = parsed.hostname
        if not target_host:
            return False

        target_host_lower = target_host.lower()

        # Try to parse the target host as an IP address
        target_ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = None
        try:
            target_ip = ipaddress.ip_address(target_host)
        except ValueError:
            pass

        for entry in no_proxy_list:
            entry = entry.strip()
            if not entry:
                continue

            entry_lower = entry.lower()

            # Check CIDR range match
            if "/" in entry and target_ip is not None:
                try:
                    network = ipaddress.ip_network(entry, strict=False)
                    if target_ip in network:
                        return True
                except ValueError:
                    pass
                continue

            # Check IP address match
            if target_ip is not None:
                try:
                    entry_ip = ipaddress.ip_address(entry)
                    if target_ip == entry_ip:
                        return True
                except ValueError:
                    pass

            # Check hostname exact match
            if target_host_lower == entry_lower:
                return True

            # Check domain suffix match (e.g., ".example.com" matches
            # "api.example.com")
            if entry_lower.startswith("."):
                if target_host_lower.endswith(entry_lower):
                    return True
            else:
                # Also match as suffix without leading dot
                # e.g., "example.com" matches "api.example.com"
                if target_host_lower.endswith("." + entry_lower):
                    return True

        return False
