import { useState, useCallback } from "react";
import { Download, FileText, FileSpreadsheet, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useExport } from "@/hooks/useLiteratureSearch";
import type { ExportFormat } from "@/types/literatureSearch";

interface ExportMenuProps {
  /** The search execution ID to export results for. */
  searchExecutionId: number | null;
}

/**
 * ExportMenu provides a dropdown button offering "Export as CSV" and
 * "Export as PDF" options. For PDF exports, a PRISMA flow diagram
 * checkbox is available. Shows a loading indicator during generation
 * and displays success/error toasts via the useExport hook.
 *
 * Validates: Requirements 9.6
 */
export function ExportMenu({ searchExecutionId }: ExportMenuProps) {
  const { loading, exportResults } = useExport();
  const [includePrisma, setIncludePrisma] = useState(false);

  const handleExport = useCallback(
    async (format: ExportFormat) => {
      if (!searchExecutionId || loading) return;

      await exportResults({
        search_execution_id: searchExecutionId,
        saved_search_id: null,
        format,
        include_prisma_flow: format === "pdf" ? includePrisma : false,
      });
    },
    [searchExecutionId, loading, includePrisma, exportResults],
  );

  const isDisabled = !searchExecutionId || loading;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          disabled={isDisabled}
          aria-label="Export search results"
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Download className="h-4 w-4" aria-hidden="true" />
          )}
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuItem
          onClick={() => handleExport("csv")}
          disabled={loading}
        >
          <FileSpreadsheet className="h-4 w-4" aria-hidden="true" />
          Export as CSV
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => handleExport("pdf")}
          disabled={loading}
        >
          <FileText className="h-4 w-4" aria-hidden="true" />
          Export as PDF
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <div className="flex items-center gap-2 px-2 py-1.5">
          <Checkbox
            id="prisma-flow"
            checked={includePrisma}
            onCheckedChange={(checked) => setIncludePrisma(checked === true)}
            disabled={loading}
          />
          <label
            htmlFor="prisma-flow"
            className="cursor-pointer text-sm leading-none"
          >
            Include PRISMA flow (PDF)
          </label>
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
