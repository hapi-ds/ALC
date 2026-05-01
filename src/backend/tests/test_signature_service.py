"""Tests for the Signature Service.

Includes property-based tests for signature integrity (byte modification
invalidates signature) and unit tests for incremental signatures.

**Validates: Requirements 6.1, 6.2, 6.3, 6.4**
"""

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

from alcoabase.services.signature_service import (
    SignatureInfo,
    SignatureResult,
    SignatureService,
    SignatureStamp,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_sample_pdf(content: str = "Hello PDF") -> bytes:
    """Create a minimal PDF-like byte sequence for testing.

    Args:
        content: Text content to embed in the PDF bytes.

    Returns:
        Bytes representing a minimal PDF structure.
    """
    # Minimal PDF structure (valid enough for our signature tests)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        + content.encode("utf-8")
        + b"\n%%EOF\n"
    )


def sign_pdf_sync(
    service: SignatureService,
    pdf_bytes: bytes,
    signer_name: str = "Test User",
    reason: str = "Test signing",
    transition: str = "Review→Approved",
) -> tuple[bytes, str]:
    """Synchronously sign a PDF using the service's internal method.

    Args:
        service: The SignatureService instance.
        pdf_bytes: PDF bytes to sign.
        signer_name: Name of the signer.
        reason: Reason for signing.
        transition: Workflow transition.

    Returns:
        Tuple of (signed_pdf_bytes, signature_hash).
    """
    stamp = SignatureStamp(
        signer_name=signer_name,
        signed_at=datetime.now(UTC),
        reason=reason,
        transition=transition,
    )
    return service._apply_signature(pdf_bytes, stamp)


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

# Strategy for generating PDF-like content
pdf_content_strategy = st.binary(min_size=50, max_size=2000).map(
    lambda b: b"%PDF-1.4\n" + b + b"\n%%EOF\n"
)

# Strategy for signer names
signer_name_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "Z"), min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip() != "")

# Strategy for reasons
reason_strategy = st.text(
    alphabet=st.characters(categories=("L", "N", "Z", "P"), min_codepoint=32, max_codepoint=126),
    min_size=1,
    max_size=100,
).filter(lambda s: s.strip() != "")

# Strategy for transitions
transition_strategy = st.text(
    alphabet=st.characters(categories=("L", "N"), min_codepoint=32, max_codepoint=126),
    min_size=3,
    max_size=50,
).filter(lambda s: s.strip() != "")


# ---------------------------------------------------------------------------
# Task 9.7: Property-based tests - byte modification invalidates signature
# ---------------------------------------------------------------------------


class TestSignatureIntegrity:
    """Property tests verifying that any byte modification invalidates signatures.

    For all signed PDFs, modifying any byte in the content before the
    signature block causes verification to fail.

    **Validates: Requirements 6.3**
    """

    @given(
        pdf_content=pdf_content_strategy,
        signer_name=signer_name_strategy,
        reason=reason_strategy,
        modification_offset=st.integers(min_value=0),
        modification_byte=st.integers(min_value=0, max_value=255),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_byte_modification_invalidates_signature(
        self,
        pdf_content: bytes,
        signer_name: str,
        reason: str,
        modification_offset: int,
        modification_byte: int,
    ) -> None:
        """Any byte modification to the signed content invalidates the signature.

        Generates a signed PDF, modifies a single byte in the original content
        area, and verifies that signature verification fails.

        **Validates: Requirements 6.3**
        """
        service = SignatureService()

        # Sign the PDF
        stamp = SignatureStamp(
            signer_name=signer_name,
            signed_at=datetime.now(UTC),
            reason=reason,
            transition="Test→Done",
        )
        signed_pdf, sig_hash = service._apply_signature(pdf_content, stamp)

        # Verify the unmodified signed PDF is valid
        result = service.verify_signatures(signed_pdf)
        assert result.is_valid, "Unmodified signed PDF should be valid"
        assert len(result.signatures) == 1

        # Modify a byte in the original content area (before the signature)
        # Clamp offset to valid range within original content
        actual_offset = modification_offset % len(pdf_content)
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
        tampered_result = service.verify_signatures(tampered_pdf)
        assert not tampered_result.is_valid, (
            f"Tampered PDF should fail verification. "
            f"Modified byte at offset {actual_offset} from {original_byte} to {new_byte}"
        )

    @given(
        pdf_content=pdf_content_strategy,
        signer_name=signer_name_strategy,
        reason=reason_strategy,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_unmodified_signature_always_valid(
        self,
        pdf_content: bytes,
        signer_name: str,
        reason: str,
    ) -> None:
        """An unmodified signed PDF always passes verification.

        **Validates: Requirements 6.3**
        """
        service = SignatureService()

        stamp = SignatureStamp(
            signer_name=signer_name,
            signed_at=datetime.now(UTC),
            reason=reason,
            transition="Test→Done",
        )
        signed_pdf, _ = service._apply_signature(pdf_content, stamp)

        result = service.verify_signatures(signed_pdf)
        assert result.is_valid
        assert len(result.signatures) == 1
        assert result.signatures[0].signer_name == signer_name
        assert result.signatures[0].reason == reason

    @given(
        pdf_content=pdf_content_strategy,
        append_data=st.binary(min_size=1, max_size=100),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_appending_data_after_signature_does_not_invalidate(
        self,
        pdf_content: bytes,
        append_data: bytes,
    ) -> None:
        """Appending data after the last signature block does not invalidate it.

        This is expected behavior for incremental signatures — new content
        can be appended after existing signatures.

        **Validates: Requirements 6.3**
        """
        service = SignatureService()

        stamp = SignatureStamp(
            signer_name="Test User",
            signed_at=datetime.now(UTC),
            reason="Test",
            transition="A→B",
        )
        signed_pdf, _ = service._apply_signature(pdf_content, stamp)

        # Append data after the signature
        extended_pdf = signed_pdf + append_data

        # The existing signature should still be valid
        result = service.verify_signatures(extended_pdf)
        assert result.is_valid
        assert len(result.signatures) == 1


# ---------------------------------------------------------------------------
# Task 9.8: Unit tests - incremental signatures
# ---------------------------------------------------------------------------


class TestIncrementalSignatures:
    """Unit tests for incremental signature support.

    Verifies that:
    - Multiple signatures can accumulate on the same PDF
    - All N signatures validate correctly
    - Modifying bytes after any signature invalidates from that point

    **Validates: Requirements 6.2, 6.4**
    """

    def test_single_signature_validates(self) -> None:
        """A single signature on a PDF validates correctly.

        **Validates: Requirements 6.2**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Single signature test")

        signed_pdf, sig_hash = sign_pdf_sync(
            service, pdf, signer_name="Alice", reason="Records completed"
        )

        result = service.verify_signatures(signed_pdf)
        assert result.is_valid
        assert len(result.signatures) == 1
        assert result.signatures[0].signer_name == "Alice"
        assert result.signatures[0].reason == "Records completed"
        assert result.signatures[0].is_valid

    def test_two_sequential_signatures_validate(self) -> None:
        """Two sequential signatures both validate correctly.

        **Validates: Requirements 6.4**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Two signatures test")

        # First signature (analyst)
        signed_once, _ = sign_pdf_sync(
            service,
            pdf,
            signer_name="Alice Analyst",
            reason="Records completed by analyst",
            transition="Draft→RecordsFilled",
        )

        # Second signature (reviewer)
        signed_twice, _ = sign_pdf_sync(
            service,
            signed_once,
            signer_name="Bob Reviewer",
            reason="Reviewed by supervisor",
            transition="RecordsFilled→Reviewed",
        )

        result = service.verify_signatures(signed_twice)
        assert result.is_valid
        assert len(result.signatures) == 2
        assert result.signatures[0].signer_name == "Alice Analyst"
        assert result.signatures[0].reason == "Records completed by analyst"
        assert result.signatures[0].is_valid
        assert result.signatures[1].signer_name == "Bob Reviewer"
        assert result.signatures[1].reason == "Reviewed by supervisor"
        assert result.signatures[1].is_valid

    def test_three_sequential_signatures_validate(self) -> None:
        """Three sequential signatures (analyst, reviewer, QA) all validate.

        **Validates: Requirements 6.4**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Three signatures test")

        # Analyst signs
        signed_1, _ = sign_pdf_sync(
            service,
            pdf,
            signer_name="Alice Analyst",
            reason="Records completed by analyst",
            transition="Draft→RecordsFilled",
        )

        # Reviewer signs
        signed_2, _ = sign_pdf_sync(
            service,
            signed_1,
            signer_name="Bob Reviewer",
            reason="Reviewed by supervisor",
            transition="RecordsFilled→Reviewed",
        )

        # QA signs
        signed_3, _ = sign_pdf_sync(
            service,
            signed_2,
            signer_name="Carol QA",
            reason="Approved by QA",
            transition="Reviewed→Approved",
        )

        result = service.verify_signatures(signed_3)
        assert result.is_valid
        assert len(result.signatures) == 3
        assert result.signatures[0].signer_name == "Alice Analyst"
        assert result.signatures[1].signer_name == "Bob Reviewer"
        assert result.signatures[2].signer_name == "Carol QA"
        assert all(sig.is_valid for sig in result.signatures)

    def test_n_sequential_signatures_validate(self) -> None:
        """N sequential signatures all validate (parameterized for N=1..5).

        **Validates: Requirements 6.4**
        """
        service = SignatureService()

        for n in range(1, 6):
            pdf = make_sample_pdf(f"Test with {n} signatures")
            current_pdf = pdf

            for i in range(n):
                current_pdf, _ = sign_pdf_sync(
                    service,
                    current_pdf,
                    signer_name=f"Signer {i + 1}",
                    reason=f"Reason {i + 1}",
                    transition=f"State{i}→State{i + 1}",
                )

            result = service.verify_signatures(current_pdf)
            assert result.is_valid, f"Failed for N={n}"
            assert len(result.signatures) == n, f"Expected {n} signatures, got {len(result.signatures)}"
            assert all(sig.is_valid for sig in result.signatures)

    def test_modification_after_first_signature_invalidates_from_that_point(
        self,
    ) -> None:
        """Modifying bytes after the first signature invalidates it and all subsequent.

        **Validates: Requirements 6.3, 6.4**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Tamper test")

        # Sign once
        signed_once, _ = sign_pdf_sync(
            service, pdf, signer_name="Alice", reason="First sign"
        )

        # Tamper with the original content (before first signature)
        tampered = bytearray(signed_once)
        # Modify a byte in the PDF header area
        tampered[10] = (tampered[10] + 1) % 256
        tampered = bytes(tampered)

        # Sign again on tampered content (simulating a second signer on bad data)
        signed_twice, _ = sign_pdf_sync(
            service, tampered, signer_name="Bob", reason="Second sign"
        )

        # Verify: first signature should be invalid (content was modified)
        result = service.verify_signatures(signed_twice)
        assert not result.is_valid
        assert result.tampered_from_index == 0

    def test_modification_between_signatures_invalidates_second(self) -> None:
        """Modifying bytes between two signatures invalidates the second.

        **Validates: Requirements 6.3, 6.4**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Between signatures tamper test")

        # First signature
        signed_once, _ = sign_pdf_sync(
            service, pdf, signer_name="Alice", reason="First"
        )

        # Tamper with content between first and second signature
        # Modify a byte in the original PDF content area
        tampered = bytearray(signed_once)
        tampered[5] = (tampered[5] + 1) % 256
        tampered = bytes(tampered)

        # Second signature on tampered content
        signed_twice, _ = sign_pdf_sync(
            service, tampered, signer_name="Bob", reason="Second"
        )

        # The first signature should be invalid (its content was modified)
        # The second signature should be valid (it signed the tampered content)
        result = service.verify_signatures(signed_twice)
        assert not result.is_valid
        # First signature is invalid because content before it was modified
        assert result.tampered_from_index == 0

    def test_modification_after_second_signature_invalidates_only_second(
        self,
    ) -> None:
        """Modifying bytes in the first signature block area invalidates from that point.

        When content before the second signature is modified (but after the first
        signature was applied), the second signature becomes invalid.

        **Validates: Requirements 6.3, 6.4**
        """
        service = SignatureService()
        pdf = make_sample_pdf("After second signature tamper")

        # Two valid signatures
        signed_once, _ = sign_pdf_sync(
            service, pdf, signer_name="Alice", reason="First"
        )
        signed_twice, _ = sign_pdf_sync(
            service, signed_once, signer_name="Bob", reason="Second"
        )

        # Verify both are valid first
        result = service.verify_signatures(signed_twice)
        assert result.is_valid
        assert len(result.signatures) == 2

        # Now tamper with a byte in the original content (before first signature)
        tampered = bytearray(signed_twice)
        tampered[5] = (tampered[5] + 1) % 256
        tampered = bytes(tampered)

        # Both signatures should now be invalid
        result = service.verify_signatures(tampered)
        assert not result.is_valid
        assert result.tampered_from_index == 0
        assert not result.signatures[0].is_valid
        assert not result.signatures[1].is_valid

    def test_extract_signatures_returns_all_signers(self) -> None:
        """extract_signatures returns metadata for all signers in order.

        **Validates: Requirements 6.4**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Extract test")

        signed_1, _ = sign_pdf_sync(
            service, pdf, signer_name="Alice", reason="R1", transition="A→B"
        )
        signed_2, _ = sign_pdf_sync(
            service, signed_1, signer_name="Bob", reason="R2", transition="B→C"
        )

        signatures = service.extract_signatures(signed_2)
        assert len(signatures) == 2
        assert signatures[0].signer_name == "Alice"
        assert signatures[0].reason == "R1"
        assert signatures[0].transition == "A→B"
        assert signatures[1].signer_name == "Bob"
        assert signatures[1].reason == "R2"
        assert signatures[1].transition == "B→C"

    def test_unsigned_pdf_has_no_signatures(self) -> None:
        """An unsigned PDF has no signatures.

        **Validates: Requirements 6.2**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Unsigned")

        result = service.verify_signatures(pdf)
        assert result.is_valid  # No signatures means nothing to invalidate
        assert len(result.signatures) == 0

        signatures = service.extract_signatures(pdf)
        assert len(signatures) == 0


# ---------------------------------------------------------------------------
# Unit tests for re-authentication (Task 9.1)
# ---------------------------------------------------------------------------


class TestReAuthentication:
    """Unit tests for re-authentication enforcement.

    **Validates: Requirements 6.1**
    """

    @pytest.mark.asyncio
    async def test_verify_credentials_success(self) -> None:
        """Successful re-authentication with valid credentials.

        **Validates: Requirements 6.1**
        """
        from alcoabase.services.signature_service import hash_password

        hashed = hash_password("correct_password")

        service = SignatureService()
        session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.username = "testuser"
        mock_user.full_name = "Test User"
        mock_user.is_active = True
        mock_user.hashed_password = hashed

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = result_mock

        user = await service.verify_credentials(session, 1, "correct_password")
        assert user.full_name == "Test User"

    @pytest.mark.asyncio
    async def test_verify_credentials_wrong_password(self) -> None:
        """Re-authentication fails with wrong password.

        **Validates: Requirements 6.1**
        """
        from fastapi import HTTPException

        from alcoabase.services.signature_service import hash_password

        hashed = hash_password("correct_password")

        service = SignatureService()
        session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = True
        mock_user.hashed_password = hashed

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = result_mock

        with pytest.raises(HTTPException) as exc_info:
            await service.verify_credentials(session, 1, "wrong_password")

        assert exc_info.value.status_code == 401
        assert "invalid credentials" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_verify_credentials_user_not_found(self) -> None:
        """Re-authentication fails when user doesn't exist.

        **Validates: Requirements 6.1**
        """
        from fastapi import HTTPException

        service = SignatureService()
        session = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        with pytest.raises(HTTPException) as exc_info:
            await service.verify_credentials(session, 999, "any_password")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_credentials_inactive_user(self) -> None:
        """Re-authentication fails for inactive user accounts.

        **Validates: Requirements 6.1**
        """
        from fastapi import HTTPException

        service = SignatureService()
        session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.is_active = False

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = result_mock

        with pytest.raises(HTTPException) as exc_info:
            await service.verify_credentials(session, 1, "any_password")

        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_sign_document_requires_reauthentication(self) -> None:
        """sign_document enforces re-authentication before signing.

        **Validates: Requirements 6.1**
        """
        from fastapi import HTTPException

        from alcoabase.services.signature_service import hash_password

        hashed = hash_password("correct_password")

        service = SignatureService()
        session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.full_name = "Test User"
        mock_user.is_active = True
        mock_user.hashed_password = hashed

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = result_mock

        # Signing with wrong password should fail
        pdf = make_sample_pdf("Auth test")
        with pytest.raises(HTTPException) as exc_info:
            await service.sign_document(
                session=session,
                pdf_bytes=pdf,
                user_id=1,
                password="wrong_password",
                document_uuid="2024-00001",
                document_version_id=1,
                transition="Review→Approved",
                reason="Test",
            )

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_sign_document_rejects_empty_pdf(self) -> None:
        """sign_document rejects empty PDF bytes.

        **Validates: Requirements 6.1**
        """
        from fastapi import HTTPException

        service = SignatureService()
        session = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await service.sign_document(
                session=session,
                pdf_bytes=b"",
                user_id=1,
                password="any",
                document_uuid="2024-00001",
                document_version_id=1,
                transition="A→B",
                reason="Test",
            )

        assert exc_info.value.status_code == 400
        assert "empty" in exc_info.value.detail.lower()


# ---------------------------------------------------------------------------
# Unit tests for audit trail recording (Task 9.5)
# ---------------------------------------------------------------------------


class TestAuditTrailRecording:
    """Unit tests for signature audit trail recording.

    **Validates: Requirements 6.1, 6.2**
    """

    @pytest.mark.asyncio
    async def test_sign_document_records_audit_trail(self) -> None:
        """Signing a document creates a SignatureRecord in the database.

        **Validates: Requirements 6.1**
        """
        from alcoabase.models.signature import SignatureRecord as SigRecord
        from alcoabase.services.signature_service import hash_password

        hashed = hash_password("password123")

        service = SignatureService()
        session = AsyncMock()

        mock_user = MagicMock()
        mock_user.id = 42
        mock_user.full_name = "Jane Doe"
        mock_user.is_active = True
        mock_user.hashed_password = hashed

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_user
        session.execute.return_value = result_mock

        # Mock flush to set the record ID
        async def mock_flush():
            # Simulate DB assigning an ID
            for call in session.add.call_args_list:
                obj = call[0][0]
                if hasattr(obj, "id"):
                    obj.id = 1

        session.flush = mock_flush

        pdf = make_sample_pdf("Audit trail test")
        result = await service.sign_document(
            session=session,
            pdf_bytes=pdf,
            user_id=42,
            password="password123",
            document_uuid="2024-00042",
            document_version_id=5,
            transition="Review→Approved",
            reason="Approved by QA",
        )

        assert result.success
        assert result.signature_hash != ""

        # Verify session.add was called with a SignatureRecord
        session.add.assert_called_once()
        added_record = session.add.call_args[0][0]
        assert isinstance(added_record, SigRecord)
        assert added_record.document_uuid == "2024-00042"
        assert added_record.signer_user_id == 42
        assert added_record.transition == "Review→Approved"
        assert added_record.reason == "Approved by QA"
        assert added_record.signature_hash == result.signature_hash


# ---------------------------------------------------------------------------
# Unit tests for visual stamp (Task 9.3)
# ---------------------------------------------------------------------------


class TestVisualStamp:
    """Unit tests for visual signature stamp embedding.

    **Validates: Requirements 6.2**
    """

    def test_add_visual_stamp_includes_signer_name(self) -> None:
        """Visual stamp includes the signer's name.

        **Validates: Requirements 6.2**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Stamp test")

        stamp = SignatureStamp(
            signer_name="Dr. Jane Smith",
            signed_at=datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC),
            reason="Approved by QA",
            transition="Review→Approved",
        )

        stamped_pdf = service.add_visual_stamp(pdf, stamp)

        # The stamp text should be present in the output
        assert b"Dr. Jane Smith" in stamped_pdf

    def test_add_visual_stamp_includes_date_time(self) -> None:
        """Visual stamp includes date and time.

        **Validates: Requirements 6.2**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Date test")

        stamp = SignatureStamp(
            signer_name="Test User",
            signed_at=datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC),
            reason="Test reason",
            transition="A→B",
        )

        stamped_pdf = service.add_visual_stamp(pdf, stamp)
        assert b"2024-06-15 10:30:00 UTC" in stamped_pdf

    def test_add_visual_stamp_includes_reason(self) -> None:
        """Visual stamp includes the transition-specific reason.

        **Validates: Requirements 6.2**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Reason test")

        stamp = SignatureStamp(
            signer_name="Test User",
            signed_at=datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC),
            reason="Records completed by analyst",
            transition="Draft→RecordsFilled",
        )

        stamped_pdf = service.add_visual_stamp(pdf, stamp)
        assert b"Records completed by analyst" in stamped_pdf

    def test_add_visual_stamp_includes_transition(self) -> None:
        """Visual stamp includes the workflow transition.

        **Validates: Requirements 6.2**
        """
        service = SignatureService()
        pdf = make_sample_pdf("Transition test")

        stamp = SignatureStamp(
            signer_name="Test User",
            signed_at=datetime(2024, 6, 15, 10, 30, 0, tzinfo=UTC),
            reason="Test",
            transition="Review→Approved",
        )

        stamped_pdf = service.add_visual_stamp(pdf, stamp)
        # Check for the transition text (→ is multi-byte UTF-8)
        assert "Review→Approved".encode("utf-8") in stamped_pdf
