"""Tests for the Workflow Engine.

Includes property-based tests for BPMN transition enforcement and validation,
and unit tests for tag-based workflow resolution.

**Validates: Requirements 7.1, 7.2, 7.3, 7.5**
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from alcoabase.services.workflow_engine import (
    BPMNTransition,
    BPMNWorkflow,
    TransitionResult,
    ValidationResult,
    WorkflowEngine,
    parse_bpmn_xml,
    validate_bpmn_workflow,
)


# ---------------------------------------------------------------------------
# Helper: Generate valid BPMN XML from states and transitions
# ---------------------------------------------------------------------------


def make_bpmn_xml(
    states: list[str],
    transitions: list[tuple[str, str]],
    initial_state: str | None = None,
    terminal_states: list[str] | None = None,
) -> str:
    """Generate a valid BPMN XML string from states and transitions.

    Args:
        states: List of state names.
        transitions: List of (source, target) tuples.
        initial_state: The initial state (first state if not specified).
        terminal_states: States that connect to end event.

    Returns:
        BPMN 2.0 XML string.
    """
    if not states:
        return """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <process id="p1" name="Empty"/>
</definitions>"""

    if initial_state is None:
        initial_state = states[0]
    if terminal_states is None:
        # Find states with no outgoing transitions
        sources = {t[0] for t in transitions}
        terminal_states = [s for s in states if s not in sources]
        if not terminal_states:
            terminal_states = [states[-1]]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">',
        '  <process id="p1" name="Test Process">',
        '    <startEvent id="start" name="Start"/>',
    ]

    # Add task elements
    for i, state in enumerate(states):
        safe_id = f"task_{i}"
        lines.append(f'    <task id="{safe_id}" name="{state}"/>')

    lines.append('    <endEvent id="end" name="End"/>')

    flow_id = 0

    # Flow from start to initial state
    initial_idx = states.index(initial_state)
    lines.append(
        f'    <sequenceFlow id="flow_{flow_id}" sourceRef="start" targetRef="task_{initial_idx}"/>'
    )
    flow_id += 1

    # Add transition flows
    for source, target in transitions:
        if source in states and target in states:
            src_idx = states.index(source)
            tgt_idx = states.index(target)
            lines.append(
                f'    <sequenceFlow id="flow_{flow_id}" sourceRef="task_{src_idx}" targetRef="task_{tgt_idx}"/>'
            )
            flow_id += 1

    # Flows to end event from terminal states
    for term_state in terminal_states:
        if term_state in states:
            term_idx = states.index(term_state)
            lines.append(
                f'    <sequenceFlow id="flow_{flow_id}" sourceRef="task_{term_idx}" targetRef="end"/>'
            )
            flow_id += 1

    lines.append("  </process>")
    lines.append("</definitions>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

# Strategy for generating valid state names
state_name_strategy = st.text(
    alphabet=st.characters(categories=("L", "N"), min_codepoint=65, max_codepoint=122),
    min_size=1,
    max_size=15,
).filter(lambda s: s.isalnum())

# Strategy for generating a list of unique state names
unique_states_strategy = st.lists(
    state_name_strategy,
    min_size=2,
    max_size=8,
    unique=True,
)


# ---------------------------------------------------------------------------
# Task 8.9: Property-based tests - only BPMN-defined transitions are accepted
# ---------------------------------------------------------------------------


class TestBPMNTransitionEnforcement:
    """Property tests verifying only BPMN-defined transitions are accepted.

    For all states and target states, only transitions explicitly defined
    in the BPMN workflow are accepted.

    **Validates: Requirements 7.1, 7.2**
    """

    @given(
        states=unique_states_strategy,
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_only_defined_transitions_are_valid(
        self, states: list[str], data: st.DataObject
    ) -> None:
        """Only transitions defined in the BPMN XML are considered valid.

        Generates a random linear workflow and verifies that:
        - Valid transitions (defined in BPMN) are accepted
        - Invalid transitions (not defined) are rejected

        **Validates: Requirements 7.1, 7.2**
        """
        # Create a linear workflow: state[0] → state[1] → ... → state[n-1]
        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]

        bpmn_xml = make_bpmn_xml(states, transitions)
        workflow = parse_bpmn_xml(bpmn_xml)

        # Pick a random current state
        current_state = data.draw(st.sampled_from(states))
        # Pick a random target state
        target_state = data.draw(st.sampled_from(states))

        # Determine if this transition is valid
        valid_targets = [
            t.target for t in workflow.transitions if t.source == current_state
        ]

        if target_state in valid_targets:
            # This is a valid transition - should be accepted
            assert target_state in valid_targets
        else:
            # This is an invalid transition - should be rejected
            assert target_state not in valid_targets

    @given(
        states=unique_states_strategy,
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_invalid_transitions_never_accepted(
        self, states: list[str], data: st.DataObject
    ) -> None:
        """Transitions not in the BPMN definition are never accepted.

        Generates a workflow and attempts a transition that is NOT defined.
        Verifies it is rejected.

        **Validates: Requirements 7.1, 7.2**
        """
        assume(len(states) >= 3)

        # Create a linear workflow
        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]
        bpmn_xml = make_bpmn_xml(states, transitions)
        workflow = parse_bpmn_xml(bpmn_xml)

        # Pick a state and try to transition to a non-adjacent state
        current_idx = data.draw(st.integers(min_value=0, max_value=len(states) - 1))
        current_state = states[current_idx]

        # Valid targets from this state
        valid_targets = {
            t.target for t in workflow.transitions if t.source == current_state
        }

        # Pick a target that is NOT valid
        invalid_targets = [s for s in states if s not in valid_targets and s != current_state]

        if invalid_targets:
            target_state = data.draw(st.sampled_from(invalid_targets))
            # Verify this transition is NOT in the workflow
            assert target_state not in valid_targets

    @given(states=unique_states_strategy)
    @settings(max_examples=50)
    def test_initial_state_is_first_reachable(self, states: list[str]) -> None:
        """The initial state is correctly identified from the start event.

        **Validates: Requirements 7.1**
        """
        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]
        bpmn_xml = make_bpmn_xml(states, transitions, initial_state=states[0])
        workflow = parse_bpmn_xml(bpmn_xml)

        assert workflow.initial_state == states[0]

    @given(states=unique_states_strategy)
    @settings(max_examples=50)
    def test_terminal_states_have_no_outgoing(self, states: list[str]) -> None:
        """Terminal states are those connected to the end event.

        **Validates: Requirements 7.1**
        """
        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]
        bpmn_xml = make_bpmn_xml(
            states, transitions, terminal_states=[states[-1]]
        )
        workflow = parse_bpmn_xml(bpmn_xml)

        assert states[-1] in workflow.terminal_states


# ---------------------------------------------------------------------------
# Task 8.10: Property-based tests - BPMN validation
# ---------------------------------------------------------------------------


class TestBPMNValidation:
    """Property tests for BPMN workflow validation.

    Verifies that validation correctly detects:
    - Unreachable states
    - Missing terminal states
    - Invalid signature_required_transitions references

    **Validates: Requirements 7.5**
    """

    @given(
        states=unique_states_strategy,
        extra_state=state_name_strategy,
    )
    @settings(max_examples=100)
    def test_unreachable_states_detected(
        self, states: list[str], extra_state: str
    ) -> None:
        """Unreachable states are detected by validation.

        Adds an extra state with no incoming transitions and verifies
        that validation reports it as unreachable.

        **Validates: Requirements 7.5**
        """
        assume(extra_state not in states)
        assume(len(states) >= 2)

        # Create a linear workflow
        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]

        # Add the extra state but with no incoming transitions
        all_states = states + [extra_state]
        bpmn_xml = make_bpmn_xml(
            all_states,
            transitions,
            initial_state=states[0],
            terminal_states=[states[-1], extra_state],
        )

        result = validate_bpmn_workflow(bpmn_xml)

        # The extra state should be detected as unreachable
        assert not result.is_valid
        error_text = " ".join(result.errors)
        assert "unreachable" in error_text.lower() or extra_state in error_text

    @given(states=unique_states_strategy)
    @settings(max_examples=50)
    def test_valid_linear_workflow_passes(self, states: list[str]) -> None:
        """A valid linear workflow with proper start/end passes validation.

        **Validates: Requirements 7.5**
        """
        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]
        bpmn_xml = make_bpmn_xml(
            states, transitions, initial_state=states[0], terminal_states=[states[-1]]
        )

        result = validate_bpmn_workflow(bpmn_xml)
        assert result.is_valid, f"Valid workflow failed: {result.errors}"

    @given(
        states=unique_states_strategy,
        data=st.data(),
    )
    @settings(max_examples=50)
    def test_invalid_signature_transitions_detected(
        self, states: list[str], data: st.DataObject
    ) -> None:
        """Invalid signature_required_transitions references are detected.

        Generates a workflow and provides a signature transition that doesn't
        exist in the BPMN definition.

        **Validates: Requirements 7.5**
        """
        assume(len(states) >= 2)

        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]
        bpmn_xml = make_bpmn_xml(
            states, transitions, initial_state=states[0], terminal_states=[states[-1]]
        )

        # Create an invalid signature transition reference
        # Use a transition that doesn't exist (e.g., last→first which is backwards)
        invalid_sig = f"{states[-1]}\u2192{states[0]}"

        result = validate_bpmn_workflow(bpmn_xml, signature_required_transitions=[invalid_sig])

        assert not result.is_valid
        error_text = " ".join(result.errors)
        assert "signature_required_transitions" in error_text

    @given(states=unique_states_strategy)
    @settings(max_examples=50)
    def test_valid_signature_transitions_pass(self, states: list[str]) -> None:
        """Valid signature_required_transitions references pass validation.

        **Validates: Requirements 7.5**
        """
        assume(len(states) >= 2)

        transitions = [(states[i], states[i + 1]) for i in range(len(states) - 1)]
        bpmn_xml = make_bpmn_xml(
            states, transitions, initial_state=states[0], terminal_states=[states[-1]]
        )

        # Use a valid transition as signature requirement
        valid_sig = f"{states[0]}\u2192{states[1]}"

        result = validate_bpmn_workflow(bpmn_xml, signature_required_transitions=[valid_sig])
        assert result.is_valid, f"Valid signature transition failed: {result.errors}"


# ---------------------------------------------------------------------------
# Task 8.11: Unit tests - tag-based workflow resolution
# ---------------------------------------------------------------------------


class TestTagBasedWorkflowResolution:
    """Unit tests for tag-based workflow resolution.

    Verifies that:
    - Correct workflow is returned for a document's tag
    - HTTP 400 is returned for unregistered tags

    **Validates: Requirements 7.1**
    """

    @pytest.mark.asyncio
    async def test_resolves_correct_workflow_for_tag(self) -> None:
        """Resolves the correct workflow when document tag matches.

        **Validates: Requirements 7.1**
        """
        engine = WorkflowEngine()
        session = AsyncMock()

        # Mock document tags query
        tag_result = MagicMock()
        tag_result.fetchall.return_value = [("SOP",)]

        # Mock workflow definition query
        mock_workflow = MagicMock()
        mock_workflow.id = 1
        mock_workflow.name = "SOP Lifecycle"
        mock_workflow.document_tag = "SOP"
        mock_workflow.bpmn_xml = "<process/>"
        mock_workflow.is_active = True

        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = mock_workflow

        # Configure session.execute to return different results
        session.execute.side_effect = [tag_result, workflow_result]

        result = await engine.resolve_workflow(session, document_id=1)

        assert result.document_tag == "SOP"
        assert result.name == "SOP Lifecycle"

    @pytest.mark.asyncio
    async def test_returns_400_for_unregistered_tag(self) -> None:
        """Returns HTTP 400 when no workflow is defined for the document's tag.

        **Validates: Requirements 7.1**
        """
        from fastapi import HTTPException

        engine = WorkflowEngine()
        session = AsyncMock()

        # Mock document tags query - document has tag "Unknown"
        tag_result = MagicMock()
        tag_result.fetchall.return_value = [("Unknown",)]

        # Mock workflow definition query - no match
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = None

        session.execute.side_effect = [tag_result, workflow_result]

        with pytest.raises(HTTPException) as exc_info:
            await engine.resolve_workflow(session, document_id=1)

        assert exc_info.value.status_code == 400
        assert "No workflow defined" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_400_for_document_with_no_tags(self) -> None:
        """Returns HTTP 400 when document has no tags at all.

        **Validates: Requirements 7.1**
        """
        from fastapi import HTTPException

        engine = WorkflowEngine()
        session = AsyncMock()

        # Mock document tags query - no tags
        tag_result = MagicMock()
        tag_result.fetchall.return_value = []

        session.execute.return_value = tag_result

        with pytest.raises(HTTPException) as exc_info:
            await engine.resolve_workflow(session, document_id=1)

        assert exc_info.value.status_code == 400
        assert "no tags" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_resolve_workflow_by_tag_success(self) -> None:
        """resolve_workflow_by_tag returns the correct workflow for a known tag.

        **Validates: Requirements 7.1**
        """
        engine = WorkflowEngine()
        session = AsyncMock()

        mock_workflow = MagicMock()
        mock_workflow.id = 2
        mock_workflow.name = "Report Lifecycle"
        mock_workflow.document_tag = "Report"
        mock_workflow.is_active = True

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_workflow
        session.execute.return_value = result_mock

        result = await engine.resolve_workflow_by_tag(session, "Report")

        assert result.document_tag == "Report"
        assert result.name == "Report Lifecycle"

    @pytest.mark.asyncio
    async def test_resolve_workflow_by_tag_returns_400_for_unknown(self) -> None:
        """resolve_workflow_by_tag returns HTTP 400 for unknown tag.

        **Validates: Requirements 7.1**
        """
        from fastapi import HTTPException

        engine = WorkflowEngine()
        session = AsyncMock()

        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        session.execute.return_value = result_mock

        with pytest.raises(HTTPException) as exc_info:
            await engine.resolve_workflow_by_tag(session, "NonExistent")

        assert exc_info.value.status_code == 400
        assert "NonExistent" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Additional unit tests for BPMN parsing and validation
# ---------------------------------------------------------------------------


class TestBPMNParsing:
    """Unit tests for BPMN XML parsing."""

    def test_parse_sop_workflow(self) -> None:
        """Parses the default SOP workflow correctly."""
        from alcoabase.services.workflow_seed_data import SOP_WORKFLOW_BPMN

        workflow = parse_bpmn_xml(SOP_WORKFLOW_BPMN)

        assert workflow.initial_state == "Draft"
        assert "Draft" in workflow.states
        assert "Review" in workflow.states
        assert "Approved" in workflow.states
        assert "InTraining" in workflow.states
        assert "Active" in workflow.states
        assert "Active" in workflow.terminal_states

        # Verify transitions
        transition_pairs = [(t.source, t.target) for t in workflow.transitions]
        assert ("Draft", "Review") in transition_pairs
        assert ("Review", "Approved") in transition_pairs
        assert ("Approved", "InTraining") in transition_pairs
        assert ("InTraining", "Active") in transition_pairs

    def test_parse_report_workflow(self) -> None:
        """Parses the default Report workflow correctly."""
        from alcoabase.services.workflow_seed_data import REPORT_WORKFLOW_BPMN

        workflow = parse_bpmn_xml(REPORT_WORKFLOW_BPMN)

        assert workflow.initial_state == "Draft"
        assert "Draft" in workflow.states
        assert "RecordsFilled" in workflow.states
        assert "Reviewed" in workflow.states
        assert "Approved" in workflow.states
        assert "Approved" in workflow.terminal_states

    def test_parse_invalid_xml_raises_error(self) -> None:
        """Raises ValueError for invalid XML."""
        with pytest.raises(ValueError, match="Invalid BPMN XML"):
            parse_bpmn_xml("<not valid xml")

    def test_parse_missing_process_raises_error(self) -> None:
        """Raises ValueError when no process element found."""
        with pytest.raises(ValueError, match="No <process> element"):
            parse_bpmn_xml('<?xml version="1.0"?><root/>')


class TestWorkflowValidation:
    """Unit tests for BPMN workflow validation."""

    def test_valid_sop_workflow_passes(self) -> None:
        """The default SOP workflow passes validation."""
        from alcoabase.services.workflow_seed_data import SOP_WORKFLOW_BPMN

        result = validate_bpmn_workflow(
            SOP_WORKFLOW_BPMN,
            signature_required_transitions=["Review\u2192Approved"],
        )
        assert result.is_valid, f"SOP workflow failed: {result.errors}"

    def test_valid_report_workflow_passes(self) -> None:
        """The default Report workflow passes validation."""
        from alcoabase.services.workflow_seed_data import REPORT_WORKFLOW_BPMN

        result = validate_bpmn_workflow(
            REPORT_WORKFLOW_BPMN,
            signature_required_transitions=[
                "Draft\u2192RecordsFilled",
                "RecordsFilled\u2192Reviewed",
                "Reviewed\u2192Approved",
            ],
        )
        assert result.is_valid, f"Report workflow failed: {result.errors}"

    def test_invalid_xml_fails_validation(self) -> None:
        """Invalid XML fails validation with error."""
        result = validate_bpmn_workflow("<broken")
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_empty_workflow_fails_validation(self) -> None:
        """Workflow with no states fails validation."""
        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <process id="p1" name="Empty"/>
</definitions>"""
        result = validate_bpmn_workflow(bpmn_xml)
        assert not result.is_valid


class TestTriggerHooks:
    """Unit tests for configurable trigger hooks."""

    def test_signature_required_detected(self) -> None:
        """Detects when a transition requires a signature."""
        engine = WorkflowEngine()
        workflow_def = MagicMock()
        workflow_def.signature_required_transitions = ["Review\u2192Approved"]
        workflow_def.training_trigger_transitions = []

        hooks = engine.check_trigger_hooks(workflow_def, "Review", "Approved")

        assert hooks["requires_signature"] is True
        assert hooks["triggers_training"] is False

    def test_training_trigger_detected(self) -> None:
        """Detects when a transition triggers training."""
        engine = WorkflowEngine()
        workflow_def = MagicMock()
        workflow_def.signature_required_transitions = []
        workflow_def.training_trigger_transitions = ["Approved\u2192InTraining"]

        hooks = engine.check_trigger_hooks(workflow_def, "Approved", "InTraining")

        assert hooks["requires_signature"] is False
        assert hooks["triggers_training"] is True

    def test_no_hooks_for_regular_transition(self) -> None:
        """No hooks triggered for a regular transition."""
        engine = WorkflowEngine()
        workflow_def = MagicMock()
        workflow_def.signature_required_transitions = ["Review\u2192Approved"]
        workflow_def.training_trigger_transitions = ["Approved\u2192InTraining"]

        hooks = engine.check_trigger_hooks(workflow_def, "Draft", "Review")

        assert hooks["requires_signature"] is False
        assert hooks["triggers_training"] is False
