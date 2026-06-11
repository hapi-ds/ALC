"""Service layer for the Literature Review & Synthesis subsystem (Phase 9.4).

This sub-package contains business logic services for screening configuration,
screening protocol management, SLR review lifecycle, screener agent orchestration,
contradiction detection, and structured audit logging.
"""

from alcoabase.literature.review.services.audit_logger import (
    EVENT_CONTRADICTION_ALERT_CREATED,
    EVENT_CONTRADICTION_ALERT_STATUS_CHANGE,
    EVENT_HUMAN_OVERRIDE,
    EVENT_NOVELTY_FLAG_CREATED,
    EVENT_RETRY_ATTEMPT,
    EVENT_SCREENING_DECISION,
    EVENT_SLR_REVIEW_STATE_TRANSITION,
    log_contradiction_alert_created,
    log_contradiction_alert_status_change,
    log_human_override,
    log_novelty_flag_created,
    log_retry_attempt,
    log_screening_decision,
    log_slr_review_state_transition,
)
from alcoabase.literature.review.services.contradiction_detection_service import (
    ContradictionAnalysisResult,
    ContradictionDetectionService,
)
from alcoabase.literature.review.services.screener_agent_runner import (
    LiteratureScreenerAgentRunner,
    ScreeningResult,
)
from alcoabase.literature.review.services.screening_config_service import (
    ScreeningConfigService,
)
from alcoabase.literature.review.services.screening_protocol_service import (
    ScreeningProtocolService,
)
from alcoabase.literature.review.services.slr_review_service import (
    SLRReviewService,
)

__all__ = [
    "ContradictionAnalysisResult",
    "ContradictionDetectionService",
    "EVENT_CONTRADICTION_ALERT_CREATED",
    "EVENT_CONTRADICTION_ALERT_STATUS_CHANGE",
    "EVENT_HUMAN_OVERRIDE",
    "EVENT_NOVELTY_FLAG_CREATED",
    "EVENT_RETRY_ATTEMPT",
    "EVENT_SCREENING_DECISION",
    "EVENT_SLR_REVIEW_STATE_TRANSITION",
    "LiteratureScreenerAgentRunner",
    "SLRReviewService",
    "ScreeningConfigService",
    "ScreeningProtocolService",
    "ScreeningResult",
    "log_contradiction_alert_created",
    "log_contradiction_alert_status_change",
    "log_human_override",
    "log_novelty_flag_created",
    "log_retry_attempt",
    "log_screening_decision",
    "log_slr_review_state_transition",
]
