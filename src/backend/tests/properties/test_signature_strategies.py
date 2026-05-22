"""Property-based tests for Signing Strategy Pattern.

Tests Properties 10, 11, 12 from the Electronic Signatures UI design document.

Property 10: Signing strategy selection — factory returns correct strategy based on mode
Property 11: Hash signature round-trip integrity — sign then verify returns valid;
             tamper then verify returns invalid
Property 12: Configuration validation — missing key/cert raises error in pades mode

References:
    - Design: .kiro/specs/Step_3-4_electronic-signatures-ui/design.md
    - Requirements: 11.1, 11.2, 11.3, 11.7, 11.9, 11.11
"""

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st
from datetime import datetime, timezone
from unittest.mock import MagicMock

from alcoabase.services.signing_strategies import (
    HashSigningStrategy,
    PAdESSigningStrategy,
    SIGNATURE_MARKER_START,
    SIGNATURE_MARKER_END,
    SignatureStamp,
    VerificationResult,
    create_signing_strategy,
)
from alcoabase.config import Settings


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for generating PDF-like byte sequences (non-empty).
# Excludes bytes that happen to contain the signature marker magic bytes,
# since those would be misinterpreted as pre-existing signature blocks.
pdf_bytes_strategy = st.binary(min_size=10, max_size=1000).filter(
    lambda b: SIGNATURE_MARKER_START not in b and SIGNATURE_MARKER_END not in b
)

# Strategy for signer names (non-empty, non-whitespace-only)
signer_name_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
).filter(lambda s: s.strip())

# Strategy for reasons (non-empty, non-whitespace-only)
reason_strategy = st.text(
    min_size=1,
    max_size=100,
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
).filter(lambda s: s.strip())

# Strategy for transitions (non-empty, non-whitespace-only)
transition_strategy = st.text(
    min_size=1,
    max_size=50,
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
).filter(lambda s: s.strip())


# ---------------------------------------------------------------------------
# Property 10: Signing strategy selection
# ---------------------------------------------------------------------------


class TestSigningStrategySelection:
    """Property tests for signing strategy factory selection logic.

    For any value of signature_mode, the factory returns PAdESSigningStrategy
    iff mode == "pades" (with valid paths), HashSigningStrategy otherwise.

    **Validates: Requirements 11.1, 11.7**
    """

    # Feature: Step_3-4_electronic-signatures-ui, Property 10: Signing strategy selection
    @settings(max_examples=100, deadline=None)
    @given(mode=st.just("hash"))
    def test_hash_mode_returns_hash_strategy(self, mode: str) -> None:
        """When mode is "hash", factory returns HashSigningStrategy.

        **Validates: Requirements 11.1, 11.7**
        """
        settings_obj = Settings(
            SIGNATURE_MODE=mode,
            SIGNATURE_KEY_PATH=None,
            SIGNATURE_CERT_PATH=None,
        )
        strategy = create_signing_strategy(settings_obj)
        assert isinstance(strategy, HashSigningStrategy)

    # Feature: Step_3-4_electronic-signatures-ui, Property 10: Signing strategy selection
    @settings(max_examples=100, deadline=None)
    @given(
        mode=st.text(min_size=0, max_size=20).filter(lambda s: s != "pades")
    )
    def test_non_pades_mode_returns_hash_strategy(self, mode: str) -> None:
        """When mode is anything other than "pades", factory returns HashSigningStrategy.

        For any string that is not exactly "pades", the factory SHALL return
        a HashSigningStrategy instance.

        **Validates: Requirements 11.1, 11.7**
        """
        # Use a MagicMock for settings since the real Settings class validates
        # signature_mode as Literal["pades", "hash"]. The factory function only
        # checks `settings.signature_mode == "pades"` — anything else returns
        # HashSigningStrategy.
        settings_obj = MagicMock()
        settings_obj.signature_mode = mode
        settings_obj.signature_key_path = None
        settings_obj.signature_cert_path = None

        strategy = create_signing_strategy(settings_obj)
        assert isinstance(strategy, HashSigningStrategy), (
            f"Expected HashSigningStrategy for mode='{mode}', "
            f"got {type(strategy).__name__}"
        )


# ---------------------------------------------------------------------------
# Property 11: Hash signature round-trip integrity (HashSigningStrategy)
# ---------------------------------------------------------------------------


class TestHashSignatureRoundTrip:
    """Property tests for HashSigningStrategy sign/verify round-trip.

    For any valid PDF byte sequence and signing parameters:
    - Signing and then verifying returns is_valid=True with exactly 1 signature
    - Modifying any byte AFTER signing causes verify to return is_valid=False
    - Signature count equals the number of times sign_pdf was called

    **Validates: Requirements 11.2, 11.9**
    """

    # Feature: Step_3-4_electronic-signatures-ui, Property 11: Hash signature round-trip integrity
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        pdf_bytes=pdf_bytes_strategy,
        signer_name=signer_name_strategy,
        reason=reason_strategy,
        transition=transition_strategy,
    )
    def test_sign_then_verify_returns_valid(
        self,
        pdf_bytes: bytes,
        signer_name: str,
        reason: str,
        transition: str,
    ) -> None:
        """For any valid PDF bytes and signing parameters, signing and then
        verifying returns is_valid=True with exactly 1 signature.

        **Validates: Requirements 11.2, 11.9**
        """
        strategy = HashSigningStrategy()
        stamp = SignatureStamp(
            signer_name=signer_name,
            signed_at=datetime.now(timezone.utc),
            reason=reason,
            transition=transition,
        )

        signed_pdf, signature_hash = strategy.sign_pdf(pdf_bytes, stamp)
        result = strategy.verify_pdf(signed_pdf)

        assert result.is_valid, (
            f"Signed PDF should verify as valid. "
            f"Got is_valid=False with {result.signature_count} signatures"
        )
        assert result.signature_count == 1, (
            f"Expected exactly 1 signature, got {result.signature_count}"
        )
        assert len(result.signatures) == 1
        assert result.signatures[0].signer_name == signer_name
        assert result.signatures[0].reason == reason
        assert result.signatures[0].is_valid
        assert signature_hash != "", "Signature hash should not be empty"

    # Feature: Step_3-4_electronic-signatures-ui, Property 11: Hash signature round-trip integrity
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        pdf_bytes=pdf_bytes_strategy,
        signer_name=signer_name_strategy,
        reason=reason_strategy,
        transition=transition_strategy,
        modification_offset=st.integers(min_value=0),
        modification_byte=st.integers(min_value=0, max_value=255),
    )
    def test_byte_modification_invalidates_signature(
        self,
        pdf_bytes: bytes,
        signer_name: str,
        reason: str,
        transition: str,
        modification_offset: int,
        modification_byte: int,
    ) -> None:
        """For any signed PDF, modifying any byte in the content before the
        signature block causes verify to return is_valid=False.

        **Validates: Requirements 11.2, 11.9**
        """
        strategy = HashSigningStrategy()
        stamp = SignatureStamp(
            signer_name=signer_name,
            signed_at=datetime.now(timezone.utc),
            reason=reason,
            transition=transition,
        )

        signed_pdf, _ = strategy.sign_pdf(pdf_bytes, stamp)

        # Modify a byte in the original content area (before the signature block)
        # The original content occupies bytes [0, len(pdf_bytes))
        actual_offset = modification_offset % len(pdf_bytes)
        original_byte = signed_pdf[actual_offset]

        # Ensure we actually change the byte
        new_byte = modification_byte % 256
        if new_byte == original_byte:
            new_byte = (original_byte + 1) % 256

        # Create tampered PDF
        tampered_pdf = bytearray(signed_pdf)
        tampered_pdf[actual_offset] = new_byte
        tampered_pdf = bytes(tampered_pdf)

        # Verify the tampered PDF fails verification
        tampered_result = strategy.verify_pdf(tampered_pdf)
        assert not tampered_result.is_valid, (
            f"Tampered PDF should fail verification. "
            f"Modified byte at offset {actual_offset} from {original_byte} to {new_byte}"
        )

    # Feature: Step_3-4_electronic-signatures-ui, Property 11: Hash signature round-trip integrity
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        pdf_bytes=pdf_bytes_strategy,
        num_signatures=st.integers(min_value=1, max_value=5),
    )
    def test_signature_count_equals_sign_calls(
        self,
        pdf_bytes: bytes,
        num_signatures: int,
    ) -> None:
        """For any signed PDF, the signature_count equals the number of times
        sign_pdf was called.

        **Validates: Requirements 11.2, 11.9**
        """
        strategy = HashSigningStrategy()
        current_pdf = pdf_bytes

        for i in range(num_signatures):
            stamp = SignatureStamp(
                signer_name=f"Signer {i + 1}",
                signed_at=datetime.now(timezone.utc),
                reason=f"Reason {i + 1}",
                transition=f"State{i}\u2192State{i + 1}",
            )
            current_pdf, _ = strategy.sign_pdf(current_pdf, stamp)

        result = strategy.verify_pdf(current_pdf)
        assert result.is_valid, "All signatures should be valid"
        assert result.signature_count == num_signatures, (
            f"Expected {num_signatures} signatures, got {result.signature_count}"
        )
        assert len(result.signatures) == num_signatures


# ---------------------------------------------------------------------------
# Property 12: Configuration validation
# ---------------------------------------------------------------------------


class TestConfigurationValidation:
    """Property tests for configuration validation at startup.

    When SIGNATURE_MODE is "pades", the factory SHALL raise RuntimeError
    if key_path or cert_path is None.

    **Validates: Requirements 11.3, 11.11**
    """

    # Feature: Step_3-4_electronic-signatures-ui, Property 12: Configuration validation
    @settings(max_examples=100, deadline=None)
    @given(
        cert_path=st.one_of(st.just(None), st.text(min_size=1, max_size=50)),
    )
    def test_pades_mode_raises_when_key_path_is_none(
        self, cert_path: str | None
    ) -> None:
        """create_signing_strategy raises RuntimeError when mode is "pades"
        but key_path is None.

        **Validates: Requirements 11.3, 11.11**
        """
        settings_obj = MagicMock()
        settings_obj.signature_mode = "pades"
        settings_obj.signature_key_path = None
        settings_obj.signature_cert_path = cert_path
        settings_obj.signature_key_password = None
        settings_obj.signature_tsa_url = None

        with pytest.raises(RuntimeError, match="SIGNATURE_KEY_PATH"):
            create_signing_strategy(settings_obj)

    # Feature: Step_3-4_electronic-signatures-ui, Property 12: Configuration validation
    @settings(max_examples=100, deadline=None)
    @given(
        key_path=st.text(min_size=1, max_size=50),
    )
    def test_pades_mode_raises_when_cert_path_is_none(
        self, key_path: str
    ) -> None:
        """create_signing_strategy raises RuntimeError when mode is "pades"
        but cert_path is None.

        **Validates: Requirements 11.3, 11.11**
        """
        settings_obj = MagicMock()
        settings_obj.signature_mode = "pades"
        settings_obj.signature_key_path = key_path
        settings_obj.signature_cert_path = None
        settings_obj.signature_key_password = None
        settings_obj.signature_tsa_url = None

        with pytest.raises(RuntimeError, match="SIGNATURE_CERT_PATH"):
            create_signing_strategy(settings_obj)
