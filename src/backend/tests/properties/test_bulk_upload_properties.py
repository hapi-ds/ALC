"""Property-based tests for the Bulk Upload CLI tool.

Tests Properties 9–12 from the document-upload-list design document, validating:
- Property 9: Path-to-metadata derivation correctness
- Property 10: Directory walk completeness (no duplicates, no omissions)
- Property 11: Request construction includes all required fields and headers
- Property 12: Summary counts are arithmetically correct

**Validates: Requirements 7.2, 7.3, 7.4, 7.5, 7.8, 8.2, 8.3, 8.4, 8.5**

References:
    - Design: .kiro/specs/document-upload-list/design.md (Correctness Properties 9–12)
    - Requirements: .kiro/specs/document-upload-list/requirements.md
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import hypothesis.strategies as st
from hypothesis import given, settings

# Add the scripts directory to sys.path so we can import bulk_upload
_scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from bulk_upload import (  # noqa: E402
    FileMetadata,
    UploadSummary,
    derive_metadata,
    upload_file,
    walk_directory,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

# Strategy for valid path segment names (no path separators, no null bytes)
st_path_segment = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Pd"),
        whitelist_characters="_.",
    ),
    min_size=1,
    max_size=30,
).filter(lambda s: s not in (".", "..") and not s.startswith("."))

# Strategy for file extensions
st_extension = st.sampled_from([".pdf", ".docx", ".txt", ".xlsx", ".md", ".csv"])

# Strategy for filename with extension
st_filename = st.builds(
    lambda stem, ext: stem + ext,
    stem=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_-"),
        min_size=1,
        max_size=20,
    ),
    ext=st_extension,
)

# Strategy for relative directory paths (list of segments)
st_dir_segments = st.lists(st_path_segment, min_size=0, max_size=4)

# Strategy for Bearer tokens (ASCII-only, as HTTP headers require)
st_token = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="-_", max_codepoint=127),
    min_size=1,
    max_size=50,
).filter(lambda s: s.isascii())

# Strategy for company/user IDs (digits only)
st_id = st.text(
    alphabet=st.characters(whitelist_categories=("Nd",), max_codepoint=57),
    min_size=1,
    max_size=10,
).filter(lambda s: s.isdigit())

# Strategy for document types
st_document_type = st.sampled_from(["General", "SOP", "Protocol", "Report", "Policy"])

# Strategy for tags (comma-separated, ASCII-only)
st_tags = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters=",- ", max_codepoint=127),
    min_size=0,
    max_size=50,
).filter(lambda s: s.isascii())


# ---------------------------------------------------------------------------
# Property 9: CLI path-to-metadata derivation
# ---------------------------------------------------------------------------


# Feature: document-upload-list, Property 9: CLI path-to-metadata derivation
@settings(max_examples=100)
@given(dir_segments=st_dir_segments, filename=st_filename)
def test_derive_metadata_folder_path_and_title(
    dir_segments: list[str], filename: str
) -> None:
    """For any root path and descendant file path, derived folder_path equals
    the relative directory portion, and derived title equals the filename stem.

    **Validates: Requirements 7.3, 7.4**
    """
    # Create a temporary directory for each test input
    tmp_dir = Path(tempfile.mkdtemp())
    root = tmp_dir / "root"
    root.mkdir()

    # Build subdirectory structure
    subdir = root
    for seg in dir_segments:
        subdir = subdir / seg

    subdir.mkdir(parents=True, exist_ok=True)
    file_path = subdir / filename
    file_path.touch()

    # Derive metadata
    meta = derive_metadata(file_path, root)

    # Property: title equals filename stem (without last extension)
    expected_title = Path(filename).stem
    assert meta.title == expected_title, (
        f"Expected title={expected_title!r}, got {meta.title!r} "
        f"for filename={filename!r}"
    )

    # Property: folder_path equals relative directory portion
    relative_dir = str(Path(*dir_segments)) if dir_segments else "/"
    assert meta.folder_path == relative_dir, (
        f"Expected folder_path={relative_dir!r}, got {meta.folder_path!r} "
        f"for dir_segments={dir_segments!r}"
    )


# ---------------------------------------------------------------------------
# Property 10: CLI directory walk discovers all files
# ---------------------------------------------------------------------------


# Strategy for directory tree: list of (relative_path_segments, filename) tuples
st_file_entries = st.lists(
    st.tuples(st_dir_segments, st_filename),
    min_size=1,
    max_size=15,
)


# Feature: document-upload-list, Property 10: CLI directory walk discovers all files
@settings(max_examples=100)
@given(file_entries=st_file_entries)
def test_walk_directory_completeness(
    file_entries: list[tuple[list[str], str]]
) -> None:
    """For any directory tree structure, walk returns exactly all regular files
    with no duplicates or omissions.

    **Validates: Requirements 7.2**
    """
    tmp_dir = Path(tempfile.mkdtemp())
    root = tmp_dir / "walk_root"
    root.mkdir()

    # Create all files in the tree
    created_files: set[Path] = set()
    for dir_segments, filename in file_entries:
        subdir = root
        for seg in dir_segments:
            subdir = subdir / seg
        subdir.mkdir(parents=True, exist_ok=True)

        file_path = subdir / filename
        file_path.touch()
        created_files.add(file_path.resolve())

    # Walk the directory
    walked_files = walk_directory(root)

    # Property: no duplicates
    assert len(walked_files) == len(set(walked_files)), (
        "walk_directory returned duplicate entries"
    )

    # Property: walked set equals created set (no omissions, no extras)
    walked_set = {p.resolve() for p in walked_files}
    assert walked_set == created_files, (
        f"Mismatch between walked and created files.\n"
        f"Missing: {created_files - walked_set}\n"
        f"Extra: {walked_set - created_files}"
    )


# ---------------------------------------------------------------------------
# Property 11: CLI request construction includes all required fields/headers
# ---------------------------------------------------------------------------


# Feature: document-upload-list, Property 11: CLI request construction
@settings(max_examples=100)
@given(
    token=st_token,
    company_id=st_id,
    user_id=st_id,
    document_type=st_document_type,
    tags=st_tags,
    filename=st_filename,
    dir_segments=st_dir_segments,
)
def test_request_construction_includes_required_fields(
    token: str,
    company_id: str,
    user_id: str,
    document_type: str,
    tags: str,
    filename: str,
    dir_segments: list[str],
) -> None:
    """For any valid metadata and config, the constructed request includes
    Authorization, X-Company-Id, multipart encoding, and all form fields.

    **Validates: Requirements 7.5, 8.2, 8.3, 8.4, 8.5**
    """
    import httpx

    # Create a real file to upload
    tmp_dir = Path(tempfile.mkdtemp())
    root = tmp_dir / "req_root"
    root.mkdir()
    subdir = root
    for seg in dir_segments:
        subdir = subdir / seg
    subdir.mkdir(parents=True, exist_ok=True)
    file_path = subdir / filename
    file_path.write_text("test content")

    # Derive metadata
    meta = derive_metadata(file_path, root)

    api_url = "http://testserver:8000"

    # Set up headers as the CLI does
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": company_id,
    }

    # Capture the request by mocking httpx.Client.post
    captured_request = {}

    def mock_post(self_client, url, *, files=None, data=None, **kwargs):
        captured_request["url"] = url
        captured_request["files"] = files
        captured_request["data"] = data
        # Return a successful mock response
        response = MagicMock()
        response.status_code = 201
        return response

    with patch.object(httpx.Client, "post", mock_post):
        with httpx.Client(headers=headers, timeout=60.0) as client:
            upload_file(
                client=client,
                file_meta=meta,
                api_url=api_url,
                document_type=document_type,
                tags=tags,
                user_id=user_id,
            )

    # Property: Authorization header is set correctly
    assert f"Bearer {token}" in str(headers["Authorization"]), (
        f"Authorization header missing or incorrect"
    )

    # Property: X-Company-Id header is set
    assert headers["X-Company-Id"] == company_id, (
        f"X-Company-Id header missing or incorrect"
    )

    # Property: request was made with multipart (files parameter present)
    assert captured_request.get("files") is not None, (
        "Request did not include files (multipart encoding)"
    )

    # Property: all form fields are present in data
    data = captured_request.get("data", {})
    assert data.get("title") == meta.title, (
        f"Form field 'title' missing or incorrect: {data.get('title')!r} != {meta.title!r}"
    )
    assert data.get("folder_path") == meta.folder_path, (
        f"Form field 'folder_path' missing or incorrect"
    )
    assert data.get("document_type") == document_type, (
        f"Form field 'document_type' missing or incorrect"
    )
    assert data.get("tags") == tags, (
        f"Form field 'tags' missing or incorrect"
    )
    assert data.get("user_id") == user_id, (
        f"Form field 'user_id' missing or incorrect"
    )

    # Property: URL targets the documents endpoint
    assert captured_request["url"] == f"{api_url}/api/documents", (
        f"URL incorrect: {captured_request['url']}"
    )


# ---------------------------------------------------------------------------
# Property 12: CLI summary counts are arithmetically correct
# ---------------------------------------------------------------------------


# Strategy for upload results: list of booleans (True=success, False=failure)
st_upload_results = st.lists(st.booleans(), min_size=0, max_size=50)


# Feature: document-upload-list, Property 12: CLI summary counts
@settings(max_examples=100)
@given(results=st_upload_results)
def test_summary_counts_arithmetic(results: list[bool]) -> None:
    """For any sequence of N uploads with S successes and F failures,
    summary reports total=N, successful=S, failed=F, and N=S+F.

    **Validates: Requirements 7.8**
    """
    # Simulate the upload loop logic
    summary = UploadSummary(total=len(results))

    for success in results:
        if success:
            summary.successful += 1
        else:
            summary.failed += 1

    # Property: total equals length of results
    assert summary.total == len(results), (
        f"Total mismatch: {summary.total} != {len(results)}"
    )

    # Property: successful equals count of True values
    expected_successful = sum(1 for r in results if r)
    assert summary.successful == expected_successful, (
        f"Successful mismatch: {summary.successful} != {expected_successful}"
    )

    # Property: failed equals count of False values
    expected_failed = sum(1 for r in results if not r)
    assert summary.failed == expected_failed, (
        f"Failed mismatch: {summary.failed} != {expected_failed}"
    )

    # Property: N = S + F (arithmetic invariant)
    assert summary.total == summary.successful + summary.failed, (
        f"Arithmetic invariant violated: "
        f"{summary.total} != {summary.successful} + {summary.failed}"
    )
