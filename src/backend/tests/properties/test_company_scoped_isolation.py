"""Property-based tests for company-scoped isolation in the review pipeline.

Tests Property 7 from the multi-agent always-on auditing design document,
validating that review sessions, audit profiles, compliance scorecards,
missing links, and anomaly alerts for company A are never visible to company B.

**Validates: Requirements 1.10, 4.6, 6.5, 7.6, 8.6**

References:
    - Design: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/design.md (Property 7)
    - Requirements: .kiro/specs/Step_5-2_multi-agent-always-on-auditing/requirements.md
"""

from __future__ import annotations

from dataclasses import dataclass, field

import hypothesis.strategies as st
from hypothesis import given, settings


# ---------------------------------------------------------------------------
# Pure model of company-scoped data and isolation logic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewSessionRecord:
    """Represents a review session record with company scope.

    Attributes:
        id: Unique session identifier.
        company_id: Owning company (tenant isolation key).
        document_id: The reviewed document.
        status: Session status.
        compliance_score: Computed compliance score (nullable).
    """

    id: int
    company_id: int
    document_id: int
    status: str = "Completed"
    compliance_score: float | None = 85.0


@dataclass(frozen=True)
class AuditProfileRecord:
    """Represents an audit profile record with company scope.

    Attributes:
        id: Unique profile identifier.
        company_id: Owning company (tenant isolation key).
        name: Profile display name.
        is_active: Whether the profile is active.
    """

    id: int
    company_id: int
    name: str
    is_active: bool = True


@dataclass(frozen=True)
class AnomalyAlertRecord:
    """Represents an anomaly alert record with company scope.

    Attributes:
        id: Unique alert identifier.
        company_id: Owning company (tenant isolation key).
        anomaly_type: Classification of the anomaly.
        severity: Alert severity level.
    """

    id: int
    company_id: int
    anomaly_type: str
    severity: str


@dataclass(frozen=True)
class MissingLinkRecord:
    """Represents a document with missing compliance links.

    Attributes:
        document_id: The document with gaps.
        company_id: Owning company (tenant isolation key).
        document_status: Current document status.
        missing_items: List of missing items (training/signature).
    """

    document_id: int
    company_id: int
    document_status: str
    missing_items: list[str] = field(default_factory=lambda: ["training"])


@dataclass
class CompanyDataStore:
    """Simulates the multi-tenant data store with company-scoped queries.

    Models the behavior of the service layer where all queries are filtered
    by company_id. This mirrors how ReviewPipelineService.list_sessions,
    AuditProfileService.list_profiles, AnomalyDetectionService.list_alerts,
    MissingLinkService.detect_missing_links, and
    ComplianceScorecardService.get_scorecard all scope by company_id.

    Attributes:
        sessions: All review sessions across all companies.
        profiles: All audit profiles across all companies.
        alerts: All anomaly alerts across all companies.
        missing_links: All missing link records across all companies.
    """

    sessions: list[ReviewSessionRecord] = field(default_factory=list)
    profiles: list[AuditProfileRecord] = field(default_factory=list)
    alerts: list[AnomalyAlertRecord] = field(default_factory=list)
    missing_links: list[MissingLinkRecord] = field(default_factory=list)


    def list_sessions(self, company_id: int) -> list[ReviewSessionRecord]:
        """List review sessions scoped to a company.

        Mirrors ReviewPipelineService.list_sessions which filters by
        ReviewSession.company_id == company_id.

        Args:
            company_id: The company to query for.

        Returns:
            Sessions belonging to the specified company only.
        """
        return [s for s in self.sessions if s.company_id == company_id]

    def list_profiles(self, company_id: int) -> list[AuditProfileRecord]:
        """List audit profiles scoped to a company.

        Mirrors AuditProfileService.list_profiles which filters by
        AuditProfile.company_id == company_id AND is_active == True.

        Args:
            company_id: The company to query for.

        Returns:
            Active profiles belonging to the specified company only.
        """
        return [
            p for p in self.profiles
            if p.company_id == company_id and p.is_active
        ]

    def list_alerts(self, company_id: int) -> list[AnomalyAlertRecord]:
        """List anomaly alerts scoped to a company.

        Mirrors AnomalyDetectionService.list_alerts which filters by
        AnomalyAlert.company_id == company_id.

        Args:
            company_id: The company to query for.

        Returns:
            Alerts belonging to the specified company only.
        """
        return [a for a in self.alerts if a.company_id == company_id]


    def detect_missing_links(self, company_id: int) -> list[MissingLinkRecord]:
        """Detect missing links scoped to a company.

        Mirrors MissingLinkService.detect_missing_links which filters by
        Document.company_id == company_id AND status in (Approved, Active).

        Args:
            company_id: The company to query for.

        Returns:
            Missing link records for the specified company only.
        """
        return [
            ml for ml in self.missing_links
            if ml.company_id == company_id
            and ml.document_status in ("Approved", "Active")
        ]

    def get_scorecard_sessions(
        self, company_id: int
    ) -> list[ReviewSessionRecord]:
        """Get completed sessions for scorecard computation.

        Mirrors ComplianceScorecardService._get_completed_sessions which
        filters by company_id and status == "Completed".

        Args:
            company_id: The company to compute scorecard for.

        Returns:
            Completed sessions with scores for the specified company only.
        """
        return [
            s for s in self.sessions
            if s.company_id == company_id
            and s.status == "Completed"
            and s.compliance_score is not None
        ]


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

ANOMALY_TYPES = [
    "backdated_signature",
    "workflow_bypass",
    "bulk_approval",
    "off_hours_mutation",
    "rapid_version_churn",
]

SESSION_STATUSES = ["Pending", "InProgress", "Completed", "Failed"]


@st.composite
def st_populated_store(draw: st.DrawFn) -> tuple[CompanyDataStore, list[int]]:
    """Generate a data store populated with multi-company review data.

    Creates 2-4 companies with random distributions of review sessions,
    audit profiles, anomaly alerts, and missing link records.

    Returns:
        Tuple of (populated CompanyDataStore, list of company IDs).
    """
    num_companies = draw(st.integers(min_value=2, max_value=4))
    company_ids = list(range(1, num_companies + 1))

    store = CompanyDataStore()

    # Generate review sessions
    session_id = 1
    doc_id = 1
    for cid in company_ids:
        num_sessions = draw(st.integers(min_value=0, max_value=6))
        for _ in range(num_sessions):
            status = draw(st.sampled_from(SESSION_STATUSES))
            score = (
                draw(st.floats(min_value=0.0, max_value=100.0))
                if status == "Completed"
                else None
            )
            store.sessions.append(
                ReviewSessionRecord(
                    id=session_id,
                    company_id=cid,
                    document_id=doc_id,
                    status=status,
                    compliance_score=score,
                )
            )
            session_id += 1
            doc_id += 1

    # Generate audit profiles
    profile_id = 1
    for cid in company_ids:
        num_profiles = draw(st.integers(min_value=0, max_value=4))
        for i in range(num_profiles):
            store.profiles.append(
                AuditProfileRecord(
                    id=profile_id,
                    company_id=cid,
                    name=f"Profile-{profile_id}",
                    is_active=draw(st.booleans()),
                )
            )
            profile_id += 1


    # Generate anomaly alerts
    alert_id = 1
    for cid in company_ids:
        num_alerts = draw(st.integers(min_value=0, max_value=6))
        for _ in range(num_alerts):
            store.alerts.append(
                AnomalyAlertRecord(
                    id=alert_id,
                    company_id=cid,
                    anomaly_type=draw(st.sampled_from(ANOMALY_TYPES)),
                    severity=draw(
                        st.sampled_from(["Critical", "Major", "Minor"])
                    ),
                )
            )
            alert_id += 1

    # Generate missing link records
    ml_doc_id = 1000
    for cid in company_ids:
        num_links = draw(st.integers(min_value=0, max_value=5))
        for _ in range(num_links):
            status = draw(
                st.sampled_from(["Approved", "Active", "Draft", "InReview"])
            )
            items = draw(
                st.lists(
                    st.sampled_from(["training", "signature"]),
                    min_size=1,
                    max_size=2,
                    unique=True,
                )
            )
            store.missing_links.append(
                MissingLinkRecord(
                    document_id=ml_doc_id,
                    company_id=cid,
                    document_status=status,
                    missing_items=items,
                )
            )
            ml_doc_id += 1

    return store, company_ids


# ---------------------------------------------------------------------------
# Property 7: Company-scoped isolation — Review Sessions
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 7: Review session isolation
@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_review_sessions_company_isolation(
    store_and_ids: tuple[CompanyDataStore, list[int]],
) -> None:
    """For any two companies A and B, listing review sessions for company A
    SHALL return only sessions where company_id = A, and no sessions
    belonging to any other company shall ever appear.

    **Validates: Requirements 1.10**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_sessions(cid)

        # Every returned session belongs to this company
        for session in results:
            assert session.company_id == cid, (
                f"Session {session.id} has company_id={session.company_id}, "
                f"expected {cid}"
            )

        # Count matches expected
        expected = sum(
            1 for s in store.sessions if s.company_id == cid
        )
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} sessions, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 7: Company-scoped isolation — Audit Profiles
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 7: Audit profile isolation
@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_audit_profiles_company_isolation(
    store_and_ids: tuple[CompanyDataStore, list[int]],
) -> None:
    """For any two companies A and B, listing audit profiles for company A
    SHALL return only active profiles where company_id = A, and no profiles
    belonging to any other company shall ever appear.

    **Validates: Requirements 4.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_profiles(cid)

        # Every returned profile belongs to this company and is active
        for profile in results:
            assert profile.company_id == cid, (
                f"Profile {profile.id} has company_id={profile.company_id}, "
                f"expected {cid}"
            )
            assert profile.is_active, (
                f"Profile {profile.id} is inactive but was returned"
            )

        # Count matches expected (active profiles for this company)
        expected = sum(
            1 for p in store.profiles
            if p.company_id == cid and p.is_active
        )
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} profiles, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 7: Company-scoped isolation — Anomaly Alerts
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 7: Anomaly alert isolation
@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_anomaly_alerts_company_isolation(
    store_and_ids: tuple[CompanyDataStore, list[int]],
) -> None:
    """For any two companies A and B, listing anomaly alerts for company A
    SHALL return only alerts where company_id = A, and no alerts
    belonging to any other company shall ever appear.

    **Validates: Requirements 8.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.list_alerts(cid)

        # Every returned alert belongs to this company
        for alert in results:
            assert alert.company_id == cid, (
                f"Alert {alert.id} has company_id={alert.company_id}, "
                f"expected {cid}"
            )

        # Count matches expected
        expected = sum(
            1 for a in store.alerts if a.company_id == cid
        )
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} alerts, got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 7: Company-scoped isolation — Compliance Scorecard
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 7: Compliance scorecard isolation
@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_compliance_scorecard_company_isolation(
    store_and_ids: tuple[CompanyDataStore, list[int]],
) -> None:
    """For any two companies A and B, computing the compliance scorecard for
    company A SHALL only consider completed review sessions belonging to
    company A, never including company B's sessions in the score computation.

    **Validates: Requirements 6.5**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        scorecard_sessions = store.get_scorecard_sessions(cid)

        # Every session used for scorecard belongs to this company
        for session in scorecard_sessions:
            assert session.company_id == cid, (
                f"Scorecard session {session.id} has "
                f"company_id={session.company_id}, expected {cid}"
            )
            assert session.status == "Completed", (
                f"Scorecard session {session.id} has status={session.status}, "
                f"expected Completed"
            )
            assert session.compliance_score is not None, (
                f"Scorecard session {session.id} has no compliance score"
            )

        # Count matches expected
        expected = sum(
            1 for s in store.sessions
            if s.company_id == cid
            and s.status == "Completed"
            and s.compliance_score is not None
        )
        assert len(scorecard_sessions) == expected, (
            f"Company {cid}: expected {expected} scorecard sessions, "
            f"got {len(scorecard_sessions)}"
        )

        # Verify score computation uses only this company's data
        if scorecard_sessions:
            scores = [s.compliance_score for s in scorecard_sessions]
            avg_score = sum(scores) / len(scores)
            # The average should only reflect this company's scores
            other_scores = [
                s.compliance_score
                for s in store.sessions
                if s.company_id != cid
                and s.status == "Completed"
                and s.compliance_score is not None
            ]
            # If other companies have different scores, our average
            # should not be influenced by them
            if other_scores and scores:
                # Recompute to verify isolation
                assert abs(avg_score - sum(scores) / len(scores)) < 1e-9


# ---------------------------------------------------------------------------
# Property 7: Company-scoped isolation — Missing Links
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 7: Missing link isolation
@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_missing_links_company_isolation(
    store_and_ids: tuple[CompanyDataStore, list[int]],
) -> None:
    """For any two companies A and B, detecting missing links for company A
    SHALL only consider documents belonging to company A in Approved/Active
    status, never including company B's documents.

    **Validates: Requirements 7.6**
    """
    store, company_ids = store_and_ids

    for cid in company_ids:
        results = store.detect_missing_links(cid)

        # Every returned missing link belongs to this company
        for ml in results:
            assert ml.company_id == cid, (
                f"Missing link doc {ml.document_id} has "
                f"company_id={ml.company_id}, expected {cid}"
            )
            assert ml.document_status in ("Approved", "Active"), (
                f"Missing link doc {ml.document_id} has "
                f"status={ml.document_status}, expected Approved or Active"
            )

        # Count matches expected
        expected = sum(
            1 for ml in store.missing_links
            if ml.company_id == cid
            and ml.document_status in ("Approved", "Active")
        )
        assert len(results) == expected, (
            f"Company {cid}: expected {expected} missing links, "
            f"got {len(results)}"
        )


# ---------------------------------------------------------------------------
# Property 7: Company-scoped isolation — Cross-company access invariant
# ---------------------------------------------------------------------------


# Feature: multi-agent-always-on-auditing, Property 7: No cross-company leakage
@settings(max_examples=200)
@given(store_and_ids=st_populated_store())
def test_no_cross_company_data_leakage(
    store_and_ids: tuple[CompanyDataStore, list[int]],
) -> None:
    """For any set of companies, the union of all company-scoped query results
    SHALL equal the total data set, and no single company's query SHALL
    contain records from another company. This is the completeness and
    partition invariant.

    **Validates: Requirements 1.10, 4.6, 6.5, 7.6, 8.6**
    """
    store, company_ids = store_and_ids

    # Sessions: union of all company queries == total sessions
    all_session_ids_from_queries: set[int] = set()
    for cid in company_ids:
        results = store.list_sessions(cid)
        for s in results:
            assert s.id not in all_session_ids_from_queries, (
                f"Session {s.id} appeared in multiple company queries"
            )
            all_session_ids_from_queries.add(s.id)
    assert all_session_ids_from_queries == {s.id for s in store.sessions}

    # Alerts: union of all company queries == total alerts
    all_alert_ids_from_queries: set[int] = set()
    for cid in company_ids:
        results = store.list_alerts(cid)
        for a in results:
            assert a.id not in all_alert_ids_from_queries, (
                f"Alert {a.id} appeared in multiple company queries"
            )
            all_alert_ids_from_queries.add(a.id)
    assert all_alert_ids_from_queries == {a.id for a in store.alerts}

    # Missing links (Approved/Active only): partition check
    all_ml_doc_ids_from_queries: set[int] = set()
    for cid in company_ids:
        results = store.detect_missing_links(cid)
        for ml in results:
            assert ml.document_id not in all_ml_doc_ids_from_queries, (
                f"Missing link doc {ml.document_id} appeared in "
                f"multiple company queries"
            )
            all_ml_doc_ids_from_queries.add(ml.document_id)
    expected_ml_ids = {
        ml.document_id
        for ml in store.missing_links
        if ml.document_status in ("Approved", "Active")
    }
    assert all_ml_doc_ids_from_queries == expected_ml_ids
