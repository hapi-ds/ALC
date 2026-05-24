"""Property-based tests for company-scoped tenant isolation in the training ecosystem.

Property 4: Company-scoped tenant isolation
For any company_id filter, results only contain records with that company_id.

This is a pure logic test — no database needed. It tests the filtering concept
that simulates the WHERE company_id = X clause used across all training
ecosystem listing endpoints.

**Validates: Requirements 1.8, 2.6, 3.10, 6.12, 7.8, 9.15**

References:
    - Design: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/design.md
    - Requirements: .kiro/specs/Step_5-3_ai-enhanced-training-ecosystem/requirements.md
"""

from dataclasses import dataclass
from typing import Any

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Data models representing training ecosystem records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleRecord:
    """Represents a training schedule record with company scope."""

    id: int
    user_id: int
    company_id: int
    compliance_percentage: float
    total_items: int


@dataclass(frozen=True)
class GapRecord:
    """Represents a skill gap record with company scope."""

    id: int
    user_id: int
    company_id: int
    document_id: int
    gap_type: str
    priority: str


@dataclass(frozen=True)
class MaterialRecord:
    """Represents a training material record with company scope."""

    id: int
    document_id: int
    company_id: int
    material_type: str
    status: str


@dataclass(frozen=True)
class QuestionRecord:
    """Represents a generated question record with company scope."""

    id: int
    document_id: int
    company_id: int
    question_type: str
    difficulty_level: str


@dataclass(frozen=True)
class SessionRecord:
    """Represents a virtual audit session record with company scope."""

    id: int
    user_id: int
    document_id: int
    company_id: int
    status: str
    overall_score: float | None


# ---------------------------------------------------------------------------
# Filtering function (simulates WHERE company_id = X)
# ---------------------------------------------------------------------------


def filter_by_company(records: list[Any], company_id: int) -> list[Any]:
    """Filter records by company_id, simulating tenant-scoped queries.

    This replicates the WHERE company_id = :company_id clause that all
    training ecosystem listing endpoints apply.

    Args:
        records: List of records with a company_id attribute.
        company_id: The company to filter for.

    Returns:
        List of records belonging to the specified company.
    """
    return [r for r in records if r.company_id == company_id]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


COMPANY_IDS = st.integers(min_value=1, max_value=10)
USER_IDS = st.integers(min_value=1, max_value=50)
DOCUMENT_IDS = st.integers(min_value=1, max_value=100)
GAP_TYPES = st.sampled_from(["missing_training", "expired_training", "new_version_available"])
PRIORITIES = st.sampled_from(["Critical", "High", "Medium", "Low"])
MATERIAL_TYPES = st.sampled_from([
    "executive_summary", "detailed_walkthrough", "key_takeaways",
    "presentation_outline", "safety_highlights",
])
CONTENT_STATUSES = st.sampled_from(["pending_review", "approved", "rejected", "draft"])
QUESTION_TYPES = st.sampled_from(["multiple_choice", "true_false", "scenario_based", "fill_in_blank"])
DIFFICULTY_LEVELS = st.sampled_from(["basic", "intermediate", "advanced"])
SESSION_STATUSES = st.sampled_from(["in_progress", "completed", "abandoned"])


@st.composite
def st_schedule_records(draw: st.DrawFn) -> list[ScheduleRecord]:
    """Generate a list of training schedule records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=20))
    records = []
    for i in range(num_records):
        total = draw(st.integers(min_value=0, max_value=50))
        records.append(ScheduleRecord(
            id=i + 1,
            user_id=draw(USER_IDS),
            company_id=draw(COMPANY_IDS),
            compliance_percentage=draw(st.floats(min_value=0.0, max_value=100.0)),
            total_items=total,
        ))
    return records


@st.composite
def st_gap_records(draw: st.DrawFn) -> list[GapRecord]:
    """Generate a list of skill gap records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=30))
    records = []
    for i in range(num_records):
        records.append(GapRecord(
            id=i + 1,
            user_id=draw(USER_IDS),
            company_id=draw(COMPANY_IDS),
            document_id=draw(DOCUMENT_IDS),
            gap_type=draw(GAP_TYPES),
            priority=draw(PRIORITIES),
        ))
    return records


@st.composite
def st_material_records(draw: st.DrawFn) -> list[MaterialRecord]:
    """Generate a list of training material records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=25))
    records = []
    for i in range(num_records):
        records.append(MaterialRecord(
            id=i + 1,
            document_id=draw(DOCUMENT_IDS),
            company_id=draw(COMPANY_IDS),
            material_type=draw(MATERIAL_TYPES),
            status=draw(CONTENT_STATUSES),
        ))
    return records


@st.composite
def st_question_records(draw: st.DrawFn) -> list[QuestionRecord]:
    """Generate a list of generated question records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=30))
    records = []
    for i in range(num_records):
        records.append(QuestionRecord(
            id=i + 1,
            document_id=draw(DOCUMENT_IDS),
            company_id=draw(COMPANY_IDS),
            question_type=draw(QUESTION_TYPES),
            difficulty_level=draw(DIFFICULTY_LEVELS),
        ))
    return records


@st.composite
def st_session_records(draw: st.DrawFn) -> list[SessionRecord]:
    """Generate a list of virtual audit session records across multiple companies."""
    num_records = draw(st.integers(min_value=1, max_value=20))
    records = []
    for i in range(num_records):
        records.append(SessionRecord(
            id=i + 1,
            user_id=draw(USER_IDS),
            document_id=draw(DOCUMENT_IDS),
            company_id=draw(COMPANY_IDS),
            status=draw(SESSION_STATUSES),
            overall_score=draw(st.one_of(
                st.none(),
                st.floats(min_value=0.0, max_value=1.0),
            )),
        ))
    return records


# ---------------------------------------------------------------------------
# Property 4: Company-scoped tenant isolation
# ---------------------------------------------------------------------------


@settings(max_examples=100)
@given(
    records=st_schedule_records(),
    target_company=COMPANY_IDS,
)
def test_schedule_listing_returns_only_target_company(
    records: list[ScheduleRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to training schedules, the filtered
    results SHALL contain only records where company_id matches the filter.

    **Validates: Requirements 1.8**
    """
    filtered = filter_by_company(records, target_company)

    # All returned records belong to the target company
    for record in filtered:
        assert record.company_id == target_company, (
            f"Schedule {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    # Count matches expected
    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count, (
        f"Expected {expected_count} schedules for company {target_company}, "
        f"got {len(filtered)}"
    )


@settings(max_examples=100)
@given(
    records=st_gap_records(),
    target_company=COMPANY_IDS,
)
def test_gap_listing_returns_only_target_company(
    records: list[GapRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to skill gaps, the filtered
    results SHALL contain only records where company_id matches the filter.

    **Validates: Requirements 2.6**
    """
    filtered = filter_by_company(records, target_company)

    for record in filtered:
        assert record.company_id == target_company, (
            f"Gap {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count


@settings(max_examples=100)
@given(
    records=st_material_records(),
    target_company=COMPANY_IDS,
)
def test_material_listing_returns_only_target_company(
    records: list[MaterialRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to training materials, the filtered
    results SHALL contain only records where company_id matches the filter.

    **Validates: Requirements 3.10**
    """
    filtered = filter_by_company(records, target_company)

    for record in filtered:
        assert record.company_id == target_company, (
            f"Material {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count


@settings(max_examples=100)
@given(
    records=st_question_records(),
    target_company=COMPANY_IDS,
)
def test_question_listing_returns_only_target_company(
    records: list[QuestionRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to generated questions, the filtered
    results SHALL contain only records where company_id matches the filter.

    **Validates: Requirements 9.15**
    """
    filtered = filter_by_company(records, target_company)

    for record in filtered:
        assert record.company_id == target_company, (
            f"Question {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count


@settings(max_examples=100)
@given(
    records=st_session_records(),
    target_company=COMPANY_IDS,
)
def test_session_listing_returns_only_target_company(
    records: list[SessionRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied to virtual audit sessions, the filtered
    results SHALL contain only records where company_id matches the filter.

    **Validates: Requirements 6.12**
    """
    filtered = filter_by_company(records, target_company)

    for record in filtered:
        assert record.company_id == target_company, (
            f"Session {record.id} has company_id={record.company_id}, "
            f"expected {target_company}"
        )

    expected_count = sum(1 for r in records if r.company_id == target_company)
    assert len(filtered) == expected_count


@settings(max_examples=100)
@given(
    schedules=st_schedule_records(),
    gaps=st_gap_records(),
    materials=st_material_records(),
    questions=st_question_records(),
    sessions=st_session_records(),
    target_company=COMPANY_IDS,
)
def test_combined_multi_resource_tenant_isolation(
    schedules: list[ScheduleRecord],
    gaps: list[GapRecord],
    materials: list[MaterialRecord],
    questions: list[QuestionRecord],
    sessions: list[SessionRecord],
    target_company: int,
) -> None:
    """For any company_id filter applied across ALL training ecosystem resource
    types simultaneously, each filtered result set SHALL contain only records
    belonging to the target company, and no records from other companies leak
    into any result set.

    **Validates: Requirements 1.8, 2.6, 3.10, 6.12, 7.8, 9.15**
    """
    filtered_schedules = filter_by_company(schedules, target_company)
    filtered_gaps = filter_by_company(gaps, target_company)
    filtered_materials = filter_by_company(materials, target_company)
    filtered_questions = filter_by_company(questions, target_company)
    filtered_sessions = filter_by_company(sessions, target_company)

    # Verify isolation for each resource type
    for s in filtered_schedules:
        assert s.company_id == target_company
    for g in filtered_gaps:
        assert g.company_id == target_company
    for m in filtered_materials:
        assert m.company_id == target_company
    for q in filtered_questions:
        assert q.company_id == target_company
    for sess in filtered_sessions:
        assert sess.company_id == target_company

    # Verify completeness: no records for target company are missing
    assert len(filtered_schedules) == sum(
        1 for r in schedules if r.company_id == target_company
    )
    assert len(filtered_gaps) == sum(
        1 for r in gaps if r.company_id == target_company
    )
    assert len(filtered_materials) == sum(
        1 for r in materials if r.company_id == target_company
    )
    assert len(filtered_questions) == sum(
        1 for r in questions if r.company_id == target_company
    )
    assert len(filtered_sessions) == sum(
        1 for r in sessions if r.company_id == target_company
    )

    # Verify no cross-company leakage: filtered results are a strict subset
    other_companies = {
        r.company_id
        for r in schedules + gaps + materials + questions + sessions
        if r.company_id != target_company
    }
    all_filtered = (
        filtered_schedules + filtered_gaps + filtered_materials
        + filtered_questions + filtered_sessions
    )
    for record in all_filtered:
        assert record.company_id not in other_companies or record.company_id == target_company
