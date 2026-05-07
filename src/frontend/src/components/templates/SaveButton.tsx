import { useTemplateBuilderStore } from "../../stores/templateBuilderStore";
import { Button } from "../ui/button";

/**
 * SaveButton component for the Template Builder.
 *
 * Displays a save button that triggers template persistence to the backend.
 * Shows loading state while saving, disables when validation fails,
 * and renders contextual validation messages below the button.
 *
 * The actual API call is handled by the templateBuilderStore's saveTemplate action,
 * which sends POST /api/templates with X-Change-Reason header.
 */
export function SaveButton() {
  const isSaving = useTemplateBuilderStore((s) => s.isSaving);
  const fields = useTemplateBuilderStore((s) => s.fields);
  const templateName = useTemplateBuilderStore((s) => s.templateName);
  const saveTemplate = useTemplateBuilderStore((s) => s.saveTemplate);
  const canSave = useTemplateBuilderStore((s) => s.canSave);

  const isDisabled = !canSave() || isSaving;

  return (
    <div className="flex flex-col items-start gap-2">
      <Button
        type="button"
        onClick={saveTemplate}
        disabled={isDisabled}
        aria-busy={isSaving}
        className="min-w-[140px]"
      >
        {isSaving ? (
          <span className="inline-flex items-center gap-2">
            <svg
              className="h-4 w-4 animate-spin"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            Saving...
          </span>
        ) : (
          "Save Template"
        )}
      </Button>

      {/* Contextual validation messages */}
      <div className="flex flex-col gap-1" role="status" aria-live="polite">
        {fields.length === 0 && (
          <p className="text-sm text-destructive">
            At least one field is required
          </p>
        )}
        {templateName.trim() === "" && (
          <p className="text-sm text-destructive">
            Template name is required
          </p>
        )}
      </div>
    </div>
  );
}
