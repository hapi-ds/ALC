"""Pydantic schemas for workflow API request/response models.

Defines the data transfer objects for workflow CRUD operations,
state transitions, and validation results.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class WorkflowCreateRequest(BaseModel):
    """Request schema for creating a new workflow definition.

    Attributes:
        name: Human-readable workflow name.
        document_tag: Unique tag binding (e.g., "SOP", "Report").
        bpmn_xml: BPMN 2.0 XML definition.
        signature_required_transitions: Transitions requiring PAdES signature.
        training_trigger_transitions: Transitions triggering training assignment.
    """

    name: str = Field(..., min_length=1, max_length=200)
    document_tag: str = Field(..., min_length=1, max_length=100)
    bpmn_xml: str = Field(..., min_length=1)
    signature_required_transitions: list[str] = Field(default_factory=list)
    training_trigger_transitions: list[str] = Field(default_factory=list)


class WorkflowUpdateRequest(BaseModel):
    """Request schema for updating an existing workflow definition.

    Attributes:
        name: Updated workflow name (optional).
        bpmn_xml: Updated BPMN XML (optional).
        signature_required_transitions: Updated signature transitions (optional).
        training_trigger_transitions: Updated training transitions (optional).
        is_active: Updated active status (optional).
    """

    name: str | None = Field(None, min_length=1, max_length=200)
    bpmn_xml: str | None = Field(None, min_length=1)
    signature_required_transitions: list[str] | None = None
    training_trigger_transitions: list[str] | None = None
    is_active: bool | None = None


class TransitionRequest(BaseModel):
    """Request schema for requesting a state transition.

    Attributes:
        document_uuid: The document's unique identifier.
        target_state: The desired target state.
    """

    document_uuid: str = Field(..., min_length=1)
    target_state: str = Field(..., min_length=1)


class TransitionResponse(BaseModel):
    """Response schema for a state transition result.

    Attributes:
        success: Whether the transition was accepted.
        previous_state: The state before the transition.
        new_state: The state after the transition.
        requires_signature: Whether this transition requires a PAdES signature.
        triggers_training: Whether this transition triggers training assignment.
    """

    success: bool
    previous_state: str
    new_state: str
    requires_signature: bool = False
    triggers_training: bool = False


class DocumentStateResponse(BaseModel):
    """Response schema for document workflow state.

    Attributes:
        document_uuid: The document's unique identifier.
        current_state: The current workflow state.
        workflow_name: The name of the active workflow.
        valid_transitions: List of valid target states from current state.
        updated_at: Timestamp of last state change.
    """

    document_uuid: str
    current_state: str
    workflow_name: str
    valid_transitions: list[str]
    updated_at: datetime | None = None


class WorkflowResponse(BaseModel):
    """Response schema for a workflow definition.

    Attributes:
        id: Workflow definition ID.
        name: Human-readable workflow name.
        document_tag: Tag binding.
        bpmn_xml: BPMN 2.0 XML definition.
        signature_required_transitions: Transitions requiring signature.
        training_trigger_transitions: Transitions triggering training.
        is_active: Whether the workflow is active.
    """

    id: int
    name: str
    document_tag: str
    bpmn_xml: str
    signature_required_transitions: list[str]
    training_trigger_transitions: list[str]
    is_active: bool


class WorkflowValidationResponse(BaseModel):
    """Response schema for workflow validation results.

    Attributes:
        is_valid: Whether the workflow passed validation.
        errors: List of validation error messages.
    """

    is_valid: bool
    errors: list[str]
