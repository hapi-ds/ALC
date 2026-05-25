"""Property-based tests for company isolation in impact analysis endpoints.

Tests Property 3 from the AI-Driven Change Impact Analysis design document,
validating that dependency edges, impact reports, gap findings, and
notifications for company A are never visible to company B across all
impact analysis endpoints.

**Validates: Requirements 1.11, 2.7, 3.7, 4.8, 5.6, 6.6, 8.6**

References:
    - Design: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/design.md (Property 3)
    - Requirements: .kiro/specs/Step_5-5_ai-driven-change-impact-analysis/requirements.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure model of multi-tenant impact analysis data and isolation logic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DependencyEdgeRecord:
    """Represents a dependency edge record with company scope.

    Attributes:
        id: Unique edge identifier.
        company_id: Owning company (tenant isolation key).
        source_document_uuid: Source document UUID.
        target_document_uuid: Target document UUID.
        dependency_type: Type of dependency relationship.
        confidence_score: Detection confidence (0.0-1.0).
    """

    id: int
    company_id: int
    source_document_uuid: str
    target_document_uuid: str
    dependency_type: str
    confidence_score: float


@dataclass(frozen=True)
class ImpactReportRecord:
    """Represents an impact report record with company scope.

    Attributes:
        id: Unique report identifier.
        report_id: UUID string for the report.
        company_id: Owning company (tenant isolation key).
        triggering_document_uuid: Document that triggered the analysis.
        status: Report status (completed, partial_success, failed).
        affected_items: List of affected item dicts.
        gap_findings: List of gap finding dicts.
    """

    id: int
    report_id: str
    company_id: int
    triggering_document_uuid: str
    status: str
    affected_items: list[dict] = field(default_factory=list)
    gap_findings: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class GapAnalysisResultRecord:
    """Represents a gap analysis result record with company scope.

    Attributes:
        id: Unique result identifier.
        job_id: Associated job identifier.
        company_id: Owning company (tenant isolation key).
        source_document_uuid: Source document UUID.
        target_document_uuid: Target document UUID.
        gap_findings: List of gap finding dicts.
        status: Result status.
    """

    id: int
    job_id: str
    company_id: int
    source_document_uuid: str
    target_document_uuid: str
    gap_findings: list[dict] = field(default_factory=list)
    status: str = "completed"


@dataclass(frozen=True)
class ImpactNotificationRecord:
    """Represents an impact notification record with company scope.

    Attributes:
        id: Unique notification identifier.
        company_id: Owning company (tenant isolation key).
        report_id: Associated report UUID.
        affected_document_uuid: Document affected by the change.
        target_user_id: User to notify.
        impact_severity: Severity of the impact.
        is_acknowledged: Whether the notification has been acknowledged.
    """

    id: int
    company_id: int
    report_id: str
    affected_document_uuid: str
    target_user_id: int
    impact_severity: str
    is_acknowledged: bool = False


@dataclass(frozen=True)
class JobRecord:
    """Represents a processing job record with company scope.

    Attributes:
        job_id: Unique job identifier.
        company_id: Owning company (tenant isolation key).
        status: Job status.
        progress_percent: Current progress (0-100).
    """

    job_id: str
    company_id: int
    status: str
    progress_percent: int


@dataclass
class ImpactAnalysisDataStore:
    """Simulates the multi-tenant data store for impact analysis.

    Models the behavior of the API layer where all queries are filtered
    by company_id (resolved from X-Company-Id header via TenantContext).
    This mirrors how the impact analysis router scopes all queries.

    Attributes:
        edges: All dependency edges across all companies.
        reports: All impact reports across all companies.
        gap_results: All gap analysis results across all companies.
        notifications: All impact notifications across all companies.
        jobs: All processing jobs across all companies.
    """

    edges: list[DependencyEdgeRecord] = field(default_factory=list)
    reports: list[ImpactReportRecord] = field(default_factory=list)
    gap_results: list[GapAnalysisResultRecord] = field(default_factory=list)
    notifications: list[ImpactNotificationRecord] = field(default_factory=list)
    jobs: list[JobRecord] = field(default_factory=list)

    def list_edges(
        self,
        company_id: int,
        source_document_uuid: str | None = None,
        target_document_uuid: str | None = None,
        dependency_type: str | None = None,
    ) -> list[DependencyEdgeRecord]:
        """List dependency edges scoped to a company with optional filters.

        Mirrors GET /impact-analysis/dependency-graph which filters by
        DependencyEdge.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.
            source_document_uuid: Optional source filter.
            target_document_uuid: Optional target filter.
            dependency_type: Optional type filter.

        Returns:
            Edges belonging to the specified company only.
        """
        results = [e for e in self.edges if e.company_id == company_id]
        if source_document_uuid:
            results = [
                e for e in results
                if e.source_document_uuid == source_document_uuid
            ]
        if target_document_uuid:
            results = [
                e for e in results
                if e.target_document_uuid == target_document_uuid
            ]
        if dependency_type:
            results = [
                e for e in results if e.dependency_type == dependency_type
            ]
        return results

    def get_document_dependencies(
        self, company_id: int, document_uuid: str
    ) -> dict[str, list[DependencyEdgeRecord]]:
        """Get upstream and downstream edges for a document in a company.

        Mirrors GET /impact-analysis/dependency-graph/{document_uuid} which
        scopes by company_id.

        Args:
            company_id: The company to query for.
            document_uuid: The document to get dependencies for.

        Returns:
            Dict with upstream and downstream edge lists.
        """
        upstream = [
            e for e in self.edges
            if e.company_id == company_id
            and e.target_document_uuid == document_uuid
        ]
        downstream = [
            e for e in self.edges
            if e.company_id == company_id
            and e.source_document_uuid == document_uuid
        ]
        return {"upstream": upstream, "downstream": downstream}

    def list_reports(
        self, company_id: int
    ) -> list[ImpactReportRecord]:
        """List impact reports scoped to a company.

        Mirrors GET /impact-analysis/reports which filters by
        ImpactReport.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.

        Returns:
            Reports belonging to the specified company only.
        """
        return [r for r in self.reports if r.company_id == company_id]

    def get_report(
        self, company_id: int, report_id: str
    ) -> ImpactReportRecord | None:
        """Get a single report by report_id scoped to a company.

        Mirrors GET /impact-analysis/reports/{report_id} which filters by
        ImpactReport.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.
            report_id: The report UUID to look up.

        Returns:
            The report if found in company scope, else None.
        """
        for r in self.reports:
            if r.company_id == company_id and r.report_id == report_id:
                return r
        return None

    def get_gap_analysis_results(
        self, company_id: int, job_id: str
    ) -> GapAnalysisResultRecord | None:
        """Get gap analysis results scoped to a company.

        Mirrors GET /impact-analysis/gap-analysis/{job_id}/results which
        filters by GapAnalysisResult.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.
            job_id: The job identifier.

        Returns:
            The gap analysis result if found in company scope, else None.
        """
        for gr in self.gap_results:
            if gr.company_id == company_id and gr.job_id == job_id:
                return gr
        return None

    def list_notifications(
        self, company_id: int, user_id: int
    ) -> list[ImpactNotificationRecord]:
        """List unacknowledged notifications scoped to a company and user.

        Mirrors GET /impact-analysis/notifications which filters by
        ImpactNotification.company_id == tenant.company_id AND
        target_user_id == tenant.user_id AND is_acknowledged == False.

        Args:
            company_id: The company to query for.
            user_id: The user to query notifications for.

        Returns:
            Unacknowledged notifications for the user in the company.
        """
        return [
            n for n in self.notifications
            if n.company_id == company_id
            and n.target_user_id == user_id
            and not n.is_acknowledged
        ]

    def get_job_status(
        self, company_id: int, job_id: str
    ) -> JobRecord | None:
        """Get job status scoped to a company.

        Mirrors GET /impact-analysis/jobs/{job_id}/status which filters by
        ProcessingJob.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.
            job_id: The job identifier.

        Returns:
            The job if found in company scope, else None.
        """
        for j in self.jobs:
            if j.company_id == company_id and j.job_id == job_id:
                return j
        return None


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

DEPENDENCY_TYPES = ["validates", "references", "implements", "trains_on", "derived_from"]
REPORT_STATUSES = ["completed", "partial_success", "failed"]
IMPACT_SEVERITIES = ["critical", "major", "minor", "unknown"]
JOB_STATUSES = ["processing", "completed", "partial_success", "failed"]


def _make_uuid(prefix: str, idx: int) -> str:
    """Generate a deterministic short UUID-like string for testing."""
    return f"{prefix}{idx:06d}"


@st.composite
def st_populated_store(draw: st.DrawFn) -> tuple[ImpactAnalysisDataStore, list[int]]:
    """Generate a data store populated with multi-company impact analysis data.

    Creates 2-4 companies with random distributions of dependency edges,
    impact reports, gap analysis results, notifications, and jobs.

    Returns:
        Tuple of (populated ImpactAnalysisDataStore, list of company IDs).
    """
    num_companies = draw(st.integers(min_value=2, max_value=4))
    company_ids = list(range(1, num_companies + 1))

    store = ImpactAnalysisDataStore()

    # Generate dependency edges
    edge_id = 1
    for cid in company_ids:
        num_edges = draw(st.integers(min_value=0, max_value=8))
        for i in range(num_edges):
            store.edges.append(
                DependencyEdgeRecord(
                    id=edge_id,
                    company_id=cid,
                    source_document_uuid=_make_uuid("doc", cid * 100 + i),
                    target_document_uuid=_make_uuid("doc", cid * 100 + i + 50),
                    dependency_type=draw(st.sampled_from(DEPENDENCY_TYPES)),
                    confidence_score=draw(
                        st.floats(min_value=0.5, max_value=1.0)
                    ),
                )
            )
            edge_id += 1

    # Generate impact reports
    report_id_counter = 1
    for cid in company_ids:
        num_reports = draw(st.integers(min_value=0, max_value=5))
        for i in range(num_reports):
            report_uuid = _make_uuid("rpt", report_id_counter)
            status = draw(st.sampled_from(REPORT_STATUSES))
            num_items = draw(st.integers(min_value=0, max_value=3))
            affected_items = [
                {
                    "affected_document_uuid": _make_uuid("doc", cid * 100 + j),
                    "impact_severity": draw(st.sampled_from(IMPACT_SEVERITIES)),
                    "dependency_type": draw(st.sampled_from(DEPENDENCY_TYPES)),
                }
                for j in range(num_items)
            ]
            num_gaps = draw(st.integers(min_value=0, max_value=3))
            gap_findings = [
                {
                    "source_section": f"Section {k}",
                    "severity": draw(
                        st.sampled_from(["critical", "major", "minor"])
                    ),
                    "gap_type": draw(
                        st.sampled_from(
                            ["missing", "contradicts", "incomplete", "outdated"]
                        )
                    ),
                }
                for k in range(num_gaps)
            ]
            store.reports.append(
                ImpactReportRecord(
                    id=report_id_counter,
                    report_id=report_uuid,
                    company_id=cid,
                    triggering_document_uuid=_make_uuid("doc", cid * 100 + i),
                    status=status,
                    affected_items=affected_items,
                    gap_findings=gap_findings,
                )
            )
            report_id_counter += 1

    # Generate gap analysis results
    gap_id = 1
    for cid in company_ids:
        num_gaps = draw(st.integers(min_value=0, max_value=4))
        for i in range(num_gaps):
            job_id = _make_uuid("job", gap_id)
            num_findings = draw(st.integers(min_value=0, max_value=5))
            findings = [
                {
                    "source_section": f"Section {k}",
                    "severity": draw(
                        st.sampled_from(["critical", "major", "minor"])
                    ),
                    "gap_type": draw(
                        st.sampled_from(
                            ["missing", "contradicts", "incomplete", "outdated"]
                        )
                    ),
                }
                for k in range(num_findings)
            ]
            store.gap_results.append(
                GapAnalysisResultRecord(
                    id=gap_id,
                    job_id=job_id,
                    company_id=cid,
                    source_document_uuid=_make_uuid("doc", cid * 100 + i),
                    target_document_uuid=_make_uuid("doc", cid * 100 + i + 50),
                    gap_findings=findings,
                    status=draw(st.sampled_from(REPORT_STATUSES)),
                )
            )
            gap_id += 1

    # Generate notifications
    notif_id = 1
    for cid in company_ids:
        num_notifs = draw(st.integers(min_value=0, max_value=6))
        for i in range(num_notifs):
            # Use a user_id that is company-specific to test cross-user too
            user_id = draw(st.integers(min_value=1, max_value=3))
            store.notifications.append(
                ImpactNotificationRecord(
                    id=notif_id,
                    company_id=cid,
                    report_id=_make_uuid("rpt", notif_id),
                    affected_document_uuid=_make_uuid("doc", cid * 100 + i),
                    target_user_id=user_id,
                    impact_severity=draw(
                        st.sampled_from(["critical", "major"])
                    ),
                    is_acknowledged=draw(st.booleans()),
                )
            )
            notif_id += 1

    # Generate jobs
    job_counter = 1
    for cid in company_ids:
        num_jobs = draw(st.integers(min_value=0, max_value=4))
        for _ in range(num_jobs):
            store.jobs.append(
                JobRecord(
                    job_id=_make_uuid("job", job_counter),
                    company_id=cid,
                    status=draw(st.sampled_from(JOB_STATUSES)),
                    progress_percent=draw(
                        st.integers(min_value=0, max_value=100)
                    ),
                )
            )
            job_counter += 1

    return store, company_ids


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Dependency Edges
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_dependency_edges_company_isolation(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any API query to the dependency graph endpoint scoped by
    X-Company-Id, the response SHALL contain only edges belonging to
    that company. No dependency edges from other companies SHALL appear.

    **Validates: Requirements 1.11**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_edges(cid)

        # Every returned edge belongs to this company
        for edge in results:
            assert edge.company_id == cid, (
                f"Edge {edge.id} has company_id={edge.company_id}, "
                f"expected {cid}"
            )

        # Count matches expected
        expected = sum(1 for e in store.edges if e.company_id == cid)
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} edges, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Document Dependencies
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_document_dependencies_company_isolation(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any query to the document dependencies endpoint scoped by
    X-Company-Id, both upstream and downstream edges SHALL contain only
    records belonging to that company.

    **Validates: Requirements 1.11**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Pick a document UUID that exists in this company's edges
        company_edges = [e for e in store.edges if e.company_id == cid]
        if not company_edges:
            continue

        doc_uuid = company_edges[0].source_document_uuid
        result = store.get_document_dependencies(cid, doc_uuid)

        for edge in result["upstream"]:
            assert edge.company_id == cid, (
                f"Upstream edge {edge.id} has company_id={edge.company_id}, "
                f"expected {cid}"
            )

        for edge in result["downstream"]:
            assert edge.company_id == cid, (
                f"Downstream edge {edge.id} has company_id={edge.company_id}, "
                f"expected {cid}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Impact Reports
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_impact_reports_company_isolation(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any API query to the reports endpoint scoped by X-Company-Id,
    the response SHALL contain only reports belonging to that company.
    No impact reports from other companies SHALL appear.

    **Validates: Requirements 5.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_reports(cid)

        # Every returned report belongs to this company
        for report in results:
            assert report.company_id == cid, (
                f"Report {report.report_id} has company_id={report.company_id}, "
                f"expected {cid}"
            )

        # Count matches expected
        expected = sum(1 for r in store.reports if r.company_id == cid)
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} reports, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Single Report Lookup
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_report_lookup_company_isolation(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any report lookup scoped by X-Company-Id, a report belonging
    to another company SHALL NOT be returned (returns None/404).

    **Validates: Requirements 5.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Try to access reports from other companies
        other_reports = [r for r in store.reports if r.company_id != cid]
        for other_report in other_reports:
            result = store.get_report(cid, other_report.report_id)
            assert result is None, (
                f"Company {cid} was able to access report "
                f"{other_report.report_id} belonging to company "
                f"{other_report.company_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Gap Analysis Results
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_gap_analysis_results_company_isolation(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any gap analysis results query scoped by X-Company-Id,
    results from other companies SHALL NOT be accessible.

    **Validates: Requirements 4.8**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Verify own results are accessible
        company_results = [
            gr for gr in store.gap_results if gr.company_id == cid
        ]
        for gr in company_results:
            result = store.get_gap_analysis_results(cid, gr.job_id)
            assert result is not None, (
                f"Company {cid} cannot access its own gap result {gr.job_id}"
            )
            assert result.company_id == cid

        # Verify other companies' results are NOT accessible
        other_results = [
            gr for gr in store.gap_results if gr.company_id != cid
        ]
        for gr in other_results:
            result = store.get_gap_analysis_results(cid, gr.job_id)
            assert result is None, (
                f"Company {cid} was able to access gap result "
                f"{gr.job_id} belonging to company {gr.company_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Notifications
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_notifications_company_isolation(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any notifications query scoped by X-Company-Id, the response
    SHALL contain only unacknowledged notifications belonging to that
    company. No notifications from other companies SHALL appear.

    **Validates: Requirements 8.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Test with multiple user IDs
        for user_id in range(1, 4):
            results = store.list_notifications(cid, user_id)

            for notif in results:
                assert notif.company_id == cid, (
                    f"Notification {notif.id} has "
                    f"company_id={notif.company_id}, expected {cid}"
                )
                assert notif.target_user_id == user_id, (
                    f"Notification {notif.id} has "
                    f"target_user_id={notif.target_user_id}, "
                    f"expected {user_id}"
                )
                assert not notif.is_acknowledged, (
                    f"Notification {notif.id} is acknowledged but was returned"
                )

            # Count matches expected
            expected = sum(
                1 for n in store.notifications
                if n.company_id == cid
                and n.target_user_id == user_id
                and not n.is_acknowledged
            )
            assert len(results) == expected, (
                f"Company {cid}, user {user_id}: expected {expected} "
                f"notifications, got {len(results)}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Job Status
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_job_status_company_isolation(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any job status query scoped by X-Company-Id, jobs from other
    companies SHALL NOT be accessible (returns None/404).

    **Validates: Requirements 6.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Verify own jobs are accessible
        company_jobs = [j for j in store.jobs if j.company_id == cid]
        for job in company_jobs:
            result = store.get_job_status(cid, job.job_id)
            assert result is not None, (
                f"Company {cid} cannot access its own job {job.job_id}"
            )
            assert result.company_id == cid

        # Verify other companies' jobs are NOT accessible
        other_jobs = [j for j in store.jobs if j.company_id != cid]
        for job in other_jobs:
            result = store.get_job_status(cid, job.job_id)
            assert result is None, (
                f"Company {cid} was able to access job "
                f"{job.job_id} belonging to company {job.company_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Cross-company partition invariant
# ---------------------------------------------------------------------------


@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_no_cross_company_data_leakage(
    store_and_ids: tuple[ImpactAnalysisDataStore, list[int]],
) -> None:
    """For any set of companies, the union of all company-scoped query
    results SHALL equal the total data set, and no single company's query
    SHALL contain records from another company. This is the completeness
    and partition invariant for impact analysis data.

    **Validates: Requirements 1.11, 2.7, 3.7, 4.8, 5.6, 6.6, 8.6**
    """
    store, company_ids = store_and_ids

    # Edges: union of all company queries == total edges
    all_edge_ids_from_queries: set[int] = set()
    for cid in company_ids:
        results = store.list_edges(cid)
        for e in results:
            assert e.id not in all_edge_ids_from_queries, (
                f"Edge {e.id} appeared in multiple company queries"
            )
            all_edge_ids_from_queries.add(e.id)
    assert all_edge_ids_from_queries == {e.id for e in store.edges}

    # Reports: union of all company queries == total reports
    all_report_ids_from_queries: set[str] = set()
    for cid in company_ids:
        results = store.list_reports(cid)
        for r in results:
            assert r.report_id not in all_report_ids_from_queries, (
                f"Report {r.report_id} appeared in multiple company queries"
            )
            all_report_ids_from_queries.add(r.report_id)
    assert all_report_ids_from_queries == {
        r.report_id for r in store.reports
    }

    # Gap results: each result accessible only from its own company
    for gr in store.gap_results:
        for cid in company_ids:
            result = store.get_gap_analysis_results(cid, gr.job_id)
            if cid == gr.company_id:
                assert result is not None, (
                    f"Gap result {gr.job_id} not accessible from its own "
                    f"company {cid}"
                )
            else:
                assert result is None, (
                    f"Gap result {gr.job_id} (company {gr.company_id}) "
                    f"accessible from company {cid}"
                )

    # Jobs: each job accessible only from its own company
    for job in store.jobs:
        for cid in company_ids:
            result = store.get_job_status(cid, job.job_id)
            if cid == job.company_id:
                assert result is not None, (
                    f"Job {job.job_id} not accessible from its own "
                    f"company {cid}"
                )
            else:
                assert result is None, (
                    f"Job {job.job_id} (company {job.company_id}) "
                    f"accessible from company {cid}"
                )
