"""Signature model for PAdES electronic signature event logging.

This module defines the SignatureRecord model that captures every
cryptographic signing event for regulatory compliance and audit purposes.

References:
    - PAdES: PDF Advanced Electronic Signatures standard
    - CFR 21 Part 11: FDA regulation for electronic records and signatures
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class SignatureRecord(Base, AuditMixin):
    """Record of a PAdES electronic signature event.

    Each record captures a single signing action, including the signer,
    the document version signed, the workflow transition that triggered
    the signature, and the cryptographic hash of the signature.

    Attributes:
        id: Primary key.
        document_uuid: Document-UUID of the signed document.
        document_version_id: Foreign key to the specific version signed.
        signer_user_id: Foreign key to the signing user.
        transition: Workflow transition that required the signature
            (e.g., "Review→Approved").
        reason: Human-readable reason for the signature
            (e.g., "Approved by QA").
        signed_at: Server-side UTC timestamp of the signing event.
        signature_hash: Cryptographic hash of the PAdES signature.
        certificate_subject: x.509 certificate subject DN (PAdES mode only).
        certificate_issuer: x.509 certificate issuer DN (PAdES mode only).
        certificate_serial: x.509 certificate serial number (PAdES mode only).
        signature_mode: Signing mode used — "hash" or "pades".
    """

    __tablename__ = "signature_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_uuid: Mapped[str] = mapped_column(String(12), index=True)
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey("document_versions.id")
    )
    signer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    transition: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    signature_hash: Mapped[str] = mapped_column(String(256))
    certificate_subject: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    certificate_issuer: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    certificate_serial: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    signature_mode: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default="hash"
    )
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"))
