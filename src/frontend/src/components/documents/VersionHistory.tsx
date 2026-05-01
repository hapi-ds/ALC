import { History } from "lucide-react";

interface Version {
  major_version: number;
  minor_version: number;
  uploaded_at: string;
  change_reason: string;
}

interface VersionHistoryProps {
  versions?: Version[];
}

export function VersionHistory({ versions = [] }: VersionHistoryProps) {
  if (versions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No versions available</p>
    );
  }

  return (
    <div className="space-y-2" role="list" aria-label="Version history">
      {versions.map((v, i) => (
        <div
          key={i}
          className="flex items-center gap-3 p-2 border-l-2 border-primary/30 pl-4"
          role="listitem"
        >
          <History className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium">
              v{v.major_version}.{v.minor_version}
            </p>
            <p className="text-xs text-muted-foreground">{v.change_reason}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
