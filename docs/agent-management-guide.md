# Agent Management User Guide

This guide explains how to use the Modular Agent Registry and Personality Framework in AlcoaBase. It covers browsing agents, creating agents from archetypes, customizing personality profiles and tuning parameters, and managing agent definitions through the UI and API.

## Overview

AlcoaBase's Agent Registry provides a fleet of configurable AI agents for document generation and review. Each agent has:

- An **archetype** — a role category (e.g., "Regulatory Compliance Auditor") with sensible defaults
- A **personality profile** — behavioral parameters like tone, verbosity, and strictness
- **Contextual tuning** — LLM inference parameters (temperature, max_tokens, etc.)
- An optional **evaluation rubric** — scoring criteria for document assessment

Agents can be created from predefined archetypes with optional customizations, or built from scratch. All changes are audited with mandatory change reasons.

## Accessing the Agents Page

Navigate to **Agents** from the main navigation. The page displays your company's active agents as cards showing name, archetype badge, agent type, and a personality summary.

## Browsing Agents

### Agent List

The list view shows all active agents for your company. Each card displays:

- **Name** — the agent's display name
- **Archetype badge** — color-coded by role (red for Regulatory Compliance Auditor, blue for Data Integrity Specialist, orange for Process Safety Reviewer, purple for Statistical Methods Auditor, green for Technical Writer, teal for Educational Specialist)
- **Agent type** — "generation" or "review"
- **Personality summary** — tone, verbosity level, and strictness score

### Filtering by Archetype

Use the filter dropdown above the list to show only agents of a specific archetype. Select "All archetypes" to reset the filter.

### Viewing Agent Details

Click any agent card to see its full configuration:

- **Header** — name, archetype, type, schema version, description
- **Personality Profile** — tone, verbosity, strictness (with visual indicator), domain focus tags, communication style
- **Contextual Tuning** — temperature, max tokens, top_p, frequency penalty, presence penalty
- **Evaluation Rubric** (if defined) — criteria with weights, severity thresholds, scoring method
- **Knowledge Scopes** — document tags the agent uses for retrieval
- **System Prompt** — the full prompt text

## Creating Agents

### From an Archetype (Recommended)

1. Click **"New Agent"** on the list view.
2. Select an archetype from the dropdown. The form auto-populates with the archetype's default personality profile and tuning parameters.
3. Enter a **name** and **description** for your agent.
4. Adjust any personality or tuning values using the sliders and inputs.
5. Enter a **change reason** (required for audit compliance).
6. Click **"Create Agent"**.

The six predefined archetypes are:

| Archetype | Strictness | Temperature | Verbosity | Best For |
|-----------|-----------|-------------|-----------|----------|
| Regulatory Compliance Auditor | 0.90 | 0.1 | Detailed | FDA/EMA/ICH compliance reviews |
| Data Integrity Specialist | 0.85 | 0.15 | Detailed | ALCOA+ and CSV assessments |
| Process Safety Reviewer | 0.95 | 0.1 | Detailed | Hazard analysis and safety reviews |
| Statistical Methods Auditor | 0.80 | 0.2 | Moderate | Validation protocols and sampling plans |
| Technical Writer | 0.50 | 0.4 | Detailed | SOP drafting and documentation |
| Educational Specialist | 0.30 | 0.6 | Moderate | Training materials and assessments |

### From Scratch

1. Click **"New Agent"** and leave the archetype selector as "None (custom agent)".
2. Fill in all required fields: name, description, system prompt.
3. Configure personality profile and tuning parameters manually.
4. Enter a change reason and submit.

## Editing Agents

1. Click an agent card to open the detail view.
2. Click **"Edit"** in the top-right corner.
3. Modify any fields. The form preserves the current values.
4. Enter a change reason explaining the modification.
5. Click **"Update Agent"**.

## Personality Profile Parameters

| Parameter | Range | Description |
|-----------|-------|-------------|
| Tone | Free text (max 100 chars) | Communication style descriptor (e.g., "formal and precise") |
| Verbosity | concise / moderate / detailed | Level of detail in responses |
| Strictness | 0.0 – 1.0 | How strictly the agent enforces rules (slider) |
| Domain Focus | Comma-separated tags (max 20) | Areas of expertise |
| Communication Style | Free text (max 200 chars) | How findings are structured |

## Contextual Tuning Parameters

| Parameter | Range | Default | Description |
|-----------|-------|---------|-------------|
| Temperature | 0.0 – 2.0 | 0.3 | Sampling randomness (lower = more deterministic) |
| Max Tokens | 1 – 131,072 | 4,096 | Maximum response length |
| Top P | 0.0 – 1.0 | 1.0 | Nucleus sampling threshold |
| Frequency Penalty | -2.0 – 2.0 | 0.0 | Penalizes repeated tokens |
| Presence Penalty | -2.0 – 2.0 | 0.0 | Encourages topic diversity |

## Hot-Reload (Admin)

System administrators can add or modify agents by placing YAML files in the `agents/examples/` directory. The system watches for changes and automatically loads new definitions within 30 seconds.

To trigger an immediate rescan, use the reload API endpoint:

```bash
curl -X POST http://localhost:8080/api/agents/reload \
  -H "X-Company-Id: 1" \
  -H "X-User-Id: 1" \
  -H "X-Change-Reason: Manual directory rescan"
```

The response includes a summary of loaded, updated, and deactivated agents.

## YAML Agent Definition Format

Agent definitions use schema v2.0:

```yaml
schema_version: "2.0"
name: "My Custom Auditor"
description: "Reviews environmental impact assessments"
archetype: "Regulatory Compliance Auditor"
personality_profile:
  tone: "formal and precise"
  verbosity: "detailed"
  strictness: 0.9
  domain_focus: ["environmental", "regulatory", "compliance"]
  communication_style: "structured findings with regulatory citations"
contextual_tuning:
  temperature: 0.1
  max_tokens: 8192
  top_p: 0.95
  frequency_penalty: 0.1
  presence_penalty: 0.0
agent_type: "review"
system_prompt: |
  You are an environmental compliance auditor...
dspy_modules:
  - name: "analyze"
    type: "ChainOfThought"
    params:
      temperature: 0.1
      max_tokens: 4096
knowledge_scopes:
  tags: ["Environmental", "Compliance"]
```

## Error Handling

- **422 Validation Error** — displayed inline on the form with field-level details. Your input is preserved so you can fix and retry.
- **409 Conflict** — shown when trying to delete an agent that's assigned to an active review pipeline.
- **404 Not Found** — the agent doesn't exist or belongs to a different company.

## API Reference

All endpoints require `X-Company-Id` and `X-User-Id` headers. Mutations additionally require `X-Change-Reason`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents` | List agents (optional `?archetype=` filter) |
| POST | `/api/agents` | Create agent from JSON body |
| GET | `/api/agents/{id}` | Get single agent |
| PUT | `/api/agents/{id}` | Update agent |
| DELETE | `/api/agents/{id}` | Soft-delete agent |
| GET | `/api/agents/archetypes` | List predefined archetypes |
| POST | `/api/agents/from-archetype` | Create from archetype with overrides |
| POST | `/api/agents/reload` | Trigger directory rescan |

## Accessibility

- All form controls have proper labels and ARIA attributes
- Sliders include `aria-valuemin`, `aria-valuemax`, and `aria-valuenow`
- Error messages use `role="alert"` with `aria-live="polite"`
- Agent cards are keyboard-navigable (Enter/Space to select)
- The strictness indicator uses `role="meter"` for screen readers
- Filter dropdown has an accessible label for assistive technology

## Keyboard Navigation

- **Tab/Shift+Tab** — navigate between form fields and buttons
- **Enter/Space** — activate buttons, select agent cards
- **Arrow keys** — adjust slider values
