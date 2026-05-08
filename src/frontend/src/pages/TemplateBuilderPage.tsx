import { useEffect, useCallback, useState, useContext } from "react";
import { UNSAFE_NavigationContext as NavigationContext, useLocation } from "react-router-dom";
import { TemplateBuilder } from "../components/templates/TemplateBuilder";
import { UnsavedChangesDialog } from "../components/templates/UnsavedChangesDialog";
import { useTemplateBuilderStore } from "../stores/templateBuilderStore";
import type { TemplateVersionResponse } from "../types/template";

/**
 * Route-level page component for the template builder (/templates/new).
 * Wraps TemplateBuilder with navigation guards:
 * - Browser beforeunload prompt when isDirty is true
 * - In-app navigation blocking via history.block with UnsavedChangesDialog
 * - Pre-populates builder from version state when creating a new version
 */
export function TemplateBuilderPage() {
  const isDirty = useTemplateBuilderStore((s) => s.isDirty);
  const loadVersionIntoCanvas = useTemplateBuilderStore((s) => s.loadVersionIntoCanvas);
  const setTemplateName = useTemplateBuilderStore((s) => s.setTemplateName);
  const setVersionMode = useTemplateBuilderStore((s) => s.setVersionMode);
  const resetBuilder = useTemplateBuilderStore((s) => s.resetBuilder);
  const markClean = useTemplateBuilderStore((s) => s.markClean);
  const versionModeUuid = useTemplateBuilderStore((s) => s.versionModeUuid);
  const [showDialog, setShowDialog] = useState(false);
  const [pendingNavigation, setPendingNavigation] = useState<(() => void) | null>(null);

  const { navigator } = useContext(NavigationContext);
  const location = useLocation();

  // --- Load version data when navigating from "Create New Version" ---
  useEffect(() => {
    const state = location.state as {
      fromVersion?: TemplateVersionResponse;
      templateUuid?: string;
      changeReason?: string;
      templateName?: string;
    } | null;

    if (state?.fromVersion && state?.templateUuid && state?.changeReason) {
      // Reset first to clear any stale state, then load version data
      resetBuilder();
      loadVersionIntoCanvas(state.fromVersion);
      if (state.templateName) {
        setTemplateName(state.templateName);
      }
      setVersionMode(state.templateUuid, state.changeReason);
      markClean(); // Don't mark as dirty from initial load
    }
  }, []); // Run only on mount

  // --- Browser beforeunload guard ---
  const handleBeforeUnload = useCallback(
    (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
      }
    },
    [isDirty]
  );

  useEffect(() => {
    if (isDirty) {
      window.addEventListener("beforeunload", handleBeforeUnload);
      return () => {
        window.removeEventListener("beforeunload", handleBeforeUnload);
      };
    }
  }, [isDirty, handleBeforeUnload]);

  // --- In-app navigation blocking via history.block ---
  useEffect(() => {
    if (!isDirty) return;

    // react-router-dom exposes the history object on the navigator
    const history = navigator as unknown as {
      block: (blocker: (tx: { retry: () => void }) => void) => () => void;
    };

    if (typeof history.block !== "function") return;

    const unblock = history.block((tx) => {
      setShowDialog(true);
      setPendingNavigation(() => () => {
        unblock();
        tx.retry();
      });
    });

    return () => {
      unblock();
    };
  }, [isDirty, navigator]);

  const handleConfirm = () => {
    setShowDialog(false);
    if (pendingNavigation) {
      pendingNavigation();
      setPendingNavigation(null);
    }
  };

  const handleCancel = () => {
    setShowDialog(false);
    setPendingNavigation(null);
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">
        {versionModeUuid ? "Create New Version" : "Create Template"}
      </h1>
      <TemplateBuilder />

      {/* Unsaved changes dialog shown when in-app navigation is blocked */}
      <UnsavedChangesDialog
        open={showDialog}
        onConfirm={handleConfirm}
        onCancel={handleCancel}
      />
    </div>
  );
}
