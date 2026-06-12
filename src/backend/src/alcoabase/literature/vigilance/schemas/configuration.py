"""Pydantic v2 schemas for Vigilance Configuration endpoints.

Provides schemas for per-company vigilance configuration including
escalation thresholds, report scheduling, and notification settings.

References:
    - Requirements: 7.7, 8.1
    - Design doc: VigilanceConfiguration model
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReportPeriodEnum = Literal["monthly", "quarterly", "annually"]


class VigilanceConfigurationSchema(BaseModel):
    """Response schema for a company's vigilance configuration.

    Attributes:
        id: Configuration record ID.
        company_id: Company this configuration belongs to.
        critical_signal_auto_escalate: Whether critical signals trigger
            automatic escalation.
        major_signal_daily_digest: Whether major signals are included
            in daily digest notifications.
        escalation_notification_channels: Notification channels for
            escalation alerts.
        report_period: Configured report generation period.
        report_generation_day: Day of the period when reports are
            auto-generated (1–28).
        auto_report_enabled: Whether automatic report generation is enabled.
        created_at: When the configuration was created.
        updated_at: When the configuration was last modified.
    """

    id: int
    company_id: int
    critical_signal_auto_escalate: bool
    major_signal_daily_digest: bool
    escalation_notification_channels: list[str]
    report_period: ReportPeriodEnum
    report_generation_day: int = Field(ge=1, le=28)
    auto_report_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VigilanceConfigurationUpdateSchema(BaseModel):
    """Request schema for updating a company's vigilance configuration.

    All fields are optional; only provided fields are updated.

    Attributes:
        critical_signal_auto_escalate: Whether critical signals trigger
            automatic escalation.
        major_signal_daily_digest: Whether major signals are included
            in daily digest notifications.
        escalation_notification_channels: Notification channels for
            escalation alerts.
        report_period: Report generation period.
        report_generation_day: Day of the period for auto-generation (1–28).
        auto_report_enabled: Whether automatic report generation is enabled.
    """

    critical_signal_auto_escalate: bool | None = None
    major_signal_daily_digest: bool | None = None
    escalation_notification_channels: list[str] | None = None
    report_period: ReportPeriodEnum | None = None
    report_generation_day: int | None = Field(None, ge=1, le=28)
    auto_report_enabled: bool | None = None
