import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/apiClient";
import {
  listArchetypes,
  createAgent,
  updateAgent,
  createFromArchetype,
} from "@/lib/agents-api";
import type {
  AgentResponse,
  AgentCreateRequest,
  ArchetypeDefinition,
  PersonalityProfile,
  ContextualTuning,
} from "@/lib/agents-api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AgentFormProps {
  /** If provided, the form is in edit mode and pre-populates fields */
  agent?: AgentResponse;
  /** Called with the created/updated agent on success */
  onSuccess: (agent: AgentResponse) => void;
  /** Called when the user cancels the form */
  onCancel: () => void;
}

interface FormState {
  name: string;
  description: string;
  archetype: string;
  agent_type: "generation" | "review";
  system_prompt: string;
  // Personality Profile
  tone: string;
  verbosity: "concise" | "moderate" | "detailed";
  strictness: number;
  domain_focus: string;
  communication_style: string;
  // Contextual Tuning
  temperature: number;
  max_tokens: number;
  top_p: number;
  frequency_penalty: number;
  presence_penalty: number;
  // Change reason
  change_reason: string;
}

interface ApiErrorDetail {
  status: number;
  message: string;
  errors?: string[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const VERBOSITY_OPTIONS: { value: PersonalityProfile["verbosity"]; label: string }[] = [
  { value: "concise", label: "Concise" },
  { value: "moderate", label: "Moderate" },
  { value: "detailed", label: "Detailed" },
];

const AGENT_TYPE_OPTIONS: { value: "generation" | "review"; label: string }[] = [
  { value: "generation", label: "Generation" },
  { value: "review", label: "Review" },
];

const DEFAULT_FORM_STATE: FormState = {
  name: "",
  description: "",
  archetype: "",
  agent_type: "generation",
  system_prompt: "",
  tone: "",
  verbosity: "moderate",
  strictness: 0.5,
  domain_focus: "",
  communication_style: "",
  temperature: 0.3,
  max_tokens: 4096,
  top_p: 1.0,
  frequency_penalty: 0.0,
  presence_penalty: 0.0,
  change_reason: "",
};

// ---------------------------------------------------------------------------
// Helper: parse API error body
// ---------------------------------------------------------------------------

function parseApiError(err: unknown): ApiErrorDetail {
  if (err instanceof ApiError) {
    try {
      const parsed = JSON.parse(err.body);
      const errors: string[] = [];
      if (parsed.errors && Array.isArray(parsed.errors)) {
        errors.push(...parsed.errors.map((e: unknown) => String(e)));
      }
      if (parsed.detail && typeof parsed.detail === "string") {
        return { status: err.status, message: parsed.detail, errors };
      }
      return { status: err.status, message: parsed.detail ?? err.message, errors };
    } catch {
      return { status: err.status, message: err.body || err.message };
    }
  }
  if (err instanceof Error) {
    return { status: 0, message: err.message };
  }
  return { status: 0, message: "An unexpected error occurred" };
}

// ---------------------------------------------------------------------------
// Slider sub-component
// ---------------------------------------------------------------------------

interface SliderFieldProps {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}

function SliderField({ id, label, value, min, max, step, onChange }: SliderFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-sm font-medium text-gray-700">
          {label}
        </label>
        <span className="text-xs text-muted-foreground tabular-nums">
          {value.toFixed(step < 1 ? 2 : 0)}
        </span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-2 rounded-lg appearance-none cursor-pointer bg-gray-200 accent-primary"
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
      />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AgentForm component
// ---------------------------------------------------------------------------

export function AgentForm({ agent, onSuccess, onCancel }: AgentFormProps) {
  const isEditMode = !!agent;

  const [form, setForm] = useState<FormState>(() => {
    if (agent) {
      return {
        name: agent.name,
        description: agent.description,
        archetype: agent.archetype ?? "",
        agent_type: agent.agent_type as "generation" | "review",
        system_prompt: agent.system_prompt,
        tone: agent.personality_profile?.tone ?? "",
        verbosity: agent.personality_profile?.verbosity ?? "moderate",
        strictness: agent.personality_profile?.strictness ?? 0.5,
        domain_focus: agent.personality_profile?.domain_focus?.join(", ") ?? "",
        communication_style: agent.personality_profile?.communication_style ?? "",
        temperature: agent.contextual_tuning?.temperature ?? 0.3,
        max_tokens: agent.contextual_tuning?.max_tokens ?? 4096,
        top_p: agent.contextual_tuning?.top_p ?? 1.0,
        frequency_penalty: agent.contextual_tuning?.frequency_penalty ?? 0.0,
        presence_penalty: agent.contextual_tuning?.presence_penalty ?? 0.0,
        change_reason: "",
      };
    }
    return { ...DEFAULT_FORM_STATE };
  });

  const [archetypes, setArchetypes] = useState<ArchetypeDefinition[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [apiError, setApiError] = useState<ApiErrorDetail | null>(null);

  // Fetch archetypes on mount
  useEffect(() => {
    let cancelled = false;
    listArchetypes()
      .then((data) => {
        if (!cancelled) setArchetypes(data);
      })
      .catch(() => {
        // Non-critical: archetypes just won't be available for selection
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Update a single form field
  const setField = useCallback(<K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  }, []);

  // Handle archetype selection — populate defaults from archetype
  const handleArchetypeChange = useCallback(
    (archetypeId: string) => {
      setField("archetype", archetypeId);

      if (!archetypeId) return;

      const selected = archetypes.find((a) => a.archetype === archetypeId);
      if (!selected) return;

      // Populate personality_profile defaults
      setForm((prev) => ({
        ...prev,
        archetype: archetypeId,
        tone: selected.personality_profile.tone,
        verbosity: selected.personality_profile.verbosity,
        strictness: selected.personality_profile.strictness,
        domain_focus: selected.personality_profile.domain_focus.join(", "),
        communication_style: selected.personality_profile.communication_style,
        // Populate contextual_tuning defaults
        temperature: selected.contextual_tuning.temperature,
        max_tokens: selected.contextual_tuning.max_tokens,
        top_p: selected.contextual_tuning.top_p,
        frequency_penalty: selected.contextual_tuning.frequency_penalty,
        presence_penalty: selected.contextual_tuning.presence_penalty,
        // Populate other fields from archetype
        system_prompt: prev.system_prompt || selected.system_prompt,
        agent_type: (selected.agent_type as "generation" | "review") || prev.agent_type,
      }));
    },
    [archetypes, setField]
  );

  // Build the request payload
  const buildPayload = (): AgentCreateRequest => {
    const personalityProfile: PersonalityProfile = {
      tone: form.tone,
      verbosity: form.verbosity,
      strictness: form.strictness,
      domain_focus: form.domain_focus
        .split(",")
        .map((s) => s.trim())
        .filter((s) => s.length > 0),
      communication_style: form.communication_style,
    };

    const contextualTuning: ContextualTuning = {
      temperature: form.temperature,
      max_tokens: form.max_tokens,
      top_p: form.top_p,
      frequency_penalty: form.frequency_penalty,
      presence_penalty: form.presence_penalty,
    };

    return {
      schema_version: "2.0",
      name: form.name,
      description: form.description,
      agent_type: form.agent_type,
      archetype: form.archetype || null,
      system_prompt: form.system_prompt,
      dspy_modules: [],
      knowledge_scopes: {},
      personality_profile: personalityProfile,
      contextual_tuning: contextualTuning,
    };
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);
    setSubmitting(true);

    try {
      let result: AgentResponse;

      if (isEditMode) {
        // Update existing agent
        result = await updateAgent(agent.id, buildPayload(), form.change_reason);
      } else if (form.archetype) {
        // Create from archetype
        result = await createFromArchetype(
          {
            archetype: form.archetype,
            name: form.name,
            description: form.description || null,
            personality_profile: {
              tone: form.tone,
              verbosity: form.verbosity,
              strictness: form.strictness,
              domain_focus: form.domain_focus
                .split(",")
                .map((s) => s.trim())
                .filter((s) => s.length > 0),
              communication_style: form.communication_style,
            },
            contextual_tuning: {
              temperature: form.temperature,
              max_tokens: form.max_tokens,
              top_p: form.top_p,
              frequency_penalty: form.frequency_penalty,
              presence_penalty: form.presence_penalty,
            },
          },
          form.change_reason
        );
      } else {
        // Create new agent directly
        result = await createAgent(buildPayload(), form.change_reason);
      }

      onSuccess(result);
    } catch (err) {
      const parsed = parseApiError(err);
      // Only display 422 and 409 inline; re-throw others
      if (parsed.status === 422 || parsed.status === 409) {
        setApiError(parsed);
      } else {
        setApiError(parsed);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const isSubmitDisabled = submitting || form.change_reason.trim().length < 1;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* API Error Display */}
      {apiError && (
        <div
          className="rounded-md border border-destructive/50 bg-destructive/10 p-4"
          role="alert"
          aria-live="polite"
        >
          <p className="text-sm font-medium text-destructive">
            Error ({apiError.status}): {apiError.message}
          </p>
          {apiError.errors && apiError.errors.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-destructive">
              {apiError.errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Basic Information */}
      <fieldset className="space-y-4 rounded-lg border border-border p-4">
        <legend className="px-2 text-sm font-semibold text-gray-700">
          Basic Information
        </legend>

        {/* Name */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-name" className="text-sm font-medium text-gray-700">
            Name <span className="text-red-500">*</span>
          </label>
          <input
            id="agent-name"
            type="text"
            value={form.name}
            onChange={(e) => setField("name", e.target.value)}
            required
            placeholder="Enter agent name"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* Description */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-description" className="text-sm font-medium text-gray-700">
            Description <span className="text-red-500">*</span>
          </label>
          <textarea
            id="agent-description"
            value={form.description}
            onChange={(e) => setField("description", e.target.value)}
            required
            rows={3}
            placeholder="Describe the agent's purpose"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* Archetype Selector */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-archetype" className="text-sm font-medium text-gray-700">
            Archetype
          </label>
          <select
            id="agent-archetype"
            value={form.archetype}
            onChange={(e) => handleArchetypeChange(e.target.value)}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            <option value="">None (custom agent)</option>
            {archetypes.map((arch) => (
              <option key={arch.archetype} value={arch.archetype}>
                {arch.name}
              </option>
            ))}
          </select>
        </div>

        {/* Agent Type */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-type" className="text-sm font-medium text-gray-700">
            Agent Type
          </label>
          <select
            id="agent-type"
            value={form.agent_type}
            onChange={(e) => setField("agent_type", e.target.value as "generation" | "review")}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {AGENT_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* System Prompt */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-system-prompt" className="text-sm font-medium text-gray-700">
            System Prompt <span className="text-red-500">*</span>
          </label>
          <textarea
            id="agent-system-prompt"
            value={form.system_prompt}
            onChange={(e) => setField("system_prompt", e.target.value)}
            required
            rows={5}
            placeholder="Enter the system prompt for this agent"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </fieldset>

      {/* Personality Profile */}
      <fieldset className="space-y-4 rounded-lg border border-border p-4">
        <legend className="px-2 text-sm font-semibold text-gray-700">
          Personality Profile
        </legend>

        {/* Tone */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-tone" className="text-sm font-medium text-gray-700">
            Tone
          </label>
          <input
            id="agent-tone"
            type="text"
            value={form.tone}
            onChange={(e) => setField("tone", e.target.value)}
            placeholder="e.g., formal and precise"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        {/* Verbosity */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-verbosity" className="text-sm font-medium text-gray-700">
            Verbosity
          </label>
          <select
            id="agent-verbosity"
            value={form.verbosity}
            onChange={(e) =>
              setField("verbosity", e.target.value as PersonalityProfile["verbosity"])
            }
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {VERBOSITY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Strictness Slider */}
        <SliderField
          id="agent-strictness"
          label="Strictness"
          value={form.strictness}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => setField("strictness", v)}
        />

        {/* Domain Focus (tag input as comma-separated) */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-domain-focus" className="text-sm font-medium text-gray-700">
            Domain Focus
          </label>
          <input
            id="agent-domain-focus"
            type="text"
            value={form.domain_focus}
            onChange={(e) => setField("domain_focus", e.target.value)}
            placeholder="e.g., regulatory, compliance, GxP (comma-separated)"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground">Separate tags with commas</p>
        </div>

        {/* Communication Style */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-communication-style" className="text-sm font-medium text-gray-700">
            Communication Style
          </label>
          <input
            id="agent-communication-style"
            type="text"
            value={form.communication_style}
            onChange={(e) => setField("communication_style", e.target.value)}
            placeholder="e.g., structured findings with regulatory citations"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </fieldset>

      {/* Contextual Tuning */}
      <fieldset className="space-y-4 rounded-lg border border-border p-4">
        <legend className="px-2 text-sm font-semibold text-gray-700">
          Contextual Tuning
        </legend>

        {/* Temperature Slider */}
        <SliderField
          id="agent-temperature"
          label="Temperature"
          value={form.temperature}
          min={0}
          max={2}
          step={0.01}
          onChange={(v) => setField("temperature", v)}
        />

        {/* Max Tokens */}
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-max-tokens" className="text-sm font-medium text-gray-700">
            Max Tokens
          </label>
          <input
            id="agent-max-tokens"
            type="number"
            value={form.max_tokens}
            onChange={(e) => setField("max_tokens", Math.max(1, parseInt(e.target.value) || 1))}
            min={1}
            max={131072}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <p className="text-xs text-muted-foreground">Range: 1 – 131,072</p>
        </div>

        {/* Top P Slider */}
        <SliderField
          id="agent-top-p"
          label="Top P"
          value={form.top_p}
          min={0}
          max={1}
          step={0.01}
          onChange={(v) => setField("top_p", v)}
        />

        {/* Frequency Penalty Slider */}
        <SliderField
          id="agent-frequency-penalty"
          label="Frequency Penalty"
          value={form.frequency_penalty}
          min={-2}
          max={2}
          step={0.01}
          onChange={(v) => setField("frequency_penalty", v)}
        />

        {/* Presence Penalty Slider */}
        <SliderField
          id="agent-presence-penalty"
          label="Presence Penalty"
          value={form.presence_penalty}
          min={-2}
          max={2}
          step={0.01}
          onChange={(v) => setField("presence_penalty", v)}
        />
      </fieldset>

      {/* Change Reason */}
      <fieldset className="space-y-2 rounded-lg border border-border p-4">
        <legend className="px-2 text-sm font-semibold text-gray-700">
          Audit Compliance
        </legend>
        <div className="flex flex-col gap-1">
          <label htmlFor="agent-change-reason" className="text-sm font-medium text-gray-700">
            Change Reason <span className="text-red-500">*</span>
          </label>
          <input
            id="agent-change-reason"
            type="text"
            value={form.change_reason}
            onChange={(e) => setField("change_reason", e.target.value)}
            required
            minLength={1}
            placeholder="Describe the reason for this change (ALCOA+ compliance)"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            aria-required="true"
            aria-describedby="change-reason-help"
          />
          <p id="change-reason-help" className="text-xs text-muted-foreground">
            Required for audit trail. Minimum 1 character.
          </p>
        </div>
      </fieldset>

      {/* Form Actions */}
      <div className="flex justify-end gap-3">
        <Button type="button" variant="outline" onClick={onCancel} disabled={submitting}>
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitDisabled}>
          {submitting
            ? "Saving…"
            : isEditMode
              ? "Update Agent"
              : "Create Agent"}
        </Button>
      </div>
    </form>
  );
}
