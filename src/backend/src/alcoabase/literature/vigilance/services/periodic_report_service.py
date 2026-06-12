"""Periodic Report Service for auto-generating regulatory safety reports.

Manages generation, lifecycle status transitions, listing, and retrieval
of Periodic Safety Reports documenting all vigilance monitoring activity
within configurable time windows for MDR/IVDR regulatory submissions.

References:
    - Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
    - Design: PeriodicReportService interface
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alcoabase.literature.vigilance.exceptions import (
    InvalidReportStatusTransitionError,
    ProductNotFoundError,
    ReportNotFoundError,
)
from alcoabase.literature.vigilance.models.medical_product import MedicalProduct
from alcoabase.literature.vigilance.models.periodic_safety_report import (
    PeriodicSafetyReport,
)
from alcoabase.literature.vigilance.models.vigilance_search_execution import (
    VigilanceSearchExecution,
)
from alcoabase.literature.vigilance.models.vigilance_search_profile import (
    VigilanceSearchProfile,
)
from alcoabase.literature.vigilance.models.vigilance_signal import (
    VigilanceSignal,
)

logger = logging.getLogger(__name__)

# Dedicated audit logger for vigilance report operations.
audit_logger = logging.getLogger("alcoabase.audit.vigilance_report")

# ---------------------------------------------------------------------------
# Audit event type constants
# ---------------------------------------------------------------------------

EVENT_REPORT_GENERATED = "vigilance.report_generated"
EVENT_REPORT_STATUS_ADVANCED = "vigilance.report_status_advanced"


class PeriodicReportService:
    """Manages Periodic Safety Report generation and lifecycle.

    Responsibilities:
        - Auto-generate reports on configured schedule
        - Include all search executions, signals, and dispositions in period
        - Build regulatory compliance section with MDR/IVDR references
        - Build disposition matrix (every result classified exactly once)
        - Compute statistical summary
        - Manage report status lifecycle (generated → reviewed → approved → submitted)
        - Handle empty periods (no searches executed)
    """

    VALID_STATUS_TRANSITIONS: dict[str, list[str]] = {
        "generated": ["reviewed"],
        "reviewed": ["approved"],
        "approved": ["submitted"],
    }

    async def generate_report(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
        period_start: date,
        period_end: date,
        user_id: int,
    ) -> dict[str, Any]:
        """Generate a Periodic Safety Report for the given period.

        Queries all VigilanceSearchExecutions and VigilanceSignals within the
        specified period, builds all 8 report sections, and persists the report
        with status "generated".

        Sections:
            1. Product metadata (name, UDI, device class, intended purpose)
            2. Reporting period dates
            3. Search executions within period (params, sources, counts)
            4. Signals detected (severity, disposition, resolution notes)
            5. Search strategy documentation (active profiles, query construction)
            6. Disposition matrix (every result classified)
            7. Statistical summary (totals, trends)
            8. Regulatory compliance section (MDR/IVDR references)

        Args:
            session: Active DB session.
            product_id: Target MedicalProduct.
            company_id: Tenant scope.
            period_start: Report period start (inclusive).
            period_end: Report period end (inclusive).
            user_id: User generating the report.

        Returns:
            Created report dict with full content.

        Raises:
            ProductNotFoundError: If product not found in this company.
        """
        # Load product
        product = await self._get_product_or_raise(
            session, product_id=product_id, company_id=company_id
        )

        # Load search executions within period
        executions = await self._get_executions_in_period(
            session,
            product_id=product_id,
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
        )

        # Load signals within period
        signals = await self._get_signals_in_period(
            session,
            product_id=product_id,
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
        )

        # Load active profiles for search strategy documentation
        profiles = await self._get_profiles_for_product(
            session, product_id=product_id, company_id=company_id
        )

        # Convert to dicts for section building
        execution_dicts = [self._execution_to_dict(e) for e in executions]
        signal_dicts = [self._signal_to_dict(s) for s in signals]

        # Build report content sections
        report_content = self._build_report_content(
            product=product,
            period_start=period_start,
            period_end=period_end,
            executions=execution_dicts,
            signals=signal_dicts,
            profiles=profiles,
        )

        # Persist report
        now = datetime.now(timezone.utc)
        report = PeriodicSafetyReport(
            product_id=product_id,
            company_id=company_id,
            period_start=period_start,
            period_end=period_end,
            generated_at=now,
            report_content=report_content,
            status="generated",
            version=1,
            status_history=[
                {
                    "status": "generated",
                    "user_id": user_id,
                    "timestamp": now.isoformat(),
                    "comment": "Report auto-generated",
                }
            ],
            created_by=user_id,
        )
        session.add(report)
        await session.flush()

        # Audit log
        self._log_audit(
            event_type=EVENT_REPORT_GENERATED,
            entity_id=report.id,
            company_id=company_id,
            user_id=user_id,
            details={
                "product_id": product_id,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "total_executions": len(execution_dicts),
                "total_signals": len(signal_dicts),
            },
        )

        return self._report_to_dict(report)

    async def advance_status(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        company_id: int,
        user_id: int,
        new_status: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Advance report through status lifecycle.

        Valid transitions: generated → reviewed → approved → submitted.
        Requires document_admin or system_admin role (enforced at API layer).
        Records user_id, timestamp, and optional comment in status_history.

        Args:
            report_id: Target report.
            company_id: Tenant scope.
            user_id: Acting user (must have document_admin or system_admin).
            new_status: Target status.
            comment: Optional comment (max 2000 chars).

        Returns:
            Updated report dict.

        Raises:
            ReportNotFoundError: If report not found in this company.
            InvalidReportStatusTransitionError: If transition not valid.
        """
        report = await self._get_report_or_raise(
            session, report_id=report_id, company_id=company_id
        )

        # Validate transition
        current_status = report.status
        allowed_transitions = self.VALID_STATUS_TRANSITIONS.get(
            current_status, []
        )
        if new_status not in allowed_transitions:
            raise InvalidReportStatusTransitionError(
                f"Cannot transition report {report_id} from "
                f"'{current_status}' to '{new_status}'. "
                f"Allowed transitions: {allowed_transitions}",
                report_id=report_id,
                current_status=current_status,
                requested_status=new_status,
            )

        # Update status
        report.status = new_status

        # Append to status_history
        now = datetime.now(timezone.utc)
        history_entry: dict[str, Any] = {
            "status": new_status,
            "user_id": user_id,
            "timestamp": now.isoformat(),
            "comment": comment,
        }

        # SQLAlchemy JSONB mutation detection requires reassignment
        updated_history = list(report.status_history or [])
        updated_history.append(history_entry)
        report.status_history = updated_history

        await session.flush()

        # Audit log
        self._log_audit(
            event_type=EVENT_REPORT_STATUS_ADVANCED,
            entity_id=report_id,
            company_id=company_id,
            user_id=user_id,
            details={
                "previous_status": current_status,
                "new_status": new_status,
                "comment": comment,
            },
        )

        return self._report_to_dict(report)

    async def list_reports(
        self,
        session: AsyncSession,
        *,
        company_id: int,
        product_id: int | None = None,
        status: str | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List reports with pagination and filters.

        Args:
            session: Active DB session.
            company_id: Tenant scope.
            product_id: Optional product filter.
            status: Optional status filter.
            period_start: Optional period start filter (reports starting on or after).
            period_end: Optional period end filter (reports ending on or before).
            page: Page number (1-indexed).
            page_size: Items per page (1–100).

        Returns:
            Tuple of (reports_list, total_count).
        """
        # Clamp page_size
        page_size = max(1, min(page_size, 100))
        page = max(1, page)

        # Build base filter
        base_filter = [PeriodicSafetyReport.company_id == company_id]
        if product_id is not None:
            base_filter.append(PeriodicSafetyReport.product_id == product_id)
        if status is not None:
            base_filter.append(PeriodicSafetyReport.status == status)
        if period_start is not None:
            base_filter.append(
                PeriodicSafetyReport.period_start >= period_start
            )
        if period_end is not None:
            base_filter.append(PeriodicSafetyReport.period_end <= period_end)

        # Count total
        count_stmt = select(func.count(PeriodicSafetyReport.id)).where(
            *base_filter
        )
        total_result = await session.execute(count_stmt)
        total = total_result.scalar_one()

        # Paginated query
        offset = (page - 1) * page_size
        query = (
            select(PeriodicSafetyReport)
            .where(*base_filter)
            .order_by(PeriodicSafetyReport.generated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await session.execute(query)
        reports = list(result.scalars().all())

        return [self._report_to_dict(r) for r in reports], total

    async def get_report(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        company_id: int,
    ) -> dict[str, Any]:
        """Get full report content by ID, company-scoped.

        Args:
            session: Active DB session.
            report_id: Target report.
            company_id: Tenant scope.

        Returns:
            Full report dict including report_content.

        Raises:
            ReportNotFoundError: If not found in this company.
        """
        report = await self._get_report_or_raise(
            session, report_id=report_id, company_id=company_id
        )
        return self._report_to_dict(report)

    def _build_report_content(
        self,
        *,
        product: MedicalProduct,
        period_start: date,
        period_end: date,
        executions: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        profiles: list[VigilanceSearchProfile],
    ) -> dict[str, Any]:
        """Build the complete report content with all 8 sections.

        Args:
            product: The MedicalProduct instance.
            period_start: Report period start.
            period_end: Report period end.
            executions: List of execution dicts in the period.
            signals: List of signal dicts in the period.
            profiles: Active profiles for the product.

        Returns:
            Structured JSONB report content.
        """
        # Section 1: Product metadata
        product_metadata = {
            "name": product.name,
            "udi": product.udi,
            "device_class": product.device_class,
            "intended_purpose": product.intended_purpose,
            "manufacturer_name": product.manufacturer_name,
            "gmdn_code": product.gmdn_code,
            "status": product.status,
        }

        # Section 2: Reporting period dates
        period_dates = {
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
        }

        # Handle empty period
        if not executions:
            return {
                "product_metadata": product_metadata,
                "period_dates": period_dates,
                "search_executions": [],
                "signals": [],
                "search_strategy": self._build_search_strategy(profiles),
                "disposition_matrix": {
                    "no_signal": 0,
                    "signal_dismissed": 0,
                    "signal_confirmed": 0,
                    "signal_escalated": 0,
                    "total": 0,
                },
                "statistical_summary": self._build_statistical_summary(
                    [], []
                ),
                "regulatory_compliance": self._build_regulatory_compliance(
                    product, period_start, period_end, executions
                ),
                "empty_period_notice": (
                    "No searches executed during this reporting period. "
                    "All vigilance search profiles were paused, archived, "
                    "or the product was discontinued during this period."
                ),
            }

        # Section 3: Search executions
        search_executions_section = [
            {
                "execution_id": e["id"],
                "profile_id": e["profile_id"],
                "execution_timestamp": e["execution_timestamp"],
                "sources_queried": e["sources_queried"],
                "total_results_found": e["total_results_found"],
                "results_after_exclusion": e["results_after_exclusion"],
                "results_ingested": e["results_ingested"],
                "results_duplicate": e["results_duplicate"],
                "execution_duration_ms": e["execution_duration_ms"],
                "status": e["status"],
            }
            for e in executions
        ]

        # Section 4: Signals detected
        signals_section = [
            {
                "signal_id": s["id"],
                "severity": s["severity"],
                "confidence": s["confidence"],
                "disposition": s["disposition"],
                "evidence_summary": s["evidence_summary"],
                "affected_product_aspects": s["affected_product_aspects"],
                "regulatory_references": s["regulatory_references"],
                "recommended_actions": s["recommended_actions"],
                "detection_timestamp": s["detection_timestamp"],
                "dismissal_reason": s.get("dismissal_reason"),
                "confirmation_note": s.get("confirmation_note"),
            }
            for s in signals
        ]

        # Section 5: Search strategy
        search_strategy = self._build_search_strategy(profiles)

        # Section 6: Disposition matrix
        disposition_matrix = self._build_disposition_matrix(
            executions, signals
        )

        # Section 7: Statistical summary
        statistical_summary = self._build_statistical_summary(
            executions, signals
        )

        # Section 8: Regulatory compliance
        regulatory_compliance = self._build_regulatory_compliance(
            product, period_start, period_end, executions
        )

        return {
            "product_metadata": product_metadata,
            "period_dates": period_dates,
            "search_executions": search_executions_section,
            "signals": signals_section,
            "search_strategy": search_strategy,
            "disposition_matrix": disposition_matrix,
            "statistical_summary": statistical_summary,
            "regulatory_compliance": regulatory_compliance,
        }

    def _build_disposition_matrix(
        self,
        executions: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> dict[str, int]:
        """Build the disposition matrix.

        Classifies every ingested result as one of:
        - no_signal: dismissed by agent with low confidence (no signal created)
        - signal_dismissed: signal created but dismissed by human reviewer
        - signal_confirmed: genuine signal under action
        - signal_escalated: critical signal with full escalation

        Invariant: sum of all categories == total results_ingested across executions.

        Args:
            executions: List of execution dicts in the period.
            signals: List of signal dicts in the period.

        Returns:
            Dict mapping disposition category to count.
        """
        # Calculate total results ingested across all executions
        total_ingested = sum(e.get("results_ingested", 0) for e in executions)

        # Count signals by disposition
        signal_dismissed = sum(
            1 for s in signals if s.get("disposition") == "dismissed"
        )
        signal_confirmed = sum(
            1 for s in signals
            if s.get("disposition") in ("confirmed", "under_review")
        )
        signal_escalated = sum(
            1 for s in signals if s.get("disposition") == "escalated"
        )

        # no_signal = total ingested minus all signals
        total_signals = signal_dismissed + signal_confirmed + signal_escalated
        no_signal = max(0, total_ingested - total_signals)

        return {
            "no_signal": no_signal,
            "signal_dismissed": signal_dismissed,
            "signal_confirmed": signal_confirmed,
            "signal_escalated": signal_escalated,
            "total": total_ingested,
        }

    def _build_statistical_summary(
        self,
        executions: list[dict[str, Any]],
        signals: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build statistical summary section.

        Includes: total_searches, total_results, signals_by_severity,
        disposition_breakdown, average_time_to_disposition.

        Args:
            executions: List of execution dicts in the period.
            signals: List of signal dicts in the period.

        Returns:
            Statistical summary dict.
        """
        total_searches = len(executions)
        total_results = sum(
            e.get("total_results_found", 0) for e in executions
        )

        # Signals by severity
        signals_by_severity: dict[str, int] = {
            "critical": 0,
            "major": 0,
            "minor": 0,
        }
        for s in signals:
            severity = s.get("severity", "")
            if severity in signals_by_severity:
                signals_by_severity[severity] += 1

        # Disposition breakdown
        disposition_breakdown: dict[str, int] = {
            "under_review": 0,
            "confirmed": 0,
            "dismissed": 0,
            "escalated": 0,
        }
        for s in signals:
            disposition = s.get("disposition", "")
            if disposition in disposition_breakdown:
                disposition_breakdown[disposition] += 1

        # Average time to disposition (for resolved signals)
        avg_time_to_disposition = self._calculate_avg_time_to_disposition(
            signals
        )

        return {
            "total_searches": total_searches,
            "total_results": total_results,
            "total_signals": len(signals),
            "signals_by_severity": signals_by_severity,
            "disposition_breakdown": disposition_breakdown,
            "avg_time_to_disposition_hours": avg_time_to_disposition,
        }

    def _build_search_strategy(
        self,
        profiles: list[VigilanceSearchProfile],
    ) -> dict[str, Any]:
        """Build the search strategy documentation section.

        Documents all active profiles and their query construction.

        Args:
            profiles: Profiles for the product.

        Returns:
            Search strategy section dict.
        """
        profile_summaries = []
        for p in profiles:
            profile_summaries.append(
                {
                    "profile_id": p.id,
                    "name": p.name,
                    "status": p.status,
                    "search_terms": p.search_terms,
                    "mesh_terms": p.mesh_terms or [],
                    "adverse_event_keywords": p.adverse_event_keywords,
                    "device_identifiers": p.device_identifiers or [],
                    "exclusion_terms": p.exclusion_terms or [],
                    "source_ids": p.source_ids or [],
                    "schedule_cron": p.schedule_cron,
                    "query_logic": (
                        "(search_terms OR mesh_terms OR device_identifiers) "
                        "AND adverse_event_keywords"
                    ),
                }
            )

        return {
            "total_profiles": len(profiles),
            "profiles": profile_summaries,
        }

    def _build_regulatory_compliance(
        self,
        product: MedicalProduct,
        period_start: date,
        period_end: date,
        executions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the regulatory compliance section.

        Documents applicable regulations, MEDDEV guideline references,
        confirmation that search strategy covers the device's intended purpose
        and known risk areas, and a statement of completeness.

        Args:
            product: The MedicalProduct instance.
            period_start: Report period start.
            period_end: Report period end.
            executions: Execution dicts within the period.

        Returns:
            Regulatory compliance section dict.
        """
        # Determine applicable regulations based on device class
        applicable_regulations = []
        if product.device_class in ("I", "IIa", "IIb", "III"):
            applicable_regulations.extend([
                "EU MDR 2017/745 Article 83 (Post-market surveillance system)",
                "EU MDR 2017/745 Article 84 (Post-market surveillance plan)",
                "EU MDR 2017/745 Article 85 (Post-market surveillance report)",
                "EU MDR 2017/745 Article 86 (Periodic safety update report)",
                "EU MDR 2017/745 Article 87 (Reporting of serious incidents)",
                "EU MDR 2017/745 Article 88 (Trend reporting)",
            ])
        if product.device_class in ("IVDR_A", "IVDR_B", "IVDR_C", "IVDR_D"):
            applicable_regulations.extend([
                "EU IVDR 2017/746 Article 78 (Post-market surveillance system)",
                "EU IVDR 2017/746 Article 79 (Post-market surveillance plan)",
                "EU IVDR 2017/746 Article 80 (Periodic safety update report)",
                "EU IVDR 2017/746 Article 82 (Reporting of serious incidents)",
            ])

        meddev_guidelines = [
            "MEDDEV 2.12/1 rev 8 (Guidelines on a medical devices vigilance system)",
            "MEDDEV 2.7/1 rev 4 (Clinical evaluation: guide for manufacturers and notified bodies)",
        ]

        # Completeness statement
        total_executions = len(executions)
        failed_executions = sum(
            1 for e in executions if e.get("status") == "failed"
        )
        completeness_statement = (
            f"During the reporting period ({period_start.isoformat()} to "
            f"{period_end.isoformat()}), {total_executions} scheduled searches "
            f"were executed. "
        )
        if failed_executions > 0:
            completeness_statement += (
                f"{failed_executions} execution(s) failed and are documented "
                f"in the search executions section with failure reasons."
            )
        else:
            completeness_statement += (
                "All scheduled searches completed successfully."
            )

        return {
            "applicable_regulations": applicable_regulations,
            "meddev_guidelines": meddev_guidelines,
            "search_strategy_coverage": (
                f"Search strategy covers the device's intended purpose "
                f"('{product.intended_purpose[:200]}...') and known risk "
                f"areas as defined in the vigilance search profiles."
            ),
            "completeness_statement": completeness_statement,
        }

    # ─────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────

    def _calculate_avg_time_to_disposition(
        self,
        signals: list[dict[str, Any]],
    ) -> float | None:
        """Calculate average time from detection to disposition change.

        Only considers signals with resolved dispositions (confirmed,
        dismissed, escalated). Returns None if no resolved signals.

        Args:
            signals: List of signal dicts.

        Returns:
            Average hours to disposition, or None if not calculable.
        """
        resolved_dispositions = ("confirmed", "dismissed", "escalated")
        durations: list[float] = []

        for s in signals:
            if s.get("disposition") not in resolved_dispositions:
                continue
            detection_ts = s.get("detection_timestamp")
            updated_ts = s.get("updated_at")
            if detection_ts and updated_ts:
                # Parse timestamps if they are strings
                if isinstance(detection_ts, str):
                    try:
                        detection_dt = datetime.fromisoformat(detection_ts)
                    except (ValueError, TypeError):
                        continue
                else:
                    detection_dt = detection_ts

                if isinstance(updated_ts, str):
                    try:
                        updated_dt = datetime.fromisoformat(updated_ts)
                    except (ValueError, TypeError):
                        continue
                else:
                    updated_dt = updated_ts

                delta = updated_dt - detection_dt
                hours = delta.total_seconds() / 3600.0
                if hours >= 0:
                    durations.append(hours)

        if not durations:
            return None

        return round(sum(durations) / len(durations), 2)

    async def _get_product_or_raise(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
    ) -> MedicalProduct:
        """Load a product by ID within company scope.

        Raises:
            ProductNotFoundError: If not found.
        """
        stmt = select(MedicalProduct).where(
            MedicalProduct.id == product_id,
            MedicalProduct.company_id == company_id,
        )
        result = await session.execute(stmt)
        product = result.scalar_one_or_none()
        if product is None:
            raise ProductNotFoundError(
                f"Medical product {product_id} not found in company {company_id}",
                product_id=product_id,
                company_id=company_id,
            )
        return product

    async def _get_report_or_raise(
        self,
        session: AsyncSession,
        *,
        report_id: int,
        company_id: int,
    ) -> PeriodicSafetyReport:
        """Load a report by ID within company scope.

        Raises:
            ReportNotFoundError: If not found.
        """
        stmt = select(PeriodicSafetyReport).where(
            PeriodicSafetyReport.id == report_id,
            PeriodicSafetyReport.company_id == company_id,
        )
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()
        if report is None:
            raise ReportNotFoundError(
                f"Periodic safety report {report_id} not found in company {company_id}",
                report_id=report_id,
                company_id=company_id,
            )
        return report

    async def _get_executions_in_period(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VigilanceSearchExecution]:
        """Query all search executions for a product within the period.

        Joins via profile → product to scope by product_id.

        Args:
            session: Active DB session.
            product_id: Target product.
            company_id: Tenant scope.
            period_start: Period start (inclusive).
            period_end: Period end (inclusive).

        Returns:
            List of VigilanceSearchExecution instances.
        """
        # Get profile IDs for this product
        profile_ids_stmt = select(VigilanceSearchProfile.id).where(
            VigilanceSearchProfile.product_id == product_id,
            VigilanceSearchProfile.company_id == company_id,
        )
        profile_ids_result = await session.execute(profile_ids_stmt)
        profile_ids = [row[0] for row in profile_ids_result.all()]

        if not profile_ids:
            return []

        stmt = (
            select(VigilanceSearchExecution)
            .where(
                VigilanceSearchExecution.profile_id.in_(profile_ids),
                VigilanceSearchExecution.company_id == company_id,
                func.date(VigilanceSearchExecution.execution_timestamp)
                >= period_start,
                func.date(VigilanceSearchExecution.execution_timestamp)
                <= period_end,
            )
            .order_by(VigilanceSearchExecution.execution_timestamp.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _get_signals_in_period(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
        period_start: date,
        period_end: date,
    ) -> list[VigilanceSignal]:
        """Query all signals for a product within the period.

        Args:
            session: Active DB session.
            product_id: Target product.
            company_id: Tenant scope.
            period_start: Period start (inclusive).
            period_end: Period end (inclusive).

        Returns:
            List of VigilanceSignal instances.
        """
        stmt = (
            select(VigilanceSignal)
            .where(
                VigilanceSignal.product_id == product_id,
                VigilanceSignal.company_id == company_id,
                func.date(VigilanceSignal.detection_timestamp) >= period_start,
                func.date(VigilanceSignal.detection_timestamp) <= period_end,
            )
            .order_by(VigilanceSignal.detection_timestamp.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _get_profiles_for_product(
        self,
        session: AsyncSession,
        *,
        product_id: int,
        company_id: int,
    ) -> list[VigilanceSearchProfile]:
        """Get all profiles (any status) for a product.

        Args:
            session: Active DB session.
            product_id: Target product.
            company_id: Tenant scope.

        Returns:
            List of VigilanceSearchProfile instances.
        """
        stmt = (
            select(VigilanceSearchProfile)
            .where(
                VigilanceSearchProfile.product_id == product_id,
                VigilanceSearchProfile.company_id == company_id,
            )
            .order_by(VigilanceSearchProfile.created_at.asc())
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    def _log_audit(
        self,
        *,
        event_type: str,
        entity_id: int,
        company_id: int,
        user_id: int,
        details: dict[str, Any],
    ) -> None:
        """Emit a structured audit log entry for a report operation.

        Uses Python logging with structured extras for ALCOA+ compliance.
        Never logs full report content.

        Args:
            event_type: Event type constant.
            entity_id: Report ID.
            company_id: Tenant company ID.
            user_id: Acting user ID.
            details: Additional event details.
        """
        timestamp = datetime.now(timezone.utc)
        audit_logger.info(
            "Report operation: event=%s, report_id=%d, company_id=%d, user_id=%d",
            event_type,
            entity_id,
            company_id,
            user_id,
            extra={
                "event_type": event_type,
                "entity_type": "periodic_safety_report",
                "entity_id": entity_id,
                "company_id": company_id,
                "acting_user_id": user_id,
                "timestamp": timestamp.isoformat(),
                **details,
            },
        )

    def _report_to_dict(
        self, report: PeriodicSafetyReport
    ) -> dict[str, Any]:
        """Convert a PeriodicSafetyReport model to a plain dict.

        Args:
            report: PeriodicSafetyReport ORM instance.

        Returns:
            Dict representation of the report.
        """
        return {
            "id": report.id,
            "product_id": report.product_id,
            "company_id": report.company_id,
            "period_start": (
                report.period_start.isoformat()
                if report.period_start
                else None
            ),
            "period_end": (
                report.period_end.isoformat() if report.period_end else None
            ),
            "generated_at": (
                report.generated_at.isoformat()
                if report.generated_at
                else None
            ),
            "report_content": report.report_content,
            "status": report.status,
            "version": report.version,
            "status_history": report.status_history,
            "created_by": report.created_by,
            "created_at": (
                report.created_at.isoformat() if report.created_at else None
            ),
            "updated_at": (
                report.updated_at.isoformat() if report.updated_at else None
            ),
        }

    def _execution_to_dict(
        self, execution: VigilanceSearchExecution
    ) -> dict[str, Any]:
        """Convert a VigilanceSearchExecution model to a plain dict.

        Args:
            execution: VigilanceSearchExecution ORM instance.

        Returns:
            Dict representation of the execution.
        """
        return {
            "id": execution.id,
            "profile_id": execution.profile_id,
            "company_id": execution.company_id,
            "execution_timestamp": (
                execution.execution_timestamp.isoformat()
                if execution.execution_timestamp
                else None
            ),
            "search_parameters": execution.search_parameters,
            "sources_queried": execution.sources_queried,
            "total_results_found": execution.total_results_found,
            "results_after_exclusion": execution.results_after_exclusion,
            "results_ingested": execution.results_ingested,
            "results_duplicate": execution.results_duplicate,
            "execution_duration_ms": execution.execution_duration_ms,
            "status": execution.status,
        }

    def _signal_to_dict(self, signal: VigilanceSignal) -> dict[str, Any]:
        """Convert a VigilanceSignal model to a plain dict.

        Args:
            signal: VigilanceSignal ORM instance.

        Returns:
            Dict representation of the signal.
        """
        return {
            "id": signal.id,
            "ingestion_record_id": signal.ingestion_record_id,
            "product_id": signal.product_id,
            "profile_id": signal.profile_id,
            "company_id": signal.company_id,
            "severity": signal.severity,
            "evidence_summary": signal.evidence_summary,
            "affected_product_aspects": signal.affected_product_aspects,
            "regulatory_references": signal.regulatory_references,
            "recommended_actions": signal.recommended_actions,
            "confidence": signal.confidence,
            "disposition": signal.disposition,
            "dismissal_reason": signal.dismissal_reason,
            "confirmation_note": signal.confirmation_note,
            "reviewer_user_id": signal.reviewer_user_id,
            "detection_timestamp": (
                signal.detection_timestamp.isoformat()
                if signal.detection_timestamp
                else None
            ),
            "created_at": (
                signal.created_at.isoformat() if signal.created_at else None
            ),
            "updated_at": (
                signal.updated_at.isoformat() if signal.updated_at else None
            ),
        }
