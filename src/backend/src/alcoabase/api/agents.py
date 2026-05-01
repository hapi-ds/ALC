"""FastAPI router for agent registry endpoints.

Provides endpoints for:
- GET /api/agents: List all registered agents
- POST /api/agents/import: Import an agent from YAML
- GET /api/agents/{agent_id}/export: Export an agent as YAML
- POST /api/agents/{agent_id}/select: Select an agent (with audit trail)

References:
    - Task 15.8: Create FastAPI router /api/agents
    - Design doc Section 11: Agent Registry
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from alcoabase.services.agent_registry import (
    AgentRegistry,
    AgentValidationError,
    UnsupportedSchemaVersionError,
)

router = APIRouter(prefix="/agents", tags=["Agents"])


# ---------------------------------------------------------------------------
# Request/Response Schemas
# ---------------------------------------------------------------------------


class DSPyModuleResponse(BaseModel):
    """Response schema for a DSPy module configuration."""

    name: str
    type: str
    params: dict | None = None


class AgentResponse(BaseModel):
    """Response schema for an agent definition."""

    id: str
    schema_version: str
    agent_type: str
    name: str
    description: str
    system_prompt: str
    dspy_modules: list[DSPyModuleResponse]
    knowledge_scopes: dict
    example_usage: str = ""
    target_document_tag: str | None = None


class AgentImportRequest(BaseModel):
    """Request schema for importing an agent from YAML."""

    yaml_content: str = Field(..., min_length=1, description="YAML content of the agent definition")


class AgentSelectRequest(BaseModel):
    """Request schema for selecting an agent."""

    user_id: int = Field(..., description="ID of the user selecting the agent")
    purpose: str = Field(default="query", description="Purpose of the selection")


class AgentSelectResponse(BaseModel):
    """Response schema for agent selection."""

    event_id: str
    agent_id: str
    agent_name: str
    user_id: int
    timestamp: str
    purpose: str


class AgentImportResponse(BaseModel):
    """Response schema for agent import."""

    id: str
    name: str
    agent_type: str
    message: str


class ValidationErrorResponse(BaseModel):
    """Response schema for validation errors."""

    detail: str
    errors: list[str]


# ---------------------------------------------------------------------------
# Dependency
# ---------------------------------------------------------------------------

_agent_registry: AgentRegistry | None = None


def get_agent_registry() -> AgentRegistry:
    """Provide the AgentRegistry instance as a FastAPI dependency.

    Returns:
        The module-level AgentRegistry instance.
    """
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
        # Try to load example agents
        examples_dir = Path(__file__).parent.parent.parent.parent.parent / "agents" / "examples"
        if examples_dir.exists():
            try:
                _agent_registry.load_agents(examples_dir)
            except Exception:
                pass
    return _agent_registry


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    agent_type: str | None = Query(default=None, description="Filter by agent type"),
    registry: AgentRegistry = Depends(get_agent_registry),
) -> list[AgentResponse]:
    """List all registered agents.

    Args:
        agent_type: Optional filter by agent type (generation or review).
        registry: AgentRegistry dependency.

    Returns:
        List of agent definitions.
    """
    agents = registry.list_agents(agent_type=agent_type)

    return [
        AgentResponse(
            id=agent.id,
            schema_version=agent.schema_version,
            agent_type=agent.agent_type,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            dspy_modules=[
                DSPyModuleResponse(
                    name=m["name"],
                    type=m["type"],
                    params=m.get("params"),
                )
                for m in agent.dspy_modules
            ],
            knowledge_scopes=agent.knowledge_scopes,
            example_usage=agent.example_usage,
            target_document_tag=agent.target_document_tag,
        )
        for agent in agents
    ]


@router.post("/import", response_model=AgentImportResponse, status_code=201)
async def import_agent(
    request: AgentImportRequest,
    registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentImportResponse:
    """Import an agent definition from YAML content.

    Validates the YAML against the JSON Schema and registers the agent.

    Args:
        request: Import request with YAML content.
        registry: AgentRegistry dependency.

    Returns:
        Import confirmation with agent details.

    Raises:
        HTTPException: 400 if validation fails or schema version unsupported.
    """
    try:
        agent = registry.import_agent(request.yaml_content.encode("utf-8"))
        return AgentImportResponse(
            id=agent.id,
            name=agent.name,
            agent_type=agent.agent_type,
            message=f"Agent '{agent.name}' imported successfully",
        )
    except UnsupportedSchemaVersionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except AgentValidationError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Validation failed: {'; '.join(e.errors)}",
        )


@router.get("/{agent_id}/export")
async def export_agent(
    agent_id: str,
    registry: AgentRegistry = Depends(get_agent_registry),
) -> Response:
    """Export an agent definition as YAML.

    Args:
        agent_id: ID of the agent to export.
        registry: AgentRegistry dependency.

    Returns:
        YAML content as downloadable response.

    Raises:
        HTTPException: 404 if agent not found.
    """
    try:
        yaml_bytes = registry.export_agent(agent_id)
        return Response(
            content=yaml_bytes,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f"attachment; filename=agent-{agent_id[:8]}.yaml"
            },
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")


@router.post("/{agent_id}/select", response_model=AgentSelectResponse)
async def select_agent(
    agent_id: str,
    request: AgentSelectRequest,
    registry: AgentRegistry = Depends(get_agent_registry),
) -> AgentSelectResponse:
    """Select an agent for use (records in audit trail).

    Args:
        agent_id: ID of the agent to select.
        request: Selection request with user ID and purpose.
        registry: AgentRegistry dependency.

    Returns:
        Selection confirmation with audit event details.

    Raises:
        HTTPException: 404 if agent not found.
    """
    try:
        event = registry.record_selection(
            user_id=request.user_id,
            agent_id=agent_id,
            purpose=request.purpose,
        )
        return AgentSelectResponse(
            event_id=event.event_id,
            agent_id=event.agent_id,
            agent_name=event.agent_name,
            user_id=event.user_id,
            timestamp=event.timestamp.isoformat(),
            purpose=event.purpose,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
