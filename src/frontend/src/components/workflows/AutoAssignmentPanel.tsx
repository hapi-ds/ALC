import { useState, useCallback } from 'react';
import { useWorkflowStore } from '@/stores/workflowStore';

/**
 * AutoAssignmentPanel component for the Workflow Editor.
 *
 * Provides a JSON editor field for auto-assignment rules configuration.
 * Displays a descriptive label about Phase 5.1 Agent Registry integration.
 * Validates JSON syntax before allowing save; shows error for malformed JSON.
 * Allows empty/null value.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
 */
export function AutoAssignmentPanel() {
  const autoAssignmentConfig = useWorkflowStore((s) => s.autoAssignmentConfig);
  const setAutoAssignmentConfig = useWorkflowStore((s) => s.setAutoAssignmentConfig);

  const [jsonText, setJsonText] = useState<string>(
    autoAssignmentConfig ? JSON.stringify(autoAssignmentConfig, null, 2) : ''
  );
  const [jsonError, setJsonError] = useState<string | null>(null);

  const handleChange = useCallback((value: string) => {
    setJsonText(value);
    // Clear error while typing
    if (jsonError) {
      setJsonError(null);
    }
  }, [jsonError]);

  const handleBlur = useCallback(() => {
    const trimmed = jsonText.trim();

    // Allow empty/null value
    if (!trimmed) {
      setJsonError(null);
      setAutoAssignmentConfig(null);
      return;
    }

    // Validate JSON syntax
    try {
      const parsed = JSON.parse(trimmed);
      setJsonError(null);
      setAutoAssignmentConfig(parsed);
    } catch (e) {
      const message = e instanceof SyntaxError ? e.message : 'Invalid JSON syntax';
      setJsonError(message);
    }
  }, [jsonText, setAutoAssignmentConfig]);

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4">
      <h4 className="text-sm font-semibold text-gray-700">
        Auto-Assignment Configuration
      </h4>

      {/* Phase 5.1 integration notice */}
      <p className="text-xs text-gray-500 bg-gray-50 rounded-md px-3 py-2 border border-gray-100">
        Auto-assignment rules will be activated when the Agent Registry (Phase 5.1) is
        integrated. Configure rules now to prepare for automated reviewer and approver
        suggestions based on document content.
      </p>

      {/* JSON editor */}
      <div className="flex flex-col gap-1">
        <label htmlFor="auto-assignment-json" className="text-xs font-medium text-gray-600">
          Assignment Rules (JSON)
        </label>
        <textarea
          id="auto-assignment-json"
          value={jsonText}
          onChange={(e) => handleChange(e.target.value)}
          onBlur={handleBlur}
          rows={6}
          placeholder='{\n  "rules": []\n}'
          className={`rounded-md border px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y ${
            jsonError ? 'border-red-300 bg-red-50' : 'border-gray-300'
          }`}
          aria-invalid={!!jsonError}
          aria-describedby={jsonError ? 'json-error' : undefined}
        />
        {jsonError && (
          <p id="json-error" className="text-xs text-red-600" role="alert">
            Invalid JSON: {jsonError}
          </p>
        )}
        {!jsonError && (
          <p className="text-xs text-gray-400">
            Leave empty for no auto-assignment rules.
          </p>
        )}
      </div>
    </div>
  );
}
