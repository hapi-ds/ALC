import { AlertTriangle } from 'lucide-react';
import { useWorkflowStore } from '@/stores/workflowStore';

/**
 * RiskConfigPanel component for the Workflow Editor.
 *
 * Displays a visual warning when risk_level is "high" or "critical",
 * and a recommendation for at least two sequential review states before approval.
 *
 * Requirements: 9.2, 9.6
 */
export function RiskConfigPanel() {
  const riskLevel = useWorkflowStore((s) => s.riskLevel);

  const isHighRisk = riskLevel === 'high' || riskLevel === 'critical';

  if (!isHighRisk) {
    return null;
  }

  return (
    <div
      className="flex flex-col gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4"
      role="alert"
      aria-label="Risk level warning"
    >
      {/* Warning header */}
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" aria-hidden="true" />
        <h4 className="text-sm font-semibold text-amber-800">
          High Risk Workflow
        </h4>
      </div>

      {/* Warning message */}
      <p className="text-sm text-amber-700">
        Documents bound to this workflow will require additional review cycles due to the{' '}
        <span className="font-medium">{riskLevel}</span> risk level classification.
      </p>

      {/* Recommendation */}
      <div className="rounded-md border border-amber-200 bg-amber-100/50 px-3 py-2">
        <p className="text-xs font-medium text-amber-800">
          Recommendation
        </p>
        <p className="mt-1 text-xs text-amber-700">
          For {riskLevel}-risk workflows, include at least two sequential review states
          before an approval state to ensure adequate oversight and compliance.
        </p>
      </div>
    </div>
  );
}
