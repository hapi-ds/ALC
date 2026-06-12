import { useCallback } from "react";
import { useForm } from "react-hook-form";
import { Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useInternalize } from "@/hooks/useLiteratureSearch";
import { CitationCollectionSelector } from "./CitationCollectionSelector";
import {
  TraceabilityLinkSelector,
  type TraceabilityLinkEntry,
} from "./TraceabilityLinkSelector";
import type { InternalizationRequest } from "@/types/literatureSearch";

interface InternalizationDialogProps {
  /** Whether the dialog is open */
  open: boolean;
  /** Callback to toggle open state */
  onOpenChange: (open: boolean) => void;
  /** The ingestion record ID to internalize */
  ingestionRecordId: number;
  /** Default document title from search result */
  defaultTitle: string;
}

interface InternalizationFormData {
  document_name: string;
  tags: string;
  citation_collection_id: number | null;
  traceability_links: TraceabilityLinkEntry[];
}

/**
 * InternalizationDialog is a modal form for one-click internalization
 * of a literature record into a managed Document entity.
 * Uses react-hook-form for form state management and validation.
 *
 * Validates: Requirements 4.1, 9.6
 */
export function InternalizationDialog({
  open,
  onOpenChange,
  ingestionRecordId,
  defaultTitle,
}: InternalizationDialogProps) {
  const { internalize, loading } = useInternalize();

  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<InternalizationFormData>({
    defaultValues: {
      document_name: defaultTitle,
      tags: "",
      citation_collection_id: null,
      traceability_links: [],
    },
  });

  const citationCollectionId = watch("citation_collection_id");
  const traceabilityLinks = watch("traceability_links");

  const onSubmit = useCallback(
    async (data: InternalizationFormData) => {
      const tagsArray = data.tags
        .split(",")
        .map((t) => t.trim())
        .filter((t) => t.length > 0);

      const validLinks = data.traceability_links
        .filter((link) => link.target_id.trim() !== "")
        .map((link) => ({
          target_type: link.target_type,
          target_id: Number(link.target_id),
        }));

      const request: InternalizationRequest = {
        ingestion_record_id: ingestionRecordId,
        document_name: data.document_name.trim() || null,
        document_type: "literature",
        tags: tagsArray,
        citation_collection_id: data.citation_collection_id,
        traceability_links: validLinks,
      };

      const result = await internalize(request);
      if (result) {
        reset();
        onOpenChange(false);
      }
    },
    [ingestionRecordId, internalize, reset, onOpenChange],
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Internalize Literature</DialogTitle>
          <DialogDescription>
            Convert this literature record into a managed document.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Document Name */}
          <div className="space-y-1">
            <label
              htmlFor="internalize-doc-name"
              className="text-sm font-medium"
            >
              Document Name
            </label>
            <Input
              id="internalize-doc-name"
              {...register("document_name", {
                required: "Document name is required",
                maxLength: {
                  value: 500,
                  message: "Name must be 500 characters or less",
                },
              })}
              placeholder="Enter document name"
              disabled={loading}
            />
            {errors.document_name && (
              <p className="text-sm text-destructive">
                {errors.document_name.message}
              </p>
            )}
          </div>

          {/* Tags */}
          <div className="space-y-1">
            <label htmlFor="internalize-tags" className="text-sm font-medium">
              Tags
            </label>
            <Input
              id="internalize-tags"
              {...register("tags")}
              placeholder="Comma-separated tags"
              disabled={loading}
            />
            <p className="text-xs text-muted-foreground">
              Separate multiple tags with commas
            </p>
          </div>

          {/* Citation Collection */}
          <div className="space-y-1">
            <label className="text-sm font-medium">Citation Collection</label>
            <CitationCollectionSelector
              value={citationCollectionId}
              onChange={(id) => setValue("citation_collection_id", id)}
              disabled={loading}
            />
          </div>

          {/* Traceability Links */}
          <div className="space-y-1">
            <label className="text-sm font-medium">Traceability Links</label>
            <TraceabilityLinkSelector
              value={traceabilityLinks}
              onChange={(links) => setValue("traceability_links", links)}
              disabled={loading}
            />
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={loading}>
              {loading && (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              Internalize
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
