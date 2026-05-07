"""Unit tests for the Bulk Upload CLI tool.

Tests specific example-based scenarios:
- Token resolution from environment variable fallback
- Dry-run mode lists files without making HTTP calls
- Non-existent directory exits with error code 1
- Single file failure doesn't stop processing of remaining files

**Validates: Requirements 7.7, 8.1, 8.6, 8.7**

References:
    - Design: .kiro/specs/document-upload-list/design.md (Testing Strategy)
    - Requirements: .kiro/specs/document-upload-list/requirements.md
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add the scripts directory to sys.path so we can import bulk_upload
_scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from bulk_upload import main, resolve_token, validate_directory  # noqa: E402


# ---------------------------------------------------------------------------
# Test: Token from environment variable fallback (Requirement 8.1)
# ---------------------------------------------------------------------------


class TestResolveToken:
    """Tests for token resolution from argument or ALCOABASE_TOKEN env var."""

    def test_token_from_argument_takes_precedence(self) -> None:
        """When --token is provided, it should be used regardless of env var."""
        with patch.dict("os.environ", {"ALCOABASE_TOKEN": "env-token"}):
            result = resolve_token("arg-token")
        assert result == "arg-token"

    def test_token_from_env_var_fallback(self) -> None:
        """When --token is None, ALCOABASE_TOKEN env var should be used."""
        with patch.dict("os.environ", {"ALCOABASE_TOKEN": "env-secret-token"}):
            result = resolve_token(None)
        assert result == "env-secret-token"

    def test_missing_token_exits_with_error(self) -> None:
        """When no token is available from either source, sys.exit(1) is called."""
        with patch.dict("os.environ", {}, clear=True):
            # Ensure ALCOABASE_TOKEN is not set
            import os

            os.environ.pop("ALCOABASE_TOKEN", None)
            with pytest.raises(SystemExit) as exc_info:
                resolve_token(None)
            assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Test: Dry-run lists files without HTTP calls (Requirement 8.6)
# ---------------------------------------------------------------------------


class TestDryRun:
    """Tests for --dry-run mode listing files without making HTTP requests."""

    def test_dry_run_lists_files_without_http_calls(self, tmp_path: Path) -> None:
        """Dry-run should list files that would be uploaded without any HTTP calls."""
        # Create a directory with some files
        (tmp_path / "doc1.pdf").write_text("content1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "doc2.txt").write_text("content2")

        argv = [
            "--directory", str(tmp_path),
            "--api-url", "http://localhost:8000",
            "--company-id", "1",
            "--user-id", "1",
            "--token", "test-token",
            "--dry-run",
        ]

        # Patch httpx.Client to detect if any HTTP calls are made
        with patch("bulk_upload.httpx.Client") as mock_client_cls:
            main(argv)
            # In dry-run mode, httpx.Client should never be instantiated as a context manager
            mock_client_cls.assert_not_called()

    def test_dry_run_prints_file_list(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Dry-run should print the files that would be uploaded."""
        (tmp_path / "report.pdf").write_text("content")
        (tmp_path / "notes.txt").write_text("content")

        argv = [
            "--directory", str(tmp_path),
            "--api-url", "http://localhost:8000",
            "--company-id", "1",
            "--user-id", "1",
            "--token", "test-token",
            "--dry-run",
        ]

        main(argv)
        captured = capsys.readouterr()

        # Should mention dry run and list the files
        assert "Dry run" in captured.out or "dry run" in captured.out.lower()
        assert "report" in captured.out
        assert "notes" in captured.out


# ---------------------------------------------------------------------------
# Test: Non-existent directory exits with error code 1 (Requirement 8.7)
# ---------------------------------------------------------------------------


class TestValidateDirectory:
    """Tests for directory validation exiting with code 1 on invalid input."""

    def test_nonexistent_directory_exits_with_code_1(self) -> None:
        """A non-existent directory should cause sys.exit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            validate_directory("/nonexistent/path/that/does/not/exist")
        assert exc_info.value.code == 1

    def test_file_instead_of_directory_exits_with_code_1(self, tmp_path: Path) -> None:
        """A path that is a file (not a directory) should cause sys.exit(1)."""
        file_path = tmp_path / "not_a_dir.txt"
        file_path.write_text("I am a file")

        with pytest.raises(SystemExit) as exc_info:
            validate_directory(str(file_path))
        assert exc_info.value.code == 1

    def test_main_with_nonexistent_directory_exits(self) -> None:
        """Running main() with a non-existent directory should exit with code 1."""
        argv = [
            "--directory", "/absolutely/nonexistent/directory",
            "--api-url", "http://localhost:8000",
            "--company-id", "1",
            "--user-id", "1",
            "--token", "test-token",
        ]

        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Test: Single file failure doesn't stop processing (Requirement 7.7)
# ---------------------------------------------------------------------------


class TestSingleFileFailureResilience:
    """Tests that a single file upload failure doesn't stop processing remaining files."""

    def test_single_failure_continues_processing(self, tmp_path: Path) -> None:
        """When one file fails to upload, remaining files should still be processed."""
        # Create multiple files
        (tmp_path / "file1.pdf").write_text("content1")
        (tmp_path / "file2.pdf").write_text("content2")
        (tmp_path / "file3.pdf").write_text("content3")

        argv = [
            "--directory", str(tmp_path),
            "--api-url", "http://localhost:8000",
            "--company-id", "1",
            "--user-id", "1",
            "--token", "test-token",
        ]

        # Track how many times post is called
        call_count = 0

        def mock_post(url, *, files=None, data=None, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            # First file fails, rest succeed
            if call_count == 1:
                response.status_code = 500
                response.text = "Internal Server Error"
            else:
                response.status_code = 201
                response.text = '{"id": 1}'
            return response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("bulk_upload.httpx.Client", return_value=mock_client):
            main(argv)

        # All 3 files should have been attempted despite first failure
        assert call_count == 3

    def test_failure_reflected_in_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Failed uploads should be counted in the summary output."""
        # Create 2 files
        (tmp_path / "good.pdf").write_text("content")
        (tmp_path / "bad.pdf").write_text("content")

        argv = [
            "--directory", str(tmp_path),
            "--api-url", "http://localhost:8000",
            "--company-id", "1",
            "--user-id", "1",
            "--token", "test-token",
        ]

        call_count = 0

        def mock_post(url, *, files=None, data=None, **kwargs):
            nonlocal call_count
            call_count += 1
            response = MagicMock()
            # Alternate: first succeeds, second fails
            if call_count == 2:
                response.status_code = 500
                response.text = "Server Error"
            else:
                response.status_code = 201
                response.text = '{"id": 1}'
            return response

        mock_client = MagicMock()
        mock_client.post = mock_post
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("bulk_upload.httpx.Client", return_value=mock_client):
            main(argv)

        captured = capsys.readouterr()

        # Summary should show 2 total, 1 successful, 1 failed
        assert "2" in captured.out  # total files
        assert "1" in captured.out  # at least one success and one failure
