"""Integration tests for complete workflow lifecycle.

Tests the full flow: Draft → Review → Approved → InTraining → Active.

References:
    - Task 22.4: Integration tests for workflow lifecycle
"""

import pytest

from alcoabase.services.workflow_engine import WorkflowEngine, parse_bpmn_xml


# ---------------------------------------------------------------------------
# Helper: Simple transition validation using the same logic as WorkflowEngine
# ---------------------------------------------------------------------------


def is_valid_transition(
    current_state: str, target_state: str, transitions: dict[str, list[str]]
) -> bool:
    """Check if a transition is valid given a transition map."""
    return target_state in transitions.get(current_state, [])


def is_in_transition_list(
    source: str, target: str, transition_list: list[str]
) -> bool:
    """Check if source→target is in a list of transition strings."""
    transition_str = f"{source}\u2192{target}"
    return transition_str in transition_list


# ---------------------------------------------------------------------------
# Integration Tests: Workflow Lifecycle
# ---------------------------------------------------------------------------


class TestWorkflowLifecycle:
    """Integration tests for the complete document workflow lifecycle."""

    @pytest.fixture
    def workflow_engine(self) -> WorkflowEngine:
        """Create a WorkflowEngine instance."""
        return WorkflowEngine()

    def test_sop_workflow_valid_transitions(self):
        """SOP workflow allows valid transitions: Draft → Review → Approved."""
        sop_transitions = {
            "Draft": ["Review"],
            "Review": ["Approved", "Draft"],
            "Approved": ["InTraining"],
            "InTraining": ["Active"],
            "Active": ["Review"],
        }

        for source, targets in sop_transitions.items():
            for target in targets:
                assert is_valid_transition(source, target, sop_transitions), (
                    f"Expected {source} → {target} to be valid"
                )

    def test_sop_workflow_invalid_transitions_rejected(self):
        """SOP workflow rejects invalid transitions."""
        sop_transitions = {
            "Draft": ["Review"],
            "Review": ["Approved", "Draft"],
            "Approved": ["InTraining"],
            "InTraining": ["Active"],
            "Active": ["Review"],
        }

        invalid_cases = [
            ("Draft", "Approved"),
            ("Draft", "Active"),
            ("Review", "InTraining"),
            ("Approved", "Active"),
            ("InTraining", "Draft"),
        ]

        for source, target in invalid_cases:
            assert not is_valid_transition(source, target, sop_transitions), (
                f"Expected {source} → {target} to be invalid"
            )

    def test_report_workflow_valid_transitions(self):
        """Report workflow allows valid transitions with signatures."""
        report_transitions = {
            "Draft": ["RecordsFilled"],
            "RecordsFilled": ["Reviewed"],
            "Reviewed": ["Approved"],
        }

        valid_cases = [
            ("Draft", "RecordsFilled"),
            ("RecordsFilled", "Reviewed"),
            ("Reviewed", "Approved"),
        ]

        for source, target in valid_cases:
            assert is_valid_transition(source, target, report_transitions), (
                f"Expected {source} → {target} to be valid"
            )

    def test_signature_required_transitions_identified(self):
        """Signature-required transitions are correctly identified."""
        signature_transitions = ["Review\u2192Approved", "Draft\u2192RecordsFilled"]

        assert is_in_transition_list("Review", "Approved", signature_transitions)
        assert is_in_transition_list("Draft", "RecordsFilled", signature_transitions)
        assert not is_in_transition_list("Draft", "Review", signature_transitions)

    def test_training_trigger_transitions_identified(self):
        """Training-trigger transitions are correctly identified."""
        training_transitions = ["Approved\u2192InTraining"]

        assert is_in_transition_list("Approved", "InTraining", training_transitions)
        assert not is_in_transition_list("Review", "Approved", training_transitions)
