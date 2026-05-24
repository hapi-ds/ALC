# Implementation Plan: Modular Agent Registry & Personality Framework

## Overview

This plan implements the modular agent registry with personality framework in incremental steps. It extends the existing in-memory YAML-based registry with schema v2.0 support, predefined archetypes, database persistence, hot-reload, full CRUD API, and a React frontend for agent management. Each task builds on previous work, starting with foundational schemas and utilities, then layering in persistence, API, and UI.

## Tasks

- [x] 1. Schema v2.0 and validation foundation
  - [x] 1.1 Create the Agent Definition v2.0 JSON Schema file
    - Create `agents/schema/agent-definition-v2.json` with all v2.0 fields (archetype required, personality_profile, contextual_tuning, evaluation_rubric optional)
    - Include all validation constraints: archetype max 100 chars, strictness 0.0-1.0, temperature 0.0-2.0, max_tokens 1-131072, top_p 0.0-1.0, frequency/presence_penalty -2.0 to 2.0, verbosity enum, scoring_method enum, criteria max 50 items, domain_focus max 20 items
    - Schema must reject unknown fields (additionalProperties: false at appropriate levels)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9_

  - [x] 1.2 Implement the SchemaValidator service
    - Create `src/backend/src/alcoabase/services/schema_validator.py`
    - Implement `SchemaValidator` class that loads both v1.0 and v2.0 JSON Schema files
    - Implement `validate(data)` method that dispatches to the correct schema based on `schema_version` field
    - Implement `get_schema_version(data)` and `is_supported_version(version)` methods
    - Return validation errors as a list of strings with field paths
    - Reject unsupported schema versions (anything other than "1.0" or "2.0") with a clear error message
    - v1.0 definitions must validate without requiring any v2.0 fields
    - _Requirements: 1.1, 1.6, 1.7, 1.10_

  - [x] 1.3 Write property test for schema validation (Property 1)
    - **Property 1: Valid v2.0 agent definitions pass schema validation**
    - Use hypothesis to generate random valid v2.0 definitions with all fields within valid ranges
    - Assert zero validation errors for all generated valid definitions
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.8, 1.9, 1.10**

  - [x] 1.4 Write property test for schema version routing (Property 2)
    - **Property 2: Schema version routing**
    - Generate random version strings; assert v1.0 passes without v2.0 fields, v2.0 requires archetype, other versions produce errors
    - **Validates: Requirements 1.6, 1.7**

- [x] 2. Deep merge utility and Pydantic schemas
  - [x] 2.1 Implement the deep merge utility
    - Create `src/backend/src/alcoabase/services/deep_merge.py`
    - Implement `deep_merge(base, overrides)` pure function
    - Scalars and arrays are replaced entirely; only dict values are recursively merged
    - Non-overridden sibling fields are preserved from base
    - _Requirements: 2.4, 8.4_

  - [x] 2.2 Write property test for deep merge (Property 3)
    - **Property 3: Deep merge preserves non-overridden sibling fields**
    - Use hypothesis to generate random nested dicts; verify all base keys not in overrides are preserved, override keys take precedence, nested dicts are recursively merged
    - **Validates: Requirements 2.4, 8.4**

  - [x] 2.3 Create Pydantic schemas for agent API
    - Create `src/backend/src/alcoabase/schemas/agent.py`
    - Implement `PersonalityProfile`, `ContextualTuning`, `EvaluationCriterion`, `EvaluationRubric` models with all field constraints
    - Implement `AgentCreateRequest`, `AgentResponse`, `FromArchetypeRequest`, `ReloadSummary` models
    - All numeric fields must have proper `ge`/`le` constraints matching the JSON Schema
    - _Requirements: 1.3, 1.4, 1.5, 5.1, 5.2, 5.3, 8.2_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Database model extension
  - [x] 4.1 Extend the AgentDefinition database model
    - Modify `src/backend/src/alcoabase/models/agent.py`
    - Add `archetype` column (String(100), nullable, indexed)
    - Add `personality_profile` column (JSONB, nullable)
    - Add `contextual_tuning` column (JSONB, nullable)
    - Add `evaluation_rubric` column (JSONB, nullable)
    - Add `updated_at` column (DateTime with timezone, server_default=func.now(), onupdate=func.now())
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.8_

  - [x] 4.2 Create Alembic migration for v2.0 columns
    - Generate and write a migration that adds the new columns to `agent_definitions` table
    - Include index creation on `archetype` column
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.8_

- [x] 5. Predefined archetypes
  - [x] 5.1 Create predefined archetype YAML files
    - Create `agents/archetypes/` directory
    - Create YAML files for all 6 archetypes: regulatory-compliance-auditor.yaml, data-integrity-specialist.yaml, process-safety-reviewer.yaml, statistical-methods-auditor.yaml, technical-writer.yaml, educational-specialist.yaml
    - Each file must include: archetype name, default personality_profile (tone, verbosity, strictness, domain_focus, communication_style), contextual_tuning (temperature, max_tokens, top_p, frequency_penalty, presence_penalty), system_prompt, and knowledge_scopes
    - Use exact values from requirements: Regulatory Compliance Auditor (strictness=0.9, temp=0.1, verbosity=detailed), Data Integrity Specialist (strictness=0.85, temp=0.15, verbosity=detailed), Process Safety Reviewer (strictness=0.95, temp=0.1, verbosity=detailed), Statistical Methods Auditor (strictness=0.8, temp=0.2, verbosity=moderate), Technical Writer (strictness=0.5, temp=0.4, verbosity=detailed), Educational Specialist (strictness=0.3, temp=0.6, verbosity=moderate)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_

- [x] 6. Agent Registry Service refactor
  - [x] 6.1 Implement the AgentRegistryService with DB persistence
    - Extend `src/backend/src/alcoabase/services/agent_registry.py` with a new `AgentRegistryService` class (keep existing `AgentRegistry` for backward compat)
    - Constructor accepts `session_factory`, `schema_validator`, `agents_dir`, `archetypes_dir`
    - Implement `initialize()` method: load active agents from DB into memory, sync YAML agents with DB (match by name within company scope)
    - Implement DB fallback: if DB unreachable within 5 seconds at startup, load from YAML only and log warning
    - Implement CRUD methods: `create_agent`, `get_agent`, `list_agents` (with archetype filter), `update_agent`, `delete_agent` (soft-delete)
    - All CRUD operations persist to DB first, then update in-memory cache on success; on DB failure, leave memory unchanged
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 5.4, 5.6, 5.7, 5.8_

  - [x] 6.2 Implement archetype operations
    - Add `list_archetypes()` method that loads archetype YAML files from `agents/archetypes/`
    - Add `create_from_archetype(archetype_id, name, overrides, company_id, user_id)` method
    - Deep-merge overrides with archetype defaults, validate merged result against v2.0 schema, persist to DB
    - Return 404 with available archetypes list if archetype_id is unknown
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 6.3 Implement tuning parameter resolution
    - Add `get_tuning_params(agent_id, overrides)` method
    - If agent has no contextual_tuning, return defaults (temperature=0.3, max_tokens=4096, top_p=1.0, frequency_penalty=0.0, presence_penalty=0.0)
    - If overrides provided, merge with agent defaults (overrides take precedence)
    - Validate override ranges; raise validation error if out of range
    - Add `get_system_prompt_with_rubric(agent_id)` method that appends evaluation_rubric criteria to system_prompt
    - _Requirements: 4.1, 4.2, 4.5, 4.6, 4.7_

  - [x] 6.4 Write property tests for tuning resolution (Properties 4, 5, 6)
    - **Property 4: Tuning parameter resolution with defaults**
    - **Property 5: Invocation override precedence and range validation**
    - **Property 6: Evaluation rubric appended to system prompt**
    - **Validates: Requirements 4.1, 4.2, 4.5, 4.6, 4.7**

  - [x] 6.5 Implement YAML export/import with round-trip fidelity
    - Add export method that outputs v2.0 fields, omits null values, preserves field ordering (schema_version, name, description, archetype, personality_profile, contextual_tuning, evaluation_rubric, agent_type, system_prompt, dspy_modules, knowledge_scopes)
    - Add import method with validations: reject unknown fields, reject files >1 MB, reject name conflicts within company scope, reject missing/invalid fields
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 6.6 Write property tests for YAML round-trip and import validation (Properties 7, 8)
    - **Property 7: YAML serialization round-trip**
    - **Property 8: Import validation rejects invalid definitions**
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.7, 5.5**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. File watcher for hot-reload
  - [x] 8.1 Implement the AgentFileWatcher
    - Create `src/backend/src/alcoabase/services/agent_file_watcher.py`
    - Use `watchfiles` package for filesystem watching (polling-based)
    - Only process files with .yaml or .yml extensions
    - On file add: validate and load new agent definition
    - On file modify: validate and reload agent definition (retain previous valid definition on failure)
    - On file remove: mark agent as inactive
    - Log warnings for invalid YAML or schema validation failures with file path and error details
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.8, 3.9_

  - [x] 8.2 Integrate file watcher with AgentRegistryService
    - Add `start_watcher()` and `stop_watcher()` methods to AgentRegistryService
    - Add `reload()` method that triggers immediate rescan and returns `ReloadSummary` (loaded, updated, deactivated, errors)
    - Wire watcher start/stop into application lifespan
    - _Requirements: 3.6, 3.7_

  - [x] 8.3 Write property test for file extension filtering (Property 10)
    - **Property 10: File extension filtering**
    - Generate random filenames with various extensions; verify only .yaml/.yml are processed
    - **Validates: Requirements 3.9**

- [x] 9. FastAPI CRUD and archetype endpoints
  - [x] 9.1 Implement full CRUD endpoints in the agents router
    - Rewrite `src/backend/src/alcoabase/api/agents.py` to use `AgentRegistryService`
    - POST /api/agents — create agent, validate against schema, return 201
    - GET /api/agents — list agents with optional `archetype` query param filter
    - GET /api/agents/{agent_id} — get single agent
    - PUT /api/agents/{agent_id} — update agent, validate, return 200
    - DELETE /api/agents/{agent_id} — soft-delete, return 204; return 409 if agent in active pipeline
    - All operations scoped to X-Company-Id header
    - All mutations require X-Change-Reason header (return 400 if missing)
    - Return 404 for non-existent or wrong-company agents
    - Return 422 with field-level errors on validation failure
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [x] 9.2 Implement archetype and reload endpoints
    - GET /api/agents/archetypes — list available archetypes with defaults
    - POST /api/agents/from-archetype — create agent from archetype with overrides, validate merged result, return 201
    - POST /api/agents/reload — trigger directory rescan, return ReloadSummary
    - Return 404 with available archetypes list for unknown archetype
    - Return 422 if merged definition fails validation
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 3.6, 3.7_

  - [x] 9.3 Write property test for company-scoped filtering (Property 9)
    - **Property 9: Company-scoped agent filtering**
    - Generate multi-company agent sets; verify listing returns only agents for the specified company and archetype filter works correctly
    - **Validates: Requirements 5.6, 6.7**

  - [x] 9.4 Write unit tests for CRUD endpoints
    - Test all HTTP status codes: 201, 200, 204, 400, 404, 409, 422
    - Test X-Change-Reason header enforcement
    - Test company scoping isolation
    - Test archetype instantiation with overrides
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Frontend agent management UI
  - [x] 11.1 Create frontend API client functions and TypeScript types
    - Create `src/frontend/src/lib/agents-api.ts` with typed API functions for all agent endpoints
    - Define TypeScript interfaces: `AgentResponse`, `PersonalityProfile`, `ContextualTuning`, `EvaluationRubric`, `ArchetypeDefinition`, `FromArchetypeRequest`, `AgentCreateRequest`
    - Use the existing `apiClient` from `src/frontend/src/lib/apiClient.ts`
    - Include X-Change-Reason header in all mutation requests
    - _Requirements: 10.1, 10.6_

  - [x] 11.2 Implement the AgentList component with archetype badges and filtering
    - Create `src/frontend/src/components/agents/AgentList.tsx`
    - Fetch agents from GET /api/agents
    - Display agent cards with name, archetype, agent_type, and personality summary (tone, verbosity, strictness)
    - Add archetype badges with unique colors per archetype
    - Add filter dropdown to filter by archetype
    - _Requirements: 10.1, 10.8, 10.9_

  - [x] 11.3 Implement the AgentDetail component
    - Create `src/frontend/src/components/agents/AgentDetail.tsx`
    - Display full agent detail: personality_profile, contextual_tuning, evaluation_rubric, knowledge_scopes
    - Show on agent card click
    - _Requirements: 10.4_

  - [x] 11.4 Implement the AgentForm component with archetype selection and sliders
    - Create `src/frontend/src/components/agents/AgentForm.tsx`
    - Archetype selector that fetches from GET /api/agents/archetypes and populates defaults on selection
    - Sliders for numeric ranges: strictness (0.0–1.0), temperature (0.0–2.0), top_p (0.0–1.0), frequency_penalty (-2.0–2.0), presence_penalty (-2.0–2.0)
    - Numeric input for max_tokens
    - Dropdowns for enum fields (verbosity, scoring_method)
    - Required X-Change-Reason text input field (minimum 1 character)
    - Display API error details (422, 409) without navigating away, preserving user input
    - _Requirements: 10.2, 10.3, 10.5, 10.6, 10.7_

  - [x] 11.5 Wire up AgentsPage with all components
    - Replace placeholder content in `src/frontend/src/pages/AgentsPage.tsx`
    - Integrate AgentList, AgentDetail, and AgentForm components
    - Handle "New Agent" button to show creation form
    - Handle agent card click to show detail view
    - Handle edit mode transition
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The existing `AgentRegistry` class is preserved for backward compatibility; the new `AgentRegistryService` wraps and extends it
- All backend API endpoints use the `/api` prefix (not `/api/v1`)
- All mutating requests require the `X-Change-Reason` header per AuditMiddleware conventions
- Frontend uses the existing `apiClient` for consistent auth and header handling

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.3"] },
    { "id": 1, "tasks": ["1.2", "2.2", "5.1"] },
    { "id": 2, "tasks": ["1.3", "1.4", "4.1"] },
    { "id": 3, "tasks": ["4.2"] },
    { "id": 4, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 5, "tasks": ["6.4", "6.5"] },
    { "id": 6, "tasks": ["6.6", "8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3"] },
    { "id": 8, "tasks": ["9.1", "9.2"] },
    { "id": 9, "tasks": ["9.3", "9.4"] },
    { "id": 10, "tasks": ["11.1"] },
    { "id": 11, "tasks": ["11.2", "11.3", "11.4"] },
    { "id": 12, "tasks": ["11.5"] }
  ]
}
```
