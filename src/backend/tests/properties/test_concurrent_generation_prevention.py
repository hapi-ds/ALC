"""Property-based tests for concurrent generation prevention.

Tests Property 14 from the AI Document Generator (Template-Based) design document,
validating that for any set of generation requests with the same
(template_id, title, company_id), at most one can be in "processing" status
at any time. Concurrent requests for the same combination are rejected.

**Validates: Requirements 7.6**

References:
    - Design: .kiro/specs/Step_5-4_ai-document-generator-template-based/design.md (Property 14)
    - Requirements: .kiro/specs/Step_5-4_ai-document-generator-template-based/requirements.md (7.6)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import hypothesis.strategies as st
import pytest
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure-logic model of the concurrent generation prevention system
# ---------------------------------------------------------------------------


@dataclass
class GenerationRequest:
    """A generation request targeting a specific (template_id, title, company_id).

    Attributes:
        request_id: Unique identifier for this request.
        template_id: ID of the template to generate from.
        title: Title of the document to generate.
        company_id: Company scope for tenant isolation.
    """

    request_id: str
    template_id: int
    title: str
    company_id: int


@dataclass
class JobRecord:
    """A generation job record tracking status.

    Attributes:
        job_id: Unique job identifier.
        template_id: Template used for generation.
        title: Document title.
        company_id: Company scope.
        status: Job status ("processing", "completed", "failed").
    """

    job_id: str
    template_id: int
    title: str
    company_id: int
    status: str = "processing"


@dataclass
class ConcurrencyGuard:
    """Models the concurrent generation prevention logic.

    Maintains a registry of active jobs and enforces the invariant that
    at most one job with status "processing" can exist for any given
    (template_id, title, company_id) combination.

    This mirrors the logic in TemplateDocumentGeneratorService.request_generation()
    which queries GenerationJobMetadata for existing processing jobs before
    accepting a new request.
    """

    jobs: list[JobRecord] = field(default_factory=list)

    def request_generation(self, request: GenerationRequest) -> tuple[bool, str]:
        """Attempt to start a generation job.

        Checks if a concurrent job already exists for the same
        (template_id, title, company_id) with status "processing".
        If so, rejects the request. Otherwise, creates a new job.

        Args:
            request: The generation request to process.

        Returns:
            Tuple of (accepted: bool, job_id_or_error: str).
            If accepted, returns (True, new_job_id).
            If rejected, returns (False, existing_job_id).
        """
        # Check for concurrent processing job with same combination
        for job in self.jobs:
            if (
                job.template_id == request.template_id
                and job.title == request.title
                and job.company_id == request.company_id
                and job.status == "processing"
            ):
                return (False, job.job_id)

        # No concurrent job found — accept the request
        new_job_id = str(uuid.uuid4())
        new_job = JobRecord(
            job_id=new_job_id,
            template_id=request.template_id,
            title=request.title,
            company_id=request.company_id,
            status="processing",
        )
        self.jobs.append(new_job)
        return (True, new_job_id)

    def complete_job(self, job_id: str) -> None:
        """Mark a job as completed."""
        for job in self.jobs:
            if job.job_id == job_id:
                job.status = "completed"
                return

    def fail_job(self, job_id: str) -> None:
        """Mark a job as failed."""
        for job in self.jobs:
            if job.job_id == job_id:
                job.status = "failed"
                return

    def get_processing_jobs_for_combination(
        self, template_id: int, title: str, company_id: int
    ) -> list[JobRecord]:
        """Get all processing jobs for a given combination."""
        return [
            job
            for job in self.jobs
            if job.template_id == template_id
            and job.title == title
            and job.company_id == company_id
            and job.status == "processing"
        ]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------


@st.composite
def st_generation_request(draw: st.DrawFn) -> GenerationRequest:
    """Generate a random generation request.

    Uses small integer ranges for template_id and company_id to increase
    collision probability, making the concurrency invariant more likely
    to be exercised.
    """
    return GenerationRequest(
        request_id=draw(st.uuids().map(str)),
        template_id=draw(st.integers(min_value=1, max_value=5)),
        title=draw(st.sampled_from(["URS Document", "SOP Manual", "MVP Plan"])),
        company_id=draw(st.integers(min_value=1, max_value=3)),
    )


@st.composite
def st_request_batch_same_combination(draw: st.DrawFn) -> list[GenerationRequest]:
    """Generate a batch of requests all targeting the same combination.

    This ensures we test the scenario where multiple requests compete
    for the same (template_id, title, company_id) slot.
    """
    template_id = draw(st.integers(min_value=1, max_value=100))
    title = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N", "Z"),
    )))
    company_id = draw(st.integers(min_value=1, max_value=100))
    count = draw(st.integers(min_value=2, max_value=10))

    return [
        GenerationRequest(
            request_id=str(uuid.uuid4()),
            template_id=template_id,
            title=title,
            company_id=company_id,
        )
        for _ in range(count)
    ]


@st.composite
def st_mixed_request_sequence(draw: st.DrawFn) -> list[dict[str, Any]]:
    """Generate a sequence of interleaved request and completion events.

    Events are either:
    - {"type": "request", "request": GenerationRequest}
    - {"type": "complete", "index": int}  (complete the Nth accepted job)
    - {"type": "fail", "index": int}  (fail the Nth accepted job)

    This models realistic scenarios where jobs start and finish over time.
    """
    # Use small domain to increase collisions
    template_ids = draw(st.lists(st.integers(min_value=1, max_value=3), min_size=1, max_size=3))
    titles = draw(st.lists(
        st.sampled_from(["URS Doc", "SOP Manual", "MVP Plan", "Protocol"]),
        min_size=1,
        max_size=3,
    ))
    company_ids = draw(st.lists(st.integers(min_value=1, max_value=2), min_size=1, max_size=2))

    num_events = draw(st.integers(min_value=3, max_value=20))
    events: list[dict[str, Any]] = []
    accepted_count = 0

    for _ in range(num_events):
        event_type = draw(st.sampled_from(["request", "request", "complete", "fail"]))

        if event_type == "request":
            request = GenerationRequest(
                request_id=str(uuid.uuid4()),
                template_id=draw(st.sampled_from(template_ids)),
                title=draw(st.sampled_from(titles)),
                company_id=draw(st.sampled_from(company_ids)),
            )
            events.append({"type": "request", "request": request})
        elif accepted_count > 0:
            # Complete or fail a random previously accepted job
            index = draw(st.integers(min_value=0, max_value=accepted_count - 1))
            events.append({"type": event_type, "index": index})

        # Track how many jobs have been accepted so far (approximate)
        if event_type == "request":
            accepted_count += 1  # Optimistic; actual acceptance depends on guard

    return events


# ---------------------------------------------------------------------------
# Property 14: Concurrent Generation Prevention
# ---------------------------------------------------------------------------


@settings(max_examples=25)
@given(requests=st_request_batch_same_combination())
def test_at_most_one_processing_for_same_combination(
    requests: list[GenerationRequest],
) -> None:
    """For any set of generation requests with the same (template_id, title,
    company_id), at most one can be in "processing" status at any time.
    All subsequent requests are rejected with the existing job_id.

    **Validates: Requirements 7.6**
    """
    guard = ConcurrencyGuard()

    accepted_job_ids: list[str] = []
    rejected_count = 0

    for request in requests:
        accepted, job_id_or_error = guard.request_generation(request)
        if accepted:
            accepted_job_ids.append(job_id_or_error)
        else:
            rejected_count += 1

    # Invariant: exactly one request should be accepted
    assert len(accepted_job_ids) == 1, (
        f"Expected exactly 1 accepted job, got {len(accepted_job_ids)} "
        f"for {len(requests)} requests with same combination"
    )

    # Invariant: all other requests should be rejected
    assert rejected_count == len(requests) - 1, (
        f"Expected {len(requests) - 1} rejections, got {rejected_count}"
    )

    # Invariant: at most one processing job exists for the combination
    template_id = requests[0].template_id
    title = requests[0].title
    company_id = requests[0].company_id
    processing_jobs = guard.get_processing_jobs_for_combination(
        template_id, title, company_id
    )
    assert len(processing_jobs) <= 1, (
        f"Found {len(processing_jobs)} processing jobs for same combination — "
        f"concurrent generation prevention violated"
    )


@settings(max_examples=25)
@given(requests=st_request_batch_same_combination())
def test_rejected_request_returns_existing_job_id(
    requests: list[GenerationRequest],
) -> None:
    """When a concurrent request is rejected, the rejection SHALL include
    the job_id of the existing processing job.

    **Validates: Requirements 7.6**
    """
    guard = ConcurrencyGuard()

    first_accepted, first_job_id = guard.request_generation(requests[0])
    assert first_accepted is True, "First request should always be accepted"

    # All subsequent requests should be rejected with the first job's ID
    for request in requests[1:]:
        accepted, returned_id = guard.request_generation(request)
        assert accepted is False, "Concurrent request should be rejected"
        assert returned_id == first_job_id, (
            f"Rejected request should return existing job_id '{first_job_id}', "
            f"got '{returned_id}'"
        )


@settings(max_examples=25)
@given(events=st_mixed_request_sequence())
def test_invariant_holds_across_interleaved_events(
    events: list[dict[str, Any]],
) -> None:
    """Across any interleaved sequence of request/complete/fail events,
    the invariant holds: at most one processing job per
    (template_id, title, company_id) combination at any point in time.

    **Validates: Requirements 7.6**
    """
    guard = ConcurrencyGuard()
    accepted_jobs: list[str] = []  # Track accepted job_ids in order

    for event in events:
        if event["type"] == "request":
            request = event["request"]
            accepted, job_id_or_error = guard.request_generation(request)
            if accepted:
                accepted_jobs.append(job_id_or_error)
        elif event["type"] == "complete":
            index = event["index"]
            if index < len(accepted_jobs):
                guard.complete_job(accepted_jobs[index])
        elif event["type"] == "fail":
            index = event["index"]
            if index < len(accepted_jobs):
                guard.fail_job(accepted_jobs[index])

        # After every event, verify the invariant holds
        # Group all processing jobs by (template_id, title, company_id)
        processing_by_combo: dict[tuple[int, str, int], list[str]] = {}
        for job in guard.jobs:
            if job.status == "processing":
                key = (job.template_id, job.title, job.company_id)
                processing_by_combo.setdefault(key, []).append(job.job_id)

        for combo, job_ids in processing_by_combo.items():
            assert len(job_ids) <= 1, (
                f"Invariant violated: {len(job_ids)} processing jobs for "
                f"combination {combo}: {job_ids}"
            )


@settings(max_examples=25)
@given(requests=st_request_batch_same_combination())
def test_completed_job_allows_new_request(
    requests: list[GenerationRequest],
) -> None:
    """After a processing job completes, a new request for the same
    (template_id, title, company_id) SHALL be accepted.

    **Validates: Requirements 7.6**
    """
    guard = ConcurrencyGuard()

    # First request is accepted
    accepted, first_job_id = guard.request_generation(requests[0])
    assert accepted is True

    # Second request is rejected while first is processing
    if len(requests) > 1:
        accepted, _ = guard.request_generation(requests[1])
        assert accepted is False

    # Complete the first job
    guard.complete_job(first_job_id)

    # Now a new request for the same combination should be accepted
    new_request = GenerationRequest(
        request_id=str(uuid.uuid4()),
        template_id=requests[0].template_id,
        title=requests[0].title,
        company_id=requests[0].company_id,
    )
    accepted, new_job_id = guard.request_generation(new_request)
    assert accepted is True, (
        "Request should be accepted after previous job completed"
    )
    assert new_job_id != first_job_id, (
        "New job should have a different job_id"
    )


@settings(max_examples=25)
@given(requests=st_request_batch_same_combination())
def test_failed_job_allows_new_request(
    requests: list[GenerationRequest],
) -> None:
    """After a processing job fails, a new request for the same
    (template_id, title, company_id) SHALL be accepted.

    **Validates: Requirements 7.6**
    """
    guard = ConcurrencyGuard()

    # First request is accepted
    accepted, first_job_id = guard.request_generation(requests[0])
    assert accepted is True

    # Fail the first job
    guard.fail_job(first_job_id)

    # Now a new request for the same combination should be accepted
    new_request = GenerationRequest(
        request_id=str(uuid.uuid4()),
        template_id=requests[0].template_id,
        title=requests[0].title,
        company_id=requests[0].company_id,
    )
    accepted, new_job_id = guard.request_generation(new_request)
    assert accepted is True, (
        "Request should be accepted after previous job failed"
    )


@settings(max_examples=25)
@given(requests=st.lists(st_generation_request(), min_size=2, max_size=15))
def test_different_combinations_are_independent(
    requests: list[GenerationRequest],
) -> None:
    """Requests with different (template_id, title, company_id) combinations
    SHALL NOT interfere with each other. Each combination has its own
    concurrency slot.

    **Validates: Requirements 7.6**
    """
    guard = ConcurrencyGuard()

    # Track accepted jobs per combination
    accepted_per_combo: dict[tuple[int, str, int], list[str]] = {}

    for request in requests:
        accepted, job_id_or_error = guard.request_generation(request)
        combo = (request.template_id, request.title, request.company_id)

        if accepted:
            accepted_per_combo.setdefault(combo, []).append(job_id_or_error)

    # Verify: each combination has at most 1 processing job
    for combo, job_ids in accepted_per_combo.items():
        processing_jobs = guard.get_processing_jobs_for_combination(
            combo[0], combo[1], combo[2]
        )
        assert len(processing_jobs) <= 1, (
            f"Combination {combo} has {len(processing_jobs)} processing jobs"
        )

    # Verify: different combinations can each have their own processing job
    # (i.e., the guard doesn't over-restrict)
    unique_combos_in_requests = {
        (r.template_id, r.title, r.company_id) for r in requests
    }
    # Each unique combination should have exactly 1 accepted job
    for combo in unique_combos_in_requests:
        processing = guard.get_processing_jobs_for_combination(
            combo[0], combo[1], combo[2]
        )
        assert len(processing) == 1, (
            f"Combination {combo} should have exactly 1 processing job, "
            f"got {len(processing)}"
        )
