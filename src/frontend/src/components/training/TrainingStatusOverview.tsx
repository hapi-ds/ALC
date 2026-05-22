import { Clock, CheckCircle, GraduationCap } from "lucide-react";
import type { TrainingStatistics } from "./types";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TrainingStatusOverviewProps {
  statistics: TrainingStatistics;
  isLoading: boolean;
}

// ---------------------------------------------------------------------------
// Skeleton placeholder for a stat card
// ---------------------------------------------------------------------------

function StatCardSkeleton() {
  return (
    <div className="rounded-lg border p-4 animate-pulse">
      <div className="flex items-center gap-3">
        <div className="h-8 w-8 bg-muted rounded" />
        <div className="space-y-2">
          <div className="h-3 w-16 bg-muted rounded" />
          <div className="h-5 w-8 bg-muted rounded" />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stat card component
// ---------------------------------------------------------------------------

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: number;
}

function StatCard({ icon, label, value }: StatCardProps) {
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center gap-3">
        <div className="shrink-0" aria-hidden="true">
          {icon}
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold">{value}</p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TrainingStatusOverview
// ---------------------------------------------------------------------------

export function TrainingStatusOverview({
  statistics,
  isLoading,
}: TrainingStatusOverviewProps) {
  if (isLoading) {
    return (
      <div
        role="region"
        aria-label="Training Status Overview"
      >
        <div aria-live="polite" className="sr-only">
          Loading training statistics...
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <StatCardSkeleton />
          <StatCardSkeleton />
          <StatCardSkeleton />
        </div>
        <div className="mt-3 animate-pulse">
          <div className="h-4 w-32 bg-muted rounded" />
        </div>
      </div>
    );
  }

  const { pending, completed, total, completionPercentage } = statistics;

  return (
    <div
      role="region"
      aria-label="Training Status Overview"
    >
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard
          icon={<Clock className="h-8 w-8 text-amber-500" />}
          label="Pending"
          value={pending}
        />
        <StatCard
          icon={<CheckCircle className="h-8 w-8 text-green-500" />}
          label="Completed"
          value={completed}
        />
        <StatCard
          icon={<GraduationCap className="h-8 w-8 text-primary" />}
          label="Total Tasks"
          value={total}
        />
      </div>
      <p className="mt-3 text-sm text-muted-foreground">
        Completion:{" "}
        <span className="font-medium text-foreground">
          {completionPercentage !== null ? `${completionPercentage}%` : "N/A"}
        </span>
      </p>
    </div>
  );
}
