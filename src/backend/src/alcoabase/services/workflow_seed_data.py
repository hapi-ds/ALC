"""Seed data for default workflow definitions.

Creates the default SOP and Report workflows that are available upon
initial system setup.

References:
    - Design doc Section 5: Workflow Engine
    - Task 8.7: Default SOP and Report workflows
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.workflow import WorkflowDefinition


# ---------------------------------------------------------------------------
# Default SOP Workflow BPMN XML
# States: Draft → Review → Approved → InTraining → Active
# Signature on: Review→Approved
# Training trigger on: Approved→InTraining
# ---------------------------------------------------------------------------

SOP_WORKFLOW_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             id="sop-workflow"
             targetNamespace="http://alcoabase.local/workflows">
  <process id="sop-lifecycle" name="SOP Lifecycle">
    <startEvent id="start" name="Start"/>
    <task id="draft" name="Draft"/>
    <task id="review" name="Review"/>
    <task id="approved" name="Approved"/>
    <task id="intraining" name="InTraining"/>
    <task id="active" name="Active"/>
    <endEvent id="end" name="End"/>
    <sequenceFlow id="flow1" sourceRef="start" targetRef="draft"/>
    <sequenceFlow id="flow2" sourceRef="draft" targetRef="review"/>
    <sequenceFlow id="flow3" sourceRef="review" targetRef="approved"/>
    <sequenceFlow id="flow4" sourceRef="approved" targetRef="intraining"/>
    <sequenceFlow id="flow5" sourceRef="intraining" targetRef="active"/>
    <sequenceFlow id="flow6" sourceRef="active" targetRef="end"/>
  </process>
</definitions>"""

# ---------------------------------------------------------------------------
# Default Report Workflow BPMN XML
# States: Draft → RecordsFilled → Reviewed → Approved
# Signature on: all transitions
# ---------------------------------------------------------------------------

REPORT_WORKFLOW_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             id="report-workflow"
             targetNamespace="http://alcoabase.local/workflows">
  <process id="report-lifecycle" name="Report Lifecycle">
    <startEvent id="start" name="Start"/>
    <task id="draft" name="Draft"/>
    <task id="records_filled" name="RecordsFilled"/>
    <task id="reviewed" name="Reviewed"/>
    <task id="approved" name="Approved"/>
    <endEvent id="end" name="End"/>
    <sequenceFlow id="flow1" sourceRef="start" targetRef="draft"/>
    <sequenceFlow id="flow2" sourceRef="draft" targetRef="records_filled"/>
    <sequenceFlow id="flow3" sourceRef="records_filled" targetRef="reviewed"/>
    <sequenceFlow id="flow4" sourceRef="reviewed" targetRef="approved"/>
    <sequenceFlow id="flow5" sourceRef="approved" targetRef="end"/>
  </process>
</definitions>"""


# ---------------------------------------------------------------------------
# Default workflow definitions
# ---------------------------------------------------------------------------

DEFAULT_WORKFLOWS = [
    {
        "name": "SOP Lifecycle",
        "document_tag": "SOP",
        "bpmn_xml": SOP_WORKFLOW_BPMN,
        "signature_required_transitions": ["Review\u2192Approved"],
        "training_trigger_transitions": ["Approved\u2192InTraining"],
    },
    {
        "name": "Report Lifecycle",
        "document_tag": "Report",
        "bpmn_xml": REPORT_WORKFLOW_BPMN,
        "signature_required_transitions": [
            "Draft\u2192RecordsFilled",
            "RecordsFilled\u2192Reviewed",
            "Reviewed\u2192Approved",
        ],
        "training_trigger_transitions": [],
    },
]


async def seed_default_workflows(
    session: AsyncSession, system_user_id: int = 1
) -> list[WorkflowDefinition]:
    """Create default workflow definitions if they don't already exist.

    This function is idempotent — it skips workflows that already exist
    by document_tag.

    Args:
        session: Active async database session.
        system_user_id: User ID to assign as creator (defaults to system user).

    Returns:
        List of created WorkflowDefinition instances (empty if all already exist).
    """
    created: list[WorkflowDefinition] = []

    for workflow_def in DEFAULT_WORKFLOWS:
        # Check if workflow already exists for this tag
        result = await session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.document_tag == workflow_def["document_tag"]
            )
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            workflow = WorkflowDefinition(
                name=workflow_def["name"],
                document_tag=workflow_def["document_tag"],
                bpmn_xml=workflow_def["bpmn_xml"],
                signature_required_transitions=workflow_def[
                    "signature_required_transitions"
                ],
                training_trigger_transitions=workflow_def[
                    "training_trigger_transitions"
                ],
                is_active=True,
                created_by=system_user_id,
            )
            session.add(workflow)
            created.append(workflow)

    if created:
        await session.flush()

    return created
