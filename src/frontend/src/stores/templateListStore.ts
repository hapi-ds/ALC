import { create } from "zustand";
import type {
  TemplateResponse,
  TemplateVersionResponse,
} from "../types/template";
import { apiClient } from "../lib/apiClient";
import { getAccessToken } from "../lib/tokenStorage";
import { useAuthStore } from "./authStore";

/** Version summary info for a template in the list view */
export interface TemplateVersionSummary {
  activeVersionNumber: number | null;
  totalVersionCount: number;
  activeVersionCreatedAt: string | null;
  activeVersionFieldCount: number;
  hasReadOnlyVersion: boolean;
}

interface TemplateListState {
  templates: TemplateResponse[];
  versionSummaries: Record<string, TemplateVersionSummary>;
  isLoading: boolean;
  error: string | null;
  downloadingUuid: string | null;
  downloadError: string | null;

  fetchTemplates: () => Promise<void>;
  downloadPdf: (documentUuid: string) => Promise<void>;
}

/** Timeout duration for template list fetch (ms) */
const FETCH_TIMEOUT_MS = 30_000;

export const useTemplateListStore = create<TemplateListState>((set) => ({
  templates: [],
  versionSummaries: {},
  isLoading: false,
  error: null,
  downloadingUuid: null,
  downloadError: null,

  fetchTemplates: async () => {
    set({ isLoading: true, error: null });

    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    try {
      const response = await Promise.race([
        apiClient.get<TemplateResponse[]>("/api/templates"),
        new Promise<never>((_, reject) => {
          timeoutId = setTimeout(() => {
            reject(new DOMException("The operation timed out.", "AbortError"));
          }, FETCH_TIMEOUT_MS);
        }),
      ]);

      set({ templates: response, isLoading: false });

      // Fetch version summaries for each template in parallel
      const summaries: Record<string, TemplateVersionSummary> = {};
      const versionFetches = response.map(async (template) => {
        try {
          const versions = await apiClient.get<TemplateVersionResponse[]>(
            `/api/templates/${template.document_uuid}/versions`
          );
          const activeVersion = versions.find((v) => v.is_active);
          const fieldCount = activeVersion
            ? activeVersion.fields.filter((f) => f.element_type === "field")
                .length
            : template.fields.length;

          summaries[template.document_uuid] = {
            activeVersionNumber: activeVersion?.version_number ?? null,
            totalVersionCount: versions.length,
            activeVersionCreatedAt: activeVersion?.created_at ?? null,
            activeVersionFieldCount: fieldCount,
            hasReadOnlyVersion: versions.some((v) => v.status === "ReadOnly"),
          };
        } catch {
          // If version fetch fails, use fallback data from template
          summaries[template.document_uuid] = {
            activeVersionNumber: null,
            totalVersionCount: 0,
            activeVersionCreatedAt: null,
            activeVersionFieldCount: template.fields.length,
            hasReadOnlyVersion: template.status === "ReadOnly",
          };
        }
      });

      await Promise.all(versionFetches);
      set({ versionSummaries: summaries });
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === "AbortError") {
        set({ error: "Request timed out", isLoading: false });
      } else {
        set({ error: "Failed to load templates", isLoading: false });
      }
    } finally {
      if (timeoutId !== undefined) {
        clearTimeout(timeoutId);
      }
    }
  },

  downloadPdf: async (documentUuid: string) => {
    set({ downloadingUuid: documentUuid, downloadError: null });

    try {
      // Build headers manually since apiClient doesn't support blob responses.
      // POST /api/templates/{uuid}/download-pdf requires X-Change-Reason header.
      const headers: Record<string, string> = {
        "X-Change-Reason": "PDF downloaded for offline data collection",
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

      const response = await fetch(
        `/api/templates/${documentUuid}/download-pdf`,
        {
          method: "POST",
          headers,
          credentials: "include",
        }
      );

      if (!response.ok) {
        if (response.status === 404) {
          set({ downloadError: "Template not found", downloadingUuid: null });
          return;
        }
        if (response.status === 400) {
          set({ downloadError: "Not downloadable", downloadingUuid: null });
          return;
        }
        set({ downloadError: "Download failed", downloadingUuid: null });
        return;
      }

      // Extract filename from Content-Disposition header
      const contentDisposition = response.headers.get("Content-Disposition");
      let filename = `template_${documentUuid}.pdf`;
      if (contentDisposition) {
        const match = contentDisposition.match(/filename="?([^";\n]+)"?/);
        if (match?.[1]) {
          filename = match[1];
        }
      }

      // Handle blob response and trigger download
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      URL.revokeObjectURL(url);
      set({ downloadingUuid: null });
    } catch {
      set({ downloadError: "Download failed", downloadingUuid: null });
    }
  },
}));
