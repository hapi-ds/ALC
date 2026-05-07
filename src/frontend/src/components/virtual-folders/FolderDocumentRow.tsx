import { FileText } from "lucide-react";
import type { DocumentResponse } from "../../types/document";

interface FolderDocumentRowProps {
  document: DocumentResponse;
}

export function FolderDocumentRow({ document }: FolderDocumentRowProps) {
  const tagNames = document.tags.map((t) => t.tag).join(", ");
  const formattedDate = new Date(document.created_at).toLocaleDateString();

  return (
    <div
      className="flex items-center gap-3 p-3 border border-border rounded-md"
      role="listitem"
    >
      <FileText className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{document.title}</p>
        <p className="text-xs text-muted-foreground">
          {document.document_uuid} • {document.document_type}
        </p>
      </div>
      {tagNames && (
        <span className="text-xs px-1.5 py-0.5 bg-primary/10 text-primary rounded shrink-0">
          {tagNames}
        </span>
      )}
      <span className="text-xs px-2 py-0.5 bg-muted rounded shrink-0">
        {document.current_status}
      </span>
      <span className="text-xs text-muted-foreground shrink-0">
        {formattedDate}
      </span>
    </div>
  );
}
