/**
 * AuditTrailPage — Main page for the centralized Audit Trail Viewer.
 *
 * Route: /admin/audit-trail
 * Composes: AuditTrailFilters, AuditTrailTable, AuditEventDetailPanel, AuditExportButton
 * On mount: calls store.fetchEvents() to load initial data.
 *
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
 */

import { useEffect } from "react";
import { useAuditTrailStore } from "@/stores/useAuditTrailStore";
import { AuditTrailFilters } from "@/components/AuditTrailFilters";
import { AuditTrailTable } from "@/components/AuditTrailTable";
import { AuditEventDetailPanel } from "@/components/AuditEventDetailPanel";
import { AuditExportButton } from "@/components/AuditExportButton";

export function AuditTrailPage() {
  const fetchEvents = useAuditTrailStore((state) => state.fetchEvents);
  const selectedEvent = useAuditTrailStore((state) => state.selectedEvent);
  const clearSelectedEvent = useAuditTrailStore(
    (state) => state.clearSelectedEvent
  );

  // Load initial data on mount
  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Audit Trail</h2>
          <p className="text-sm text-muted-foreground">
            Centralized view of all audit events across the system
          </p>
        </div>
        <AuditExportButton />
      </div>

      {/* Filter bar */}
      <AuditTrailFilters />

      {/* Data table */}
      <AuditTrailTable />

      {/* Detail slide-over panel */}
      <AuditEventDetailPanel
        open={selectedEvent !== null}
        onOpenChange={(open) => {
          if (!open) {
            clearSelectedEvent();
          }
        }}
      />
    </div>
  );
}
