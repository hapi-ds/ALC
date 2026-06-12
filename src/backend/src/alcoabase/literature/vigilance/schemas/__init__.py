"""Pydantic v2 schemas for the Vigilance & Post-Market Surveillance module.

Contains request/response schemas for medical products, vigilance search
profiles, search executions, vigilance signals, periodic safety reports,
and vigilance configuration management.

References:
    - Requirements: 2.1, 2.6, 3.1, 3.6, 6.4, 8.5, 9.1, 9.6, 10.1, 10.3, 11.1, 11.3
"""

from alcoabase.literature.vigilance.schemas.configuration import (
    VigilanceConfigurationSchema,
    VigilanceConfigurationUpdateSchema,
)
from alcoabase.literature.vigilance.schemas.execution import (
    ExecutionListResponseSchema,
    VigilanceSearchExecutionResponseSchema,
)
from alcoabase.literature.vigilance.schemas.product import (
    MedicalProductCreateSchema,
    MedicalProductResponseSchema,
    MedicalProductUpdateSchema,
)
from alcoabase.literature.vigilance.schemas.profile import (
    VigilanceSearchProfileCreateSchema,
    VigilanceSearchProfileResponseSchema,
    VigilanceSearchProfileUpdateSchema,
)
from alcoabase.literature.vigilance.schemas.report import (
    PeriodicSafetyReportResponseSchema,
    ReportGenerateRequestSchema,
    ReportStatusUpdateSchema,
)
from alcoabase.literature.vigilance.schemas.signal import (
    SignalDispositionUpdateSchema,
    SignalSummaryResponseSchema,
    VigilanceSignalResponseSchema,
)

__all__ = [
    "ExecutionListResponseSchema",
    "MedicalProductCreateSchema",
    "MedicalProductResponseSchema",
    "MedicalProductUpdateSchema",
    "PeriodicSafetyReportResponseSchema",
    "ReportGenerateRequestSchema",
    "ReportStatusUpdateSchema",
    "SignalDispositionUpdateSchema",
    "SignalSummaryResponseSchema",
    "VigilanceConfigurationSchema",
    "VigilanceConfigurationUpdateSchema",
    "VigilanceSearchExecutionResponseSchema",
    "VigilanceSearchProfileCreateSchema",
    "VigilanceSearchProfileResponseSchema",
    "VigilanceSearchProfileUpdateSchema",
    "VigilanceSignalResponseSchema",
]
