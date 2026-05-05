"""FastAPI router for workflow management endpoints.

Provides CRUD operations for workflow definitions and state transition
management for documents.

Endpoints:
    POST /api/workflows - Create a new workflow definition
    PUT /api/workflows/{workflow_id} - Update a workflow definition
    POST /api/workflows/transition - Request a state transition
    GET /api/workflows/state/{document_uuid} - Get document workflow state
    GET /api/workflows - List all workflow definitions
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.workflow import WorkflowDefinition
from alcoabase.schemas.workflow import (
    DocumentStateResponse,
    TransitionRequest,
    TransitionResponse,
    WorkflowCreateRequest,
    WorkflowResponse,
    WorkflowUpdateRequest,
    WorkflowValidationResponse,
)
from alcoabase.services.workflow_engine import WorkflowEngine, parse_bpmn_xml

router = APIRouter(prefix="/workflows", tags=["Workflows"])


def _get_workflow_engine() -> WorkflowEngine:
    """Provide a WorkflowEngine instance."""
    return WorkflowEngine()


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    request: WorkflowCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    engine: WorkflowEngine = Depends(_get_workflow_engine),
    tenant: TenantContext = Depends(get_tenant_context),
) -> WorkflowResponse:
    """Create a new workflow definition with BPMN validation.

    Validates the BPMN XML, checks document_tag uniqueness, and validates
    signature_required_transitions before persisting.

    Args:
        request: Workflow creation request body.
        session: Database session.
        engine: WorkflowEngine instance.

    Returns:
        The created workflow definition.

    Raises:
        HTTPException: 400 if validation fails.
    """
    # Validate the workflow definition
    validation = await engine.validate_workflow_definition(
        session=session,
        bpmn_xml=request.bpmn_xml,
        document_tag=request.document_tag,
        signature_required_transitions=request.signature_required_transitions,
    )

    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow validation failed: {'; '.join(validation.errors)}",
        )

    # Create the workflow definition
    # TODO: Set company_id=tenant.company_id on created resource
    workflow_def = WorkflowDefinition(
        name=request.name,
        document_tag=request.document_tag,
        bpmn_xml=request.bpmn_xml,
        signature_required_transitions=request.signature_required_transitions,
        training_trigger_transitions=request.training_trigger_transitions,
        is_active=True,
        created_by=1,  # TODO: Get from auth context
    )
    session.add(workflow_def)
    await session.flush()

    return WorkflowResponse(
        id=workflow_def.id,
        name=workflow_def.name,
        document_tag=workflow_def.document_tag,
        bpmn_xml=workflow_def.bpmn_xml,
        signature_required_transitions=workflow_def.signature_required_transitions or [],
        training_trigger_transitions=workflow_def.training_trigger_transitions or [],
        is_active=workflow_def.is_active,
    )


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: int,
    request: WorkflowUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    engine: WorkflowEngine = Depends(_get_workflow_engine),
    tenant: TenantContext = Depends(get_tenant_context),
) -> WorkflowResponse:
    """Update an existing workflow definition.

    Re-validates the BPMN XML if it's being updated.

    Args:
        workflow_id: The workflow definition ID.
        request: Workflow update request body.
        session: Database session.
        engine: WorkflowEngine instance.

    Returns:
        The updated workflow definition.

    Raises:
        HTTPException: 404 if workflow not found.
        HTTPException: 400 if validation fails.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    result = await session.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == workflow_id)
    )
    workflow_def = result.scalar_one_or_none()

    if workflow_def is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Determine the BPMN XML and signature transitions to validate
    bpmn_xml = request.bpmn_xml if request.bpmn_xml is not None else workflow_def.bpmn_xml
    sig_transitions = (
        request.signature_required_transitions
        if request.signature_required_transitions is not None
        else workflow_def.signature_required_transitions
    )

    # Validate if BPMN or signature transitions changed
    if request.bpmn_xml is not None or request.signature_required_transitions is not None:
        validation = await engine.validate_workflow_definition(
            session=session,
            bpmn_xml=bpmn_xml,
            document_tag=workflow_def.document_tag,
            signature_required_transitions=sig_transitions,
            workflow_id=workflow_id,
        )

        if not validation.is_valid:
            raise HTTPException(
                status_code=400,
                detail=f"Workflow validation failed: {'; '.join(validation.errors)}",
            )

    # Apply updates
    if request.name is not None:
        workflow_def.name = request.name
    if request.bpmn_xml is not None:
        workflow_def.bpmn_xml = request.bpmn_xml
    if request.signature_required_transitions is not None:
        workflow_def.signature_required_transitions = request.signature_required_transitions
    if request.training_trigger_transitions is not None:
        workflow_def.training_trigger_transitions = request.training_trigger_transitions
    if request.is_active is not None:
        workflow_def.is_active = request.is_active

    await session.flush()

    return WorkflowResponse(
        id=workflow_def.id,
        name=workflow_def.name,
        document_tag=workflow_def.document_tag,
        bpmn_xml=workflow_def.bpmn_xml,
        signature_required_transitions=workflow_def.signature_required_transitions or [],
        training_trigger_transitions=workflow_def.training_trigger_transitions or [],
        is_active=workflow_def.is_active,
    )


@router.post("/transition", response_model=TransitionResponse)
async def request_transition(
    request: TransitionRequest,
    session: AsyncSession = Depends(get_db_session),
    engine: WorkflowEngine = Depends(_get_workflow_engine),
    tenant: TenantContext = Depends(get_tenant_context),
) -> TransitionResponse:
    """Request a state transition for a document.

    Validates the transition against the BPMN workflow and executes it
    if valid. Returns trigger flags for signature and training hooks.

    Args:
        request: Transition request body.
        session: Database session.
        engine: WorkflowEngine instance.

    Returns:
        TransitionResponse with result and trigger flags.

    Raises:
        HTTPException: 400 if transition is invalid or no workflow defined.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    result = await engine.request_transition(
        session=session,
        document_uuid=request.document_uuid,
        target_state=request.target_state,
        user_id=1,  # TODO: Get from auth context
    )

    return TransitionResponse(
        success=result.success,
        previous_state=result.previous_state,
        new_state=result.new_state,
        requires_signature=result.requires_signature,
        triggers_training=result.triggers_training,
    )


@router.get("/state/{document_uuid}", response_model=DocumentStateResponse)
async def get_document_state(
    document_uuid: str,
    session: AsyncSession = Depends(get_db_session),
    engine: WorkflowEngine = Depends(_get_workflow_engine),
    tenant: TenantContext = Depends(get_tenant_context),
) -> DocumentStateResponse:
    """Get the current workflow state for a document.

    Args:
        document_uuid: The document's unique identifier.
        session: Database session.
        engine: WorkflowEngine instance.

    Returns:
        DocumentStateResponse with current state and valid transitions.

    Raises:
        HTTPException: 404 if document state not found.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    doc_state = await engine.get_document_state(session, document_uuid)

    if doc_state is None:
        raise HTTPException(
            status_code=404,
            detail=f"No workflow state found for document: {document_uuid}",
        )

    # Get workflow definition for name and valid transitions
    result = await session.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == doc_state.workflow_id
        )
    )
    workflow_def = result.scalar_one_or_none()

    valid_transitions: list[str] = []
    workflow_name = "Unknown"
    if workflow_def:
        workflow_name = workflow_def.name
        valid_transitions = engine.get_valid_transitions(
            workflow_def.bpmn_xml, doc_state.current_state
        )

    return DocumentStateResponse(
        document_uuid=document_uuid,
        current_state=doc_state.current_state,
        workflow_name=workflow_name,
        valid_transitions=valid_transitions,
        updated_at=doc_state.updated_at,
    )


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[WorkflowResponse]:
    """List all workflow definitions.

    Args:
        session: Database session.

    Returns:
        List of all workflow definitions.
    """
    # TODO: Pass tenant.company_id to service layer for filtering
    result = await session.execute(select(WorkflowDefinition))
    workflows = result.scalars().all()

    return [
        WorkflowResponse(
            id=w.id,
            name=w.name,
            document_tag=w.document_tag,
            bpmn_xml=w.bpmn_xml,
            signature_required_transitions=w.signature_required_transitions or [],
            training_trigger_transitions=w.training_trigger_transitions or [],
            is_active=w.is_active,
        )
        for w in workflows
    ]
