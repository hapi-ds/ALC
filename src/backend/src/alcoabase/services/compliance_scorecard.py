"""Compliance Scorecard Service for computing company-level audit readiness.

This module provides the ComplianceScorecardService that computes real-time
compliance scorecards per company. It aggregates compliance scores from
completed review sessions, classifies risk bands, detects trends, and
provides breakdowns by document type.

Score formula:
    score = max(0.0, 100.0 - Σ(weight[severity] × count[severity]))

Severity weights:
    Critical      = 25.0
    Major         = 10.0
    Minor         =  3.0
    Informational =  0.5

Risk bands:
    Excellent:       90–100
    Good:            75–89
    Needs Attention: 50–74
    At Risk:         25–49
    Critical:         0–24

References:
    - Requirements 6.1, 6.2, 6.3, 6.4, 6.5
    - Design doc Section 3: Compliance Scorecard Service
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from alcoabase.models.document import Document
from alcoabase.models.review import ActionItem, ReviewSession

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Severity weights for compliance score computation.
SEVERITY_WEIGHTS: dict[str, float] = {
    "Critical": 25.0,
    "Major": 10.0,
    "Minor": 3.0,
    "Informational": 0.5,
}

#: Risk band thresholds (lower bound inclusive, upper bound inclusive).
RISK_BANDS: list[tuple[float, float, str]] = [
    (90.0, 100.0, "Excellent"),
    (75.0, 89.99, "Good"),
    (50.0, 74.99, "Needs Attention"),
    (25.0, 49.99, "At Risk"),
    (0.0, 24.99, "Critical"),
]

#: Default scoring window in days.
DEFAULT_SCORING_WINDOW_DAYS: int = 90


# ---------------------------------------------------------------------------
# Pure computation functions (testable without DB)
# ---------------------------------------------------------------------------


def compute_compliance_score(finding_counts: dict[str, int]) -> float:
    """Compute a compliance score from finding counts by severity.

    Applies the formula: max(0.0, 100.0 - Σ(weight[severity] × count[severity]))

    Args:
        finding_counts: Dictionary mapping severity names to their counts.
            Keys should be one of: Critical, Major, Minor, Informational.
            Unknown severity keys are ignored.

    Returns:
        Compliance score clamped to [0.0, 100.0].

    Examples:
        >>> compute_compliance_score({"Critical": 2, "Major": 3, "Minor": 5})
        5.0
        >>> compute_compliance_score({})
        100.0
        >>> compute_compliance_score({"Critical": 10})
        0.0
    """
    penalty = sum(
        SEVERITY_WEIGHTS.get(severity, 0.0) * count
        for severity, count in finding_counts.items()
    )
    return max(0.0, 100.0 - penalty)


def classify_risk_band(score: float) -> str:
    """Classify a compliance score into a risk band.

    Args:
        score: Compliance score in [0.0, 100.0].

    Returns:
        Risk band label: Excellent, Good, Needs Attention, At Risk, or Critical.
    """
    for lower, upper, label in RISK_BANDS:
        if lower <= score <= upper:
            return label
    # Edge case: score exactly 100.0 should be Excellent
    if score >= 90.0:
        return "Excellent"
    return "Critical"


def determine_trend(current_avg: float | None, previous_avg: float | None) -> str:
    """Determine the compliance trend by comparing two period averages.

    Args:
        current_avg: Average score for the current period (None if no data).
        previous_avg: Average score for the previous period (None if no data).

    Returns:
        One of: "improving", "stable", or "declining".
        Returns "stable" if either period has no data.
    """
    if current_avg is None or previous_avg is None:
        return "stable"

    diff = current_avg - previous_avg
    if diff > 2.0:
        return "improving"
    elif diff < -2.0:
        return "declining"
    return "stable"


# ---------------------------------------------------------------------------
# Service Class
# ---------------------------------------------------------------------------


class ComplianceScorecardService:
    """Computes real-time compliance scorecards per company.

    Aggregates compliance scores from completed review sessions within
    a configurable time window (default 90 days), classifies risk bands,
    detects trends, and provides breakdowns by document type.

    Attributes:
        _session_factory: SQLAlchemy async session factory for DB access.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Initialize the ComplianceScorecardService.

        Args:
            session_factory: SQLAlchemy async session factory for DB access.
        """
        self._session_factory = session_factory

    async def get_scorecard(self, company_id: int) -> dict:
        """Compute the full compliance scorecard for a company.

        Averages compliance scores of all completed review sessions within
        the last 90 days. Includes trend analysis, document counts, and
        breakdown by document type.

        Args:
            company_id: The company to compute the scorecard for.

        Returns:
            Dictionary containing:
                - overall_score: Average compliance score (0.0–100.0)
                - risk_band: Risk classification label
                - trend: "improving", "stable", or "declining"
                - total_documents_reviewed: Count of completed sessions
                - documents_with_critical_findings: Sessions with score < 25
                - documents_with_open_action_items: Sessions with open action items
                - score_by_document_type: Breakdown by document type
                - last_updated: Current UTC timestamp
        """
        now = datetime.now(UTC)
        window_start = now - timedelta(days=DEFAULT_SCORING_WINDOW_DAYS)

        async with self._session_factory() as session:
            # Get all completed sessions within the scoring window
            completed_sessions = await self._get_completed_sessions(
                session, company_id, window_start
            )

            # Compute overall score (average of session scores)
            scores = [
                s.compliance_score
                for s in completed_sessions
                if s.compliance_score is not None
            ]
            overall_score = sum(scores) / len(scores) if scores else 100.0

            # Count documents with critical findings (score < 25)
            critical_count = sum(1 for s in scores if s < 25.0)

            # Count documents with open action items
            open_action_items_count = await self._count_sessions_with_open_items(
                session, company_id, completed_sessions
            )

            # Get score breakdown by document type
            score_by_type = await self.get_score_by_document_type(
                company_id, session=session, window_start=window_start
            )

            # Get trend
            trend = await self.get_trend(company_id, session=session)

        return {
            "overall_score": round(overall_score, 2),
            "risk_band": classify_risk_band(overall_score),
            "trend": trend,
            "total_documents_reviewed": len(completed_sessions),
            "documents_with_critical_findings": critical_count,
            "documents_with_open_action_items": open_action_items_count,
            "score_by_document_type": score_by_type,
            "last_updated": now,
        }

    async def get_score_by_document_type(
        self,
        company_id: int,
        *,
        session: AsyncSession | None = None,
        window_start: datetime | None = None,
    ) -> dict[str, float]:
        """Compute average compliance score grouped by document type.

        Args:
            company_id: The company to compute scores for.
            session: Optional existing DB session (creates one if None).
            window_start: Optional start of scoring window (defaults to 90 days ago).

        Returns:
            Dictionary mapping document type to average compliance score.
        """
        if window_start is None:
            window_start = datetime.now(UTC) - timedelta(
                days=DEFAULT_SCORING_WINDOW_DAYS
            )

        async def _query(db_session: AsyncSession) -> dict[str, float]:
            stmt = (
                select(
                    Document.document_type,
                    func.avg(ReviewSession.compliance_score).label("avg_score"),
                )
                .join(Document, ReviewSession.document_id == Document.id)
                .where(
                    ReviewSession.company_id == company_id,
                    ReviewSession.status == "Completed",
                    ReviewSession.completed_at >= window_start,
                    ReviewSession.compliance_score.isnot(None),
                )
                .group_by(Document.document_type)
            )
            result = await db_session.execute(stmt)
            rows = result.all()
            return {
                row.document_type: round(float(row.avg_score), 2)
                for row in rows
            }

        if session is not None:
            return await _query(session)

        async with self._session_factory() as new_session:
            return await _query(new_session)

    async def get_trend(
        self,
        company_id: int,
        days: int = 30,
        *,
        session: AsyncSession | None = None,
    ) -> str:
        """Compare current period average vs previous period average.

        Computes the average compliance score for the most recent `days`
        period and compares it to the preceding `days` period.

        Args:
            company_id: The company to compute the trend for.
            days: Number of days for each comparison period (default 30).
            session: Optional existing DB session (creates one if None).

        Returns:
            One of: "improving", "stable", or "declining".
        """

        async def _query(db_session: AsyncSession) -> str:
            now = datetime.now(UTC)
            current_start = now - timedelta(days=days)
            previous_start = now - timedelta(days=days * 2)

            # Current period average
            current_avg = await self._get_period_average(
                db_session, company_id, current_start, now
            )

            # Previous period average
            previous_avg = await self._get_period_average(
                db_session, company_id, previous_start, current_start
            )

            return determine_trend(current_avg, previous_avg)

        if session is not None:
            return await _query(session)

        async with self._session_factory() as new_session:
            return await _query(new_session)

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    async def _get_completed_sessions(
        self,
        session: AsyncSession,
        company_id: int,
        window_start: datetime,
    ) -> list[ReviewSession]:
        """Fetch completed review sessions within the scoring window.

        Args:
            session: Active DB session.
            company_id: Company to filter by.
            window_start: Start of the scoring window.

        Returns:
            List of ReviewSession objects with status "Completed".
        """
        stmt = select(ReviewSession).where(
            ReviewSession.company_id == company_id,
            ReviewSession.status == "Completed",
            ReviewSession.completed_at >= window_start,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _count_sessions_with_open_items(
        self,
        session: AsyncSession,
        company_id: int,
        completed_sessions: list[ReviewSession],
    ) -> int:
        """Count sessions that have at least one open action item.

        Args:
            session: Active DB session.
            company_id: Company to filter by (unused, sessions already filtered).
            completed_sessions: List of completed sessions to check.

        Returns:
            Number of sessions with open action items.
        """
        if not completed_sessions:
            return 0

        session_ids = [s.id for s in completed_sessions]

        stmt = (
            select(func.count(func.distinct(ActionItem.session_id)))
            .where(
                ActionItem.session_id.in_(session_ids),
                ActionItem.status.in_(["Open", "InProgress"]),
            )
        )
        result = await session.execute(stmt)
        count = result.scalar_one_or_none()
        return count or 0

    async def _get_period_average(
        self,
        session: AsyncSession,
        company_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> float | None:
        """Compute average compliance score for a time period.

        Args:
            session: Active DB session.
            company_id: Company to filter by.
            period_start: Start of the period (inclusive).
            period_end: End of the period (exclusive).

        Returns:
            Average compliance score, or None if no sessions in the period.
        """
        stmt = select(func.avg(ReviewSession.compliance_score)).where(
            ReviewSession.company_id == company_id,
            ReviewSession.status == "Completed",
            ReviewSession.completed_at >= period_start,
            ReviewSession.completed_at < period_end,
            ReviewSession.compliance_score.isnot(None),
        )
        result = await session.execute(stmt)
        avg = result.scalar_one_or_none()
        return float(avg) if avg is not None else None
