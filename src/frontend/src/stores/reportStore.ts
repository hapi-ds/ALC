import { create } from "zustand";
import { apiClient, ApiError } from "../lib/apiClient";
import { getAccessToken } from "../lib/tokenStorage";
import { useAuthStore } from "./authStore";
import type {
  ReportResponse,
  FieldValueEntry,
  ComparisonData,
} from "../types/report";

// ---------------------------------------------------------------------------
// State interface
// ---------------------------------------------------------------------------

interface ReportState {
  // List state
  reports: ReportResponse[];
  isLoadingList: boolean;
  listError: string | null;

  // Detail state
  currentReport: ReportResponse | null;
  isLoadingDetail: boolean;
  detailError: string | null;

  // Submission state
  isSubmitting: boolean;
  submitError: string | null;

  // Upload state
  isUploading: boolean;
  uploadError: string | null;

  // Comparison state
  comparisonData: ComparisonData | null;
  isLoadingComparison: boolean;
  comparisonError: string | null;

  // PDF download state
  isDownloadingPdf: boolean;
  downloadPdfError: string | null;

  // Actions
  fetchReportList: () => Promise<void>;
  fetchReportDetail: (reportId: number) => Promise<void>;
  submitReport: (documentUuid: string, fieldValues: FieldValueEntry[]) => Promise<ReportResponse>;
  uploadPdf: (file: File) => Promise<ReportResponse>;
  fetchComparisonData: (reportId: number) => Promise<void>;
  downloadBlankPdf: (documentUuid: string) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useReportStore = create<ReportState>((set, get) => ({
  // Initial state
  reports: [],
  isLoadingList: false,
  listError: null,
  currentReport: null,
  isLoadingDetail: false,
  detailError: null,
  isSubmitting: false,
  submitError: null,
  isUploading: false,
  uploadError: null,
  comparisonData: null,
  isLoadingComparison: false,
  comparisonError: null,
  isDownloadingPdf: false,
  downloadPdfError: null,

  fetchReportList: async () => {
    set({ isLoadingList: true, listError: null });
    try {
      const reports = await apiClient.get<ReportResponse[]>("/api/reports");
      set({ reports, isLoadingList: false });
    } catch (err) {
      const message = err instanceof ApiError ? err.body : "Failed to load reports";
      set({ listError: message, isLoadingList: false });
    }
  },

  fetchReportDetail: async (reportId: number) => {
    set({ isLoadingDetail: true, detailError: null });
    try {
      const report = await apiClient.get<ReportResponse>(`/api/reports/${reportId}`);
      set({ currentReport: report, isLoadingDetail: false });
    } catch (err) {
      const message = err instanceof ApiError ? err.body : "Failed to load report";
      set({ detailError: message, isLoadingDetail: false });
    }
  },

  submitReport: async (documentUuid: string, fieldValues: FieldValueEntry[]) => {
    set({ isSubmitting: true, submitError: null });
    try {
      const report = await apiClient.post<ReportResponse>("/api/reports", {
        document_uuid: documentUuid,
        field_values: fieldValues,
      }, { changeReason: "Report created via manual data entry" });
      // Prepend to list if previously fetched
      const { reports } = get();
      set({
        currentReport: report,
        isSubmitting: false,
        reports: reports.length > 0 ? [report, ...reports] : reports,
      });
      return report;
    } catch (err) {
      const message = err instanceof ApiError ? err.body : "Failed to submit report";
      set({ submitError: message, isSubmitting: false });
      throw err;
    }
  },

  uploadPdf: async (file: File) => {
    set({ isUploading: true, uploadError: null });
    try {
      const formData = new FormData();
      formData.append("file", file);
      const report = await apiClient.upload<ReportResponse>(
        "/api/reports/upload-pdf",
        formData,
        undefined,
        "Report created via PDF extraction",
      );
      // Prepend to list if previously fetched
      const { reports } = get();
      set({
        currentReport: report,
        isUploading: false,
        reports: reports.length > 0 ? [report, ...reports] : reports,
      });
      return report;
    } catch (err) {
      const message = err instanceof ApiError ? err.body : "Failed to upload PDF";
      set({ uploadError: message, isUploading: false });
      throw err;
    }
  },

  fetchComparisonData: async (reportId: number) => {
    set({ isLoadingComparison: true, comparisonError: null, comparisonData: null });
    try {
      const data = await apiClient.get<ComparisonData>(`/api/reports/${reportId}/compare`);
      set({ comparisonData: data, isLoadingComparison: false });
    } catch (err) {
      const message = err instanceof ApiError ? err.body : "Failed to load comparison";
      set({ comparisonError: message, isLoadingComparison: false, comparisonData: null });
    }
  },

  downloadBlankPdf: async (documentUuid: string) => {
    set({ isDownloadingPdf: true, downloadPdfError: null });
    try {
      // Use fetch directly for blob handling (apiClient only supports JSON responses)
      const headers: Record<string, string> = {
        "X-Change-Reason": "PDF downloaded for offline data collection from report page",
      };

      const token = getAccessToken();
      if (token) {
        headers["Authorization"] = `Bearer ${token}`;
      }

      const authState = useAuthStore.getState();
      if (authState.user?.id != null) {
        headers["X-User-Id"] = String(authState.user.id);
      }
      if (authState.activeCompanyId != null) {
        headers["X-Company-Id"] = String(authState.activeCompanyId);
      }

      const response = await fetch(`/api/templates/${documentUuid}/download-pdf`, {
        method: "POST",
        headers,
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error(`Download failed: ${response.status}`);
      }

      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition");
      const filename = disposition?.match(/filename="?(.+?)"?$/)?.[1] ?? `${documentUuid}.pdf`;

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);

      set({ isDownloadingPdf: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Download failed";
      set({ downloadPdfError: message, isDownloadingPdf: false });
    }
  },
}));
