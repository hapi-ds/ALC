"""Shared pytest fixtures for AlcoaBase backend tests.

Provides:
- Database setup fixtures (mock async sessions)
- MinIO/storage mock fixtures
- Test user creation fixtures
- Common test data factories

References:
    - Task 22.1: Create pytest fixtures for database setup, MinIO mock, and test user creation
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from alcoabase.models.document import Document, DocumentVersion
from alcoabase.models.user import User


# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def async_session() -> AsyncMock:
    """Create a mock AsyncSession for database operations.

    Provides a session with mocked add, flush, execute, commit,
    and rollback methods.

    Returns:
        Mock AsyncSession instance.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    session.close = AsyncMock()
    return session


@pytest.fixture
def db_session_factory(async_session: AsyncMock):
    """Create a session factory that returns the mock session.

    Args:
        async_session: The mock session to return.

    Returns:
        Async context manager yielding the mock session.
    """
    async def _factory():
        yield async_session

    return _factory


# ---------------------------------------------------------------------------
# Storage Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Create a mock MinIO/S3 storage service.

    Provides upload, download, and delete operations that
    succeed by default.

    Returns:
        Mock StorageService instance.
    """
    storage = AsyncMock()
    storage.upload_file = AsyncMock(return_value="documents/test/1.0/file.pdf")
    storage.download_file = AsyncMock(return_value=b"mock file content")
    storage.delete_file = AsyncMock()
    storage.file_exists = AsyncMock(return_value=True)
    return storage


# ---------------------------------------------------------------------------
# User Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def test_user() -> User:
    """Create a test user with admin role.

    Returns:
        User instance with ID=1 and admin role.
    """
    user = User(
        id=1,
        username="testuser",
        email="test@alcoabase.local",
        hashed_password="hashed_password_placeholder",
        is_active=True,
    )
    return user


@pytest.fixture
def csv_test_user() -> User:
    """Create a CSV validation test user.

    Returns:
        User instance configured as CSV test user.
    """
    user = User(
        id=99,
        username="csv_test_user",
        email="csv@alcoabase.local",
        hashed_password="hashed_password_placeholder",
        is_active=True,
    )
    return user


# ---------------------------------------------------------------------------
# Document Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_document() -> Document:
    """Create a sample document for testing.

    Returns:
        Document instance with standard test values.
    """
    return Document(
        id=1,
        document_uuid="2025-00001",
        title="Test SOP Document",
        folder_path="/sops/lab-a",
        document_type="SOP",
        current_status="Draft",
        created_by=1,
    )


@pytest.fixture
def sample_document_version() -> DocumentVersion:
    """Create a sample document version for testing.

    Returns:
        DocumentVersion instance with standard test values.
    """
    return DocumentVersion(
        id=1,
        document_id=1,
        major_version=1,
        minor_version=0,
        storage_key="documents/2025-00001/1.0/test.pdf",
        file_hash="a" * 128,
        uploaded_by=1,
        change_reason="Initial upload",
    )


# ---------------------------------------------------------------------------
# UUID Service Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_uuid_service() -> AsyncMock:
    """Create a mock UUIDService.

    Returns:
        Mock UUIDService with predictable UUID generation.
    """
    svc = AsyncMock()
    svc.generate_document_uuid = AsyncMock(return_value="2025-00001")
    svc.generate_field_uuid = MagicMock(return_value="FLD-ABCD1234")
    return svc


# ---------------------------------------------------------------------------
# Timestamp Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fixed_timestamp() -> datetime:
    """Provide a fixed UTC timestamp for deterministic tests.

    Returns:
        Fixed datetime in UTC.
    """
    return datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC)
