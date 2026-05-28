"""Agent definition model for persisted AI agent configurations.

This module defines the AgentDefinition model that stores AI agent
configurations loaded from YAML files. Agents can be of type
"generation" (document creation) or "review" (document review).

References:
    - Agent YAML schema: agents/schema/agent-definition-v1.json
    - Agent YAML schema v2.0: agents/schema/agent-definition-v2.json
    - DSPy: Framework for composing LLM-based agent pipelines
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from alcoabase.database import Base
from alcoabase.models.audit import AuditMixin


class AgentDefinition(Base, AuditMixin):
    """Persisted AI agent configuration.

    Agent definitions describe the behavior, system prompt, DSPy module
    chain, and knowledge scopes for AI-powered document generation or
    review agents. They are loaded from YAML files and validated against
    the agent definition JSON schema.

    Attributes:
        id: Primary key.
        name: Agent display name.
        description: Human-readable description of the agent's purpose.
        agent_type: Type of agent ("generation" or "review").
        schema_version: Version of the agent definition schema.
        yaml_content: Raw YAML content of the agent definition.
        is_active: Whether this agent is currently available for use.
        created_by: Foreign key to the user who imported the agent.
        created_at: Server-side UTC timestamp of creation.
        company_id: Foreign key to the company (multi-tenancy).
        archetype: Role category identifier (v2.0, nullable for v1.0 agents).
        personality_profile: Structured personality configuration as JSONB (v2.0).
        contextual_tuning: LLM tuning parameters as JSONB (v2.0).
        evaluation_rubric: Evaluation rubric configuration as JSONB (v2.0).
        updated_at: Server-side timestamp updated on every INSERT and UPDATE.
    """

    __tablename__ = "agent_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str] = mapped_column(String(50))
    schema_version: Mapped[str] = mapped_column(String(20))
    yaml_content: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )

    # v2.0 fields
    archetype: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    personality_profile: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    contextual_tuning: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    evaluation_rubric: Mapped[dict | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
