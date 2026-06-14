"""Database models for AlcoaBase.

This package contains all SQLAlchemy ORM models for the AlcoaBase system.
Models requiring GxP audit trail versioning should inherit from AuditMixin.
"""

from alcoabase.models.agent import AgentDefinition
from alcoabase.models.anomaly import AnomalyAlert
from alcoabase.models.audit import AuditMixin
from alcoabase.models.audit_access_log import AuditAccessLog
from alcoabase.models.audit_profile import AuditProfile
from alcoabase.models.document_access_log import DocumentAccessLog
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
from alcoabase.models.permission_template import PermissionTemplate
from alcoabase.models.refresh_token import RefreshToken
from alcoabase.models.risk_framework import (
    AIOperationLog,
    AITaskType,
    AuditDepth,
    CheckpointStatus,
    CompanyRiskProfile,
    ControlEnforcementLog,
    GateResult,
    HITLCheckpoint,
    RiskAssessmentRecord,
    RiskTier,
    RiskTierOverride,
)
from alcoabase.models.report import Report, ReportFieldValue
from alcoabase.models.review import (
    ActionItem,
    AgentReview,
    MasterReviewSummary,
    ReviewSession,
)
from alcoabase.models.setup_status import SetupStatus
from alcoabase.models.signature import SignatureRecord
from alcoabase.models.system_config import (
    BackupRecord,
    ConfigurationSnapshot,
    HealthCheckResult,
    ResourceMetricPoint,
    StorageQuota,
    SystemConfiguration,
)
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
    "AIOperationLog",
    "AITaskType",
    "ActionItem",
    "ActiveQuestionSet",
    "AgentDefinition",
    "AgentReview",
    "AnomalyAlert",
    "AuditAccessLog",
    "AuditDepth",
    "AuditMixin",
    "AuditProfile",
    "BackupRecord",
    "CheckpointStatus",
    "Company",
    "CompanyAgentActivation",
    "CompanyMembership",
    "CompanyRiskProfile",
    "ConfigurationSnapshot",
    "ControlEnforcementLog",
    "CoverageSnapshot",
    "CrossReferenceEntry",
    "DependencyEdge",
    "DiscrepancyReport",
    "Document",
    "DocumentAccessLog",
    "DocumentState",
    "DocumentTag",
    "DocumentTemplate",
    "DocumentVersion",
    "DynamicFeedbackCache",
    "GapAnalysisResult",
    "GateResult",
    "GeneratedQuestion",
    "GenerationJobMetadata",
    "GenerationProvenance",
    "HITLCheckpoint",
    "HealthCheckResult",
    "ImmutableRecordError",
    "ImpactNotification",
    "ImpactReport",
    "MasterReviewSummary",
    "PermissionTemplate",
    "ProcessingJob",
    "QuizAttempt",
    "RefreshToken",
    "Report",
    "ReportFieldValue",
    "ResourceMetricPoint",
    "ReviewSession",
    "RiskAssessmentRecord",
    "RiskTier",
    "RiskTierOverride",
    "Role",
    "SetupStatus",
    "SignatureRecord",
    "SkillGap",
    "StaleLinkMarker",
    "StorageQuota",
    "SystemConfiguration",
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
