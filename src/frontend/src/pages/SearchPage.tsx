import { Button } from "@/components/ui/button";
import { Search } from "lucide-react";

export function SearchPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Search</h2>
        <p className="text-sm text-muted-foreground">
          Hybrid search combining BM25 lexical and semantic kNN search
        </p>
      </div>

      {/* Search input */}
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <input
            type="search"
            placeholder="Search documents..."
            className="w-full pl-10 pr-4 py-2 border border-border rounded-md bg-background text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            aria-label="Search documents"
          />
        </div>
        <Button>Search</Button>
      </div>

      {/* Results placeholder */}
      <div className="border border-border rounded-lg p-8 text-center text-muted-foreground">
        <Search className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
        <p>Enter a query to search across all documents</p>
        <p className="text-xs mt-1">
          Results include Document-UUID, title, version, excerpt, and relevance score
        </p>
      </div>
    </div>
  );
}
