"""Pydantic v2 schemas for Medical Product endpoints.

Provides request/response schemas for CRUD operations on medical device
products within a company's portfolio. Products store regulatory metadata
used to scope vigilance monitoring activities.

References:
    - Requirements: 2.1, 2.6, 9.1, 9.4
    - Design doc: ProductPortfolioService interface
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DeviceClassEnum = Literal[
    "I", "IIa", "IIb", "III", "IVDR_A", "IVDR_B", "IVDR_C", "IVDR_D"
]

ProductStatusEnum = Literal["active", "discontinued", "recalled"]


class MedicalProductCreateSchema(BaseModel):
    """Request schema for creating a medical product.

    Attributes:
        name: Product name (1–300 characters, required).
        device_class: EU MDR/IVDR device classification.
        intended_purpose: Description of the device's intended use (max 5000 chars).
        udi: Unique Device Identifier (1–128 chars, optional, unique per company).
        gmdn_code: Global Medical Device Nomenclature code (1–20 chars, optional).
        manufacturer_name: Manufacturer name (1–300 chars, optional).
        predicate_devices: List of predicate device names (max 10 entries,
            each 1–300 chars, optional).
        risk_class_justification: Justification for device classification
            (max 3000 chars, optional).
    """

    name: str = Field(..., min_length=1, max_length=300)
    device_class: DeviceClassEnum
    intended_purpose: str = Field(..., min_length=1, max_length=5000)
    udi: str | None = Field(None, min_length=1, max_length=128)
    gmdn_code: str | None = Field(None, min_length=1, max_length=20)
    manufacturer_name: str | None = Field(None, min_length=1, max_length=300)
    predicate_devices: list[str] | None = Field(None, max_length=10)
    risk_class_justification: str | None = Field(None, max_length=3000)

    @field_validator("predicate_devices")
    @classmethod
    def validate_predicate_devices(
        cls, v: list[str] | None
    ) -> list[str] | None:
        """Validate each predicate device entry is 1–300 characters."""
        if v is None:
            return v
        if len(v) > 10:
            msg = "predicate_devices must have at most 10 entries"
            raise ValueError(msg)
        for i, entry in enumerate(v):
            if not 1 <= len(entry) <= 300:
                msg = (
                    f"predicate_devices[{i}] must be 1–300 characters, "
                    f"got {len(entry)}"
                )
                raise ValueError(msg)
        return v


class MedicalProductUpdateSchema(BaseModel):
    """Request schema for updating an existing medical product.

    All fields are optional; only provided fields are updated.

    Attributes:
        name: Updated product name (1–300 chars).
        device_class: Updated device classification.
        intended_purpose: Updated intended use (max 5000 chars).
        udi: Updated UDI (1–128 chars).
        gmdn_code: Updated GMDN code (1–20 chars).
        manufacturer_name: Updated manufacturer name (1–300 chars).
        predicate_devices: Updated predicate devices (max 10, each 1–300 chars).
        risk_class_justification: Updated classification justification (max 3000 chars).
        status: Updated product status.
    """

    name: str | None = Field(None, min_length=1, max_length=300)
    device_class: DeviceClassEnum | None = None
    intended_purpose: str | None = Field(None, min_length=1, max_length=5000)
    udi: str | None = Field(None, min_length=1, max_length=128)
    gmdn_code: str | None = Field(None, min_length=1, max_length=20)
    manufacturer_name: str | None = Field(None, min_length=1, max_length=300)
    predicate_devices: list[str] | None = Field(None, max_length=10)
    risk_class_justification: str | None = Field(None, max_length=3000)
    status: ProductStatusEnum | None = None

    @field_validator("predicate_devices")
    @classmethod
    def validate_predicate_devices(
        cls, v: list[str] | None
    ) -> list[str] | None:
        """Validate each predicate device entry is 1–300 characters."""
        if v is None:
            return v
        if len(v) > 10:
            msg = "predicate_devices must have at most 10 entries"
            raise ValueError(msg)
        for i, entry in enumerate(v):
            if not 1 <= len(entry) <= 300:
                msg = (
                    f"predicate_devices[{i}] must be 1–300 characters, "
                    f"got {len(entry)}"
                )
                raise ValueError(msg)
        return v


class MedicalProductResponseSchema(BaseModel):
    """Response schema for a medical product.

    Attributes:
        id: Product record ID.
        company_id: Company this product belongs to.
        name: Product name.
        device_class: EU MDR/IVDR device classification.
        intended_purpose: Device intended use description.
        udi: Unique Device Identifier (None if not set).
        gmdn_code: GMDN code (None if not set).
        manufacturer_name: Manufacturer name (None if not set).
        predicate_devices: List of predicate device names (None if not set).
        risk_class_justification: Classification justification (None if not set).
        status: Current product status.
        created_by: User ID who created the product.
        created_at: When the product was created.
        updated_at: When the product was last modified.
    """

    id: int
    company_id: int
    name: str
    device_class: DeviceClassEnum
    intended_purpose: str
    udi: str | None = None
    gmdn_code: str | None = None
    manufacturer_name: str | None = None
    predicate_devices: list[str] | None = None
    risk_class_justification: str | None = None
    status: ProductStatusEnum
    created_by: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
