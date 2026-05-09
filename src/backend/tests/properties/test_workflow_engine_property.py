"""Property-based tests for BPMN XML parsing and validation.

Tests Property 1 (BPMN XML state and transition extraction consistency)
and Property 8 (Backend validation rejects invalid workflows) from the
BPMN Workflow Visual Editor design document.

**Validates: Requirements 12.2, 12.3, 16.1**

References:
    - Design: .kiro/specs/Step_3-1_bpmn-workflow-visual-editor/design.md
    - Requirements: .kiro/specs/Step_3-1_bpmn-workflow-visual-editor/requirements.md
"""

import random

import hypothesis.strategies as st
from hypothesis import assume, given, settings

from alcoabase.services.workflow_engine import (
    parse_bpmn_xml,
    validate_bpmn_workflow,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_state_name() -> st.SearchStrategy[str]:
    """Generate a valid state name (alphanumeric, non-empty).

    Returns:
        Strategy producing state name strings.
    """
    return st.text(
        alphabet=st.characters(
            categories=("L", "N"), min_codepoint=65, max_codepoint=122
        ),
        min_size=2,
        max_size=15,
    ).filter(lambda s: s.isalnum() and len(s) >= 2)


def st_unique_states(
    min_size: int = 2, max_size: int = 8
) -> st.SearchStrategy[list[str]]:
    """Generate a list of unique state names.

    Args:
        min_size: Minimum number of states.
        max_size: Maximum number of states.

    Returns:
        Strategy producing lists of unique state name strings.
    """
    return st.lists(
        st_state_name(),
        min_size=min_size,
        max_size=max_size,
        unique=True,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_bpmn_xml(
    states: list[str],
    transitions: list[tuple[str, str]],
    initial_state: str | None = None,
    terminal_states: list[str] | None = None,
) -> str:
    """Generate a valid BPMN XML string from states and transitions.

    Args:
        states: List of state names (tasks).
        transitions: List of (source, target) tuples for sequence flows.
        initial_state: The state connected from the start event.
        terminal_states: States connected to the end event.

    Returns:
        BPMN 2.0 XML string.
    """
    if not states:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">'
            '  <process id="p1" name="Empty"/>'
            "</definitions>"
        )

    if initial_state is None:
        initial_state = states[0]
    if terminal_states is None:
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

    for i, state in enumerate(states):
        lines.append(f'    <task id="task_{i}" name="{state}"/>')

    lines.append('    <endEvent id="end" name="End"/>')

    flow_id = 0

    # Flow from start to initial state
    initial_idx = states.index(initial_state)
    lines.append(
        f'    <sequenceFlow id="flow_{flow_id}" '
        f'sourceRef="start" targetRef="task_{initial_idx}"/>'
    )
    flow_id += 1

    # Add transition flows between tasks
    for source, target in transitions:
        if source in states and target in states:
            src_idx = states.index(source)
            tgt_idx = states.index(target)
            lines.append(
                f'    <sequenceFlow id="flow_{flow_id}" '
                f'sourceRef="task_{src_idx}" targetRef="task_{tgt_idx}"/>'
            )
            flow_id += 1

    # Flows to end event from terminal states
    for term_state in terminal_states:
        if term_state in states:
            term_idx = states.index(term_state)
            lines.append(
                f'    <sequenceFlow id="flow_{flow_id}" '
                f'sourceRef="task_{term_idx}" targetRef="end"/>'
            )
            flow_id += 1

    lines.append("  </process>")
    lines.append("</definitions>")

    return "\n".join(lines)


def make_shuffled_bpmn_xml(
    states: list[str],
    transitions: list[tuple[str, str]],
    initial_state: str,
    terminal_states: list[str],
    seed: int,
) -> str:
    """Generate BPMN XML with elements in a shuffled order.

    Uses a seeded random to shuffle task elements and sequence flow elements
    independently, producing a different XML element ordering while
    maintaining the same logical structure.

    Args:
        states: List of state names.
        transitions: List of (source, target) tuples.
        initial_state: The initial state name.
        terminal_states: Terminal state names.
        seed: Random seed for shuffling.

    Returns:
        BPMN 2.0 XML string with shuffled element ordering.
    """
    rng = random.Random(seed)

    # Create indexed state list and shuffle it
    indexed_states = list(enumerate(states))
    rng.shuffle(indexed_states)

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL">',
        '  <process id="p1" name="Test Process">',
    ]

    # Build all elements in a list, then shuffle
    elements: list[str] = []
    elements.append('    <startEvent id="start" name="Start"/>')
    elements.append('    <endEvent id="end" name="End"/>')

    for orig_idx, state in indexed_states:
        elements.append(f'    <task id="task_{orig_idx}" name="{state}"/>')

    rng.shuffle(elements)
    lines.extend(elements)

    # Build sequence flows and shuffle them
    flows: list[str] = []
    flow_id = 0

    initial_idx = states.index(initial_state)
    flows.append(
        f'    <sequenceFlow id="flow_{flow_id}" '
        f'sourceRef="start" targetRef="task_{initial_idx}"/>'
    )
    flow_id += 1

    for source, target in transitions:
        src_idx = states.index(source)
        tgt_idx = states.index(target)
        flows.append(
            f'    <sequenceFlow id="flow_{flow_id}" '
            f'sourceRef="task_{src_idx}" targetRef="task_{tgt_idx}"/>'
        )
        flow_id += 1

    for term_state in terminal_states:
        term_idx = states.index(term_state)
        flows.append(
            f'    <sequenceFlow id="flow_{flow_id}" '
            f'sourceRef="task_{term_idx}" targetRef="end"/>'
        )
        flow_id += 1

    rng.shuffle(flows)
    lines.extend(flows)

    lines.append("  </process>")
    lines.append("</definitions>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Property 1: BPMN XML state and transition extraction consistency
# ---------------------------------------------------------------------------


class TestBPMNXMLParsingConsistency:
    """Property tests verifying BPMN XML parsing produces consistent results
    regardless of element ordering.

    For any valid BPMN XML containing Task elements and Sequence Flows,
    parse_bpmn_xml SHALL extract the same set of states and transitions
    regardless of element ordering in the XML.

    **Validates: Requirements 16.1**
    """

    @given(
        states=st_unique_states(min_size=2, max_size=6),
        data=st.data(),
    )
    @settings(max_examples=100)
    def test_parsing_consistent_regardless_of_element_order(
        self, states: list[str], data: st.DataObject
    ) -> None:
        """Parsing BPMN XML produces the same states and transitions
        regardless of element ordering in the XML document.

        **Validates: Requirements 16.1**
        """
        # Build a linear workflow: state[0] -> state[1] -> ... -> state[n-1]
        transitions = [
            (states[i], states[i + 1]) for i in range(len(states) - 1)
        ]
        initial_state = states[0]
        terminal_states = [states[-1]]

        # Parse the canonical ordering
        canonical_xml = make_bpmn_xml(
            states, transitions, initial_state, terminal_states
        )
        canonical_workflow = parse_bpmn_xml(canonical_xml)

        # Parse a shuffled ordering
        seed = data.draw(st.integers(min_value=0, max_value=10000))
        shuffled_xml = make_shuffled_bpmn_xml(
            states, transitions, initial_state, terminal_states, seed
        )
        shuffled_workflow = parse_bpmn_xml(shuffled_xml)

        # States should be identical sets
        assert canonical_workflow.states == shuffled_workflow.states, (
            f"States differ: canonical={canonical_workflow.states}, "
            f"shuffled={shuffled_workflow.states}"
        )

        # Transitions should be identical sets (order-independent)
        canonical_trans = {
            (t.source, t.target) for t in canonical_workflow.transitions
        }
        shuffled_trans = {
            (t.source, t.target) for t in shuffled_workflow.transitions
        }
        assert canonical_trans == shuffled_trans, (
            f"Transitions differ: canonical={canonical_trans}, "
            f"shuffled={shuffled_trans}"
        )

        # Initial state should be the same
        assert (
            canonical_workflow.initial_state == shuffled_workflow.initial_state
        ), (
            f"Initial state differs: "
            f"canonical={canonical_workflow.initial_state}, "
            f"shuffled={shuffled_workflow.initial_state}"
        )

        # Terminal states should be the same
        assert (
            canonical_workflow.terminal_states
            == shuffled_workflow.terminal_states
        ), (
            f"Terminal states differ: "
            f"canonical={canonical_workflow.terminal_states}, "
            f"shuffled={shuffled_workflow.terminal_states}"
        )

    @given(
        states=st_unique_states(min_size=2, max_size=6),
    )
    @settings(max_examples=100)
    def test_extracted_states_equal_task_names(
        self, states: list[str]
    ) -> None:
        """The extracted states SHALL equal the set of all Task name
        attributes.

        **Validates: Requirements 16.1**
        """
        # Build a connected workflow so all states are reachable
        transitions = [
            (states[i], states[i + 1]) for i in range(len(states) - 1)
        ]
        initial_state = states[0]
        terminal_states = [states[-1]]

        bpmn_xml = make_bpmn_xml(
            states, transitions, initial_state, terminal_states
        )
        workflow = parse_bpmn_xml(bpmn_xml)

        # All task names should appear as states
        assert workflow.states == set(states), (
            f"Expected states={set(states)}, got={workflow.states}"
        )

    @given(
        states=st_unique_states(min_size=3, max_size=6),
    )
    @settings(max_examples=100)
    def test_extracted_transitions_equal_sequence_flows(
        self, states: list[str]
    ) -> None:
        """The extracted transitions SHALL equal the set of all Sequence Flows
        connecting Task elements (excluding start/end event flows).

        **Validates: Requirements 16.1**
        """
        # Build a linear workflow
        transitions = [
            (states[i], states[i + 1]) for i in range(len(states) - 1)
        ]
        initial_state = states[0]
        terminal_states = [states[-1]]

        bpmn_xml = make_bpmn_xml(
            states, transitions, initial_state, terminal_states
        )
        workflow = parse_bpmn_xml(bpmn_xml)

        # Extracted transitions should match the defined task-to-task flows
        extracted_trans = {
            (t.source, t.target) for t in workflow.transitions
        }
        expected_trans = set(transitions)

        assert extracted_trans == expected_trans, (
            f"Expected transitions={expected_trans}, got={extracted_trans}"
        )


# ---------------------------------------------------------------------------
# Property 8: Backend validation rejects invalid workflows
# ---------------------------------------------------------------------------


class TestBackendValidationRejectsInvalid:
    """Property tests verifying that validate_bpmn_workflow correctly rejects
    invalid workflows.

    For any BPMN XML containing unreachable states, validation SHALL return
    is_valid=False with an error mentioning "unreachable". For any invalid
    signature_required_transitions, validation SHALL return is_valid=False.

    **Validates: Requirements 12.2, 12.3**
    """

    @given(
        connected_states=st_unique_states(min_size=2, max_size=5),
        unreachable_states=st_unique_states(min_size=1, max_size=3),
    )
    @settings(max_examples=100)
    def test_unreachable_states_detected(
        self,
        connected_states: list[str],
        unreachable_states: list[str],
    ) -> None:
        """BPMN XML with unreachable states SHALL produce is_valid=False
        with an error mentioning "unreachable".

        **Validates: Requirements 12.2**
        """
        # Ensure no overlap between connected and unreachable states
        assume(not set(connected_states) & set(unreachable_states))

        # Build a connected workflow
        transitions = [
            (connected_states[i], connected_states[i + 1])
            for i in range(len(connected_states) - 1)
        ]
        initial_state = connected_states[0]
        terminal_states = [connected_states[-1]]

        # Add unreachable states (tasks with no incoming transitions from
        # the connected component)
        all_states = connected_states + unreachable_states

        bpmn_xml = make_bpmn_xml(
            all_states, transitions, initial_state, terminal_states
        )

        result = validate_bpmn_workflow(bpmn_xml)

        assert result.is_valid is False, (
            f"Expected is_valid=False for unreachable states "
            f"{unreachable_states}, got is_valid=True"
        )
        # At least one error should mention "unreachable" (case-insensitive)
        has_unreachable_error = any(
            "unreachable" in err.lower() for err in result.errors
        )
        assert has_unreachable_error, (
            f"Expected error mentioning 'unreachable', got: {result.errors}"
        )

    @given(
        states=st_unique_states(min_size=2, max_size=5),
        invalid_transitions=st.lists(
            st_state_name(), min_size=1, max_size=3, unique=True
        ),
    )
    @settings(max_examples=100)
    def test_invalid_signature_transitions_detected(
        self,
        states: list[str],
        invalid_transitions: list[str],
    ) -> None:
        """signature_required_transitions referencing non-existent transitions
        SHALL produce is_valid=False with appropriate error.

        **Validates: Requirements 12.3**
        """
        # Build a valid connected workflow
        transitions = [
            (states[i], states[i + 1]) for i in range(len(states) - 1)
        ]
        initial_state = states[0]
        terminal_states = [states[-1]]

        bpmn_xml = make_bpmn_xml(
            states, transitions, initial_state, terminal_states
        )

        # Build valid transition strings from the workflow
        valid_transition_strings = {
            f"{src}\u2192{tgt}" for src, tgt in transitions
        }

        # Create invalid signature_required_transitions that reference
        # non-existent transitions (using made-up state names)
        fake_sig_transitions = [
            f"{name}\u2192NonExistent" for name in invalid_transitions
        ]

        # Ensure none of the fake transitions happen to be valid
        assume(not set(fake_sig_transitions) & valid_transition_strings)

        result = validate_bpmn_workflow(
            bpmn_xml, signature_required_transitions=fake_sig_transitions
        )

        assert result.is_valid is False, (
            f"Expected is_valid=False for invalid signature transitions "
            f"{fake_sig_transitions}, got is_valid=True"
        )
        # Should have error about invalid transition reference
        has_transition_error = any(
            "signature_required_transitions" in err
            or "invalid transition" in err.lower()
            for err in result.errors
        )
        assert has_transition_error, (
            f"Expected error about invalid transition reference, "
            f"got: {result.errors}"
        )
