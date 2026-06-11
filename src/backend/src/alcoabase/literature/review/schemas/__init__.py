"""Pydantic schemas for the Literature Review & Synthesis sub-package (Phase 9.4).

Provides request/response schemas for screening protocols, SLR reviews,
screening decisions, contradiction alerts, novelty flags, and per-company
screening configuration.

References:
    - Requirements: 8.1, 8.2, 8.3, 9.1, 9.3, 9.5, 10.1, 10.5, 11.4, 11.6
    - Design doc: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from alcoabase.literature.review.schemas.configuration import (
    ScreeningConfigurationSchema,
    ScreeningConfigurationUpdateSchema,
)
from alcoabase.literature.review.schemas.contradiction import (
    ContradictionAlertResponseSchema,
    ContradictionStatusUpdateSchema,
    ContradictionSummarySchema,
)
from alcoabase.literature.review.schemas.decision import (
    HumanOverrideRequestSchema,
    ScreeningDecisionResponseSchema,
)
from alcoabase.literature.review.schemas.novelty import (
    NoveltyFlagResponseSchema,
    NoveltyStatusUpdateSchema,
)
from alcoabase.literature.review.schemas.protocol import (
    PICOCriteriaSchema,
    ScreeningProtocolCreateSchema,
    ScreeningProtocolResponseSchema,
    ScreeningProtocolUpdateSchema,
)
from alcoabase.literature.review.schemas.review import (
    InterRaterReliabilitySchema,
    PRISMAFlowSchema,
    ScreeningProgressSchema,
    SLRReportSchema,
    SLRReviewCreateSchema,
    SLRReviewResponseSchema,
)

__all__ = [
    # Protocol
    "PICOCriteriaSchema",
    "ScreeningProtocolCreateSchema",
    "ScreeningProtocolUpdateSchema",
    "ScreeningProtocolResponseSchema",
    # Review
    "SLRReviewCreateSchema",
    "SLRReviewResponseSchema",
    "PRISMAFlowSchema",
    "ScreeningProgressSchema",
    "InterRaterReliabilitySchema",
    "SLRReportSchema",
    # Decision
    "ScreeningDecisionResponseSchema",
    "HumanOverrideRequestSchema",
    # Contradiction
    "ContradictionAlertResponseSchema",
    "ContradictionStatusUpdateSchema",
    "ContradictionSummarySchema",
    # Novelty
    "NoveltyFlagResponseSchema",
    "NoveltyStatusUpdateSchema",
    # Configuration
    "ScreeningConfigurationSchema",
    "ScreeningConfigurationUpdateSchema",
]
