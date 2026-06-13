"""ALC Corporate Environment seed service orchestrator.

Implements the ALCSeedService class that initializes the dedicated "ALC"
company tenant within AlcoaBase's multi-tenancy framework. The service
provisions company entity, user pool, regulatory configuration, governance
folder structure, AI risk profile, agent activations, and a governance
workflow definition.

All operations run within the caller-provided session transaction.
The service does NOT commit — the caller (API route or CLI) manages
the transaction boundary.

References:
    - Design doc: .kiro/specs/Step_8-2_alc-corporate-environment-setup/design.md
    - Requirements: 6.1, 6.3, 6.4, 6.6, 6.7
"""

import logging
import time

from passlib.context import CryptContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.config import get_settings
from alcoabase.models.agent import AgentDefinition
from alcoabase.models.company import Company, CompanyAgentActivation, CompanyMembership
from alcoabase.models.document import Document
from alcoabase.models.setup_status import SetupStatus
from alcoabase.models.system_config import SystemConfiguration
from alcoabase.models.user import Role, User, UserRole
from alcoabase.models.virtual_folder import VirtualFolder
from alcoabase.schemas.alc_seed import (
    AgentResult,
    FolderResult,
    SeedReport,
    UserPoolResult,
)
from alcoabase.services.alc_seed_constants import (
    ALC_AUDIT_CONFIG,
    ALC_COMPANY_DATA,
    ALC_GOVERNANCE_FOLDERS,
    ALC_REGULATORY_BASELINE,
    ALC_USER_POOL,
)

logger = logging.getLogger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class ALCSeedService:
    """Orchestrates ALC corporate environment seeding.

    All operations run within the caller-provided session transaction.
    The service does NOT commit — the caller (API route or CLI) manages
    the transaction boundary.

    Attributes:
        session: The async database session for persistence operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the seed service with a database session.

        Args:
            session: An async SQLAlchemy session. The caller is responsible
                for managing the transaction boundary (commit/rollback).
        """
        self._session = session

    async def execute(self) -> SeedReport:
        """Run the full seeding sequence and return a SeedReport.

        Executes each seeding step in order:
        1. Create or retrieve the ALC company
        2. Provision the corporate user pool
        3. Apply regulatory baseline configuration
        4. Create governance folder structure
        5. Configure AI risk profile
        6. Activate global agents
        7. Create governance workflow definition

        Returns:
            SeedReport summarizing all entities created or skipped.
        """
        start_time = time.monotonic()
        logger.info("Starting ALC corporate environment seeding", extra={"seed_step": "execute"})

        # Step 1: Create or retrieve the ALC company
        company, company_created = await self._create_company()
        logger.info(
            "Company step complete: %s (created=%s)",
            company.slug,
            company_created,
            extra={"seed_step": "create_company"},
        )

        # Step 2: Provision the corporate user pool
        user_pool_result = await self._provision_users(company)
        logger.info(
            "User pool step complete: %d created, %d skipped",
            len(user_pool_result.users_created),
            len(user_pool_result.users_skipped),
            extra={"seed_step": "provision_users"},
        )

        # Step 3: Find the IT admin user for subsequent steps
        it_admin = await self._find_it_admin()

        # Step 4: Apply regulatory baseline configuration
        baseline_created, audit_created = await self._apply_regulatory_baseline(
            company, it_admin
        )
        logger.info(
            "Regulatory baseline step complete: baseline_created=%s, audit_created=%s",
            baseline_created,
            audit_created,
            extra={"seed_step": "apply_regulatory_baseline"},
        )

        # Step 5: Create governance folder structure
        folder_result = await self._create_folder_structure(company, it_admin)
        logger.info(
            "Folder structure step complete: %d created, %d skipped",
            len(folder_result.folders_created),
            len(folder_result.folders_skipped),
            extra={"seed_step": "create_folder_structure"},
        )

        # Step 6: Configure AI risk profile
        risk_profile_created = await self._configure_risk_profile(company, it_admin)
        logger.info(
            "Risk profile step complete: created=%s",
            risk_profile_created,
            extra={"seed_step": "configure_risk_profile"},
        )

        # Step 7: Activate global agents
        agent_result = await self._activate_agents(company)
        logger.info(
            "Agent activation step complete: %d activated, %d skipped",
            len(agent_result.agents_activated),
            len(agent_result.agents_skipped),
            extra={"seed_step": "activate_agents"},
        )

        # Step 8: Create governance workflow
        workflow_created = await self._create_governance_workflow(company, it_admin)
        logger.info(
            "Governance workflow step complete: created=%s",
            workflow_created,
            extra={"seed_step": "create_governance_workflow"},
        )

        # Step 9: Upload governance documents
        docs_uploaded, docs_skipped = await self._upload_governance_documents(
            company, it_admin
        )
        logger.info(
            "Governance documents step complete: %d uploaded, %d skipped",
            len(docs_uploaded),
            len(docs_skipped),
            extra={"seed_step": "upload_governance_documents"},
        )

        # Assemble the final report
        total_duration_ms = int((time.monotonic() - start_time) * 1000)
        report = SeedReport(
            company_id=company.id,
            company_slug=ALC_COMPANY_DATA["slug"],
            users_created=user_pool_result.users_created,
            users_skipped=user_pool_result.users_skipped,
            folders_created=folder_result.folders_created,
            folders_skipped=folder_result.folders_skipped,
            risk_profile_created=risk_profile_created,
            regulatory_baseline_created=baseline_created,
            audit_config_created=audit_created,
            agents_activated=agent_result.agents_activated,
            agents_skipped=agent_result.agents_skipped,
            workflow_created=workflow_created,
            documents_uploaded=docs_uploaded,
            documents_skipped=docs_skipped,
            total_duration_ms=total_duration_ms,
        )

        logger.info(
            "ALC corporate environment seeding complete in %dms",
            total_duration_ms,
            extra={"seed_step": "execute"},
        )
        return report

    async def _find_it_admin(self) -> User:
        """Query the IT admin user by username from the database.

        Looks up the "alc-it-admin" user which should have been created
        during the _provision_users step.

        Returns:
            The IT admin User instance.

        Raises:
            RuntimeError: If the IT admin user cannot be found in the database.
        """
        stmt = select(User).where(User.username == "alc-it-admin")
        result = await self._session.execute(stmt)
        it_admin = result.scalars().first()

        if it_admin is None:
            raise RuntimeError(
                "ALC IT Administrator user (alc-it-admin) not found. "
                "User provisioning may have failed or been skipped."
            )

        return it_admin

    async def _create_company(self) -> tuple[Company, bool]:
        """Create or retrieve the ALC company.

        Queries for an existing company by slug 'alc-corporate'. If found,
        skips creation and returns the existing entity. If not found, creates
        a new Company with all attributes from ALC_COMPANY_DATA.

        Returns:
            A tuple of (company, was_created) where was_created is True
            if the company was newly created, False if it already existed.
        """
        stmt = select(Company).where(Company.slug == ALC_COMPANY_DATA["slug"])
        result = await self._session.execute(stmt)
        existing = result.scalars().first()

        if existing is not None:
            logger.info(
                "ALC company already exists, reusing",
                extra={"seed_step": "create_company"},
            )
            return (existing, False)

        company = Company(
            slug=ALC_COMPANY_DATA["slug"],
            display_name=ALC_COMPANY_DATA["display_name"],
            regulatory_framework=ALC_COMPANY_DATA["regulatory_framework"],
            audit_config=ALC_COMPANY_DATA["audit_config"],
            is_active=True,
        )
        self._session.add(company)
        await self._session.flush()

        logger.info(
            "ALC company created",
            extra={"seed_step": "create_company"},
        )
        return (company, True)

    async def _provision_users(self, company: Company) -> UserPoolResult:
        """Create corporate user pool.

        Loops through ALC_USER_POOL, checks existence by username and email,
        creates User, Role (if not exists with company_id and is_system=True),
        UserRole, and CompanyMembership records. Hashes password using the
        configured ALC_SEED_DEFAULT_PASSWORD.

        Also checks if the root admin user (from Setup Wizard) needs a
        CompanyMembership for the ALC company.

        Args:
            company: The ALC company entity.

        Returns:
            UserPoolResult with created/skipped username lists.
        """
        settings = get_settings()
        hashed_password = _pwd_context.hash(settings.alc_seed_default_password)

        created: list[str] = []
        skipped: list[str] = []

        for user_def in ALC_USER_POOL:
            username = user_def["username"]
            email = user_def["email"]
            role_name = user_def["role"]

            # Check if username already exists
            stmt = select(User).where(User.username == username)
            result = await self._session.execute(stmt)
            existing_user = result.scalars().first()

            if existing_user is not None:
                logger.info(
                    "User already exists, skipping: %s",
                    username,
                    extra={"seed_step": "provision_users"},
                )
                skipped.append(username)
                continue

            # Check for email conflict
            stmt = select(User).where(User.email == email)
            result = await self._session.execute(stmt)
            email_conflict = result.scalars().first()

            if email_conflict is not None:
                logger.warning(
                    "Email conflict for user '%s': email '%s' already in use by '%s', skipping",
                    username,
                    email,
                    email_conflict.username,
                    extra={"seed_step": "provision_users"},
                )
                skipped.append(username)
                continue

            # Create User record
            user = User(
                username=username,
                full_name=user_def["full_name"],
                email=email,
                hashed_password=hashed_password,
                is_active=True,
            )
            self._session.add(user)
            await self._session.flush()

            # Create or get Role (company-scoped, is_system=True)
            role = await self._get_or_create_role(role_name, company.id)

            # Create UserRole association
            stmt = UserRole.insert().values(user_id=user.id, role_id=role.id)
            await self._session.execute(stmt)

            # Create CompanyMembership
            membership = CompanyMembership(
                user_id=user.id,
                company_id=company.id,
                role=role_name,
                role_id=role.id,
            )
            self._session.add(membership)

            logger.info(
                "User created: %s (role=%s)",
                username,
                role_name,
                extra={"seed_step": "provision_users"},
            )
            created.append(username)

        # Check root admin CompanyMembership
        await self._ensure_root_admin_membership(company)

        await self._session.flush()

        return UserPoolResult(users_created=created, users_skipped=skipped)

    async def _get_or_create_role(self, role_name: str, company_id: int) -> Role:
        """Get or create a company-scoped system role.

        Args:
            role_name: The role name (e.g. "system_administrator").
            company_id: The company ID to scope the role to.

        Returns:
            The existing or newly created Role record.
        """
        stmt = select(Role).where(
            Role.name == role_name,
            Role.company_id == company_id,
        )
        result = await self._session.execute(stmt)
        role = result.scalars().first()

        if role is None:
            role = Role(
                name=role_name,
                company_id=company_id,
                is_system=True,
            )
            self._session.add(role)
            await self._session.flush()

        return role

    async def _ensure_root_admin_membership(self, company: Company) -> None:
        """Ensure the root admin user has a CompanyMembership for the ALC company.

        Queries the SetupStatus to find the root admin user_id. If the root
        admin has no active CompanyMembership (revoked_at IS NULL) for the
        ALC company, creates one with the system_administrator role.

        Args:
            company: The ALC company entity.
        """
        # Get root admin user_id from setup_status
        stmt = select(SetupStatus)
        result = await self._session.execute(stmt)
        setup_status = result.scalars().first()

        if setup_status is None or setup_status.root_admin_id is None:
            logger.info(
                "No root admin found in setup_status, skipping root admin membership",
                extra={"seed_step": "provision_users"},
            )
            return

        root_admin_id = setup_status.root_admin_id

        # Check if root admin already has an active membership for this company
        stmt = select(CompanyMembership).where(
            CompanyMembership.user_id == root_admin_id,
            CompanyMembership.company_id == company.id,
            CompanyMembership.revoked_at.is_(None),
        )
        result = await self._session.execute(stmt)
        existing_membership = result.scalars().first()

        if existing_membership is not None:
            logger.info(
                "Root admin already has active ALC company membership, skipping",
                extra={"seed_step": "provision_users"},
            )
            return

        # Get or create the system_administrator role for this company
        role = await self._get_or_create_role("system_administrator", company.id)

        # Create CompanyMembership for root admin
        membership = CompanyMembership(
            user_id=root_admin_id,
            company_id=company.id,
            role="system_administrator",
            role_id=role.id,
        )
        self._session.add(membership)

        logger.info(
            "Created ALC company membership for root admin (user_id=%d)",
            root_admin_id,
            extra={"seed_step": "provision_users"},
        )

    async def _apply_regulatory_baseline(
        self, company: Company, it_admin: User
    ) -> tuple[bool, bool]:
        """Create SystemConfiguration rows for regulatory baseline and audit config.

        Checks for existing rows by category. Since SystemConfiguration uses
        globally unique category names (no company_id column), the ALC-prefixed
        categories are inherently company-specific.

        Args:
            company: The ALC company entity.
            it_admin: The IT administrator user for updated_by attribution.

        Returns:
            A tuple of (baseline_created, audit_created) booleans.
        """
        # Check for existing regulatory baseline
        result = await self._session.execute(
            select(SystemConfiguration).where(
                SystemConfiguration.category == "alc_regulatory_baseline"
            )
        )
        existing_baseline = result.scalars().first()

        baseline_created = False
        if existing_baseline is None:
            baseline_row = SystemConfiguration(
                category="alc_regulatory_baseline",
                config_values=ALC_REGULATORY_BASELINE,
                updated_by=it_admin.id,
            )
            self._session.add(baseline_row)
            baseline_created = True
            logger.info(
                "Created SystemConfiguration: alc_regulatory_baseline",
                extra={"seed_step": "apply_regulatory_baseline"},
            )
        else:
            logger.info(
                "Skipped SystemConfiguration: alc_regulatory_baseline (already exists)",
                extra={"seed_step": "apply_regulatory_baseline"},
            )

        # Check for existing audit config
        result = await self._session.execute(
            select(SystemConfiguration).where(
                SystemConfiguration.category == "alc_audit_config"
            )
        )
        existing_audit = result.scalars().first()

        audit_created = False
        if existing_audit is None:
            audit_row = SystemConfiguration(
                category="alc_audit_config",
                config_values=ALC_AUDIT_CONFIG,
                updated_by=it_admin.id,
            )
            self._session.add(audit_row)
            audit_created = True
            logger.info(
                "Created SystemConfiguration: alc_audit_config",
                extra={"seed_step": "apply_regulatory_baseline"},
            )
        else:
            logger.info(
                "Skipped SystemConfiguration: alc_audit_config (already exists)",
                extra={"seed_step": "apply_regulatory_baseline"},
            )

        # Flush to ensure rows are persisted within the transaction
        await self._session.flush()

        return (baseline_created, audit_created)

    async def _create_folder_structure(
        self, company: Company, it_admin: User
    ) -> FolderResult:
        """Create governance virtual folders.

        Iterates through ALC_GOVERNANCE_FOLDERS and creates each VirtualFolder
        if it does not already exist for the given company. All folders are
        marked as system defaults and attributed to the IT Administrator.

        Args:
            company: The ALC company entity.
            it_admin: The IT administrator user for created_by attribution.

        Returns:
            FolderResult with created/skipped folder name lists.

        Raises:
            RuntimeError: If it_admin is None, indicating the required
                ALC IT Administrator user account is missing.
        """
        if it_admin is None:
            raise RuntimeError(
                "ALC IT Administrator user account is required for "
                "governance folder creation but was not found. "
                "Ensure user provisioning completed successfully."
            )

        created: list[str] = []
        skipped: list[str] = []

        for folder_def in ALC_GOVERNANCE_FOLDERS:
            folder_name = folder_def["name"]

            # Check if folder already exists for this company
            stmt = select(VirtualFolder).where(
                VirtualFolder.name == folder_name,
                VirtualFolder.company_id == company.id,
            )
            result = await self._session.execute(stmt)
            existing = result.scalars().first()

            if existing is not None:
                logger.info(
                    "Governance folder already exists, skipping: %s",
                    folder_name,
                    extra={"seed_step": "create_folder_structure"},
                )
                skipped.append(folder_name)
                continue

            folder = VirtualFolder(
                name=folder_name,
                tag_filter=folder_def["tag_filter"],
                sort_order=folder_def["sort_order"],
                company_id=company.id,
                is_system_default=True,
                created_by=it_admin.id,
            )
            self._session.add(folder)
            logger.info(
                "Governance folder created: %s",
                folder_name,
                extra={"seed_step": "create_folder_structure"},
            )
            created.append(folder_name)

        await self._session.flush()

        return FolderResult(folders_created=created, folders_skipped=skipped)

    async def _configure_risk_profile(
        self, company: Company, it_admin: User
    ) -> bool:
        """Create CompanyRiskProfile for the ALC company.

        Checks for an existing active profile, verifies all 8 required
        AITaskType records exist and are active, then creates a new
        CompanyRiskProfile with empty overrides (no RiskTierOverride or
        RiskAssessmentRecord records).

        Args:
            company: The ALC company entity.
            it_admin: The IT administrator user for created_by attribution.

        Returns:
            True if a new risk profile was created, False if one already existed.

        Raises:
            RuntimeError: If any of the 8 required AITaskType records are
                missing or inactive.
        """
        from alcoabase.models.risk_framework import AITaskType, CompanyRiskProfile

        # Check for existing active CompanyRiskProfile
        stmt = select(CompanyRiskProfile).where(
            CompanyRiskProfile.company_id == company.id,
            CompanyRiskProfile.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        existing = result.scalars().first()

        if existing is not None:
            logger.info(
                "Active CompanyRiskProfile already exists for ALC company, skipping",
                extra={"seed_step": "configure_risk_profile"},
            )
            return False

        # Verify all 8 required AITaskType records exist and are active
        required_task_type_ids = [
            "rag_knowledge_query",
            "document_search",
            "template_analysis",
            "change_impact_analysis",
            "traceability_gap_discovery",
            "document_generation",
            "multi_agent_audit",
            "training_content_generation",
        ]

        stmt = select(AITaskType).where(
            AITaskType.task_type_id.in_(required_task_type_ids),
            AITaskType.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        found_types = result.scalars().all()
        found_type_ids = {t.task_type_id for t in found_types}

        missing_types = [
            tid for tid in required_task_type_ids if tid not in found_type_ids
        ]
        if missing_types:
            raise RuntimeError(
                f"Cannot create ALC risk profile: missing or inactive AITaskType records: {missing_types}"
            )

        # Create CompanyRiskProfile with empty overrides
        profile = CompanyRiskProfile(
            company_id=company.id,
            profile_name="ALC Corporate Risk Profile",
            description=(
                "Baseline risk profile for AlcoaBase corporate environment "
                "\u2014 software platform development and governance context"
            ),
            regulatory_frameworks=["ISO_27001", "ISO_9001", "EU_AI_Act"],
            is_active=True,
            created_by=it_admin.id,
        )
        self._session.add(profile)
        await self._session.flush()

        logger.info(
            "CompanyRiskProfile created for ALC company",
            extra={"seed_step": "configure_risk_profile"},
        )
        return True

    async def _activate_agents(self, company: Company) -> AgentResult:
        """Activate all global agents for the ALC company.

        Queries all global AgentDefinition records (company_id IS NULL,
        is_active=True) and ensures each has an active CompanyAgentActivation
        for the given company. Existing active activations are skipped,
        inactive ones are reactivated, and missing ones are created.

        Args:
            company: The ALC company entity.

        Returns:
            AgentResult with activated/skipped agent name lists.
        """
        activated: list[str] = []
        skipped: list[str] = []

        # Query all global agent definitions
        stmt = select(AgentDefinition).where(
            AgentDefinition.company_id.is_(None),
            AgentDefinition.is_active == True,  # noqa: E712
        )
        result = await self._session.execute(stmt)
        global_agents = result.scalars().all()

        if not global_agents:
            logger.info(
                "No global agents found",
                extra={"seed_step": "activate_agents"},
            )
            return AgentResult(agents_activated=[], agents_skipped=[])

        for agent in global_agents:
            # Check for existing activation
            activation_stmt = select(CompanyAgentActivation).where(
                CompanyAgentActivation.agent_definition_id == agent.id,
                CompanyAgentActivation.company_id == company.id,
            )
            activation_result = await self._session.execute(activation_stmt)
            existing = activation_result.scalars().first()

            if existing is not None:
                if existing.is_active:
                    # Already active — skip
                    skipped.append(agent.name)
                else:
                    # Inactive — reactivate
                    existing.is_active = True
                    existing.config_overrides = {}
                    activated.append(agent.name)
            else:
                # Missing — create new activation
                activation = CompanyAgentActivation(
                    agent_definition_id=agent.id,
                    company_id=company.id,
                    is_active=True,
                    config_overrides={},
                )
                self._session.add(activation)
                activated.append(agent.name)

        await self._session.flush()

        return AgentResult(agents_activated=activated, agents_skipped=skipped)

    async def _create_governance_workflow(
        self, company: Company, it_admin: User
    ) -> bool:
        """Create governance WorkflowDefinition and WorkflowVersion.

        Args:
            company: The ALC company entity.
            it_admin: The IT administrator user for created_by attribution.

        Returns:
            True if the workflow was newly created, False if it already existed.
        """
        from alcoabase.models.workflow import WorkflowDefinition

        # Check if governance workflow already exists
        existing = await self._session.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.company_id == company.id,
                WorkflowDefinition.name == "ALC Governance Workflow",
            )
        )
        if existing.scalar_one_or_none() is not None:
            return False

        bpmn_xml = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">
  <bpmn:process id="alc-governance" name="ALC Governance Workflow">
    <bpmn:startEvent id="start" name="Draft"/>
    <bpmn:task id="review" name="Review"/>
    <bpmn:task id="approved" name="Approved"/>
    <bpmn:task id="active" name="Active"/>
    <bpmn:endEvent id="end" name="Archived"/>
    <bpmn:sequenceFlow sourceRef="start" targetRef="review"/>
    <bpmn:sequenceFlow sourceRef="review" targetRef="approved"/>
    <bpmn:sequenceFlow sourceRef="approved" targetRef="active"/>
    <bpmn:sequenceFlow sourceRef="active" targetRef="end"/>
  </bpmn:process>
</bpmn:definitions>"""

        workflow = WorkflowDefinition(
            name="ALC Governance Workflow",
            document_tag="governance",
            bpmn_xml=bpmn_xml,
            signature_required_transitions=["Review→Approved"],
            training_trigger_transitions=["Approved→Active"],
            is_active=True,
            created_by=it_admin.id,
            company_id=company.id,
            risk_level="high",
        )
        self._session.add(workflow)
        await self._session.flush()
        return True

    # ─────────────────────────────────────────────────────────────────────
    # Governance Document Upload
    # ─────────────────────────────────────────────────────────────────────

    # Static governance documents shipped with the project.
    # These are uploaded as documents into the ALC corporate company
    # during the seed, with document_type "governance".
    GOVERNANCE_DOCUMENTS = [
        {
            "title": "User Requirement Specification (URS) — AlcoaBase",
            "filename": "URS-AlcoaBase-Enhanced.md",
            "document_type": "urs",
            "folder_path": "/governance/urs",
        },
        {
            "title": "AI Regulatory Guidelines — Cross-Sector Compliance",
            "filename": "AI-Regulatory-Guidelines.md",
            "document_type": "guideline",
            "folder_path": "/governance/ai-guidelines",
        },
        {
            "title": "AlcoaBase User Guide",
            "filename": "User-Guide-AlcoaBase.md",
            "document_type": "user_guide",
            "folder_path": "/governance/user-guides",
        },
        {
            "title": "AlcoaBase Administrator Guide",
            "filename": "Admin-Guide-AlcoaBase.md",
            "document_type": "admin_guide",
            "folder_path": "/governance/admin-guides",
        },
    ]

    async def _upload_governance_documents(
        self, company: Company, it_admin: User
    ) -> tuple[list[str], list[str]]:
        """Upload static governance documents into the ALC corporate company.

        Reads markdown files from docs/governance/ and creates Document
        records. Skips documents that already exist (matched by title).

        Args:
            company: The ALC company entity.
            it_admin: User for created_by attribution.

        Returns:
            Tuple of (uploaded titles, skipped titles).
        """
        import pathlib

        uploaded: list[str] = []
        skipped: list[str] = []

        # Resolve the governance docs directory relative to the project root
        # In Docker, the project is at /app; docs/ is at /app/docs/governance/
        # We also check the workspace root for dev environments.
        possible_paths = [
            pathlib.Path("/app/docs/governance"),
            pathlib.Path(__file__).parents[4] / "docs" / "governance",
        ]

        docs_dir: pathlib.Path | None = None
        for p in possible_paths:
            if p.is_dir():
                docs_dir = p
                break

        if docs_dir is None:
            logger.warning(
                "Governance docs directory not found. Skipping document upload.",
                extra={"seed_step": "upload_governance_documents"},
            )
            return (uploaded, skipped)

        for doc_def in self.GOVERNANCE_DOCUMENTS:
            title = doc_def["title"]

            # Check if document already exists
            existing = await self._session.execute(
                select(Document).where(
                    Document.title == title,
                    Document.company_id == company.id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped.append(title)
                continue

            # Read the file content
            filepath = docs_dir / doc_def["filename"]
            if not filepath.exists():
                logger.warning(
                    "Governance doc file not found: %s",
                    filepath,
                    extra={"seed_step": "upload_governance_documents"},
                )
                skipped.append(title)
                continue

            # Create the document record (file storage is handled separately
            # by the document service on actual upload; here we create the
            # metadata record so it appears in the system)
            from datetime import datetime, timezone

            year = datetime.now(timezone.utc).year
            # Generate a unique UUID by counting ALL existing docs globally
            count_result = await self._session.execute(
                select(func.count(Document.id))
            )
            next_seq = (count_result.scalar_one() or 0) + 1
            document_uuid = f"{year}-{next_seq:05d}"

            doc = Document(
                document_uuid=document_uuid,
                title=title,
                folder_path=doc_def["folder_path"],
                document_type=doc_def["document_type"],
                current_status="Approved",
                created_by=it_admin.id,
                company_id=company.id,
                is_demo_data=False,
            )
            self._session.add(doc)
            await self._session.flush()
            uploaded.append(title)

            logger.info(
                "Governance document created: %s",
                title,
                extra={"seed_step": "upload_governance_documents"},
            )

        await self._session.flush()
        return (uploaded, skipped)
