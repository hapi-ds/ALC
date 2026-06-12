import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useLiteratureSearchStore } from "@/stores/literatureSearchStore";

interface SaveSearchDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Modal dialog for saving the current search query configuration.
 * Collects a required name (1–200 characters) and an optional description
 * (max 1000 characters), then dispatches the saveCurrentSearch store action.
 */
export function SaveSearchDialog({ open, onOpenChange }: SaveSearchDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const saveCurrentSearch = useLiteratureSearchStore(
    (state) => state.saveCurrentSearch
  );

  const isNameValid = name.trim().length >= 1 && name.trim().length <= 200;
  const isDescriptionValid = description.length <= 1000;
  const canSubmit = isNameValid && isDescriptionValid && !isSaving;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!canSubmit) return;

    setError(null);
    setIsSaving(true);

    try {
      await saveCurrentSearch(
        name.trim(),
        description.trim() || undefined
      );
      // Reset form and close dialog on success
      setName("");
      setDescription("");
      onOpenChange(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to save search.";
      setError(message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      // Reset form state when closing
      setName("");
      setDescription("");
      setError(null);
    }
    onOpenChange(nextOpen);
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Save Search</DialogTitle>
            <DialogDescription>
              Save this search configuration for later re-execution. Provide a
              name to identify it in your saved searches list.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 space-y-4">
            <div className="space-y-2">
              <label
                htmlFor="save-search-name"
                className="text-sm font-medium leading-none"
              >
                Name <span className="text-destructive">*</span>
              </label>
              <Input
                id="save-search-name"
                placeholder="e.g., MDR Clinical Evaluation Q1 2025"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={200}
                required
                aria-describedby="save-search-name-hint"
              />
              <p
                id="save-search-name-hint"
                className="text-xs text-muted-foreground"
              >
                {name.trim().length}/200 characters
              </p>
            </div>

            <div className="space-y-2">
              <label
                htmlFor="save-search-description"
                className="text-sm font-medium leading-none"
              >
                Description
              </label>
              <Textarea
                id="save-search-description"
                placeholder="Optional description of this search strategy..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={1000}
                rows={3}
                aria-describedby="save-search-description-hint"
              />
              <p
                id="save-search-description-hint"
                className="text-xs text-muted-foreground"
              >
                {description.length}/1000 characters
              </p>
            </div>

            {error && (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            )}
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isSaving}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {isSaving ? "Saving..." : "Save Search"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
