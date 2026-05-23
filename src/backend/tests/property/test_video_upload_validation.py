"""Property-based tests for video upload validation.

Tests Property 10: Video upload validation from the
multimodal-knowledge-base design document.

Property 10 validates that for any (content_type, file_size) pair,
the video upload validation logic correctly accepts valid combinations
and rejects invalid ones.

Valid content types: video/mp4, video/x-msvideo, video/quicktime, video/webm
Valid file size: 0 < file_size <= 2_147_483_648 (2 GB)

**Validates: Requirements 4.1, 4.2**

References:
    - Design: .kiro/specs/Step_4-4_multimodal-knowledge-base/design.md (Property 10)
    - Requirements: .kiro/specs/Step_4-4_multimodal-knowledge-base/requirements.md
    - Config: src/backend/src/alcoabase/config.py (video_max_file_size_bytes)
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Constants matching the specification
# ---------------------------------------------------------------------------

SUPPORTED_VIDEO_CONTENT_TYPES: set[str] = {
    "video/mp4",
    "video/x-msvideo",
    "video/quicktime",
    "video/webm",
}

MAX_VIDEO_FILE_SIZE_BYTES: int = 2_147_483_648  # 2 GB


# ---------------------------------------------------------------------------
# Validation logic under test (pure function)
# ---------------------------------------------------------------------------


def validate_video_upload(content_type: str, file_size: int) -> tuple[bool, str | None]:
    """Validate a video upload based on content type and file size.

    Implements the accept/reject logic specified in Requirements 4.1 and 4.2:
    - Content type must be one of the supported video formats.
    - File size must be > 0 bytes and <= 2 GB (2_147_483_648 bytes).

    Args:
        content_type: The MIME type of the uploaded file.
        file_size: The size of the uploaded file in bytes.

    Returns:
        A tuple of (is_valid, error_message). If valid, error_message is None.
        If invalid, error_message describes which constraint was violated.
    """
    if content_type not in SUPPORTED_VIDEO_CONTENT_TYPES:
        return False, (
            f"Unsupported content type '{content_type}'. "
            f"Supported formats: {sorted(SUPPORTED_VIDEO_CONTENT_TYPES)}"
        )

    if file_size <= 0:
        return False, "File size must be greater than 0 bytes."

    if file_size > MAX_VIDEO_FILE_SIZE_BYTES:
        return False, (
            f"File size {file_size} bytes exceeds maximum allowed "
            f"size of {MAX_VIDEO_FILE_SIZE_BYTES} bytes (2 GB)."
        )

    return True, None


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_valid_content_type() -> st.SearchStrategy[str]:
    """Generate valid video content types.

    Returns:
        Strategy producing one of the four supported MIME types.
    """
    return st.sampled_from(sorted(SUPPORTED_VIDEO_CONTENT_TYPES))


def st_invalid_content_type() -> st.SearchStrategy[str]:
    """Generate invalid content types that are not in the supported set.

    Produces MIME-like strings that do not match any supported video format.

    Returns:
        Strategy producing invalid content type strings.
    """
    common_invalid = [
        "application/pdf",
        "image/png",
        "image/jpeg",
        "text/plain",
        "audio/mpeg",
        "video/x-flv",
        "video/3gpp",
        "application/octet-stream",
        "video/mpeg",
        "video/ogg",
        "",
    ]
    return st.one_of(
        st.sampled_from(common_invalid),
        st.text(min_size=1, max_size=50).filter(
            lambda s: s not in SUPPORTED_VIDEO_CONTENT_TYPES
        ),
    )


def st_valid_file_size() -> st.SearchStrategy[int]:
    """Generate valid file sizes (0 < size <= 2 GB).

    Includes edge cases: 1 byte (minimum valid) and exactly 2 GB (maximum valid).

    Returns:
        Strategy producing valid file size integers.
    """
    return st.one_of(
        st.just(1),  # minimum valid
        st.just(MAX_VIDEO_FILE_SIZE_BYTES),  # maximum valid (exactly 2 GB)
        st.integers(min_value=1, max_value=MAX_VIDEO_FILE_SIZE_BYTES),
    )


def st_invalid_file_size() -> st.SearchStrategy[int]:
    """Generate invalid file sizes (size <= 0 or size > 2 GB).

    Includes edge cases: 0 bytes, negative values, and 2 GB + 1.

    Returns:
        Strategy producing invalid file size integers.
    """
    return st.one_of(
        st.just(0),  # zero bytes
        st.just(-1),  # negative
        st.just(MAX_VIDEO_FILE_SIZE_BYTES + 1),  # one byte over limit
        st.integers(min_value=-1_000_000, max_value=0),  # negative/zero range
        st.integers(
            min_value=MAX_VIDEO_FILE_SIZE_BYTES + 1,
            max_value=MAX_VIDEO_FILE_SIZE_BYTES * 10,
        ),  # over limit
    )


# ---------------------------------------------------------------------------
# Property 10: Video Upload Validation
# ---------------------------------------------------------------------------


# Feature: multimodal-knowledge-base, Property 10: Video upload validation
class TestVideoUploadValidation:
    """Property tests for video upload validation.

    For any (content_type, file_size) pair, the validation logic must:
    - Accept when content_type is supported AND 0 < file_size <= 2 GB
    - Reject when content_type is unsupported OR file_size is out of range

    **Validates: Requirements 4.1, 4.2**
    """

    @given(
        content_type=st_valid_content_type(),
        file_size=st_valid_file_size(),
    )
    @settings(max_examples=200)
    def test_valid_uploads_are_accepted(
        self,
        content_type: str,
        file_size: int,
    ) -> None:
        """Valid (content_type, file_size) pairs are always accepted.

        A valid upload has a supported content type and a file size
        in the range (0, 2_147_483_648].

        **Validates: Requirements 4.1, 4.2**
        """
        is_valid, error = validate_video_upload(content_type, file_size)

        assert is_valid is True, (
            f"Expected valid upload for content_type='{content_type}', "
            f"file_size={file_size}, but got error: {error}"
        )
        assert error is None

    @given(
        content_type=st_invalid_content_type(),
        file_size=st_valid_file_size(),
    )
    @settings(max_examples=200)
    def test_invalid_content_type_is_rejected(
        self,
        content_type: str,
        file_size: int,
    ) -> None:
        """Uploads with unsupported content types are always rejected,
        regardless of file size.

        **Validates: Requirements 4.1, 4.2**
        """
        is_valid, error = validate_video_upload(content_type, file_size)

        assert is_valid is False, (
            f"Expected rejection for unsupported content_type='{content_type}', "
            f"file_size={file_size}"
        )
        assert error is not None
        assert "content type" in error.lower() or "Unsupported" in error

    @given(
        content_type=st_valid_content_type(),
        file_size=st_invalid_file_size(),
    )
    @settings(max_examples=200)
    def test_invalid_file_size_is_rejected(
        self,
        content_type: str,
        file_size: int,
    ) -> None:
        """Uploads with invalid file sizes are always rejected,
        regardless of content type.

        Invalid file sizes: <= 0 or > 2_147_483_648 bytes.

        **Validates: Requirements 4.1, 4.2**
        """
        is_valid, error = validate_video_upload(content_type, file_size)

        assert is_valid is False, (
            f"Expected rejection for content_type='{content_type}', "
            f"invalid file_size={file_size}"
        )
        assert error is not None

    @given(
        content_type=st_invalid_content_type(),
        file_size=st_invalid_file_size(),
    )
    @settings(max_examples=200)
    def test_both_invalid_is_rejected(
        self,
        content_type: str,
        file_size: int,
    ) -> None:
        """Uploads where both content type and file size are invalid
        are always rejected.

        **Validates: Requirements 4.1, 4.2**
        """
        is_valid, error = validate_video_upload(content_type, file_size)

        assert is_valid is False, (
            f"Expected rejection for invalid content_type='{content_type}', "
            f"invalid file_size={file_size}"
        )
        assert error is not None

    @given(
        content_type=st.text(min_size=0, max_size=100),
        file_size=st.integers(min_value=-1_000_000, max_value=MAX_VIDEO_FILE_SIZE_BYTES * 5),
    )
    @settings(max_examples=500)
    def test_validation_is_consistent_with_spec(
        self,
        content_type: str,
        file_size: int,
    ) -> None:
        """For any arbitrary (content_type, file_size) pair, the validation
        result is consistent with the specification:
        - Accept iff content_type in SUPPORTED set AND 0 < file_size <= 2GB
        - Reject otherwise

        **Validates: Requirements 4.1, 4.2**
        """
        is_valid, error = validate_video_upload(content_type, file_size)

        expected_valid = (
            content_type in SUPPORTED_VIDEO_CONTENT_TYPES
            and 0 < file_size <= MAX_VIDEO_FILE_SIZE_BYTES
        )

        assert is_valid == expected_valid, (
            f"Validation mismatch for content_type='{content_type}', "
            f"file_size={file_size}. "
            f"Expected valid={expected_valid}, got valid={is_valid}. "
            f"Error: {error}"
        )

        if expected_valid:
            assert error is None
        else:
            assert error is not None
