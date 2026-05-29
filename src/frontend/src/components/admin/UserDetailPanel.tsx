import { useEffect, useState } from "react";
import {
  X,
  Pencil,
  ShieldOff,
  ShieldCheck,
  KeyRound,
  Building2,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAdminStore } from "@/stores/adminStore";
import { useAuthStore } from "@/stores/authStore";
import { UserHistoryTimeline } from "./UserHistoryTimeline";
import type { UserDetail } from "@/types/admin";

interface UserDetailPanelProps {
  userId: number;
  onClose: () => void;
  onEdit: (user: UserDetail) => void;
}

/**
 * Side panel showing user details, memberships (active and revoked),
 * action buttons (Edit, Deactivate/Reactivate, Reset Password),
 * and change history timeline.
 *
 * Prevents self-deactivation by disabling the deactivate button
 * when the viewed user is the currently authenticated user.
 */
export function UserDetailPanel({ userId, onClose, onEdit }: UserDetailPanelProps) {
  const {
    currentUser,
    userHistory,
    isLoading,
    fetchUserDetail,
    fetchUserHistory,
    deactivateUser,
    reactivateUser,
    resetPassword,
  } = useAdminStore();

  const authUser = useAuthStore((s) => s.user);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reasonDialogAction, setReasonDialogAction] = useState<
    "deactivate" | "reactivate" | "reset-password" | null
  >(null);
  const [reason, setReason] = useState("");

  const isSelf = authUser?.id === userId;

  useEffect(() => {
    fetchUserDetail(userId);
    fetchUserHistory(userId);
  }, [userId, fetchUserDetail, fetchUserHistory]);

  const handleAction = async () => {
    if (!reasonDialogAction || reason.trim().length < 10) return;

    setActionError(null);
    try {
      if (reasonDialogAction === "deactivate") {
        await deactivateUser(userId, reason.trim());
        await fetchUserDetail(userId);
      } else if (reasonDialogAction === "reactivate") {
        await reactivateUser(userId, reason.trim());
        await fetchUserDetail(userId);
      } else if (reasonDialogAction === "reset-password") {
        const password = await resetPassword(userId, reason.trim());
        setTempPassword(password);
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setReasonDialogAction(null);
      setReason("");
    }
  };

  if (isLoading && !currentUser) {
    return (
      <aside className="w-full max-w-md border-l border-border bg-background p-6" aria-label="User detail panel">
        <div className="animate-pulse space-y-4">
          <div className="h-6 w-2/3 rounded bg-muted" />
          <div className="h-4 w-1/2 rounded bg-muted" />
          <div className="h-4 w-3/4 rounded bg-muted" />
        </div>
      </aside>
    );
  }

  if (!currentUser) {
    return (
      <aside className="w-full max-w-md border-l border-border bg-background p-6" aria-label="User detail panel">
        <p className="text-sm text-muted-foreground">User not found.</p>
      </aside>
    );
  }

  return (
    <aside className="flex w-full max-w-md flex-col border-l border-border bg-background" aria-label="User detail panel">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <h2 className="text-lg font-semibold text-foreground">User Details</h2>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
        {/* User info */}
        <section aria-labelledby="user-info-heading">
          <h3 id="user-info-heading" className="sr-only">User information</h3>
          <div className="space-y-3">
            <div>
              <p className="text-xl font-semibold text-foreground">{currentUser.full_name}</p>
              <p className="text-sm text-muted-foreground">@{currentUser.username}</p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <span className="text-muted-foreground">Email</span>
                <p className="font-medium text-foreground">{currentUser.email}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Status</span>
                <p className="font-medium">
                  {currentUser.is_active ? (
                    <span className="inline-flex items-center gap-1 text-green-600">
                      <span className="h-2 w-2 rounded-full bg-green-500" aria-hidden="true" />
                      Active
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-red-600">
                      <span className="h-2 w-2 rounded-full bg-red-500" aria-hidden="true" />
                      Deactivated
                    </span>
                  )}
                </p>
              </div>
              <div>
                <span className="text-muted-foreground">Created</span>
                <p className="font-medium text-foreground">
                  {new Date(currentUser.created_at).toLocaleDateString()}
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* Action buttons */}
        <section aria-labelledby="actions-heading">
          <h3 id="actions-heading" className="text-sm font-medium text-muted-foreground mb-2">
            Actions
          </h3>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => onEdit(currentUser)}>
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
              Edit
            </Button>

            {currentUser.is_active ? (
              <Button
                variant="outline"
                size="sm"
                disabled={isSelf}
                title={isSelf ? "You cannot deactivate your own account" : "Deactivate user"}
                onClick={() => setReasonDialogAction("deactivate")}
              >
                <ShieldOff className="h-3.5 w-3.5" aria-hidden="true" />
                Deactivate
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setReasonDialogAction("reactivate")}
              >
                <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Reactivate
              </Button>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={() => setReasonDialogAction("reset-password")}
            >
              <KeyRound className="h-3.5 w-3.5" aria-hidden="true" />
              Reset Password
            </Button>
          </div>

          {isSelf && currentUser.is_active && (
            <p className="mt-1 text-xs text-muted-foreground">
              You cannot deactivate your own account.
            </p>
          )}

          {actionError && (
            <p className="mt-2 text-sm text-red-600" role="alert">{actionError}</p>
          )}

          {tempPassword && (
            <div className="mt-3 rounded-md border border-green-200 bg-green-50 p-3" role="alert">
              <p className="text-sm font-medium text-green-800">Password reset successful</p>
              <p className="mt-1 text-sm text-green-700">
                Temporary password:{" "}
                <code className="rounded bg-green-100 px-1.5 py-0.5 font-mono text-xs">
                  {tempPassword}
                </code>
              </p>
              <p className="mt-1 text-xs text-green-600">
                Communicate this password securely to the user.
              </p>
            </div>
          )}
        </section>

        {/* Memberships */}
        <section aria-labelledby="memberships-heading">
          <h3 id="memberships-heading" className="text-sm font-medium text-muted-foreground mb-2">
            Company Memberships
          </h3>
          {currentUser.memberships.length === 0 ? (
            <p className="text-sm text-muted-foreground">No memberships.</p>
          ) : (
            <ul className="space-y-2">
              {currentUser.memberships.map((membership) => (
                <li
                  key={membership.id}
                  className="rounded-md border border-border p-3 text-sm"
                >
                  <div className="flex items-center gap-2">
                    <Building2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                    <span className="font-medium text-foreground">
                      {membership.company_name}
                    </span>
                    <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground">
                      {membership.role}
                    </span>
                  </div>
                  <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" aria-hidden="true" />
                      Assigned: {new Date(membership.created_at).toLocaleDateString()}
                    </span>
                    {membership.revoked_at ? (
                      <span className="text-red-500">
                        Revoked: {new Date(membership.revoked_at).toLocaleDateString()}
                      </span>
                    ) : (
                      <span className="text-green-600">Active</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* History timeline */}
        <section aria-labelledby="history-heading">
          <h3 id="history-heading" className="text-sm font-medium text-muted-foreground mb-3">
            Change History
          </h3>
          <UserHistoryTimeline entries={userHistory} />
        </section>
      </div>

      {/* Reason dialog (inline modal) */}
      {reasonDialogAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" aria-hidden={!reasonDialogAction}>
          <div className="fixed inset-0 bg-black/50" aria-hidden="true" onClick={() => setReasonDialogAction(null)} />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reason-dialog-title"
            className="relative z-10 w-full max-w-md rounded-lg bg-background p-6 shadow-xl"
          >
            <h2 id="reason-dialog-title" className="text-lg font-semibold text-foreground">
              {reasonDialogAction === "deactivate" && "Deactivate User"}
              {reasonDialogAction === "reactivate" && "Reactivate User"}
              {reasonDialogAction === "reset-password" && "Reset Password"}
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Provide a reason for this action. This will be recorded in the audit trail.
            </p>
            <div className="mt-4">
              <label htmlFor="action-reason" className="block text-sm font-medium text-foreground">
                Reason
              </label>
              <textarea
                id="action-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Describe the reason for this action..."
                rows={3}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
                autoFocus
              />
              <p className="mt-1 text-xs text-muted-foreground">
                {reason.trim().length}/10 characters minimum
              </p>
            </div>
            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" onClick={() => { setReasonDialogAction(null); setReason(""); }}>
                Cancel
              </Button>
              <Button
                variant={reasonDialogAction === "deactivate" ? "destructive" : "default"}
                disabled={reason.trim().length < 10}
                onClick={handleAction}
              >
                Confirm
              </Button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
