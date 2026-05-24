/**
 * AgentDetail Component
 *
 * Displays the full detail view of an agent definition including
 * personality profile, contextual tuning, evaluation rubric,
 * knowledge scopes, and system prompt.
 *
 * References:
 *   - Design doc Section 8: Frontend Components
 *   - Requirement 10.4
 */

import { ArrowLeft, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  AgentResponse,
  PersonalityProfile,
  ContextualTuning,
  EvaluationRubric,
} from "@/lib/agents-api";

interface AgentDetailProps {
  agent: AgentResponse;
  onEdit: () => void;
  onBack: () => void;
}

export function AgentDetail({ agent, onEdit, onBack }: AgentDetailProps) {
  return (
    <div className="space-y-6">
      {/* Header with back and edit buttons */}
      <div className="flex items-center justify-between">
        <Button
          variant="ghost"
          size="sm"
          onClick={onBack}
          className="gap-1"
          aria-label="Back to agent list"
        >
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Back
        </Button>
        <Button onClick={onEdit} size="sm" className="gap-1">
          <Pencil className="h-4 w-4" aria-hidden="true" />
          Edit
        </Button>
      </div>

      {/* Agent header metadata */}
      <div className="border border-border rounded-md p-4 space-y-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">{agent.name}</h2>
          {agent.archetype && (
            <span className="inline-block text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full font-medium">
              {agent.archetype}
            </span>
          )}
        </div>

        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <div>
            <dt className="text-muted-foreground">Agent Type</dt>
            <dd className="font-medium capitalize">{agent.agent_type}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Schema Version</dt>
            <dd className="font-medium">v{agent.schema_version}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-muted-foreground">Description</dt>
            <dd className="font-medium">{agent.description}</dd>
          </div>
        </dl>
      </div>

      {/* Personality Profile section */}
      {agent.personality_profile && (
        <PersonalityProfileSection profile={agent.personality_profile} />
      )}

      {/* Contextual Tuning section */}
      {agent.contextual_tuning && (
        <ContextualTuningSection tuning={agent.contextual_tuning} />
      )}

      {/* Evaluation Rubric section */}
      {agent.evaluation_rubric && (
        <EvaluationRubricSection rubric={agent.evaluation_rubric} />
      )}

      {/* Knowledge Scopes section */}
      <KnowledgeScopesSection scopes={agent.knowledge_scopes} />

      {/* System Prompt section */}
      <SystemPromptSection prompt={agent.system_prompt} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-sections
// ---------------------------------------------------------------------------

function PersonalityProfileSection({ profile }: { profile: PersonalityProfile }) {
  return (
    <section
      className="border border-border rounded-md p-4 space-y-4"
      aria-labelledby="personality-profile-heading"
    >
      <h3 id="personality-profile-heading" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Personality Profile
      </h3>

      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Tone</dt>
          <dd className="font-medium">{profile.tone}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Verbosity</dt>
          <dd className="font-medium capitalize">{profile.verbosity}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Communication Style</dt>
          <dd className="font-medium">{profile.communication_style}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Strictness</dt>
          <dd className="flex items-center gap-2">
            <StrictnessIndicator value={profile.strictness} />
            <span className="font-medium text-xs">{profile.strictness.toFixed(2)}</span>
          </dd>
        </div>
      </dl>

      {/* Domain Focus tags */}
      {profile.domain_focus.length > 0 && (
        <div className="space-y-2">
          <dt className="text-sm text-muted-foreground">Domain Focus</dt>
          <div className="flex flex-wrap gap-2" role="list" aria-label="Domain focus tags">
            {profile.domain_focus.map((tag) => (
              <span
                key={tag}
                role="listitem"
                className="inline-flex items-center text-xs px-2 py-0.5 bg-secondary text-secondary-foreground rounded-full font-medium"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

function ContextualTuningSection({ tuning }: { tuning: ContextualTuning }) {
  return (
    <section
      className="border border-border rounded-md p-4 space-y-4"
      aria-labelledby="contextual-tuning-heading"
    >
      <h3 id="contextual-tuning-heading" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Contextual Tuning
      </h3>

      <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-3 text-sm">
        <div>
          <dt className="text-muted-foreground">Temperature</dt>
          <dd className="font-medium">{tuning.temperature}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Max Tokens</dt>
          <dd className="font-medium">{tuning.max_tokens.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Top P</dt>
          <dd className="font-medium">{tuning.top_p}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Frequency Penalty</dt>
          <dd className="font-medium">{tuning.frequency_penalty}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Presence Penalty</dt>
          <dd className="font-medium">{tuning.presence_penalty}</dd>
        </div>
      </dl>
    </section>
  );
}

function EvaluationRubricSection({ rubric }: { rubric: EvaluationRubric }) {
  return (
    <section
      className="border border-border rounded-md p-4 space-y-4"
      aria-labelledby="evaluation-rubric-heading"
    >
      <h3 id="evaluation-rubric-heading" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Evaluation Rubric
      </h3>

      {/* Scoring method */}
      <div className="text-sm">
        <span className="text-muted-foreground">Scoring Method: </span>
        <span className="font-medium capitalize">
          {rubric.scoring_method.replace(/_/g, " ")}
        </span>
      </div>

      {/* Criteria list */}
      {rubric.criteria.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Criteria</h4>
          <div className="space-y-2">
            {rubric.criteria.map((criterion) => (
              <div
                key={criterion.name}
                className="border border-border/50 rounded p-3 text-sm"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">{criterion.name}</span>
                  <span className="text-xs text-muted-foreground">
                    Weight: {(criterion.weight * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-muted-foreground text-xs">
                  {criterion.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Severity thresholds */}
      {Object.keys(rubric.severity_thresholds).length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-medium">Severity Thresholds</h4>
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
            {Object.entries(rubric.severity_thresholds).map(([level, threshold]) => (
              <div key={level} className="text-center border border-border/50 rounded p-2">
                <dt className="text-xs text-muted-foreground capitalize">{level}</dt>
                <dd className="font-medium">{threshold}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </section>
  );
}

function KnowledgeScopesSection({ scopes }: { scopes: Record<string, unknown> }) {
  const tags = Array.isArray(scopes.tags) ? (scopes.tags as string[]) : [];

  return (
    <section
      className="border border-border rounded-md p-4 space-y-4"
      aria-labelledby="knowledge-scopes-heading"
    >
      <h3 id="knowledge-scopes-heading" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        Knowledge Scopes
      </h3>

      {tags.length > 0 ? (
        <div className="flex flex-wrap gap-2" role="list" aria-label="Knowledge scope tags">
          {tags.map((tag) => (
            <span
              key={tag}
              role="listitem"
              className="inline-flex items-center text-xs px-2 py-0.5 bg-primary/10 text-primary rounded-full font-medium"
            >
              {tag}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No knowledge scopes defined.</p>
      )}
    </section>
  );
}

function SystemPromptSection({ prompt }: { prompt: string }) {
  return (
    <section
      className="border border-border rounded-md p-4 space-y-4"
      aria-labelledby="system-prompt-heading"
    >
      <h3 id="system-prompt-heading" className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        System Prompt
      </h3>

      <pre className="text-sm whitespace-pre-wrap bg-muted/50 rounded p-3 max-h-64 overflow-y-auto font-mono">
        {prompt}
      </pre>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Visual indicators
// ---------------------------------------------------------------------------

/** Visual bar indicator for strictness value (0.0 to 1.0). */
function StrictnessIndicator({ value }: { value: number }) {
  const percentage = Math.round(value * 100);

  return (
    <div
      className="w-24 h-2 bg-muted rounded-full overflow-hidden"
      role="meter"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={1}
      aria-label={`Strictness: ${percentage}%`}
    >
      <div
        className="h-full bg-primary rounded-full transition-all"
        style={{ width: `${percentage}%` }}
      />
    </div>
  );
}
