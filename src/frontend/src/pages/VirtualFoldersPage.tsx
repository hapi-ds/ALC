import { Button } from "@/components/ui/button";
import { FolderPlus, FolderOpen } from "lucide-react";

const defaultFolders = [
  { name: "All SOPs", filter: { tags: ["SOP"] }, isSystem: true },
  { name: "All Reports", filter: { tags: ["Report"] }, isSystem: true },
  { name: "All Templates", filter: { tags: ["Template"] }, isSystem: true },
  { name: "Approved Documents", filter: { status: "Approved" }, isSystem: true },
  { name: "Documents In Training", filter: { status: "InTraining" }, isSystem: true },
];

export function VirtualFoldersPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Virtual Folders</h2>
          <p className="text-sm text-muted-foreground">
            Tag-based dynamic document views
          </p>
        </div>
        <Button>
          <FolderPlus className="h-4 w-4 mr-2" aria-hidden="true" />
          Create Folder
        </Button>
      </div>

      {/* Virtual folder list */}
      <div className="grid gap-3">
        {defaultFolders.map((folder) => (
          <div
            key={folder.name}
            className="flex items-center gap-3 p-4 border border-border rounded-lg hover:bg-accent/50 cursor-pointer transition-colors"
          >
            <FolderOpen className="h-5 w-5 text-primary" aria-hidden="true" />
            <div className="flex-1">
              <p className="font-medium">{folder.name}</p>
              <p className="text-xs text-muted-foreground">
                Filter: {JSON.stringify(folder.filter)}
              </p>
            </div>
            {folder.isSystem && (
              <span className="text-xs bg-muted px-2 py-0.5 rounded">System</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
