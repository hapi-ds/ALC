"""Property-based tests for dependency type classification.

Property 2: Dependency Type Classification

For any pair of documents with identifiable cross-references, the dependency_type
SHALL be classified correctly:
- "validates" for requirement ID cross-references between MVP/IQ/OQ/PQ and URS documents
- "references" for explicit document_uuid citations or title mentions
- "implements" for test case IDs referencing requirement IDs
- "trains_on" for TrainingTask records (handled in _build_db_linked_edges)
- "derived_from" for GenerationProvenance records (handled in _build_db_linked_edges)

**Validates: Requirements 1.4**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
    - Module: src/backend/src/alcoabase/services/dependency_graph.py
"""

from __future__ import annotations

from dataclasses import dataclass

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings

from alcoabase.services.cross_reference import CrossReference
from alcoabase.services.dependency_graph import (
    DependencyGraphService,
    _VALIDATION_DOC_TYPES,
    _URS_DOC_TYPES,
)


# ---------------------------------------------------------------------------
# Lightweight Document stub for pure-logic testing
# ---------------------------------------------------------------------------


@dataclass
class DocumentStub:
    """Minimal Document-like object for testing _classify_dependency_type.

    Only the fields accessed by the classification method are needed:
    id, document_uuid, document_type.
    """

    id: int
    document_uuid: str
    document_type: str
    title: str = "Test Document"


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

DOCUMENT_IDS = st.integers(min_value=1, max_value=10000)
DOCUMENT_UUIDS = st.from_regex(r"2025-\d{5}", fullmatch=True)

VALIDATION_DOC_TYPES = st.sampled_from(sorted(_VALIDATION_DOC_TYPES))
URS_DOC_TYPES = st.sampled_from(sorted(_URS_DOC_TYPES))

# Document types that are neither validation nor URS
OTHER_DOC_TYPES = st.sampled_from(["SOP", "Report", "Template", "Protocol", "Form"])

# All possible document types
ALL_DOC_TYPES = st.sampled_from(
    sorted(_VALIDATION_DOC_TYPES) + sorted(_URS_DOC_TYPES)
    + ["SOP", "Report", "Template", "Protocol", "Form"]
)

REFERENCE_TYPES = st.sampled_from(["requirement", "test_case", "section"])

REFERENCE_IDENTIFIERS = st.from_regex(r"[A-Z]{2,4}-\d{3,5}", fullmatch=True)

REFERENCE_TEXTS = st.text(min_size=5, max_size=150, alphabet=st.characters(
    whitelist_categories=("L", "N", "P", "Z"),
))

DOCUMENT_TITLES = st.text(min_size=3, max_size=100, alphabet=st.characters(
    whitelist_categories=("L", "N", "Z"),
))


@st.composite
def st_cross_reference(
    draw: st.DrawFn,
    reference_type: st.SearchStrategy[str] | None = None,
) -> CrossReference:
    """Generate a CrossReference with configurable reference_type."""
    ref_type = draw(reference_type if reference_type is not None else REFERENCE_TYPES)
    return CrossReference(
        reference_type=ref_type,
        reference_identifier=draw(REFERENCE_IDENTIFIERS),
        reference_text=draw(REFERENCE_TEXTS),
        source_document_id=draw(DOCUMENT_IDS),
        source_document_title=draw(DOCUMENT_TITLES),
    )


@st.composite
def st_document_stub(
    draw: st.DrawFn,
    doc_type: st.SearchStrategy[str] | None = None,
) -> DocumentStub:
    """Generate a DocumentStub with configurable document_type."""
    return DocumentStub(
        id=draw(DOCUMENT_IDS),
        document_uuid=draw(DOCUMENT_UUIDS),
        document_type=draw(doc_type if doc_type is not None else ALL_DOC_TYPES),
        title=draw(DOCUMENT_TITLES),
    )


# ---------------------------------------------------------------------------
# Service instance (stateless for classification — no session_factory needed)
# ---------------------------------------------------------------------------

_service = DependencyGraphService()


# ---------------------------------------------------------------------------
# Property 2: Dependency Type Classification
# ---------------------------------------------------------------------------


class TestValidatesClassification:
    """Validates: requirement ID cross-references between MVP/IQ/OQ/PQ and URS."""

    @settings(max_examples=100)
    @given(
        source_doc=st_document_stub(doc_type=VALIDATION_DOC_TYPES),
        target_doc=st_document_stub(doc_type=URS_DOC_TYPES),
        ref=st_cross_reference(reference_type=st.just("requirement")),
    )
    def test_validation_doc_referencing_urs_with_requirement_type_returns_validates(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """When a validation document (MVP/IQ/OQ/PQ) references a URS document
        with reference_type "requirement", the dependency type SHALL be "validates".

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result == "validates"

    @settings(max_examples=100)
    @given(
        source_doc=st_document_stub(doc_type=URS_DOC_TYPES),
        target_doc=st_document_stub(doc_type=VALIDATION_DOC_TYPES),
        ref=st_cross_reference(reference_type=st.just("requirement")),
    )
    def test_urs_doc_referencing_validation_doc_with_requirement_type_returns_validates(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """When a URS document references a validation document (MVP/IQ/OQ/PQ)
        with reference_type "requirement", the dependency type SHALL be "validates".

        This covers the reverse direction: URS → validation doc.

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result == "validates"


class TestImplementsClassification:
    """Implements: test case IDs referencing requirement IDs."""

    @settings(max_examples=100)
    @given(
        source_doc=st_document_stub(doc_type=OTHER_DOC_TYPES),
        target_doc=st_document_stub(doc_type=OTHER_DOC_TYPES),
        ref=st_cross_reference(reference_type=st.just("test_case")),
    )
    def test_test_case_reference_type_returns_implements(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """When a cross-reference has reference_type "test_case" (and the
        source/target are not in the validates path), the dependency type
        SHALL be "implements".

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result == "implements"

    @settings(max_examples=50)
    @given(
        source_doc=st_document_stub(doc_type=VALIDATION_DOC_TYPES),
        target_doc=st_document_stub(doc_type=URS_DOC_TYPES),
        ref=st_cross_reference(reference_type=st.just("test_case")),
    )
    def test_test_case_reference_from_validation_to_urs_returns_implements(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """When a validation doc references a URS doc with reference_type
        "test_case", the dependency type SHALL be "implements" because
        the "validates" path requires reference_type "requirement".

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        # The validates check requires reference_type == "requirement",
        # so test_case falls through to the implements check
        assert result == "implements"


class TestReferencesClassification:
    """References: explicit document_uuid citations or title mentions."""

    @settings(max_examples=100)
    @given(
        source_doc=st_document_stub(doc_type=OTHER_DOC_TYPES),
        target_doc=st_document_stub(doc_type=OTHER_DOC_TYPES),
        ref=st_cross_reference(reference_type=st.just("section")),
    )
    def test_section_reference_between_non_special_docs_returns_references(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """When a cross-reference has reference_type "section" between
        non-validation/non-URS documents, the dependency type SHALL be
        "references" (the default classification).

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result == "references"

    @settings(max_examples=100)
    @given(
        source_doc=st_document_stub(doc_type=OTHER_DOC_TYPES),
        target_doc=st_document_stub(doc_type=OTHER_DOC_TYPES),
        ref=st_cross_reference(reference_type=st.just("requirement")),
    )
    def test_requirement_reference_between_non_special_docs_returns_references(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """When a cross-reference has reference_type "requirement" but neither
        document is a validation doc or URS, the dependency type SHALL be
        "references" (the default).

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result == "references"

    @settings(max_examples=50)
    @given(
        source_doc=st_document_stub(doc_type=VALIDATION_DOC_TYPES),
        target_doc=st_document_stub(doc_type=OTHER_DOC_TYPES),
        ref=st_cross_reference(reference_type=st.just("section")),
    )
    def test_section_reference_from_validation_to_non_urs_returns_references(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """When a validation doc references a non-URS doc with reference_type
        "section", the dependency type SHALL be "references" because the
        validates path requires target to be URS.

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result == "references"


class TestDbLinkedTypesHandledSeparately:
    """Trains_on and derived_from are handled in _build_db_linked_edges,
    not in _classify_dependency_type. This test verifies that the
    classification method never returns these types for cross-references."""

    @settings(max_examples=200)
    @given(
        source_doc=st_document_stub(),
        target_doc=st_document_stub(),
        ref=st_cross_reference(),
    )
    def test_classify_never_returns_trains_on_or_derived_from(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """The _classify_dependency_type method SHALL never return "trains_on"
        or "derived_from" because those types are exclusively assigned by
        _build_db_linked_edges from TrainingTask and GenerationProvenance records.

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result in {"validates", "references", "implements"}
        assert result not in {"trains_on", "derived_from"}


class TestClassificationExhaustiveness:
    """Verify that all possible inputs produce a valid dependency type."""

    @settings(max_examples=200)
    @given(
        source_doc=st_document_stub(),
        target_doc=st_document_stub(),
        ref=st_cross_reference(),
    )
    def test_classification_always_returns_valid_type(
        self,
        source_doc: DocumentStub,
        target_doc: DocumentStub,
        ref: CrossReference,
    ) -> None:
        """For any combination of document types and reference types, the
        _classify_dependency_type method SHALL always return one of the
        valid dependency types: "validates", "references", or "implements".

        **Validates: Requirements 1.4**
        """
        # Ensure distinct documents
        target_doc.id = source_doc.id + 1

        result = _service._classify_dependency_type(ref, source_doc, target_doc)
        assert result in {"validates", "references", "implements"}
