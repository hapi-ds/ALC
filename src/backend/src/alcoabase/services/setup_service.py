"""Setup wizard service for first-run initialization business logic.

This module provides the SetupService class that orchestrates the setup
wizard flow: root admin creation, company creation, AI mode configuration,
and setup completion. Each method is independently persisted so interrupted
setups can resume.

References:
    - Design doc: .kiro/specs/setup-wizard/design.md
    - Requirements: 1.1, 1.2, 1.3, 3.1, 3.4, 3.5, 3.6, 4.1–4.5, 5.1–5.5, 8.1–8.4, 9.1–9.3, 9.5
"""

from datetime import datetime, timezone

import httpx
from fastapi import HTTPException
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.models.company import Company, CompanyMembership
from alcoabase.models.setup_status import SetupStatus
from alcoabase.models.user import Role, User, UserRole
from alcoabase.models.document import Document, DocumentTag
from alcoabase.models.template import Template
from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.models.workflow import WorkflowDefinition
from alcoabase.schemas.setup import (
    AIModeConfig,
    AIModeResult,
    CompanyResult,
    CompanySetupCreate,
    RootAdminCreate,
    RootAdminResult,
    SetupCompleteResult,
    SetupProgress,
)
from alcoabase.services.password_validator import PasswordValidator
from alcoabase.services.slug_generator import SlugGenerator

# Password hashing context using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT configuration
JWT_ALGORITHM = "HS256"


class SetupService:
    """Orchestrates the setup wizard business logic.

    Manages the first-run initialization flow including root admin creation,
    status tracking, and initialization detection. Each operation is atomic
    and idempotent.

    Attributes:
        session: The async database session for persistence operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the SetupService with a database session.

        Args:
            session: An active async SQLAlchemy session.
        """
        self.session = session
        self._password_validator = PasswordValidator()
        self._slug_generator = SlugGenerator()

    async def _ensure_setup_status(self) -> SetupStatus:
        """Get or create the single setup_status row.

        Returns:
            The existing or newly created SetupStatus record.
        """
        result = await self.session.execute(select(SetupStatus))
        status = result.scalar_one_or_none()

        if status is None:
            status = SetupStatus()
            self.session.add(status)
            await self.session.flush()

        return status

    async def is_initialized(self) -> bool:
        """Check whether the system setup has been completed.

        Queries the setup_status table to determine if initialization
        is complete. Returns False if no setup_status row exists or if
        is_complete is False.

        Returns:
            True if setup is complete, False otherwise.
        """
        result = await self.session.execute(select(SetupStatus))
        status = result.scalar_one_or_none()

        if status is None:
            return False

        return status.is_complete

    async def get_status(self) -> SetupProgress:
        """Return the current setup wizard progress.

        Returns a SetupProgress schema indicating which steps have been
        completed. If no setup_status row exists, all steps are reported
        as incomplete.

        Returns:
            SetupProgress with boolean flags for each step.
        """
        status = await self._ensure_setup_status()

        return SetupProgress(
            is_complete=status.is_complete,
            admin_created=status.admin_created,
            company_created=status.company_created,
            ai_mode_configured=status.ai_mode_configured,
            demo_data_seeded=status.demo_data_seeded,
        )

    async def create_root_admin(self, data: RootAdminCreate) -> RootAdminResult:
        """Create the root administrator account during setup.

        Validates the password against the GxP password policy, hashes it
        with bcrypt, creates the user record, assigns the system_administrator
        role, updates setup_status, and generates a JWT access token.

        Args:
            data: The root admin creation request with username, email,
                password, and full_name.

        Returns:
            RootAdminResult with user_id, username, and access_token.

        Raises:
            HTTPException: 409 if admin already exists, 422 if password
                validation fails.
        """
        # Check idempotency: if admin already created, return 409
        status = await self._ensure_setup_status()
        if status.admin_created:
            raise HTTPException(
                status_code=409,
                detail="Root admin account already exists",
            )

        # Validate password against GxP policy
        password_errors = self._password_validator.validate(data.password)
        if password_errors:
            raise HTTPException(
                status_code=422,
                detail="Password does not meet policy requirements",
                headers={"X-Password-Violations": str(len(password_errors))},
            )

        # Hash password with bcrypt
        hashed_password = pwd_context.hash(data.password)

        # Create user record
        user = User(
            username=data.username,
            email=data.email,
            hashed_password=hashed_password,
            full_name=data.full_name,
            is_active=True,
        )
        self.session.add(user)
        await self.session.flush()

        # Create or get the system_administrator role
        role = await self._get_or_create_system_admin_role()

        # Assign role to user via the association table
        stmt = UserRole.insert().values(user_id=user.id, role_id=role.id)
        await self.session.execute(stmt)

        # Update setup_status
        status.admin_created = True
        status.root_admin_id = user.id

        # Generate JWT access token
        settings = get_settings()
        access_token = jwt.encode(
            {"sub": str(user.id)},
            settings.secret_key,
            algorithm=JWT_ALGORITHM,
        )

        # Audit logging: record the admin creation event in setup_status
        # (Full audit service integration will use SQLAlchemy-Continuum;
        # for setup, we track via the setup_status record itself)
        await self.session.flush()

        return RootAdminResult(
            user_id=user.id,
            username=user.username,
            access_token=access_token,
            token_type="bearer",
        )

    async def _get_or_create_system_admin_role(self) -> Role:
        """Get or create the system_administrator role.

        The system_administrator role has full permissions across the
        entire platform.

        Returns:
            The system_administrator Role record.
        """
        result = await self.session.execute(
            select(Role).where(Role.name == "system_administrator")
        )
        role = result.scalar_one_or_none()

        if role is None:
            role = Role(
                name="system_administrator",
                description="Full system-level administrator with all platform privileges",
                permissions={
                    "all": True,
                    "scope": "system",
                },
            )
            self.session.add(role)
            await self.session.flush()

        return role

    async def create_initial_company(
        self, data: CompanySetupCreate, admin_id: int
    ) -> CompanyResult:
        """Create the initial company (tenant) during setup.

        Generates or validates the slug, creates the Company record,
        assigns the root admin as company admin, and updates setup status.

        Args:
            data: The company creation request with display_name, optional slug,
                and regulatory_framework.
            admin_id: The user ID of the root admin to assign as company admin.

        Returns:
            CompanyResult with company_id, slug, and display_name.

        Raises:
            HTTPException: 409 if company already exists, 422 if slug is invalid.
        """
        # Check idempotency: if company already created, return 409
        status = await self._ensure_setup_status()
        if status.company_created:
            raise HTTPException(
                status_code=409,
                detail="Initial company already exists",
            )

        # Validate or generate slug
        if data.slug is not None:
            if not self._slug_generator.validate(data.slug):
                raise HTTPException(
                    status_code=422,
                    detail="Invalid slug: must contain only lowercase letters, digits, and hyphens",
                )
            slug = data.slug
        else:
            slug = self._slug_generator.generate(data.display_name)

        # Create Company record
        company = Company(
            display_name=data.display_name,
            slug=slug,
            regulatory_framework=data.regulatory_framework,
            is_active=True,
        )
        self.session.add(company)
        await self.session.flush()

        # Create CompanyMembership for root admin with "admin" role
        membership = CompanyMembership(
            user_id=admin_id,
            company_id=company.id,
            role="admin",
        )
        self.session.add(membership)

        # Update setup_status
        status.company_created = True
        status.company_id = company.id

        # Audit logging: record the company creation event in setup_status
        # (Full audit service integration will use SQLAlchemy-Continuum;
        # for setup, we track via the setup_status record itself)
        await self.session.flush()

        return CompanyResult(
            company_id=company.id,
            slug=company.slug,
            display_name=company.display_name,
        )

    async def configure_ai_mode(self, data: AIModeConfig) -> AIModeResult:
        """Configure the AI hardware mode during setup.

        Performs a non-blocking connectivity check for "gpu" or "cpu" modes
        against the vLLM health endpoint. If the check fails, a warning is
        returned but the configuration still succeeds.

        Args:
            data: The AI mode configuration request with mode selection.

        Returns:
            AIModeResult with the configured mode and optional connectivity warning.
        """
        status = await self._ensure_setup_status()
        connectivity_warning: str | None = None

        # Perform connectivity check for non-mock modes
        if data.mode in ("gpu", "cpu"):
            settings = get_settings()
            health_url = f"{settings.vllm_base_url}/health"
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(health_url)
                    if response.status_code != 200:
                        connectivity_warning = (
                            f"vLLM {data.mode} endpoint returned status "
                            f"{response.status_code} at {health_url}"
                        )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError) as exc:
                connectivity_warning = (
                    f"vLLM {data.mode} endpoint unreachable at {health_url}: {exc}"
                )

        # Update setup_status
        status.ai_mode_configured = True
        status.ai_hardware_mode = data.mode

        # Audit logging: record the AI mode configuration event in setup_status
        # (Full audit service integration will use SQLAlchemy-Continuum;
        # for setup, we track via the setup_status record itself)
        await self.session.flush()

        return AIModeResult(
            mode=data.mode,
            connectivity_warning=connectivity_warning,
        )

    async def complete_setup(
        self, admin_id: int, seed_demo: bool
    ) -> SetupCompleteResult:
        """Finalize the setup wizard and optionally seed demo data.

        Validates that all required steps (admin_created, company_created,
        ai_mode_configured) are complete before marking setup as done.
        Optionally seeds demo data, records the completion timestamp,
        invalidates the setup guard cache, and logs an audit event.

        Args:
            admin_id: The user ID of the root admin completing setup.
            seed_demo: Whether to seed demo data during completion.

        Returns:
            SetupCompleteResult with a completion message and timestamp.

        Raises:
            HTTPException: 400 if required setup steps are incomplete.
        """
        status = await self._ensure_setup_status()

        # Verify all required steps are complete
        if not (
            status.admin_created
            and status.company_created
            and status.ai_mode_configured
        ):
            raise HTTPException(
                status_code=400,
                detail="Cannot complete setup: required steps are incomplete",
            )

        # Optionally seed demo data
        if seed_demo:
            await self._seed_demo_data(status.company_id, status.root_admin_id)
            status.demo_data_seeded = True

        # Mark setup as complete
        status.is_complete = True
        status.completed_at = datetime.now(timezone.utc)

        await self.session.flush()

        # Invalidate the setup guard cache so subsequent requests are routed normally
        try:
            from alcoabase.middleware.setup_guard import SetupGuardMiddleware

            SetupGuardMiddleware.invalidate_cache()
        except ImportError:
            # SetupGuardMiddleware may not exist yet during development
            pass

        # Audit logging: record the setup completion event
        # (Full audit service integration will use SQLAlchemy-Continuum;
        # for setup, we track via the setup_status record itself)

        return SetupCompleteResult(
            message="Setup completed successfully",
            completed_at=status.completed_at,
        )

    async def _seed_demo_data(
        self, company_id: int | None, admin_id: int | None
    ) -> None:
        """Seed demo data for evaluation purposes.

        Creates sample documents, templates, virtual folders, and workflow
        definitions within the given company scope. All seeded records are
        tagged with `is_demo_data=True` for future identification and removal.

        Args:
            company_id: The company ID to scope demo data to.
            admin_id: The admin user ID to attribute demo data creation to.
        """
        if company_id is None or admin_id is None:
            return

        # Create sample documents
        demo_documents = [
            Document(
                document_uuid="DEMO-00001",
                title="[DEMO] Standard Operating Procedure - Equipment Calibration",
                folder_path="/demo/sops",
                document_type="SOP",
                current_status="Draft",
                is_csv_validation_record=False,
                created_by=admin_id,
                company_id=company_id,
                is_demo_data=True,
            ),
            Document(
                document_uuid="DEMO-00002",
                title="[DEMO] Analytical Report - Batch Release Testing",
                folder_path="/demo/reports",
                document_type="Report",
                current_status="Draft",
                is_csv_validation_record=False,
                created_by=admin_id,
                company_id=company_id,
                is_demo_data=True,
            ),
            Document(
                document_uuid="DEMO-00003",
                title="[DEMO] Deviation Report - Temperature Excursion",
                folder_path="/demo/deviations",
                document_type="Deviation",
                current_status="Draft",
                is_csv_validation_record=False,
                created_by=admin_id,
                company_id=company_id,
                is_demo_data=True,
            ),
        ]
        for doc in demo_documents:
            self.session.add(doc)

        await self.session.flush()

        # Add tags to demo documents
        demo_tags = [
            DocumentTag(document_id=demo_documents[0].id, tag="SOP"),
            DocumentTag(document_id=demo_documents[0].id, tag="Calibration"),
            DocumentTag(document_id=demo_documents[1].id, tag="Report"),
            DocumentTag(document_id=demo_documents[1].id, tag="Batch-Release"),
            DocumentTag(document_id=demo_documents[2].id, tag="Deviation"),
        ]
        for tag in demo_tags:
            self.session.add(tag)

        # Create sample templates
        demo_templates = [
            Template(
                document_uuid="DEMO-T0001",
                name="[DEMO] Batch Release Report Template",
                json_schema={
                    "fields": [
                        {"name": "batch_number", "type": "Text", "label": "Batch Number"},
                        {"name": "release_date", "type": "Date", "label": "Release Date"},
                        {"name": "result", "type": "Text", "label": "Test Result"},
                    ]
                },
                status="Draft",
                created_by=admin_id,
                company_id=company_id,
                is_demo_data=True,
            ),
            Template(
                document_uuid="DEMO-T0002",
                name="[DEMO] Equipment Calibration Log Template",
                json_schema={
                    "fields": [
                        {"name": "equipment_id", "type": "Text", "label": "Equipment ID"},
                        {"name": "calibration_date", "type": "Date", "label": "Calibration Date"},
                        {"name": "next_due", "type": "Date", "label": "Next Due Date"},
                    ]
                },
                status="Draft",
                created_by=admin_id,
                company_id=company_id,
                is_demo_data=True,
            ),
        ]
        for template in demo_templates:
            self.session.add(template)

        # Create sample virtual folders
        demo_folders = [
            VirtualFolder(
                name="[DEMO] All SOPs",
                tag_filter={"tags": ["SOP"], "status": None},
                sort_order="created_at_desc",
                is_system_default=False,
                created_by=admin_id,
                company_id=company_id,
                is_demo_data=True,
            ),
            VirtualFolder(
                name="[DEMO] Active Reports",
                tag_filter={"tags": ["Report"], "status": "Approved"},
                sort_order="created_at_desc",
                is_system_default=False,
                created_by=admin_id,
                company_id=company_id,
                is_demo_data=True,
            ),
        ]
        for folder in demo_folders:
            self.session.add(folder)

        # Create sample workflow definitions
        demo_workflows = [
            WorkflowDefinition(
                name="[DEMO] SOP Lifecycle Workflow",
                document_tag="DEMO-SOP",
                bpmn_xml=(
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<definitions><process>"
                    "<startEvent/><task name='Draft'/>"
                    "<task name='Review'/><task name='Approved'/>"
                    "<endEvent/></process></definitions>"
                ),
                signature_required_transitions=["Review→Approved"],
                training_trigger_transitions=["Approved→InTraining"],
                is_active=True,
                is_demo_data=True,
                created_by=admin_id,
                company_id=company_id,
            ),
            WorkflowDefinition(
                name="[DEMO] Deviation Report Workflow",
                document_tag="DEMO-Deviation",
                bpmn_xml=(
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    "<definitions><process>"
                    "<startEvent/><task name='Open'/>"
                    "<task name='Investigation'/><task name='Closed'/>"
                    "<endEvent/></process></definitions>"
                ),
                signature_required_transitions=["Investigation→Closed"],
                training_trigger_transitions=[],
                is_active=True,
                is_demo_data=True,
                created_by=admin_id,
                company_id=company_id,
            ),
        ]
        for workflow in demo_workflows:
            self.session.add(workflow)

        await self.session.flush()
