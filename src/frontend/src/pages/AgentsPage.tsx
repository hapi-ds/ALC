import { Button } from "@/components/ui/button";
import { Bot, Upload, Download, Plus } from "lucide-react";

export function AgentsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Agents</h2>
          <p className="text-sm text-muted-foreground">
            Manage AI agents for document generation and review
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline">
            <Upload className="h-4 w-4 mr-2" aria-hidden="true" />
            Import
          </Button>
          <Button variant="outline">
            <Download className="h-4 w-4 mr-2" aria-hidden="true" />
            Export
          </Button>
          <Button>
            <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
            New Agent
          </Button>
        </div>
      </div>

      {/* Agent list placeholder */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Example agent cards */}
        {["SOP Drafting Agent", "Deviation Report Agent", "Protocol Summary Agent"].map(
          (name) => (
            <div
              key={name}
              className="border border-border rounded-lg p-4 hover:border-primary/50 cursor-pointer transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <Bot className="h-5 w-5 text-primary" aria-hidden="true" />
                <h3 className="font-medium">{name}</h3>
              </div>
              <p className="text-xs text-muted-foreground">
                Generation agent • Schema v1.0
              </p>
            </div>
          )
        )}
      </div>
    </div>
  );
}
