"""FastAPI router for agent registry CRUD endpoints.

Provides full CRUD operations for agent definitions using the
AgentRegistryService with database persistence and company scoping.

Endpoints:
    - POST /api/agents: Create a new agent definition
    - GET /api/agents: List agents (filterable by archetype)
    - GET /api/agents/{agent_id}: Get a single agent
    - PUT /api/agents/{agent_id}: Update an agent definition
    - DELETE /api/agents/{agent_id}: Soft-delete an agent

References:
    - Design doc Section 5: FastAPI Router
    - Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.agent import AgentCreateRequest, AgentResponse
from alcoabase.services.agent_registry import (
    AgentInUseError,
    AgentNotFoundError,
    AgentRegistryService,
    AgentValidationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


# ---------------------------------------------------------------------------
# Dependency: AgentRegistryService
# ---------------------------------------------------------------------------

_agent_registry_service: AgentRegistryService | None = None


def set_agent_registry_service(service: AgentRegistryService) -> None:
    """Set the module-level AgentRegistryService instance.

    Called during application startup to wire the service into the router.

    Args:
        service: The initialized AgentRegistryService instance.
    """
    global _agent_registry_service
    _agent_registry_service = service


def get_agent_registry_service() -> AgentRegistryService:
    """Provide the AgentRegistryService as a FastAPI dependency.

    Returns:
        The module-level AgentRegistryService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _agent_registry_service is None:
        raise HTTPException(
            status_code=503,
            detail="Agent registry service is not available.",
        )
    return _agent_registry_service


# ---------------------------------------------------------------------------
# CRUD Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent(
    request: AgentCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentResponse:
    """Create a new agent definition.

    Validates the request body against the Agent Schema and persists
    the agent to the database scoped to the requesting company.

    Args:
        request: Agent creation request body.
        tenant: Resolved tenant context (company_id, user_id).
        service: AgentRegistryService dependency.

    Returns:
        The created agent definition with HTTP 201.

    Raises:
        HTTPException 422: If the agent definition fails schema validation.
    """
    try:
        agent = await service.create_agent(
            data=request.model_dump(exclude_none=True),
            company_id=tenant.company_id,
            user_id=tenant.user_id,
        )
    except AgentValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": "Validation failed", "errors": e.errors},
        )

    return AgentResponse.model_validate(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    archetype: str | None = Query(default=None, description="Filter by archetype"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: AgentRegistryService = Depends(get_agent_registry_service),
) -> list[AgentResponse]:
    """List active agent definitions for the current company.

    Optionally filter by archetype using the `archetype` query parameter.

    Args:
        archetype: Optional archetype filter.
        tenant: Resolved tenant context (company_id).
        service: AgentRegistryService dependency.

    Returns:
        List of active agent definitions.
    """
    agents = await service.list_agents(
        company_id=tenant.company_id,
        archetype=archetype,
    )
    return [AgentResponse.model_validate(agent) for agent in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentResponse:
    """Get a single agent definition by ID.

    Returns 404 if the agent does not exist or does not belong to
    the requesting company.

    Args:
        agent_id: The agent's primary key.
        tenant: Resolved tenant context (company_id).
        service: AgentRegistryService dependency.

    Returns:
        The agent definition.

    Raises:
        HTTPException 404: If agent not found or wrong company.
    """
    agent = await service.get_agent(agent_id=agent_id, company_id=tenant.company_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse.model_validate(agent)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: int,
    request: AgentCreateRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AgentRegistryService = Depends(get_agent_registry_service),
) -> AgentResponse:
    """Update an existing agent definition.

    Validates the request body against the Agent Schema and updates
    the agent in the database. Returns 404 if the agent does not exist
    or does not belong to the requesting company.

    Args:
        agent_id: The agent's primary key.
        request: Updated agent definition request body.
        tenant: Resolved tenant context (company_id).
        service: AgentRegistryService dependency.

    Returns:
        The updated agent definition with HTTP 200.

    Raises:
        HTTPException 404: If agent not found or wrong company.
        HTTPException 422: If the agent definition fails schema validation.
    """
    try:
        agent = await service.update_agent(
            agent_id=agent_id,
            data=request.model_dump(exclude_none=True),
            company_id=tenant.company_id,
        )
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent not found")
    except AgentValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={"message": "Validation failed", "errors": e.errors},
        )

    return AgentResponse.model_validate(agent)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: int,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AgentRegistryService = Depends(get_agent_registry_service),
) -> None:
    """Soft-delete an agent definition.

    Sets is_active to False. Returns 409 if the agent is currently
    assigned to an active review pipeline.

    Args:
        agent_id: The agent's primary key.
        tenant: Resolved tenant context (company_id).
        service: AgentRegistryService dependency.

    Raises:
        HTTPException 404: If agent not found or wrong company.
        HTTPException 409: If agent is assigned to an active pipeline.
    """
    try:
        await service.delete_agent(agent_id=agent_id, company_id=tenant.company_id)
    except AgentNotFoundError:
        raise HTTPException(status_code=404, detail="Agent not found")
    except AgentInUseError:
        raise HTTPException(
            status_code=409,
            detail="Agent is assigned to active pipeline",
        )
