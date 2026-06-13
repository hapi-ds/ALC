"""ALC Corporate Environment seed data constants.

Defines all static configuration data used by ALCSeedService to provision
the ALC corporate tenant environment. These constants are immutable and
represent the canonical seed state for the corporate environment.
"""

from typing import Any

# Reserved slugs that cannot be used by other companies
RESERVED_SLUGS: frozenset[str] = frozenset({"alc-corporate"})

ALC_COMPANY_DATA: dict[str, Any] = {
    "slug": "alc-corporate",
    "display_name": "AlcoaBase Corporate",
    "regulatory_framework": "ISO_27001",
    "audit_config": {
        "review_quorum": 2,
        "auto_audit_on_upload": True,
        "severity_threshold": "medium",
    },
}

ALC_USER_POOL: list[dict[str, str]] = [
    {
        "username": "alc-it-admin",
        "full_name": "ALC IT Administrator",
        "email": "it-admin@alc.local",
        "role": "system_admin",
    },
    {
        "username": "alc-doc-admin",
        "full_name": "ALC Document Administrator",
        "email": "doc-admin@alc.local",
        "role": "doc_admin",
    },
    {
        "username": "alc-quality-mgr",
        "full_name": "ALC Quality Manager",
        "email": "quality@alc.local",
        "role": "doc_admin",
    },
    {
        "username": "alc-user",
        "full_name": "ALC Standard User",
        "email": "user@alc.local",
        "role": "member",
    },
]

ALC_GOVERNANCE_FOLDERS: list[dict[str, Any]] = [
    {
        "name": "Governance — User Requirement Specifications",
        "tag_filter": {"tags": ["URS", "ALC-GOV"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "Governance — AI Regulatory Guidelines",
        "tag_filter": {"tags": ["AI-Guidelines", "ALC-GOV"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "Governance — User Guides",
        "tag_filter": {"tags": ["User-Guide", "ALC-GOV"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "Governance — Admin Guides",
        "tag_filter": {"tags": ["Admin-Guide", "ALC-GOV"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "Governance — Risk Framework",
        "tag_filter": {"tags": ["Risk-Framework", "ALC-GOV"]},
        "sort_order": "created_at_desc",
    },
    {
        "name": "Governance — All Documents",
        "tag_filter": {"tags": ["ALC-GOV"]},
        "sort_order": "created_at_desc",
    },
]

ALC_REGULATORY_BASELINE: dict[str, Any] = {
    "applicable_frameworks": ["ISO_27001", "ISO_9001", "EU_AI_Act"],
    "document_retention_years": 10,
    "signature_required_for_approval": True,
    "training_required_before_access": True,
    "audit_log_retention_years": 7,
    "review_cycle_days": 365,
}

ALC_AUDIT_CONFIG: dict[str, Any] = {
    "review_quorum": 2,
    "auto_audit_on_upload": True,
    "severity_threshold": "medium",
    "default_workflow_tag": "ALC-GOV",
}

ALC_GOVERNANCE_BPMN_XML: str = """<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             id="ALC_Governance_Definitions"
             targetNamespace="http://alcoabase.local/bpmn/governance">
  <process id="alc_governance_lifecycle" name="ALC Governance Document Lifecycle" isExecutable="true">
    <startEvent id="start" name="Start"/>
    <userTask id="draft" name="Draft"/>
    <userTask id="review" name="Review"/>
    <userTask id="approved" name="Approved"/>
    <userTask id="in_training" name="InTraining"/>
    <userTask id="active" name="Active"/>
    <endEvent id="retired" name="Retired"/>
    <sequenceFlow id="flow_start_draft" sourceRef="start" targetRef="draft"/>
    <sequenceFlow id="flow_draft_review" sourceRef="draft" targetRef="review"/>
    <sequenceFlow id="flow_review_approved" sourceRef="review" targetRef="approved"/>
    <sequenceFlow id="flow_approved_training" sourceRef="approved" targetRef="in_training"/>
    <sequenceFlow id="flow_training_active" sourceRef="in_training" targetRef="active"/>
    <sequenceFlow id="flow_active_retired" sourceRef="active" targetRef="retired"/>
  </process>
</definitions>"""


def validate_company_slug(slug: str) -> None:
    """Raise ValueError if slug is reserved for the ALC corporate environment.

    Args:
        slug: The company slug to validate.

    Raises:
        ValueError: If the slug is in RESERVED_SLUGS.
    """
    if slug in RESERVED_SLUGS:
        raise ValueError(
            f"Slug '{slug}' is reserved for the ALC corporate environment"
        )
