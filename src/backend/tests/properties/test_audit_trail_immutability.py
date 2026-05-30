"""Property-based tests for audit trail immutability enforcement.

Property 15: Immutability enforcement

For any HTTP request using PUT, PATCH, or DELETE methods against any audit
trail endpoint path, regardless of the requesting user's role or permissions,
the service SHALL return HTTP 403 with the message "Audit records are
immutable per ALCOA+ and CFR 21 Part 11".

**Validates: Requirements 8.1, 8.2, 8.4**

References:
    - Design: .kiro/specs/Step_6-3_audit-trail-viewer/design.md
    - Requirements: .kiro/specs/Step_6-3_audit-trail-viewer/requirements.md
    - Module: src/backend/src/alcoabase/api/audit_trail.py
"""

from __future__ import annotations

import hypothesis.strategies as st
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings

from alcoabase.api.audit_trail import router

# ---------------------------------------------------------------------------
# Test application setup
# ---------------------------------------------------------------------------

# Create a minimal FastAPI app with only the audit trail router mounted
# at the same prefix as in production (/api/audit-trail).
# This avoids needing the full app with all middleware and dependencies.
_app = FastAPI()
_app.include_router(router, prefix="/api")

_client = TestClient(_app, raise_server_exceptions=False)

# ---------------------------------------------------------------------------
# Expected immutability response
# ---------------------------------------------------------------------------

_IMMUTABILITY_MESSAGE = (
    "Audit records are immutable per ALCOA+ and CFR 21 Part 11"
)

# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# HTTP methods that should be blocked
MUTATION_METHODS = st.sampled_from(["PUT", "PATCH", "DELETE"])

# User roles — immutability applies regardless of role
USER_ROLES = st.sampled_from([
    "system_admin",
    "doc_admin",
    "it_admin",
    "operator",
    "viewer",
    "quality_manager",
    "auditor",
])

# Random user IDs
USER_IDS = st.integers(min_value=1, max_value=10000)

# Random company IDs
COMPANY_IDS = st.integers(min_value=1, max_value=1000)

# Path segments that could appear in audit trail URLs
PATH_SEGMENTS = st.sampled_from([
    "",
    "documents",
    "templates",
    "reports",
    "workflows",
    "signatures",
    "training_tasks",
    "training_records",
    "export",
    "1",
    "42",
    "999",
    "documents/1/5",
    "templates/10/20",
    "export/abc-123",
    "some/nested/path",
])

# Generate random alphanumeric path segments
RANDOM_PATH_SEGMENTS = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N"),
        whitelist_characters="-_/",
    ),
    min_size=1,
    max_size=50,
).filter(lambda s: not s.startswith("/") and "//" not in s)


# Combined path strategy: either known paths or random paths
AUDIT_TRAIL_PATHS = st.one_of(PATH_SEGMENTS, RANDOM_PATH_SEGMENTS)


# ---------------------------------------------------------------------------
# Property 15: Immutability enforcement
# Tag: Feature: Step_6-3_audit-trail-viewer, Property 15: Immutability enforcement
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    method=MUTATION_METHODS,
    path=AUDIT_TRAIL_PATHS,
    user_id=USER_IDS,
    company_id=COMPANY_IDS,
    role=USER_ROLES,
)
def test_immutability_enforcement_rejects_all_mutations(
    method: str,
    path: str,
    user_id: int,
    company_id: int,
    role: str,
) -> None:
    """For any HTTP request using PUT, PATCH, or DELETE methods against any
    audit trail endpoint path, regardless of the requesting user's role or
    permissions, the service SHALL return HTTP 403 with the message
    "Audit records are immutable per ALCOA+ and CFR 21 Part 11".

    This property generates random combinations of:
    - HTTP methods (PUT, PATCH, DELETE)
    - Audit trail sub-paths (root, known paths, random paths)
    - User roles (including system_admin)
    - Auth headers with varying user/company IDs

    All combinations must be rejected with HTTP 403 and the immutability message.

    **Validates: Requirements 8.1, 8.2, 8.4**
    """
    # Build the full URL path
    if path:
        url = f"/api/audit-trail/{path}"
    else:
        url = "/api/audit-trail/"

    # Build headers simulating an authenticated user with a specific role
    headers = {
        "X-User-Id": str(user_id),
        "X-Company-Id": str(company_id),
        "X-User-Role": role,
        "Content-Type": "application/json",
    }

    # Make the request using the appropriate method
    response = _client.request(method, url, headers=headers, json={})

    # Assert immutability enforcement
    assert response.status_code == 403, (
        f"Expected HTTP 403 for {method} {url} with role={role}, "
        f"got {response.status_code}: {response.text}"
    )

    response_body = response.json()
    assert response_body["detail"] == _IMMUTABILITY_MESSAGE, (
        f"Expected immutability message for {method} {url}, "
        f"got: {response_body.get('detail')}"
    )
