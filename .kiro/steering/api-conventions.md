# API Conventions

## URL Prefixes

- Backend API base prefix is `/api` (NOT `/api/v1`) for most endpoints
- Only `/api/v1/auth` and `/api/v1/setup` use the `v1` prefix
- Router file: `src/backend/src/alcoabase/api/router.py`
- Individual routers define their own sub-prefix (e.g., `/documents`, `/templates`)
- Final paths: `/api/documents`, `/api/templates`, `/api/workflows`, etc.

## Audit Middleware (CRITICAL)

- The `AuditMiddleware` requires an `X-Change-Reason` header on ALL mutating requests (POST, PUT, PATCH, DELETE)
- Requests without this header get HTTP 400: "X-Change-Reason header is required for mutating requests to GxP-relevant endpoints."
- Exempt paths: `/health`, `/docs`, `/openapi.json`, `/redoc`, `/api/v1/auth`, `/api/v1/setup`
- Middleware source: `src/backend/src/alcoabase/middleware/audit_middleware.py`

## Required Headers for API Calls

| Header | When | Purpose |
|--------|------|---------|
| `Authorization: Bearer {token}` | All authenticated requests | Auth |
| `X-User-Id` | All authenticated requests | Audit trail attribution |
| `X-Company-Id` | All tenant-scoped requests | Multi-tenancy |
| `X-Change-Reason` | All POST/PUT/PATCH/DELETE (except exempt paths) | ALCOA+ compliance |

## Frontend API Client

- Located at `src/frontend/src/lib/apiClient.ts`
- `apiClient.get()` — JSON GET requests
- `apiClient.post()` — JSON POST requests (auto-sets Content-Type: application/json)
- `apiClient.upload()` — Multipart POST (does NOT set Content-Type, browser handles boundary)
- All methods support 401 retry with token refresh

## Before Writing Frontend API Integration

**Always read the actual backend router file first** to confirm:
1. The exact URL path (check prefix in router.py + sub-prefix in the domain router)
2. Required headers (especially X-Change-Reason for mutations)
3. Request format (JSON body vs. multipart form vs. query params)
4. Response schema (check the Pydantic response_model)
