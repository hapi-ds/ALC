import { PenTool, Lock } from "lucide-react";

export function SignaturesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Electronic Signatures</h2>
        <p className="text-sm text-muted-foreground">
          PAdES digital signatures with re-authentication
        </p>
      </div>

      {/* Re-authentication dialog placeholder */}
      <div className="max-w-md mx-auto border border-border rounded-lg p-6">
        <div className="text-center mb-4">
          <Lock className="h-8 w-8 mx-auto mb-2 text-primary" aria-hidden="true" />
          <h3 className="font-semibold">Re-Authentication Required</h3>
          <p className="text-sm text-muted-foreground mt-1">
            Enter your credentials to sign this document
          </p>
        </div>
        <div className="space-y-3">
          <div>
            <label htmlFor="sig-password" className="text-sm font-medium">
              Password
            </label>
            <input
              id="sig-password"
              type="password"
              className="w-full mt-1 px-3 py-2 border border-border rounded-md bg-background"
              placeholder="Enter password"
            />
          </div>
          <div>
            <label htmlFor="sig-reason" className="text-sm font-medium">
              Reason for Signature
            </label>
            <input
              id="sig-reason"
              type="text"
              className="w-full mt-1 px-3 py-2 border border-border rounded-md bg-background"
              placeholder="e.g., Approved by QA"
              readOnly
            />
          </div>
        </div>
        <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
          <PenTool className="h-3 w-3" aria-hidden="true" />
          <span>PAdES signature with x.509 certificate</span>
        </div>
      </div>
    </div>
  );
}
