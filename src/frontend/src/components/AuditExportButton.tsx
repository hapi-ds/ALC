/**
 * AuditExportButton component.
 *
 * Triggers PDF export of the current audit trail view. Handles both
 * synchronous (≤10k events, immediate download) and asynchronous
 * (>10k events, background processing with polling) export flows.
 *
 * Requirements: 7.7, 7.8, 7.9
 */

import { useCallback, useEffect, useRef } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuditTrailStore } from "@/stores/useAuditTrailStore";

const POLL_INTERVAL_MS = 5000;

export function AuditExportButton() {
  const totalCount = useAuditTrailStore((state) => state.totalCount);
  const exportStatus = useAuditTrailStore((state) => state.exportStatus);
  const triggerExport = useAuditTrailStore((state) => state.triggerExport);
  const checkExportStatus = useAuditTrailStore(
    (state) => state.checkExportStatus
  );

  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastNotifiedRef = useRef<string | null>(null);

  const isDisabled = totalCount === 0;
  const isExporting =
    exportStatus?.status === "pending" ||
    exportStatus?.status === "processing";

  // Handle export click
  const handleExport = useCallback(async () => {
    await triggerExport();
  }, [triggerExport]);

  // React to exportStatus changes for toast notifications
  useEffect(() => {
    if (!exportStatus) {
      lastNotifiedRef.current = null;
      return;
    }

    // Build a key to avoid duplicate notifications
    const notificationKey = `${exportStatus.job_id}:${exportStatus.status}`;
    if (lastNotifiedRef.current === notificationKey) return;
    lastNotifiedRef.current = notificationKey;

    if (
      exportStatus.status === "pending" ||
      exportStatus.status === "processing"
    ) {
      toast.info("Export started, you'll be notified when ready");
    } else if (exportStatus.status === "completed") {
      if (exportStatus.download_url) {
        const downloadUrl = exportStatus.download_url;
        toast.success("Export ready", {
          description: "Your PDF export is ready for download.",
          action: {
            label: "Download",
            onClick: () => {
              window.open(downloadUrl, "_blank");
            },
          },
        });
      } else {
        toast.success("Export completed successfully.");
      }
    } else if (exportStatus.status === "failed") {
      toast.error("Export failed", {
        description:
          exportStatus.error_message ?? "An unexpected error occurred.",
      });
    }
  }, [exportStatus]);

  // Poll export status every 5 seconds when async export is pending
  useEffect(() => {
    if (isExporting && exportStatus?.job_id) {
      const jobId = exportStatus.job_id;
      pollIntervalRef.current = setInterval(() => {
        void checkExportStatus(jobId);
      }, POLL_INTERVAL_MS);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [isExporting, exportStatus?.job_id, checkExportStatus]);

  const button = (
    <Button
      variant="outline"
      size="default"
      disabled={isDisabled || isExporting}
      onClick={() => void handleExport()}
    >
      <Download className="mr-2 h-4 w-4" />
      {isExporting ? "Exporting…" : "Export to PDF"}
    </Button>
  );

  if (isDisabled) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span tabIndex={0} className="inline-block">
              {button}
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>No events to export</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return button;
}
