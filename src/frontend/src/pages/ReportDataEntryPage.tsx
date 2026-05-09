import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReportStore } from "@/stores/reportStore";
import { TemplateSelector } from "@/components/reports/TemplateSelector";
import { DynamicForm } from "@/components/reports/DynamicForm";
import { PdfUploadSection } from "@/components/reports/PdfUploadSection";
import type { TemplateResponse } from "@/types/template";
import type { FieldValueEntry } from "@/types/report";
import { apiClient } from "@/lib/apiClient";

/**
 * Report data entry page with template selection, dynamic form,
 * PDF upload, and blank PDF download.
 *
 * API endpoints used (verified against backend router):
 * - GET /api/templates (via TemplateSelector -> templateListStore)
 * - GET /api/templates/{document_uuid} (via apiClient.get)
 * - POST /api/reports (via reportStore.submitReport, includes X-Change-Reason)
 * - POST /api/reports/upload-pdf (via reportStore.uploadPdf, includes X-Change-Reason)
 * - POST /api/templates/{uuid}/download-pdf (via reportStore.downloadBlankPdf, includes X-Change-Reason)
 */
export function ReportDataEntryPage() {
  const { documentUuid } = useParams<{ documentUuid: string }>();
  const navigate = useNavigate();

  const {
    isSubmitting,
    submitError,
    isUploading,
    uploadError,
    isDownloadingPdf,
    submitReport,
    uploadPdf,
    downloadBlankPdf,
  } = useReportStore();

  const [selectedTemplate, setSelectedTemplate] = useState<TemplateResponse | null>(null);
  const [templateDetail, setTemplateDetail] = useState<TemplateResponse | null>(null);
  const [isLoadingTemplate, setIsLoadingTemplate] = useState(false);
  const [templateError, setTemplateError] = useState<string | null>(null);
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({});

  const handleTemplateSelect = useCallback(async (template: TemplateResponse) => {
    setSelectedTemplate(template);
    setIsLoadingTemplate(true);
    setTemplateError(null);
    setServerErrors({});

    try {
      const detail = await apiClient.get<TemplateResponse>(
        `/api/templates/${template.document_uuid}`
      );
      setTemplateDetail(detail);
    } catch {
      setTemplateError("Failed to load template details. Please try again.");
      setSelectedTemplate(null);
    } finally {
      setIsLoadingTemplate(false);
    }
  }, []);

  const handleSubmit = useCallback(
    async (fieldValues: FieldValueEntry[]) => {
      if (!selectedTemplate) return;
      setServerErrors({});

      try {
        const report = await submitReport(
          selectedTemplate.document_uuid,
          fieldValues
        );
        navigate(`/reports/${report.id}`);
      } catch (err: unknown) {
        if (err && typeof err === "object" && "body" in err) {
          const body = (err as { body: unknown }).body;
          if (typeof body === "object" && body && "validation_errors" in body) {
            const valErrors = (body as { validation_errors: Array<{ field_uuid: string; message: string }> }).validation_errors;
            const mapped: Record<string, string> = {};
            for (const ve of valErrors) {
              mapped[ve.field_uuid] = ve.message;
            }
            setServerErrors(mapped);
          }
        }
      }
    },
    [selectedTemplate, submitReport, navigate]
  );

  const handleUpload = useCallback(
    async (file: File) => {
      try {
        const report = await uploadPdf(file);
        navigate(`/reports/${report.id}`);
      } catch {
        // Error stored in uploadError via the store
      }
    },
    [uploadPdf, navigate]
  );

  const handleDownloadPdf = useCallback(() => {
    if (selectedTemplate) {
      downloadBlankPdf(selectedTemplate.document_uuid);
    }
  }, [selectedTemplate, downloadBlankPdf]);

  const elements = (templateDetail?.json_schema?.elements ?? []) as import("@/types/template").SerializedElement[];
  const templateFields = templateDetail?.fields ?? [];

  return (
    <div className="space-y-8 max-w-3xl">
      <h2 className="text-2xl font-bold">New Report</h2>

      {!selectedTemplate && (
        <TemplateSelector
          onSelect={handleTemplateSelect}
          preSelectedUuid={documentUuid}
        />
      )}

      {isLoadingTemplate && (
        <div className="flex items-center justify-center py-8" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" aria-hidden="true" />
          <span className="ml-2 text-sm text-muted-foreground">Loading template…</span>
        </div>
      )}

      {templateError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {templateError}
        </div>
      )}

      {templateDetail && selectedTemplate && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700">
                Template: {selectedTemplate.name}
              </p>
              <p className="text-xs text-gray-500">
                {selectedTemplate.document_uuid}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadPdf}
              disabled={isDownloadingPdf}
            >
              {isDownloadingPdf ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <Download className="h-4 w-4 mr-1" aria-hidden="true" />
              )}
              Download Blank PDF
            </Button>
          </div>

          <DynamicForm
            elements={elements}
            templateFields={templateFields}
            onSubmit={handleSubmit}
            isSubmitting={isSubmitting}
            serverErrors={serverErrors}
          />

          {submitError && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {typeof submitError === "string" ? submitError : "Submission failed"}
            </div>
          )}

          <PdfUploadSection
            onUpload={handleUpload}
            isUploading={isUploading}
            uploadError={uploadError}
          />
        </>
      )}
    </div>
  );
}
