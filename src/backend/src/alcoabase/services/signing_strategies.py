"""Signing Strategy Pattern for electronic signatures.

This module implements the Strategy pattern for PDF signing operations,
allowing the system to switch between:
- HashSigningStrategy: SHA-256 hash-based signing for development/testing
- PAdESSigningStrategy: Real cryptographic PAdES-B-LT signing with pyHanko + x.509

The factory function `create_signing_strategy` selects the appropriate strategy
based on the SIGNATURE_MODE configuration setting.

References:
    - Design doc: Signing Strategy Pattern (class diagram)
    - CFR 21 Part 11: Electronic records and signatures
    - PAdES: PDF Advanced Electronic Signatures standard
"""

import hashlib
import io
import logging
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from alcoabase.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Conditional pyHanko imports
# ---------------------------------------------------------------------------

try:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.fields import SigFieldSpec, SigSeedSubFilter
    from pyhanko.sign.signers.pdf_cms import SimpleSigner
    from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata, PdfSigner
    from pyhanko.sign.timestamps.requests_client import HTTPTimeStamper
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko.stamp import TextStampStyle

    PYHANKO_AVAILABLE = True
except ImportError:
    PYHANKO_AVAILABLE = False
    logger.warning(
        "pyHanko is not installed. PAdES signing mode will not be available. "
        "Install pyhanko to enable production cryptographic signatures."
    )


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CertificateInfo:
    """Certificate information from a PAdES signature.

    Attributes:
        subject: Distinguished name of the certificate subject
                 (e.g., "CN=John Doe, O=ALC Corp, C=DE").
        issuer: Distinguished name of the certificate issuer
                (e.g., "CN=ALC Internal CA, O=ALC Corp, C=DE").
        serial: Hex string of the certificate serial number.
    """

    subject: str
    issuer: str
    serial: str


@dataclass
class SignatureStamp:
    """Visual signature stamp data.

    Attributes:
        signer_name: Full name of the signer.
        signed_at: UTC timestamp of the signing event.
        reason: Transition-specific reason for the signature.
        transition: The workflow transition that triggered signing.
    """

    signer_name: str
    signed_at: datetime
    reason: str
    transition: str


@dataclass
class VerificationEntry:
    """Individual signature verification result.

    Attributes:
        signer_name: Full name of the signer.
        signed_at: UTC timestamp of the signing event.
        reason: Reason for the signature.
        is_valid: Whether this signature is still valid (not tampered).
        certificate_subject: Certificate subject DN (PAdES mode only).
        certificate_issuer: Certificate issuer DN (PAdES mode only).
    """

    signer_name: str
    signed_at: datetime
    reason: str
    is_valid: bool
    certificate_subject: str | None = None
    certificate_issuer: str | None = None


@dataclass
class VerificationResult:
    """Result of verifying all signatures on a PDF.

    Attributes:
        is_valid: Whether all signatures are valid.
        signature_count: Total number of signatures found.
        signatures: List of individual verification entries.
        tampered_from_index: Index of first invalid signature (-1 if all valid).
    """

    is_valid: bool
    signature_count: int
    signatures: list[VerificationEntry]
    tampered_from_index: int = -1


# ---------------------------------------------------------------------------
# Signature marker constants
# ---------------------------------------------------------------------------

# Magic bytes to identify signature blocks in the PDF
SIGNATURE_MARKER_START = b"\x00\x01ALCOA_SIG_START\x00"
SIGNATURE_MARKER_END = b"\x00\x01ALCOA_SIG_END\x00"


# ---------------------------------------------------------------------------
# Abstract Base Class
# ---------------------------------------------------------------------------


class SigningStrategy(ABC):
    """Abstract base class for signing strategies.

    Defines the interface that all signing strategies must implement,
    enabling the system to switch between hash-based (development) and
    PAdES (production) signing without changing the calling code.
    """

    @abstractmethod
    def sign_pdf(self, pdf_bytes: bytes, stamp: SignatureStamp) -> tuple[bytes, str]:
        """Sign a PDF and return (signed_pdf_bytes, signature_hash).

        Args:
            pdf_bytes: The PDF content to sign.
            stamp: The signature stamp metadata.

        Returns:
            Tuple of (signed_pdf_bytes, signature_hash).
        """
        ...

    @abstractmethod
    def verify_pdf(self, pdf_bytes: bytes) -> VerificationResult:
        """Verify all signatures on a PDF.

        Args:
            pdf_bytes: The complete PDF bytes with signatures.

        Returns:
            VerificationResult with per-signature validity.
        """
        ...

    @abstractmethod
    def get_certificate_info(self) -> CertificateInfo | None:
        """Return certificate info if available (PAdES mode), None for hash mode.

        Returns:
            CertificateInfo for PAdES mode, None for hash mode.
        """
        ...


# ---------------------------------------------------------------------------
# Hash-based Signing Strategy (development/testing)
# ---------------------------------------------------------------------------


class HashSigningStrategy(SigningStrategy):
    """SHA-256 hash-based signing strategy for development/testing.

    This strategy appends signature blocks to the PDF containing:
    - Hash of the original PDF content (up to this signature)
    - Signer metadata (name, timestamp, reason, transition)
    - A SHA-256 hash that can be verified later

    This does NOT provide cryptographic non-repudiation but is sufficient
    for development and testing of the signature workflow.
    """

    def sign_pdf(self, pdf_bytes: bytes, stamp: SignatureStamp) -> tuple[bytes, str]:
        """Sign a PDF using SHA-256 hash-based approach.

        Computes a hash of the content being signed, builds a signature
        metadata string, and appends a binary signature block to the PDF.

        Args:
            pdf_bytes: The PDF content to sign.
            stamp: The signature stamp metadata.

        Returns:
            Tuple of (signed_pdf_bytes, signature_hash).
        """
        # Compute hash of the content being signed (everything before this signature)
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # Build signature metadata
        sig_metadata = (
            f"{stamp.signer_name}|"
            f"{stamp.signed_at.isoformat()}|"
            f"{stamp.reason}|"
            f"{stamp.transition}|"
            f"{content_hash}"
        )

        # Compute signature hash
        signature_hash = hashlib.sha256(sig_metadata.encode("utf-8")).hexdigest()

        # Build signature block
        sig_block = self._build_signature_block(
            signer_name=stamp.signer_name,
            signed_at=stamp.signed_at,
            reason=stamp.reason,
            transition=stamp.transition,
            content_hash=content_hash,
            signature_hash=signature_hash,
        )

        # Append signature block to PDF (incremental signature)
        signed_pdf = pdf_bytes + sig_block

        return signed_pdf, signature_hash

    def verify_pdf(self, pdf_bytes: bytes) -> VerificationResult:
        """Verify all signatures on a PDF document.

        Checks each signature in order. For each signature:
        - Computes the hash of all content before that signature block
        - Compares against the stored content_hash in the signature
        - If they don't match, the document was tampered after that signature

        Args:
            pdf_bytes: The complete PDF bytes with signatures.

        Returns:
            VerificationResult with per-signature validity.
        """
        signatures: list[VerificationEntry] = []
        search_start = 0
        all_valid = True
        tampered_from = -1

        while True:
            start_idx = pdf_bytes.find(SIGNATURE_MARKER_START, search_start)
            if start_idx == -1:
                break

            end_idx = pdf_bytes.find(
                SIGNATURE_MARKER_END, start_idx + len(SIGNATURE_MARKER_START)
            )
            if end_idx == -1:
                break

            # Content before this signature block
            content_before = pdf_bytes[:start_idx]
            actual_hash = hashlib.sha256(content_before).hexdigest()

            # Parse the signature block
            block_content = pdf_bytes[
                start_idx + len(SIGNATURE_MARKER_START) : end_idx
            ]
            parsed = self._parse_signature_block(block_content)

            if parsed is not None:
                signer_name, signed_at, reason, transition, stored_content_hash, signature_hash = parsed

                is_valid = True

                # Verify content hash matches
                if actual_hash != stored_content_hash:
                    is_valid = False
                    all_valid = False
                    if tampered_from == -1:
                        tampered_from = len(signatures)
                else:
                    # Also verify the signature hash itself
                    sig_metadata = (
                        f"{signer_name}|"
                        f"{signed_at.isoformat()}|"
                        f"{reason}|"
                        f"{transition}|"
                        f"{stored_content_hash}"
                    )
                    expected_sig_hash = hashlib.sha256(
                        sig_metadata.encode("utf-8")
                    ).hexdigest()

                    if expected_sig_hash != signature_hash:
                        is_valid = False
                        all_valid = False
                        if tampered_from == -1:
                            tampered_from = len(signatures)

                signatures.append(
                    VerificationEntry(
                        signer_name=signer_name,
                        signed_at=signed_at,
                        reason=reason,
                        is_valid=is_valid,
                        certificate_subject=None,
                        certificate_issuer=None,
                    )
                )

            search_start = end_idx + len(SIGNATURE_MARKER_END)

        # If tampered from a certain point, all subsequent signatures are invalid
        if tampered_from >= 0:
            for i in range(tampered_from, len(signatures)):
                signatures[i].is_valid = False

        return VerificationResult(
            is_valid=all_valid,
            signature_count=len(signatures),
            signatures=signatures,
            tampered_from_index=tampered_from,
        )

    def get_certificate_info(self) -> CertificateInfo | None:
        """Hash mode does not use certificates.

        Returns:
            None (no certificate info in hash mode).
        """
        return None

    def _build_signature_block(
        self,
        signer_name: str,
        signed_at: datetime,
        reason: str,
        transition: str,
        content_hash: str,
        signature_hash: str,
    ) -> bytes:
        """Build a binary signature block to append to the PDF.

        The block format:
        - SIGNATURE_MARKER_START (17 bytes)
        - content_hash length (4 bytes, big-endian uint32)
        - content_hash (variable)
        - signature_hash length (4 bytes)
        - signature_hash (variable)
        - signer_name length (4 bytes)
        - signer_name (variable, UTF-8)
        - signed_at ISO string length (4 bytes)
        - signed_at ISO string (variable, UTF-8)
        - reason length (4 bytes)
        - reason (variable, UTF-8)
        - transition length (4 bytes)
        - transition (variable, UTF-8)
        - SIGNATURE_MARKER_END (15 bytes)

        Args:
            signer_name: Full name of the signer.
            signed_at: UTC timestamp.
            reason: Reason for signing.
            transition: Workflow transition.
            content_hash: SHA-256 hash of content before this signature.
            signature_hash: The computed signature hash.

        Returns:
            Binary signature block bytes.
        """
        parts: list[bytes] = [SIGNATURE_MARKER_START]

        for value in [
            content_hash,
            signature_hash,
            signer_name,
            signed_at.isoformat(),
            reason,
            transition,
        ]:
            encoded = value.encode("utf-8")
            parts.append(struct.pack(">I", len(encoded)))
            parts.append(encoded)

        parts.append(SIGNATURE_MARKER_END)
        return b"".join(parts)

    def _parse_signature_block(
        self, block: bytes
    ) -> tuple[str, datetime, str, str, str, str] | None:
        """Parse a signature block back into its component fields.

        Args:
            block: Raw signature block bytes (without markers).

        Returns:
            Tuple of (signer_name, signed_at, reason, transition,
            content_hash, signature_hash) or None if parsing fails.
        """
        try:
            offset = 0

            def read_field() -> str:
                nonlocal offset
                length = struct.unpack(">I", block[offset : offset + 4])[0]
                offset += 4
                value = block[offset : offset + length].decode("utf-8")
                offset += length
                return value

            content_hash = read_field()
            signature_hash = read_field()
            signer_name = read_field()
            signed_at_str = read_field()
            reason = read_field()
            transition = read_field()

            signed_at = datetime.fromisoformat(signed_at_str)

            return (signer_name, signed_at, reason, transition, content_hash, signature_hash)
        except (struct.error, UnicodeDecodeError, ValueError, IndexError):
            return None


# ---------------------------------------------------------------------------
# PAdES Signing Strategy (production — real cryptographic PAdES-B-LT)
# ---------------------------------------------------------------------------


class PAdESSigningStrategy(SigningStrategy):
    """Real cryptographic PAdES signing strategy using pyHanko + x.509.

    This strategy uses asymmetric cryptography (RSA/ECDSA private keys,
    x.509 certificates) to create PAdES-B-LT compliant PDF signatures
    with optional RFC 3161 timestamping.
    """

    def __init__(
        self,
        key_path: str,
        cert_path: str,
        key_password: str | None = None,
        tsa_url: str | None = None,
    ) -> None:
        """Initialize PAdES signing strategy.

        Args:
            key_path: Path to PEM-encoded private key file.
            cert_path: Path to PEM-encoded certificate chain file.
            key_password: Passphrase for encrypted private keys (None if unencrypted).
            tsa_url: RFC 3161 Timestamp Authority URL (None to skip timestamping).

        Raises:
            RuntimeError: If pyHanko is not installed.
            ValueError: If key or certificate cannot be loaded.
        """
        if not PYHANKO_AVAILABLE:
            raise RuntimeError(
                "pyHanko is not installed. Cannot use PAdES signing mode. "
                "Install pyhanko to enable production cryptographic signatures."
            )

        self._key_path = key_path
        self._cert_path = cert_path
        self._key_password = key_password
        self._tsa_url = tsa_url
        self._cert_info: CertificateInfo | None = None

        # Load certificate to extract info using cryptography library
        self._load_certificate_info()

    def _load_certificate_info(self) -> None:
        """Load certificate and extract subject/issuer/serial info."""
        try:
            from cryptography.x509 import load_pem_x509_certificate

            with open(self._cert_path, "rb") as f:
                cert_data = f.read()
            cert = load_pem_x509_certificate(cert_data)
            self._cert_info = CertificateInfo(
                subject=cert.subject.rfc4514_string(),
                issuer=cert.issuer.rfc4514_string(),
                serial=format(cert.serial_number, "x"),
            )
        except Exception as e:
            logger.warning(
                "Could not load certificate info from %s: %s",
                self._cert_path,
                e,
            )
            self._cert_info = None

    def _create_signer(self) -> "SimpleSigner":
        """Create a SimpleSigner instance from key and certificate files.

        Returns:
            A configured SimpleSigner ready for signing operations.

        Raises:
            ValueError: If key or certificate cannot be loaded.
        """
        passphrase = (
            self._key_password.encode("utf-8")
            if self._key_password
            else None
        )
        signer = SimpleSigner.load(
            key_file=self._key_path,
            cert_file=self._cert_path,
            key_passphrase=passphrase,
        )
        if signer is None:
            raise ValueError(
                f"Failed to load signing key/certificate from "
                f"key={self._key_path}, cert={self._cert_path}. "
                f"Check that the files exist and are valid PEM-encoded."
            )
        return signer

    def sign_pdf(self, pdf_bytes: bytes, stamp: SignatureStamp) -> tuple[bytes, str]:
        """Sign a PDF using PAdES-B-LT with pyHanko.

        Creates a PAdES compliant signature with a visible annotation on the
        last page (bottom-right quadrant, approximately 200x80 points).

        Args:
            pdf_bytes: The PDF content to sign.
            stamp: The signature stamp metadata.

        Returns:
            Tuple of (signed_pdf_bytes, signature_hash).

        Raises:
            ValueError: If the signer cannot be created.
            RuntimeError: If the signing operation fails.
        """
        signer = self._create_signer()

        # Build stamp text with signer info
        cert_subject_dn = (
            self._cert_info.subject if self._cert_info else "Unknown"
        )
        stamp_text = (
            f"Signed by: {stamp.signer_name}\n"
            f"Date: {stamp.signed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Reason: {stamp.reason}\n"
            f"Transition: {stamp.transition}\n"
            f"Cert: {cert_subject_dn}"
        )

        # Configure visible stamp style
        stamp_style = TextStampStyle(
            stamp_text=stamp_text,
            timestamp_format="%Y-%m-%d %H:%M:%S %Z",
        )

        # Create a unique field name for this signature
        field_name = f"AlcoaBase_Sig_{stamp.signed_at.strftime('%Y%m%d%H%M%S')}"

        # Configure signature metadata for PAdES
        sig_metadata = PdfSignatureMetadata(
            field_name=field_name,
            reason=f"{stamp.reason} ({stamp.transition})",
            name=stamp.signer_name,
            subfilter=SigSeedSubFilter.PADES,
        )

        # Configure signature field on last page, bottom-right quadrant
        # Box format: (ll_x, ll_y, ur_x, ur_y) — lower-left x, lower-left y,
        # upper-right x, upper-right y
        sig_field_spec = SigFieldSpec(
            sig_field_name=field_name,
            on_page=-1,  # Last page
            box=(350, 50, 550, 130),  # ~200x80 points, bottom-right
        )

        # Configure timestamper if TSA URL is provided
        timestamper = None
        if self._tsa_url:
            timestamper = HTTPTimeStamper(url=self._tsa_url)

        # Create PdfSigner
        pdf_signer = PdfSigner(
            signature_meta=sig_metadata,
            signer=signer,
            timestamper=timestamper,
            stamp_style=stamp_style,
            new_field_spec=sig_field_spec,
        )

        # Create IncrementalPdfFileWriter from the input bytes
        pdf_input = io.BytesIO(pdf_bytes)
        writer = IncrementalPdfFileWriter(pdf_input)

        # Sign the PDF
        output = io.BytesIO()
        try:
            pdf_signer.sign_pdf(
                writer,
                existing_fields_only=False,
                output=output,
            )
        except Exception as e:
            raise RuntimeError(f"PAdES signing failed: {e}") from e

        signed_pdf_bytes = output.getvalue()

        # Extract signature hash from the CMS signature
        signature_hash = self._extract_signature_hash(signed_pdf_bytes)

        return signed_pdf_bytes, signature_hash

    def _extract_signature_hash(self, signed_pdf_bytes: bytes) -> str:
        """Extract a SHA-256 hash from the CMS signature in the signed PDF.

        Args:
            signed_pdf_bytes: The signed PDF bytes.

        Returns:
            Hex-encoded SHA-256 hash of the CMS signature bytes.
        """
        try:
            reader = PdfFileReader(io.BytesIO(signed_pdf_bytes))
            embedded_sigs = reader.embedded_signatures
            if embedded_sigs:
                # Get the last (most recent) signature
                last_sig = embedded_sigs[-1]
                # Hash the PKCS#7/CMS content
                cms_bytes = last_sig.pkcs7_content
                return hashlib.sha256(cms_bytes).hexdigest()
        except Exception as e:
            logger.warning("Could not extract CMS signature hash: %s", e)

        # Fallback: hash the entire signed PDF
        return hashlib.sha256(signed_pdf_bytes).hexdigest()

    def verify_pdf(self, pdf_bytes: bytes) -> VerificationResult:
        """Verify all PAdES signatures on a PDF.

        Opens the PDF, enumerates all embedded signatures, and validates
        each one using pyHanko's validation framework.

        Args:
            pdf_bytes: The complete PDF bytes with signatures.

        Returns:
            VerificationResult with per-signature validity.
        """
        try:
            reader = PdfFileReader(io.BytesIO(pdf_bytes))
            embedded_sigs = reader.embedded_signatures
        except Exception as e:
            logger.error("Failed to read PDF for verification: %s", e)
            return VerificationResult(
                is_valid=False,
                signature_count=0,
                signatures=[],
                tampered_from_index=-1,
            )

        if not embedded_sigs:
            return VerificationResult(
                is_valid=True,
                signature_count=0,
                signatures=[],
                tampered_from_index=-1,
            )

        signatures: list[VerificationEntry] = []
        all_valid = True
        tampered_from = -1

        for idx, emb_sig in enumerate(embedded_sigs):
            try:
                status = validate_pdf_signature(
                    emb_sig,
                    signer_validation_context=None,
                    skip_diff=False,
                )

                # Extract signer info from the certificate
                signer_cert = emb_sig.signer_cert
                cert_subject = (
                    signer_cert.subject.human_friendly
                    if signer_cert
                    else None
                )
                cert_issuer = (
                    signer_cert.issuer.human_friendly
                    if signer_cert
                    else None
                )

                # Extract signer name from signature dictionary
                sig_obj = emb_sig.sig_object
                signer_name = "Unknown"
                if "/Name" in sig_obj:
                    signer_name = str(sig_obj["/Name"])
                elif cert_subject:
                    signer_name = cert_subject

                # Extract signing time
                signed_at = emb_sig.self_reported_timestamp or datetime.now(
                    tz=timezone.utc
                )

                # Extract reason
                reason = ""
                if "/Reason" in sig_obj:
                    reason = str(sig_obj["/Reason"])

                # Determine validity: intact means content hash matches,
                # valid means full chain validation passed
                is_valid = status.intact and status.valid

                if not is_valid:
                    all_valid = False
                    if tampered_from == -1:
                        tampered_from = idx

                signatures.append(
                    VerificationEntry(
                        signer_name=signer_name,
                        signed_at=signed_at,
                        reason=reason,
                        is_valid=is_valid,
                        certificate_subject=cert_subject,
                        certificate_issuer=cert_issuer,
                    )
                )
            except Exception as e:
                logger.warning(
                    "Failed to validate signature %d: %s", idx, e
                )
                all_valid = False
                if tampered_from == -1:
                    tampered_from = idx
                signatures.append(
                    VerificationEntry(
                        signer_name="Unknown",
                        signed_at=datetime.now(tz=timezone.utc),
                        reason="",
                        is_valid=False,
                        certificate_subject=None,
                        certificate_issuer=None,
                    )
                )

        return VerificationResult(
            is_valid=all_valid,
            signature_count=len(signatures),
            signatures=signatures,
            tampered_from_index=tampered_from,
        )

    def get_certificate_info(self) -> CertificateInfo | None:
        """Return certificate info if loaded.

        Returns:
            CertificateInfo if the certificate has been loaded, None otherwise.
        """
        return self._cert_info


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def create_signing_strategy(settings: Settings) -> SigningStrategy:
    """Create the appropriate signing strategy based on SIGNATURE_MODE.

    Returns PAdESSigningStrategy if mode is "pades", HashSigningStrategy otherwise.

    Args:
        settings: Application settings instance.

    Returns:
        The configured SigningStrategy implementation.

    Raises:
        RuntimeError: If mode is "pades" but pyHanko is not installed or
                      required configuration is missing.
    """
    if settings.signature_mode == "pades":
        if not PYHANKO_AVAILABLE:
            raise RuntimeError(
                "SIGNATURE_MODE is set to 'pades' but pyHanko is not installed. "
                "Install pyhanko to enable production cryptographic signatures, "
                "or set SIGNATURE_MODE=hash for development/testing."
            )
        if not settings.signature_key_path:
            raise RuntimeError(
                "SIGNATURE_MODE is 'pades' but SIGNATURE_KEY_PATH is not set. "
                "Provide the path to a PEM-encoded private key file."
            )
        if not settings.signature_cert_path:
            raise RuntimeError(
                "SIGNATURE_MODE is 'pades' but SIGNATURE_CERT_PATH is not set. "
                "Provide the path to a PEM-encoded certificate chain file."
            )
        return PAdESSigningStrategy(
            key_path=settings.signature_key_path,
            cert_path=settings.signature_cert_path,
            key_password=settings.signature_key_password,
            tsa_url=settings.signature_tsa_url,
        )
    return HashSigningStrategy()
