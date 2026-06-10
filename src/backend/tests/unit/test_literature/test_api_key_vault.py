"""Unit tests for the APIKeyVault encryption service.

Tests cover:
- Encryption/decryption round-trip
- Master key validation
- Key masking logic
- EncryptionKeyMissingError on missing env var
- Tampered ciphertext detection
"""

from __future__ import annotations

import base64
import os

import pytest
from cryptography.exceptions import InvalidTag

from alcoabase.literature.exceptions import EncryptionKeyMissingError
from alcoabase.literature.services.api_key_vault import APIKeyVault, EncryptedKey


@pytest.fixture
def master_key() -> bytes:
    """Generate a valid 32-byte master key for tests."""
    return os.urandom(32)


@pytest.fixture
def vault(master_key: bytes) -> APIKeyVault:
    """Create an APIKeyVault instance with a test master key."""
    return APIKeyVault(master_key)


class TestAPIKeyVaultInit:
    """Tests for APIKeyVault initialization."""

    def test_valid_32_byte_key(self, master_key: bytes) -> None:
        """Accept exactly 32-byte master key."""
        vault = APIKeyVault(master_key)
        assert vault is not None

    def test_reject_short_key(self) -> None:
        """Raise ValueError for key shorter than 32 bytes."""
        with pytest.raises(ValueError, match="exactly 32 bytes"):
            APIKeyVault(b"too-short")

    def test_reject_long_key(self) -> None:
        """Raise ValueError for key longer than 32 bytes."""
        with pytest.raises(ValueError, match="exactly 32 bytes"):
            APIKeyVault(os.urandom(64))

    def test_reject_empty_key(self) -> None:
        """Raise ValueError for empty key."""
        with pytest.raises(ValueError, match="exactly 32 bytes"):
            APIKeyVault(b"")


class TestEncrypt:
    """Tests for the encrypt method."""

    def test_returns_encrypted_key_dataclass(self, vault: APIKeyVault) -> None:
        """encrypt() returns an EncryptedKey with all fields populated."""
        result = vault.encrypt("test-api-key")
        assert isinstance(result, EncryptedKey)
        assert result.ciphertext
        assert result.nonce
        assert result.tag

    def test_all_fields_are_base64(self, vault: APIKeyVault) -> None:
        """All EncryptedKey fields should be valid base64 strings."""
        result = vault.encrypt("my-secret-key-123")
        # These should not raise
        base64.b64decode(result.ciphertext)
        base64.b64decode(result.nonce)
        base64.b64decode(result.tag)

    def test_nonce_is_12_bytes(self, vault: APIKeyVault) -> None:
        """Nonce should decode to exactly 12 bytes."""
        result = vault.encrypt("key")
        nonce_bytes = base64.b64decode(result.nonce)
        assert len(nonce_bytes) == 12

    def test_tag_is_16_bytes(self, vault: APIKeyVault) -> None:
        """GCM tag should decode to exactly 16 bytes."""
        result = vault.encrypt("key")
        tag_bytes = base64.b64decode(result.tag)
        assert len(tag_bytes) == 16

    def test_unique_nonce_per_call(self, vault: APIKeyVault) -> None:
        """Each encryption should produce a different nonce."""
        r1 = vault.encrypt("same-key")
        r2 = vault.encrypt("same-key")
        assert r1.nonce != r2.nonce

    def test_unique_ciphertext_per_call(self, vault: APIKeyVault) -> None:
        """Encrypting the same key twice should produce different ciphertexts."""
        r1 = vault.encrypt("same-key")
        r2 = vault.encrypt("same-key")
        assert r1.ciphertext != r2.ciphertext


class TestDecrypt:
    """Tests for the decrypt method."""

    def test_round_trip_simple(self, vault: APIKeyVault) -> None:
        """Encrypt then decrypt should return original key."""
        original = "sk-test-key-12345"
        encrypted = vault.encrypt(original)
        assert vault.decrypt(encrypted) == original

    def test_round_trip_unicode(self, vault: APIKeyVault) -> None:
        """Round-trip works with Unicode characters."""
        original = "api-key-日本語-émojis-🔑"
        encrypted = vault.encrypt(original)
        assert vault.decrypt(encrypted) == original

    def test_round_trip_long_key(self, vault: APIKeyVault) -> None:
        """Round-trip works with maximum-length keys."""
        original = "x" * 512
        encrypted = vault.encrypt(original)
        assert vault.decrypt(encrypted) == original

    def test_round_trip_single_char(self, vault: APIKeyVault) -> None:
        """Round-trip works with single character."""
        original = "a"
        encrypted = vault.encrypt(original)
        assert vault.decrypt(encrypted) == original

    def test_tampered_ciphertext_raises(self, vault: APIKeyVault) -> None:
        """Modifying ciphertext should raise InvalidTag."""
        encrypted = vault.encrypt("my-key")
        # Tamper with ciphertext
        raw = base64.b64decode(encrypted.ciphertext)
        tampered = bytes([b ^ 0xFF for b in raw])
        tampered_enc = EncryptedKey(
            ciphertext=base64.b64encode(tampered).decode(),
            nonce=encrypted.nonce,
            tag=encrypted.tag,
        )
        with pytest.raises(InvalidTag):
            vault.decrypt(tampered_enc)

    def test_tampered_tag_raises(self, vault: APIKeyVault) -> None:
        """Modifying the tag should raise InvalidTag."""
        encrypted = vault.encrypt("my-key")
        raw_tag = base64.b64decode(encrypted.tag)
        tampered_tag = bytes([b ^ 0xFF for b in raw_tag])
        tampered_enc = EncryptedKey(
            ciphertext=encrypted.ciphertext,
            nonce=encrypted.nonce,
            tag=base64.b64encode(tampered_tag).decode(),
        )
        with pytest.raises(InvalidTag):
            vault.decrypt(tampered_enc)

    def test_wrong_key_raises(self, master_key: bytes) -> None:
        """Decrypting with a different master key should fail."""
        vault1 = APIKeyVault(master_key)
        vault2 = APIKeyVault(os.urandom(32))

        encrypted = vault1.encrypt("secret")
        with pytest.raises(InvalidTag):
            vault2.decrypt(encrypted)


class TestMaskKey:
    """Tests for the mask_key static method."""

    def test_long_key_shows_last_4(self) -> None:
        """Keys >= 4 chars show asterisks + last 4."""
        assert APIKeyVault.mask_key("abcdefgh") == "****efgh"

    def test_exactly_4_chars(self) -> None:
        """4-char key returns the key itself (0 asterisks + 4 chars)."""
        assert APIKeyVault.mask_key("abcd") == "abcd"

    def test_short_key_all_asterisks(self) -> None:
        """Keys < 4 chars return all asterisks."""
        assert APIKeyVault.mask_key("abc") == "***"
        assert APIKeyVault.mask_key("ab") == "**"
        assert APIKeyVault.mask_key("a") == "*"

    def test_empty_key(self) -> None:
        """Empty key returns empty string."""
        assert APIKeyVault.mask_key("") == ""

    def test_mask_preserves_length(self) -> None:
        """Masked output has same length as input."""
        key = "sk-live-abc123def456"
        masked = APIKeyVault.mask_key(key)
        assert len(masked) == len(key)


class TestFromEnv:
    """Tests for the from_env factory method."""

    def test_missing_env_var_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raise EncryptionKeyMissingError when env var not set."""
        monkeypatch.delenv("ALC_LITERATURE_ENCRYPTION_KEY", raising=False)
        with pytest.raises(EncryptionKeyMissingError) as exc_info:
            APIKeyVault.from_env()
        assert exc_info.value.env_var_name == "ALC_LITERATURE_ENCRYPTION_KEY"

    def test_valid_env_var_creates_vault(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Successfully create vault from valid base64-encoded env var."""
        key = os.urandom(32)
        encoded = base64.b64encode(key).decode()
        monkeypatch.setenv("ALC_LITERATURE_ENCRYPTION_KEY", encoded)

        vault = APIKeyVault.from_env()
        # Verify it works
        encrypted = vault.encrypt("test")
        assert vault.decrypt(encrypted) == "test"

    def test_empty_env_var_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Raise EncryptionKeyMissingError when env var is empty string."""
        monkeypatch.setenv("ALC_LITERATURE_ENCRYPTION_KEY", "")
        with pytest.raises(EncryptionKeyMissingError):
            APIKeyVault.from_env()
