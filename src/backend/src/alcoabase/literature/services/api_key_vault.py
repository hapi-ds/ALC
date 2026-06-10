"""AES-256-GCM encryption service for API keys at rest.

Provides secure encryption and decryption of API keys stored in the database.
Keys are encrypted using AES-256-GCM with a unique 12-byte nonce per encryption
operation. The GCM authentication tag provides integrity verification.

References:
    - Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6

See also:
    https://cryptography.io/en/latest/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from alcoabase.literature.exceptions import EncryptionKeyMissingError


@dataclass(frozen=True)
class EncryptedKey:
    """Stored representation of an encrypted API key.

    All fields are base64-encoded strings suitable for database storage.

    Attributes:
        ciphertext: AES-256-GCM encrypted key bytes (base64-encoded).
        nonce: 12-byte GCM nonce (base64-encoded).
        tag: 16-byte GCM authentication tag (base64-encoded).
    """

    ciphertext: str
    nonce: str
    tag: str


class APIKeyVault:
    """Manages encryption and decryption of API keys using AES-256-GCM.

    The master key is derived from the ``ALC_LITERATURE_ENCRYPTION_KEY``
    environment variable. Keys are only decrypted at the moment of
    outbound request construction, held in memory for minimum duration.

    Example:
        >>> master_key = os.urandom(32)
        >>> vault = APIKeyVault(master_key)
        >>> encrypted = vault.encrypt("sk-my-secret-key")
        >>> vault.decrypt(encrypted)
        'sk-my-secret-key'
    """

    def __init__(self, master_key: bytes) -> None:
        """Initialize vault with the master encryption key.

        Args:
            master_key: 32-byte AES-256 key derived from env var.

        Raises:
            ValueError: If master_key is not exactly 32 bytes.
        """
        if len(master_key) != 32:
            raise ValueError(
                f"Master key must be exactly 32 bytes, got {len(master_key)} bytes."
            )
        self._master_key = master_key
        self._aesgcm = AESGCM(master_key)

    def encrypt(self, plaintext_key: str) -> EncryptedKey:
        """Encrypt an API key using AES-256-GCM.

        Generates a random 12-byte nonce per call to ensure unique
        ciphertexts even for identical plaintext keys.

        Args:
            plaintext_key: The API key to encrypt (1–512 characters).

        Returns:
            EncryptedKey containing base64-encoded ciphertext, nonce, and tag.
        """
        nonce = os.urandom(12)
        # AESGCM.encrypt appends the 16-byte GCM tag to the ciphertext
        encrypted = self._aesgcm.encrypt(nonce, plaintext_key.encode(), None)

        # Split: actual ciphertext is everything except the last 16 bytes (tag)
        actual_ciphertext = encrypted[:-16]
        tag = encrypted[-16:]

        return EncryptedKey(
            ciphertext=base64.b64encode(actual_ciphertext).decode(),
            nonce=base64.b64encode(nonce).decode(),
            tag=base64.b64encode(tag).decode(),
        )

    def decrypt(self, encrypted: EncryptedKey) -> str:
        """Decrypt an API key from its stored representation.

        Verifies integrity via the GCM authentication tag before
        returning the plaintext.

        Args:
            encrypted: The EncryptedKey to decrypt.

        Returns:
            The original plaintext API key.

        Raises:
            cryptography.exceptions.InvalidTag: If the ciphertext has been
                tampered with or the tag/nonce is incorrect.
        """
        nonce = base64.b64decode(encrypted.nonce)
        ciphertext = base64.b64decode(encrypted.ciphertext)
        tag = base64.b64decode(encrypted.tag)

        # Reassemble: AESGCM.decrypt expects ciphertext + tag concatenated
        data = ciphertext + tag
        plaintext_bytes = self._aesgcm.decrypt(nonce, data, None)

        return plaintext_bytes.decode()

    @staticmethod
    def mask_key(plaintext_key: str) -> str:
        """Return a masked representation showing only last 4 characters.

        Used for API responses to avoid exposing full key values.

        Args:
            plaintext_key: The key to mask.

        Returns:
            String like ``"****abcd"`` (asterisks + last 4 chars).
            For keys shorter than 4 chars, returns all asterisks.
        """
        if len(plaintext_key) < 4:
            return "*" * len(plaintext_key)
        return "*" * (len(plaintext_key) - 4) + plaintext_key[-4:]

    @staticmethod
    def from_env(env_var_name: str = "ALC_LITERATURE_ENCRYPTION_KEY") -> "APIKeyVault":
        """Create an APIKeyVault from the environment variable.

        Convenience factory that reads the master key from the specified
        environment variable and validates it.

        Args:
            env_var_name: Name of the environment variable containing the
                base64-encoded 32-byte master key.

        Returns:
            Configured APIKeyVault instance.

        Raises:
            EncryptionKeyMissingError: If the environment variable is not set.
            ValueError: If the decoded key is not exactly 32 bytes.
        """
        raw_value = os.environ.get(env_var_name)
        if not raw_value:
            raise EncryptionKeyMissingError(
                f"Master encryption key environment variable '{env_var_name}' is not set.",
                env_var_name=env_var_name,
            )
        master_key = base64.b64decode(raw_value)
        return APIKeyVault(master_key)
