"""Celery tasks for multi-agent review pipeline execution.

Implements the async task layer for the review pipeline:
- execute_agent_review: Individual agent review with LLM inference
- execute_master_summary: Master Auditor synthesis of all agent reports
- check_review_completion: Quorum checking and pipeline progression
- scan_anomalies_periodic: Periodic anomaly detection across all active companies

These tasks run in Celery workers and use synchronous DB access via
asyncio.run() since Celery workers are synchronous.

References:
    - Requirements 1.4–1.7: Pipeline orchestration and quorum
    - Requirements 2.1–2.7: Individual agent review execution
    - Requirements 3.1–3.8: Master Auditor summarization
    - Requirement 8.1: Anomaly detection periodic task (every 15 minutes)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from celery.utils.log import get_task_logger

from alcoabase.tasks.celery_app import celery_app

logger = get_task_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: Sync DB session creation
# ---------------------------------------------------------------------------


def _get_async_session_factory():
    """Get the async session factory for DB access in Celery tasks.

    Creates a standalone async engine and session factory since Celery
    workers don't share the FastAPI application's DB lifecycle.

    Returns:
        async_sessionmaker bound to a fresh async engine.
    """
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from alcoabase.config import get_settings

    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


def _get_inference_client():
    """Get or create the InferenceClient for Celery workers.

    Returns:
        InferenceClient instance configured from settings.
    """
    from alcoabase.services.service_factory import get_inference_client

    return get_inference_client()


def _get_storage_service():
    """Get a StorageService instance for Celery workers.

    Returns:
        StorageService instance.
    """
    from alcoabase.services.storage_service import StorageService

    return StorageService()


# ---------------------------------------------------------------------------
# Task: execute_agent_review
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, max_retries=0, time_limit=1800)
def execute_agent_review(
    self,
    session_id: int,
    agent_review_id: int,
    agent_id: int,
) -> dict[str, Any]:
    """Execute a single agent review via LLM inference.

    Retrieves the document content from MinIO, gets the agent's tuning
    parameters, constructs a review prompt, calls InferenceClient, parses
    the response into a ReviewReport, and persists the result.

    On failure: marks the AgentReview as Failed with error_reason and
    triggers check_review_completion.

    Args:
        self: Celery task instance (bound).
        session_id: The parent ReviewSession ID.
        agent_review_id: The AgentReview record ID to update.
        agent_id: The AgentDefinition ID for tuning parameters.

    Returns:
        Dict with review results (status, duration_ms).
    """
    try:
        result = asyncio.run(
            _execute_agent_review_async(
                session_id=session_id,
                agent_review_id=agent_review_id,
                agent_id=agent_id,
            )
        )
        return result
    except Exception as exc:
        logger.error(
            "Agent review task failed for agent_review_id=%d: %s",
            agent_review_id,
            exc,
        )
        # Mark as failed and trigger completion check
        asyncio.run(
            _mark_agent_review_failed(
                agent_review_id=agent_review_id,
                session_id=session_id,
                error_reason=str(exc)[:500],
            )
        )
        check_review_completion.delay(session_id=session_id)
        return {
            "status": "Failed",
            "agent_review_id": agent_review_id,
            "error": str(exc)[:500],
        }


async def _execute_agent_review_async(
    session_id: int,
    agent_review_id: int,
    agent_id: int,
) -> dict[str, Any]:
    """Async implementation of the agent review execution.

    Args:
        session_id: The parent ReviewSession ID.
        agent_review_id: The AgentReview record ID.
        agent_id: The AgentDefinition ID.

    Returns:
        Dict with review results.
    """
    from sqlalchemy import select

    from alcoabase.config import get_settings
    from alcoabase.models.agent import AgentDefinition
    from alcoabase.models.document import DocumentVersion
    from alcoabase.models.review import AgentReview, ReviewSession
    from alcoabase.services.inference_client import (
        InferenceConnectionError,
        InferenceError,
        InferenceTimeoutError,
    )

    settings = get_settings()
    session_factory = _get_async_session_factory()
    inference_client = _get_inference_client()
    storage_service = _get_storage_service()

    # 1. Mark agent review as InProgress and update session status
    async with session_factory() as db:
        agent_review = await db.get(AgentReview, agent_review_id)
        if agent_review is None:
            raise ValueError(f"AgentReview {agent_review_id} not found")

        agent_review.status = "InProgress"
        agent_review.started_at = datetime.now(UTC)

        # Transition session to InProgress if still Pending
        review_session = await db.get(ReviewSession, session_id)
        if review_session and review_session.status == "Pending":
            review_session.status = "InProgress"

        await db.commit()

    # 2. Get agent definition and tuning parameters
    async with session_factory() as db:
        agent_def = await db.get(AgentDefinition, agent_id)
        if agent_def is None:
            raise ValueError(f"AgentDefinition {agent_id} not found")

        agent_name = agent_def.name
        system_prompt = ""
        tuning_params: dict[str, Any] = {
            "temperature": 0.3,
            "max_tokens": 4096,
        }

        # Extract system_prompt from YAML content
        if agent_def.yaml_content:
            import yaml

            try:
                yaml_data = yaml.safe_load(agent_def.yaml_content)
                if isinstance(yaml_data, dict):
                    system_prompt = yaml_data.get("system_prompt", "")
                    # Append evaluation rubric if present
                    rubric = yaml_data.get("evaluation_rubric")
                    if rubric and isinstance(rubric, dict):
                        criteria = rubric.get("criteria", [])
                        if criteria:
                            rubric_text = "\n\nEvaluation Rubric:\n"
                            for c in criteria:
                                rubric_text += (
                                    f"- {c.get('name', '')}: "
                                    f"{c.get('description', '')}\n"
                                )
                            system_prompt += rubric_text
            except Exception:
                pass

        # Use contextual_tuning from DB if available (v2.0 agents)
        if agent_def.contextual_tuning:
            ct = agent_def.contextual_tuning
            tuning_params["temperature"] = ct.get("temperature", 0.3)
            tuning_params["max_tokens"] = ct.get("max_tokens", 4096)
            tuning_params["top_p"] = ct.get("top_p", 1.0)

    # 3. Retrieve document content from MinIO
    async with session_factory() as db:
        review_session = await db.get(ReviewSession, session_id)
        if review_session is None:
            raise ValueError(f"ReviewSession {session_id} not found")

        doc_version = await db.get(
            DocumentVersion, review_session.document_version_id
        )
        if doc_version is None:
            raise ValueError(
                f"DocumentVersion {review_session.document_version_id} not found"
            )
        storage_key = doc_version.storage_key

    # Download document content from MinIO
    file_bytes = await storage_service.download_file(storage_key)
    document_content = file_bytes.decode("utf-8", errors="replace")

    # 4. Construct review prompt
    review_instruction = (
        "Review the following document and produce a structured JSON response "
        "containing your findings. For each finding, include: severity "
        "(Critical, Major, Minor, or Informational), chapter/section reference, "
        "description, and recommendation.\n\n"
        "Respond in JSON format with this structure:\n"
        '{\n'
        '  "overall_status": "Pass|Pass with Findings|Fail",\n'
        '  "findings": [\n'
        '    {\n'
        '      "severity": "Critical|Major|Minor|Informational",\n'
        '      "chapter": "string",\n'
        '      "description": "string",\n'
        '      "recommendation": "string"\n'
        '    }\n'
        '  ],\n'
        '  "chapter_results": [\n'
        '    {\n'
        '      "chapter_name": "string",\n'
        '      "present": true,\n'
        '      "complete": true,\n'
        '      "notes": "string"\n'
        '    }\n'
        '  ],\n'
        '  "summary": "string"\n'
        '}\n\n'
        "Document content:\n"
        "---\n"
        f"{document_content}\n"
        "---"
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": review_instruction},
    ]

    # 5. Call InferenceClient
    start_time = time.monotonic()
    try:
        response_text = await inference_client.chat_completion(
            model=settings.model_chat_name,
            messages=messages,
            temperature=tuning_params.get("temperature", 0.3),
            max_tokens=tuning_params.get("max_tokens", 4096),
            timeout=1700.0,  # Leave margin within 1800s time_limit
        )
    except InferenceTimeoutError:
        raise RuntimeError("timeout")
    except InferenceConnectionError as e:
        raise RuntimeError(f"connection_error: {e}")
    except InferenceError as e:
        raise RuntimeError(f"inference_error: {e}")

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # 6. Parse response into ReviewReport structure
    report_data = _parse_review_response(response_text)
    if report_data is None:
        # Store raw response for debugging, mark as failed
        async with session_factory() as db:
            agent_review = await db.get(AgentReview, agent_review_id)
            if agent_review:
                agent_review.status = "Failed"
                agent_review.error_reason = "invalid_response"
                agent_review.report_data = {"raw_response": response_text[:5000]}
                agent_review.completed_at = datetime.now(UTC)
                agent_review.inference_duration_ms = elapsed_ms
                await db.commit()

        check_review_completion.delay(session_id=session_id)
        return {
            "status": "Failed",
            "agent_review_id": agent_review_id,
            "error": "invalid_response",
            "inference_duration_ms": elapsed_ms,
        }

    # 7. Persist completed review
    async with session_factory() as db:
        agent_review = await db.get(AgentReview, agent_review_id)
        if agent_review:
            agent_review.status = "Completed"
            agent_review.report_data = report_data
            agent_review.inference_duration_ms = elapsed_ms
            agent_review.completed_at = datetime.now(UTC)
            await db.commit()

    # 8. Trigger completion check
    check_review_completion.delay(session_id=session_id)

    logger.info(
        "Agent review completed: agent_review_id=%d, agent=%s, duration=%dms",
        agent_review_id,
        agent_name,
        elapsed_ms,
    )

    return {
        "status": "Completed",
        "agent_review_id": agent_review_id,
        "agent_name": agent_name,
        "inference_duration_ms": elapsed_ms,
    }


def _parse_review_response(response_text: str) -> dict[str, Any] | None:
    """Parse the LLM response into a structured ReviewReport dict.

    Attempts to extract JSON from the response text. Handles cases where
    the JSON is wrapped in markdown code blocks.

    Args:
        response_text: Raw text response from the LLM.

    Returns:
        Parsed report dict, or None if parsing fails.
    """
    text = response_text.strip()

    # Strip markdown code block wrappers if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None

    # Validate minimum required fields
    if not isinstance(data, dict):
        return None

    # Ensure findings is a list
    if "findings" not in data:
        data["findings"] = []

    if not isinstance(data.get("findings"), list):
        data["findings"] = []

    return data


async def _mark_agent_review_failed(
    agent_review_id: int,
    session_id: int,
    error_reason: str,
) -> None:
    """Mark an agent review as Failed in the database.

    Args:
        agent_review_id: The AgentReview record ID.
        session_id: The parent ReviewSession ID.
        error_reason: Reason for the failure.
    """
    from alcoabase.models.review import AgentReview

    session_factory = _get_async_session_factory()
    async with session_factory() as db:
        agent_review = await db.get(AgentReview, agent_review_id)
        if agent_review:
            agent_review.status = "Failed"
            agent_review.error_reason = error_reason
            agent_review.completed_at = datetime.now(UTC)
            await db.commit()


# ---------------------------------------------------------------------------
# Task: execute_master_summary
# ---------------------------------------------------------------------------


@celery_app.task(bind=True, max_retries=1)
def execute_master_summary(
    self,
    session_id: int,
    agent_reports: list[dict[str, Any]],
    company_id: int,
) -> dict[str, Any]:
    """Execute the Master Auditor summarization of all agent reports.

    Collects completed agent reports, constructs the Master Auditor prompt,
    calls InferenceClient, parses the response into a MasterReviewSummary,
    computes the compliance score, and persists the result.

    Args:
        self: Celery task instance (bound).
        session_id: The parent ReviewSession ID.
        agent_reports: List of completed agent report dicts.
        company_id: Company ID for context.

    Returns:
        Dict with summary results (status, compliance_score).
    """
    try:
        result = asyncio.run(
            _execute_master_summary_async(
                session_id=session_id,
                agent_reports=agent_reports,
                company_id=company_id,
            )
        )
        return result
    except Exception as exc:
        logger.error(
            "Master summary task failed for session_id=%d: %s",
            session_id,
            exc,
        )
        # Mark session as completed with summary_failed flag
        asyncio.run(
            _mark_session_summary_failed(session_id=session_id)
        )
        return {
            "status": "Failed",
            "session_id": session_id,
            "error": str(exc)[:500],
        }


async def _execute_master_summary_async(
    session_id: int,
    agent_reports: list[dict[str, Any]],
    company_id: int,
) -> dict[str, Any]:
    """Async implementation of the master summary execution.

    Args:
        session_id: The parent ReviewSession ID.
        agent_reports: List of completed agent report dicts.
        company_id: Company ID for context.

    Returns:
        Dict with summary results.
    """
    from alcoabase.config import get_settings
    from alcoabase.models.review import MasterReviewSummary, ReviewSession
    from alcoabase.services.compliance_scorecard import (
        classify_risk_band,
        compute_compliance_score,
    )

    settings = get_settings()
    session_factory = _get_async_session_factory()
    inference_client = _get_inference_client()

    # 1. Load the Master Auditor archetype system prompt
    master_system_prompt = _get_master_auditor_system_prompt()

    # 2. Construct the user prompt with all agent reports
    reports_json = json.dumps(agent_reports, indent=2, default=str)

    user_prompt = (
        f"You are synthesizing {len(agent_reports)} individual review reports "
        f"into a unified executive summary.\n\n"
        f"## Individual Agent Reports:\n"
        f"{reports_json}\n\n"
        f"## Instructions:\n"
        f"1. Identify CONSENSUS findings (same chapter + same/similar severity "
        f"in 2+ reports)\n"
        f"2. Identify CONTRADICTIONS (one agent flags Critical/Major, another "
        f"finds nothing)\n"
        f"3. Produce PRIORITIZED action items (Critical first, then Major, "
        f"then by frequency)\n"
        f"4. Compute compliance score using formula: "
        f"100 - Σ(severity_weight × count)\n"
        f"   Weights: Critical=25, Major=10, Minor=3, Informational=0.5\n"
        f"5. Assign risk assessment: Critical (0-24), At Risk (25-49), "
        f"Needs Attention (50-74), Good (75-89), Excellent (90-100)\n\n"
        f"Respond in JSON format as specified in your system prompt."
    )

    messages = [
        {"role": "system", "content": master_system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 3. Call InferenceClient with Master Auditor tuning
    start_time = time.monotonic()
    response_text = await inference_client.chat_completion(
        model=settings.model_chat_name,
        messages=messages,
        temperature=0.1,
        max_tokens=8192,
        timeout=300.0,
    )
    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # 4. Parse the response
    summary_data = _parse_review_response(response_text)
    if summary_data is None:
        raise ValueError("Failed to parse Master Auditor response as JSON")

    # 5. Compute compliance score from findings
    finding_counts = _count_findings_from_reports(agent_reports)
    compliance_score = compute_compliance_score(finding_counts)
    risk_assessment = classify_risk_band(compliance_score)

    # Override with computed values (don't trust LLM math)
    summary_data["compliance_score"] = compliance_score
    summary_data["risk_assessment"] = risk_assessment

    # 6. Persist MasterReviewSummary
    async with session_factory() as db:
        master_summary = MasterReviewSummary(
            session_id=session_id,
            summary_data=summary_data,
            compliance_score=compliance_score,
            risk_assessment=risk_assessment,
        )
        db.add(master_summary)

        # Update session status to Completed with score
        review_session = await db.get(ReviewSession, session_id)
        if review_session:
            review_session.status = "Completed"
            review_session.compliance_score = compliance_score
            review_session.completed_at = datetime.now(UTC)

        await db.commit()

    logger.info(
        "Master summary completed: session_id=%d, score=%.1f, "
        "risk=%s, duration=%dms",
        session_id,
        compliance_score,
        risk_assessment,
        elapsed_ms,
    )

    return {
        "status": "Completed",
        "session_id": session_id,
        "compliance_score": compliance_score,
        "risk_assessment": risk_assessment,
        "inference_duration_ms": elapsed_ms,
    }


def _get_master_auditor_system_prompt() -> str:
    """Load the Master Auditor system prompt from the archetype YAML.

    Falls back to a default prompt if the YAML file is not found.

    Returns:
        The Master Auditor system prompt string.
    """
    from pathlib import Path

    import yaml

    # Try to load from the archetypes directory
    archetype_path = (
        Path(__file__).parent.parent.parent.parent.parent.parent
        / "agents"
        / "archetypes"
        / "master-auditor.yaml"
    )

    if archetype_path.exists():
        try:
            with open(archetype_path) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "system_prompt" in data:
                return data["system_prompt"]
        except Exception:
            pass

    # Fallback default prompt
    return (
        "You are the Master Auditor. Synthesize the provided individual review "
        "reports into a unified executive summary. Identify consensus findings, "
        "contradictions, compute compliance score, and produce prioritized "
        "action items. Respond in JSON format."
    )


def _count_findings_from_reports(
    agent_reports: list[dict[str, Any]],
) -> dict[str, int]:
    """Count findings by severity across all agent reports.

    Uses the unique findings (deduplicates by chapter+severity) to compute
    the compliance score fairly.

    Args:
        agent_reports: List of agent report dicts containing findings.

    Returns:
        Dict mapping severity to count.
    """
    counts: dict[str, int] = {
        "Critical": 0,
        "Major": 0,
        "Minor": 0,
        "Informational": 0,
    }

    for report in agent_reports:
        findings = report.get("findings", [])
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            severity = finding.get("severity", "")
            if severity in counts:
                counts[severity] += 1

    return counts


async def _mark_session_summary_failed(session_id: int) -> None:
    """Mark a session as Completed with summary_failed=True.

    Preserves individual agent reports as accessible even when the
    Master Auditor synthesis fails.

    Args:
        session_id: The ReviewSession ID.
    """
    from alcoabase.models.review import ReviewSession

    session_factory = _get_async_session_factory()
    async with session_factory() as db:
        review_session = await db.get(ReviewSession, session_id)
        if review_session:
            review_session.status = "Completed"
            review_session.summary_failed = True
            review_session.completed_at = datetime.now(UTC)
            await db.commit()


# ---------------------------------------------------------------------------
# Task: check_review_completion
# ---------------------------------------------------------------------------


@celery_app.task
def check_review_completion(session_id: int) -> None:
    """Check if the review session has met quorum and trigger next steps.

    Counts completed and failed agent reviews. If quorum is met, triggers
    the master summary. If quorum is impossible (too many failures), marks
    the session as Failed.

    Args:
        session_id: The ReviewSession ID to check.
    """
    asyncio.run(_check_review_completion_async(session_id))


async def _check_review_completion_async(session_id: int) -> None:
    """Async implementation of the review completion check.

    Args:
        session_id: The ReviewSession ID to check.
    """
    from sqlalchemy import select

    from alcoabase.models.audit_profile import AuditProfile
    from alcoabase.models.review import AgentReview, ReviewSession

    session_factory = _get_async_session_factory()

    async with session_factory() as db:
        # Get the review session
        review_session = await db.get(ReviewSession, session_id)
        if review_session is None:
            logger.warning(
                "check_review_completion: session %d not found", session_id
            )
            return

        # Skip if session is already in a terminal state
        if review_session.status in {"Completed", "Failed", "Approved", "Rejected"}:
            return

        # Get all agent reviews for this session
        result = await db.execute(
            select(AgentReview).where(AgentReview.session_id == session_id)
        )
        agent_reviews = list(result.scalars().all())

        total_agents = len(agent_reviews)
        completed = [ar for ar in agent_reviews if ar.status == "Completed"]
        failed = [ar for ar in agent_reviews if ar.status == "Failed"]
        completed_count = len(completed)
        failed_count = len(failed)

        # Get quorum from audit profile
        quorum = total_agents  # Default: all must complete
        if review_session.audit_profile_id:
            profile = await db.get(AuditProfile, review_session.audit_profile_id)
            if profile:
                quorum = profile.quorum

        logger.info(
            "check_review_completion: session=%d, completed=%d, "
            "failed=%d, total=%d, quorum=%d",
            session_id,
            completed_count,
            failed_count,
            total_agents,
            quorum,
        )

        # Check if quorum is met
        if completed_count >= quorum:
            # Collect completed reports and trigger master summary
            agent_reports = []
            for ar in completed:
                if ar.report_data:
                    agent_reports.append(ar.report_data)

            # Trigger master summary task
            execute_master_summary.delay(
                session_id=session_id,
                agent_reports=agent_reports,
                company_id=review_session.company_id,
            )
            return

        # Check if quorum is impossible
        remaining = total_agents - completed_count - failed_count
        if completed_count + remaining < quorum:
            # Cannot reach quorum — mark session as Failed
            failed_agents = [
                f"agent_def_id={ar.agent_definition_id}: {ar.error_reason or 'unknown'}"
                for ar in failed
            ]
            review_session.status = "Failed"
            review_session.completed_at = datetime.now(UTC)
            await db.commit()

            logger.warning(
                "Session %d marked as Failed: insufficient quorum "
                "(completed=%d, quorum=%d, failed_agents=%s)",
                session_id,
                completed_count,
                quorum,
                failed_agents,
            )


# ---------------------------------------------------------------------------
# Task: scan_anomalies_periodic
# ---------------------------------------------------------------------------


@celery_app.task
def scan_anomalies_periodic() -> dict[str, Any]:
    """Periodic task to scan all active companies for audit trail anomalies.

    Runs every 15 minutes via Celery beat. Iterates over all active
    companies and calls AnomalyDetectionService.scan_for_anomalies()
    for each one.

    Returns:
        Dict with scan results per company (company_id → alert count).

    References:
        - Requirement 8.1: Celery periodic task (every 15 minutes)
    """
    result = asyncio.run(_scan_anomalies_periodic_async())
    return result


async def _scan_anomalies_periodic_async() -> dict[str, Any]:
    """Async implementation of the periodic anomaly scan.

    Queries all active companies and runs anomaly detection for each.

    Returns:
        Dict with scan results: total_companies, total_alerts, and
        per-company alert counts.
    """
    from sqlalchemy import select

    from alcoabase.models.company import Company
    from alcoabase.services.anomaly_detection import AnomalyDetectionService

    session_factory = _get_async_session_factory()
    anomaly_service = AnomalyDetectionService(session_factory)

    # Query all active companies
    async with session_factory() as session:
        result = await session.execute(
            select(Company.id).where(Company.is_active == True)  # noqa: E712
        )
        company_ids = [row[0] for row in result.all()]

    logger.info(
        "scan_anomalies_periodic: scanning %d active companies",
        len(company_ids),
    )

    results: dict[str, Any] = {
        "total_companies": len(company_ids),
        "total_alerts": 0,
        "companies": {},
    }

    for company_id in company_ids:
        try:
            alerts = await anomaly_service.scan_for_anomalies(company_id)
            alert_count = len(alerts)
            results["companies"][str(company_id)] = alert_count
            results["total_alerts"] += alert_count

            if alert_count > 0:
                logger.info(
                    "scan_anomalies_periodic: company %d — %d new alerts",
                    company_id,
                    alert_count,
                )
        except Exception:
            logger.exception(
                "scan_anomalies_periodic: error scanning company %d",
                company_id,
            )
            results["companies"][str(company_id)] = "error"

    logger.info(
        "scan_anomalies_periodic: completed — %d total alerts across %d companies",
        results["total_alerts"],
        results["total_companies"],
    )

    return results
