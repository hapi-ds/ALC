"""Pydantic schemas for signature API request/response models.

References:
    - Design doc Section 6: Signature Service (PAdES)
    - CFR 21 Part 11: Electronic records and signatures
"""

from datetime import datetime

from pydantic import BaseModel, Field


class SignRequest(BaseModel):
    """Request schema for signing a document.

    Attributes:
        document_uuid: Document-UUID of the document to sign.
        document_version_id: ID of the specific version to sign.
        transition: Workflow transition requiring the signature.
        reason: Human-readable reason for the signature.
        password: User's password for re-authentication.
    """

    document_uuid: str = Field(
        ...,
        description="Document-UUID of the document to sign",
        examples=["2024-00001"],
    )
    document_version_id: int = Field(
        ...,
        description="ID of the specific document version to sign",
    )
    transition: str = Field(
        ...,
        description="Workflow transition requiring the signature",
        examples=["Review→Approved"],
    )
    reason: str = Field(
        ...,
        description="Human-readable reason for the signature",
        examples=["Approved by QA Manager"],
    )
    password: str = Field(
        ...,
        description="User's password for re-authentication",
        min_length=1,
    )


class SignatureStampResponse(BaseModel):
    """Response schema for the visual signature stamp data.

    Attributes:
        signer_name: Full name of the signer.
        signed_at: UTC timestamp of the signing event.
        reason: Reason for the signature.
        transition: Workflow transition that triggered signing.
    """

    signer_name: str
    signed_at: datetime
    reason: str
    transition: str


class SignResponse(BaseModel):
    """Response schema for a successful signing operation.

    Attributes:
        success: Whether the signing was successful.
        signature_hash: SHA-256 hash of the signature.
        signature_record_id: Database ID of the signature record.
        stamp: The visual stamp data that was embedded.
    """

    success: bool
    signature_hash: str
    signature_record_id: int | None = None
    stamp: SignatureStampResponse


class SignatureRecordResponse(BaseModel):
    """Response schema for a signature record from the audit trail.

    Attributes:
        id: Primary key of the signature record.
        document_uuid: Document-UUID of the signed document.
        signer_user_id: ID of the signing user.
        transition: Workflow transition that required the signature.
        reason: Reason for the signature.
        signed_at: UTC timestamp of the signing event.
        signature_hash: SHA-256 hash of the signature.
    """

    id: int
    document_uuid: str
    signer_user_id: int
    transition: str
    reason: str | None
    signed_at: datetime
    signature_hash: str

    model_config = {"from_attributes": True}


class VerifyResponse(BaseModel):
    """Response schema for signature verification.

    Attributes:
        is_valid: Whether all signatures are valid.
        signature_count: Number of signatures found.
        tampered_from_index: Index of first invalid signature (-1 if all valid).
    """

    is_valid: bool
    signature_count: int
    tampered_from_index: int = -1
