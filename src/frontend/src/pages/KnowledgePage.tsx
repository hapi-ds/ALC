import { Button } from "@/components/ui/button";
import { MessageSquare, Send } from "lucide-react";

export function KnowledgePage() {
  return (
    <div className="flex flex-col h-full">
      <div className="mb-4">
        <h2 className="text-2xl font-bold">Knowledge Chat</h2>
        <p className="text-sm text-muted-foreground">
          Conversational RAG queries with source citations
        </p>
      </div>

      {/* Chat messages area */}
      <div className="flex-1 border border-border rounded-lg p-4 overflow-y-auto mb-4">
        <div className="flex items-center justify-center h-full text-muted-foreground">
          <div className="text-center">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
            <p>Ask questions about your documents</p>
            <p className="text-xs mt-1">
              Responses include source citations with Document-UUID, title, version, and page
            </p>
          </div>
        </div>
      </div>

      {/* Chat input */}
      <div className="flex gap-2">
        <input
          type="text"
          placeholder="Ask a question about your documents..."
          className="flex-1 px-4 py-2 border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          aria-label="Chat message input"
        />
        <Button aria-label="Send message">
          <Send className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
