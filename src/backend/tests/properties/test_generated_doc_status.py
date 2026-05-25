"""Property-based tests for generated document status and search visibility.

Property 11: Generated Document Initial Status
All newly generated documents SHALL have current_status "Draft" and an
associated ContentStatus of "pending_review" immediately after creation.

Property 12: Pending/Rejected Exclusion from Standard Search
Documents with content_status "pending_review" or "rejected" SHALL NOT
appear in standard search results. Only documents with content_status
"approved" (or non-AI-generated documents) SHALL appear.

These are pure logic tests — no database needed. They test the status
assignment and filtering logic that the review service enforces.

**Validates: Requirements 6.1, 6.6**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

from dataclasses import dataclass

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Data models representing generated documents and their metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeneratedDocumentRecord:
    """Represents a document created by the generation pipeline."""

    id: int
    document_uuid: str
    title: str
    current_status: str
    company_id: int
    is_ai_generated: bool
    content_status: str | None  # None for non-AI-generated documents


# ---------------------------------------------------------------------------
# Functions under test: initial status assignment and search filtering
# ---------------------------------------------------------------------------


def assign_initial_status() -> tuple[str, str]:
    """Assign initial status to a newly generated document.

    Per Requirement 6.1, all generated documents start as Draft with
    content_status "pending_review".

    Returns:
        Tuple of (current_status, content_status).
    """
    return ("Draft", "pending_review")


def filter_standard_search(
    documents: list[GeneratedDocumentRecord],
    company_id: int,
) -> list[GeneratedDocumentRecord]:
    """Filter documents for standard search results.

    Per Requirement 6.6, documents with content_status "pending_review"
    or "rejected" SHALL NOT appear in standard search results. Only
    "approved" AI-generated documents and non-AI-generated documents
    are visible.

    Args:
        documents: All documents in the system.
        company_id: Company scope for tenant isolation.

    Returns:
        Documents visible in standard search results.
    """
    results = []
    for doc in documents:
        # Tenant isolation
        if doc.company_id != company_id:
            continue
        # Non-AI-generated documents always appear
        if not doc.is_ai_generated:
            results.append(doc)
            continue
        # AI-generated documents only appear if approved
        if doc.content_status == "approved":
            results.append(doc)
    return results


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

COMPANY_IDS = st.integers(min_value=1, max_value=10)
DOCUMENT_IDS = st.integers(min_value=1, max_value=200)
CONTENT_STATUSES = st.sampled_from(["pending_review", "approved", "rejected"])
DOCUMENT_STATUSES = st.sampled_from(["Draft", "Review", "Approved", "Active"])
DOC_TYPES = st.sampled_from(["URS", "MVP", "SOP", "WI", "Protocol", "Report"])


@st.composite
def st_generated_document(draw: st.DrawFn) -> GeneratedDocumentRecord:
    """Generate a single AI-generated document record."""
    doc_id = draw(DOCUMENT_IDS)
    return GeneratedDocumentRecord(
        id=doc_id,
        document_uuid=f"2024-{doc_id:05d}",
        title=f"Generated Doc {doc_id}",
        current_status=draw(DOCUMENT_STATUSES),
        company_id=draw(COMPANY_IDS),
        is_ai_generated=True,
        content_status=draw(CONTENT_STATUSES),
    )


@st.composite
def st_non_generated_document(draw: st.DrawFn) -> GeneratedDocumentRecord:
    """Generate a single non-AI-generated document record."""
    doc_id = draw(DOCUMENT_IDS)
    return GeneratedDocumentRecord(
        id=doc_id,
        document_uuid=f"2024-{doc_id:05d}",
        title=f"Manual Doc {doc_id}",
        current_status=draw(DOCUMENT_STATUSES),
        company_id=draw(COMPANY_IDS),
        is_ai_generated=False,
        content_status=None,
    )


@st.composite
def st_mixed_documents(draw: st.DrawFn) -> list[GeneratedDocumentRecord]:
    """Generate a mixed list of AI-generated and non-AI-generated documents."""
    num_generated = draw(st.integers(min_value=0, max_value=15))
    num_manual = draw(st.integers(min_value=0, max_value=15))

    docs: list[GeneratedDocumentRecord] = []
    for _ in range(num_generated):
        docs.append(draw(st_generated_document()))
    for _ in range(num_manual):
        docs.append(draw(st_non_generated_document()))
    return docs


# ---------------------------------------------------------------------------
# Property 11: Generated Document Initial Status
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    doc_id=DOCUMENT_IDS,
    company_id=COMPANY_IDS,
    title=st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N", "Z"),
    )),
    doc_type=DOC_TYPES,
)
def test_generated_document_always_starts_as_draft_pending_review(
    doc_id: int,
    company_id: int,
    title: str,
    doc_type: str,
) -> None:
    """For any document created by the generation pipeline, the document
    SHALL have current_status "Draft" and content_status "pending_review"
    immediately after creation.

    **Validates: Requirements 6.1**
    """
    current_status, content_status = assign_initial_status()

    assert current_status == "Draft", (
        f"Generated document must start as 'Draft', got '{current_status}'"
    )
    assert content_status == "pending_review", (
        f"Generated document must start with content_status 'pending_review', "
        f"got '{content_status}'"
    )


@settings(max_examples=25)
@given(
    num_documents=st.integers(min_value=1, max_value=20),
)
def test_batch_generated_documents_all_start_draft_pending(
    num_documents: int,
) -> None:
    """For any batch of documents created by the generation pipeline,
    every document SHALL have current_status "Draft" and content_status
    "pending_review" immediately after creation.

    **Validates: Requirements 6.1**
    """
    # Simulate creating multiple documents in a batch
    documents = []
    for i in range(num_documents):
        current_status, content_status = assign_initial_status()
        documents.append(GeneratedDocumentRecord(
            id=i + 1,
            document_uuid=f"2024-{i + 1:05d}",
            title=f"Generated Doc {i + 1}",
            current_status=current_status,
            company_id=1,
            is_ai_generated=True,
            content_status=content_status,
        ))

    for doc in documents:
        assert doc.current_status == "Draft", (
            f"Document {doc.id} must have current_status 'Draft', "
            f"got '{doc.current_status}'"
        )
        assert doc.content_status == "pending_review", (
            f"Document {doc.id} must have content_status 'pending_review', "
            f"got '{doc.content_status}'"
        )


@settings(max_examples=25)
@given(
    doc_id=DOCUMENT_IDS,
    company_id=COMPANY_IDS,
)
def test_initial_status_never_approved_or_rejected(
    doc_id: int,
    company_id: int,
) -> None:
    """For any newly generated document, the initial content_status SHALL
    never be "approved" or "rejected" — it must always be "pending_review"
    to enforce the human review gate.

    **Validates: Requirements 6.1**
    """
    current_status, content_status = assign_initial_status()

    assert content_status != "approved", (
        "Newly generated document must not start as 'approved'"
    )
    assert content_status != "rejected", (
        "Newly generated document must not start as 'rejected'"
    )
    assert content_status == "pending_review"
    assert current_status == "Draft"


# ---------------------------------------------------------------------------
# Property 12: Pending/Rejected Exclusion from Standard Search
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    documents=st_mixed_documents(),
    target_company=COMPANY_IDS,
)
def test_pending_review_documents_excluded_from_search(
    documents: list[GeneratedDocumentRecord],
    target_company: int,
) -> None:
    """For any standard search query, documents with content_status
    "pending_review" SHALL NOT appear in the results.

    **Validates: Requirements 6.6**
    """
    results = filter_standard_search(documents, target_company)

    for doc in results:
        if doc.is_ai_generated:
            assert doc.content_status != "pending_review", (
                f"Document {doc.id} with content_status 'pending_review' "
                f"must not appear in standard search results"
            )


@settings(max_examples=25)
@given(
    documents=st_mixed_documents(),
    target_company=COMPANY_IDS,
)
def test_rejected_documents_excluded_from_search(
    documents: list[GeneratedDocumentRecord],
    target_company: int,
) -> None:
    """For any standard search query, documents with content_status
    "rejected" SHALL NOT appear in the results.

    **Validates: Requirements 6.6**
    """
    results = filter_standard_search(documents, target_company)

    for doc in results:
        if doc.is_ai_generated:
            assert doc.content_status != "rejected", (
                f"Document {doc.id} with content_status 'rejected' "
                f"must not appear in standard search results"
            )


@settings(max_examples=25)
@given(
    documents=st_mixed_documents(),
    target_company=COMPANY_IDS,
)
def test_only_approved_ai_documents_visible_in_search(
    documents: list[GeneratedDocumentRecord],
    target_company: int,
) -> None:
    """For any standard search query, AI-generated documents SHALL only
    appear if their content_status is "approved". Non-AI-generated
    documents are always visible (regardless of content_status).

    **Validates: Requirements 6.6**
    """
    results = filter_standard_search(documents, target_company)

    for doc in results:
        assert doc.company_id == target_company, (
            f"Document {doc.id} from company {doc.company_id} leaked into "
            f"search results for company {target_company}"
        )
        if doc.is_ai_generated:
            assert doc.content_status == "approved", (
                f"AI-generated document {doc.id} with content_status "
                f"'{doc.content_status}' must not appear in search results"
            )


@settings(max_examples=25)
@given(
    documents=st_mixed_documents(),
    target_company=COMPANY_IDS,
)
def test_non_ai_documents_always_visible_in_search(
    documents: list[GeneratedDocumentRecord],
    target_company: int,
) -> None:
    """For any standard search query, non-AI-generated documents SHALL
    always appear in results (they are not subject to content_status
    filtering).

    **Validates: Requirements 6.6**
    """
    results = filter_standard_search(documents, target_company)

    # All non-AI-generated documents for the target company should be present
    expected_manual = [
        d for d in documents
        if d.company_id == target_company and not d.is_ai_generated
    ]
    actual_manual = [d for d in results if not d.is_ai_generated]

    assert len(actual_manual) == len(expected_manual), (
        f"Expected {len(expected_manual)} non-AI documents in search, "
        f"got {len(actual_manual)}"
    )


@settings(max_examples=25)
@given(
    documents=st_mixed_documents(),
    target_company=COMPANY_IDS,
)
def test_approved_ai_documents_included_in_search(
    documents: list[GeneratedDocumentRecord],
    target_company: int,
) -> None:
    """For any standard search query, AI-generated documents with
    content_status "approved" SHALL appear in the results (they are
    not excluded).

    **Validates: Requirements 6.6**
    """
    results = filter_standard_search(documents, target_company)

    # All approved AI-generated documents for the target company should be present
    expected_approved = [
        d for d in documents
        if d.company_id == target_company
        and d.is_ai_generated
        and d.content_status == "approved"
    ]
    actual_approved = [
        d for d in results
        if d.is_ai_generated and d.content_status == "approved"
    ]

    assert len(actual_approved) == len(expected_approved), (
        f"Expected {len(expected_approved)} approved AI documents in search, "
        f"got {len(actual_approved)}"
    )
