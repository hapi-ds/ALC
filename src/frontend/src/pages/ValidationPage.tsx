import { Button } from "@/components/ui/button";
import { ShieldCheck, Play, Download, FileCheck } from "lucide-react";

export function ValidationPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">CSV Validation</h2>
          <p className="text-sm text-muted-foreground">
            Computer System Validation — trigger test runs and view results
          </p>
        </div>
        <div className="flex gap-2">
          <Button>
            <Play className="h-4 w-4 mr-2" aria-hidden="true" />
            Run Validation
          </Button>
          <Button variant="outline">
            <Download className="h-4 w-4 mr-2" aria-hidden="true" />
            Download Certificate
          </Button>
        </div>
      </div>

      {/* Validation status */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="border border-border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Last Run</p>
          <p className="text-lg font-bold">Never</p>
        </div>
        <div className="border border-border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Pass Rate</p>
          <p className="text-lg font-bold">—</p>
        </div>
        <div className="border border-border rounded-lg p-4">
          <p className="text-sm text-muted-foreground">Requirements Covered</p>
          <p className="text-lg font-bold">—</p>
        </div>
      </div>

      {/* Traceability matrix placeholder */}
      <section aria-label="Traceability matrix">
        <h3 className="text-lg font-semibold flex items-center gap-2">
          <FileCheck className="h-4 w-4" aria-hidden="true" />
          Traceability Matrix
        </h3>
        <div className="border border-border rounded-lg p-8 mt-3 text-center text-muted-foreground">
          <ShieldCheck className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
          <p>Run a validation suite to generate the traceability matrix</p>
          <p className="text-xs mt-1">Maps URS REQ-IDs to Playwright test results</p>
        </div>
      </section>
    </div>
  );
}
