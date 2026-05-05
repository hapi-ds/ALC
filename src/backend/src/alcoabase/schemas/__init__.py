"""Pydantic request/response schemas for AlcoaBase API."""

from alcoabase.schemas.setup import (
    AIModeConfig,
    AIModeResult,
    CompanyResult,
    CompanySetupCreate,
    RootAdminCreate,
    RootAdminResult,
    SetupCompleteRequest,
    SetupCompleteResult,
    SetupProgress,
)

__all__ = [
    "AIModeConfig",
    "AIModeResult",
    "CompanyResult",
    "CompanySetupCreate",
    "RootAdminCreate",
    "RootAdminResult",
    "SetupCompleteRequest",
    "SetupCompleteResult",
    "SetupProgress",
]
