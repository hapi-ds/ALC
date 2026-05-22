import { useEffect } from "react";
import { FileText } from "lucide-react";
import type { DocumentResponse } from "@/types/document";
import { SignatureStatusBadge } from "@/components/signatures/SignatureStatusBadge";
import { useSignatureStore } from "@/stores/signatureStore";

interface DocumentListProps {
  documents?: DocumentResponse[];
  onDocumentClick: (uuid: string) => void;
}

export function DocumentList({ documents = [], onDocumentClick }: DocumentListProps) {
  const { records, fetchSignatureRecords } = useSignatureStore();

  // Fetch signature records for visible documents not already in the store
  useEffect(() => {
    for (const doc of documents) {
      if (!(doc.document_uuid in records)) {
        fetchSignatureRecords(doc.document_uuid);
      }
    }
  }, [documents, records, fetchSignatureRecords]);

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
      {documents.map((doc) => {
        const docRecords = records[doc.document_uuid] ?? [];
        const signatureCount = docRecords.length;

        // Derive latestSigner from the most recent record (sorted by signed_at descending)
        let latestSigner: { displayName: string; transition: string; signedAt: string } | undefined;
        if (signatureCount > 0) {
          const sorted = [...docRecords].sort(
            (a, b) => new Date(b.signed_at).getTime() - new Date(a.signed_at).getTime()
          );
          const latest = sorted[0];
          latestSigner = {
            displayName: "User #" + latest.signer_user_id,
            transition: latest.transition,
            signedAt: latest.signed_at,
          };
        }

        return (
          <div
            key={doc.document_uuid}
            className="flex items-center gap-3 p-3 border border-border rounded-md hover:bg-accent/50 cursor-pointer"
            role="listitem"
            onClick={() => onDocumentClick(doc.document_uuid)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onDocumentClick(doc.document_uuid);
              }
            }}
            tabIndex={0}
          >
            <FileText className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{doc.title}</p>
              <p className="text-xs text-muted-foreground">
                {doc.document_uuid} • {doc.document_type}
              </p>
            </div>
            {doc.tags && doc.tags.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {doc.tags.map((tag) => (
                  <span
                    key={tag.id}
                    className="text-xs px-1.5 py-0.5 bg-primary/10 text-primary rounded"
                  >
                    {tag.tag}
                  </span>
                ))}
              </div>
            )}
            <SignatureStatusBadge
              documentUuid={doc.document_uuid}
              signatureCount={signatureCount}
              latestSigner={latestSigner}
            />
            <span className="text-xs px-2 py-0.5 bg-muted rounded shrink-0">
              {doc.current_status}
            </span>
            <span className="text-xs text-muted-foreground shrink-0">
              {new Date(doc.created_at).toLocaleDateString()}
            </span>
          </div>
        );
      })}
    </div>
  );
}
