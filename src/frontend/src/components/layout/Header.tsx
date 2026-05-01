import { Button } from "@/components/ui/button";
import { LogOut, User } from "lucide-react";

export function Header() {
  return (
    <header className="h-14 border-b border-border bg-background flex items-center justify-between px-6">
      <div className="text-sm text-muted-foreground">
        AlcoaBase — Local GxP Document & Knowledge Management
      </div>
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" aria-label="User profile">
          <User className="h-4 w-4" aria-hidden="true" />
          <span className="ml-1">Admin</span>
        </Button>
        <Button variant="ghost" size="icon" aria-label="Sign out">
          <LogOut className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </header>
  );
}
