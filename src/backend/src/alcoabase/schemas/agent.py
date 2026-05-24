"""Pydantic request/response schemas for agent endpoints.

Provides validated schemas for agent CRUD operations, archetype
instantiation, personality profiles, contextual tuning, and
evaluation rubrics.

References:
    - Design doc Section 6: Pydantic Schemas
    - Requirements 1.3, 1.4, 1.5, 5.1, 5.2, 5.3, 8.2
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PersonalityProfile(BaseModel):
    """Structured behavioral parameters shaping agent communication.

    Attributes:
        tone: Communication tone descriptor (e.g., "formal and precise").
        verbosity: Level of detail in responses.
        strictness: How strictly the agent enforces rules (0.0 = lenient, 1.0 = strict).
        domain_focus: List of domain expertise areas.
        communication_style: Description of how the agent structures output.
    """

    tone: str = Field(max_length=100)
    verbosity: Literal["concise", "moderate", "detailed"]
    strictness: float = Field(ge=0.0, le=1.0)
    domain_focus: list[str] = Field(max_length=20)
    communication_style: str = Field(max_length=200)


class ContextualTuning(BaseModel):
    """LLM inference parameters configured per agent role.

    Attributes:
        temperature: Sampling temperature (0.0 = deterministic, 2.0 = creative).
        max_tokens: Maximum tokens in the response.
        top_p: Nucleus sampling probability threshold.
        frequency_penalty: Penalty for token frequency (-2.0 to 2.0).
        presence_penalty: Penalty for token presence (-2.0 to 2.0).
    """

    temperature: float = Field(ge=0.0, le=2.0, default=0.3)
    max_tokens: int = Field(ge=1, le=131072, default=4096)
    top_p: float = Field(ge=0.0, le=1.0, default=1.0)
    frequency_penalty: float = Field(ge=-2.0, le=2.0, default=0.0)
    presence_penalty: float = Field(ge=-2.0, le=2.0, default=0.0)


class EvaluationCriterion(BaseModel):
    """A single evaluation criterion within a rubric.

    Attributes:
        name: Criterion identifier.
        weight: Relative importance (0.0 to 1.0).
        description: What this criterion evaluates.
    """

    name: str
    weight: float = Field(ge=0.0, le=1.0)
    description: str


class EvaluationRubric(BaseModel):
    """Structured scoring guide for agent document assessment.

    Attributes:
        criteria: List of evaluation criteria (max 50).
        severity_thresholds: Threshold values for severity levels
            (critical, major, minor, informational).
        scoring_method: How criteria scores are combined.
    """

    criteria: list[EvaluationCriterion] = Field(max_length=50)
    severity_thresholds: dict[str, float]
    scoring_method: Literal["weighted_average", "pass_fail", "tiered"]


class AgentCreateRequest(BaseModel):
    """Request schema for creating a new agent definition.

    Attributes:
        schema_version: Agent schema version ("1.0" or "2.0").
        name: Agent display name.
        description: Agent purpose description.
        agent_type: Whether the agent generates or reviews content.
        archetype: Optional archetype role category.
        system_prompt: The agent's system prompt.
        dspy_modules: List of DSPy module configurations.
        knowledge_scopes: Knowledge base scope configuration.
        personality_profile: Optional behavioral parameters.
        contextual_tuning: Optional LLM tuning parameters.
        evaluation_rubric: Optional evaluation scoring guide.
    """

    schema_version: Literal["1.0", "2.0"]
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    agent_type: Literal["generation", "review"] = "generation"
    archetype: str | None = Field(default=None, max_length=100)
    system_prompt: str = Field(min_length=1)
    dspy_modules: list[dict]
    knowledge_scopes: dict
    personality_profile: PersonalityProfile | None = None
    contextual_tuning: ContextualTuning | None = None
    evaluation_rubric: EvaluationRubric | None = None


class AgentResponse(BaseModel):
    """Response schema for an agent definition.

    Attributes:
        id: Agent primary key.
        schema_version: Agent schema version.
        name: Agent display name.
        description: Agent purpose description.
        agent_type: Whether the agent generates or reviews content.
        archetype: Archetype role category (null for v1.0 agents).
        personality_profile: Behavioral parameters (null if not set).
        contextual_tuning: LLM tuning parameters (null if not set).
        evaluation_rubric: Evaluation scoring guide (null if not set).
        system_prompt: The agent's system prompt.
        dspy_modules: List of DSPy module configurations.
        knowledge_scopes: Knowledge base scope configuration.
        is_active: Whether the agent is active.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    id: int
    schema_version: str
    name: str
    description: str
    agent_type: str
    archetype: str | None
    personality_profile: PersonalityProfile | None
    contextual_tuning: ContextualTuning | None
    evaluation_rubric: EvaluationRubric | None
    system_prompt: str
    dspy_modules: list[dict]
    knowledge_scopes: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class FromArchetypeRequest(BaseModel):
    """Request schema for creating an agent from a predefined archetype.

    Attributes:
        archetype: Archetype identifier to base the agent on.
        name: Display name for the new agent.
        description: Optional description override.
        personality_profile: Partial personality overrides (deep-merged with defaults).
        contextual_tuning: Partial tuning overrides (deep-merged with defaults).
        knowledge_scopes: Optional knowledge scope overrides.
    """

    archetype: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    personality_profile: dict | None = None
    contextual_tuning: dict | None = None
    knowledge_scopes: dict | None = None


class ReloadSummary(BaseModel):
    """Summary of a directory rescan operation.

    Attributes:
        loaded: Names of newly loaded agent definitions.
        updated: Names of updated agent definitions.
        deactivated: Names of deactivated agent definitions.
        errors: List of error details for files that failed to load.
    """

    loaded: list[str]
    updated: list[str]
    deactivated: list[str]
    errors: list[dict[str, str]]
