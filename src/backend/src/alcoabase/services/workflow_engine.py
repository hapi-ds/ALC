"""Workflow Engine for BPMN-based document lifecycle management.

This module implements a simplified BPMN state machine that:
- Parses BPMN XML to extract states and transitions
- Validates requested transitions against the workflow definition
- Supports tag-based workflow resolution
- Records audit trail entries for all state transitions
- Provides configurable trigger hooks for signatures and training

References:
    - Design doc Section 5: Workflow Engine (SpiffWorkflow)
    - Requirements 7: BPMN Workflow State Transition Enforcement
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.models.document import Document, DocumentTag
from alcoabase.models.workflow import DocumentState, WorkflowDefinition


# ---------------------------------------------------------------------------
# BPMN XML Namespace
# ---------------------------------------------------------------------------

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"


# ---------------------------------------------------------------------------
# Data classes for parsed BPMN structures
# ---------------------------------------------------------------------------


@dataclass
class BPMNTransition:
    """A single transition (sequence flow) in the BPMN workflow.

    Attributes:
        source: The source state name.
        target: The target state name.
    """

    source: str
    target: str


@dataclass
class BPMNWorkflow:
    """Parsed BPMN workflow with states and transitions.

    Attributes:
        states: Set of all state names in the workflow.
        transitions: List of valid transitions between states.
        initial_state: The starting state of the workflow.
        terminal_states: Set of states with no outgoing transitions.
    """

    states: set[str] = field(default_factory=set)
    transitions: list[BPMNTransition] = field(default_factory=list)
    initial_state: str | None = None
    terminal_states: set[str] = field(default_factory=set)


@dataclass
class TransitionResult:
    """Result of a state transition request.

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


@dataclass
class ValidationResult:
    """Result of BPMN workflow validation.

    Attributes:
        is_valid: Whether the workflow passed all validation checks.
        errors: List of validation error messages.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# BPMN Parser
# ---------------------------------------------------------------------------


def parse_bpmn_xml(bpmn_xml: str) -> BPMNWorkflow:
    """Parse BPMN XML to extract states and transitions.

    Supports BPMN 2.0 XML with task elements as states and sequence flows
    as transitions. Start events define the initial state, and end events
    define terminal states.

    Args:
        bpmn_xml: BPMN 2.0 XML string.

    Returns:
        BPMNWorkflow with extracted states, transitions, initial and terminal states.

    Raises:
        ValueError: If the XML is malformed or contains no process definition.
    """
    try:
        root = ET.fromstring(bpmn_xml)
    except ET.ParseError as e:
        raise ValueError(f"Invalid BPMN XML: {e}") from e

    # Find the process element (with or without namespace)
    process = root.find(f"{{{BPMN_NS}}}process")
    if process is None:
        process = root.find("process")
    if process is None:
        raise ValueError("No <process> element found in BPMN XML")

    workflow = BPMNWorkflow()

    # Build a map of element IDs to names
    element_names: dict[str, str] = {}

    # Parse start events
    start_event_id: str | None = None
    for elem in _find_elements(process, "startEvent"):
        start_event_id = elem.get("id", "")
        name = elem.get("name", "Start")
        element_names[start_event_id] = name

    # Parse end events
    end_event_ids: set[str] = set()
    for elem in _find_elements(process, "endEvent"):
        eid = elem.get("id", "")
        end_event_ids.add(eid)
        name = elem.get("name", "End")
        element_names[eid] = name

    # Parse tasks (user tasks, service tasks, generic tasks)
    for tag in ("task", "userTask", "serviceTask", "manualTask", "scriptTask"):
        for elem in _find_elements(process, tag):
            eid = elem.get("id", "")
            name = elem.get("name", eid)
            element_names[eid] = name
            workflow.states.add(name)

    # Parse sequence flows (transitions)
    for elem in _find_elements(process, "sequenceFlow"):
        source_id = elem.get("sourceRef", "")
        target_id = elem.get("targetRef", "")

        source_name = element_names.get(source_id)
        target_name = element_names.get(target_id)

        if source_name and target_name:
            # Skip transitions from/to start/end events as state names
            # but use them to determine initial and terminal states
            if source_id == start_event_id:
                workflow.initial_state = target_name
            elif target_id in end_event_ids:
                workflow.terminal_states.add(source_name)
            else:
                workflow.transitions.append(
                    BPMNTransition(source=source_name, target=target_name)
                )
                workflow.states.add(source_name)
                workflow.states.add(target_name)

    # If initial state was set from start event, ensure it's in states
    if workflow.initial_state:
        workflow.states.add(workflow.initial_state)

    # If no terminal states found from end events, identify states with no outgoing transitions
    if not workflow.terminal_states:
        states_with_outgoing = {t.source for t in workflow.transitions}
        workflow.terminal_states = workflow.states - states_with_outgoing

    return workflow


def _find_elements(process: ET.Element, tag: str) -> list[ET.Element]:
    """Find elements by tag name, checking both namespaced and non-namespaced.

    Args:
        process: The parent XML element to search within.
        tag: The local tag name to search for.

    Returns:
        List of matching XML elements.
    """
    elements = process.findall(f"{{{BPMN_NS}}}{tag}")
    elements.extend(process.findall(tag))
    return elements


# ---------------------------------------------------------------------------
# BPMN Validation
# ---------------------------------------------------------------------------


def validate_bpmn_workflow(
    bpmn_xml: str,
    signature_required_transitions: list[str] | None = None,
) -> ValidationResult:
    """Validate a BPMN workflow definition for correctness.

    Checks:
    - No unreachable states (all states reachable from initial state)
    - At least one terminal state exists
    - All signature_required_transitions reference valid transitions

    Args:
        bpmn_xml: BPMN 2.0 XML string to validate.
        signature_required_transitions: List of transition strings to validate
            (format: "Source→Target").

    Returns:
        ValidationResult with is_valid flag and list of errors.
    """
    errors: list[str] = []

    try:
        workflow = parse_bpmn_xml(bpmn_xml)
    except ValueError as e:
        return ValidationResult(is_valid=False, errors=[str(e)])

    if not workflow.states:
        errors.append("Workflow contains no states")
        return ValidationResult(is_valid=False, errors=errors)

    # Check for initial state
    if not workflow.initial_state:
        errors.append("Workflow has no initial state (missing start event)")

    # Check for terminal states
    if not workflow.terminal_states:
        errors.append("Workflow has no terminal states (missing end event)")

    # Check for unreachable states
    if workflow.initial_state:
        reachable = _find_reachable_states(workflow)
        unreachable = workflow.states - reachable
        if unreachable:
            errors.append(
                f"Unreachable states detected: {sorted(unreachable)}"
            )

    # Validate signature_required_transitions references
    if signature_required_transitions:
        valid_transitions = {
            f"{t.source}\u2192{t.target}" for t in workflow.transitions
        }
        for sig_transition in signature_required_transitions:
            if sig_transition not in valid_transitions:
                errors.append(
                    f"signature_required_transitions references invalid "
                    f"transition: '{sig_transition}'"
                )

    return ValidationResult(is_valid=len(errors) == 0, errors=errors)


def _find_reachable_states(workflow: BPMNWorkflow) -> set[str]:
    """Find all states reachable from the initial state via BFS.

    Args:
        workflow: The parsed BPMN workflow.

    Returns:
        Set of state names reachable from the initial state.
    """
    if not workflow.initial_state:
        return set()

    reachable: set[str] = {workflow.initial_state}
    queue = [workflow.initial_state]

    # Build adjacency list
    adjacency: dict[str, list[str]] = {}
    for t in workflow.transitions:
        adjacency.setdefault(t.source, []).append(t.target)

    while queue:
        current = queue.pop(0)
        for neighbor in adjacency.get(current, []):
            if neighbor not in reachable:
                reachable.add(neighbor)
                queue.append(neighbor)

    return reachable


# ---------------------------------------------------------------------------
# Workflow Engine
# ---------------------------------------------------------------------------


class WorkflowEngine:
    """Engine for managing BPMN-based document workflow state transitions.

    Provides methods for:
    - Resolving workflows by document tag
    - Validating and executing state transitions
    - Recording audit trail entries
    - Checking trigger hooks (signatures, training)

    Usage:
        engine = WorkflowEngine()
        result = await engine.request_transition(session, doc_uuid, "Review", user_id=1)
    """

    async def resolve_workflow(
        self, session: AsyncSession, document_id: int
    ) -> WorkflowDefinition:
        """Resolve the applicable workflow for a document based on its tags.

        Matches document tags against WorkflowDefinition.document_tag to find
        the active workflow definition.

        Args:
            session: Active async database session.
            document_id: The document's primary key ID.

        Returns:
            The matching WorkflowDefinition.

        Raises:
            HTTPException: 400 if no workflow is defined for the document's tags.
        """
        # Get document tags
        result = await session.execute(
            select(DocumentTag.tag).where(DocumentTag.document_id == document_id)
        )
        tags = [row[0] for row in result.fetchall()]

        if not tags:
            raise HTTPException(
                status_code=400,
                detail="No workflow defined: document has no tags",
            )

        # Find matching workflow definition
        result = await session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.document_tag.in_(tags),
                WorkflowDefinition.is_active.is_(True),
            )
        )
        workflow_def = result.scalar_one_or_none()

        if workflow_def is None:
            raise HTTPException(
                status_code=400,
                detail=f"No workflow defined for document tags: {tags}",
            )

        return workflow_def

    async def resolve_workflow_by_tag(
        self, session: AsyncSession, tag: str
    ) -> WorkflowDefinition:
        """Resolve the applicable workflow for a specific document tag.

        Args:
            session: Active async database session.
            tag: The document tag to match.

        Returns:
            The matching WorkflowDefinition.

        Raises:
            HTTPException: 400 if no workflow is defined for the tag.
        """
        result = await session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.document_tag == tag,
                WorkflowDefinition.is_active.is_(True),
            )
        )
        workflow_def = result.scalar_one_or_none()

        if workflow_def is None:
            raise HTTPException(
                status_code=400,
                detail=f"No workflow defined for document tag: '{tag}'",
            )

        return workflow_def

    async def request_transition(
        self,
        session: AsyncSession,
        document_uuid: str,
        target_state: str,
        user_id: int,
    ) -> TransitionResult:
        """Validate and execute a state transition for a document.

        Args:
            session: Active async database session.
            document_uuid: The document's unique identifier.
            target_state: The desired target state.
            user_id: The user requesting the transition.

        Returns:
            TransitionResult with transition details and trigger flags.

        Raises:
            HTTPException: 400 if the transition is invalid.
            HTTPException: 400 if no workflow is defined for the document.
        """
        # Load document
        result = await session.execute(
            select(Document).where(Document.document_uuid == document_uuid)
        )
        document = result.scalar_one_or_none()
        if document is None:
            raise HTTPException(
                status_code=400,
                detail=f"Document not found: {document_uuid}",
            )

        # Resolve workflow
        workflow_def = await self.resolve_workflow(session, document.id)

        # Parse BPMN
        workflow = parse_bpmn_xml(workflow_def.bpmn_xml)

        # Get current state
        doc_state = await self._get_or_create_document_state(
            session, document.id, workflow_def.id, workflow.initial_state or "", user_id
        )
        current_state = doc_state.current_state

        # Validate transition
        valid_transitions = [
            t for t in workflow.transitions
            if t.source == current_state and t.target == target_state
        ]

        if not valid_transitions:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid transition: '{current_state}' → '{target_state}' "
                    f"is not allowed by the workflow definition"
                ),
            )

        # Execute transition
        previous_state = current_state
        doc_state.current_state = target_state
        doc_state.updated_at = datetime.now(UTC)
        doc_state.updated_by = user_id

        # Update document current_status
        document.current_status = target_state

        # Record audit trail
        await self._record_transition_audit(
            session, document.id, user_id, previous_state, target_state
        )

        # Check trigger hooks
        transition_str = f"{previous_state}\u2192{target_state}"
        requires_signature = transition_str in (
            workflow_def.signature_required_transitions or []
        )
        triggers_training = transition_str in (
            workflow_def.training_trigger_transitions or []
        )

        return TransitionResult(
            success=True,
            previous_state=previous_state,
            new_state=target_state,
            requires_signature=requires_signature,
            triggers_training=triggers_training,
        )

    async def get_document_state(
        self, session: AsyncSession, document_uuid: str
    ) -> DocumentState | None:
        """Get the current workflow state for a document.

        Args:
            session: Active async database session.
            document_uuid: The document's unique identifier.

        Returns:
            The DocumentState or None if no state exists.
        """
        result = await session.execute(
            select(DocumentState)
            .join(Document, Document.id == DocumentState.document_id)
            .where(Document.document_uuid == document_uuid)
        )
        return result.scalar_one_or_none()

    async def validate_workflow_definition(
        self,
        session: AsyncSession,
        bpmn_xml: str,
        document_tag: str,
        signature_required_transitions: list[str] | None = None,
        workflow_id: int | None = None,
    ) -> ValidationResult:
        """Validate a workflow definition before saving.

        Checks:
        - BPMN XML is valid with no unreachable/missing terminal states
        - document_tag is unique (no other active workflow uses it)
        - All signature_required_transitions reference valid transitions

        Args:
            session: Active async database session.
            bpmn_xml: BPMN 2.0 XML string.
            document_tag: The tag to bind the workflow to.
            signature_required_transitions: Transitions requiring signatures.
            workflow_id: If updating, the ID of the existing workflow (to exclude
                from uniqueness check).

        Returns:
            ValidationResult with is_valid flag and errors.
        """
        # Validate BPMN structure
        result = validate_bpmn_workflow(bpmn_xml, signature_required_transitions)
        errors = list(result.errors)

        # Check document_tag uniqueness
        query = select(WorkflowDefinition).where(
            WorkflowDefinition.document_tag == document_tag,
            WorkflowDefinition.is_active.is_(True),
        )
        if workflow_id is not None:
            query = query.where(WorkflowDefinition.id != workflow_id)

        existing = await session.execute(query)
        if existing.scalar_one_or_none() is not None:
            errors.append(
                f"document_tag '{document_tag}' is already used by another active workflow"
            )

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    async def _get_or_create_document_state(
        self,
        session: AsyncSession,
        document_id: int,
        workflow_id: int,
        initial_state: str,
        user_id: int,
    ) -> DocumentState:
        """Get existing document state or create one at the initial state.

        Args:
            session: Active async database session.
            document_id: The document's primary key.
            workflow_id: The workflow definition's primary key.
            initial_state: The initial state if creating new.
            user_id: The user ID for the state record.

        Returns:
            The DocumentState instance.
        """
        result = await session.execute(
            select(DocumentState).where(
                DocumentState.document_id == document_id
            )
        )
        doc_state = result.scalar_one_or_none()

        if doc_state is None:
            doc_state = DocumentState(
                document_id=document_id,
                current_state=initial_state,
                workflow_id=workflow_id,
                updated_by=user_id,
            )
            session.add(doc_state)
            await session.flush()

        return doc_state

    async def _record_transition_audit(
        self,
        session: AsyncSession,
        document_id: int,
        user_id: int,
        previous_state: str,
        new_state: str,
    ) -> None:
        """Record a state transition in the audit trail.

        Creates a WorkflowTransitionAudit record with user_id, timestamp,
        previous_state, and new_state.

        Args:
            session: Active async database session.
            document_id: The document's primary key.
            user_id: The user who triggered the transition.
            previous_state: The state before the transition.
            new_state: The state after the transition.
        """
        audit_entry = WorkflowTransitionAudit(
            document_id=document_id,
            user_id=user_id,
            previous_state=previous_state,
            new_state=new_state,
            timestamp=datetime.now(UTC),
        )
        session.add(audit_entry)

    def get_valid_transitions(
        self, bpmn_xml: str, current_state: str
    ) -> list[str]:
        """Get all valid target states from the current state.

        Args:
            bpmn_xml: BPMN 2.0 XML string.
            current_state: The current state name.

        Returns:
            List of valid target state names.
        """
        workflow = parse_bpmn_xml(bpmn_xml)
        return [
            t.target
            for t in workflow.transitions
            if t.source == current_state
        ]

    def check_trigger_hooks(
        self,
        workflow_def: WorkflowDefinition,
        previous_state: str,
        new_state: str,
    ) -> dict[str, bool]:
        """Check if a transition triggers any hooks.

        Args:
            workflow_def: The workflow definition to check against.
            previous_state: The source state of the transition.
            new_state: The target state of the transition.

        Returns:
            Dict with 'requires_signature' and 'triggers_training' flags.
        """
        transition_str = f"{previous_state}\u2192{new_state}"
        return {
            "requires_signature": transition_str in (
                workflow_def.signature_required_transitions or []
            ),
            "triggers_training": transition_str in (
                workflow_def.training_trigger_transitions or []
            ),
        }


# ---------------------------------------------------------------------------
# Audit model for workflow transitions
# ---------------------------------------------------------------------------


from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base


class WorkflowTransitionAudit(Base):
    """Audit trail record for workflow state transitions.

    Records every state transition with full attribution for
    regulatory compliance.

    Attributes:
        id: Primary key.
        document_id: Foreign key to the document.
        user_id: The user who triggered the transition.
        previous_state: The state before the transition.
        new_state: The state after the transition.
        timestamp: Server-side UTC timestamp of the transition.
    """

    __tablename__ = "workflow_transition_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    previous_state: Mapped[str] = mapped_column(String(50))
    new_state: Mapped[str] = mapped_column(String(50))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
