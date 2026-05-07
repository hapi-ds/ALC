import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { AlertCircle } from "lucide-react";
import { useVirtualFolderStore } from "@/stores/virtualFolderStore";
import {
  FolderListView,
  FolderDocumentView,
  CreateFolderDialog,
  EditFolderDialog,
  DeleteConfirmDialog,
} from "@/components/virtual-folders";
import type { VirtualFolderResponse } from "@/types/virtualFolder";

/** Cache staleness threshold in milliseconds (300 seconds). */
const CACHE_STALENESS_MS = 300_000;

/**
 * VirtualFoldersPage is the top-level page component for virtual folders.
 *
 * It reads `folderId` from the URL params:
 * - If absent → renders FolderListView
 * - If present and valid → renders FolderDocumentView for that folder
 * - If present but invalid → renders FolderListView with an error message
 *
 * Manages dialog state for create, edit, and delete operations.
 * Implements 300-second cache staleness check before re-fetching folders.
 */
export function VirtualFoldersPage() {
  const { folderId } = useParams<{ folderId: string }>();
  const navigate = useNavigate();

  const { folders, fetchFolders, selectFolder, lastFetchedAt } =
    useVirtualFolderStore();

  // Dialog state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingFolder, setEditingFolder] = useState<VirtualFolderResponse | null>(null);
  const [deletingFolder, setDeletingFolder] = useState<VirtualFolderResponse | null>(null);

  // Error for invalid folderId
  const [routeError, setRouteError] = useState<string | null>(null);

  // Fetch folders on mount with cache staleness check
  useEffect(() => {
    const isStale =
      lastFetchedAt === null ||
      Date.now() - lastFetchedAt > CACHE_STALENESS_MS;

    if (isStale) {
      fetchFolders();
    }
  }, [fetchFolders, lastFetchedAt]);

  // Resolve folderId from URL to a folder object
  const currentFolder = folderId
    ? folders.find((f) => String(f.id) === folderId) ?? null
    : null;

  // Handle invalid folderId: show error when folders are loaded but folderId doesn't match
  useEffect(() => {
    if (folderId && folders.length > 0 && !currentFolder) {
      setRouteError("Folder not found.");
    } else {
      setRouteError(null);
    }
  }, [folderId, folders, currentFolder]);

  // When a valid folder is resolved, select it in the store to trigger document fetch
  useEffect(() => {
    if (currentFolder) {
      selectFolder(currentFolder);
    }
  }, [currentFolder, selectFolder]);

  // Navigation handlers
  const handleFolderClick = useCallback(
    (folder: VirtualFolderResponse) => {
      navigate(`/folders/${folder.id}`);
    },
    [navigate]
  );

  const handleBack = useCallback(() => {
    navigate("/folders");
  }, [navigate]);

  // Dialog handlers
  const handleCreateClick = useCallback(() => {
    setIsCreateOpen(true);
  }, []);

  const handleCreateClose = useCallback(() => {
    setIsCreateOpen(false);
  }, []);

  const handleEditFolder = useCallback((folder: VirtualFolderResponse) => {
    setEditingFolder(folder);
  }, []);

  const handleEditClose = useCallback(() => {
    setEditingFolder(null);
  }, []);

  const handleDeleteFolder = useCallback((folder: VirtualFolderResponse) => {
    setDeletingFolder(folder);
  }, []);

  const handleDeleteClose = useCallback(() => {
    setDeletingFolder(null);
  }, []);

  // If folderId is present and valid, show document view
  if (folderId && currentFolder) {
    return (
      <>
        <FolderDocumentView folder={currentFolder} onBack={handleBack} />

        {/* Dialogs still available in document view for potential future use */}
        <DeleteConfirmDialog
          open={deletingFolder !== null}
          onClose={handleDeleteClose}
          folder={deletingFolder ?? currentFolder}
        />
      </>
    );
  }

  // Otherwise show folder list (including when folderId is invalid)
  return (
    <>
      {/* Route error for invalid folderId */}
      {routeError && (
        <div
          role="alert"
          className="mb-4 flex items-center gap-2 p-4 border border-destructive/50 bg-destructive/10 rounded-md text-sm text-destructive"
        >
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{routeError}</p>
        </div>
      )}

      <FolderListView
        onFolderClick={handleFolderClick}
        onCreateClick={handleCreateClick}
        onEditFolder={handleEditFolder}
        onDeleteFolder={handleDeleteFolder}
      />

      {/* Create Folder Dialog */}
      <CreateFolderDialog open={isCreateOpen} onClose={handleCreateClose} />

      {/* Edit Folder Dialog */}
      {editingFolder && (
        <EditFolderDialog
          open={editingFolder !== null}
          onClose={handleEditClose}
          folder={editingFolder}
        />
      )}

      {/* Delete Confirm Dialog */}
      {deletingFolder && (
        <DeleteConfirmDialog
          open={deletingFolder !== null}
          onClose={handleDeleteClose}
          folder={deletingFolder}
        />
      )}
    </>
  );
}
