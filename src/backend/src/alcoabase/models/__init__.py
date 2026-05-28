"""Database models for AlcoaBase.

This package contains all SQLAlchemy ORM models for the AlcoaBase system.
Models requiring GxP audit trail versioning should inherit from AuditMixin.
"""

from alcoabase.models.agent import AgentDefinition
from alcoabase.models.anomaly import AnomalyAlert
from alcoabase.models.audit import AuditMixin
from alcoabase.models.audit_profile import AuditProfile
from alcoabase.models.company import Company, CompanyAgentActivation, CompanyMembership
from alcoabase.models.document import Document, DocumentTag, DocumentVersion
from alcoabase.models.document_generation import (
    CrossReferenceEntry,
    DocumentTemplate,
    GenerationJobMetadata,
    GenerationProvenance,
)
from alcoabase.models.immutability import ImmutableRecordError
from alcoabase.models.impact_analysis import (
    DependencyEdge,
    GapAnalysisResult,
    ImpactNotification,
    ImpactReport,
)
from alcoabase.models.refresh_token import RefreshToken
from alcoabase.models.report import Report, ReportFieldValue
from alcoabase.models.review import (
    ActionItem,
    AgentReview,
    MasterReviewSummary,
    ReviewSession,
)
from alcoabase.models.setup_status import SetupStatus
from alcoabase.models.signature import SignatureRecord
from alcoabase.models.template import Template, TemplateField
from alcoabase.models.template_version import TemplateVersion, TemplateVersionField
from alcoabase.models.training import QuizAttempt, TrainingRecord, TrainingTask
from alcoabase.models.training_ecosystem import (
    ActiveQuestionSet,
    DynamicFeedbackCache,
    GeneratedQuestion,
    SkillGap,
    TrainingMaterial,
    TrainingSchedule,
    VirtualAuditSession,
)
from alcoabase.models.traceability import (
    CoverageSnapshot,
    StaleLinkMarker,
    TraceabilityAlert,
    TraceabilityMatrix,
)
from alcoabase.models.user import Role, User, UserRole
from alcoabase.models.video import (
    DiscrepancyReport,
    ProcessingJob,
    VideoMetadata,
    VideoSOPLink,
    VideoStepSequence,
)
from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.models.workflow import DocumentState, WorkflowDefinition, WorkflowVersion

__all__ = [
    "ActionItem",
    "ActiveQuestionSet",
    "AgentDefinition",
    "AgentReview",
    "AnomalyAlert",
    "AuditMixin",
    "AuditProfile",
    "Company",
    "CompanyAgentActivation",
    "CompanyMembership",
    "CoverageSnapshot",
    "CrossReferenceEntry",
    "DependencyEdge",
    "DiscrepancyReport",
    "Document",
    "DocumentState",
    "DocumentTag",
    "DocumentTemplate",
    "DocumentVersion",
    "DynamicFeedbackCache",
    "GapAnalysisResult",
    "GeneratedQuestion",
    "GenerationJobMetadata",
    "GenerationProvenance",
    "ImmutableRecordError",
    "ImpactNotification",
    "ImpactReport",
    "MasterReviewSummary",
    "ProcessingJob",
    "QuizAttempt",
    "RefreshToken",
    "Report",
    "ReportFieldValue",
    "ReviewSession",
    "Role",
    "SetupStatus",
    "SignatureRecord",
    "SkillGap",
    "StaleLinkMarker",
    "Template",
    "TemplateField",
    "TemplateVersion",
    "TemplateVersionField",
    "TraceabilityAlert",
    "TraceabilityMatrix",
    "TrainingMaterial",
    "TrainingRecord",
    "TrainingSchedule",
    "TrainingTask",
    "User",
    "UserRole",
    "VideoMetadata",
    "VideoSOPLink",
    "VideoStepSequence",
    "VirtualAuditSession",
    "VirtualFolder",
    "WorkflowDefinition",
    "WorkflowVersion",
]
