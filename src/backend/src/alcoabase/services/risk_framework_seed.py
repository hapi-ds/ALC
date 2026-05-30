"""Seed data for default AI task types in the Risk & Compliance Framework.

Creates the 8 system-defined AI task types with their default risk tiers,
risk factors, and module references. These entries form the Default_Risk_Profile
that applies when a company has not configured a custom Company_Risk_Profile.

The seed function is idempotent — it skips task types that already exist
by task_type_id.

References:
    - Design: .kiro/specs/Step_8-1_ai-risk-compliance-framework/design.md
    - Requirements: 1.2 (Default AI Task Types in Default_Risk_Profile)
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.risk_framework import AITaskType, RiskTier


# Default AI task type definitions per Requirements 1.2
DEFAULT_AI_TASK_TYPES: list[dict] = [
    {
        "task_type_id": "document_generation",
        "display_name": "Document Generation",
        "description": (
            "Generates GxP-regulated content such as SOPs, protocols, and reports "
            "that may enter approval workflows and become controlled documents."
        ),
        "module_reference": "5.4",
        "default_risk_tier": RiskTier.HIGH.value,
        "risk_factors": [
            "Generates GxP-regulated content that may enter approval workflows",
            "Output may become controlled documents subject to regulatory audit",
            "Errors in generated content could propagate through approval chains",
            "Content directly impacts product quality and patient safety decisions",
        ],
    },
    {
        "task_type_id": "multi_agent_audit",
        "display_name": "Multi-Agent Audit",
        "description": (
            "Produces compliance assessments using multiple AI agent archetypes "
            "that influence approval decisions and regulatory submissions."
        ),
        "module_reference": "5.2",
        "default_risk_tier": RiskTier.HIGH.value,
        "risk_factors": [
            "Produces compliance assessments that influence approval decisions",
            "Multi-agent consensus may mask individual agent errors",
            "Assessment outcomes directly gate regulatory submissions",
            "Incorrect assessments could lead to non-compliant approvals",
        ],
    },
    {
        "task_type_id": "training_content_generation",
        "display_name": "Training Content Generation",
        "description": (
            "Generates training materials and comprehension assessments that gate "
            "user access to GxP operations and controlled document workflows."
        ),
        "module_reference": "5.3",
        "default_risk_tier": RiskTier.HIGH.value,
        "risk_factors": [
            "Generates training materials and assessments that gate user access to GxP operations",
            "Incorrect training content could lead to unqualified personnel performing critical tasks",
            "Quiz questions directly determine personnel competency certification",
            "Training gaps may result in regulatory non-compliance findings",
        ],
    },
    {
        "task_type_id": "change_impact_analysis",
        "display_name": "Change Impact Analysis",
        "description": (
            "Identifies documents and processes affected by a proposed change. "
            "Analyzes dependencies but does not modify any documents or records."
        ),
        "module_reference": "5.5",
        "default_risk_tier": RiskTier.MEDIUM.value,
        "risk_factors": [
            "Identifies affected documents but does not modify them",
            "Missed dependencies could lead to incomplete change control",
            "Output informs human decision-making but does not execute changes",
            "Errors are catchable during human review of impact assessment",
        ],
    },
    {
        "task_type_id": "traceability_gap_discovery",
        "display_name": "Traceability Gap Discovery",
        "description": (
            "Identifies gaps in traceability matrices between requirements, "
            "specifications, and test records. Does not create or modify "
            "traceability records."
        ),
        "module_reference": "5.6",
        "default_risk_tier": RiskTier.MEDIUM.value,
        "risk_factors": [
            "Identifies gaps but does not create or modify traceability records",
            "Missed gaps could leave compliance blind spots unaddressed",
            "Output guides human remediation actions rather than executing them",
            "False positives create investigation overhead but no data integrity risk",
        ],
    },
    {
        "task_type_id": "rag_knowledge_query",
        "display_name": "RAG Knowledge Query",
        "description": (
            "Retrieves and summarizes existing approved content from the knowledge "
            "base using retrieval-augmented generation without creating new records."
        ),
        "module_reference": "4.2",
        "default_risk_tier": RiskTier.LOW.value,
        "risk_factors": [
            "Retrieves and summarizes existing approved content without creating new records",
            "Output is informational and does not enter controlled document workflows",
            "Source content is already approved — summarization adds interpretation risk only",
            "Users are expected to verify against source documents before acting",
        ],
    },
    {
        "task_type_id": "document_search",
        "display_name": "Document Search",
        "description": (
            "Performs hybrid lexical and semantic search across existing indexed "
            "content to help users locate relevant documents and sections."
        ),
        "module_reference": "4.1",
        "default_risk_tier": RiskTier.LOW.value,
        "risk_factors": [
            "Performs hybrid search across existing indexed content",
            "Does not generate or modify any content",
            "Ranking errors may surface less relevant results but cause no data integrity risk",
            "Users independently verify search results before taking action",
        ],
    },
    {
        "task_type_id": "template_analysis",
        "display_name": "Template Analysis",
        "description": (
            "Analyzes document structure and template schemas to extract field "
            "definitions, section layouts, and validation rules without generating "
            "new content."
        ),
        "module_reference": "2.4",
        "default_risk_tier": RiskTier.LOW.value,
        "risk_factors": [
            "Analyzes document structure without generating content",
            "Output describes existing template properties — no new regulated content created",
            "Errors in analysis are visible during template configuration review",
            "No downstream workflow or approval process depends on analysis output",
        ],
    },
]


async def seed_default_ai_task_types(
    session: AsyncSession,
) -> list[AITaskType]:
    """Create default AI task types if they don't already exist.

    This function is idempotent — it skips task types that already exist
    by task_type_id. All created entries are marked as system-defined
    (is_system_defined=True, company_id=None).

    Args:
        session: Active async database session.

    Returns:
        List of created AITaskType instances (empty if all already exist).
    """
    created: list[AITaskType] = []

    for task_def in DEFAULT_AI_TASK_TYPES:
        # Check if task type already exists by task_type_id
        result = await session.execute(
            select(AITaskType).where(
                AITaskType.task_type_id == task_def["task_type_id"]
            )
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            task_type = AITaskType(
                task_type_id=task_def["task_type_id"],
                display_name=task_def["display_name"],
                description=task_def["description"],
                module_reference=task_def["module_reference"],
                default_risk_tier=task_def["default_risk_tier"],
                risk_factors=task_def["risk_factors"],
                is_active=True,
                is_system_defined=True,
                company_id=None,
            )
            session.add(task_type)
            created.append(task_type)

    if created:
        await session.flush()

    return created
