"""FastAPI router for workflow management endpoints.

Provides CRUD operations for workflow definitions, versioning,
validation, and state transition management for documents.

Endpoints:
    POST /api/workflows - Create a new workflow definition
    POST /api/workflows/validate - Validate BPMN XML without persisting
    PUT /api/workflows/{workflow_id} - Update a workflow definition
    GET /api/workflows - List all workflow definitions (tenant-scoped)
    GET /api/workflows/{workflow_id} - Get a single workflow definition
    DELETE /api/workflows/{workflow_id} - Delete a workflow definition
    GET /api/workflows/{workflow_id}/versions - List version history
    GET /api/workflows/{workflow_id}/versions/{version_id} - Get version detail
    POST /api/workflows/transition - Request a state transition
    GET /api/workflows/state/{document_uuid} - Get document workflow state
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.models.workflow import (
    DocumentState,
    WorkflowDefinition,
    WorkflowVersion,
)
from alcoabase.schemas.workflow import (
    DocumentStateResponse,
    TransitionRequest,
    TransitionResponse,
    WorkflowCreateRequest,
    WorkflowResponse,
    WorkflowUpdateRequest,
    WorkflowValidationResponse,
    WorkflowVersionDetail,
    WorkflowVersionSummary,
)
from alcoabase.services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/workflows", tags=["Workflows"])


class WorkflowValidateRequest(BaseModel):
    """Request schema for standalone workflow validation.

    Attributes:
        bpmn_xml: BPMN 2.0 XML to validate.
        signature_required_transitions: Optional list of transitions to validate.
    """

    bpmn_xml: str = Field(..., min_length=1)
    signature_required_transitions: list[str] = Field(default_factory=list)


def _get_workflow_engine() -> WorkflowEngine:
    """Provide a WorkflowEngine instance."""
    return WorkflowEngine()


def _build_workflow_response(workflow_def: WorkflowDefinition) -> WorkflowResponse:
    """Build a WorkflowResponse from a WorkflowDefinition model instance."""
    return WorkflowResponse(
        id=workflow_def.id,
        name=workflow_def.name,
        document_tag=workflow_def.document_tag,
        bpmn_xml=workflow_def.bpmn_xml,
        signature_required_transitions=workflow_def.signature_required_transitions or [],
        training_trigger_transitions=workflow_def.training_trigger_transitions or [],
        is_active=workflow_def.is_active,
        risk_level=workflow_def.risk_level or "low",
        auto_assignment_config=workflow_def.auto_assignment_config,
        current_version_number=workflow_def.current_version,
    )


@router.post("/validate", response_model=WorkflowValidationResponse)
async def validate_workflow(
    body: WorkflowValidateRequest,
    session: AsyncSession = Depends(get_db_session),
    engine: WorkflowEngine = Depends(_get_workflow_engine),
    tenant: TenantContext = Depends(get_tenant_context),
) -> WorkflowValidationResponse:
    """Validate BPMN XML without creating or updating a workflow.

    Performs structural validation of the BPMN XML and checks that
    signature_required_transitions reference valid transitions.

    Args:
        body: Validation request with bpmn_xml and optional transitions.
        session: Database session.
        engine: WorkflowEngine instance.
        tenant: Resolved tenant context.

    Returns:
        WorkflowValidationResponse with is_valid flag and errors list.
    """
    from alcoabase.services.workflow_engine import validate_bpmn_workflow

    result = validate_bpmn_workflow(
        bpmn_xml=body.bpmn_xml,
        signature_required_transitions=body.signature_required_transitions or None,
    )

    return WorkflowValidationResponse(
        is_valid=result.is_valid,
        errors=result.errors,
    )


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    body: WorkflowCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    engine: WorkflowEngine = Depends(_get_workflow_engine),
    tenant: TenantContext = Depends(get_tenant_context),
) -> WorkflowResponse:
    """Create a new workflow definition with BPMN validation.

    Validates the BPMN XML, checks document_tag uniqueness, and validates
    signature_required_transitions before persisting. Creates an initial
    WorkflowVersion record (version 1).

    Args:
        body: Workflow creation request body.
        request: The incoming HTTP request (for X-Change-Reason header).
        session: Database session.
        engine: WorkflowEngine instance.
        tenant: Resolved tenant context.

    Returns:
        The created workflow definition.

    Raises:
        HTTPException: 400 if validation fails.
    """
    # Validate the workflow definition
    validation = await engine.validate_workflow_definition(
        session=session,
        bpmn_xml=body.bpmn_xml,
        document_tag=body.document_tag,
        signature_required_transitions=body.signature_required_transitions,
    )

    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Workflow validation failed: {'; '.join(validation.errors)}",
        )

    # Create the workflow definition with tenant scoping
    workflow_def = WorkflowDefinition(
        name=body.name,
        document_tag=body.document_tag,
        bpmn_xml=body.bpmn_xml,
        signature_required_transitions=body.signature_required_transitions,
        training_trigger_transitions=body.training_trigger_transitions,
        risk_level=body.risk_level,
        auto_assignment_config=body.auto_assignment_config,
        is_active=True,
        current_version=1,
        created_by=tenant.user_id,
        company_id=tenant.company_id,
    )
    session.add(workflow_def)
    await session.flush()

    # Create initial WorkflowVersion record (version 1)
    change_reason = request.headers.get("x-change-reason") or "Workflow created"
    version_record = WorkflowVersion(
        workflow_id=workflow_def.id,
        version_number=1,
        bpmn_xml=workflow_def.bpmn_xml,
        name=workflow_def.name,
        document_tag=workflow_def.document_tag,
        risk_level=workflow_def.risk_level,
        signature_required_transitions=workflow_def.signature_required_transitions,
        training_trigger_transitions=workflow_def.training_trigger_transitions,
        auto_assignment_config=workflow_def.auto_assignment_config,
        created_by=tenant.user_id,
        change_reason=change_reason,
        company_id=tenant.company_id,
    )
    session.add(version_record)
    await session.flush()

    return _build_workflow_response(workflow_def)


@router.put("/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(
    workflow_id: int,
    body: WorkflowUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    engine: WorkflowEngine = Depends(_get_workflow_engine),
    tenant: TenantContext = Depends(get_tenant_context),
) -> WorkflowResponse:
    """Update an existing workflow definition.

    Re-validates the BPMN XML if it's being updated. Creates a new
    WorkflowVersion record if structural changes (bpmn_xml, transitions)
    are detected.

    Args:
        workflow_id: The workflow definition ID.
        body: Workflow update request body.
        request: The incoming HTTP request (for X-Change-Reason header).
        session: Database session.
        engine: WorkflowEngine instance.
        tenant: Resolved tenant context.

    Returns:
        The updated workflow definition.

    Raises:
        HTTPException: 404 if workflow not found or wrong tenant.
        HTTPException: 400 if validation fails.
    """
    # Tenant-scoped query
    result = await session.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.company_id == tenant.company_id,
        )
    )
    workflow_def = result.scalar_one_or_none()

    if workflow_def is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Determine the BPMN XML and signature transitions to validate
    bpmn_xml = body.bpmn_xml if body.bpmn_xml is not None else workflow_def.bpmn_xml
    sig_transitions = (
        body.signature_required_transitions
        if body.signature_required_transitions is not None
        else workflow_def.signature_required_transitions
    )

    # Validate if BPMN or signature transitions changed
    if body.bpmn_xml is not None or body.signature_required_transitions is not None:
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

    # Detect structural changes for versioning
    structural_change = False
    if body.bpmn_xml is not None and body.bpmn_xml != workflow_def.bpmn_xml:
        structural_change = True
    if (
        body.signature_required_transitions is not None
        and body.signature_required_transitions != workflow_def.signature_required_transitions
    ):
        structural_change = True
    if (
        body.training_trigger_transitions is not None
        and body.training_trigger_transitions != workflow_def.training_trigger_transitions
    ):
        structural_change = True

    # Apply updates
    if body.name is not None:
        workflow_def.name = body.name
    if body.bpmn_xml is not None:
        workflow_def.bpmn_xml = body.bpmn_xml
    if body.signature_required_transitions is not None:
        workflow_def.signature_required_transitions = body.signature_required_transitions
    if body.training_trigger_transitions is not None:
        workflow_def.training_trigger_transitions = body.training_trigger_transitions
    if body.is_active is not None:
        workflow_def.is_active = body.is_active
    if body.risk_level is not None:
        workflow_def.risk_level = body.risk_level
    if body.auto_assignment_config is not None:
        workflow_def.auto_assignment_config = body.auto_assignment_config

    # Create new version on structural changes
    if structural_change:
        workflow_def.current_version += 1
        change_reason = request.headers.get("x-change-reason") or "Workflow updated"
        version_record = WorkflowVersion(
            workflow_id=workflow_def.id,
            version_number=workflow_def.current_version,
            bpmn_xml=workflow_def.bpmn_xml,
            name=workflow_def.name,
            document_tag=workflow_def.document_tag,
            risk_level=workflow_def.risk_level,
            signature_required_transitions=workflow_def.signature_required_transitions,
            training_trigger_transitions=workflow_def.training_trigger_transitions,
            auto_assignment_config=workflow_def.auto_assignment_config,
            created_by=tenant.user_id,
            change_reason=change_reason,
            company_id=tenant.company_id,
        )
        session.add(version_record)

    await session.flush()

    return _build_workflow_response(workflow_def)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[WorkflowResponse]:
    """List all workflow definitions scoped to the current tenant.

    Args:
        session: Database session.
        tenant: Resolved tenant context.

    Returns:
        List of workflow definitions for the tenant.
    """
    result = await session.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.company_id == tenant.company_id
        )
    )
    workflows = result.scalars().all()

    return [_build_workflow_response(w) for w in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> WorkflowResponse:
    """Get a single workflow definition by ID, scoped to tenant.

    Args:
        workflow_id: The workflow definition ID.
        session: Database session.
        tenant: Resolved tenant context.

    Returns:
        The workflow definition.

    Raises:
        HTTPException: 404 if workflow not found or belongs to different tenant.
    """
    result = await session.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.company_id == tenant.company_id,
        )
    )
    workflow_def = result.scalar_one_or_none()

    if workflow_def is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return _build_workflow_response(workflow_def)


@router.delete("/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> None:
    """Delete a workflow definition and all associated versions.

    Checks for active DocumentState records referencing the workflow
    before deletion. Returns 409 if the workflow is in use.

    Args:
        workflow_id: The workflow definition ID.
        session: Database session.
        tenant: Resolved tenant context.

    Returns:
        None (204 No Content on success).

    Raises:
        HTTPException: 404 if workflow not found or belongs to different tenant.
        HTTPException: 409 if workflow is in use by active documents.
    """
    # Find workflow scoped to tenant
    result = await session.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.company_id == tenant.company_id,
        )
    )
    workflow_def = result.scalar_one_or_none()

    if workflow_def is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Check for active DocumentState records referencing this workflow
    active_states_result = await session.execute(
        select(DocumentState).where(DocumentState.workflow_id == workflow_id).limit(1)
    )
    if active_states_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail="Workflow cannot be deleted because it is in use by active documents",
        )

    # Delete all associated WorkflowVersion records
    await session.execute(
        delete(WorkflowVersion).where(WorkflowVersion.workflow_id == workflow_id)
    )

    # Delete the workflow definition
    await session.delete(workflow_def)
    await session.flush()


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionSummary])
async def list_workflow_versions(
    workflow_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> list[WorkflowVersionSummary]:
    """List version history for a workflow, ordered by version_number descending.

    Args:
        workflow_id: The workflow definition ID.
        session: Database session.
        tenant: Resolved tenant context.

    Returns:
        List of WorkflowVersionSummary records.

    Raises:
        HTTPException: 404 if workflow not found or belongs to different tenant.
    """
    # Verify workflow exists and belongs to tenant
    wf_result = await session.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.company_id == tenant.company_id,
        )
    )
    if wf_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Fetch versions ordered by version_number descending
    versions_result = await session.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_number.desc())
    )
    versions = versions_result.scalars().all()

    return [
        WorkflowVersionSummary(
            version_number=v.version_number,
            created_by=v.created_by,
            created_at=v.created_at,
            change_reason=v.change_reason,
        )
        for v in versions
    ]


@router.get(
    "/{workflow_id}/versions/{version_id}",
    response_model=WorkflowVersionDetail,
)
async def get_workflow_version(
    workflow_id: int,
    version_id: int,
    session: AsyncSession = Depends(get_db_session),
    tenant: TenantContext = Depends(get_tenant_context),
) -> WorkflowVersionDetail:
    """Get a single workflow version with full detail including bpmn_xml.

    Args:
        workflow_id: The workflow definition ID.
        version_id: The version record ID.
        session: Database session.
        tenant: Resolved tenant context.

    Returns:
        WorkflowVersionDetail with all fields.

    Raises:
        HTTPException: 404 if workflow or version not found, or wrong tenant.
    """
    # Verify workflow exists and belongs to tenant
    wf_result = await session.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.company_id == tenant.company_id,
        )
    )
    if wf_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Fetch the specific version
    version_result = await session.execute(
        select(WorkflowVersion).where(
            WorkflowVersion.id == version_id,
            WorkflowVersion.workflow_id == workflow_id,
        )
    )
    version = version_result.scalar_one_or_none()

    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")

    return WorkflowVersionDetail(
        version_number=version.version_number,
        bpmn_xml=version.bpmn_xml,
        name=version.name,
        document_tag=version.document_tag,
        risk_level=version.risk_level,
        signature_required_transitions=version.signature_required_transitions or [],
        training_trigger_transitions=version.training_trigger_transitions or [],
        auto_assignment_config=version.auto_assignment_config,
        created_by=version.created_by,
        created_at=version.created_at,
        change_reason=version.change_reason,
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
        tenant: Resolved tenant context.

    Returns:
        TransitionResponse with result and trigger flags.

    Raises:
        HTTPException: 400 if transition is invalid or no workflow defined.
    """
    result = await engine.request_transition(
        session=session,
        document_uuid=request.document_uuid,
        target_state=request.target_state,
        user_id=tenant.user_id,
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
        tenant: Resolved tenant context.

    Returns:
        DocumentStateResponse with current state and valid transitions.

    Raises:
        HTTPException: 404 if document state not found.
    """
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
