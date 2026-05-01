"""Signature Service for PAdES electronic signatures.

This module implements the Signature Service responsible for:
- Re-authentication enforcement before signing
- PAdES-style PDF signing (placeholder for pyHanko integration)
- Visual signature stamp embedding
- Incremental signature support (multiple signers)
- Audit trail recording for all signature events

References:
    - Design doc Section 6: Signature Service (PAdES)
    - CFR 21 Part 11: Electronic records and signatures
    - PAdES: PDF Advanced Electronic Signatures standard
"""

import hashlib
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime

import bcrypt as _bcrypt
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.signature import SignatureRecord
from alcoabase.models.user import User


# ---------------------------------------------------------------------------
# Password hashing utilities
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plaintext password to hash.

    Returns:
        Bcrypt hash string.
    """
    return _bcrypt.hashpw(
        password.encode("utf-8"), _bcrypt.gensalt()
    ).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash.

    Args:
        password: Plaintext password to verify.
        hashed: Bcrypt hash to verify against.

    Returns:
        True if the password matches the hash.
    """
    return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SignatureStamp:
    """Visual signature stamp data embedded in the PDF.

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
class SignatureResult:
    """Result of a signing operation.

    Attributes:
        success: Whether the signing was successful.
        signature_hash: SHA-256 hash of the signature data.
        signed_pdf: The signed PDF bytes.
        stamp: The visual stamp data that was embedded.
        signature_record_id: Database ID of the recorded signature event.
    """

    success: bool
    signature_hash: str
    signed_pdf: bytes
    stamp: SignatureStamp
    signature_record_id: int | None = None


@dataclass
class SignatureInfo:
    """Information about a single signature on a PDF.

    Attributes:
        signer_name: Full name of the signer.
        signed_at: UTC timestamp of the signing event.
        reason: Reason for the signature.
        transition: Workflow transition that triggered signing.
        signature_hash: SHA-256 hash of the signature data.
        is_valid: Whether the signature is still valid (not tampered).
    """

    signer_name: str
    signed_at: datetime
    reason: str
    transition: str
    signature_hash: str
    is_valid: bool = True


@dataclass
class VerificationResult:
    """Result of signature verification on a PDF.

    Attributes:
        is_valid: Whether all signatures are valid.
        signatures: List of individual signature verification results.
        tampered_from_index: Index of first invalid signature (-1 if all valid).
    """

    is_valid: bool
    signatures: list[SignatureInfo] = field(default_factory=list)
    tampered_from_index: int = -1


# ---------------------------------------------------------------------------
# Signature marker constants
# ---------------------------------------------------------------------------

# Magic bytes to identify signature blocks in the PDF
SIGNATURE_MARKER_START = b"\x00\x01ALCOA_SIG_START\x00"
SIGNATURE_MARKER_END = b"\x00\x01ALCOA_SIG_END\x00"


# ---------------------------------------------------------------------------
# Signature Service
# ---------------------------------------------------------------------------


class SignatureService:
    """Service for PAdES-style electronic signatures.

    Provides re-authentication enforcement, PDF signing with visual stamps,
    incremental signature support, and audit trail recording.

    The current implementation uses a simplified signing approach that can
    be swapped for full pyHanko PAdES signing when x.509 certificates are
    configured.

    Usage:
        service = SignatureService()
        result = await service.sign_document(
            session=session,
            pdf_bytes=pdf_data,
            user_id=1,
            password="secret",
            document_uuid="2024-00001",
            document_version_id=1,
            transition="Review→Approved",
            reason="Approved by QA Manager",
        )
    """

    async def verify_credentials(
        self,
        session: AsyncSession,
        user_id: int,
        password: str,
    ) -> User:
        """Verify user credentials for re-authentication before signing.

        This enforces the re-authentication requirement: users must provide
        their password/PIN before any signing operation.

        Args:
            session: Active async database session.
            user_id: The user's primary key ID.
            password: The plaintext password to verify.

        Returns:
            The authenticated User instance.

        Raises:
            HTTPException: 401 if credentials are invalid.
            HTTPException: 403 if user account is inactive.
        """
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user is None:
            raise HTTPException(
                status_code=401,
                detail="Re-authentication failed: user not found",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="Re-authentication failed: user account is inactive",
            )

        if not verify_password(password, user.hashed_password):
            raise HTTPException(
                status_code=401,
                detail="Re-authentication failed: invalid credentials",
            )

        return user

    async def sign_document(
        self,
        session: AsyncSession,
        pdf_bytes: bytes,
        user_id: int,
        password: str,
        document_uuid: str,
        document_version_id: int,
        transition: str,
        reason: str,
    ) -> SignatureResult:
        """Sign a PDF document with re-authentication enforcement.

        Performs the full signing flow:
        1. Verify user credentials (re-authentication)
        2. Create visual signature stamp
        3. Apply PAdES-style signature to PDF
        4. Record signature event in audit trail

        Args:
            session: Active async database session.
            pdf_bytes: The PDF content to sign.
            user_id: The signing user's ID.
            password: User's password for re-authentication.
            document_uuid: Document-UUID of the document being signed.
            document_version_id: Foreign key to the specific version.
            transition: Workflow transition requiring the signature.
            reason: Human-readable reason for the signature.

        Returns:
            SignatureResult with signed PDF and metadata.

        Raises:
            HTTPException: 401 if re-authentication fails.
            HTTPException: 403 if user account is inactive.
            HTTPException: 400 if PDF bytes are empty.
        """
        if not pdf_bytes:
            raise HTTPException(
                status_code=400,
                detail="Cannot sign empty document",
            )

        # Step 1: Re-authenticate user
        user = await self.verify_credentials(session, user_id, password)

        # Step 2: Create signature stamp
        signed_at = datetime.now(UTC)
        stamp = SignatureStamp(
            signer_name=user.full_name,
            signed_at=signed_at,
            reason=reason,
            transition=transition,
        )

        # Step 3: Apply signature to PDF
        signed_pdf, signature_hash = self._apply_signature(
            pdf_bytes=pdf_bytes,
            stamp=stamp,
        )

        # Step 4: Record in audit trail
        record = SignatureRecord(
            document_uuid=document_uuid,
            document_version_id=document_version_id,
            signer_user_id=user_id,
            transition=transition,
            reason=reason,
            signed_at=signed_at,
            signature_hash=signature_hash,
        )
        session.add(record)
        await session.flush()

        return SignatureResult(
            success=True,
            signature_hash=signature_hash,
            signed_pdf=signed_pdf,
            stamp=stamp,
            signature_record_id=record.id,
        )

    def _apply_signature(
        self,
        pdf_bytes: bytes,
        stamp: SignatureStamp,
    ) -> tuple[bytes, str]:
        """Apply a PAdES-style signature to PDF bytes.

        This is a simplified implementation that appends a signature block
        to the PDF. The signature block contains:
        - Hash of the original PDF content (up to this signature)
        - Signer metadata (name, timestamp, reason, transition)
        - A cryptographic hash that can be verified later

        In production, this would use pyHanko for full PAdES compliance
        with x.509 certificates.

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

        # Compute signature hash (in production, this would be a cryptographic signature)
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

    def _parse_signature_block(self, block: bytes) -> SignatureInfo | None:
        """Parse a signature block back into SignatureInfo.

        Args:
            block: Raw signature block bytes (without markers).

        Returns:
            SignatureInfo or None if parsing fails.
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

            return SignatureInfo(
                signer_name=signer_name,
                signed_at=signed_at,
                reason=reason,
                transition=transition,
                signature_hash=signature_hash,
                is_valid=True,  # Will be validated separately
            )
        except (struct.error, UnicodeDecodeError, ValueError, IndexError):
            return None

    def extract_signatures(self, pdf_bytes: bytes) -> list[SignatureInfo]:
        """Extract all signature blocks from a signed PDF.

        Args:
            pdf_bytes: The PDF bytes (possibly with multiple signatures).

        Returns:
            List of SignatureInfo in order of signing.
        """
        signatures: list[SignatureInfo] = []
        search_start = 0

        while True:
            # Find next signature block
            start_idx = pdf_bytes.find(SIGNATURE_MARKER_START, search_start)
            if start_idx == -1:
                break

            end_idx = pdf_bytes.find(
                SIGNATURE_MARKER_END, start_idx + len(SIGNATURE_MARKER_START)
            )
            if end_idx == -1:
                break

            # Extract block content (between markers)
            block_content = pdf_bytes[
                start_idx + len(SIGNATURE_MARKER_START) : end_idx
            ]

            sig_info = self._parse_signature_block(block_content)
            if sig_info is not None:
                signatures.append(sig_info)

            search_start = end_idx + len(SIGNATURE_MARKER_END)

        return signatures

    def verify_signatures(self, pdf_bytes: bytes) -> VerificationResult:
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
        signatures: list[SignatureInfo] = []
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
            sig_info = self._parse_signature_block(block_content)

            if sig_info is not None:
                # Read the stored content_hash from the block
                offset = 0
                length = struct.unpack(">I", block_content[offset : offset + 4])[0]
                stored_content_hash = block_content[4 : 4 + length].decode("utf-8")

                # Verify content hash matches
                if actual_hash != stored_content_hash:
                    sig_info.is_valid = False
                    all_valid = False
                    if tampered_from == -1:
                        tampered_from = len(signatures)
                else:
                    # Also verify the signature hash itself
                    sig_metadata = (
                        f"{sig_info.signer_name}|"
                        f"{sig_info.signed_at.isoformat()}|"
                        f"{sig_info.reason}|"
                        f"{sig_info.transition}|"
                        f"{stored_content_hash}"
                    )
                    expected_sig_hash = hashlib.sha256(
                        sig_metadata.encode("utf-8")
                    ).hexdigest()

                    if expected_sig_hash != sig_info.signature_hash:
                        sig_info.is_valid = False
                        all_valid = False
                        if tampered_from == -1:
                            tampered_from = len(signatures)

                signatures.append(sig_info)

            search_start = end_idx + len(SIGNATURE_MARKER_END)

        # If tampered from a certain point, all subsequent signatures are invalid
        if tampered_from >= 0:
            for i in range(tampered_from, len(signatures)):
                signatures[i].is_valid = False

        return VerificationResult(
            is_valid=all_valid,
            signatures=signatures,
            tampered_from_index=tampered_from,
        )

    def add_visual_stamp(
        self,
        pdf_bytes: bytes,
        stamp: SignatureStamp,
    ) -> bytes:
        """Add a visual signature stamp annotation to the PDF.

        Embeds a text annotation with signer name, date, time, and reason.
        This is a simplified implementation; in production, use ReportLab
        or PyMuPDF to render a proper visual stamp on the PDF page.

        Args:
            pdf_bytes: The PDF content.
            stamp: The signature stamp data.

        Returns:
            PDF bytes with visual stamp annotation appended.
        """
        # Build a human-readable stamp text
        stamp_text = (
            f"Electronically signed by: {stamp.signer_name}\n"
            f"Date: {stamp.signed_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"Reason: {stamp.reason}\n"
            f"Transition: {stamp.transition}"
        )

        # Encode as a PDF comment annotation (simplified approach)
        # In production, this would use ReportLab/PyMuPDF to render on-page
        stamp_annotation = (
            f"\n% SIGNATURE STAMP\n"
            f"% {stamp_text.replace(chr(10), chr(10) + '% ')}\n"
        ).encode("utf-8")

        return pdf_bytes + stamp_annotation

    async def get_signature_records(
        self,
        session: AsyncSession,
        document_uuid: str,
    ) -> list[SignatureRecord]:
        """Get all signature records for a document.

        Args:
            session: Active async database session.
            document_uuid: The document's unique identifier.

        Returns:
            List of SignatureRecord instances ordered by signed_at.
        """
        result = await session.execute(
            select(SignatureRecord)
            .where(SignatureRecord.document_uuid == document_uuid)
            .order_by(SignatureRecord.signed_at)
        )
        return list(result.scalars().all())
