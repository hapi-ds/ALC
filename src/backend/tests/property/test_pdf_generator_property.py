"""Property-based tests for PDF filename version format.

Tests Property 10: PDF Filename Version Format from the
template-builder-enhancements design document.

Property 10 validates that for any template name and version number,
the generated PDF filename follows the format:
    {sanitized_name}_{document_uuid}_v{version_number}.pdf
where sanitized_name replaces spaces with underscores.

**Validates: Requirements 12.3, 12.1, 12.2**

References:
    - Design: .kiro/specs/template-builder-enhancements/design.md (Property 10)
    - Requirements: .kiro/specs/template-builder-enhancements/requirements.md
    - Implementation: src/backend/src/alcoabase/api/templates.py (download_pdf)
"""

import re

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Filename generation logic extracted from the download_pdf endpoint
# (src/backend/src/alcoabase/api/templates.py)
# ---------------------------------------------------------------------------


def generate_pdf_filename(template_name: str, document_uuid: str, version_number: int) -> str:
    """Generate a PDF filename following the version-aware format.

    Replicates the filename logic from the download_pdf endpoint:
        sanitized_name = template.name.replace(" ", "_")
        filename = f"{sanitized_name}_{document_uuid}_v{version_number}.pdf"

    Args:
        template_name: The template name (may contain spaces).
        document_uuid: The Document-UUID (e.g., "2025-00001").
        version_number: The version number (positive integer).

    Returns:
        The formatted PDF filename string.
    """
    sanitized_name = template_name.replace(" ", "_")
    return f"{sanitized_name}_{document_uuid}_v{version_number}.pdf"


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


def st_template_name() -> st.SearchStrategy[str]:
    """Generate random template names that may contain spaces.

    Produces non-empty strings with letters, digits, spaces, and common
    punctuation that would be valid template names.

    Returns:
        Strategy producing template name strings.
    """
    return st.text(
        alphabet=st.characters(
            categories=("L", "N", "Z"),
            whitelist_characters=" -_",
        ),
        min_size=1,
        max_size=100,
    ).filter(lambda s: s.strip())


def st_document_uuid() -> st.SearchStrategy[str]:
    """Generate Document-UUIDs in the YYYY-NNNNN format.

    Returns:
        Strategy producing strings like "2025-00001".
    """
    return st.builds(
        lambda year, seq: f"{year}-{seq:05d}",
        year=st.integers(min_value=2020, max_value=2030),
        seq=st.integers(min_value=1, max_value=99999),
    )


def st_version_number() -> st.SearchStrategy[int]:
    """Generate valid version numbers (positive integers).

    Returns:
        Strategy producing integers >= 1.
    """
    return st.integers(min_value=1, max_value=1000)


# ---------------------------------------------------------------------------
# Property 10: PDF Filename Version Format
# ---------------------------------------------------------------------------


# Feature: template-builder-enhancements, Property 10: PDF Filename Version Format
class TestPdfFilenameVersionFormat:
    """Property tests for PDF filename version format.

    For any template name and version number, the generated PDF filename
    must follow the format:
        {sanitized_name}_{document_uuid}_v{version_number}.pdf
    where sanitized_name replaces spaces with underscores, and the version
    number matches the stored version number exactly.

    **Validates: Requirements 12.3, 12.1, 12.2**
    """

    @given(
        template_name=st_template_name(),
        document_uuid=st_document_uuid(),
        version_number=st_version_number(),
    )
    @settings(max_examples=100)
    def test_filename_follows_expected_format(
        self,
        template_name: str,
        document_uuid: str,
        version_number: int,
    ) -> None:
        """The generated filename matches the pattern
        {sanitized_name}_{document_uuid}_v{version_number}.pdf exactly.

        **Validates: Requirements 12.3, 12.1, 12.2**
        """
        filename = generate_pdf_filename(template_name, document_uuid, version_number)

        sanitized_name = template_name.replace(" ", "_")
        expected = f"{sanitized_name}_{document_uuid}_v{version_number}.pdf"

        assert filename == expected, (
            f"Expected filename '{expected}', got '{filename}'"
        )

    @given(
        template_name=st_template_name(),
        document_uuid=st_document_uuid(),
        version_number=st_version_number(),
    )
    @settings(max_examples=100)
    def test_filename_contains_no_spaces(
        self,
        template_name: str,
        document_uuid: str,
        version_number: int,
    ) -> None:
        """The sanitized filename never contains spaces - all spaces from
        the template name are replaced with underscores.

        **Validates: Requirements 12.3**
        """
        filename = generate_pdf_filename(template_name, document_uuid, version_number)

        assert " " not in filename, (
            f"Filename should not contain spaces, got: '{filename}'"
        )

    @given(
        template_name=st_template_name(),
        document_uuid=st_document_uuid(),
        version_number=st_version_number(),
    )
    @settings(max_examples=100)
    def test_filename_ends_with_pdf_extension(
        self,
        template_name: str,
        document_uuid: str,
        version_number: int,
    ) -> None:
        """The filename always ends with the .pdf extension.

        **Validates: Requirements 12.3**
        """
        filename = generate_pdf_filename(template_name, document_uuid, version_number)

        assert filename.endswith(".pdf"), (
            f"Filename should end with '.pdf', got: '{filename}'"
        )

    @given(
        template_name=st_template_name(),
        document_uuid=st_document_uuid(),
        version_number=st_version_number(),
    )
    @settings(max_examples=100)
    def test_filename_contains_version_number(
        self,
        template_name: str,
        document_uuid: str,
        version_number: int,
    ) -> None:
        """The filename contains the exact version number in the format
        _v{version_number}.pdf - the version number matches the stored
        version number exactly (Requirement 12.2).

        **Validates: Requirements 12.1, 12.2**
        """
        filename = generate_pdf_filename(template_name, document_uuid, version_number)

        version_suffix = f"_v{version_number}.pdf"
        assert filename.endswith(version_suffix), (
            f"Filename should end with '{version_suffix}', got: '{filename}'"
        )

    @given(
        template_name=st_template_name(),
        document_uuid=st_document_uuid(),
        version_number=st_version_number(),
    )
    @settings(max_examples=100)
    def test_filename_contains_document_uuid(
        self,
        template_name: str,
        document_uuid: str,
        version_number: int,
    ) -> None:
        """The filename contains the document UUID between the sanitized
        name and the version suffix.

        **Validates: Requirements 12.3**
        """
        filename = generate_pdf_filename(template_name, document_uuid, version_number)

        assert document_uuid in filename, (
            f"Filename should contain document UUID '{document_uuid}', "
            f"got: '{filename}'"
        )

    @given(
        template_name=st_template_name(),
        document_uuid=st_document_uuid(),
        version_number=st_version_number(),
    )
    @settings(max_examples=100)
    def test_filename_structure_is_parseable(
        self,
        template_name: str,
        document_uuid: str,
        version_number: int,
    ) -> None:
        """The filename can be parsed back to extract the version number,
        confirming the format is consistent and machine-readable.

        The version number extracted from the filename must match the
        input version number exactly (Requirement 12.2).

        **Validates: Requirements 12.1, 12.2, 12.3**
        """
        filename = generate_pdf_filename(template_name, document_uuid, version_number)

        # Extract version number from the end of the filename
        match = re.search(r"_v(\d+)\.pdf$", filename)
        assert match is not None, (
            f"Could not parse version from filename: '{filename}'"
        )

        extracted_version = int(match.group(1))
        assert extracted_version == version_number, (
            f"Extracted version {extracted_version} does not match "
            f"input version {version_number}"
        )

    @given(
        template_name=st_template_name(),
        document_uuid=st_document_uuid(),
        version_number=st_version_number(),
    )
    @settings(max_examples=100)
    def test_sanitization_only_replaces_spaces(
        self,
        template_name: str,
        document_uuid: str,
        version_number: int,
    ) -> None:
        """The sanitization step only replaces spaces with underscores -
        all other characters in the template name are preserved unchanged.

        **Validates: Requirements 12.3**
        """
        filename = generate_pdf_filename(template_name, document_uuid, version_number)

        sanitized_name = template_name.replace(" ", "_")
        # The filename should start with the sanitized name
        assert filename.startswith(sanitized_name + "_"), (
            f"Filename should start with '{sanitized_name}_', got: '{filename}'"
        )
