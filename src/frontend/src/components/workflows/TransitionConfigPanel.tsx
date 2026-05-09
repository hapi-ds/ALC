/**
 * TransitionConfigPanel component
 *
 * Displays a list of transitions extracted from the BPMN diagram, each with
 * checkboxes for "Signature Required" and "Training Trigger". Updates the
 * workflow store's signatureRequiredTransitions and trainingTriggerTransitions
 * arrays when toggled.
 *
 * Requirements: 3.3, 3.4, 3.5
 */

import { useWorkflowStore } from "@/stores/workflowStore";

// ---------------------------------------------------------------------------
// Pure utility function for toggling transitions in/out of an array
// ---------------------------------------------------------------------------

/**
 * Toggles a transition in or out of an array.
 * - If the transition is not in the array, adds it.
 * - If the transition is already in the array, removes it.
 * - All other elements remain unchanged in their original order.
 *
 * @param transitions - Current array of selected transitions
 * @param transition - The transition to toggle
 * @returns A new array with the transition toggled
 */
export function toggleTransition(
  transitions: string[],
  transition: string
): string[] {
  if (transitions.includes(transition)) {
    return transitions.filter((t) => t !== transition);
  }
  return [...transitions, transition];
}

// ---------------------------------------------------------------------------
// Component Props
// ---------------------------------------------------------------------------

export interface TransitionConfigPanelProps {
  /** List of transitions extracted from the current BPMN diagram */
  transitions: string[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Panel displaying all transitions from the BPMN diagram with checkboxes
 * for marking each as requiring a PAdES signature or triggering training.
 */
export function TransitionConfigPanel({
  transitions,
}: TransitionConfigPanelProps) {
  const signatureRequiredTransitions = useWorkflowStore(
    (s) => s.signatureRequiredTransitions
  );
  const trainingTriggerTransitions = useWorkflowStore(
    (s) => s.trainingTriggerTransitions
  );
  const setSignatureTransitions = useWorkflowStore(
    (s) => s.setSignatureTransitions
  );
  const setTrainingTransitions = useWorkflowStore(
    (s) => s.setTrainingTransitions
  );

  const handleSignatureToggle = (transition: string) => {
    const updated = toggleTransition(
      signatureRequiredTransitions,
      transition
    );
    setSignatureTransitions(updated);
  };

  const handleTrainingToggle = (transition: string) => {
    const updated = toggleTransition(
      trainingTriggerTransitions,
      transition
    );
    setTrainingTransitions(updated);
  };

  if (transitions.length === 0) {
    return (
      <div className="rounded-md border border-gray-200 p-4">
        <h3 className="text-sm font-medium text-gray-700 mb-2">
          Transition Configuration
        </h3>
        <p className="text-sm text-gray-500">
          No transitions detected. Add tasks and connect them with sequence
          flows in the BPMN editor to configure transition hooks.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-gray-200 p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-3">
        Transition Configuration
      </h3>

      <div className="space-y-2">
        {/* Header row */}
        <div className="grid grid-cols-[1fr_auto_auto] gap-2 text-xs font-medium text-gray-500 pb-1 border-b border-gray-100">
          <span>Transition</span>
          <span className="w-24 text-center">Signature</span>
          <span className="w-24 text-center">Training</span>
        </div>

        {/* Transition rows */}
        {transitions.map((transition) => (
          <div
            key={transition}
            className="grid grid-cols-[1fr_auto_auto] gap-2 items-center py-1"
          >
            <span
              className="text-sm text-gray-800 truncate"
              title={transition}
            >
              {transition}
            </span>

            <label className="w-24 flex justify-center">
              <input
                type="checkbox"
                checked={signatureRequiredTransitions.includes(transition)}
                onChange={() => handleSignatureToggle(transition)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                aria-label={`Signature required for ${transition}`}
              />
            </label>

            <label className="w-24 flex justify-center">
              <input
                type="checkbox"
                checked={trainingTriggerTransitions.includes(transition)}
                onChange={() => handleTrainingToggle(transition)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                aria-label={`Training trigger for ${transition}`}
              />
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}
