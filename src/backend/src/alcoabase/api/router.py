"""Main API router aggregating all sub-routers for AlcoaBase.

This module defines the top-level API router and registers all
domain sub-routers. Concrete implementations are imported from
their respective modules.
"""

from fastapi import APIRouter

from alcoabase.api.audit import router as audit_router
from alcoabase.api.audit_trail import router as audit_trail_router
from alcoabase.api.companies import router as companies_router
from alcoabase.api.setup import router as setup_router
from alcoabase.api.documents import router as documents_router
from alcoabase.api.document_generation import router as document_generation_router
from alcoabase.api.document_review import router as document_review_router
from alcoabase.api.document_templates import router as document_templates_router
from alcoabase.api.models import router as models_router
from alcoabase.api.reports import router as reports_router
from alcoabase.api.search import router as search_router
from alcoabase.api.signatures import router as signatures_router
from alcoabase.api.templates import router as templates_router
from alcoabase.api.training import router as training_router
from alcoabase.api.virtual_folders import router as virtual_folders_router
from alcoabase.api.workflows import router as workflows_router
from alcoabase.api.knowledge import router as knowledge_router
from alcoabase.api.agents import router as agents_router
from alcoabase.api.memberships import router as memberships_router
from alcoabase.api.agent_activations import router as agent_activations_router
from alcoabase.api.audit_profiles import router as audit_profiles_router
from alcoabase.api.compliance import router as compliance_router
from alcoabase.api.reviews import router as reviews_router
from alcoabase.api.video_alignment import router as video_alignment_router
from alcoabase.api.training_feedback import router as training_feedback_router
from alcoabase.api.training_materials import router as training_materials_router
from alcoabase.api.training_planner import router as training_planner_router
from alcoabase.api.training_questions import router as training_questions_router
from alcoabase.api.training_roleplay import router as training_roleplay_router
from alcoabase.api.admin_memberships import router as admin_memberships_router
from alcoabase.api.admin_permission_templates import (
    router as admin_permission_templates_router,
)
from alcoabase.api.admin_documentation import router as admin_documentation_router
from alcoabase.api.admin_guidelines import router as admin_guidelines_router
from alcoabase.api.admin_seed import router as admin_seed_router
from alcoabase.api.admin_roles import router as admin_roles_router
from alcoabase.api.admin_urs import router as admin_urs_router
from alcoabase.api.admin_users import router as admin_users_router
from alcoabase.api.auth import auth_router
from alcoabase.api.impact_analysis import router as impact_analysis_router
from alcoabase.api.system_config import router as system_config_router
from alcoabase.api.risk_framework import router as risk_framework_router
from alcoabase.api.ingestion_router import router as ingestion_router
from alcoabase.api.literature_router import router as literature_router
from alcoabase.api.literature_search import router as literature_search_citation_router
from alcoabase.api.literature_search_router import router as literature_search_router
from alcoabase.api.literature_index_router import router as literature_index_router
from alcoabase.api.literature_screening_router import (
    router as literature_screening_router,
)
from alcoabase.api.literature_review_router import (
    router as literature_review_router,
)
from alcoabase.api.literature_contradiction_router import (
    router as literature_contradiction_router,
)
from alcoabase.api.traceability import router as traceability_router
from alcoabase.api.vigilance_signal_router import router as vigilance_signal_router
from alcoabase.api.vigilance_product_router import (
    profile_router as vigilance_profile_router,
    router as vigilance_product_router,
)
from alcoabase.api.vigilance_report_router import router as vigilance_report_router

# ---------------------------------------------------------------------------
# Main API router — all domain routers are included under /api
# ---------------------------------------------------------------------------
api_router = APIRouter(prefix="/api")
validation_router = APIRouter(prefix="/validation", tags=["Validation"])

# ---------------------------------------------------------------------------
# Register all sub-routers on the main API router
# ---------------------------------------------------------------------------
api_router.include_router(companies_router)
api_router.include_router(document_templates_router)
api_router.include_router(document_generation_router)
api_router.include_router(document_review_router)
api_router.include_router(documents_router)
api_router.include_router(virtual_folders_router)
api_router.include_router(templates_router)
api_router.include_router(reports_router)
api_router.include_router(workflows_router)
api_router.include_router(signatures_router)
api_router.include_router(training_router)
api_router.include_router(search_router)
api_router.include_router(knowledge_router)
api_router.include_router(agents_router)
api_router.include_router(validation_router)
api_router.include_router(audit_router)
api_router.include_router(audit_trail_router)
api_router.include_router(models_router)
api_router.include_router(memberships_router)
api_router.include_router(agent_activations_router)
api_router.include_router(audit_profiles_router)
api_router.include_router(reviews_router)
api_router.include_router(video_alignment_router)
api_router.include_router(training_feedback_router)
api_router.include_router(training_materials_router)
api_router.include_router(training_planner_router)
api_router.include_router(training_questions_router)
api_router.include_router(training_roleplay_router)
api_router.include_router(compliance_router)
api_router.include_router(impact_analysis_router)
api_router.include_router(system_config_router)
api_router.include_router(traceability_router)
api_router.include_router(admin_users_router)
api_router.include_router(admin_roles_router)
api_router.include_router(admin_permission_templates_router)
api_router.include_router(admin_memberships_router)
api_router.include_router(admin_seed_router)
api_router.include_router(admin_urs_router)
api_router.include_router(admin_guidelines_router)
api_router.include_router(admin_documentation_router)
api_router.include_router(risk_framework_router)
api_router.include_router(literature_router)
api_router.include_router(literature_search_router)
api_router.include_router(literature_search_citation_router)
api_router.include_router(literature_index_router)
api_router.include_router(literature_screening_router)
api_router.include_router(literature_review_router)
api_router.include_router(literature_contradiction_router)
api_router.include_router(ingestion_router)
api_router.include_router(vigilance_product_router)
api_router.include_router(vigilance_profile_router)
api_router.include_router(vigilance_signal_router)
api_router.include_router(vigilance_report_router)
api_router.include_router(setup_router, prefix="/v1/setup")
api_router.include_router(auth_router, prefix="/v1/auth")
