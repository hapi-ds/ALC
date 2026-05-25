/**
 * TemplateRegistrationPanel
 *
 * Form component for registering a .docx file as a Master Template.
 * Collects document_id, document_version_id, template_name, and
 * document_type_target, then dispatches registration via the store.
 *
 * Requirements: 1.1
 */

import { useState, useCallback } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useDocumentGeneratorStore } from "@/stores/documentGeneratorStore";

const DOCUMENT_TYPE_OPTIONS = ["URS", "SOP", "Protocol", "Report", "MVP"] as const;

export function TemplateRegistrationPanel() {
  const { isRegistering, error, registerTemplate, fetchTemplates } =
    useDocumentGeneratorStore();

  const [documentId, setDocumentId] = useState("");
  const [documentVersionId, setDocumentVersionId] = useState("");
  const [templateName, setTemplateName] = useState("");
  const [documentTypeTarget, setDocumentTypeTarget] = useState<string>(
    DOCUMENT_TYPE_OPTIONS[0],
  );
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const isFormValid =
    documentId.trim() !== "" &&
    documentVersionId.trim() !== "" &&
    templateName.trim() !== "" &&
    documentTypeTarget.trim() !== "";

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      setSuccessMessage(null);

      const jobId = await registerTemplate(
        {
          document_id: Number(documentId),
          document_version_id: Number(documentVersionId),
          template_name: templateName.trim(),
          document_type_target: documentTypeTarget,
        },
        "Register new document template for AI generation",
      );

      if (jobId) {
        setSuccessMessage(`Template registration started (Job: ${jobId})`);
        setDocumentId("");
        setDocumentVersionId("");
        setTemplateName("");
        setDocumentTypeTarget(DOCUMENT_TYPE_OPTIONS[0]);
        // Refresh the template list
        await fetchTemplates();
      }
    },
    [
      documentId,
      documentVersionId,
      templateName,
      documentTypeTarget,
      registerTemplate,
      fetchTemplates,
    ],
  );

  return (
    <section aria-labelledby="template-registration-heading" className="rounded-lg border p-6">
      <h3 id="template-registration-heading" className="text-lg font-semibold mb-4">
        Register New Template
      </h3>
      <p className="text-sm text-muted-foreground mb-4">
        Designate an existing .docx file as a Master Template for AI document generation.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4" aria-label="Template registration form">
        {/* Document ID */}
        <div className="space-y-1">
          <label htmlFor="reg-document-id" className="text-sm font-medium">
            Document ID
          </label>
          <input
            id="reg-document-id"
            type="number"
            min="1"
            value={documentId}
            onChange={(e) => setDocumentId(e.target.value)}
            placeholder="Enter document ID"
            required
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            aria-describedby="reg-document-id-desc"
          />
          <p id="reg-document-id-desc" className="text-xs text-muted-foreground">
            The ID of the document containing the .docx template file.
          </p>
        </div>

        {/* Document Version ID */}
        <div className="space-y-1">
          <label htmlFor="reg-version-id" className="text-sm font-medium">
            Document Version ID
          </label>
          <input
            id="reg-version-id"
            type="number"
            min="1"
            value={documentVersionId}
            onChange={(e) => setDocumentVersionId(e.target.value)}
            placeholder="Enter document version ID"
            required
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            aria-describedby="reg-version-id-desc"
          />
          <p id="reg-version-id-desc" className="text-xs text-muted-foreground">
            The specific version of the document to use as a template.
          </p>
        </div>

        {/* Template Name */}
        <div className="space-y-1">
          <label htmlFor="reg-template-name" className="text-sm font-medium">
            Template Name
          </label>
          <input
            id="reg-template-name"
            type="text"
            maxLength={500}
            value={templateName}
            onChange={(e) => setTemplateName(e.target.value)}
            placeholder="e.g., URS Master Template v2"
            required
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            aria-describedby="reg-template-name-desc"
          />
          <p id="reg-template-name-desc" className="text-xs text-muted-foreground">
            A descriptive name for this template (max 500 characters).
          </p>
        </div>

        {/* Document Type Target */}
        <div className="space-y-1">
          <label htmlFor="reg-doc-type" className="text-sm font-medium">
            Document Type Target
          </label>
          <select
            id="reg-doc-type"
            value={documentTypeTarget}
            onChange={(e) => setDocumentTypeTarget(e.target.value)}
            required
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            aria-describedby="reg-doc-type-desc"
          >
            {DOCUMENT_TYPE_OPTIONS.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
          <p id="reg-doc-type-desc" className="text-xs text-muted-foreground">
            The type of regulatory document this template produces.
          </p>
        </div>

        {/* Error display */}
        {error && (
          <div role="alert" className="text-sm text-destructive bg-destructive/10 rounded-md p-3">
            {error}
          </div>
        )}

        {/* Success display */}
        {successMessage && (
          <div role="status" className="text-sm text-green-700 bg-green-50 rounded-md p-3">
            {successMessage}
          </div>
        )}

        {/* Submit button */}
        <Button
          type="submit"
          disabled={!isFormValid || isRegistering}
          className="w-full"
        >
          {isRegistering ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Registering...
            </>
          ) : (
            "Register Template"
          )}
        </Button>
      </form>
    </section>
  );
}
