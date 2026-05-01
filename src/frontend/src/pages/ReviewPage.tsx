import { Button } from "@/components/ui/button";
import { ClipboardCheck, AlertTriangle, CheckCircle, Info } from "lucide-react";

export function ReviewPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Document Review</h2>
          <p className="text-sm text-muted-foreground">
            AI-powered document review with structured findings
          </p>
        </div>
        <Button>
          <ClipboardCheck className="h-4 w-4 mr-2" aria-hidden="true" />
          Start Review
        </Button>
      </div>

      {/* Review report placeholder */}
      <div className="border border-border rounded-lg p-6">
        <h3 className="font-semibold mb-4">Review Report</h3>

        {/* Severity legend */}
        <div className="flex gap-4 mb-4 text-sm">
          <span className="flex items-center gap-1 text-red-600">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" /> Critical
          </span>
          <span className="flex items-center gap-1 text-orange-600">
            <AlertTriangle className="h-3 w-3" aria-hidden="true" /> Major
          </span>
          <span className="flex items-center gap-1 text-yellow-600">
            <Info className="h-3 w-3" aria-hidden="true" /> Minor
          </span>
          <span className="flex items-center gap-1 text-blue-600">
            <Info className="h-3 w-3" aria-hidden="true" /> Informational
          </span>
        </div>

        {/* Chapter results placeholder */}
        <div className="space-y-2">
          {["Purpose", "Scope", "Responsibilities", "Procedure", "Safety", "References"].map(
            (chapter) => (
              <div
                key={chapter}
                className="flex items-center justify-between p-3 bg-muted/30 rounded"
              >
                <span className="text-sm font-medium">{chapter}</span>
                <CheckCircle className="h-4 w-4 text-green-600" aria-hidden="true" />
              </div>
            )
          )}
        </div>

        <p className="text-sm text-muted-foreground mt-4">
          Select a document and trigger AI review to see structured results
        </p>
      </div>
    </div>
  );
}
