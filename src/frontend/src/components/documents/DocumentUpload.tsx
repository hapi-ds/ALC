import { Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

export function DocumentUpload() {
  return (
    <div className="border-2 border-dashed border-border rounded-lg p-8 text-center">
      <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm font-medium">Upload Document</p>
      <p className="text-xs text-muted-foreground mt-1">
        Drag and drop or click to select a file
      </p>
      <Button variant="outline" size="sm" className="mt-3">
        Select File
      </Button>
    </div>
  );
}
