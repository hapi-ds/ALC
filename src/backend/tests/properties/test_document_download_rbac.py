"""Property-based tests for RBAC Enforcement Consistency.

Tests Property 3 from the document-content-viewer design document, validating
that for any user/document combination, the download endpoint grants access
(returns 200) if and only if `check_document_access` returns True, and denies
access (returns 403) if and only if it returns False. No file bytes are
transmitted when access is denied.

**Validates: Requirements 1.4, 6.2, 6.3**

References:
    - Design: .kiro/specs/document-content-viewer/design.md (Correctness Property 3)
    - Requirements: .kiro/specs/document-content-viewer/requirements.md (1.4, 6.2, 6.3)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import hypothesis.strategies as st
import pytest
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings

from alcoabase.api.documents import get_document_service, get_storage_service
from alcoabase.database import get_db_session
from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.main import app
from alcoabase.models.document import Document, DocumentVersion


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

st_user_id = st.integers(min_value=1, max_value=10000)
st_company_id = st.integers(min_value=1, max_value=10000)
st_access_granted = st.booleans()


@st.composite
def st_rbac_scenario(draw: st.DrawFn) -> tuple[int, int, bool]:
    """Generate a random (user_id, company_id, access_granted) tuple.

    Returns:
        A tuple representing a user/document access scenario.
    """
    user_id = draw(st_user_id)
    company_id = draw(st_company_id)
    access_granted = draw(st_access_granted)
    return (user_id, company_id, access_granted)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOCUMENT_UUID = "2025-00001"
MAJOR_VERSION = 1
MINOR_VERSION = 0
DOWNLOAD_URL = f"/api/documents/{DOCUMENT_UUID}/versions/{MAJOR_VERSION}/{MINOR_VERSION}/download"
FILE_CONTENT = b"test file content for RBAC property test"


def _make_mock_document() -> Document:
    """Create a mock Document instance."""
    doc = MagicMock(spec=Document)
    doc.document_uuid = DOCUMENT_UUID
    doc.title = "Test Document"
    doc.company_id = 1
    return doc


def _make_mock_version() -> DocumentVersion:
    """Create a mock DocumentVersion instance."""
    version = MagicMock(spec=DocumentVersion)
    version.major_version = MAJOR_VERSION
    version.minor_version = MINOR_VERSION
    version.storage_key = "documents/2025-00001/1.0/test.pdf"
    version.content_type = "application/pdf"
    return version


# ---------------------------------------------------------------------------
# Property 3: RBAC Enforcement Consistency
# ---------------------------------------------------------------------------


# Feature: document-content-viewer, Property 3: RBAC Enforcement Consistency
@settings(max_examples=200, deadline=None)
@given(scenario=st_rbac_scenario())
@pytest.mark.asyncio
async def test_download_grants_access_iff_check_returns_true(
    scenario: tuple[int, int, bool],
) -> None:
    """For any user/document combination, the download endpoint SHALL grant
    access (HTTP 200) if and only if check_document_access returns True,
    and SHALL deny access (HTTP 403) if and only if it returns False.

    **Validates: Requirements 1.4, 6.2, 6.3**
    """
    user_id, company_id, access_granted = scenario

    # Create mock services
    mock_service = AsyncMock()
    mock_service.get_document = AsyncMock(return_value=_make_mock_document())
    mock_service.get_version = AsyncMock(return_value=_make_mock_version())
    mock_service.check_document_access = AsyncMock(return_value=access_granted)

    mock_storage = AsyncMock()
    mock_storage.download_file = AsyncMock(return_value=FILE_CONTENT)

    mock_session = AsyncMock()

    # Set up dependency overrides
    def _override_tenant() -> TenantContext:
        return TenantContext(
            company_id=company_id,
            company_slug="test-company",
            user_id=user_id,
            membership_role="member",
        )

    async def _override_db_session():
        yield mock_session

    app.dependency_overrides[get_tenant_context] = _override_tenant
    app.dependency_overrides[get_db_session] = _override_db_session
    app.dependency_overrides[get_document_service] = lambda: mock_service
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch(
                "alcoabase.api.documents.log_document_access", new_callable=AsyncMock
            ):
                response = await client.get(DOWNLOAD_URL)

        if access_granted:
            assert response.status_code == 200, (
                f"Expected HTTP 200 when access_granted=True for "
                f"user_id={user_id}, company_id={company_id}, "
                f"but got {response.status_code}: {response.text}"
            )
            # Verify file bytes were served
            assert response.content == FILE_CONTENT, (
                f"Expected file content to be served when access is granted, "
                f"but got different content."
            )
        else:
            assert response.status_code == 403, (
                f"Expected HTTP 403 when access_granted=False for "
                f"user_id={user_id}, company_id={company_id}, "
                f"but got {response.status_code}: {response.text}"
            )
            # Verify no file bytes are transmitted when access is denied
            assert response.content != FILE_CONTENT, (
                f"File bytes should NOT be transmitted when access is denied."
            )

        # Verify check_document_access was called with correct parameters
        mock_service.check_document_access.assert_called_once()
        call_kwargs = mock_service.check_document_access.call_args
        assert call_kwargs.kwargs["user_id"] == user_id
        assert call_kwargs.kwargs["company_id"] == company_id
        assert call_kwargs.kwargs["action"] == "read"

    finally:
        app.dependency_overrides.clear()


# Feature: document-content-viewer, Property 3: RBAC Enforcement Consistency
@settings(max_examples=200, deadline=None)
@given(scenario=st_rbac_scenario())
@pytest.mark.asyncio
async def test_denied_access_never_calls_storage_download(
    scenario: tuple[int, int, bool],
) -> None:
    """For any user/document combination where access is denied,
    the endpoint SHALL NOT call storage.download_file — ensuring
    no file bytes are retrieved or transmitted.

    **Validates: Requirements 1.4, 6.2, 6.3**
    """
    user_id, company_id, access_granted = scenario

    # Create mock services
    mock_service = AsyncMock()
    mock_service.get_document = AsyncMock(return_value=_make_mock_document())
    mock_service.get_version = AsyncMock(return_value=_make_mock_version())
    mock_service.check_document_access = AsyncMock(return_value=access_granted)

    mock_storage = AsyncMock()
    mock_storage.download_file = AsyncMock(return_value=FILE_CONTENT)

    mock_session = AsyncMock()

    # Set up dependency overrides
    def _override_tenant() -> TenantContext:
        return TenantContext(
            company_id=company_id,
            company_slug="test-company",
            user_id=user_id,
            membership_role="member",
        )

    async def _override_db_session():
        yield mock_session

    app.dependency_overrides[get_tenant_context] = _override_tenant
    app.dependency_overrides[get_db_session] = _override_db_session
    app.dependency_overrides[get_document_service] = lambda: mock_service
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with patch(
                "alcoabase.api.documents.log_document_access", new_callable=AsyncMock
            ):
                await client.get(DOWNLOAD_URL)

        if not access_granted:
            # Storage should never be called when access is denied
            mock_storage.download_file.assert_not_called()
        else:
            # Storage should be called exactly once when access is granted
            mock_storage.download_file.assert_called_once()

    finally:
        app.dependency_overrides.clear()
