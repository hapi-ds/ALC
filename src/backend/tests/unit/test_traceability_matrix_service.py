"""Unit tests for TraceabilityMatrixService three-pass matching strategy.

Tests the three-pass matching logic (exact ID, cross-reference, semantic),
link deduplication, and service unavailability handling.

Requirements: 1.2, 1.3, 1.7, 1.11
"""

import pytest

from alcoabase.services.traceability_matrix import (
    CandidateLink,
    ExtractedRequirement,
    ExtractedTestCase,
    MatchingResult,
    TraceabilityMatrixService,
)


@pytest.fixture
def service():
    """Create a TraceabilityMatrixService with None dependencies for pure function tests."""
    return TraceabilityMatrixService()


@pytest.fixture
def sample_requirements():
    """Sample extracted requirements for testing."""
    return [
        ExtractedRequirement(
            requirement_id="REQ-001",
            requirement_text="The system shall validate user input.",
            source_document_uuid="doc-src-001",
            source_section="1.1 Input Validation",
        ),
        ExtractedRequirement(
            requirement_id="URS-2.1",
            requirement_text="The system shall log all access attempts.",
            source_document_uuid="doc-src-001",
            source_section="2.1 Audit Logging",
        ),
        ExtractedRequirement(
            requirement_id="R.3.1",
            requirement_text="The system shall encrypt data at rest.",
            source_document_uuid="doc-src-002",
            source_section="3.1 Data Security",
        ),
    ]


@pytest.fixture
def sample_test_cases():
    """Sample extracted test cases for testing."""
    return [
        ExtractedTestCase(
            test_case_id="TC-001",
            test_case_text="Verify REQ-001: Submit invalid input and confirm rejection.",
            target_document_uuid="doc-tgt-001",
            target_section="1.1 Input Validation Tests",
        ),
        ExtractedTestCase(
            test_case_id="IQ-002",
            test_case_text="Verify that audit logs capture login attempts per URS-2.1.",
            target_document_uuid="doc-tgt-001",
            target_section="2.1 Audit Tests",
        ),
        ExtractedTestCase(
            test_case_id="OQ-003",
            test_case_text="Verify encryption at rest for stored data.",
            target_document_uuid="doc-tgt-002",
            target_section="3.1 Security Tests",
        ),
    ]


class TestPass1ExactIdMatch:
    """Tests for pass_1_exact_id_match."""

    def test_finds_req_pattern_in_test_case_text(
        self, service: TraceabilityMatrixService, sample_requirements, sample_test_cases
    ):
        """REQ-NNN pattern in test case text creates a link with confidence 1.0."""
        links = service.pass_1_exact_id_match(sample_requirements, sample_test_cases)

        req_001_links = [l for l in links if l.requirement_id == "REQ-001"]
        assert len(req_001_links) == 1
        assert req_001_links[0].test_case_id == "TC-001"
        assert req_001_links[0].link_confidence == 1.0
        assert req_001_links[0].link_method == "exact_id_match"

    def test_finds_urs_pattern_in_test_case_text(
        self, service: TraceabilityMatrixService, sample_requirements, sample_test_cases
    ):
        """URS-N.N pattern in test case text creates a link with confidence 1.0."""
        links = service.pass_1_exact_id_match(sample_requirements, sample_test_cases)

        urs_links = [l for l in links if l.requirement_id == "URS-2.1"]
        assert len(urs_links) == 1
        assert urs_links[0].test_case_id == "IQ-002"
        assert urs_links[0].link_confidence == 1.0

    def test_no_match_when_id_not_in_text(
        self, service: TraceabilityMatrixService, sample_requirements, sample_test_cases
    ):
        """No link created when requirement ID is not cited in test case text."""
        links = service.pass_1_exact_id_match(sample_requirements, sample_test_cases)

        # R.3.1 is not cited in any test case text
        r31_links = [l for l in links if l.requirement_id == "R.3.1"]
        assert len(r31_links) == 0

    def test_empty_requirements_returns_empty(
        self, service: TraceabilityMatrixService, sample_test_cases
    ):
        """Empty requirements list returns no links."""
        links = service.pass_1_exact_id_match([], sample_test_cases)
        assert links == []

    def test_empty_test_cases_returns_empty(
        self, service: TraceabilityMatrixService, sample_requirements
    ):
        """Empty test cases list returns no links."""
        links = service.pass_1_exact_id_match(sample_requirements, [])
        assert links == []

    def test_multiple_req_ids_in_single_test_case(
        self, service: TraceabilityMatrixService
    ):
        """Multiple requirement IDs in one test case create multiple links."""
        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Requirement one.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
            ),
            ExtractedRequirement(
                requirement_id="REQ-002",
                requirement_text="Requirement two.",
                source_document_uuid="doc-src-001",
                source_section="1.2",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-010",
                test_case_text="This test validates REQ-001 and REQ-002 together.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]

        links = service.pass_1_exact_id_match(requirements, test_cases)
        assert len(links) == 2
        req_ids = {l.requirement_id for l in links}
        assert req_ids == {"REQ-001", "REQ-002"}

    def test_unrecognized_id_in_text_not_linked(
        self, service: TraceabilityMatrixService
    ):
        """Requirement ID in text that doesn't match any known requirement is ignored."""
        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Known requirement.",
                source_document_uuid="doc-src-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-010",
                test_case_text="This references REQ-999 which is unknown.",
                target_document_uuid="doc-tgt-001",
                target_section="1.1",
            ),
        ]

        links = service.pass_1_exact_id_match(requirements, test_cases)
        assert links == []

    def test_link_contains_correct_metadata(
        self, service: TraceabilityMatrixService
    ):
        """Links contain correct source/target document and section metadata."""
        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-050",
                requirement_text="The system shall do X.",
                source_document_uuid="src-uuid-1",
                source_section="Section 5.0",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-050",
                test_case_text="Verify REQ-050 by doing Y.",
                target_document_uuid="tgt-uuid-1",
                target_section="Section 5.0 Tests",
            ),
        ]

        links = service.pass_1_exact_id_match(requirements, test_cases)
        assert len(links) == 1
        link = links[0]
        assert link.source_document_uuid == "src-uuid-1"
        assert link.source_section == "Section 5.0"
        assert link.target_document_uuid == "tgt-uuid-1"
        assert link.target_section == "Section 5.0 Tests"
        assert link.requirement_text == "The system shall do X."
        assert link.test_case_text == "Verify REQ-050 by doing Y."


class TestPass3SemanticMatch:
    """Tests for pass_3_semantic_match."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_knowledge_service_none(self):
        """Returns empty list when KnowledgeService is not available."""
        service = TraceabilityMatrixService(knowledge_service=None)
        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Some requirement.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Some test case.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        links = await service.pass_3_semantic_match(requirements, test_cases, 1)
        assert links == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_requirements(self):
        """Returns empty list when requirements list is empty."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        service = TraceabilityMatrixService(knowledge_service=mock_ks)

        links = await service.pass_3_semantic_match([], [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ], 1)
        assert links == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_test_cases(self):
        """Returns empty list when test cases list is empty."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        service = TraceabilityMatrixService(knowledge_service=mock_ks)

        links = await service.pass_3_semantic_match([
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ], [], 1)
        assert links == []

    @pytest.mark.asyncio
    async def test_creates_links_above_threshold(self):
        """Creates links when similarity >= 0.5 threshold."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        # Return unit vectors that are identical (similarity = 1.0)
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=[
                [[1.0, 0.0, 0.0]],  # requirement embedding
                [[1.0, 0.0, 0.0]],  # test case embedding (identical)
            ]
        )
        service = TraceabilityMatrixService(knowledge_service=mock_ks)

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Validate user input.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test user input validation.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        links = await service.pass_3_semantic_match(requirements, test_cases, 1)
        assert len(links) == 1
        assert links[0].link_confidence == 1.0
        assert links[0].link_method == "semantic_match"

    @pytest.mark.asyncio
    async def test_discards_links_below_threshold(self):
        """Discards links when similarity < 0.5 threshold."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        # Return orthogonal vectors (similarity = 0.0)
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=[
                [[1.0, 0.0, 0.0]],  # requirement embedding
                [[0.0, 1.0, 0.0]],  # test case embedding (orthogonal)
            ]
        )
        service = TraceabilityMatrixService(knowledge_service=mock_ks)

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Validate user input.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Unrelated test case.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        links = await service.pass_3_semantic_match(requirements, test_cases, 1)
        assert links == []

    @pytest.mark.asyncio
    async def test_confidence_equals_similarity_score(self):
        """Link confidence equals the cosine similarity score."""
        from unittest.mock import AsyncMock
        import math

        mock_ks = AsyncMock()
        # Vectors at ~60 degree angle → similarity ≈ 0.5
        # cos(60°) = 0.5, so use [1, 0] and [0.5, sqrt(3)/2]
        vec_a = [1.0, 0.0]
        vec_b = [0.5, math.sqrt(3) / 2]
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=[
                [vec_a],  # requirement embedding
                [vec_b],  # test case embedding
            ]
        )
        service = TraceabilityMatrixService(knowledge_service=mock_ks)

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Some requirement.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Some test.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        links = await service.pass_3_semantic_match(requirements, test_cases, 1)
        assert len(links) == 1
        # Cosine similarity of [1,0] and [0.5, sqrt(3)/2] = 0.5
        assert abs(links[0].link_confidence - 0.5) < 0.01

    @pytest.mark.asyncio
    async def test_raises_on_knowledge_service_failure(self):
        """Raises exception when KnowledgeService fails."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=ConnectionError("Service unavailable")
        )
        service = TraceabilityMatrixService(knowledge_service=mock_ks)

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Req.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        with pytest.raises(ConnectionError):
            await service.pass_3_semantic_match(requirements, test_cases, 1)


class TestDeduplicateLinks:
    """Tests for deduplicate_links."""

    def test_no_duplicates_returns_all(self, service: TraceabilityMatrixService):
        """Non-duplicate links are all retained."""
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test 1.",
                target_document_uuid="doc-002",
                target_section="1.1",
                link_confidence=1.0,
                link_method="exact_id_match",
            ),
            CandidateLink(
                requirement_id="REQ-002",
                requirement_text="Req 2.",
                source_document_uuid="doc-001",
                source_section="1.2",
                test_case_id="TC-002",
                test_case_text="Test 2.",
                target_document_uuid="doc-002",
                target_section="1.2",
                link_confidence=0.9,
                link_method="cross_reference",
            ),
        ]

        result = service.deduplicate_links(links)
        assert len(result) == 2

    def test_duplicate_keeps_highest_confidence(
        self, service: TraceabilityMatrixService
    ):
        """Duplicate (req_id, tc_id) pairs keep the highest confidence link."""
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test 1.",
                target_document_uuid="doc-002",
                target_section="1.1",
                link_confidence=0.7,
                link_method="semantic_match",
            ),
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test 1.",
                target_document_uuid="doc-002",
                target_section="1.1",
                link_confidence=1.0,
                link_method="exact_id_match",
            ),
        ]

        result = service.deduplicate_links(links)
        assert len(result) == 1
        assert result[0].link_confidence == 1.0
        assert result[0].link_method == "exact_id_match"

    def test_duplicate_merges_all_methods(
        self, service: TraceabilityMatrixService
    ):
        """Duplicate pairs record all detection methods in link_methods."""
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test 1.",
                target_document_uuid="doc-002",
                target_section="1.1",
                link_confidence=0.8,
                link_method="semantic_match",
            ),
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test 1.",
                target_document_uuid="doc-002",
                target_section="1.1",
                link_confidence=0.9,
                link_method="cross_reference",
            ),
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test 1.",
                target_document_uuid="doc-002",
                target_section="1.1",
                link_confidence=1.0,
                link_method="exact_id_match",
            ),
        ]

        result = service.deduplicate_links(links)
        assert len(result) == 1

        methods = service.get_link_methods("REQ-001", "TC-001")
        # Methods should be ordered by confidence (highest first)
        assert "exact_id_match" in methods
        assert "cross_reference" in methods
        assert "semantic_match" in methods
        assert len(methods) == 3

    def test_empty_input_returns_empty(self, service: TraceabilityMatrixService):
        """Empty candidate list returns empty result."""
        result = service.deduplicate_links([])
        assert result == []

    def test_different_pairs_not_deduplicated(
        self, service: TraceabilityMatrixService
    ):
        """Links with different (req_id, tc_id) pairs are not deduplicated."""
        links = [
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-001",
                test_case_text="Test 1.",
                target_document_uuid="doc-002",
                target_section="1.1",
                link_confidence=1.0,
                link_method="exact_id_match",
            ),
            CandidateLink(
                requirement_id="REQ-001",
                requirement_text="Req 1.",
                source_document_uuid="doc-001",
                source_section="1.1",
                test_case_id="TC-002",
                test_case_text="Test 2.",
                target_document_uuid="doc-002",
                target_section="1.2",
                link_confidence=0.9,
                link_method="cross_reference",
            ),
        ]

        result = service.deduplicate_links(links)
        assert len(result) == 2


class TestRunThreePassMatching:
    """Tests for run_three_pass_matching orchestration."""

    @pytest.mark.asyncio
    async def test_completed_status_when_all_passes_succeed(self):
        """Status is 'completed' when all three passes succeed."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],  # req embeddings
                [[0.0, 1.0]],  # tc embeddings (orthogonal, no match)
            ]
        )
        mock_xref = AsyncMock()
        mock_xref.build_cross_reference_map = AsyncMock(
            return_value={"requirement": [], "test_case": [], "section": []}
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_ks,
            cross_reference_service=mock_xref,
        )

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Validate input.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test REQ-001 validation.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        result = await service.run_three_pass_matching(
            requirements, test_cases, company_id=1
        )
        assert result.status == "completed"
        assert len(result.links) >= 1  # At least the exact match

    @pytest.mark.asyncio
    async def test_partial_success_when_knowledge_service_fails(self):
        """Status is 'partial_success' when KnowledgeService is unavailable."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=ConnectionError("Service unavailable")
        )
        mock_xref = AsyncMock()
        mock_xref.build_cross_reference_map = AsyncMock(
            return_value={"requirement": [], "test_case": [], "section": []}
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_ks,
            cross_reference_service=mock_xref,
        )

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Validate input.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test REQ-001 validation.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        result = await service.run_three_pass_matching(
            requirements, test_cases, company_id=1
        )
        assert result.status == "partial_success"
        assert "semantic_match" in result.metadata.get("skipped_passes", [])
        assert result.metadata.get("pass_3_skipped") is True

    @pytest.mark.asyncio
    async def test_partial_success_when_cross_reference_service_fails(self):
        """Status is 'partial_success' when CrossReferenceService is unavailable."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],  # req embeddings
                [[0.0, 1.0]],  # tc embeddings (orthogonal)
            ]
        )
        mock_xref = AsyncMock()
        mock_xref.build_cross_reference_map = AsyncMock(
            side_effect=ConnectionError("Service unavailable")
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_ks,
            cross_reference_service=mock_xref,
        )

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Validate input.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test REQ-001 validation.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        result = await service.run_three_pass_matching(
            requirements, test_cases, company_id=1
        )
        assert result.status == "partial_success"
        assert "cross_reference" in result.metadata.get("skipped_passes", [])
        assert result.metadata.get("pass_2_skipped") is True

    @pytest.mark.asyncio
    async def test_metadata_contains_pass_counts(self):
        """Metadata includes counts from each pass."""
        from unittest.mock import AsyncMock

        mock_ks = AsyncMock()
        mock_ks.generate_embeddings = AsyncMock(
            side_effect=[
                [[1.0, 0.0]],
                [[0.0, 1.0]],
            ]
        )
        mock_xref = AsyncMock()
        mock_xref.build_cross_reference_map = AsyncMock(
            return_value={"requirement": [], "test_case": [], "section": []}
        )

        service = TraceabilityMatrixService(
            knowledge_service=mock_ks,
            cross_reference_service=mock_xref,
        )

        requirements = [
            ExtractedRequirement(
                requirement_id="REQ-001",
                requirement_text="Validate input.",
                source_document_uuid="doc-001",
                source_section="1.1",
            ),
        ]
        test_cases = [
            ExtractedTestCase(
                test_case_id="TC-001",
                test_case_text="Test REQ-001 validation.",
                target_document_uuid="doc-002",
                target_section="1.1",
            ),
        ]

        result = await service.run_three_pass_matching(
            requirements, test_cases, company_id=1
        )
        assert "pass_1_count" in result.metadata
        assert "pass_2_count" in result.metadata
        assert "pass_3_count" in result.metadata
        assert "total_candidates_before_dedup" in result.metadata
        assert "total_links_after_dedup" in result.metadata


class TestCosineSimilarity:
    """Tests for _cosine_similarity static method."""

    def test_identical_vectors_return_one(self):
        """Identical unit vectors have similarity 1.0."""
        result = TraceabilityMatrixService._cosine_similarity(
            [1.0, 0.0, 0.0], [1.0, 0.0, 0.0]
        )
        assert abs(result - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self):
        """Orthogonal vectors have similarity 0.0."""
        result = TraceabilityMatrixService._cosine_similarity(
            [1.0, 0.0], [0.0, 1.0]
        )
        assert abs(result - 0.0) < 1e-9

    def test_zero_vector_returns_zero(self):
        """Zero magnitude vector returns 0.0."""
        result = TraceabilityMatrixService._cosine_similarity(
            [0.0, 0.0], [1.0, 0.0]
        )
        assert result == 0.0

    def test_different_lengths_return_zero(self):
        """Vectors of different lengths return 0.0."""
        result = TraceabilityMatrixService._cosine_similarity(
            [1.0, 0.0], [1.0, 0.0, 0.0]
        )
        assert result == 0.0

    def test_negative_similarity_clamped_to_zero(self):
        """Negative cosine similarity is clamped to 0.0."""
        result = TraceabilityMatrixService._cosine_similarity(
            [1.0, 0.0], [-1.0, 0.0]
        )
        assert result == 0.0
