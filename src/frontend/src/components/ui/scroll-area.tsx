import * as React from "react";

import { cn } from "@/lib/utils";

/**
 * A lightweight scrollable container styled to match shadcn/ui conventions.
 * Uses native overflow scrolling with custom scrollbar styles.
 */
const ScrollArea = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, children, ...props }, ref) => {
  return (
    <div
      ref={ref}
      className={cn(
        "relative overflow-auto scrollbar-thin scrollbar-thumb-muted-foreground/20 scrollbar-track-transparent",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
});
ScrollArea.displayName = "ScrollArea";

export { ScrollArea };
