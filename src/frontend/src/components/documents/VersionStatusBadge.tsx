interface VersionStatusBadgeProps {
  isCurrent: boolean;
}

export function VersionStatusBadge({ isCurrent }: VersionStatusBadgeProps) {
  if (isCurrent) {
    return (
      <span
        className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-primary/15 text-primary"
        aria-label="Current version"
      >
        Current
      </span>
    );
  }

  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground"
      aria-label="Previous version"
    >
      Previous
    </span>
  );
}
