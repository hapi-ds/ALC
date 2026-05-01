import { FileText } from "lucide-react";

interface DocumentListProps {
  documents?: Array<{
    document_uuid: string;
    title: string;
    document_type: string;
    current_status: string;
  }>;
}

export function DocumentList({ documents = [] }: DocumentListProps) {
  if (documents.length === 0) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
        <p>No documents found</p>
      </div>
    );
  }

  return (
    <div className="space-y-2" role="list" aria-label="Document list">
      {documents.map((doc) => (
        <div
          key={doc.document_uuid}
          className="flex items-center gap-3 p-3 border border-border rounded-md hover:bg-accent/50 cursor-pointer"
          role="listitem"
        >
          <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium">{doc.title}</p>
            <p className="text-xs text-muted-foreground">
              {doc.document_uuid} • {doc.document_type}
            </p>
          </div>
          <span className="text-xs px-2 py-0.5 bg-muted rounded">
            {doc.current_status}
          </span>
        </div>
      ))}
    </div>
  );
}
