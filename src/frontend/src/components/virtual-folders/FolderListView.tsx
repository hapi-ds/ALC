import { useEffect } from "react";
import { FolderPlus, FolderOpen, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useVirtualFolderStore } from "@/stores/virtualFolderStore";
import { FolderListItem } from "./FolderListItem";
import type { VirtualFolderResponse } from "@/types/virtualFolder";

export interface FolderListViewProps {
  onFolderClick: (folder: VirtualFolderResponse) => void;
  onCreateClick: () => void;
  onEditFolder: (folder: VirtualFolderResponse) => void;
  onDeleteFolder: (folder: VirtualFolderResponse) => void;
}

/**
 * Renders the virtual folder list view with header, loading/error/empty states,
 * and folder items. System default folders are displayed before user-created
 * folders (API sort order preserved).
 */
export function FolderListView({
  onFolderClick,
  onCreateClick,
  onEditFolder,
  onDeleteFolder,
}: FolderListViewProps) {
  const { folders, isFoldersLoading, foldersError, fetchFolders } =
    useVirtualFolderStore();

  useEffect(() => {
    fetchFolders();
  }, [fetchFolders]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Virtual Folders</h2>
          <p className="text-sm text-muted-foreground">
            Tag-based dynamic document views
          </p>
        </div>
        <Button onClick={onCreateClick}>
          <FolderPlus className="h-4 w-4 mr-2" aria-hidden="true" />
          Create Folder
        </Button>
      </div>

      {/* Error state */}
      {foldersError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p className="flex-1">{foldersError}</p>
          <Button variant="ghost" size="sm" onClick={fetchFolders}>
            Retry
          </Button>
        </div>
      )}

      {/* Loading state */}
      {isFoldersLoading && (
        <div
          className="flex items-center justify-center py-8"
          aria-label="Loading folders"
        >
          <Loader2
            className="h-6 w-6 animate-spin text-muted-foreground"
            aria-hidden="true"
          />
          <span className="sr-only">Loading folders</span>
        </div>
      )}

      {/* Empty state */}
      {!isFoldersLoading && !foldersError && folders.length === 0 && (
        <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
          <FolderOpen
            className="h-12 w-12 mx-auto mb-4 opacity-50"
            aria-hidden="true"
          />
          <p className="text-lg font-medium">No folders yet</p>
          <p className="text-sm mt-1">
            Create your first virtual folder to organize documents
          </p>
        </div>
      )}

      {/* Folder list */}
      {!isFoldersLoading && folders.length > 0 && (
        <div className="grid gap-3" role="list" aria-label="Virtual folders">
          {folders.map((folder) => (
            <FolderListItem
              key={folder.id}
              folder={folder}
              onClick={() => onFolderClick(folder)}
              onEdit={() => onEditFolder(folder)}
              onDelete={() => onDeleteFolder(folder)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
