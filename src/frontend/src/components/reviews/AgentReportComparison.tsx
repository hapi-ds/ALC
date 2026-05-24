/**
 * AgentReportComparison Component
 *
 * Side-by-side display of 2–4 agent reports with synchronized scrolling.
 * Highlights consensus findings (green border) and contradictions (red border).
 *
 * References:
 *   - Design doc Section 8: Frontend Components
 *   - Requirements: 11.3
 */

import { useRef, useCallback, useMemo } from "react";
import { cn } from "@/lib/utils";
import type { AgentReview } from "@/lib/reviews-api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A finding extracted from an agent's report_data. */
export interface ReportFinding {
  chapter: string;
  severity: string;
  description: string;
  recommendation?: string;
}

/** Classification of a finding across agents. */
export type FindingClassification = "consensus" | "contradiction" | "neutral";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface AgentReportComparisonProps {
  /** 2–4 completed agent reviews to compare side-by-side. */
  agentReviews: AgentReview[];
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function AgentReportComparison({ agentReviews }: AgentReportComparisonProps) {
  const scrollRefs = useRef<(HTMLDivElement | null)[]>([]);
  const isSyncing = useRef(false);

  // Limit to 2–4 reports
  const reports = agentReviews
    .filter((r) => r.status === "Completed" && r.report_data)
    .slice(0, 4);

  // Extract findings from all reports
  const allFindings = useMemo(() => extractAllFindings(reports), [reports]);

  // Compute consensus and contradiction sets
  const classifications = useMemo(
    () => classifyFindings(allFindings),
    [allFindings],
  );

  // Synchronized scrolling handler
  const handleScroll = useCallback(
    (sourceIndex: number) => {
      if (isSyncing.current) return;
      isSyncing.current = true;

      const source = scrollRefs.current[sourceIndex];
      if (!source) {
        isSyncing.current = false;
        return;
      }

      const { scrollTop, scrollLeft } = source;

      scrollRefs.current.forEach((ref, idx) => {
        if (ref && idx !== sourceIndex) {
          ref.scrollTop = scrollTop;
          ref.scrollLeft = scrollLeft;
        }
      });

      // Use requestAnimationFrame to release the sync lock after the browser
      // has processed the scroll events triggered by our programmatic scrolling
      requestAnimationFrame(() => {
        isSyncing.current = false;
      });
    },
    [],
  );

  const setScrollRef = useCallback(
    (index: number) => (el: HTMLDivElement | null) => {
      scrollRefs.current[index] = el;
    },
    [],
  );

  if (reports.length < 2) {
    return (
      <div
        className="text-sm text-muted-foreground text-center py-8"
        role="status"
      >
        At least 2 completed agent reports are required for comparison.
      </div>
    );
  }

  return (
    <section
      className="space-y-4"
      aria-labelledby="report-comparison-heading"
      role="region"
      aria-label="Agent report comparison"
    >
      <h3
        id="report-comparison-heading"
        className="text-sm font-semibold uppercase tracking-wide text-muted-foreground"
      >
        Agent Report Comparison
      </h3>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs" aria-label="Comparison legend">
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded border-2 border-green-500 bg-green-50" />
          <span>Consensus</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded border-2 border-red-500 bg-red-50" />
          <span>Contradiction</span>
        </div>
      </div>

      {/* Side-by-side panels */}
      <div
        className={cn(
          "grid gap-4",
          reports.length === 2 && "grid-cols-2",
          reports.length === 3 && "grid-cols-3",
          reports.length === 4 && "grid-cols-4",
        )}
      >
        {reports.map((review, index) => (
          <ReportPanel
            key={review.id}
            review={review}
            index={index}
            classifications={classifications}
            onScroll={() => handleScroll(index)}
            scrollRef={setScrollRef(index)}
          />
        ))}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Report Panel
// ---------------------------------------------------------------------------

interface ReportPanelProps {
  review: AgentReview;
  index: number;
  classifications: Map<string, FindingClassification>;
  onScroll: () => void;
  scrollRef: (el: HTMLDivElement | null) => void;
}

function ReportPanel({
  review,
  index,
  classifications,
  onScroll,
  scrollRef,
}: ReportPanelProps) {
  const report = review.report_data as Record<string, unknown> | null;
  const findings = extractFindings(report);

  return (
    <div className="border border-border rounded-md flex flex-col overflow-hidden">
      {/* Panel header */}
      <div className="px-3 py-2 border-b border-border bg-muted/30 shrink-0">
        <div className="font-medium text-sm truncate">{review.agent_name}</div>
        {review.agent_archetype && (
          <div className="text-xs text-muted-foreground">{review.agent_archetype}</div>
        )}
        <div className="text-xs text-muted-foreground mt-0.5">
          {findings.length} finding{findings.length !== 1 ? "s" : ""}
        </div>
      </div>

      {/* Scrollable content */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="flex-1 overflow-auto p-3 space-y-2 max-h-96"
        aria-label={`Report from ${review.agent_name}`}
        data-testid={`report-panel-${index}`}
      >
        {/* Summary */}
        {report?.summary && (
          <div className="text-xs text-muted-foreground pb-2 border-b border-border/50">
            {String(report.summary)}
          </div>
        )}

        {/* Findings */}
        {findings.length === 0 ? (
          <div className="text-xs text-muted-foreground italic">No findings</div>
        ) : (
          findings.map((finding, idx) => {
            const key = makeFindingKey(finding.chapter, finding.severity);
            const classification = classifications.get(key) ?? "neutral";

            return (
              <FindingCard
                key={idx}
                finding={finding}
                classification={classification}
              />
            );
          })
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Finding Card
// ---------------------------------------------------------------------------

interface FindingCardProps {
  finding: ReportFinding;
  classification: FindingClassification;
}

function FindingCard({ finding, classification }: FindingCardProps) {
  const borderClass = cn(
    "rounded-md border-2 p-2 text-xs space-y-1",
    classification === "consensus" && "border-green-500 bg-green-50/50",
    classification === "contradiction" && "border-red-500 bg-red-50/50",
    classification === "neutral" && "border-border bg-background",
  );

  return (
    <div className={borderClass} data-classification={classification}>
      <div className="flex items-center gap-2">
        <SeverityDot severity={finding.severity} />
        <span className="font-medium">{finding.severity}</span>
        {finding.chapter && (
          <span className="text-muted-foreground truncate">
            — {finding.chapter}
          </span>
        )}
      </div>
      {finding.description && (
        <p className="text-muted-foreground">{finding.description}</p>
      )}
      {finding.recommendation && (
        <p className="text-muted-foreground italic">
          Rec: {finding.recommendation}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Severity Dot
// ---------------------------------------------------------------------------

function SeverityDot({ severity }: { severity: string }) {
  const colorMap: Record<string, string> = {
    Critical: "bg-red-500",
    Major: "bg-orange-500",
    Minor: "bg-yellow-500",
    Informational: "bg-blue-500",
  };

  return (
    <span
      className={cn(
        "inline-block w-2 h-2 rounded-full shrink-0",
        colorMap[severity] || "bg-gray-400",
      )}
      aria-hidden="true"
    />
  );
}

// ---------------------------------------------------------------------------
// Logic — Finding Extraction & Classification
// ---------------------------------------------------------------------------

/** Extract findings from a single report's report_data. */
function extractFindings(report: Record<string, unknown> | null): ReportFinding[] {
  if (!report) return [];
  const rawFindings = report.findings;
  if (!Array.isArray(rawFindings)) return [];

  return rawFindings.map((f: unknown) => {
    const finding = f as Record<string, unknown>;
    return {
      chapter: String(finding.chapter || finding.section || ""),
      severity: String(finding.severity || "Unknown"),
      description: String(finding.description || ""),
      recommendation: finding.recommendation ? String(finding.recommendation) : undefined,
    };
  });
}

/** Extract findings from all reports, grouped by report index. */
function extractAllFindings(reports: AgentReview[]): ReportFinding[][] {
  return reports.map((review) =>
    extractFindings(review.report_data as Record<string, unknown> | null),
  );
}

/**
 * Classify findings as consensus or contradiction.
 *
 * Consensus: 2+ reports have findings with the same severity for the same chapter.
 * Contradiction: one report has Critical/Major for a chapter, another has nothing
 * or only Informational for the same chapter.
 *
 * Returns a Map from finding key (chapter|severity) to classification.
 */
export function classifyFindings(
  allFindings: ReportFinding[][],
): Map<string, FindingClassification> {
  const classifications = new Map<string, FindingClassification>();

  // Count how many reports have each (chapter, severity) pair
  const keyCountMap = new Map<string, number>();
  // Track which chapters each report covers (any severity)
  const chaptersByReport = allFindings.map((findings) => {
    const chapters = new Set<string>();
    findings.forEach((f) => {
      if (f.chapter) chapters.add(f.chapter);
    });
    return chapters;
  });

  // Track severities per chapter per report
  const chapterSeveritiesByReport: Map<string, string[]>[] = allFindings.map(
    (findings) => {
      const map = new Map<string, string[]>();
      findings.forEach((f) => {
        const chapter = f.chapter || "";
        const existing = map.get(chapter) || [];
        existing.push(f.severity);
        map.set(chapter, existing);
      });
      return map;
    },
  );

  // Count occurrences of each (chapter, severity) across reports
  allFindings.forEach((findings) => {
    // Use a set to avoid double-counting within the same report
    const seenKeys = new Set<string>();
    findings.forEach((f) => {
      const key = makeFindingKey(f.chapter, f.severity);
      if (!seenKeys.has(key)) {
        seenKeys.add(key);
        keyCountMap.set(key, (keyCountMap.get(key) || 0) + 1);
      }
    });
  });

  // Mark consensus: key appears in 2+ reports
  keyCountMap.forEach((count, key) => {
    if (count >= 2) {
      classifications.set(key, "consensus");
    }
  });

  // Detect contradictions: one report has Critical/Major for a chapter,
  // another report has nothing or only Informational for the same chapter
  const allChapters = new Set<string>();
  allFindings.forEach((findings) => {
    findings.forEach((f) => {
      if (f.chapter) allChapters.add(f.chapter);
    });
  });

  allChapters.forEach((chapter) => {
    const hasCriticalOrMajor: number[] = [];
    const hasNothingOrInfoOnly: number[] = [];

    chapterSeveritiesByReport.forEach((severityMap, reportIdx) => {
      const severities = severityMap.get(chapter) || [];
      const hasHighSeverity = severities.some(
        (s) => s === "Critical" || s === "Major",
      );
      const hasOnlyInfoOrNothing =
        severities.length === 0 ||
        severities.every((s) => s === "Informational");

      if (hasHighSeverity) {
        hasCriticalOrMajor.push(reportIdx);
      }
      // Only count as "nothing or info only" if the report is aware of this chapter
      // (i.e., the chapter appears in at least one report from this agent)
      if (hasOnlyInfoOrNothing && chaptersByReport[reportIdx].has(chapter)) {
        hasNothingOrInfoOnly.push(reportIdx);
      }
    });

    // If at least one report has Critical/Major AND at least one has nothing/Info
    if (hasCriticalOrMajor.length > 0 && hasNothingOrInfoOnly.length > 0) {
      // Mark the Critical/Major findings for this chapter as contradictions
      hasCriticalOrMajor.forEach((reportIdx) => {
        const severities = chapterSeveritiesByReport[reportIdx].get(chapter) || [];
        severities.forEach((severity) => {
          if (severity === "Critical" || severity === "Major") {
            const key = makeFindingKey(chapter, severity);
            // Contradiction takes precedence over consensus
            classifications.set(key, "contradiction");
          }
        });
      });
      // Also mark the Informational findings in the other reports as contradictions
      hasNothingOrInfoOnly.forEach((reportIdx) => {
        const severities = chapterSeveritiesByReport[reportIdx].get(chapter) || [];
        severities.forEach((severity) => {
          if (severity === "Informational") {
            const key = makeFindingKey(chapter, severity);
            classifications.set(key, "contradiction");
          }
        });
      });
    }
  });

  return classifications;
}

/** Create a unique key for a (chapter, severity) pair. */
export function makeFindingKey(chapter: string, severity: string): string {
  return `${chapter || "unknown"}|${severity}`;
}
