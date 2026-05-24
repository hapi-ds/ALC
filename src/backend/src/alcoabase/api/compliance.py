"""FastAPI router for compliance monitoring endpoints.

Provides endpoints for compliance scorecards, missing link detection,
and anomaly alert management.

Endpoints:
    - GET /api/compliance/scorecard: Get company compliance scorecard
    - GET /api/compliance/missing-links: Detect missing links
    - GET /api/compliance/anomalies: List anomaly alerts
    - PATCH /api/compliance/anomalies/{anomaly_id}/resolve: Resolve anomaly

References:
    - Requirements 6.2, 7.1, 8.4, 8.5
    - Design: FastAPI Routers — Compliance Router
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from alcoabase.dependencies.tenant import TenantContext, get_tenant_context
from alcoabase.schemas.review import (
    AnomalyAlertResponse,
    AnomalyResolveRequest,
    ComplianceScorecardResponse,
    MissingLinkResponse,
)
from alcoabase.services.anomaly_detection import AnomalyDetectionService
from alcoabase.services.compliance_scorecard import ComplianceScorecardService
from alcoabase.services.missing_link_service import MissingLinkService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["Compliance"])


# ---------------------------------------------------------------------------
# Dependencies: Services
# ---------------------------------------------------------------------------

_compliance_scorecard_service: ComplianceScorecardService | None = None
_missing_link_service: MissingLinkService | None = None
_anomaly_detection_service: AnomalyDetectionService | None = None


def set_compliance_scorecard_service(service: ComplianceScorecardService) -> None:
    """Set the module-level ComplianceScorecardService instance.

    Args:
        service: The initialized ComplianceScorecardService instance.
    """
    global _compliance_scorecard_service
    _compliance_scorecard_service = service


def set_missing_link_service(service: MissingLinkService) -> None:
    """Set the module-level MissingLinkService instance.

    Args:
        service: The initialized MissingLinkService instance.
    """
    global _missing_link_service
    _missing_link_service = service


def set_anomaly_detection_service(service: AnomalyDetectionService) -> None:
    """Set the module-level AnomalyDetectionService instance.

    Args:
        service: The initialized AnomalyDetectionService instance.
    """
    global _anomaly_detection_service
    _anomaly_detection_service = service


def get_compliance_scorecard_service() -> ComplianceScorecardService:
    """Provide the ComplianceScorecardService as a FastAPI dependency.

    Returns:
        The module-level ComplianceScorecardService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _compliance_scorecard_service is None:
        raise HTTPException(
            status_code=503,
            detail="Compliance scorecard service is not available.",
        )
    return _compliance_scorecard_service


# Alias for shorter dependency override names in tests
get_scorecard_service = get_compliance_scorecard_service


def get_missing_link_service() -> MissingLinkService:
    """Provide the MissingLinkService as a FastAPI dependency.

    Returns:
        The module-level MissingLinkService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _missing_link_service is None:
        raise HTTPException(
            status_code=503,
            detail="Missing link service is not available.",
        )
    return _missing_link_service


def get_anomaly_detection_service() -> AnomalyDetectionService:
    """Provide the AnomalyDetectionService as a FastAPI dependency.

    Returns:
        The module-level AnomalyDetectionService instance.

    Raises:
        HTTPException 503: If the service has not been initialized.
    """
    if _anomaly_detection_service is None:
        raise HTTPException(
            status_code=503,
            detail="Anomaly detection service is not available.",
        )
    return _anomaly_detection_service


# Alias for shorter dependency override names in tests
get_anomaly_service = get_anomaly_detection_service


# ---------------------------------------------------------------------------
# Scorecard Endpoint
# ---------------------------------------------------------------------------


@router.get("/scorecard", response_model=ComplianceScorecardResponse)
async def get_compliance_scorecard(
    tenant: TenantContext = Depends(get_tenant_context),
    service: ComplianceScorecardService = Depends(get_compliance_scorecard_service),
) -> ComplianceScorecardResponse:
    """Get the company-level compliance scorecard.

    Returns the aggregate compliance score, risk band, trend,
    and breakdown by document type for the last 90 days.

    Args:
        tenant: Resolved tenant context (company_id).
        service: ComplianceScorecardService dependency.

    Returns:
        The compliance scorecard for the company.
    """
    scorecard = await service.get_scorecard(company_id=tenant.company_id)
    return ComplianceScorecardResponse.model_validate(scorecard)


# ---------------------------------------------------------------------------
# Missing Links Endpoint
# ---------------------------------------------------------------------------


@router.get("/missing-links", response_model=list[MissingLinkResponse])
async def get_missing_links(
    tenant: TenantContext = Depends(get_tenant_context),
    service: MissingLinkService = Depends(get_missing_link_service),
) -> list[MissingLinkResponse]:
    """Detect documents with missing training records or signatures.

    Returns a list of documents in "Approved" or "Active" status
    that are missing required training records or electronic signatures.

    Args:
        tenant: Resolved tenant context (company_id).
        service: MissingLinkService dependency.

    Returns:
        List of missing link records with severity classification.
    """
    missing_links = await service.detect_missing_links(
        company_id=tenant.company_id
    )
    return [
        MissingLinkResponse.model_validate(ml, from_attributes=True)
        for ml in missing_links
    ]


# ---------------------------------------------------------------------------
# Anomaly Alert Endpoints
# ---------------------------------------------------------------------------


@router.get("/anomalies", response_model=list[AnomalyAlertResponse])
async def list_anomaly_alerts(
    anomaly_type: str | None = Query(default=None, description="Filter by anomaly type"),
    severity: str | None = Query(default=None, description="Filter by severity"),
    is_resolved: bool | None = Query(default=None, description="Filter by resolution status"),
    date_from: datetime | None = Query(default=None, description="Filter from date"),
    date_to: datetime | None = Query(default=None, description="Filter to date"),
    tenant: TenantContext = Depends(get_tenant_context),
    service: AnomalyDetectionService = Depends(get_anomaly_detection_service),
) -> list[AnomalyAlertResponse]:
    """List anomaly alerts for the current company.

    Supports filtering by anomaly type, severity, resolution status,
    and date range.

    Args:
        anomaly_type: Optional anomaly type filter.
        severity: Optional severity filter.
        is_resolved: Optional resolution status filter.
        date_from: Optional start date filter.
        date_to: Optional end date filter.
        tenant: Resolved tenant context (company_id).
        service: AnomalyDetectionService dependency.

    Returns:
        List of anomaly alerts matching the filters.
    """
    alerts = await service.list_alerts(
        company_id=tenant.company_id,
        anomaly_type=anomaly_type,
        severity=severity,
        is_resolved=is_resolved,
        date_from=date_from,
        date_to=date_to,
    )
    return [
        AnomalyAlertResponse.model_validate(alert, from_attributes=True)
        for alert in alerts
    ]


@router.patch("/anomalies/{anomaly_id}/resolve", response_model=AnomalyAlertResponse)
async def resolve_anomaly_alert(
    anomaly_id: int,
    request: AnomalyResolveRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    service: AnomalyDetectionService = Depends(get_anomaly_detection_service),
) -> AnomalyAlertResponse:
    """Resolve an anomaly alert with a resolution note.

    Args:
        anomaly_id: The anomaly alert primary key.
        request: Resolution request with resolution_note.
        tenant: Resolved tenant context (company_id).
        service: AnomalyDetectionService dependency.

    Returns:
        The updated anomaly alert.

    Raises:
        HTTPException 404: If anomaly not found or wrong company.
    """
    try:
        alert = await service.resolve_alert(
            anomaly_id=anomaly_id,
            resolution_note=request.resolution_note,
            company_id=tenant.company_id,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="Anomaly alert not found")

    return AnomalyAlertResponse.model_validate(alert, from_attributes=True)
