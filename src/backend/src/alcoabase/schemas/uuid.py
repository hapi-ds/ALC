"""Pydantic schemas and annotated types for UUID validation.

Provides validated types for the two UUID formats used in AlcoaBase:
- DocumentUUID: Validates the YYYY-NNNNN pattern (e.g., "2026-00001")
- FieldUUID: Validates the FLD-XXXXXXXX pattern (e.g., "FLD-A1B2C3D4")

These types can be used directly in Pydantic models and FastAPI
request/response schemas for automatic validation.

References:
    - Design doc Section 2: UUID Generation Service
    - Requirements 1.1: Document-UUID format YYYY-NNNNN
    - Requirements 3.2: Field-UUID format FLD-XXXXXXXX
"""

from typing import Annotated

from pydantic import Field


# Document-UUID: 4-digit year, dash, 5-digit zero-padded sequence
DocumentUUID = Annotated[
    str,
    Field(
        pattern=r"^\d{4}-\d{5}$",
        description="Document-UUID in YYYY-NNNNN format (e.g., '2026-00001').",
        examples=["2026-00001", "2025-00042"],
    ),
]

# Field-UUID: "FLD-" prefix followed by exactly 8 uppercase hex characters
FieldUUID = Annotated[
    str,
    Field(
        pattern=r"^FLD-[A-F0-9]{8}$",
        description="Field-UUID in FLD-XXXXXXXX format (e.g., 'FLD-A1B2C3D4').",
        examples=["FLD-A1B2C3D4", "FLD-00FF11AA"],
    ),
]
