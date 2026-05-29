"""FastAPI dependency injection functions for AlcoaBase.

This package provides reusable FastAPI dependencies for:
- Tenant context resolution (multi-tenancy)
- RBAC permission enforcement
"""

from alcoabase.dependencies.rbac import require_permission
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context

__all__ = ["TenantContext", "get_tenant_context", "require_permission"]
