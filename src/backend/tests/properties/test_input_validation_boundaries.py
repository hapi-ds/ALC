"""Property-based tests for input validation boundaries on document generation schemas.

Property 19: Input Validation Boundaries
Pydantic schemas correctly validate input boundaries — valid inputs within
bounds are accepted, and invalid inputs outside bounds are rejected with
ValidationError.

Tests three request schemas:
- TemplateRegisterRequest: template_name (1-500 chars), document_type_target (1-100 chars)
- GenerateFromTemplateRequest: title (1-500 chars), generation_instructions (1-10000 chars),
  reference_document_ids (max 20 items), output_folder_path (1-1000 chars)
- DocumentReviewRequest: reviewer_comments (max 2000 chars), action must be "approve" or "reject"

**Validates: Requirements 1.13, 2.13**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md
"""

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings
from pydantic import ValidationError

from alcoabase.schemas.document_generation import (
    DocumentReviewRequest,
    GenerateFromTemplateRequest,
    TemplateRegisterRequest,
)


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

VALID_IDS = st.integers(min_value=1, max_value=10000)


def st_string_of_length(min_len: int, max_len: int) -> st.SearchStrategy[str]:
    """Generate a non-whitespace-only string within the given length bounds."""
    return st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N", "P", "S"),
            min_codepoint=32,
            max_codepoint=126,
        ),
        min_size=min_len,
        max_size=max_len,
    ).filter(lambda s: len(s.strip()) > 0)


# ---------------------------------------------------------------------------
# Property 19: TemplateRegisterRequest — Valid inputs accepted
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    document_id=VALID_IDS,
    document_version_id=VALID_IDS,
    template_name=st_string_of_length(1, 500),
    document_type_target=st_string_of_length(1, 100),
)
def test_template_register_request_accepts_valid_inputs(
    document_id: int,
    document_version_id: int,
    template_name: str,
    document_type_target: str,
) -> None:
    """TemplateRegisterRequest SHALL accept template_name (1-500 chars) and
    document_type_target (1-100 chars) when within valid bounds.

    **Validates: Requirements 1.13**
    """
    request = TemplateRegisterRequest(
        document_id=document_id,
        document_version_id=document_version_id,
        template_name=template_name,
        document_type_target=document_type_target,
    )
    assert request.template_name == template_name
    assert request.document_type_target == document_type_target
    assert 1 <= len(request.template_name) <= 500
    assert 1 <= len(request.document_type_target) <= 100


# ---------------------------------------------------------------------------
# Property 19: TemplateRegisterRequest — Invalid inputs rejected
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    document_id=VALID_IDS,
    document_version_id=VALID_IDS,
    # Generate a string that exceeds 500 characters
    template_name=st.text(
        alphabet=st.characters(min_codepoint=65, max_codepoint=90),
        min_size=501,
        max_size=600,
    ),
    document_type_target=st_string_of_length(1, 100),
)
def test_template_register_request_rejects_template_name_too_long(
    document_id: int,
    document_version_id: int,
    template_name: str,
    document_type_target: str,
) -> None:
    """TemplateRegisterRequest SHALL reject template_name exceeding 500 characters
    with a ValidationError.

    **Validates: Requirements 1.13**
    """
    with pytest.raises(ValidationError):
        TemplateRegisterRequest(
            document_id=document_id,
            document_version_id=document_version_id,
            template_name=template_name,
            document_type_target=document_type_target,
        )


@settings(max_examples=25)
@given(
    document_id=VALID_IDS,
    document_version_id=VALID_IDS,
    template_name=st_string_of_length(1, 500),
    # Generate a string that exceeds 100 characters
    document_type_target=st.text(
        alphabet=st.characters(min_codepoint=65, max_codepoint=90),
        min_size=101,
        max_size=200,
    ),
)
def test_template_register_request_rejects_document_type_target_too_long(
    document_id: int,
    document_version_id: int,
    template_name: str,
    document_type_target: str,
) -> None:
    """TemplateRegisterRequest SHALL reject document_type_target exceeding 100
    characters with a ValidationError.

    **Validates: Requirements 1.13**
    """
    with pytest.raises(ValidationError):
        TemplateRegisterRequest(
            document_id=document_id,
            document_version_id=document_version_id,
            template_name=template_name,
            document_type_target=document_type_target,
        )


@settings(max_examples=25)
@given(
    document_id=VALID_IDS,
    document_version_id=VALID_IDS,
    document_type_target=st_string_of_length(1, 100),
)
def test_template_register_request_rejects_empty_template_name(
    document_id: int,
    document_version_id: int,
    document_type_target: str,
) -> None:
    """TemplateRegisterRequest SHALL reject an empty template_name with a
    ValidationError.

    **Validates: Requirements 1.13**
    """
    with pytest.raises(ValidationError):
        TemplateRegisterRequest(
            document_id=document_id,
            document_version_id=document_version_id,
            template_name="",
            document_type_target=document_type_target,
        )


@settings(max_examples=25)
@given(
    document_id=VALID_IDS,
    document_version_id=VALID_IDS,
    template_name=st_string_of_length(1, 500),
)
def test_template_register_request_rejects_empty_document_type_target(
    document_id: int,
    document_version_id: int,
    template_name: str,
) -> None:
    """TemplateRegisterRequest SHALL reject an empty document_type_target with a
    ValidationError.

    **Validates: Requirements 1.13**
    """
    with pytest.raises(ValidationError):
        TemplateRegisterRequest(
            document_id=document_id,
            document_version_id=document_version_id,
            template_name=template_name,
            document_type_target="",
        )


# ---------------------------------------------------------------------------
# Property 19: GenerateFromTemplateRequest — Valid inputs accepted
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    template_id=VALID_IDS,
    title=st_string_of_length(1, 500),
    generation_instructions=st_string_of_length(1, 10000),
    output_folder_path=st_string_of_length(1, 1000),
    num_ref_docs=st.integers(min_value=0, max_value=20),
)
def test_generate_from_template_request_accepts_valid_inputs(
    template_id: int,
    title: str,
    generation_instructions: str,
    output_folder_path: str,
    num_ref_docs: int,
) -> None:
    """GenerateFromTemplateRequest SHALL accept title (1-500 chars),
    generation_instructions (1-10000 chars), output_folder_path (1-1000 chars),
    and reference_document_ids (max 20 items) when within valid bounds.

    **Validates: Requirements 2.13**
    """
    ref_ids = list(range(1, num_ref_docs + 1)) if num_ref_docs > 0 else None

    request = GenerateFromTemplateRequest(
        template_id=template_id,
        title=title,
        generation_instructions=generation_instructions,
        reference_document_ids=ref_ids,
        output_folder_path=output_folder_path,
    )
    assert request.title == title
    assert request.generation_instructions == generation_instructions
    assert request.output_folder_path == output_folder_path
    assert 1 <= len(request.title) <= 500
    assert 1 <= len(request.generation_instructions) <= 10000
    assert 1 <= len(request.output_folder_path) <= 1000
    if ref_ids is not None:
        assert len(request.reference_document_ids) <= 20


# ---------------------------------------------------------------------------
# Property 19: GenerateFromTemplateRequest — Invalid inputs rejected
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    template_id=VALID_IDS,
    title=st.text(
        alphabet=st.characters(min_codepoint=65, max_codepoint=90),
        min_size=501,
        max_size=600,
    ),
    generation_instructions=st_string_of_length(1, 100),
    output_folder_path=st_string_of_length(1, 100),
)
def test_generate_from_template_request_rejects_title_too_long(
    template_id: int,
    title: str,
    generation_instructions: str,
    output_folder_path: str,
) -> None:
    """GenerateFromTemplateRequest SHALL reject title exceeding 500 characters
    with a ValidationError.

    **Validates: Requirements 2.13**
    """
    with pytest.raises(ValidationError):
        GenerateFromTemplateRequest(
            template_id=template_id,
            title=title,
            generation_instructions=generation_instructions,
            reference_document_ids=None,
            output_folder_path=output_folder_path,
        )


@settings(max_examples=25)
@given(
    template_id=VALID_IDS,
    title=st_string_of_length(1, 500),
    extra_length=st.integers(min_value=1, max_value=100),
    output_folder_path=st_string_of_length(1, 100),
)
def test_generate_from_template_request_rejects_instructions_too_long(
    template_id: int,
    title: str,
    extra_length: int,
    output_folder_path: str,
) -> None:
    """GenerateFromTemplateRequest SHALL reject generation_instructions exceeding
    10000 characters with a ValidationError.

    **Validates: Requirements 2.13**
    """
    # Build a string that exceeds the 10000 char limit
    generation_instructions = "A" * (10000 + extra_length)

    with pytest.raises(ValidationError):
        GenerateFromTemplateRequest(
            template_id=template_id,
            title=title,
            generation_instructions=generation_instructions,
            reference_document_ids=None,
            output_folder_path=output_folder_path,
        )


@settings(max_examples=25)
@given(
    template_id=VALID_IDS,
    title=st_string_of_length(1, 500),
    generation_instructions=st_string_of_length(1, 100),
    output_folder_path=st.text(
        alphabet=st.characters(min_codepoint=65, max_codepoint=90),
        min_size=1001,
        max_size=1100,
    ),
)
def test_generate_from_template_request_rejects_output_folder_path_too_long(
    template_id: int,
    title: str,
    generation_instructions: str,
    output_folder_path: str,
) -> None:
    """GenerateFromTemplateRequest SHALL reject output_folder_path exceeding
    1000 characters with a ValidationError.

    **Validates: Requirements 2.13**
    """
    with pytest.raises(ValidationError):
        GenerateFromTemplateRequest(
            template_id=template_id,
            title=title,
            generation_instructions=generation_instructions,
            reference_document_ids=None,
            output_folder_path=output_folder_path,
        )


@settings(max_examples=25)
@given(
    template_id=VALID_IDS,
    title=st_string_of_length(1, 500),
    generation_instructions=st_string_of_length(1, 100),
    output_folder_path=st_string_of_length(1, 100),
    num_ref_docs=st.integers(min_value=21, max_value=30),
)
def test_generate_from_template_request_rejects_too_many_reference_docs(
    template_id: int,
    title: str,
    generation_instructions: str,
    output_folder_path: str,
    num_ref_docs: int,
) -> None:
    """GenerateFromTemplateRequest SHALL reject reference_document_ids with more
    than 20 items with a ValidationError.

    **Validates: Requirements 2.13**
    """
    ref_ids = list(range(1, num_ref_docs + 1))

    with pytest.raises(ValidationError):
        GenerateFromTemplateRequest(
            template_id=template_id,
            title=title,
            generation_instructions=generation_instructions,
            reference_document_ids=ref_ids,
            output_folder_path=output_folder_path,
        )


@settings(max_examples=25)
@given(
    template_id=VALID_IDS,
    generation_instructions=st_string_of_length(1, 100),
    output_folder_path=st_string_of_length(1, 100),
)
def test_generate_from_template_request_rejects_empty_title(
    template_id: int,
    generation_instructions: str,
    output_folder_path: str,
) -> None:
    """GenerateFromTemplateRequest SHALL reject an empty title with a
    ValidationError.

    **Validates: Requirements 2.13**
    """
    with pytest.raises(ValidationError):
        GenerateFromTemplateRequest(
            template_id=template_id,
            title="",
            generation_instructions=generation_instructions,
            reference_document_ids=None,
            output_folder_path=output_folder_path,
        )


@settings(max_examples=25)
@given(
    template_id=VALID_IDS,
    title=st_string_of_length(1, 500),
    output_folder_path=st_string_of_length(1, 100),
)
def test_generate_from_template_request_rejects_empty_instructions(
    template_id: int,
    title: str,
    output_folder_path: str,
) -> None:
    """GenerateFromTemplateRequest SHALL reject empty generation_instructions
    with a ValidationError.

    **Validates: Requirements 2.13**
    """
    with pytest.raises(ValidationError):
        GenerateFromTemplateRequest(
            template_id=template_id,
            title=title,
            generation_instructions="",
            reference_document_ids=None,
            output_folder_path=output_folder_path,
        )


# ---------------------------------------------------------------------------
# Property 19: DocumentReviewRequest — Valid inputs accepted
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    action=st.sampled_from(["approve", "reject"]),
    reviewer_comments=st.one_of(
        st.none(),
        st_string_of_length(1, 2000),
    ),
)
def test_document_review_request_accepts_valid_inputs(
    action: str,
    reviewer_comments: str | None,
) -> None:
    """DocumentReviewRequest SHALL accept action ("approve" or "reject") and
    reviewer_comments (None or up to 2000 chars) when within valid bounds.

    **Validates: Requirements 1.13, 2.13**
    """
    request = DocumentReviewRequest(
        action=action,
        reviewer_comments=reviewer_comments,
    )
    assert request.action in ("approve", "reject")
    if request.reviewer_comments is not None:
        assert len(request.reviewer_comments) <= 2000


# ---------------------------------------------------------------------------
# Property 19: DocumentReviewRequest — Invalid inputs rejected
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(
    action=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=20,
    ).filter(lambda s: s not in ("approve", "reject")),
)
def test_document_review_request_rejects_invalid_action(
    action: str,
) -> None:
    """DocumentReviewRequest SHALL reject action values other than "approve"
    or "reject" with a ValidationError.

    **Validates: Requirements 1.13, 2.13**
    """
    with pytest.raises(ValidationError):
        DocumentReviewRequest(
            action=action,
            reviewer_comments=None,
        )


@settings(max_examples=25)
@given(
    action=st.sampled_from(["approve", "reject"]),
    reviewer_comments=st.text(
        alphabet=st.characters(min_codepoint=65, max_codepoint=90),
        min_size=2001,
        max_size=2100,
    ),
)
def test_document_review_request_rejects_comments_too_long(
    action: str,
    reviewer_comments: str,
) -> None:
    """DocumentReviewRequest SHALL reject reviewer_comments exceeding 2000
    characters with a ValidationError.

    **Validates: Requirements 1.13, 2.13**
    """
    with pytest.raises(ValidationError):
        DocumentReviewRequest(
            action=action,
            reviewer_comments=reviewer_comments,
        )
