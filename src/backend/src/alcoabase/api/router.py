"""Main API router aggregating all sub-routers for AlcoaBase.

This module defines the top-level API router and registers all
domain sub-routers. Concrete implementations are imported from
their respective modules.
"""

from fastapi import APIRouter

from alcoabase.api.audit import router as audit_router
from alcoabase.api.companies import router as companies_router
from alcoabase.api.documents import router as documents_router
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

# ---------------------------------------------------------------------------
# Main API router — all domain routers are included under /api
# ---------------------------------------------------------------------------
api_router = APIRouter(prefix="/api")
validation_router = APIRouter(prefix="/validation", tags=["Validation"])

# ---------------------------------------------------------------------------
# Register all sub-routers on the main API router
# ---------------------------------------------------------------------------
api_router.include_router(companies_router)
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
api_router.include_router(models_router)
api_router.include_router(memberships_router)
api_router.include_router(agent_activations_router)
