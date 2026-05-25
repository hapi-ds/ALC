"""Unit tests for CrossReferenceService.

Tests the pure extraction logic and validation functionality of the
CrossReferenceService, focusing on regex-based reference extraction
and output validation.

Requirements: 3.1, 3.2, 3.4, 3.5, 3.6, 3.7, 3.8
"""

import pytest

from alcoabase.services.cross_reference import (
    MAX_ENTRIES_PER_DOCUMENT,
    CrossReference,
    CrossReferenceService,
)


@pytest.fixture
def service():
    """Create a CrossReferenceService with None dependencies for pure function tests."""
    # For testing pure functions, we don't need real dependencies
    return CrossReferenceService(
        session_factory=None,  # type: ignore[arg-type]
        knowledge_service=None,  # type: ignore[arg-type]
        storage_service=None,  # type: ignore[arg-type]
    )


class TestExtractReferencesFromText:
    """Tests for extract_references_from_text pure function."""

    def test_extracts_req_pattern(self, service: CrossReferenceService):
        """REQ-NNNNN patterns are extracted as requirements."""
        text = "This document references REQ-00123 for validation."
        refs = service.extract_references_from_text(text, 1, "Test Doc")

        assert len(refs) == 1
        assert refs[0].reference_type == "requirement"
        assert refs[0].reference_identifier == "REQ-00123"
        assert refs[0].source_document_id == 1
        assert refs[0].source_document_title == "Test Doc"

    def test_extracts_urs_pattern(self, service: CrossReferenceService):
        """URS-N.N patterns are extracted as requirements."""
        text = "See URS-1.2 and URS-12.34 for details."
        refs = service.extract_references_from_text(text, 2, "URS Doc")

        req_refs = [r for r in refs if r.reference_type == "requirement"]
        identifiers = {r.reference_identifier for r in req_refs}
        assert "URS-1.2" in identifiers
        assert "URS-12.34" in identifiers

    def test_extracts_tc_pattern(self, service: CrossReferenceService):
        """TC-NNNNN patterns are extracted as test_case."""
        text = "Execute TC-00045 to verify compliance."
        refs = service.extract_references_from_text(text, 3, "Test Plan")

        tc_refs = [r for r in refs if r.reference_type == "test_case"]
        assert len(tc_refs) == 1
        assert tc_refs[0].reference_identifier == "TC-00045"

    def test_extracts_test_pattern(self, service: CrossReferenceService):
        """TEST-NNNNN patterns are extracted as test_case."""
        text = "Run TEST-12345 after deployment."
        refs = service.extract_references_from_text(text, 4, "Deployment Guide")

        tc_refs = [r for r in refs if r.reference_type == "test_case"]
        assert len(tc_refs) == 1
        assert tc_refs[0].reference_identifier == "TEST-12345"

    def test_extracts_section_numbering(self, service: CrossReferenceService):
        """Heading-level numbering at line start is extracted as section."""
        text = "1 Introduction\n1.1 Purpose\n1.1.1 Scope\n1.1.1.1 Details"
        refs = service.extract_references_from_text(text, 5, "SOP")

        section_refs = [r for r in refs if r.reference_type == "section"]
        identifiers = {r.reference_identifier for r in section_refs}
        assert "1" in identifiers
        assert "1.1" in identifiers
        assert "1.1.1" in identifiers
        assert "1.1.1.1" in identifiers

    def test_section_numbering_requires_line_start(self, service: CrossReferenceService):
        """Section numbering must be at the start of a line."""
        text = "This is version 2.0 of the document."
        refs = service.extract_references_from_text(text, 6, "Doc")

        section_refs = [r for r in refs if r.reference_type == "section"]
        # "2.0" should not be extracted since it's not at line start
        assert len(section_refs) == 0

    def test_deduplicates_references(self, service: CrossReferenceService):
        """Duplicate identifiers are only extracted once."""
        text = "REQ-001 is important. See REQ-001 again here."
        refs = service.extract_references_from_text(text, 7, "Doc")

        assert len(refs) == 1
        assert refs[0].reference_identifier == "REQ-001"

    def test_mixed_reference_types(self, service: CrossReferenceService):
        """Multiple reference types are extracted from the same text."""
        text = (
            "1 Introduction\n"
            "REQ-001 defines the requirement.\n"
            "TC-100 validates REQ-001.\n"
            "URS-2.1 provides context.\n"
            "TEST-500 is the integration test."
        )
        refs = service.extract_references_from_text(text, 8, "Mixed Doc")

        types = {r.reference_type for r in refs}
        assert "requirement" in types
        assert "test_case" in types
        assert "section" in types

    def test_empty_text_returns_empty(self, service: CrossReferenceService):
        """Empty text returns no references."""
        refs = service.extract_references_from_text("", 9, "Empty")
        assert refs == []

    def test_no_matches_returns_empty(self, service: CrossReferenceService):
        """Text without reference patterns returns empty list."""
        text = "This is a plain document with no references."
        refs = service.extract_references_from_text(text, 10, "Plain")
        assert refs == []

    def test_reference_text_truncated_to_150(self, service: CrossReferenceService):
        """Reference text context is truncated to 150 characters."""
        long_line = "REQ-001 " + "x" * 200
        refs = service.extract_references_from_text(long_line, 11, "Long")

        assert len(refs[0].reference_text) <= 150

    def test_req_pattern_boundary(self, service: CrossReferenceService):
        """REQ pattern respects word boundaries."""
        text = "FREQ-001 should not match but REQ-001 should."
        refs = service.extract_references_from_text(text, 12, "Boundary")

        identifiers = {r.reference_identifier for r in refs}
        assert "REQ-001" in identifiers
        # FREQ-001 should not be extracted due to word boundary
        assert "FREQ-001" not in identifiers

    def test_max_digit_lengths(self, service: CrossReferenceService):
        """Patterns respect maximum digit lengths."""
        text = (
            "REQ-99999 is valid.\n"
            "REQ-123456 has too many digits.\n"
            "TC-12345 is valid.\n"
            "URS-123.456 has too many digits in second part."
        )
        refs = service.extract_references_from_text(text, 13, "Limits")

        identifiers = {r.reference_identifier for r in refs}
        assert "REQ-99999" in identifiers
        assert "TC-12345" in identifiers
        # REQ-123456 has 6 digits, should not match \d{1,5}
        assert "REQ-123456" not in identifiers


class TestValidateReferencesInOutput:
    """Tests for validate_references_in_output."""

    @pytest.mark.asyncio
    async def test_no_unverified_when_all_in_map(self, service: CrossReferenceService):
        """No unverified references when all are in the map."""
        text = "This references REQ-001 and TC-100."
        cross_ref_map = {
            "requirement": [
                CrossReference(
                    reference_type="requirement",
                    reference_identifier="REQ-001",
                    reference_text="Some text",
                    source_document_id=1,
                    source_document_title="Doc",
                )
            ],
            "test_case": [
                CrossReference(
                    reference_type="test_case",
                    reference_identifier="TC-100",
                    reference_text="Test text",
                    source_document_id=1,
                    source_document_title="Doc",
                )
            ],
            "section": [],
        }

        unverified = await service.validate_references_in_output(text, cross_ref_map)
        assert unverified == []

    @pytest.mark.asyncio
    async def test_flags_unverified_references(self, service: CrossReferenceService):
        """References not in the map are flagged as unverified."""
        text = "This references REQ-999 which is not in the map."
        cross_ref_map: dict[str, list[CrossReference]] = {
            "requirement": [],
            "test_case": [],
            "section": [],
        }

        unverified = await service.validate_references_in_output(text, cross_ref_map)
        assert len(unverified) == 1
        assert unverified[0]["reference_identifier"] == "REQ-999"
        assert unverified[0]["reference_type"] == "requirement"
        assert "section_number" in unverified[0]["location"]
        assert "paragraph_index" in unverified[0]["location"]

    @pytest.mark.asyncio
    async def test_tracks_section_location(self, service: CrossReferenceService):
        """Unverified references include correct section location."""
        text = "1 Introduction\nSome text\n2 Details\nSee REQ-555 here."
        cross_ref_map: dict[str, list[CrossReference]] = {
            "requirement": [],
            "test_case": [],
            "section": [],
        }

        unverified = await service.validate_references_in_output(text, cross_ref_map)
        assert len(unverified) == 1
        assert unverified[0]["location"]["section_number"] == "2"

    @pytest.mark.asyncio
    async def test_empty_text_no_unverified(self, service: CrossReferenceService):
        """Empty generated text produces no unverified references."""
        cross_ref_map: dict[str, list[CrossReference]] = {
            "requirement": [],
            "test_case": [],
            "section": [],
        }

        unverified = await service.validate_references_in_output("", cross_ref_map)
        assert unverified == []

    @pytest.mark.asyncio
    async def test_multiple_unverified_references(self, service: CrossReferenceService):
        """Multiple unverified references are all flagged."""
        text = "See REQ-100, TC-200, and TEST-300 for details."
        cross_ref_map: dict[str, list[CrossReference]] = {
            "requirement": [],
            "test_case": [],
            "section": [],
        }

        unverified = await service.validate_references_in_output(text, cross_ref_map)
        identifiers = {u["reference_identifier"] for u in unverified}
        assert "REQ-100" in identifiers
        assert "TC-200" in identifiers
        assert "TEST-300" in identifiers
