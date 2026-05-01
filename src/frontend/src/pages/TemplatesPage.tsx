import { Button } from "@/components/ui/button";
import { Plus, GripVertical, Layout } from "lucide-react";

const fieldTypes = ["Text", "Float", "Integer", "Date", "Boolean"];

export function TemplatesPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Templates</h2>
          <p className="text-sm text-muted-foreground">
            Visual form builder with drag-and-drop field ordering
          </p>
        </div>
        <Button>
          <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
          New Template
        </Button>
      </div>

      {/* Template form builder placeholder */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Field palette */}
        <div className="border border-border rounded-lg p-4">
          <h3 className="font-semibold mb-3">Field Types</h3>
          <div className="space-y-2">
            {fieldTypes.map((type) => (
              <div
                key={type}
                className="flex items-center gap-2 p-2 border border-dashed border-border rounded cursor-grab hover:bg-accent/50"
              >
                <GripVertical className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                <span className="text-sm">{type}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Form canvas */}
        <div className="lg:col-span-2 border border-border rounded-lg p-4 min-h-[400px]">
          <h3 className="font-semibold mb-3">Form Canvas</h3>
          <div className="flex items-center justify-center h-64 border-2 border-dashed border-border rounded-lg text-muted-foreground">
            <div className="text-center">
              <Layout className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
              <p className="text-sm">Drag fields here to build your template</p>
              <p className="text-xs mt-1">
                Uses react-hook-form + @hello-pangea/dnd
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
