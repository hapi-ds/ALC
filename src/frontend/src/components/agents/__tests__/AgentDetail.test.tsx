import { describe, it, expect, vi, afterEach } from "vitest";
import "@testing-library/jest-dom/vitest";
import { render, screen, cleanup } from "@testing-library/react";
import { AgentDetail } from "../AgentDetail";
import type { AgentResponse } from "@/lib/agents-api";

/**
 * Unit tests for AgentDetail component.
 *
 * Tests: header rendering, personality profile display, contextual tuning display,
 * evaluation rubric display, knowledge scopes tags, system prompt display,
 * back/edit button callbacks.
 *
 * Validates: Requirement 10.4
 */

afterEach(() => {
  cleanup();
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockAgent: AgentResponse = {
  id: 1,
  schema_version: "2.0",
  name: "Environmental Impact Auditor",
  description: "Reviews environmental impact assessments for regulatory compliance",
  agent_type: "review",
  archetype: "Regulatory Compliance Auditor",
  personality_profile: {
    tone: "formal and precise",
    verbosity: "detailed",
    strictness: 0.9,
    domain_focus: ["environmental", "regulatory", "compliance"],
    communication_style: "structured findings with regulatory citations",
  },
  contextual_tuning: {
    temperature: 0.1,
    max_tokens: 8192,
    top_p: 0.95,
    frequency_penalty: 0.1,
    presence_penalty: 0.0,
  },
  evaluation_rubric: {
    criteria: [
      {
        name: "Regulatory Coverage",
        weight: 0.4,
        description: "All applicable regulations are addressed",
      },
      {
        name: "Data Completeness",
        weight: 0.3,
        description: "Supporting data and measurements are present",
      },
    ],
    severity_thresholds: {
      critical: 0.9,
      major: 0.7,
      minor: 0.4,
      informational: 0.2,
    },
    scoring_method: "weighted_average",
  },
  system_prompt: "You are an environmental compliance auditor...",
  dspy_modules: [{ name: "analyze", type: "ChainOfThought" }],
  knowledge_scopes: { tags: ["Environmental", "Compliance", "Assessment"] },
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-02T00:00:00Z",
};

const mockAgentMinimal: AgentResponse = {
  id: 2,
  schema_version: "1.0",
  name: "Simple Agent",
  description: "A basic agent without v2.0 fields",
  agent_type: "generation",
  archetype: null,
  personality_profile: null,
  contextual_tuning: null,
  evaluation_rubric: null,
  system_prompt: "You are a helpful assistant.",
  dspy_modules: [],
  knowledge_scopes: {},
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: null,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AgentDetail", () => {
  it("renders agent header with name, archetype badge, type, and description", () => {
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.getByText("Environmental Impact Auditor")).toBeInTheDocument();
    expect(screen.getByText("Regulatory Compliance Auditor")).toBeInTheDocument();
    expect(screen.getByText("review")).toBeInTheDocument();
    expect(screen.getByText("v2.0")).toBeInTheDocument();
    expect(
      screen.getByText("Reviews environmental impact assessments for regulatory compliance")
    ).toBeInTheDocument();
  });

  it("renders personality profile section with all fields", () => {
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.getByText("Personality Profile")).toBeInTheDocument();
    expect(screen.getByText("formal and precise")).toBeInTheDocument();
    expect(screen.getByText("detailed")).toBeInTheDocument();
    expect(screen.getByText("structured findings with regulatory citations")).toBeInTheDocument();
    expect(screen.getByText("0.90")).toBeInTheDocument();
    // Domain focus tags
    expect(screen.getByText("environmental")).toBeInTheDocument();
    expect(screen.getByText("regulatory")).toBeInTheDocument();
    expect(screen.getByText("compliance")).toBeInTheDocument();
  });

  it("renders contextual tuning section with all parameters", () => {
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.getByText("Contextual Tuning")).toBeInTheDocument();
    // Temperature and frequency_penalty are both 0.1, so multiple matches expected
    expect(screen.getAllByText("0.1")).toHaveLength(2);
    expect(screen.getByText("8,192")).toBeInTheDocument();
    expect(screen.getByText("0.95")).toBeInTheDocument();
  });

  it("renders evaluation rubric section with criteria and thresholds", () => {
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.getByText("Evaluation Rubric")).toBeInTheDocument();
    expect(screen.getByText("weighted average")).toBeInTheDocument();
    expect(screen.getByText("Regulatory Coverage")).toBeInTheDocument();
    expect(screen.getByText("Weight: 40%")).toBeInTheDocument();
    expect(screen.getByText("Data Completeness")).toBeInTheDocument();
    expect(screen.getByText("Weight: 30%")).toBeInTheDocument();
    // Severity thresholds
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("major")).toBeInTheDocument();
  });

  it("renders knowledge scopes tags", () => {
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.getByText("Knowledge Scopes")).toBeInTheDocument();
    expect(screen.getByText("Environmental")).toBeInTheDocument();
    expect(screen.getByText("Compliance")).toBeInTheDocument();
    expect(screen.getByText("Assessment")).toBeInTheDocument();
  });

  it("renders system prompt section", () => {
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.getByText("System Prompt")).toBeInTheDocument();
    expect(
      screen.getByText("You are an environmental compliance auditor...")
    ).toBeInTheDocument();
  });

  it("calls onBack when Back button is clicked", () => {
    const onBack = vi.fn();
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={onBack} />);

    screen.getByRole("button", { name: /back to agent list/i }).click();
    expect(onBack).toHaveBeenCalledOnce();
  });

  it("calls onEdit when Edit button is clicked", () => {
    const onEdit = vi.fn();
    render(<AgentDetail agent={mockAgent} onEdit={onEdit} onBack={vi.fn()} />);

    // The Edit button contains both icon and text "Edit"
    const editButtons = screen.getAllByRole("button");
    const editButton = editButtons.find((btn) => btn.textContent?.includes("Edit"));
    editButton!.click();
    expect(onEdit).toHaveBeenCalledOnce();
  });

  it("does not render optional sections when fields are null", () => {
    render(<AgentDetail agent={mockAgentMinimal} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.getByText("Simple Agent")).toBeInTheDocument();
    expect(screen.queryByText("Personality Profile")).not.toBeInTheDocument();
    expect(screen.queryByText("Contextual Tuning")).not.toBeInTheDocument();
    expect(screen.queryByText("Evaluation Rubric")).not.toBeInTheDocument();
    // Knowledge scopes section still renders but shows empty message
    expect(screen.getByText("Knowledge Scopes")).toBeInTheDocument();
    expect(screen.getByText("No knowledge scopes defined.")).toBeInTheDocument();
  });

  it("does not render archetype badge when archetype is null", () => {
    render(<AgentDetail agent={mockAgentMinimal} onEdit={vi.fn()} onBack={vi.fn()} />);

    expect(screen.queryByText("Regulatory Compliance Auditor")).not.toBeInTheDocument();
  });

  it("renders strictness indicator with correct aria attributes", () => {
    render(<AgentDetail agent={mockAgent} onEdit={vi.fn()} onBack={vi.fn()} />);

    const meter = screen.getByRole("meter", { name: /strictness: 90%/i });
    expect(meter).toBeInTheDocument();
    expect(meter).toHaveAttribute("aria-valuenow", "0.9");
    expect(meter).toHaveAttribute("aria-valuemin", "0");
    expect(meter).toHaveAttribute("aria-valuemax", "1");
  });
});
