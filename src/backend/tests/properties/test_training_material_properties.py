"""Property-based tests for AI-generated content initial status.

Tests Property 5 from the AI-Enhanced Training Ecosystem design document,
validating that all AI-generated content (TrainingMaterial and GeneratedQuestion)
starts with ContentStatus "pending_review" regardless of material type or
generation parameters.

**Validates: Requirements 3.6, 4.7**

References:
    - Design: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/design.md (Property 5)
    - Requirements: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/requirements.md (3.6, 4.7)
"""

import hypothesis.strategies as st
from hypothesis import given, settings

from alcoabase.models.training_ecosystem import (
    ContentStatus,
    DifficultyLevel,
    GeneratedQuestion,
    MaterialType,
    QuestionType,
    TrainingMaterial,
)

# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

#: All valid material types from the MaterialType enum.
MATERIAL_TYPES = list(MaterialType)

#: All valid question types from the QuestionType enum.
QUESTION_TYPES = list(QuestionType)

#: All valid difficulty levels from the DifficultyLevel enum.
DIFFICULTY_LEVELS = list(DifficultyLevel)

#: Bloom's taxonomy levels used in question generation.
BLOOM_LEVELS = ["remember", "understand", "apply", "analyze"]


@st.composite
def st_training_material_params(draw: st.DrawFn) -> dict:
    """Generate random parameters for creating a TrainingMaterial instance.

    Produces valid combinations of material type, content data, learning
    objectives, and duration that would be used during material generation.

    Returns:
        Dictionary of keyword arguments for TrainingMaterial construction.
    """
    material_type = draw(st.sampled_from(MATERIAL_TYPES))
    content_data = draw(
        st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.text(min_size=1, max_size=100),
            min_size=1,
            max_size=5,
        )
    )
    learning_objectives = draw(
        st.lists(
            st.text(min_size=5, max_size=100),
            min_size=1,
            max_size=5,
        )
    )
    estimated_duration_minutes = draw(st.integers(min_value=1, max_value=480))
    document_id = draw(st.integers(min_value=1, max_value=10000))
    document_version_id = draw(st.integers(min_value=1, max_value=10000))
    company_id = draw(st.integers(min_value=1, max_value=10000))

    return {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "company_id": company_id,
        "material_type": material_type,
        "content_data": content_data,
        "learning_objectives": learning_objectives,
        "estimated_duration_minutes": estimated_duration_minutes,
    }


@st.composite
def st_generated_question_params(draw: st.DrawFn) -> dict:
    """Generate random parameters for creating a GeneratedQuestion instance.

    Produces valid combinations of question type, difficulty level, and
    content that would be used during question generation.

    Returns:
        Dictionary of keyword arguments for GeneratedQuestion construction.
    """
    question_type = draw(st.sampled_from(QUESTION_TYPES))
    difficulty_level = draw(st.sampled_from(DIFFICULTY_LEVELS))
    bloom_taxonomy_level = draw(st.sampled_from(BLOOM_LEVELS))
    question_text = draw(st.text(min_size=10, max_size=200))
    correct_answer = draw(st.text(min_size=1, max_size=100))
    explanation = draw(st.text(min_size=5, max_size=200))
    sop_section_ref = draw(st.text(min_size=3, max_size=50))
    document_id = draw(st.integers(min_value=1, max_value=10000))
    document_version_id = draw(st.integers(min_value=1, max_value=10000))
    company_id = draw(st.integers(min_value=1, max_value=10000))

    params: dict = {
        "document_id": document_id,
        "document_version_id": document_version_id,
        "company_id": company_id,
        "question_text": question_text,
        "question_type": question_type,
        "correct_answer": correct_answer,
        "explanation": explanation,
        "difficulty_level": difficulty_level,
        "bloom_taxonomy_level": bloom_taxonomy_level,
        "sop_section_ref": sop_section_ref,
    }

    # Add distractors for multiple choice questions
    if question_type == QuestionType.MULTIPLE_CHOICE:
        params["distractors"] = draw(
            st.lists(
                st.text(min_size=1, max_size=50),
                min_size=3,
                max_size=3,
            )
        )

    return params


# ---------------------------------------------------------------------------
# Property 5: All AI-generated content starts in pending_review status
# ---------------------------------------------------------------------------


# Feature: ai-enhanced-training-ecosystem, Property 5: TrainingMaterial defaults to pending_review
@settings(max_examples=200)
@given(params=st_training_material_params())
def test_training_material_starts_pending_review(params: dict) -> None:
    """For any material type and generation parameters, a newly created
    TrainingMaterial SHALL have status equal to ContentStatus.PENDING_REVIEW.

    **Validates: Requirements 3.6, 4.7**
    """
    material = TrainingMaterial(**params)

    assert material.status == ContentStatus.PENDING_REVIEW.value, (
        f"TrainingMaterial status is '{material.status}' instead of "
        f"'{ContentStatus.PENDING_REVIEW.value}' for material_type="
        f"{params['material_type']}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 5: GeneratedQuestion defaults to pending_review
@settings(max_examples=200)
@given(params=st_generated_question_params())
def test_generated_question_starts_pending_review(params: dict) -> None:
    """For any question type, difficulty level, and generation parameters,
    a newly created GeneratedQuestion SHALL have status equal to
    ContentStatus.PENDING_REVIEW.

    **Validates: Requirements 3.6, 4.7**
    """
    question = GeneratedQuestion(**params)

    assert question.status == ContentStatus.PENDING_REVIEW.value, (
        f"GeneratedQuestion status is '{question.status}' instead of "
        f"'{ContentStatus.PENDING_REVIEW.value}' for question_type="
        f"{params['question_type']}, difficulty_level="
        f"{params['difficulty_level']}"
    )


# Feature: ai-enhanced-training-ecosystem, Property 5: Status is never None on creation
@settings(max_examples=200)
@given(
    material_params=st_training_material_params(),
    question_params=st_generated_question_params(),
)
def test_content_status_never_none_on_creation(
    material_params: dict, question_params: dict
) -> None:
    """For any combination of generation parameters, the status field
    SHALL never be None when a TrainingMaterial or GeneratedQuestion
    is instantiated.

    **Validates: Requirements 3.6, 4.7**
    """
    material = TrainingMaterial(**material_params)
    question = GeneratedQuestion(**question_params)

    assert material.status is not None, (
        "TrainingMaterial status is None on creation"
    )
    assert question.status is not None, (
        "GeneratedQuestion status is None on creation"
    )
