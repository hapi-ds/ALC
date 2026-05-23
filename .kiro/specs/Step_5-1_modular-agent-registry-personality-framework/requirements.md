# Requirements Document

## Introduction

This feature extends the existing Agent Registry (in-memory, YAML-based) into a full Modular Agent Registry with a Personality Framework. The system introduces pluggable agent archetypes with configurable personality traits, domain expertise profiles, contextual LLM tuning parameters, and evaluation rubrics. Agent definitions are stored in an extensible YAML/JSON format with hot-reload capability, enabling operators to add new archetypes (e.g., "Environmental Impact Auditor") without code changes. The registry is company-scoped and integrates with the existing vLLM inference layer and RAG knowledge base.

## Glossary

- **Agent_Registry**: The backend service that loads, validates, stores, and serves agent definitions. Currently implemented as an in-memory dictionary with YAML file loading.
- **Agent_Definition**: A validated configuration describing an agent's identity, behavior, and tuning parameters. Persisted as YAML and stored in the database.
- **Archetype**: A reusable agent template defining a role category (e.g., "Regulatory Auditor", "Technical Writer") with default personality, expertise, and tuning values.
- **Personality_Profile**: A structured set of behavioral parameters (tone, verbosity, strictness, domain focus) that shape how an agent communicates and evaluates.
- **Contextual_Tuning**: LLM inference parameters (temperature, max_tokens, top_p, frequency_penalty) and evaluation rubrics configured per agent role.
- **Evaluation_Rubric**: A structured scoring guide that defines how an agent assesses documents, including criteria, weights, and severity thresholds.
- **Hot_Reload**: The ability to detect and load new or modified agent YAML files into the running registry without restarting the application.
- **Agent_Schema**: The JSON Schema (currently v1.0) that validates agent definition YAML files. This feature introduces v2.0 with archetype and personality fields.
- **Company_Scope**: Multi-tenancy boundary ensuring agents belong to and are accessible only within a specific company/tenant.
- **ModelManager**: The existing vLLM service layer that provides LLM inference with configurable parameters.

## Requirements

### Requirement 1: Agent Schema v2.0 with Archetype and Personality Fields

**User Story:** As a system administrator, I want agent definitions to include archetype classification, personality profiles, and contextual tuning parameters, so that agents have well-defined behavioral identities beyond just a system prompt.

#### Acceptance Criteria

1. THE Agent_Schema SHALL define a v2.0 schema that includes all v1.0 required fields (schema_version, name, description, system_prompt, dspy_modules, knowledge_scopes) plus the following additional fields: archetype (required), personality_profile (optional), contextual_tuning (optional), and evaluation_rubric (optional).
2. WHEN an agent definition specifies schema_version "2.0", THE Agent_Schema SHALL require the archetype field as a non-empty string with a maximum length of 100 characters identifying the role category.
3. THE Agent_Schema SHALL define personality_profile as an object containing: tone (string, max 100 characters), verbosity (enum: concise, moderate, detailed), strictness (number 0.0-1.0 inclusive), domain_focus (array of strings, maximum 20 items), and communication_style (string, max 200 characters).
4. THE Agent_Schema SHALL define contextual_tuning as an object containing: temperature (number 0.0-2.0 inclusive), max_tokens (integer, minimum 1, maximum 131072), top_p (number 0.0-1.0 inclusive), frequency_penalty (number -2.0 to 2.0 inclusive), and presence_penalty (number -2.0 to 2.0 inclusive).
5. THE Agent_Schema SHALL define evaluation_rubric as an optional object containing: criteria (array of objects with name (string), weight (number 0.0-1.0 inclusive), and description (string), maximum 50 items), severity_thresholds (object with keys critical, major, minor, informational each mapping to a numeric threshold 0.0-1.0), and scoring_method (enum: weighted_average, pass_fail, tiered).
6. WHEN an agent definition specifies schema_version "1.0", THE Agent_Registry SHALL continue to validate and load the definition using the existing v1.0 schema rules without requiring any v2.0 fields.
7. IF an agent definition specifies a schema_version value other than "1.0" or "2.0", THEN THE Agent_Schema SHALL reject the definition with a validation error indicating the unsupported schema version.
8. THE Agent_Schema SHALL validate that personality_profile.strictness is a number between 0.0 and 1.0 inclusive.
9. THE Agent_Schema SHALL validate that contextual_tuning.temperature is a number between 0.0 and 2.0 inclusive.
10. IF a v2.0 agent definition omits personality_profile or contextual_tuning, THEN THE Agent_Registry SHALL accept the definition as valid and apply system defaults when those fields are accessed at runtime.

### Requirement 2: Predefined Agent Archetypes

**User Story:** As a quality manager, I want a set of predefined agent archetypes for common regulatory roles, so that I can quickly deploy specialized review and generation agents without writing definitions from scratch.

#### Acceptance Criteria

1. THE Agent_Registry SHALL provide predefined archetype definitions for: "Regulatory Compliance Auditor", "Data Integrity Specialist", "Process Safety Reviewer", "Statistical Methods Auditor", "Technical Writer", and "Educational Specialist".
2. WHEN a predefined archetype is loaded, THE Agent_Registry SHALL populate the archetype definition with a default personality_profile (tone, verbosity, strictness, domain_focus, communication_style), contextual_tuning (temperature, max_tokens, top_p, frequency_penalty, presence_penalty), system_prompt, and knowledge_scopes, where each default value is explicitly defined in the archetype YAML file.
3. THE Agent_Registry SHALL store predefined archetypes as YAML files in the agents/archetypes/ directory, with one YAML file per archetype.
4. WHEN a company creates a new agent from an archetype, THE Agent_Registry SHALL perform a deep merge of the override fields into the archetype defaults, where override values at any nesting level replace the corresponding default values while preserving non-overridden sibling fields.
5. THE Agent_Registry SHALL assign the "Regulatory Compliance Auditor" archetype a strictness value of 0.9, temperature of 0.1, and verbosity of "detailed".
6. THE Agent_Registry SHALL assign the "Technical Writer" archetype a strictness value of 0.5, temperature of 0.4, and verbosity of "detailed".
7. THE Agent_Registry SHALL assign the "Educational Specialist" archetype a strictness value of 0.3, temperature of 0.6, and verbosity of "moderate".
8. THE Agent_Registry SHALL assign the "Data Integrity Specialist" archetype a strictness value of 0.85, temperature of 0.15, and verbosity of "detailed".
9. THE Agent_Registry SHALL assign the "Process Safety Reviewer" archetype a strictness value of 0.95, temperature of 0.1, and verbosity of "detailed".
10. THE Agent_Registry SHALL assign the "Statistical Methods Auditor" archetype a strictness value of 0.8, temperature of 0.2, and verbosity of "moderate".

### Requirement 3: Extensible Agent Configuration with Hot-Reload

**User Story:** As a system administrator, I want to add new agent archetypes by dropping YAML files into a directory without restarting the application, so that the system can evolve without downtime.

#### Acceptance Criteria

1. WHEN a new YAML file (with .yaml or .yml extension) is added to the configured agents directory, THE Agent_Registry SHALL detect the file within 30 seconds and load the new agent definition.
2. WHEN an existing YAML file is modified in the configured agents directory, THE Agent_Registry SHALL detect the change within 30 seconds and reload the agent definition.
3. WHEN a YAML file is removed from the configured agents directory, THE Agent_Registry SHALL mark the corresponding agent definition as inactive within 30 seconds.
4. IF a newly detected or modified YAML file fails schema validation, THEN THE Agent_Registry SHALL log a warning with the file path and validation errors, skip loading the invalid file, and retain the previous valid definition for modified files.
5. IF a newly detected or modified YAML file contains syntax errors that prevent YAML parsing, THEN THE Agent_Registry SHALL log a warning with the file path and parse error details, skip loading the file, and retain the previous valid definition for modified files.
6. THE Agent_Registry SHALL expose an API endpoint POST /api/agents/reload that triggers an immediate rescan of the agents directory.
7. WHEN the reload endpoint is called, THE Agent_Registry SHALL return a summary listing newly loaded agents, updated agents, deactivated agents, and validation errors encountered.
8. THE Agent_Registry SHALL use filesystem watching (polling-based) to detect file changes without requiring external dependencies beyond the Python standard library and watchfiles package.
9. THE Agent_Registry SHALL only process files with .yaml or .yml extensions in the configured agents directory and ignore all other files.

### Requirement 4: Contextual Tuning per Agent Role

**User Story:** As an AI engineer, I want each agent role to have independently configurable LLM parameters and evaluation rubrics, so that inference behavior is optimized for each agent's specific task.

#### Acceptance Criteria

1. WHEN the ModelManager invokes inference for an agent, THE Agent_Registry SHALL provide the agent-specific contextual_tuning parameters (temperature, max_tokens, top_p, frequency_penalty, presence_penalty) to the inference call.
2. IF an agent definition does not specify a contextual_tuning field, THEN THE Agent_Registry SHALL apply default tuning values: temperature 0.3, max_tokens 4096, top_p 1.0, frequency_penalty 0.0, presence_penalty 0.0.
3. WHEN an agent definition is loaded or updated, THE Agent_Registry SHALL validate that contextual_tuning.max_tokens does not exceed the model context window limit reported by the ModelManager.
4. IF contextual_tuning.max_tokens exceeds the model context window limit, THEN THE Agent_Registry SHALL reject the agent definition with a validation error indicating the configured max_tokens value and the model's context window limit.
5. IF an agent has an evaluation_rubric defined, THEN THE Agent_Registry SHALL append the rubric criteria to the agent's system prompt context so the LLM uses the rubric during evaluation.
6. THE Agent_Registry SHALL allow contextual_tuning parameters to be overridden at invocation time by passing explicit parameters, with invocation-time values taking precedence over agent defaults.
7. IF invocation-time override parameters are outside the valid schema ranges (temperature 0.0–2.0, top_p 0.0–1.0, frequency_penalty -2.0 to 2.0, presence_penalty -2.0 to 2.0, max_tokens greater than 0), THEN THE Agent_Registry SHALL reject the inference request with a validation error indicating which parameter is out of range.

### Requirement 5: Agent CRUD API

**User Story:** As a frontend developer, I want full CRUD endpoints for agent definitions, so that users can create, view, update, and delete agents through the UI.

#### Acceptance Criteria

1. THE Agent_Registry SHALL expose a POST /api/agents endpoint that creates a new agent definition from a JSON request body, validates it against the Agent_Schema, and returns the full created agent object with HTTP 201.
2. THE Agent_Registry SHALL expose a GET /api/agents endpoint that returns a list of active agent definitions for the current company, and a GET /api/agents/{agent_id} endpoint that returns a single agent definition by ID.
3. THE Agent_Registry SHALL expose a PUT /api/agents/{agent_id} endpoint that replaces an existing agent definition with the provided JSON request body, validates it against the Agent_Schema, and returns the full updated agent object with HTTP 200.
4. THE Agent_Registry SHALL expose a DELETE /api/agents/{agent_id} endpoint that soft-deletes an agent by setting is_active to false and returns HTTP 204.
5. WHEN a POST or PUT request contains an agent definition that fails Agent_Schema validation, THE Agent_Registry SHALL return HTTP 422 with a response body containing a list of field-level validation errors.
6. THE Agent_Registry SHALL scope all CRUD operations to the company identified by the X-Company-Id header, and all mutating requests (POST, PUT, DELETE) SHALL require the X-Change-Reason header.
7. IF a GET, PUT, or DELETE request references an agent_id that does not exist or does not belong to the requesting company, THEN THE Agent_Registry SHALL return HTTP 404 with a message indicating the agent was not found.
8. IF a DELETE request targets an agent that is currently assigned to an active review pipeline, THEN THE Agent_Registry SHALL return HTTP 409 with a message indicating the agent is in use.
9. IF a mutating request (POST, PUT, DELETE) is missing the X-Change-Reason header, THEN THE Agent_Registry SHALL return HTTP 400 with a message indicating the header is required.

### Requirement 6: Agent Database Model Extension

**User Story:** As a backend developer, I want the database model to persist archetype, personality, and tuning data, so that agent configurations survive application restarts and support querying.

#### Acceptance Criteria

1. THE AgentDefinition database model SHALL include an archetype column (String with maximum length of 100 characters, nullable) storing the archetype identifier, where the column is null for agents with schema_version "1.0".
2. THE AgentDefinition database model SHALL include a personality_profile column (JSONB, nullable) storing the structured personality configuration, where the column is null for agents with schema_version "1.0".
3. THE AgentDefinition database model SHALL include a contextual_tuning column (JSONB, nullable) storing the LLM tuning parameters, where the column is null for agents with schema_version "1.0".
4. THE AgentDefinition database model SHALL include an evaluation_rubric column (JSONB, nullable) storing the evaluation rubric configuration.
5. THE AgentDefinition database model SHALL include an updated_at column (DateTime with timezone) that is set to the current server time via a database-level trigger or ORM event on every INSERT and UPDATE operation.
6. WHEN an agent definition is imported from YAML with schema_version "2.0", THE Agent_Registry SHALL persist the archetype, personality_profile, contextual_tuning, and evaluation_rubric fields to the corresponding database columns, storing null for any optional v2.0 field not present in the YAML.
7. WHEN the list endpoint receives an archetype query parameter, THE AgentDefinition database model SHALL support filtering agents to return only those whose archetype column matches the provided value, returning an empty list if no agents match.
8. THE AgentDefinition database model SHALL include a database index on the archetype column to support efficient filtering queries.

### Requirement 7: Agent Registry Persistence with Database Backend

**User Story:** As a system administrator, I want agent definitions persisted in the database rather than only in memory, so that agents survive restarts and can be managed across multiple application instances.

#### Acceptance Criteria

1. WHEN the application starts, THE Agent_Registry SHALL load all agent definitions with is_active set to true from the database into the in-memory registry.
2. WHEN a new agent is created via the API, THE Agent_Registry SHALL persist the definition to the database and, only upon successful persistence, add the definition to the in-memory registry.
3. WHEN an agent is updated via the API, THE Agent_Registry SHALL update the database record and, only upon successful database update, update the in-memory registry entry.
4. WHEN an agent is soft-deleted via the API, THE Agent_Registry SHALL set is_active to false in the database and remove the definition from the in-memory registry.
5. WHEN the application starts, THE Agent_Registry SHALL synchronize YAML-loaded agents with the database by matching on agent name within the same company scope, creating database records for any YAML agents that do not have a matching database entry.
6. IF the database connection cannot be established within 5 seconds during startup, THEN THE Agent_Registry SHALL fall back to loading agents from YAML files only and log a warning indicating the database was unreachable.
7. IF a database write fails during an API create or update operation, THEN THE Agent_Registry SHALL return an error response and leave the in-memory registry unchanged.

### Requirement 8: Archetype-Based Agent Instantiation API

**User Story:** As a quality manager, I want to create new agents from predefined archetypes with optional customizations, so that I can quickly deploy role-specific agents without manual configuration.

#### Acceptance Criteria

1. THE Agent_Registry SHALL expose a GET /api/agents/archetypes endpoint that returns the list of available predefined archetypes with their default configurations, scoped to the company identified by the X-Company-Id header.
2. THE Agent_Registry SHALL expose a POST /api/agents/from-archetype endpoint that accepts a request body containing a required archetype identifier, a required agent name, and optional field overrides for personality_profile, contextual_tuning, knowledge_scopes, and description.
3. WHEN the from-archetype endpoint receives an unknown archetype identifier, THE Agent_Registry SHALL return HTTP 404 with a message listing available archetypes.
4. WHEN the from-archetype endpoint receives override values, THE Agent_Registry SHALL deep-merge the overrides with the archetype defaults such that individual nested fields within personality_profile and contextual_tuning can be overridden independently while unspecified sibling fields retain their archetype default values.
5. THE Agent_Registry SHALL validate the merged agent definition against the v2.0 schema before persisting the new agent, and return HTTP 201 with the complete created agent definition on success.
6. IF the merged agent definition fails v2.0 schema validation, THEN THE Agent_Registry SHALL return HTTP 422 with a list of validation errors indicating which fields failed and why.
7. THE Agent_Registry SHALL scope the from-archetype creation to the company identified by the X-Company-Id header, associating the newly created agent with that company.

### Requirement 9: Agent Definition YAML Serialization Round-Trip

**User Story:** As a system administrator, I want to export agent definitions as YAML and re-import them without data loss, so that I can transfer agent configurations between environments.

#### Acceptance Criteria

1. WHEN an agent definition is exported as YAML, THE Agent_Registry SHALL include all v2.0 fields (archetype, personality_profile, contextual_tuning, evaluation_rubric) in the output, omitting fields that have null values.
2. WHEN an Agent_Definition is exported to YAML and the resulting YAML is imported, THE Agent_Registry SHALL produce an Agent_Definition with identical values for all schema-defined fields, excluding system-generated fields (id, created_at, updated_at, company_id).
3. THE Agent_Registry SHALL preserve field ordering in exported YAML as follows: schema_version, name, description, archetype, personality_profile, contextual_tuning, evaluation_rubric, agent_type, system_prompt, dspy_modules, knowledge_scopes.
4. WHEN importing a YAML file that contains unknown fields not in the schema, THE Agent_Registry SHALL reject the file with a validation error listing the unknown fields.
5. IF an imported YAML file exceeds 1 MB in size, THEN THE Agent_Registry SHALL reject the file with a validation error indicating the size limit.
6. IF an imported YAML file specifies a name that matches an existing active agent definition within the same company scope, THEN THE Agent_Registry SHALL reject the import with a validation error indicating the name conflict.
7. IF an imported YAML file is missing required fields or contains fields with invalid types, THEN THE Agent_Registry SHALL reject the file with a validation error listing each missing or invalid field.

### Requirement 10: Frontend Agent Management UI

**User Story:** As a quality manager, I want a UI to browse, create, edit, and manage agents with their personality profiles and tuning parameters, so that I can configure the agent fleet without editing YAML files.

#### Acceptance Criteria

1. THE AgentsPage SHALL fetch and display the list of active agents from the GET /api/agents endpoint, showing name, archetype, agent_type, and a personality summary consisting of the tone, verbosity, and strictness values from the personality_profile.
2. WHEN a user clicks "New Agent", THE AgentsPage SHALL display a form allowing selection of an archetype from the available archetypes returned by GET /api/agents/archetypes, and customization of personality_profile and contextual_tuning fields.
3. WHEN a user selects an archetype in the creation form, THE AgentsPage SHALL populate the personality_profile and contextual_tuning fields with the archetype's default values, allowing the user to override individual fields before submission.
4. WHEN a user clicks on an existing agent card, THE AgentsPage SHALL display the full agent detail view including personality_profile, contextual_tuning, evaluation_rubric, and knowledge_scopes.
5. THE AgentsPage SHALL provide an edit mode for modifying agent personality_profile and contextual_tuning fields using sliders for numeric ranges (strictness: 0.0–1.0, temperature: 0.0–2.0, top_p: 0.0–1.0, frequency_penalty: -2.0–2.0, presence_penalty: -2.0–2.0), a numeric input for max_tokens, and dropdowns for enum fields (verbosity, scoring_method).
6. WHEN a user submits agent creation or update, THE AgentsPage SHALL require the user to provide a non-empty X-Change-Reason value (minimum 1 character) and include it as the X-Change-Reason header in the request.
7. IF the API returns an error response (HTTP 422 or 409) after agent creation or update submission, THEN THE AgentsPage SHALL display the error details returned by the API without navigating away from the form, preserving the user's input.
8. THE AgentsPage SHALL display archetype badges with a unique color per archetype to visually differentiate agent roles in the list view.
9. THE AgentsPage SHALL provide a filter dropdown to filter agents by archetype, populated with the archetypes present in the current agent list.
