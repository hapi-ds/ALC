/**
 * NotificationPanel
 *
 * Lists unacknowledged impact notifications with affected document title,
 * severity badge, change summary, and an "Acknowledge" button that calls
 * POST with X-Change-Reason header.
 *
 * Requirements: 10.5
 */

import { useState } from "react";
import {
  AlertTriangle,
  AlertCircle,
  Bell,
  Check,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useImpactAnalysisStore } from "@/stores/impactAnalysisStore";
import type { ImpactNotification } from "@/types/impactAnalysis";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getSeverityBadge(severity: string) {
  switch (severity) {
    case "critical":
      return {
        label: "Critical",
        className: "bg-red-100 text-red-800",
        icon: AlertTriangle,
      };
    case "major":
      return {
        label: "Major",
        className: "bg-orange-100 text-orange-800",
        icon: AlertTriangle,
      };
    case "minor":
      return {
        label: "Minor",
        className: "bg-yellow-100 text-yellow-800",
        icon: AlertCircle,
      };
    default:
      return {
        label: severity,
        className: "bg-gray-100 text-gray-700",
        icon: AlertCircle,
      };
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface NotificationPanelProps {
  notifications: ImpactNotification[];
}

export function NotificationPanel({ notifications }: NotificationPanelProps) {
  const acknowledgeNotification = useImpactAnalysisStore(
    (s) => s.acknowledgeNotification,
  );
  const [acknowledgingIds, setAcknowledgingIds] = useState<Set<number>>(
    new Set(),
  );

  async function handleAcknowledge(id: number) {
    setAcknowledgingIds((prev) => new Set(prev).add(id));
    try {
      await acknowledgeNotification(id, "Acknowledged impact notification");
    } finally {
      setAcknowledgingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  if (notifications.length === 0) {
    return (
      <div className="border border-border rounded-lg p-6 text-center text-muted-foreground">
        <Bell className="h-10 w-10 mx-auto mb-3 opacity-50" aria-hidden="true" />
        <p className="text-sm font-medium">No unacknowledged notifications</p>
        <p className="text-xs mt-1">
          You will be notified when document changes impact your documents.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2" role="list" aria-label="Impact notifications">
      {notifications.map((notification) => {
        const badge = getSeverityBadge(notification.impact_severity);
        const BadgeIcon = badge.icon;
        const isAcknowledging = acknowledgingIds.has(notification.id);

        return (
          <div
            key={notification.id}
            className="border border-border rounded-lg p-3 flex items-start gap-3"
            role="listitem"
          >
            {/* Severity badge */}
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium shrink-0 mt-0.5 ${badge.className}`}
            >
              <BadgeIcon className="h-3 w-3" aria-hidden="true" />
              {badge.label}
            </span>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">
                {notification.affected_document_uuid}
              </p>
              <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
                {notification.change_summary}
              </p>
            </div>

            {/* Acknowledge button */}
            <Button
              variant="outline"
              size="sm"
              disabled={isAcknowledging}
              onClick={() => handleAcknowledge(notification.id)}
              aria-label={`Acknowledge notification for ${notification.affected_document_uuid}`}
            >
              {isAcknowledging ? (
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
              ) : (
                <Check className="h-3 w-3" aria-hidden="true" />
              )}
              Acknowledge
            </Button>
          </div>
        );
      })}
    </div>
  );
}
