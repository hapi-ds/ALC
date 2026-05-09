import { useEffect, useCallback, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Save,
  CheckCircle2,
  Trash2,
  Loader2,
  AlertCircle,
  ArrowLeft,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useWorkflowStore } from '@/stores/workflowStore';
import { MetadataForm } from '@/components/workflows/MetadataForm';
import { BpmnEditor } from '@/components/workflows/BpmnEditor';
import { TransitionConfigPanel } from '@/components/workflows/TransitionConfigPanel';
import { RiskConfigPanel } from '@/components/workflows/RiskConfigPanel';
import { AutoAssignmentPanel } from '@/components/workflows/AutoAssignmentPanel';
import { VersionHistoryPanel } from '@/components/workflows/VersionHistoryPanel';

/**
 * WorkflowEditorPage component.
 *
 * Composes the BPMN editor, metadata form, and configuration panels into a
 * full workflow editor page. Supports both create and edit modes, with
 * unsaved changes protection, save/validate/delete actions, and error handling.
 *
 * All API calls are delegated to the workflowStore which uses apiClient with
 * proper X-Change-Reason headers and /api/workflows endpoints.
 *
 * Requirements: 5.1–5.7, 6.1–6.6, 7.1–7.8
 */

interface WorkflowEditorPageProps {
  /** Editor mode — can also be derived from route params */
  mode?: 'create' | 'edit';
}

export function WorkflowEditorPage({ mode: modeProp }: WorkflowEditorPageProps) {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();

  // Derive mode from prop or route params
  const mode = modeProp ?? (workflowId ? 'edit' : 'create');
  const numericWorkflowId = workflowId ? parseInt(workflowId, 10) : null;

  // Store state
  const currentWorkflow = useWorkflowStore((s) => s.currentWorkflow);
  const bpmnXml = useWorkflowStore((s) => s.bpmnXml);
  const workflowName = useWorkflowStore((s) => s.workflowName);
  const isDirty = useWorkflowStore((s) => s.isDirty);
  const isSaving = useWorkflowStore((s) => s.isSaving);
  const isDeleting = useWorkflowStore((s) => s.isDeleting);
  const isValidating = useWorkflowStore((s) => s.isValidating);
  const isLoadingDetail = useWorkflowStore((s) => s.isLoadingDetail);
  const saveError = useWorkflowStore((s) => s.saveError);
  const deleteError = useWorkflowStore((s) => s.deleteError);
  const detailError = useWorkflowStore((s) => s.detailError);
  const validationResult = useWorkflowStore((s) => s.validationResult);
  const validateError = useWorkflowStore((s) => s.validateError);

  // Store actions
  const fetchWorkflowDetail = useWorkflowStore((s) => s.fetchWorkflowDetail);
  const createWorkflow = useWorkflowStore((s) => s.createWorkflow);
  const updateWorkflow = useWorkflowStore((s) => s.updateWorkflow);
  const deleteWorkflow = useWorkflowStore((s) => s.deleteWorkflow);
  const validateWorkflow = useWorkflowStore((s) => s.validateWorkflow);
  const resetEditor = useWorkflowStore((s) => s.resetEditor);
  const setBpmnXml = useWorkflowStore((s) => s.setBpmnXml);

  // Local state
  const [transitions, setTransitions] = useState<string[]>([]);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [notification, setNotification] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);

  // --- Initialization ---
  useEffect(() => {
    if (mode === 'edit' && numericWorkflowId) {
      fetchWorkflowDetail(numericWorkflowId);
    } else if (mode === 'create') {
      resetEditor();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, numericWorkflowId]);

  // --- Unsaved changes: beforeunload ---
  useEffect(() => {
    if (!isDirty) return;

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [isDirty]);

  // --- Auto-dismiss notifications ---
  useEffect(() => {
    if (notification) {
      const timer = setTimeout(() => setNotification(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [notification]);

  // --- Handlers ---

  const handleXmlChange = useCallback(
    (xml: string) => {
      setBpmnXml(xml);
    },
    [setBpmnXml]
  );

  const handleTransitionsChange = useCallback((newTransitions: string[]) => {
    setTransitions(newTransitions);
  }, []);

  const handleSave = useCallback(async () => {
    if (mode === 'create') {
      const result = await createWorkflow();
      if (result) {
        setNotification({ type: 'success', message: 'Workflow created successfully.' });
        // Transition to edit mode
        navigate(`/workflows/${result.id}/edit`, { replace: true });
      }
    } else if (numericWorkflowId) {
      const result = await updateWorkflow(numericWorkflowId);
      if (result) {
        setNotification({ type: 'success', message: 'Workflow saved successfully.' });
      }
    }
  }, [mode, numericWorkflowId, createWorkflow, updateWorkflow, navigate]);

  const handleValidate = useCallback(async () => {
    await validateWorkflow();
  }, [validateWorkflow]);

  const handleDelete = useCallback(async () => {
    if (!numericWorkflowId) return;
    const success = await deleteWorkflow(numericWorkflowId);
    if (success) {
      setShowDeleteDialog(false);
      setNotification({ type: 'success', message: 'Workflow deleted.' });
      navigate('/workflows');
    }
  }, [numericWorkflowId, deleteWorkflow, navigate]);

  const handleBack = useCallback(() => {
    navigate('/workflows');
  }, [navigate]);

  // --- Derive error messages for display ---
  const displayError = saveError || deleteError;

  // Determine if the error is a specific HTTP status
  const is409Error = displayError?.toLowerCase().includes('in use') ||
    displayError?.toLowerCase().includes('cannot be deleted');
  const is404Error = displayError?.toLowerCase().includes('not found');

  // --- Loading state for edit mode ---
  if (mode === 'edit' && isLoadingDetail) {
    return (
      <div className="flex items-center justify-center min-h-[400px]" role="status">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" aria-hidden="true" />
        <span className="ml-3 text-gray-600">Loading workflow...</span>
      </div>
    );
  }

  // --- 404 error state ---
  if (mode === 'edit' && detailError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <AlertCircle className="h-12 w-12 text-red-400" aria-hidden="true" />
        <p className="text-lg text-gray-700">{detailError}</p>
        <Button variant="outline" onClick={handleBack}>
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back to Workflows
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={handleBack} aria-label="Back to workflows">
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <div>
            <h1 className="text-xl font-bold text-gray-900">
              {mode === 'create' ? 'Create Workflow' : `Edit: ${workflowName || 'Workflow'}`}
            </h1>
            {mode === 'edit' && currentWorkflow && (
              <p className="text-xs text-gray-500">
                Version {currentWorkflow.current_version_number}
                {isDirty && <span className="ml-2 text-amber-600">• Unsaved changes</span>}
              </p>
            )}
            {mode === 'create' && isDirty && (
              <p className="text-xs text-amber-600">Unsaved changes</p>
            )}
          </div>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={handleValidate}
            disabled={isValidating || isSaving}
          >
            {isValidating ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            )}
            Validate
          </Button>

          <Button
            onClick={handleSave}
            disabled={isSaving || isDeleting}
            className="bg-blue-600 text-white hover:bg-blue-700"
          >
            {isSaving ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Save className="h-4 w-4" aria-hidden="true" />
            )}
            Save
          </Button>

          {mode === 'edit' && (
            <Button
              variant="destructive"
              onClick={() => setShowDeleteDialog(true)}
              disabled={isDeleting || isSaving}
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              )}
              Delete
            </Button>
          )}
        </div>
      </div>

      {/* Notification banner */}
      {notification && (
        <div
          className={`flex items-center gap-2 rounded-md px-4 py-2 text-sm ${
            notification.type === 'success'
              ? 'bg-green-50 border border-green-200 text-green-800'
              : 'bg-red-50 border border-red-200 text-red-800'
          }`}
          role="alert"
        >
          {notification.type === 'success' ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <XCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          {notification.message}
        </div>
      )}

      {/* Error display */}
      {displayError && (
        <div
          className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800"
          role="alert"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            {is409Error && 'This workflow cannot be deleted because documents are currently using it.'}
            {is404Error && 'Workflow not found. It may have been deleted.'}
            {!is409Error && !is404Error && displayError}
          </span>
        </div>
      )}

      {/* Validation results */}
      {validationResult && (
        <div
          className={`rounded-md border px-4 py-3 text-sm ${
            validationResult.is_valid
              ? 'border-green-200 bg-green-50 text-green-800'
              : 'border-red-200 bg-red-50 text-red-800'
          }`}
          role="alert"
        >
          {validationResult.is_valid ? (
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span>Workflow is valid.</span>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 font-medium">
                <XCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span>Validation errors:</span>
              </div>
              <ul className="ml-6 list-disc space-y-0.5">
                {validationResult.errors.map((error, idx) => (
                  <li key={idx}>{error}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Validate error (network failure) */}
      {validateError && !validationResult && (
        <div
          className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800"
          role="alert"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>Validation could not be completed: {validateError}</span>
        </div>
      )}

      {/* Main content: BPMN editor + sidebar */}
      <div className="flex flex-1 gap-4 min-h-0">
        {/* BPMN Editor (takes most space) */}
        <div className="flex-1 rounded-lg border border-gray-200 bg-white overflow-hidden min-h-[500px]">
          <BpmnEditor
            initialXml={bpmnXml}
            onXmlChange={handleXmlChange}
            onTransitionsChange={handleTransitionsChange}
            readOnly={false}
          />
        </div>

        {/* Sidebar panels */}
        <div className="w-80 flex-shrink-0 flex flex-col gap-4 overflow-y-auto">
          <MetadataForm mode={mode} />
          <TransitionConfigPanel transitions={transitions} />
          <RiskConfigPanel />
          <AutoAssignmentPanel />
          {mode === 'edit' && numericWorkflowId && (
            <VersionHistoryPanel workflowId={numericWorkflowId} />
          )}
        </div>
      </div>

      {/* Delete confirmation dialog */}
      {showDeleteDialog && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
        >
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
            <h2 id="delete-dialog-title" className="text-lg font-semibold text-gray-900">
              Delete Workflow
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              Are you sure you want to delete{' '}
              <span className="font-medium">{workflowName || 'this workflow'}</span>?
              This action is permanent and cannot be undone.
            </p>

            {deleteError && (
              <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {deleteError}
              </div>
            )}

            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setShowDeleteDialog(false)}
                disabled={isDeleting}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                ) : (
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                )}
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
