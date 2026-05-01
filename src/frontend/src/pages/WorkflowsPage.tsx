import { Button } from "@/components/ui/button";
import { Plus, GitBranch } from "lucide-react";

export function WorkflowsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Workflows</h2>
          <p className="text-sm text-muted-foreground">
            BPMN workflow editor for document lifecycle management
          </p>
        </div>
        <Button>
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          New Workflow
        </Button>
      </div>

      {/* BPMN editor placeholder */}
      <div className="border border-border rounded-lg p-8 min-h-[500px]">
        <div className="flex items-center justify-center h-full text-muted-foreground">
          <div className="text-center">
            <GitBranch className="h-12 w-12 mx-auto mb-4 opacity-50" aria-hidden="true" />
            <p className="text-lg font-medium">BPMN Workflow Editor</p>
            <p className="text-sm mt-2 max-w-md">
              Define document lifecycle workflows with states, transitions,
              signature requirements, and training triggers.
            </p>
            <div className="mt-4 text-xs text-muted-foreground">
              <p>Example SOP workflow:</p>
              <p className="font-mono mt-1">
                Draft → Review → Approved → InTraining → Active
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
