"""Property-based tests for Setup Guard Routing Correctness.

Tests Property 1 from the setup-wizard design document, validating that the
SetupGuardMiddleware correctly routes or blocks requests based on the system's
initialization state and the request path.

**Validates: Requirements 1.2, 2.1, 2.2, 2.3, 7.3**

References:
    - Design: .kiro/specs/setup-wizard/design.md (Correctness Property 1)
    - Requirements: .kiro/specs/setup-wizard/requirements.md (Requirements 1, 2, 7)
"""

import hypothesis.strategies as st
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from hypothesis import given, settings

from alcoabase.middleware.setup_guard import SetupGuardMiddleware


# ---------------------------------------------------------------------------
# Test Application
# ---------------------------------------------------------------------------

def _create_test_app() -> FastAPI:
    """Create a minimal FastAPI app with SetupGuardMiddleware for testing.

    The app has catch-all routes that return 200 for any path, allowing us
    to test the middleware's routing logic in isolation without needing a
    database or other dependencies.

    Returns:
        A FastAPI application with the SetupGuardMiddleware installed.
    """
    test_app = FastAPI()
    test_app.add_middleware(SetupGuardMiddleware)

    @test_app.api_route("/health", methods=["GET"])
    async def health():
        return {"status": "ok"}

    @test_app.api_route("/docs", methods=["GET"])
    async def docs():
        return {"docs": True}

    @test_app.api_route("/openapi.json", methods=["GET"])
    async def openapi():
        return {"openapi": "3.0.0"}

    @test_app.api_route("/api/v1/setup/{path:path}", methods=["GET", "POST"])
    async def setup_catchall(path: str = ""):
        return {"setup": True, "path": path}

    @test_app.api_route("/api/v1/setup", methods=["GET", "POST"])
    async def setup_root():
        return {"setup": True, "path": ""}

    @test_app.api_route("/{path:path}", methods=["GET", "POST"])
    async def catchall(path: str = ""):
        return {"allowed": True, "path": path}

    return test_app


# Shared test app instance
_test_app = _create_test_app()


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Path segments that form valid API-like paths
_PATH_SEGMENTS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=1,
    max_size=20,
)


@st.composite
def st_random_api_path(draw: st.DrawFn) -> str:
    """Generate a random API path that is NOT a setup path and NOT always-allowed.

    These paths should be blocked (503) when uninitialized and allowed when initialized.

    Returns:
        A path string like /api/v1/documents/123 or /api/v2/users.
    """
    num_segments = draw(st.integers(min_value=1, max_value=5))
    segments = [draw(_PATH_SEGMENTS) for _ in range(num_segments)]
    path = "/" + "/".join(segments)

    # Ensure it's not a setup path or always-allowed path
    if path.startswith("/api/v1/setup") or path in ("/health", "/docs", "/openapi.json"):
        # Prefix with something else to avoid collision
        path = "/api/v1/other" + path

    return path


@st.composite
def st_setup_path(draw: st.DrawFn) -> str:
    """Generate a valid setup wizard path.

    Returns:
        A path string matching /api/v1/setup or /api/v1/setup/...
    """
    suffix = draw(
        st.sampled_from(
            [
                "",
                "/",
                "/status",
                "/admin",
                "/company",
                "/ai-mode",
                "/complete",
            ]
        )
    )
    return f"/api/v1/setup{suffix}"


def st_always_allowed_path() -> st.SearchStrategy[str]:
    """Generate a path that is always allowed regardless of initialization state.

    Returns:
        Strategy producing one of /health, /docs, /openapi.json.
    """
    return st.sampled_from(["/health", "/docs", "/openapi.json"])


# ---------------------------------------------------------------------------
# Property 1: Setup Guard Routing Correctness
# ---------------------------------------------------------------------------


# Feature: setup-wizard, Property 1: Setup Guard Routing Correctness
@settings(max_examples=100, deadline=None)
@given(
    path=st_random_api_path(),
    is_initialized=st.booleans(),
)
@pytest.mark.asyncio
async def test_setup_guard_routing_non_exempt_paths(
    path: str,
    is_initialized: bool,
) -> None:
    """For any non-exempt, non-setup API path and any initialization state:
    - When uninitialized: returns 503
    - When initialized: allows the request through (200)

    **Validates: Requirements 1.2, 2.1, 2.3**
    """
    from httpx import ASGITransport, AsyncClient

    # Override the cached initialization state directly
    SetupGuardMiddleware._is_initialized = is_initialized

    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    if not is_initialized:
        # Non-exempt, non-setup paths should get 503 when uninitialized
        assert response.status_code == 503, (
            f"Expected 503 for path '{path}' when uninitialized, "
            f"got {response.status_code}"
        )
        body = response.json()
        assert body["detail"] == "System setup required"
        assert body["setup_url"] == "/api/v1/setup/"
    else:
        # When initialized, non-setup paths should be allowed through (200)
        assert response.status_code == 200, (
            f"Expected 200 for path '{path}' when initialized, "
            f"got {response.status_code}"
        )


# Feature: setup-wizard, Property 1: Setup Guard Routing Correctness
@settings(max_examples=100, deadline=None)
@given(
    path=st_setup_path(),
)
@pytest.mark.asyncio
async def test_setup_guard_allows_setup_paths_when_uninitialized(
    path: str,
) -> None:
    """For any setup path (/api/v1/setup/**), when the system is uninitialized,
    the guard SHALL allow the request through (not return 503).

    **Validates: Requirements 2.2**
    """
    from httpx import ASGITransport, AsyncClient

    # Set system as uninitialized
    SetupGuardMiddleware._is_initialized = False

    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    # Setup paths should be allowed through when uninitialized (200)
    assert response.status_code == 200, (
        f"Setup path '{path}' got {response.status_code} when uninitialized — "
        f"expected 200 (allowed through)"
    )


# Feature: setup-wizard, Property 1: Setup Guard Routing Correctness
@settings(max_examples=100, deadline=None)
@given(
    path=st_always_allowed_path(),
)
@pytest.mark.asyncio
async def test_setup_guard_allows_exempt_paths_when_uninitialized(
    path: str,
) -> None:
    """For any always-allowed path (/health, /docs, /openapi.json), when the
    system is uninitialized, the guard SHALL allow the request through.

    **Validates: Requirements 2.3**
    """
    from httpx import ASGITransport, AsyncClient

    # Set system as uninitialized
    SetupGuardMiddleware._is_initialized = False

    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    # Exempt paths should be allowed through when uninitialized (200)
    assert response.status_code == 200, (
        f"Exempt path '{path}' got {response.status_code} when uninitialized — "
        f"expected 200 (allowed through)"
    )


# Feature: setup-wizard, Property 1: Setup Guard Routing Correctness
@settings(max_examples=100, deadline=None)
@given(
    path=st_setup_path(),
)
@pytest.mark.asyncio
async def test_setup_guard_blocks_setup_paths_when_initialized(
    path: str,
) -> None:
    """For any setup path (/api/v1/setup/**), when the system is initialized,
    the guard SHALL return 403.

    **Validates: Requirements 7.3**
    """
    from httpx import ASGITransport, AsyncClient

    # Set system as initialized
    SetupGuardMiddleware._is_initialized = True

    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(path)

    # Setup paths should get 403 when initialized
    assert response.status_code == 403, (
        f"Setup path '{path}' got {response.status_code} when initialized — "
        f"expected 403"
    )
    body = response.json()
    assert body["detail"] == "Setup already completed"
