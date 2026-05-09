import { useState, useCallback } from 'react';
import { useWorkflowStore, type RiskLevel } from '@/stores/workflowStore';

/**
 * MetadataForm component for the Workflow Editor.
 *
 * Displays fields for workflow name, document tag, risk level, and active status.
 * Pre-populates from store's currentWorkflow in edit mode.
 * Validates required fields on blur with inline error messages.
 * Connects to workflowStore actions (setWorkflowName, setDocumentTag, setRiskLevel).
 *
 * Requirements: 3.1, 3.2, 3.6, 3.7
 */

interface MetadataFormProps {
  /** Whether the form is in edit mode (pre-populates from currentWorkflow) */
  mode: 'create' | 'edit';
}

const RISK_LEVELS: { value: RiskLevel; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
];

export function MetadataForm({ mode }: MetadataFormProps) {
  const workflowName = useWorkflowStore((s) => s.workflowName);
  const documentTag = useWorkflowStore((s) => s.documentTag);
  const riskLevel = useWorkflowStore((s) => s.riskLevel);
  const currentWorkflow = useWorkflowStore((s) => s.currentWorkflow);
  const setWorkflowName = useWorkflowStore((s) => s.setWorkflowName);
  const setDocumentTag = useWorkflowStore((s) => s.setDocumentTag);
  const setRiskLevel = useWorkflowStore((s) => s.setRiskLevel);

  const [errors, setErrors] = useState<{ name?: string; documentTag?: string }>({});

  const isActive = mode === 'edit' ? currentWorkflow?.is_active ?? true : true;

  const validateName = useCallback((value: string) => {
    if (!value.trim()) {
      setErrors((prev) => ({ ...prev, name: 'Workflow name is required' }));
    } else if (value.length > 200) {
      setErrors((prev) => ({ ...prev, name: 'Workflow name must be 200 characters or less' }));
    } else {
      setErrors((prev) => ({ ...prev, name: undefined }));
    }
  }, []);

  const validateDocumentTag = useCallback((value: string) => {
    if (!value.trim()) {
      setErrors((prev) => ({ ...prev, documentTag: 'Document tag is required' }));
    } else if (value.length > 100) {
      setErrors((prev) => ({ ...prev, documentTag: 'Document tag must be 100 characters or less' }));
    } else {
      setErrors((prev) => ({ ...prev, documentTag: undefined }));
    }
  }, []);

  return (
    <div className="flex flex-col gap-4 p-4 rounded-lg border border-gray-200 bg-white">
      <h3 className="text-sm font-semibold text-gray-700">Workflow Metadata</h3>

      {/* Workflow Name */}
      <div className="flex flex-col gap-1">
        <label htmlFor="workflow-name" className="text-sm font-medium text-gray-700">
          Workflow Name <span className="text-red-500">*</span>
        </label>
        <input
          id="workflow-name"
          type="text"
          value={workflowName}
          onChange={(e) => setWorkflowName(e.target.value)}
          onBlur={(e) => validateName(e.target.value)}
          maxLength={200}
          placeholder="Enter workflow name"
          className={`rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.name ? 'border-red-300 bg-red-50' : 'border-gray-300'
          }`}
          aria-required="true"
          aria-invalid={!!errors.name}
          aria-describedby={errors.name ? 'workflow-name-error' : undefined}
        />
        {errors.name && (
          <p id="workflow-name-error" className="text-xs text-red-600" role="alert">
            {errors.name}
          </p>
        )}
      </div>

      {/* Document Tag */}
      <div className="flex flex-col gap-1">
        <label htmlFor="document-tag" className="text-sm font-medium text-gray-700">
          Document Tag <span className="text-red-500">*</span>
        </label>
        <input
          id="document-tag"
          type="text"
          value={documentTag}
          onChange={(e) => setDocumentTag(e.target.value)}
          onBlur={(e) => validateDocumentTag(e.target.value)}
          maxLength={100}
          placeholder="Enter document tag"
          className={`rounded-md border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            errors.documentTag ? 'border-red-300 bg-red-50' : 'border-gray-300'
          }`}
          aria-required="true"
          aria-invalid={!!errors.documentTag}
          aria-describedby={errors.documentTag ? 'document-tag-error' : undefined}
        />
        {errors.documentTag && (
          <p id="document-tag-error" className="text-xs text-red-600" role="alert">
            {errors.documentTag}
          </p>
        )}
      </div>

      {/* Risk Level */}
      <div className="flex flex-col gap-1">
        <label htmlFor="risk-level" className="text-sm font-medium text-gray-700">
          Risk Level
        </label>
        <select
          id="risk-level"
          value={riskLevel}
          onChange={(e) => setRiskLevel(e.target.value as RiskLevel)}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {RISK_LEVELS.map((level) => (
            <option key={level.value} value={level.value}>
              {level.label}
            </option>
          ))}
        </select>
      </div>

      {/* Active Status Toggle */}
      <div className="flex items-center gap-3">
        <label htmlFor="active-status" className="text-sm font-medium text-gray-700">
          Active Status
        </label>
        <div className="flex items-center gap-2">
          <div
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
              isActive ? 'bg-blue-600' : 'bg-gray-300'
            }`}
            role="presentation"
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                isActive ? 'translate-x-4.5' : 'translate-x-0.5'
              }`}
            />
          </div>
          <span className="text-xs text-gray-500">
            {isActive ? 'Active' : 'Inactive'}
          </span>
        </div>
      </div>
    </div>
  );
}
