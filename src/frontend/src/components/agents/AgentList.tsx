import { useCallback, useEffect, useMemo, useState } from "react";
import { Bot, Filter } from "lucide-react";
import { listAgents } from "@/lib/agents-api";
import type { AgentResponse } from "@/lib/agents-api";

// ---------------------------------------------------------------------------
// Archetype color map — unique colors per archetype for visual differentiation
// ---------------------------------------------------------------------------

const ARCHETYPE_COLORS: Record<string, { bg: string; text: string }> = {
  "Regulatory Compliance Auditor": { bg: "bg-red-100", text: "text-red-700" },
  "Data Integrity Specialist": { bg: "bg-blue-100", text: "text-blue-700" },
  "Process Safety Reviewer": { bg: "bg-orange-100", text: "text-orange-700" },
  "Statistical Methods Auditor": { bg: "bg-purple-100", text: "text-purple-700" },
  "Technical Writer": { bg: "bg-green-100", text: "text-green-700" },
  "Educational Specialist": { bg: "bg-teal-100", text: "text-teal-700" },
};

const DEFAULT_BADGE_COLORS = { bg: "bg-gray-100", text: "text-gray-700" };

// ---------------------------------------------------------------------------
// ArchetypeBadge sub-component
// ---------------------------------------------------------------------------

interface ArchetypeBadgeProps {
  archetype: string;
}

function ArchetypeBadge({ archetype }: ArchetypeBadgeProps) {
  const colors = ARCHETYPE_COLORS[archetype] ?? DEFAULT_BADGE_COLORS;

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors.bg} ${colors.text}`}
      aria-label={`Archetype: ${archetype}`}
    >
      {archetype}
    </span>
  );
}

// ---------------------------------------------------------------------------
// AgentList component
// ---------------------------------------------------------------------------

interface AgentListProps {
  /** Callback when a user clicks on an agent card */
  onSelect?: (agent: AgentResponse) => void;
}

export function AgentList({ onSelect }: AgentListProps) {
  const [agents, setAgents] = useState<AgentResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [archetypeFilter, setArchetypeFilter] = useState<string>("");

  // Derive unique archetypes from the fetched agents for the filter dropdown
  const uniqueArchetypes = useMemo(() => {
    const archetypes = agents
      .map((a) => a.archetype)
      .filter((a): a is string => a != null && a.length > 0);
    return [...new Set(archetypes)].sort();
  }, [agents]);

  // Fetch agents from the API
  const fetchAgents = useCallback(async (archetype?: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAgents(archetype || undefined);
      setAgents(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to fetch agents";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount
  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  // Re-fetch when filter changes
  const handleFilterChange = (value: string) => {
    setArchetypeFilter(value);
    fetchAgents(value || undefined);
  };

  // Loading state
  if (loading) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <Bot className="h-8 w-8 mx-auto mb-2 opacity-50 animate-pulse" aria-hidden="true" />
        <p>Loading agents…</p>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="text-center py-8 text-destructive">
        <p>Error: {error}</p>
        <button
          type="button"
          onClick={() => fetchAgents(archetypeFilter || undefined)}
          className="mt-2 text-sm underline hover:no-underline"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filter dropdown */}
      <div className="flex items-center gap-2" role="search" aria-label="Agent filters">
        <Filter className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
        <label htmlFor="archetype-filter" className="sr-only">
          Filter by archetype
        </label>
        <select
          id="archetype-filter"
          value={archetypeFilter}
          onChange={(e) => handleFilterChange(e.target.value)}
          className="flex h-9 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          aria-label="Filter agents by archetype"
        >
          <option value="">All archetypes</option>
          {uniqueArchetypes.map((archetype) => (
            <option key={archetype} value={archetype}>
              {archetype}
            </option>
          ))}
        </select>
      </div>

      {/* Agent list */}
      {agents.length === 0 ? (
        <div className="text-center py-8 text-muted-foreground">
          <Bot className="h-8 w-8 mx-auto mb-2 opacity-50" aria-hidden="true" />
          <p>No agents found</p>
        </div>
      ) : (
        <div className="space-y-2" role="list" aria-label="Agent list">
          {agents.map((agent) => (
            <div
              key={agent.id}
              role="listitem"
              className="rounded-lg border border-border p-4 transition-colors hover:bg-accent/50 cursor-pointer"
              onClick={() => onSelect?.(agent)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect?.(agent);
                }
              }}
              tabIndex={0}
              aria-label={`Agent: ${agent.name}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <h3 className="text-sm font-medium leading-tight">{agent.name}</h3>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Type: {agent.agent_type}
                  </p>
                  {agent.personality_profile && (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      <span>Tone: {agent.personality_profile.tone}</span>
                      <span className="text-border">•</span>
                      <span>Verbosity: {agent.personality_profile.verbosity}</span>
                      <span className="text-border">•</span>
                      <span>Strictness: {agent.personality_profile.strictness.toFixed(2)}</span>
                    </div>
                  )}
                </div>
                <div className="shrink-0">
                  {agent.archetype && <ArchetypeBadge archetype={agent.archetype} />}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
