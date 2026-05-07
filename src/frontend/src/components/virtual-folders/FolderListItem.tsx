import { FolderOpen, FolderLock, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { VirtualFolderResponse } from "@/types/virtualFolder";
import { formatTagFilter } from "@/lib/virtualFolderUtils";

export interface FolderListItemProps {
  folder: VirtualFolderResponse;
  onClick: () => void;
  onEdit: () => void;
  onDelete: () => void;
}

/**
 * Renders a single folder row in the folder list.
 *
 * - Displays folder name and filter summary (via formatTagFilter)
 * - Shows "System" badge and distinct icon for system default folders
 * - Shows edit/delete action buttons only for non-system-default folders
 */
export function FolderListItem({ folder, onClick, onEdit, onDelete }: FolderListItemProps) {
  const isSystem = folder.is_system_default;

  return (
    <div
      className="flex items-center gap-3 p-4 border border-border rounded-lg hover:bg-accent/50 cursor-pointer transition-colors"
      role="listitem"
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      tabIndex={0}
      aria-label={`Folder: ${folder.name}`}
    >
      {isSystem ? (
        <FolderLock className="h-5 w-5 text-muted-foreground shrink-0" aria-hidden="true" />
      ) : (
        <FolderOpen className="h-5 w-5 text-primary shrink-0" aria-hidden="true" />
      )}

      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{folder.name}</p>
        <p className="text-xs text-muted-foreground truncate">
          {formatTagFilter(folder.tag_filter)}
        </p>
      </div>

      {isSystem && (
        <span className="text-xs bg-muted px-2 py-0.5 rounded shrink-0">
          System
        </span>
      )}

      {!isSystem && (
        <div className="flex items-center gap-1 shrink-0" data-testid="folder-actions">
          <Button
            variant="ghost"
            size="icon"
            onClick={(e) => {
              e.stopPropagation();
              onEdit();
            }}
            aria-label={`Edit folder: ${folder.name}`}
          >
            <Pencil className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={(e) => {
              e.stopPropagation();
              onDelete();
            }}
            aria-label={`Delete folder: ${folder.name}`}
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  );
}
