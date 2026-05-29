"""Property-based tests for company isolation in traceability endpoints.

Tests Property 3 from the AI-Powered Traceability & Gap Discovery design
document, validating that traceability matrices, coverage snapshots, alerts,
stale-link markers, and job status for company A are never visible to
company B across all traceability endpoints.

**Validates: Requirements 1.8, 2.6, 3.6, 4.5, 5.6, 7.6, 7.7, 9.6, 11.6**

References:
    - Design: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/design.md
    - Requirements: .kiro/specs/Step_5-6_ai-powered-traceability-gap-discovery/requirements.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure model of multi-tenant traceability data and isolation logic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatrixRecord:
    """Represents a traceability matrix record with company scope.

    Attributes:
        matrix_id: Unique matrix UUID identifier.
        company_id: Owning company (tenant isolation key).
        matrix_name: Human-readable matrix name.
        source_document_uuids: Source document UUIDs.
        target_document_uuids: Target document UUIDs.
        status: Matrix status (completed, partial_success, failed).
        traceability_links: List of link dicts.
        orphan_requirements: List of orphan requirement dicts.
        orphan_test_cases: List of orphan test case dicts.
        deleted_at: Soft-delete timestamp or None.
    """

    matrix_id: str
    company_id: int
    matrix_name: str
    source_document_uuids: list[str] = field(default_factory=list)
    target_document_uuids: list[str] = field(default_factory=list)
    status: str = "completed"
    traceability_links: list[dict] = field(default_factory=list)
    orphan_requirements: list[dict] = field(default_factory=list)
    orphan_test_cases: list[dict] = field(default_factory=list)
    deleted_at: datetime | None = None


@dataclass(frozen=True)
class CoverageSnapshotRecord:
    """Represents a coverage snapshot record with company scope.

    Attributes:
        id: Unique snapshot identifier.
        matrix_id: Associated matrix UUID.
        company_id: Owning company (tenant isolation key).
        source_document_uuid: Source document UUID.
        coverage_percentage: Coverage percentage (0.0-100.0).
        compliance_readiness_score: Compliance score (0.0-100.0).
        snapshot_date: When the snapshot was taken.
    """

    id: int
    matrix_id: str
    company_id: int
    source_document_uuid: str
    coverage_percentage: float
    compliance_readiness_score: float
    snapshot_date: datetime
    total_requirements: int = 0
    covered_requirements: int = 0
    orphan_requirements_count: int = 0
    total_test_cases: int = 0
    linked_test_cases: int = 0
    orphan_test_cases_count: int = 0


@dataclass(frozen=True)
class AlertRecord:
    """Represents a traceability alert record with company scope.

    Attributes:
        alert_id: Unique alert UUID identifier.
        company_id: Owning company (tenant isolation key).
        triggering_report_id: Impact report that triggered this alert.
        affected_matrix_ids: List of affected matrix UUIDs.
        affected_link_count: Number of affected links.
        alert_severity: Severity level (critical, major, minor).
        is_resolved: Whether the alert has been resolved.
    """

    alert_id: str
    company_id: int
    triggering_report_id: str
    affected_matrix_ids: list[str] = field(default_factory=list)
    affected_link_count: int = 0
    alert_severity: str = "major"
    is_resolved: bool = False


@dataclass(frozen=True)
class StaleLinkMarkerRecord:
    """Represents a stale link marker record with company scope.

    Attributes:
        id: Unique marker identifier.
        matrix_id: Associated matrix UUID.
        company_id: Owning company (tenant isolation key).
        requirement_id: The requirement that became stale.
        triggering_report_id: Impact report that triggered staleness.
        is_cleared: Whether the marker has been cleared.
    """

    id: int
    matrix_id: str
    company_id: int
    requirement_id: str
    triggering_report_id: str
    is_cleared: bool = False


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
class TraceabilityDataStore:
    """Simulates the multi-tenant data store for traceability.

    Models the behavior of the API layer where all queries are filtered
    by company_id (resolved from X-Company-Id header via TenantContext).
    This mirrors how the traceability router scopes all queries.

    Attributes:
        matrices: All traceability matrices across all companies.
        snapshots: All coverage snapshots across all companies.
        alerts: All traceability alerts across all companies.
        stale_markers: All stale link markers across all companies.
        jobs: All processing jobs across all companies.
    """

    matrices: list[MatrixRecord] = field(default_factory=list)
    snapshots: list[CoverageSnapshotRecord] = field(default_factory=list)
    alerts: list[AlertRecord] = field(default_factory=list)
    stale_markers: list[StaleLinkMarkerRecord] = field(default_factory=list)
    jobs: list[JobRecord] = field(default_factory=list)

    def list_matrices(
        self,
        company_id: int,
        source_document_uuid: str | None = None,
        target_document_uuid: str | None = None,
        status: str | None = None,
    ) -> list[MatrixRecord]:
        """List matrices scoped to a company, excluding soft-deleted.

        Mirrors GET /traceability/matrices which filters by
        TraceabilityMatrix.company_id == tenant.company_id AND
        deleted_at IS NULL.

        Args:
            company_id: The company to query for.
            source_document_uuid: Optional source filter.
            target_document_uuid: Optional target filter.
            status: Optional status filter.

        Returns:
            Matrices belonging to the specified company only.
        """
        results = [
            m for m in self.matrices
            if m.company_id == company_id and m.deleted_at is None
        ]
        if source_document_uuid:
            results = [
                m for m in results
                if source_document_uuid in m.source_document_uuids
            ]
        if target_document_uuid:
            results = [
                m for m in results
                if target_document_uuid in m.target_document_uuids
            ]
        if status:
            results = [m for m in results if m.status == status]
        return results

    def get_matrix(
        self, company_id: int, matrix_id: str
    ) -> MatrixRecord | None:
        """Get a single matrix by matrix_id scoped to a company.

        Mirrors GET /traceability/matrices/{matrix_id} which filters by
        TraceabilityMatrix.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.
            matrix_id: The matrix UUID to look up.

        Returns:
            The matrix if found in company scope, else None.
        """
        for m in self.matrices:
            if m.company_id == company_id and m.matrix_id == matrix_id:
                return m
        return None

    def get_matrix_links(
        self, company_id: int, matrix_id: str
    ) -> list[dict] | None:
        """Get traceability links for a matrix scoped to a company.

        Mirrors GET /traceability/matrices/{matrix_id}/links which first
        verifies the matrix belongs to the company.

        Args:
            company_id: The company to query for.
            matrix_id: The matrix UUID to look up.

        Returns:
            Links list if matrix found in company scope, else None.
        """
        matrix = self.get_matrix(company_id, matrix_id)
        if matrix is None:
            return None
        return matrix.traceability_links

    def get_orphan_requirements(
        self, company_id: int, matrix_id: str
    ) -> list[dict] | None:
        """Get orphan requirements for a matrix scoped to a company.

        Mirrors GET /traceability/matrices/{matrix_id}/orphan-requirements
        which first verifies the matrix belongs to the company.

        Args:
            company_id: The company to query for.
            matrix_id: The matrix UUID to look up.

        Returns:
            Orphan requirements if matrix found in company scope, else None.
        """
        matrix = self.get_matrix(company_id, matrix_id)
        if matrix is None:
            return None
        return matrix.orphan_requirements

    def get_orphan_test_cases(
        self, company_id: int, matrix_id: str
    ) -> list[dict] | None:
        """Get orphan test cases for a matrix scoped to a company.

        Mirrors GET /traceability/matrices/{matrix_id}/orphan-test-cases
        which first verifies the matrix belongs to the company.

        Args:
            company_id: The company to query for.
            matrix_id: The matrix UUID to look up.

        Returns:
            Orphan test cases if matrix found in company scope, else None.
        """
        matrix = self.get_matrix(company_id, matrix_id)
        if matrix is None:
            return None
        return matrix.orphan_test_cases

    def list_snapshots(
        self,
        company_id: int,
        source_document_uuid: str | None = None,
    ) -> list[CoverageSnapshotRecord]:
        """List coverage snapshots scoped to a company.

        Mirrors GET /traceability/coverage/history which filters by
        CoverageSnapshot.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.
            source_document_uuid: Optional source document filter.

        Returns:
            Snapshots belonging to the specified company only.
        """
        results = [s for s in self.snapshots if s.company_id == company_id]
        if source_document_uuid:
            results = [
                s for s in results
                if s.source_document_uuid == source_document_uuid
            ]
        return results

    def get_coverage_summary(
        self, company_id: int
    ) -> dict:
        """Get aggregated coverage summary scoped to a company.

        Mirrors GET /traceability/coverage/summary which aggregates
        across all non-deleted matrices for the company.

        Args:
            company_id: The company to query for.

        Returns:
            Summary dict with aggregated metrics for the company.
        """
        company_matrices = [
            m for m in self.matrices
            if m.company_id == company_id and m.deleted_at is None
        ]
        return {
            "total_matrices": len(company_matrices),
            "company_id": company_id,
        }

    def list_alerts(
        self,
        company_id: int,
        unresolved_only: bool = True,
    ) -> list[AlertRecord]:
        """List traceability alerts scoped to a company.

        Mirrors GET /traceability/alerts which filters by
        TraceabilityAlert.company_id == tenant.company_id AND
        is_resolved == False.

        Args:
            company_id: The company to query for.
            unresolved_only: If True, only return unresolved alerts.

        Returns:
            Alerts belonging to the specified company only.
        """
        results = [a for a in self.alerts if a.company_id == company_id]
        if unresolved_only:
            results = [a for a in results if not a.is_resolved]
        return results

    def get_alert(
        self, company_id: int, alert_id: str
    ) -> AlertRecord | None:
        """Get a single alert by alert_id scoped to a company.

        Mirrors POST /traceability/alerts/{alert_id}/resolve which
        verifies the alert belongs to the company.

        Args:
            company_id: The company to query for.
            alert_id: The alert UUID to look up.

        Returns:
            The alert if found in company scope, else None.
        """
        for a in self.alerts:
            if a.company_id == company_id and a.alert_id == alert_id:
                return a
        return None

    def list_stale_markers(
        self, company_id: int, matrix_id: str | None = None
    ) -> list[StaleLinkMarkerRecord]:
        """List stale link markers scoped to a company.

        Mirrors the stale marker queries which filter by
        StaleLinkMarker.company_id == tenant.company_id.

        Args:
            company_id: The company to query for.
            matrix_id: Optional matrix filter.

        Returns:
            Stale markers belonging to the specified company only.
        """
        results = [
            sm for sm in self.stale_markers if sm.company_id == company_id
        ]
        if matrix_id:
            results = [sm for sm in results if sm.matrix_id == matrix_id]
        return results

    def get_job_status(
        self, company_id: int, job_id: str
    ) -> JobRecord | None:
        """Get job status scoped to a company.

        Mirrors GET /traceability/jobs/{job_id}/status which filters by
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

MATRIX_STATUSES = ["completed", "partial_success", "failed"]
ALERT_SEVERITIES = ["critical", "major", "minor"]
LINK_METHODS = ["exact_id_match", "cross_reference", "semantic_match"]
ORPHAN_SEVERITIES = ["critical", "major", "minor"]
RISK_LEVELS = ["high", "medium", "low"]
JOB_STATUSES = ["processing", "completed", "partial_success", "failed"]


def _make_uuid(prefix: str, idx: int) -> str:
    """Generate a deterministic short UUID-like string for testing."""
    return f"{prefix}{idx:06d}"


@st.composite
def st_populated_store(
    draw: st.DrawFn,
) -> tuple[TraceabilityDataStore, list[int]]:
    """Generate a data store populated with multi-company traceability data.

    Creates 2-4 companies with random distributions of matrices, snapshots,
    alerts, stale markers, and jobs.

    Returns:
        Tuple of (populated TraceabilityDataStore, list of company IDs).
    """
    num_companies = draw(st.integers(min_value=2, max_value=4))
    company_ids = list(range(1, num_companies + 1))

    store = TraceabilityDataStore()

    # Generate traceability matrices
    matrix_counter = 1
    for cid in company_ids:
        num_matrices = draw(st.integers(min_value=0, max_value=6))
        for i in range(num_matrices):
            matrix_id = _make_uuid("mtx", matrix_counter)
            num_links = draw(st.integers(min_value=0, max_value=4))
            links = [
                {
                    "requirement_id": f"REQ-{cid:03d}-{j:03d}",
                    "test_case_id": f"TC-{cid:03d}-{j:03d}",
                    "link_confidence": draw(
                        st.floats(min_value=0.5, max_value=1.0)
                    ),
                    "link_method": draw(st.sampled_from(LINK_METHODS)),
                }
                for j in range(num_links)
            ]
            num_orphan_reqs = draw(st.integers(min_value=0, max_value=3))
            orphan_reqs = [
                {
                    "requirement_id": f"REQ-{cid:03d}-O{j:03d}",
                    "severity": draw(st.sampled_from(ORPHAN_SEVERITIES)),
                    "source_document_uuid": _make_uuid("doc", cid * 100 + j),
                }
                for j in range(num_orphan_reqs)
            ]
            num_orphan_tcs = draw(st.integers(min_value=0, max_value=3))
            orphan_tcs = [
                {
                    "test_case_id": f"TC-{cid:03d}-O{j:03d}",
                    "risk_level": draw(st.sampled_from(RISK_LEVELS)),
                    "target_document_uuid": _make_uuid("doc", cid * 100 + j + 50),
                }
                for j in range(num_orphan_tcs)
            ]
            is_deleted = draw(st.booleans()) and draw(st.booleans())
            deleted_at = (
                datetime(2024, 1, 1, tzinfo=timezone.utc) if is_deleted else None
            )
            store.matrices.append(
                MatrixRecord(
                    matrix_id=matrix_id,
                    company_id=cid,
                    matrix_name=f"Matrix {matrix_counter}",
                    source_document_uuids=[
                        _make_uuid("doc", cid * 100 + k)
                        for k in range(draw(st.integers(min_value=1, max_value=3)))
                    ],
                    target_document_uuids=[
                        _make_uuid("doc", cid * 100 + k + 50)
                        for k in range(draw(st.integers(min_value=1, max_value=3)))
                    ],
                    status=draw(st.sampled_from(MATRIX_STATUSES)),
                    traceability_links=links,
                    orphan_requirements=orphan_reqs,
                    orphan_test_cases=orphan_tcs,
                    deleted_at=deleted_at,
                )
            )
            matrix_counter += 1

    # Generate coverage snapshots
    snapshot_id = 1
    for cid in company_ids:
        num_snapshots = draw(st.integers(min_value=0, max_value=5))
        for i in range(num_snapshots):
            store.snapshots.append(
                CoverageSnapshotRecord(
                    id=snapshot_id,
                    matrix_id=_make_uuid("mtx", snapshot_id),
                    company_id=cid,
                    source_document_uuid=_make_uuid("doc", cid * 100 + i),
                    coverage_percentage=draw(
                        st.floats(min_value=0.0, max_value=100.0)
                    ),
                    compliance_readiness_score=draw(
                        st.floats(min_value=0.0, max_value=100.0)
                    ),
                    snapshot_date=datetime(
                        2024, 1, draw(st.integers(min_value=1, max_value=28)),
                        tzinfo=timezone.utc,
                    ),
                    total_requirements=draw(
                        st.integers(min_value=0, max_value=50)
                    ),
                    covered_requirements=draw(
                        st.integers(min_value=0, max_value=50)
                    ),
                    orphan_requirements_count=draw(
                        st.integers(min_value=0, max_value=20)
                    ),
                    total_test_cases=draw(
                        st.integers(min_value=0, max_value=50)
                    ),
                    linked_test_cases=draw(
                        st.integers(min_value=0, max_value=50)
                    ),
                    orphan_test_cases_count=draw(
                        st.integers(min_value=0, max_value=20)
                    ),
                )
            )
            snapshot_id += 1

    # Generate traceability alerts
    alert_counter = 1
    for cid in company_ids:
        num_alerts = draw(st.integers(min_value=0, max_value=5))
        for i in range(num_alerts):
            store.alerts.append(
                AlertRecord(
                    alert_id=_make_uuid("alt", alert_counter),
                    company_id=cid,
                    triggering_report_id=_make_uuid("rpt", alert_counter),
                    affected_matrix_ids=[
                        _make_uuid("mtx", alert_counter + k)
                        for k in range(
                            draw(st.integers(min_value=1, max_value=3))
                        )
                    ],
                    affected_link_count=draw(
                        st.integers(min_value=0, max_value=20)
                    ),
                    alert_severity=draw(st.sampled_from(ALERT_SEVERITIES)),
                    is_resolved=draw(st.booleans()),
                )
            )
            alert_counter += 1

    # Generate stale link markers
    marker_id = 1
    for cid in company_ids:
        num_markers = draw(st.integers(min_value=0, max_value=6))
        for i in range(num_markers):
            store.stale_markers.append(
                StaleLinkMarkerRecord(
                    id=marker_id,
                    matrix_id=_make_uuid("mtx", marker_id),
                    company_id=cid,
                    requirement_id=f"REQ-{cid:03d}-{i:03d}",
                    triggering_report_id=_make_uuid("rpt", marker_id),
                    is_cleared=draw(st.booleans()),
                )
            )
            marker_id += 1

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
# Property 3: Company Isolation — Traceability Matrices
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_matrices_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any API query to the matrices endpoint scoped by X-Company-Id,
    the response SHALL contain only non-deleted matrices belonging to that
    company. No matrices from other companies SHALL appear.

    **Validates: Requirements 1.8, 4.5, 5.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_matrices(cid)

        # Every returned matrix belongs to this company
        for matrix in results:
            assert matrix.company_id == cid, (
                f"Matrix {matrix.matrix_id} has company_id={matrix.company_id}, "
                f"expected {cid}"
            )
            # Soft-deleted matrices are excluded
            assert matrix.deleted_at is None, (
                f"Matrix {matrix.matrix_id} is soft-deleted but was returned"
            )

        # Count matches expected (non-deleted only)
        expected = sum(
            1 for m in store.matrices
            if m.company_id == cid and m.deleted_at is None
        )
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} matrices, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Single Matrix Lookup
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_matrix_lookup_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any matrix lookup scoped by X-Company-Id, a matrix belonging
    to another company SHALL NOT be returned (returns None/404).

    **Validates: Requirements 1.8, 4.5, 5.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Try to access matrices from other companies
        other_matrices = [m for m in store.matrices if m.company_id != cid]
        for other_matrix in other_matrices:
            result = store.get_matrix(cid, other_matrix.matrix_id)
            assert result is None, (
                f"Company {cid} was able to access matrix "
                f"{other_matrix.matrix_id} belonging to company "
                f"{other_matrix.company_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Traceability Links
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_links_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any links query scoped by X-Company-Id, links from matrices
    belonging to other companies SHALL NOT be accessible (returns None/404).

    **Validates: Requirements 1.8, 5.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Try to access links from other companies' matrices
        other_matrices = [m for m in store.matrices if m.company_id != cid]
        for other_matrix in other_matrices:
            result = store.get_matrix_links(cid, other_matrix.matrix_id)
            assert result is None, (
                f"Company {cid} was able to access links from matrix "
                f"{other_matrix.matrix_id} belonging to company "
                f"{other_matrix.company_id}"
            )

        # Verify own matrices' links are accessible
        own_matrices = [m for m in store.matrices if m.company_id == cid]
        for own_matrix in own_matrices:
            result = store.get_matrix_links(cid, own_matrix.matrix_id)
            assert result is not None, (
                f"Company {cid} cannot access links from its own matrix "
                f"{own_matrix.matrix_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Orphan Requirements
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_orphan_requirements_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any orphan requirements query scoped by X-Company-Id, orphans
    from matrices belonging to other companies SHALL NOT be accessible.

    **Validates: Requirements 2.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Try to access orphan requirements from other companies' matrices
        other_matrices = [m for m in store.matrices if m.company_id != cid]
        for other_matrix in other_matrices:
            result = store.get_orphan_requirements(cid, other_matrix.matrix_id)
            assert result is None, (
                f"Company {cid} was able to access orphan requirements from "
                f"matrix {other_matrix.matrix_id} belonging to company "
                f"{other_matrix.company_id}"
            )

        # Verify own matrices' orphan requirements are accessible
        own_matrices = [m for m in store.matrices if m.company_id == cid]
        for own_matrix in own_matrices:
            result = store.get_orphan_requirements(cid, own_matrix.matrix_id)
            assert result is not None, (
                f"Company {cid} cannot access orphan requirements from its "
                f"own matrix {own_matrix.matrix_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Orphan Test Cases
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_orphan_test_cases_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any orphan test cases query scoped by X-Company-Id, orphans
    from matrices belonging to other companies SHALL NOT be accessible.

    **Validates: Requirements 3.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Try to access orphan test cases from other companies' matrices
        other_matrices = [m for m in store.matrices if m.company_id != cid]
        for other_matrix in other_matrices:
            result = store.get_orphan_test_cases(cid, other_matrix.matrix_id)
            assert result is None, (
                f"Company {cid} was able to access orphan test cases from "
                f"matrix {other_matrix.matrix_id} belonging to company "
                f"{other_matrix.company_id}"
            )

        # Verify own matrices' orphan test cases are accessible
        own_matrices = [m for m in store.matrices if m.company_id == cid]
        for own_matrix in own_matrices:
            result = store.get_orphan_test_cases(cid, own_matrix.matrix_id)
            assert result is not None, (
                f"Company {cid} cannot access orphan test cases from its "
                f"own matrix {own_matrix.matrix_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Coverage Snapshots
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_coverage_snapshots_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any coverage history query scoped by X-Company-Id, the response
    SHALL contain only snapshots belonging to that company. No snapshots
    from other companies SHALL appear.

    **Validates: Requirements 7.6, 7.7**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_snapshots(cid)

        # Every returned snapshot belongs to this company
        for snapshot in results:
            assert snapshot.company_id == cid, (
                f"Snapshot {snapshot.id} has company_id={snapshot.company_id}, "
                f"expected {cid}"
            )

        # Count matches expected
        expected = sum(1 for s in store.snapshots if s.company_id == cid)
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} snapshots, "
            f"got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Traceability Alerts
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_alerts_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any alerts query scoped by X-Company-Id, the response SHALL
    contain only unresolved alerts belonging to that company. No alerts
    from other companies SHALL appear.

    **Validates: Requirements 9.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_alerts(cid, unresolved_only=True)

        # Every returned alert belongs to this company
        for alert in results:
            assert alert.company_id == cid, (
                f"Alert {alert.alert_id} has company_id={alert.company_id}, "
                f"expected {cid}"
            )
            assert not alert.is_resolved, (
                f"Alert {alert.alert_id} is resolved but was returned"
            )

        # Count matches expected
        expected = sum(
            1 for a in store.alerts
            if a.company_id == cid and not a.is_resolved
        )
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} unresolved alerts, "
            f"got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Alert Lookup (cross-tenant)
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_alert_lookup_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any alert lookup scoped by X-Company-Id, an alert belonging
    to another company SHALL NOT be returned (returns None/404).

    **Validates: Requirements 9.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        # Try to access alerts from other companies
        other_alerts = [a for a in store.alerts if a.company_id != cid]
        for other_alert in other_alerts:
            result = store.get_alert(cid, other_alert.alert_id)
            assert result is None, (
                f"Company {cid} was able to access alert "
                f"{other_alert.alert_id} belonging to company "
                f"{other_alert.company_id}"
            )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Stale Link Markers
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_stale_markers_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any stale link marker query scoped by X-Company-Id, the response
    SHALL contain only markers belonging to that company. No markers from
    other companies SHALL appear.

    **Validates: Requirements 9.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_stale_markers(cid)

        # Every returned marker belongs to this company
        for marker in results:
            assert marker.company_id == cid, (
                f"Stale marker {marker.id} has "
                f"company_id={marker.company_id}, expected {cid}"
            )

        # Count matches expected
        expected = sum(
            1 for sm in store.stale_markers if sm.company_id == cid
        )
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} stale markers, "
            f"got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 3: Company Isolation — Job Status
# ---------------------------------------------------------------------------


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_job_status_company_isolation(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any job status query scoped by X-Company-Id, jobs from other
    companies SHALL NOT be accessible (returns None/404).

    **Validates: Requirements 11.6**
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


@settings(max_examples=10)
@given(store_and_ids=st_populated_store())
def test_no_cross_company_data_leakage(
    store_and_ids: tuple[TraceabilityDataStore, list[int]],
) -> None:
    """For any set of companies, the union of all company-scoped query
    results SHALL equal the total data set, and no single company's query
    SHALL contain records from another company. This is the completeness
    and partition invariant for traceability data.

    **Validates: Requirements 1.8, 2.6, 3.6, 4.5, 5.6, 7.6, 7.7, 9.6, 11.6**
    """
    store, company_ids = store_and_ids

    # Matrices: union of all company queries == total non-deleted matrices
    all_matrix_ids_from_queries: set[str] = set()
    for cid in company_ids:
        results = store.list_matrices(cid)
        for m in results:
            assert m.matrix_id not in all_matrix_ids_from_queries, (
                f"Matrix {m.matrix_id} appeared in multiple company queries"
            )
            all_matrix_ids_from_queries.add(m.matrix_id)
    expected_non_deleted = {
        m.matrix_id for m in store.matrices if m.deleted_at is None
    }
    assert all_matrix_ids_from_queries == expected_non_deleted

    # Snapshots: union of all company queries == total snapshots
    all_snapshot_ids_from_queries: set[int] = set()
    for cid in company_ids:
        results = store.list_snapshots(cid)
        for s in results:
            assert s.id not in all_snapshot_ids_from_queries, (
                f"Snapshot {s.id} appeared in multiple company queries"
            )
            all_snapshot_ids_from_queries.add(s.id)
    assert all_snapshot_ids_from_queries == {s.id for s in store.snapshots}

    # Alerts: each alert accessible only from its own company
    for alert in store.alerts:
        for cid in company_ids:
            result = store.get_alert(cid, alert.alert_id)
            if cid == alert.company_id:
                assert result is not None, (
                    f"Alert {alert.alert_id} not accessible from its own "
                    f"company {cid}"
                )
            else:
                assert result is None, (
                    f"Alert {alert.alert_id} (company {alert.company_id}) "
                    f"accessible from company {cid}"
                )

    # Stale markers: union of all company queries == total markers
    all_marker_ids_from_queries: set[int] = set()
    for cid in company_ids:
        results = store.list_stale_markers(cid)
        for sm in results:
            assert sm.id not in all_marker_ids_from_queries, (
                f"Stale marker {sm.id} appeared in multiple company queries"
            )
            all_marker_ids_from_queries.add(sm.id)
    assert all_marker_ids_from_queries == {
        sm.id for sm in store.stale_markers
    }

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
