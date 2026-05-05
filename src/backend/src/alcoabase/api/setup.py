"""FastAPI router for the Setup Wizard endpoints.

Provides the first-run initialization flow: status check, root admin
creation, company creation, AI mode configuration, and setup completion.

Endpoints:
    GET  /status   - Get current setup progress (no auth)
    POST /admin    - Create root admin account (no auth)
    POST /company  - Create initial company (JWT required)
    POST /ai-mode  - Configure AI hardware mode (JWT required)
    POST /complete - Finalize setup (JWT required)

References:
    - Design doc: .kiro/specs/setup-wizard/design.md
    - Requirements: 3.1, 3.3, 3.6, 4.1, 4.3, 5.1, 6.1, 6.3, 7.1, 7.4, 8.1, 8.2, 8.3
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.database import get_db_session
from alcoabase.schemas.setup import (
    AIModeConfig,
    AIModeResult,
    CompanyResult,
    CompanySetupCreate,
    RootAdminCreate,
    RootAdminResult,
    SetupCompleteRequest,
    SetupCompleteResult,
    SetupProgress,
)
from alcoabase.services.setup_service import SetupService

router = APIRouter(tags=["Setup"])
security = HTTPBearer()

# JWT algorithm matching the one used in SetupService
JWT_ALGORITHM = "HS256"


async def get_current_admin_id(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> int:
    """Extract and validate the admin user ID from the JWT Bearer token.

    Decodes the token using the application secret key and returns the
    user ID from the 'sub' claim.

    Args:
        credentials: The HTTP Bearer token credentials extracted from
            the Authorization header.

    Returns:
        The admin user ID as an integer.

    Raises:
        HTTPException: 401 if the token is missing, invalid, or cannot
            be decoded.
    """
    settings = get_settings()
    token = credentials.credentials

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: missing subject claim",
            )
        return int(sub)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired token: {exc}",
        )


@router.get("/status", response_model=SetupProgress)
async def get_setup_status(
    session: AsyncSession = Depends(get_db_session),
) -> SetupProgress:
    """Get the current setup wizard progress.

    Returns which setup steps have been completed. This endpoint
    requires no authentication since it must be accessible before
    any user exists.

    Args:
        session: Database session.

    Returns:
        SetupProgress indicating completion state of each step.
    """
    service = SetupService(session)
    return await service.get_status()


@router.post("/admin", response_model=RootAdminResult, status_code=201)
async def create_root_admin(
    data: RootAdminCreate,
    session: AsyncSession = Depends(get_db_session),
) -> RootAdminResult:
    """Create the root administrator account.

    This is the first setup step. No authentication is required since
    no user exists yet. Returns a JWT access token for subsequent
    setup steps.

    Args:
        data: Root admin creation request with username, email,
            password, and full_name.
        session: Database session.

    Returns:
        RootAdminResult with user_id, username, and access_token.

    Raises:
        HTTPException: 409 if admin already exists.
        HTTPException: 422 if password validation fails.
    """
    service = SetupService(session)
    return await service.create_root_admin(data)


@router.post("/company", response_model=CompanyResult, status_code=201)
async def create_initial_company(
    data: CompanySetupCreate,
    session: AsyncSession = Depends(get_db_session),
    admin_id: int = Depends(get_current_admin_id),
) -> CompanyResult:
    """Create the initial company (tenant).

    Requires JWT authentication from the root admin created in the
    previous step. Generates or validates the slug, creates the company,
    and assigns the admin as company admin.

    Args:
        data: Company creation request with display_name, optional slug,
            and regulatory_framework.
        session: Database session.
        admin_id: The authenticated admin's user ID from the JWT.

    Returns:
        CompanyResult with company_id, slug, and display_name.

    Raises:
        HTTPException: 401 if token is invalid.
        HTTPException: 409 if company already exists.
        HTTPException: 422 if slug is invalid.
    """
    service = SetupService(session)
    return await service.create_initial_company(data, admin_id)


@router.post("/ai-mode", response_model=AIModeResult)
async def configure_ai_mode(
    data: AIModeConfig,
    session: AsyncSession = Depends(get_db_session),
    admin_id: int = Depends(get_current_admin_id),
) -> AIModeResult:
    """Configure the AI hardware mode.

    Requires JWT authentication. Performs a non-blocking connectivity
    check for "gpu" or "cpu" modes. If the check fails, a warning is
    returned but the configuration still succeeds.

    Args:
        data: AI mode configuration request with mode selection.
        session: Database session.
        admin_id: The authenticated admin's user ID from the JWT.

    Returns:
        AIModeResult with the configured mode and optional warning.

    Raises:
        HTTPException: 401 if token is invalid.
    """
    service = SetupService(session)
    return await service.configure_ai_mode(data)


@router.post("/complete", response_model=SetupCompleteResult)
async def complete_setup(
    data: SetupCompleteRequest,
    session: AsyncSession = Depends(get_db_session),
    admin_id: int = Depends(get_current_admin_id),
) -> SetupCompleteResult:
    """Finalize the setup wizard.

    Requires JWT authentication. Validates that all required steps
    (admin, company, AI mode) are complete. Optionally seeds demo data.
    After completion, setup endpoints become permanently inaccessible.

    Args:
        data: Setup completion request with optional seed_demo_data flag.
        session: Database session.
        admin_id: The authenticated admin's user ID from the JWT.

    Returns:
        SetupCompleteResult with completion message and timestamp.

    Raises:
        HTTPException: 401 if token is invalid.
        HTTPException: 400 if required setup steps are incomplete.
    """
    service = SetupService(session)
    return await service.complete_setup(admin_id, data.seed_demo_data)
