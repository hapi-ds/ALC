import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import React from "react";

/**
 * Unit tests for AgentList component
 *
 * Tests: agent card rendering, archetype badges with colors, filter dropdown,
 * loading/error/empty states, onSelect callback, personality summary display.
 *
 * Validates: Requirements 10.1, 10.8, 10.9
 */

// Mock the agents-api module
vi.mock("@/lib/agents-api", () => ({
  listAgents: vi.fn(),
}));

import { listAgents } from "@/lib/agents-api";
import type { AgentResponse } from "@/lib/agents-api";
import { AgentList } from "../AgentList";

const mockListAgents = vi.mocked(listAgents);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockAgent(overrides: Partial<AgentResponse> = {}): AgentResponse {
  return {
    id: 1,
    schema_version: "2.0",
    name: "Test Agent",
    description: "A test agent",
    agent_type: "review",
    archetype: "Regulatory Compliance Auditor",
    personality_profile: {
      tone: "formal and precise",
      verbosity: "detailed",
      strictness: 0.9,
      domain_focus: ["regulatory"],
      communication_style: "structured",
    },
    contextual_tuning: null,
    evaluation_rubric: null,
    system_prompt: "You are a test agent",
    dspy_modules: [],
    knowledge_scopes: {},
    is_active: true,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: null,
    ...overrides,
  };
}

const mockAgents: AgentResponse[] = [
  createMockAgent({
    id: 1,
    name: "Compliance Agent",
    archetype: "Regulatory Compliance Auditor",
    agent_type: "review",
    personality_profile: {
      tone: "formal and precise",
      verbosity: "detailed",
      strictness: 0.9,
      domain_focus: ["regulatory"],
      communication_style: "structured",
    },
  }),
  createMockAgent({
    id: 2,
    name: "Writer Agent",
    archetype: "Technical Writer",
    agent_type: "generation",
    personality_profile: {
      tone: "clear and helpful",
      verbosity: "detailed",
      strictness: 0.5,
      domain_focus: ["documentation"],
      communication_style: "instructive",
    },
  }),
  createMockAgent({
    id: 3,
    name: "Education Agent",
    archetype: "Educational Specialist",
    agent_type: "generation",
    personality_profile: {
      tone: "encouraging",
      verbosity: "moderate",
      strictness: 0.3,
      domain_focus: ["training"],
      communication_style: "conversational",
    },
  }),
];

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AgentList", () => {
  beforeEach(() => {
    mockListAgents.mockResolvedValue(mockAgents);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // 1. Loading state
  // -------------------------------------------------------------------------
  it("shows loading state initially", () => {
    // Never resolve to keep loading state
    mockListAgents.mockReturnValue(new Promise(() => {}));

    render(<AgentList />);

    expect(screen.getByText("Loading agents…")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 2. Renders agent cards
  // -------------------------------------------------------------------------
  it("renders agent cards with name, type, and personality summary", async () => {
    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Compliance Agent")).toBeInTheDocument();
    });

    expect(screen.getByText("Writer Agent")).toBeInTheDocument();
    expect(screen.getByText("Education Agent")).toBeInTheDocument();

    // Agent type (first agent is review)
    expect(screen.getByText("Type: review")).toBeInTheDocument();

    // Personality summary for first agent
    expect(screen.getByText("Tone: formal and precise")).toBeInTheDocument();
    expect(screen.getByText("Strictness: 0.90")).toBeInTheDocument();

    // Verify multiple verbosity values rendered
    expect(screen.getAllByText("Verbosity: detailed")).toHaveLength(2);
    expect(screen.getByText("Verbosity: moderate")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 3. Archetype badges with unique colors
  // -------------------------------------------------------------------------
  it("renders archetype badges with unique colors per archetype", async () => {
    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Compliance Agent")).toBeInTheDocument();
    });

    const complianceBadge = screen.getByLabelText("Archetype: Regulatory Compliance Auditor");
    expect(complianceBadge.className).toContain("bg-red-100");
    expect(complianceBadge.className).toContain("text-red-700");

    const writerBadge = screen.getByLabelText("Archetype: Technical Writer");
    expect(writerBadge.className).toContain("bg-green-100");
    expect(writerBadge.className).toContain("text-green-700");

    const educationBadge = screen.getByLabelText("Archetype: Educational Specialist");
    expect(educationBadge.className).toContain("bg-teal-100");
    expect(educationBadge.className).toContain("text-teal-700");
  });

  // -------------------------------------------------------------------------
  // 4. Filter dropdown populated with unique archetypes
  // -------------------------------------------------------------------------
  it("populates filter dropdown with unique archetypes from agents", async () => {
    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Compliance Agent")).toBeInTheDocument();
    });

    const select = screen.getByLabelText("Filter agents by archetype") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.textContent);

    expect(options).toContain("All archetypes");
    expect(options).toContain("Educational Specialist");
    expect(options).toContain("Regulatory Compliance Auditor");
    expect(options).toContain("Technical Writer");
  });

  // -------------------------------------------------------------------------
  // 5. Filter triggers re-fetch with archetype parameter
  // -------------------------------------------------------------------------
  it("re-fetches agents with archetype parameter when filter changes", async () => {
    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Compliance Agent")).toBeInTheDocument();
    });

    // Initial fetch without filter
    expect(mockListAgents).toHaveBeenCalledWith(undefined);

    const select = screen.getByLabelText("Filter agents by archetype");
    fireEvent.change(select, { target: { value: "Technical Writer" } });

    await waitFor(() => {
      expect(mockListAgents).toHaveBeenCalledWith("Technical Writer");
    });
  });

  // -------------------------------------------------------------------------
  // 6. onSelect callback
  // -------------------------------------------------------------------------
  it("calls onSelect when an agent card is clicked", async () => {
    const onSelect = vi.fn();
    render(<AgentList onSelect={onSelect} />);

    await waitFor(() => {
      expect(screen.getByText("Compliance Agent")).toBeInTheDocument();
    });

    const card = screen.getByLabelText("Agent: Compliance Agent");
    fireEvent.click(card);

    expect(onSelect).toHaveBeenCalledWith(mockAgents[0]);
  });

  it("calls onSelect on Enter key press", async () => {
    const onSelect = vi.fn();
    render(<AgentList onSelect={onSelect} />);

    await waitFor(() => {
      expect(screen.getByText("Writer Agent")).toBeInTheDocument();
    });

    const card = screen.getByLabelText("Agent: Writer Agent");
    fireEvent.keyDown(card, { key: "Enter" });

    expect(onSelect).toHaveBeenCalledWith(mockAgents[1]);
  });

  // -------------------------------------------------------------------------
  // 7. Empty state
  // -------------------------------------------------------------------------
  it("shows empty state when no agents are returned", async () => {
    mockListAgents.mockResolvedValue([]);

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("No agents found")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 8. Error state
  // -------------------------------------------------------------------------
  it("shows error state when API call fails", async () => {
    mockListAgents.mockRejectedValue(new Error("Network error"));

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Error: Network error")).toBeInTheDocument();
    });
  });

  it("retries fetch when retry button is clicked", async () => {
    mockListAgents.mockRejectedValueOnce(new Error("Network error"));

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Error: Network error")).toBeInTheDocument();
    });

    // Now make it succeed on retry
    mockListAgents.mockResolvedValue(mockAgents);

    const retryButton = screen.getByText("Retry");
    fireEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText("Compliance Agent")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // 9. Agent without personality profile
  // -------------------------------------------------------------------------
  it("renders agent card without personality summary when profile is null", async () => {
    mockListAgents.mockResolvedValue([
      createMockAgent({ id: 10, name: "Basic Agent", personality_profile: null }),
    ]);

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Basic Agent")).toBeInTheDocument();
    });

    // Should not show personality fields
    expect(screen.queryByText(/Tone:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Verbosity:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Strictness:/)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 10. Agent without archetype
  // -------------------------------------------------------------------------
  it("does not render archetype badge when archetype is null", async () => {
    mockListAgents.mockResolvedValue([
      createMockAgent({ id: 11, name: "No Archetype Agent", archetype: null }),
    ]);

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("No Archetype Agent")).toBeInTheDocument();
    });

    expect(screen.queryByLabelText(/Archetype:/)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // 11. Accessibility - list role
  // -------------------------------------------------------------------------
  it("renders with proper list role and aria-label", async () => {
    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText("Compliance Agent")).toBeInTheDocument();
    });

    expect(screen.getByRole("list", { name: "Agent list" })).toBeInTheDocument();
  });
});
