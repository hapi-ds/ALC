"""FastAPI router for per-company agent activation management endpoints.

Provides endpoints for activating, deactivating, and listing global agent
definitions within a company's tenant context.

Endpoints:
    POST /api/companies/{slug}/agents/{agent_id}/activate - Activate global agent for company
    DELETE /api/companies/{slug}/agents/{agent_id}/deactivate - Deactivate agent for company
    GET /api/companies/{slug}/agents - List activated agents for company

References:
    - Design doc: .kiro/specs/multi-tenancy/design.md
    - Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.database import get_db_session
from alcoabase.models.agent import AgentDefinition
from alcoabase.models.company import Company, CompanyAgentActivation
from alcoabase.schemas.company import (
    AgentActivationCreate,
    AgentActivationResponse,
)

router = APIRouter(prefix="/companies/{slug}/agents", tags=["Agent Activations"])


@router.post(
    "/{agent_id}/activate", response_model=AgentActivationResponse, status_code=201
)
async def activate_agent(
    slug: str,
    agent_id: int,
    payload: AgentActivationCreate,
    session: AsyncSession = Depends(get_db_session),
) -> AgentActivationResponse:
    """Activate a global agent definition for a company.

    Creates a CompanyAgentActivation record linking the specified global
    agent to the company. Only global agents (company_id IS NULL) can be
    activated this way.

    Args:
        slug: The unique URL-safe identifier of the company.
        agent_id: The ID of the global agent definition to activate.
        payload: Activation request body with optional config_overrides.
        session: Database session.

    Returns:
        The created activation record.

    Raises:
        HTTPException: 404 if company not found.
        HTTPException: 404 if agent definition not found.
        HTTPException: 403 if agent is not global (has a company_id).
        HTTPException: 409 if agent is already activated for this company.
    """
    # TODO: Add auth guard — Company Admin only
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    agent_result = await session.execute(
        select(AgentDefinition).where(AgentDefinition.id == agent_id)
    )
    agent = agent_result.scalar_one_or_none()

    if agent is None:
        raise HTTPException(status_code=404, detail="Agent definition not found.")

    if agent.company_id is not None:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify global agent. Create a company-scoped override instead.",
        )

    activation = CompanyAgentActivation(
        company_id=company.id,
        agent_definition_id=agent_id,
        config_overrides=payload.config_overrides or {},
        is_active=True,
    )
    session.add(activation)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Agent is already activated for this company.",
        )

    return AgentActivationResponse.model_validate(activation)


@router.delete("/{agent_id}/deactivate", response_model=AgentActivationResponse)
async def deactivate_agent(
    slug: str,
    agent_id: int,
    session: AsyncSession = Depends(get_db_session),
) -> AgentActivationResponse:
    """Deactivate an agent for a company.

    Sets is_active=False on the activation record rather than deleting it,
    preserving audit history.

    Args:
        slug: The unique URL-safe identifier of the company.
        agent_id: The ID of the agent definition to deactivate.
        session: Database session.

    Returns:
        The updated activation record with is_active=False.

    Raises:
        HTTPException: 404 if company not found.
        HTTPException: 404 if activation record not found.
    """
    # TODO: Add auth guard — Company Admin only
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    activation_result = await session.execute(
        select(CompanyAgentActivation).where(
            CompanyAgentActivation.company_id == company.id,
            CompanyAgentActivation.agent_definition_id == agent_id,
        )
    )
    activation = activation_result.scalar_one_or_none()

    if activation is None:
        raise HTTPException(
            status_code=404, detail="Agent activation not found for this company."
        )

    activation.is_active = False
    await session.flush()
    return AgentActivationResponse.model_validate(activation)


@router.get("", response_model=list[AgentActivationResponse])
async def list_activated_agents(
    slug: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[AgentActivationResponse]:
    """List all active agent activations for a company.

    Returns only activations where is_active=True.

    Args:
        slug: The unique URL-safe identifier of the company.
        session: Database session.

    Returns:
        List of active agent activation records for the company.

    Raises:
        HTTPException: 404 if company not found.
    """
    # TODO: Add auth guard — Company Member
    result = await session.execute(select(Company).where(Company.slug == slug))
    company = result.scalar_one_or_none()

    if company is None:
        raise HTTPException(status_code=404, detail="Company not found.")

    activations_result = await session.execute(
        select(CompanyAgentActivation).where(
            CompanyAgentActivation.company_id == company.id,
            CompanyAgentActivation.is_active == True,  # noqa: E712
        )
    )
    activations = activations_result.scalars().all()
    return [AgentActivationResponse.model_validate(a) for a in activations]
