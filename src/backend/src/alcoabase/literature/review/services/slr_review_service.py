"""SLR Review workflow management service.

Manages the end-to-end Systematic Literature Review lifecycle including
state machine transitions, screening initiation, human overrides, PRISMA
flow statistics, inter-rater reliability metrics, and report generation.

All operations are company-scoped and emit audit trail events via logging.

References:
    - Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9
    - Design: .kiro/specs/Step_9-4_literature-review-synthesis-agents/design.md
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.literature.review.exceptions import (
    DecisionNotFoundError,
    InvalidStateTransitionError,
    ProtocolNotFoundError,
    ReviewNotFoundError,
)
from alcoabase.literature.review.models.screening_decision import (
    ScreeningDecision,
)
from alcoabase.literature.review.models.screening_protocol import (
    ScreeningProtocol,
)
from alcoabase.literature.review.models.screening_run import ScreeningRun
from alcoabase.literature.review.models.slr_review import SLRReview

logger = logging.getLogger(__name__)


class SLRReviewService:
    """Manages SLR Review lifecycle with state machine enforcement.

    Responsibilities:
        - Create reviews linked to protocols and record sets
        - Enforce state machine transitions
        - Initiate screening runs as Celery tasks
        - Record human overrides on screening decisions
        - Compute PRISMA flow statistics from decision aggregates
        - Provide real-time screening progress
        - Compute inter-rater reliability (Cohen's kappa)
        - Generate comprehensive SLR reports
        - Auto-transition to screening_complete when criteria are met
    """

    # Valid state transitions for the SLR Review lifecycle.
    # protocol_defined → screening_in_progress → screening_complete →
    # human_review_in_progress → completed
    VALID_TRANSITIONS: dict[str, list[str]] = {
        "protocol_defined": ["screening_in_progress"],
        "screening_in_progress": ["screening_complete"],
        "screening_complete": ["human_review_in_progress", "completed"],
        "human_review_in_progress": ["completed"],
        "completed": [],
    }

    async def create_review(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        user_id: int,
        protocol_id: int,
        name: str,
        description: str | None = None,
        record_filter: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new SLR Review in protocol_defined state.

        Validates that the protocol exists within the same company scope,
        resolves the record_filter into IngestionRecord IDs to count
        records_identified, and persists the review.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            user_id: Creating user.
            protocol_id: FK to the ScreeningProtocol to use.
            name: Review name (1–200 chars).
            description: Optional description.
            record_filter: Optional JSONB filter for record selection. Supports
                keys: ingestion_record_ids, state, date_range, source_id.

        Returns:
            Dict with created review fields.

        Raises:
            ProtocolNotFoundError: If protocol not found in this company.
        """
        # Validate protocol belongs to this company
        await self._get_protocol_or_raise(session, protocol_id, company_id)

        # Resolve record count from filter
        records_identified = await self._resolve_record_count(
            session, company_id=company_id, record_filter=record_filter
        )

        review = SLRReview(
            company_id=company_id,
            protocol_id=protocol_id,
            name=name,
            description=description,
            status="protocol_defined",
            record_filter=record_filter,
            created_by=user_id,
            records_identified=records_identified,
        )

        session.add(review)
        await session.flush()
        await session.refresh(review)

        logger.info(
            "SLR review created: id=%d, company_id=%d, protocol_id=%d, "
            "user_id=%d, records_identified=%d",
            review.id,
            company_id,
            protocol_id,
            user_id,
            records_identified,
        )

        return self._review_to_dict(review)

    async def initiate_screening(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
        user_id: int,
        batch_size: int = 20,
        re_screen_uncertain: bool = False,
    ) -> dict[str, Any]:
        """Initiate a screening run for the review.

        Creates a ScreeningRun record, transitions the review to
        screening_in_progress, and dispatches a Celery task for
        asynchronous execution.

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.
            user_id: Initiating user.
            batch_size: Records per batch (1–100, default 20).
            re_screen_uncertain: Whether to re-screen uncertain records only.

        Returns:
            Dict with task_id and screening_run_id.

        Raises:
            ReviewNotFoundError: If review not found in this company.
            InvalidStateTransitionError: If review not in a valid state for screening.
        """
        review = await self._get_review_or_raise(session, review_id, company_id)

        # Allow screening from protocol_defined or screening_complete (re-screen)
        valid_initiation_states = ("protocol_defined", "screening_complete")
        if review.status not in valid_initiation_states:
            raise InvalidStateTransitionError(
                f"Cannot initiate screening from state '{review.status}'. "
                f"Review must be in one of: {valid_initiation_states}.",
                current_state=review.status,
                target_state="screening_in_progress",
            )

        # Transition state
        self._transition_state(review, "screening_in_progress")

        # Determine total records for this run
        total_records = review.records_identified
        total_batches = (total_records + batch_size - 1) // batch_size if total_records > 0 else 0

        # Generate task ID
        task_id = str(uuid.uuid4())

        # Create ScreeningRun record
        screening_run = ScreeningRun(
            review_id=review.id,
            protocol_id=review.protocol_id,
            company_id=company_id,
            status="queued",
            total_records=total_records,
            batch_size=batch_size,
            total_batches=total_batches,
            celery_task_id=task_id,
        )

        session.add(screening_run)
        await session.flush()
        await session.refresh(screening_run)

        logger.info(
            "Screening run initiated: run_id=%d, review_id=%d, company_id=%d, "
            "task_id=%s, total_records=%d, batch_size=%d",
            screening_run.id,
            review_id,
            company_id,
            task_id,
            total_records,
            batch_size,
        )

        # Dispatch Celery task (placeholder — connected later)
        from alcoabase.tasks.literature_screening_tasks import (
            execute_screening_batch,
        )

        execute_screening_batch.delay(
            screening_run_id=screening_run.id,
            review_id=review_id,
            protocol_id=review.protocol_id,
            company_id=company_id,
            batch_size=batch_size,
            re_screen_uncertain=re_screen_uncertain,
        )

        return {
            "task_id": task_id,
            "screening_run_id": screening_run.id,
            "review_id": review_id,
            "status": "queued",
            "total_records": total_records,
            "batch_size": batch_size,
            "total_batches": total_batches,
        }

    async def record_human_override(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        decision_id: int,
        company_id: int,
        user_id: int,
        human_verdict: str,
        human_rationale: str,
    ) -> dict[str, Any]:
        """Record a human override on a screening decision.

        Stores the human_verdict, human_rationale, reviewer user_id, and
        timestamp on the ScreeningDecision. Records the override in the
        audit trail. After recording, checks if auto-completion criteria
        are met.

        Args:
            session: Active async DB session.
            review_id: Parent review.
            decision_id: Target decision.
            company_id: Tenant scope.
            user_id: Reviewer user.
            human_verdict: "include" or "exclude".
            human_rationale: Explanation text (max 2000 chars).

        Returns:
            Dict with the updated decision fields.

        Raises:
            ReviewNotFoundError: If review not found in this company.
            DecisionNotFoundError: If decision not found in this review.
        """
        # Validate review exists
        review = await self._get_review_or_raise(session, review_id, company_id)

        # Find the decision
        stmt = select(ScreeningDecision).where(
            ScreeningDecision.id == decision_id,
            ScreeningDecision.company_id == company_id,
        )
        result = await session.execute(stmt)
        decision = result.scalar_one_or_none()

        if decision is None:
            raise DecisionNotFoundError(
                f"Screening decision id={decision_id} not found "
                f"in review_id={review_id}.",
                decision_id=decision_id,
                review_id=review_id,
            )

        # Record the human override
        now = datetime.now(tz=timezone.utc)
        decision.human_verdict = human_verdict
        decision.human_rationale = human_rationale
        decision.human_reviewer_id = user_id
        decision.human_override_at = now

        await session.flush()

        logger.info(
            "Human override recorded: decision_id=%d, review_id=%d, "
            "company_id=%d, user_id=%d, verdict=%s",
            decision_id,
            review_id,
            company_id,
            user_id,
            human_verdict,
        )

        # If the review is in screening_complete or human_review_in_progress,
        # transition to human_review_in_progress if needed and check auto-completion
        if review.status == "screening_complete":
            self._transition_state(review, "human_review_in_progress")

        # Check auto-completion
        should_complete = await self._check_auto_completion(
            session, review_id=review_id, company_id=company_id
        )
        if should_complete and review.status == "human_review_in_progress":
            self._transition_state(review, "completed")
            review.completed_at = now
            review.completed_by = user_id
            logger.info(
                "SLR review auto-completed: review_id=%d, company_id=%d",
                review_id,
                company_id,
            )

        await session.flush()

        return self._decision_to_dict(decision)

    async def get_prisma_flow(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Compute PRISMA flow statistics from ScreeningDecision aggregates.

        Computes real-time statistics:
        - records_identified: total records in the review
        - records_screened: total with a ScreeningDecision
        - records_eligible: include or uncertain after AI screening
        - records_included_final: confirmed by human or uncontested AI include
        - records_excluded_with_reasons: grouped by exclusion category

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.

        Returns:
            Dict with PRISMA flow statistics.

        Raises:
            ReviewNotFoundError: If review not found in this company.
        """
        review = await self._get_review_or_raise(session, review_id, company_id)

        # Get all screening runs for this review
        runs_stmt = select(ScreeningRun.id).where(
            ScreeningRun.review_id == review_id,
            ScreeningRun.company_id == company_id,
        )
        runs_result = await session.execute(runs_stmt)
        run_ids = [row[0] for row in runs_result.all()]

        if not run_ids:
            return {
                "review_id": review_id,
                "records_identified": review.records_identified,
                "records_screened": 0,
                "records_eligible": 0,
                "records_included_final": 0,
                "records_excluded_with_reasons": {},
            }

        # Total screened (distinct ingestion_record_ids with decisions)
        screened_stmt = select(
            func.count(ScreeningDecision.id.distinct())
        ).where(
            ScreeningDecision.screening_run_id.in_(run_ids),
            ScreeningDecision.company_id == company_id,
        )
        screened_result = await session.execute(screened_stmt)
        records_screened = screened_result.scalar_one() or 0

        # Records eligible (include or uncertain AI verdict)
        eligible_stmt = select(
            func.count(ScreeningDecision.id.distinct())
        ).where(
            ScreeningDecision.screening_run_id.in_(run_ids),
            ScreeningDecision.company_id == company_id,
            ScreeningDecision.verdict.in_(["include", "uncertain"]),
        )
        eligible_result = await session.execute(eligible_stmt)
        records_eligible = eligible_result.scalar_one() or 0

        # Records included final: human_verdict = "include" OR
        # (AI verdict = "include" with confidence >= 0.8 and no human override)
        included_final_stmt = select(
            func.count(ScreeningDecision.id.distinct())
        ).where(
            ScreeningDecision.screening_run_id.in_(run_ids),
            ScreeningDecision.company_id == company_id,
        ).where(
            (ScreeningDecision.human_verdict == "include")
            | (
                (ScreeningDecision.verdict == "include")
                & (ScreeningDecision.confidence >= 0.8)
                & (ScreeningDecision.human_verdict.is_(None))
            )
        )
        included_result = await session.execute(included_final_stmt)
        records_included_final = included_result.scalar_one() or 0

        # Excluded with reasons: human_verdict = "exclude" OR
        # (AI verdict = "exclude" with confidence >= 0.8 and no human override)
        excluded_stmt = select(
            ScreeningDecision.verdict,
            func.count(ScreeningDecision.id),
        ).where(
            ScreeningDecision.screening_run_id.in_(run_ids),
            ScreeningDecision.company_id == company_id,
        ).where(
            (ScreeningDecision.human_verdict == "exclude")
            | (
                (ScreeningDecision.verdict == "exclude")
                & (ScreeningDecision.confidence >= 0.8)
                & (ScreeningDecision.human_verdict.is_(None))
            )
        ).group_by(ScreeningDecision.verdict)
        excluded_result = await session.execute(excluded_stmt)
        excluded_rows = excluded_result.all()

        records_excluded_with_reasons: dict[str, int] = {}
        for verdict, count in excluded_rows:
            records_excluded_with_reasons[verdict] = count

        return {
            "review_id": review_id,
            "records_identified": review.records_identified,
            "records_screened": records_screened,
            "records_eligible": records_eligible,
            "records_included_final": records_included_final,
            "records_excluded_with_reasons": records_excluded_with_reasons,
        }

    async def get_progress(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Return real-time screening progress for a review.

        Aggregates progress from all ScreeningRuns associated with the review.

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.

        Returns:
            Dict with progress metrics: total, screened, pending,
            include/exclude/uncertain counts, estimated_time_remaining.

        Raises:
            ReviewNotFoundError: If review not found in this company.
        """
        review = await self._get_review_or_raise(session, review_id, company_id)

        # Aggregate progress from all screening runs
        progress_stmt = select(
            func.coalesce(func.sum(ScreeningRun.total_records), 0).label("total"),
            func.coalesce(func.sum(ScreeningRun.screened_count), 0).label("screened"),
            func.coalesce(func.sum(ScreeningRun.include_count), 0).label("include_count"),
            func.coalesce(func.sum(ScreeningRun.exclude_count), 0).label("exclude_count"),
            func.coalesce(func.sum(ScreeningRun.uncertain_count), 0).label("uncertain_count"),
        ).where(
            ScreeningRun.review_id == review_id,
            ScreeningRun.company_id == company_id,
        )
        progress_result = await session.execute(progress_stmt)
        row = progress_result.one()

        total = int(row.total)
        screened = int(row.screened)
        pending = total - screened
        include_count = int(row.include_count)
        exclude_count = int(row.exclude_count)
        uncertain_count = int(row.uncertain_count)

        # Estimate time remaining based on average screening duration
        estimated_time_remaining: float | None = None
        if screened > 0 and pending > 0:
            # Get average screening duration from decisions
            avg_stmt = select(
                func.avg(ScreeningDecision.screening_duration_ms)
            ).where(
                ScreeningDecision.screening_run_id.in_(
                    select(ScreeningRun.id).where(
                        ScreeningRun.review_id == review_id,
                        ScreeningRun.company_id == company_id,
                    )
                )
            )
            avg_result = await session.execute(avg_stmt)
            avg_duration_ms = avg_result.scalar_one()
            if avg_duration_ms is not None:
                estimated_time_remaining = (
                    float(avg_duration_ms) * pending / 1000.0
                )

        return {
            "review_id": review_id,
            "status": review.status,
            "total_records": total,
            "screened_count": screened,
            "pending_count": pending,
            "include_count": include_count,
            "exclude_count": exclude_count,
            "uncertain_count": uncertain_count,
            "estimated_time_remaining_seconds": estimated_time_remaining,
        }

    async def compute_inter_rater_reliability(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Compute inter-rater reliability metrics between AI and human verdicts.

        Calculates:
        - agreement_rate: percentage of AI decisions confirmed by humans
        - cohens_kappa: Cohen's kappa coefficient
        - per_criterion_rates: false positive/negative rates per criterion

        Cohen's kappa: kappa = (P_observed - P_expected) / (1 - P_expected)
        Handles edge case where P_expected == 1.0 (returns kappa=0.0).

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.

        Returns:
            Dict with inter-rater reliability metrics.

        Raises:
            ReviewNotFoundError: If review not found in this company.
        """
        await self._get_review_or_raise(session, review_id, company_id)

        # Get all decisions with human overrides for this review
        run_ids_stmt = select(ScreeningRun.id).where(
            ScreeningRun.review_id == review_id,
            ScreeningRun.company_id == company_id,
        )
        decisions_stmt = select(ScreeningDecision).where(
            ScreeningDecision.screening_run_id.in_(run_ids_stmt),
            ScreeningDecision.company_id == company_id,
            ScreeningDecision.human_verdict.isnot(None),
        )
        decisions_result = await session.execute(decisions_stmt)
        decisions = list(decisions_result.scalars().all())

        if not decisions:
            return {
                "review_id": review_id,
                "total_overrides": 0,
                "agreement_rate": None,
                "cohens_kappa": None,
                "per_criterion_false_positive_rate": {},
                "per_criterion_false_negative_rate": {},
            }

        # Compute agreement rate and confusion matrix
        total = len(decisions)
        agreements = 0
        # For kappa: binary classification (include vs exclude)
        # AI predictions and human labels
        ai_include = 0
        ai_exclude = 0
        human_include = 0
        human_exclude = 0
        both_include = 0
        both_exclude = 0

        # Per-criterion tracking for false positive/negative rates
        # False positive: AI says include criteria matched, human says exclude
        # False negative: AI says exclude criteria matched, human says include
        inclusion_criteria_fp: dict[int, int] = {}
        inclusion_criteria_total: dict[int, int] = {}
        exclusion_criteria_fn: dict[int, int] = {}
        exclusion_criteria_total: dict[int, int] = {}

        for decision in decisions:
            ai_verdict = decision.verdict
            h_verdict = decision.human_verdict

            # Map uncertain to exclude for kappa computation
            ai_binary = "include" if ai_verdict == "include" else "exclude"

            if ai_binary == h_verdict:
                agreements += 1

            if ai_binary == "include":
                ai_include += 1
            else:
                ai_exclude += 1

            if h_verdict == "include":
                human_include += 1
            else:
                human_exclude += 1

            if ai_binary == "include" and h_verdict == "include":
                both_include += 1
            elif ai_binary == "exclude" and h_verdict == "exclude":
                both_exclude += 1

            # Per-criterion analysis
            if h_verdict == "exclude" and ai_binary == "include":
                # False positive: AI matched inclusion criteria incorrectly
                for idx in (decision.matched_inclusion_criteria or []):
                    inclusion_criteria_fp[idx] = inclusion_criteria_fp.get(idx, 0) + 1

            if h_verdict == "include" and ai_binary == "exclude":
                # False negative: AI matched exclusion criteria incorrectly
                for idx in (decision.matched_exclusion_criteria or []):
                    exclusion_criteria_fn[idx] = exclusion_criteria_fn.get(idx, 0) + 1

            # Track total appearances per criterion
            for idx in (decision.matched_inclusion_criteria or []):
                inclusion_criteria_total[idx] = inclusion_criteria_total.get(idx, 0) + 1
            for idx in (decision.matched_exclusion_criteria or []):
                exclusion_criteria_total[idx] = exclusion_criteria_total.get(idx, 0) + 1

        # Agreement rate
        agreement_rate = agreements / total if total > 0 else 0.0

        # Cohen's kappa
        p_observed = agreements / total if total > 0 else 0.0

        # Expected agreement by chance
        p_ai_include = ai_include / total if total > 0 else 0.0
        p_ai_exclude = ai_exclude / total if total > 0 else 0.0
        p_human_include = human_include / total if total > 0 else 0.0
        p_human_exclude = human_exclude / total if total > 0 else 0.0

        p_expected = (p_ai_include * p_human_include) + (
            p_ai_exclude * p_human_exclude
        )

        # Handle edge case where P_expected == 1.0
        if p_expected >= 1.0:
            cohens_kappa = 0.0
        else:
            cohens_kappa = (p_observed - p_expected) / (1.0 - p_expected)

        # Per-criterion false positive rates
        per_criterion_fp: dict[str, float] = {}
        for idx, fp_count in inclusion_criteria_fp.items():
            total_for_criterion = inclusion_criteria_total.get(idx, 1)
            per_criterion_fp[str(idx)] = fp_count / total_for_criterion

        # Per-criterion false negative rates
        per_criterion_fn: dict[str, float] = {}
        for idx, fn_count in exclusion_criteria_fn.items():
            total_for_criterion = exclusion_criteria_total.get(idx, 1)
            per_criterion_fn[str(idx)] = fn_count / total_for_criterion

        return {
            "review_id": review_id,
            "total_overrides": total,
            "agreement_rate": agreement_rate,
            "cohens_kappa": cohens_kappa,
            "per_criterion_false_positive_rate": per_criterion_fp,
            "per_criterion_false_negative_rate": per_criterion_fn,
        }

    async def generate_report(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Generate a comprehensive SLR summary report.

        Compiles metadata, PRISMA flow, statistics, rationale summaries,
        and inter-rater reliability into a JSON-exportable report for
        regulatory submissions.

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.

        Returns:
            Dict with full report content.

        Raises:
            ReviewNotFoundError: If review not found in this company.
        """
        review = await self._get_review_or_raise(session, review_id, company_id)

        # Get protocol metadata
        protocol = await self._get_protocol_or_raise(
            session, review.protocol_id, company_id
        )

        # PRISMA flow
        prisma_flow = await self.get_prisma_flow(
            session, review_id=review_id, company_id=company_id
        )

        # Progress/statistics
        progress = await self.get_progress(
            session, review_id=review_id, company_id=company_id
        )

        # Inter-rater reliability
        irr = await self.compute_inter_rater_reliability(
            session, review_id=review_id, company_id=company_id
        )

        # Rationale summaries (sample of top rationales by verdict)
        rationale_summaries = await self._get_rationale_summaries(
            session, review_id=review_id, company_id=company_id
        )

        # Compute duration
        duration_days: float | None = None
        if review.completed_at and review.created_at:
            delta = review.completed_at - review.created_at
            duration_days = delta.total_seconds() / 86400.0

        return {
            "review_id": review_id,
            "review_name": review.name,
            "review_description": review.description,
            "status": review.status,
            "metadata": {
                "protocol_id": review.protocol_id,
                "protocol_name": protocol.name,
                "company_id": company_id,
                "created_by": review.created_by,
                "created_at": (
                    review.created_at.isoformat() if review.created_at else None
                ),
                "completed_at": (
                    review.completed_at.isoformat()
                    if review.completed_at
                    else None
                ),
                "duration_days": duration_days,
            },
            "prisma_flow": prisma_flow,
            "screening_statistics": {
                "total_records": progress["total_records"],
                "screened_count": progress["screened_count"],
                "include_count": progress["include_count"],
                "exclude_count": progress["exclude_count"],
                "uncertain_count": progress["uncertain_count"],
            },
            "rationale_summaries": rationale_summaries,
            "inter_rater_reliability": irr,
        }

    async def get_review(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Get full review details.

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.

        Returns:
            Dict with review fields.

        Raises:
            ReviewNotFoundError: If review not found in this company.
        """
        review = await self._get_review_or_raise(session, review_id, company_id)
        return self._review_to_dict(review)

    async def list_reviews(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List reviews for a company with pagination and optional status filter.

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            status: Optional status filter.
            page: Page number (1-indexed).
            page_size: Items per page (1–100).

        Returns:
            Tuple of (reviews_list, total_count).
        """
        conditions = [SLRReview.company_id == company_id]
        if status is not None:
            conditions.append(SLRReview.status == status)

        # Count total
        count_stmt = select(func.count(SLRReview.id)).where(*conditions)
        total_result = await session.execute(count_stmt)
        total_count = total_result.scalar_one()

        # Fetch page
        offset = (page - 1) * page_size
        list_stmt = (
            select(SLRReview)
            .where(*conditions)
            .order_by(SLRReview.updated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(list_stmt)
        reviews = result.scalars().all()

        return [self._review_to_dict(r) for r in reviews], total_count

    # ─── Auto-Completion Check ────────────────────────────────────────────

    async def _check_auto_completion(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
        confidence_threshold: float = 0.8,
    ) -> bool:
        """Check if all records meet auto-completion criteria.

        Auto-transitions to screening_complete when all records have either:
        - A final human verdict, OR
        - An uncontested AI verdict with confidence >= threshold

        An "uncontested" AI verdict is one with verdict in ("include", "exclude")
        and no human override set.

        This is a pure logic check that returns bool without side effects.

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.
            confidence_threshold: Minimum confidence for uncontested AI verdicts.

        Returns:
            True if all records meet completion criteria.
        """
        # Get screening runs for this review
        run_ids_stmt = select(ScreeningRun.id).where(
            ScreeningRun.review_id == review_id,
            ScreeningRun.company_id == company_id,
        )

        # Count total decisions
        total_stmt = select(func.count(ScreeningDecision.id)).where(
            ScreeningDecision.screening_run_id.in_(run_ids_stmt),
            ScreeningDecision.company_id == company_id,
        )
        total_result = await session.execute(total_stmt)
        total_decisions = total_result.scalar_one() or 0

        if total_decisions == 0:
            return False

        # Count decisions that meet completion criteria:
        # 1. Has human verdict (regardless of AI), OR
        # 2. AI verdict in (include, exclude) with confidence >= threshold
        #    and no human override
        completed_stmt = select(func.count(ScreeningDecision.id)).where(
            ScreeningDecision.screening_run_id.in_(run_ids_stmt),
            ScreeningDecision.company_id == company_id,
        ).where(
            (ScreeningDecision.human_verdict.isnot(None))
            | (
                (ScreeningDecision.verdict.in_(["include", "exclude"]))
                & (ScreeningDecision.confidence >= confidence_threshold)
                & (ScreeningDecision.human_verdict.is_(None))
            )
        )
        completed_result = await session.execute(completed_stmt)
        completed_count = completed_result.scalar_one() or 0

        return completed_count >= total_decisions

    # ─── Private Helpers ──────────────────────────────────────────────────

    def _transition_state(self, review: SLRReview, target_state: str) -> None:
        """Enforce valid state transition and update status.

        Args:
            review: The SLRReview instance.
            target_state: The desired new state.

        Raises:
            InvalidStateTransitionError: If transition is not allowed.
        """
        current_state = review.status
        valid_targets = self.VALID_TRANSITIONS.get(current_state, [])

        if target_state not in valid_targets:
            raise InvalidStateTransitionError(
                f"Cannot transition from '{current_state}' to '{target_state}'. "
                f"Valid transitions from '{current_state}': {valid_targets}.",
                current_state=current_state,
                target_state=target_state,
            )

        review.status = target_state

    async def _get_review_or_raise(
        self,
        session: AsyncSession,
        review_id: int,
        company_id: int,
    ) -> SLRReview:
        """Fetch a review by ID within company scope, or raise.

        Args:
            session: Active async DB session.
            review_id: Review primary key.
            company_id: Tenant scope.

        Returns:
            The SLRReview instance.

        Raises:
            ReviewNotFoundError: If not found.
        """
        stmt = select(SLRReview).where(
            SLRReview.id == review_id,
            SLRReview.company_id == company_id,
        )
        result = await session.execute(stmt)
        review = result.scalar_one_or_none()

        if review is None:
            raise ReviewNotFoundError(
                f"SLR review id={review_id} not found "
                f"in company_id={company_id}.",
                review_id=review_id,
                company_id=company_id,
            )

        return review

    async def _get_protocol_or_raise(
        self,
        session: AsyncSession,
        protocol_id: int,
        company_id: int,
    ) -> ScreeningProtocol:
        """Fetch a protocol by ID within company scope, or raise.

        Args:
            session: Active async DB session.
            protocol_id: Protocol primary key.
            company_id: Tenant scope.

        Returns:
            The ScreeningProtocol instance.

        Raises:
            ProtocolNotFoundError: If not found.
        """
        stmt = select(ScreeningProtocol).where(
            ScreeningProtocol.id == protocol_id,
            ScreeningProtocol.company_id == company_id,
        )
        result = await session.execute(stmt)
        protocol = result.scalar_one_or_none()

        if protocol is None:
            raise ProtocolNotFoundError(
                f"Screening protocol id={protocol_id} not found "
                f"in company_id={company_id}.",
                protocol_id=protocol_id,
                company_id=company_id,
            )

        return protocol

    async def _resolve_record_count(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        record_filter: dict[str, Any] | None,
    ) -> int:
        """Resolve record_filter into a count of matching IngestionRecord IDs.

        Supports filter keys:
        - ingestion_record_ids: explicit list of IDs
        - state: filter by IngestionRecord state
        - source_id: filter by source adapter
        - date_range: filter by publication_date (from/to)

        Args:
            session: Active async DB session.
            company_id: Tenant scope.
            record_filter: Optional filter dict.

        Returns:
            Count of matching records.
        """
        from alcoabase.literature.ingestion.models.ingestion import (
            IngestionRecord,
        )

        if record_filter is None:
            # No filter: count all records for company
            stmt = select(func.count(IngestionRecord.id)).where(
                IngestionRecord.company_id == company_id
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

        # If explicit IDs are provided, just count those
        if "ingestion_record_ids" in record_filter:
            ids = record_filter["ingestion_record_ids"]
            if not ids:
                return 0
            stmt = select(func.count(IngestionRecord.id)).where(
                IngestionRecord.company_id == company_id,
                IngestionRecord.id.in_(ids),
            )
            result = await session.execute(stmt)
            return result.scalar_one() or 0

        # Build dynamic filter
        conditions = [IngestionRecord.company_id == company_id]

        if "state" in record_filter and record_filter["state"]:
            conditions.append(IngestionRecord.state == record_filter["state"])

        if "source_id" in record_filter and record_filter["source_id"]:
            conditions.append(
                IngestionRecord.source_id == record_filter["source_id"]
            )

        if "date_range" in record_filter and record_filter["date_range"]:
            date_range = record_filter["date_range"]
            if "from" in date_range and date_range["from"]:
                conditions.append(
                    IngestionRecord.publication_date >= date_range["from"]
                )
            if "to" in date_range and date_range["to"]:
                conditions.append(
                    IngestionRecord.publication_date <= date_range["to"]
                )

        stmt = select(func.count(IngestionRecord.id)).where(*conditions)
        result = await session.execute(stmt)
        return result.scalar_one() or 0

    async def _get_rationale_summaries(
        self,
        session: AsyncSession,
        *,
        review_id: int,
        company_id: int,
        limit: int = 10,
    ) -> dict[str, list[str]]:
        """Get sample rationales grouped by verdict for the report.

        Args:
            session: Active async DB session.
            review_id: Target review.
            company_id: Tenant scope.
            limit: Max rationales per verdict category.

        Returns:
            Dict mapping verdict to list of rationale strings.
        """
        run_ids_stmt = select(ScreeningRun.id).where(
            ScreeningRun.review_id == review_id,
            ScreeningRun.company_id == company_id,
        )

        summaries: dict[str, list[str]] = {
            "include": [],
            "exclude": [],
            "uncertain": [],
        }

        for verdict in ("include", "exclude", "uncertain"):
            stmt = (
                select(ScreeningDecision.rationale)
                .where(
                    ScreeningDecision.screening_run_id.in_(run_ids_stmt),
                    ScreeningDecision.company_id == company_id,
                    ScreeningDecision.verdict == verdict,
                )
                .limit(limit)
            )
            result = await session.execute(stmt)
            rationales = [row[0] for row in result.all() if row[0]]
            summaries[verdict] = rationales

        return summaries

    def _review_to_dict(self, review: SLRReview) -> dict[str, Any]:
        """Convert an SLRReview ORM instance to a plain dict.

        Args:
            review: ORM instance to serialize.

        Returns:
            Dict representation suitable for API responses.
        """
        return {
            "id": review.id,
            "company_id": review.company_id,
            "protocol_id": review.protocol_id,
            "name": review.name,
            "description": review.description,
            "status": review.status,
            "record_filter": review.record_filter,
            "created_by": review.created_by,
            "completed_by": review.completed_by,
            "records_identified": review.records_identified,
            "created_at": (
                review.created_at.isoformat() if review.created_at else None
            ),
            "updated_at": (
                review.updated_at.isoformat() if review.updated_at else None
            ),
            "completed_at": (
                review.completed_at.isoformat() if review.completed_at else None
            ),
        }

    def _decision_to_dict(self, decision: ScreeningDecision) -> dict[str, Any]:
        """Convert a ScreeningDecision ORM instance to a plain dict.

        Args:
            decision: ORM instance to serialize.

        Returns:
            Dict representation suitable for API responses.
        """
        return {
            "id": decision.id,
            "screening_run_id": decision.screening_run_id,
            "ingestion_record_id": decision.ingestion_record_id,
            "protocol_id": decision.protocol_id,
            "company_id": decision.company_id,
            "verdict": decision.verdict,
            "confidence": decision.confidence,
            "rationale": decision.rationale,
            "matched_inclusion_criteria": decision.matched_inclusion_criteria,
            "matched_exclusion_criteria": decision.matched_exclusion_criteria,
            "screening_duration_ms": decision.screening_duration_ms,
            "human_verdict": decision.human_verdict,
            "human_rationale": decision.human_rationale,
            "human_reviewer_id": decision.human_reviewer_id,
            "human_override_at": (
                decision.human_override_at.isoformat()
                if decision.human_override_at
                else None
            ),
            "created_at": (
                decision.created_at.isoformat() if decision.created_at else None
            ),
        }
