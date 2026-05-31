"""AI Regulatory Guidelines content templates and sector module definitions.

Contains the template constants, sector module configurations, and content
assembly functions for generating AI usage guideline documents. Content is
deterministic and version-controlled; dynamic risk data is injected at
generation time from the Risk Classification Service (Phase 8.1).

The module defines:
- MASTER_GUIDELINE_TITLE: Title for the cross-sector master document
- SECTOR_MODULES: List of SectorModule configurations (Pharma, MedTech, IVD)
- REGULATORY_FRAMEWORKS: Static regulatory framework reference data
- PROHIBITED_USES: List of universally prohibited AI operations
- Template assembly functions for each document section

References:
    - Design: .kiro/specs/Step_8-4_cross-sector-ai-regulatory-guidelines/design.md
    - Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.1–2.8, 4.4, 7.1–7.7
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegulatoryFramework:
    """A regulatory framework referenced in guidelines.

    Attributes:
        identifier: Machine-readable identifier (e.g., "EU_AI_Act").
        display_name: Human-readable name with regulation number.
        key_articles: List of specific articles/sections referenced.
    """

    identifier: str
    display_name: str
    key_articles: list[str]


@dataclass(frozen=True)
class SectorModule:
    """Configuration for a sector-specific guideline document.

    Attributes:
        sector_id: Machine-readable sector identifier.
        title: Full document title for the sector guideline.
        sector_label: Human-readable sector label.
        applicable_regulations: Regulatory frameworks applicable to this sector.
        dedicated_subsections: Required subsection topics for this sector.
        risk_elevation_rules: Mapping of task_type_id to elevation rationale.
    """

    sector_id: str
    title: str
    sector_label: str
    applicable_regulations: list[RegulatoryFramework]
    dedicated_subsections: list[str]
    risk_elevation_rules: dict[str, str]


@dataclass
class RiskFrameworkContext:
    """Aggregated risk framework data for guideline content assembly.

    Loaded once at the start of generation and passed to all content
    assembly functions to avoid repeated DB queries.

    Attributes:
        task_types: All active AI task type records.
        effective_tiers: Mapping of task_type_id to effective tier level.
        tier_definitions: Mapping of tier_level to control set definition.
        company_profile_active: Whether a company-specific profile exists.
        risk_factors_map: Mapping of task_type_id to risk_factors array.
    """

    task_types: list[Any]
    effective_tiers: dict[str, str]
    tier_definitions: dict[str, Any]
    company_profile_active: bool
    risk_factors_map: dict[str, list[str]]


@dataclass
class DocumentResult:
    """Result of a single document upload/version operation.

    Attributes:
        document_id: Database primary key of the document.
        document_uuid: Generated UUID in YYYY-NNNNN format.
        title: Document title.
        sector: Sector identifier (cross-sector, pharma_gmp, etc.).
        version_number: Current version number.
        is_new_document: True if newly created, False if versioned.
        tags_applied: List of tags applied to the document.
        workflow_state: Current workflow state (always "Draft").
    """

    document_id: int
    document_uuid: str
    title: str
    sector: str
    version_number: int
    is_new_document: bool
    tags_applied: list[str]
    workflow_state: str


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MASTER_GUIDELINE_TITLE: str = "AlcoaBase — AI Usage Guidelines (Cross-Sector)"

PHARMA_GUIDELINE_TITLE: str = (
    "AlcoaBase — AI Usage Guidelines (Pharma / GMP)"
)

MEDTECH_GUIDELINE_TITLE: str = (
    "AlcoaBase — AI Usage Guidelines (MedTech / ISO 13485)"
)

IVD_GUIDELINE_TITLE: str = "AlcoaBase — AI Usage Guidelines (IVD / IVDR)"

GUIDELINE_TAGS: list[str] = ["AI-Guidelines", "ALC-GOV"]

GUIDELINE_DOCUMENT_TYPE: str = "AI Usage Guidelines"


# ---------------------------------------------------------------------------
# Regulatory Frameworks
# ---------------------------------------------------------------------------

REGULATORY_FRAMEWORKS: list[RegulatoryFramework] = [
    RegulatoryFramework(
        identifier="EU_AI_Act",
        display_name="EU AI Act (Regulation 2024/1689)",
        key_articles=[
            "Article 6 — Classification Rules for High-Risk AI Systems",
            "Article 9 — Risk Management System",
            "Article 14 — Human Oversight",
            "Article 17 — Quality Management System",
            "Article 61 — Post-Market Monitoring",
        ],
    ),
    RegulatoryFramework(
        identifier="FDA_21CFR11",
        display_name="21 CFR Part 11 — Electronic Records; Electronic Signatures",
        key_articles=[
            "§11.10(a) — Validation of Systems",
            "§11.10(b) — Accurate and Complete Copies",
            "§11.10(e) — Audit Trails",
            "§11.10(k) — Authority Checks",
            "§11.50 — Signature Manifestations",
        ],
    ),
    RegulatoryFramework(
        identifier="EU_GMP_Annex11",
        display_name="EU GMP Annex 11 — Computerised Systems",
        key_articles=[
            "Section 1 — Risk Management",
            "Section 4 — Validation",
            "Section 7 — Data Storage and Integrity",
            "Section 9 — Audit Trails",
            "Section 12 — Security",
        ],
    ),
    RegulatoryFramework(
        identifier="ISO_13485",
        display_name="ISO 13485:2016 — Medical Devices QMS",
        key_articles=[
            "Section 4.1.6 — Software Validation",
            "Section 7.3 — Design and Development",
            "Section 7.5.6 — Validation of Processes",
            "Section 8.2.3 — Monitoring and Measurement of Processes",
        ],
    ),
    RegulatoryFramework(
        identifier="IVDR_2017_746",
        display_name="IVDR 2017/746 — In Vitro Diagnostic Regulation",
        key_articles=[
            "Article 9 — Common Specifications",
            "Article 48 — Conformity Assessment Procedures",
            "Article 56 — Performance Studies",
            "Annex XIII — Clinical Evidence and Performance Evaluation",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Prohibited Uses
# ---------------------------------------------------------------------------

PROHIBITED_USES: list[str] = [
    (
        "Using AI outputs as sole basis for batch release decisions "
        "without human verification"
    ),
    "Bypassing HITL checkpoints for High-tier operations",
    (
        "Using AI-generated content in regulatory submissions without "
        "formal review and approval through the governance workflow"
    ),
    "Disabling audit logging for any AI operation",
]


# ---------------------------------------------------------------------------
# Sector Module Definitions
# ---------------------------------------------------------------------------

_PHARMA_REGULATIONS: list[RegulatoryFramework] = [
    RegulatoryFramework(
        identifier="EU_GMP_Annex11",
        display_name="EU GMP Annex 11 — Computerised Systems",
        key_articles=[
            "Section 1 — Risk Management",
            "Section 4 — Validation",
            "Section 7 — Data Storage and Integrity",
            "Section 9 — Audit Trails",
        ],
    ),
    RegulatoryFramework(
        identifier="FDA_21CFR11",
        display_name="21 CFR Part 11 — Electronic Records; Electronic Signatures",
        key_articles=[
            "§11.10(a) — Validation of Systems",
            "§11.10(e) — Audit Trails",
            "§11.10(k) — Authority Checks",
        ],
    ),
    RegulatoryFramework(
        identifier="EU_GMP_Chapter4",
        display_name="EU GMP Chapter 4 — Documentation",
        key_articles=[
            "Section 4.1 — Principle of Good Documentation Practice",
            "Section 4.2 — Change Control Requirements",
        ],
    ),
    RegulatoryFramework(
        identifier="ICH_Q9_Q10",
        display_name="ICH Q9/Q10 — Quality Risk Management / Pharmaceutical QS",
        key_articles=[
            "ICH Q9 Section 4 — Risk Assessment Methodology",
            "ICH Q10 Section 3 — Pharmaceutical Quality System Elements",
        ],
    ),
]


_MEDTECH_REGULATIONS: list[RegulatoryFramework] = [
    RegulatoryFramework(
        identifier="ISO_13485",
        display_name="ISO 13485:2016 — Medical Devices QMS",
        key_articles=[
            "Section 4.1.6 — Software Validation",
            "Section 7.3 — Design and Development",
            "Section 7.5.6 — Validation of Processes",
        ],
    ),
    RegulatoryFramework(
        identifier="MDR_2017_745",
        display_name="MDR 2017/745 — Medical Device Regulation",
        key_articles=[
            "Article 10 — General Obligations of Manufacturers",
            "Article 83 — Vigilance Requirements",
        ],
    ),
    RegulatoryFramework(
        identifier="IEC_62304",
        display_name="IEC 62304 — Medical Device Software Lifecycle",
        key_articles=[
            "Section 5 — Software Development Process",
            "Section 6 — Software Maintenance Process",
            "Section 7 — Software Risk Management Process",
        ],
    ),
    RegulatoryFramework(
        identifier="FDA_21CFR820",
        display_name="FDA 21 CFR 820 — Quality System Regulation",
        key_articles=[
            "§820.30 — Design Controls",
            "§820.70 — Production and Process Controls",
            "§820.90 — Nonconforming Product",
        ],
    ),
]


_IVD_REGULATIONS: list[RegulatoryFramework] = [
    RegulatoryFramework(
        identifier="IVDR_2017_746",
        display_name="IVDR 2017/746 — In Vitro Diagnostic Regulation",
        key_articles=[
            "Article 9 — Common Specifications",
            "Article 48 — Conformity Assessment Procedures",
            "Article 56 — Performance Studies",
            "Annex XIII — Clinical Evidence and Performance Evaluation",
        ],
    ),
    RegulatoryFramework(
        identifier="ISO_13485",
        display_name="ISO 13485:2016 — Medical Devices QMS",
        key_articles=[
            "Section 4.1.6 — Software Validation",
            "Section 7.3 — Design and Development",
            "Section 7.5.6 — Validation of Processes",
        ],
    ),
    RegulatoryFramework(
        identifier="EU_Common_Specifications",
        display_name="EU Common Specifications for IVDs",
        key_articles=[
            "Part A — Common Specifications for Performance Evaluation",
            "Part B — Common Specifications for Post-Market Performance",
        ],
    ),
]


SECTOR_MODULES: list[SectorModule] = [
    SectorModule(
        sector_id="pharma_gmp",
        title=PHARMA_GUIDELINE_TITLE,
        sector_label="Pharma / GMP",
        applicable_regulations=_PHARMA_REGULATIONS,
        dedicated_subsections=[
            "GMP Data Integrity Requirements (ALCOA+ Applied to AI Outputs)",
            "Computer System Validation Expectations for AI-Assisted Processes",
            "AI Model Qualification Requirements for GxP-Regulated Activities",
            "Change Control Procedures for AI Model Updates",
        ],
        risk_elevation_rules={
            "document_generation": (
                "GMP Annex 11 Section 7 requires validated data integrity "
                "controls for all computerised records entering batch documentation"
            ),
            "multi_agent_audit": (
                "21 CFR Part 11 §11.10(a) mandates full validation of systems "
                "producing electronic records used in GMP decisions"
            ),
            "training_content_generation": (
                "ICH Q10 Section 3 requires qualified personnel; AI-generated "
                "training must meet GMP competency assurance standards"
            ),
        },
    ),
    SectorModule(
        sector_id="medtech_iso13485",
        title=MEDTECH_GUIDELINE_TITLE,
        sector_label="MedTech / ISO 13485",
        applicable_regulations=_MEDTECH_REGULATIONS,
        dedicated_subsections=[
            "Design Control Integration for AI Outputs as Design Inputs",
            "Software Lifecycle Requirements for AI Components (IEC 62304)",
            "Risk Management Integration (ISO 14971 Applied to AI Content)",
            "Post-Market Surveillance for AI-Assisted Decisions",
        ],
        risk_elevation_rules={
            "document_generation": (
                "ISO 13485 Section 7.3 requires design input review; "
                "AI-generated documents entering design history files "
                "require elevated controls"
            ),
            "change_impact_analysis": (
                "MDR 2017/745 Article 83 vigilance requirements mandate "
                "comprehensive impact assessment for device-related changes"
            ),
            "traceability_gap_discovery": (
                "IEC 62304 Section 7 requires complete software risk "
                "traceability; gaps in AI-identified traceability require "
                "elevated review"
            ),
        },
    ),
    SectorModule(
        sector_id="ivd_ivdr",
        title=IVD_GUIDELINE_TITLE,
        sector_label="IVD / IVDR",
        applicable_regulations=_IVD_REGULATIONS,
        dedicated_subsections=[
            "Performance Evaluation Requirements for AI-Assisted Analytical Processes",
            "Common Specifications Compliance for AI-Generated IVD Documentation",
            "Clinical Evidence Requirements for AI-Supported Performance Studies",
            "Notified Body Expectations for AI Usage Documentation",
        ],
        risk_elevation_rules={
            "document_generation": (
                "IVDR Article 56 requires documented performance evaluation; "
                "AI-generated IVD documentation must meet performance study "
                "evidence standards"
            ),
            "multi_agent_audit": (
                "IVDR Article 48 conformity assessment requires complete "
                "documentation of all quality system processes including "
                "AI-assisted auditing"
            ),
            "training_content_generation": (
                "IVDR Annex XIII clinical evidence requirements extend to "
                "personnel competency for IVD performance evaluation tasks"
            ),
        },
    ),
]


# ---------------------------------------------------------------------------
# Content Assembly Functions
# ---------------------------------------------------------------------------


def assemble_document_header(
    title: str,
    version_number: int,
    applicable_regulations: list[RegulatoryFramework],
) -> str:
    """Assemble the document header section with metadata table.

    Args:
        title: Document title.
        version_number: Current version number.
        applicable_regulations: List of applicable regulatory frameworks.

    Returns:
        Markdown string for the document header section.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reg_names = ", ".join(r.display_name for r in applicable_regulations)

    header = f"# {title}\n\n"
    header += "## Document Header\n\n"
    header += "| Field | Value |\n"
    header += "|-------|-------|\n"
    header += f"| **Document Title** | {title} |\n"
    header += f"| **Document Type** | {GUIDELINE_DOCUMENT_TYPE} |\n"
    header += f"| **Version** | {version_number} |\n"
    header += f"| **Generated** | {timestamp} |\n"
    header += f"| **Applicable Regulations** | {reg_names} |\n"
    header += "| **Classification** | Controlled Document — ALC Governance |\n"
    header += "\n### Revision History\n\n"
    header += "| Version | Date | Author | Description |\n"
    header += "|---------|------|--------|-------------|\n"
    header += (
        f"| {version_number} | {timestamp} | "
        "Guidelines Generator Service | Automated generation |\n"
    )
    return header


def assemble_purpose_and_scope() -> str:
    """Assemble the Purpose and Scope section.

    Returns:
        Markdown string for the purpose and scope section.
    """
    return (
        "\n---\n\n## Purpose and Scope\n\n"
        "This document provides comprehensive guidance on the permitted, "
        "restricted, and prohibited uses of AI-powered features within "
        "AlcoaBase. It establishes the compliance framework for AI operations "
        "across all regulated sectors, integrating risk classifications from "
        "the AI Risk & Compliance Framework (Phase 8.1) with applicable "
        "regulatory requirements.\n\n"
        "**Scope:** This guideline applies to all users of AlcoaBase AI "
        "features including Document Generation, Multi-Agent Auditing, "
        "Training Content Generation, Change Impact Analysis, Traceability "
        "Gap Discovery, RAG Knowledge Query, Document Search, and Template "
        "Analysis. It covers operations within Pharma/GMP, MedTech/ISO 13485, "
        "and IVD/IVDR regulatory environments.\n\n"
        "**Objective:** Ensure that AI-assisted operations maintain data "
        "integrity (ALCOA+ principles), comply with applicable regulations, "
        "and support audit readiness at all times.\n"
    )


def assemble_regulatory_overview(
    frameworks: list[RegulatoryFramework],
) -> str:
    """Assemble the Regulatory Framework Overview section.

    Args:
        frameworks: List of regulatory frameworks to include.

    Returns:
        Markdown string for the regulatory overview section.
    """
    section = "\n---\n\n## Regulatory Framework Overview\n\n"
    section += (
        "The following regulatory frameworks govern AI usage within "
        "AlcoaBase. Each control requirement in this document includes "
        "an inline citation referencing the applicable regulation and "
        "specific article.\n\n"
    )
    for fw in frameworks:
        section += f"### {fw.display_name}\n\n"
        for article in fw.key_articles:
            section += f"- {article}\n"
        section += "\n"
    return section


def assemble_risk_classification_summary(
    risk_context: RiskFrameworkContext,
) -> str:
    """Assemble the Risk Classification Summary section.

    Generates a Risk_Integration_Block for each active AI task type showing
    the effective tier, controls, HITL requirements, and risk factors.

    Args:
        risk_context: Aggregated risk framework data.

    Returns:
        Markdown string for the risk classification summary section.
    """
    section = "\n---\n\n## Risk Classification Summary\n\n"
    section += (
        "The following risk classifications are derived from the AI Risk & "
        "Compliance Framework (Phase 8.1). Each AI task type is assigned a "
        "risk tier determining the applicable control set.\n\n"
    )

    if not risk_context.company_profile_active:
        section += (
            "> **Notice:** Default risk classifications are applied because "
            "no company-specific risk profile is currently active. Contact "
            "your system administrator to configure a Company Risk Profile "
            "for tailored tier assignments.\n\n"
        )

    for task_type in risk_context.task_types:
        tid = task_type.task_type_id
        tier = risk_context.effective_tiers.get(tid, "low")
        tier_def = risk_context.tier_definitions.get(tier)
        risk_factors = risk_context.risk_factors_map.get(tid, [])

        section += f"### {task_type.display_name}\n\n"
        section += f"- **Risk Tier:** {tier.capitalize()}\n"
        section += (
            f"- **HITL Required:** "
            f"{'Yes' if tier_def and tier_def.hitl_required else 'No'}\n"
        )
        if tier_def:
            section += f"- **Audit Depth:** {tier_def.audit_depth.capitalize()}\n"
            if tier_def.validations:
                validations_str = ", ".join(tier_def.validations)
                section += f"- **Validations:** {validations_str}\n"
            if tier_def.output_label:
                section += f"- **Output Labeling:** {tier_def.output_label}\n"
            if tier_def.expiry_hours:
                section += (
                    f"- **Expiry Window:** {tier_def.expiry_hours} hours\n"
                )
            if tier_def.rate_limit:
                section += (
                    f"- **Rate Limit:** {tier_def.rate_limit} "
                    "requests/user/hour\n"
                )

        if risk_factors:
            section += "- **Risk Factors:**\n"
            for factor in risk_factors:
                section += f"  - {factor}\n"
        section += "\n"

    return section


def _get_compliance_steps(tier: str, task_type_id: str) -> list[str]:
    """Get compliance procedure steps based on tier and task type.

    Returns between 3 and 15 steps depending on the risk tier.

    Args:
        tier: The effective risk tier (high, medium, low).
        task_type_id: The task type identifier for context.

    Returns:
        List of numbered compliance procedure steps.
    """
    if tier == "high":
        return [
            "Verify user has valid training record for the relevant SOP version",
            "Confirm the AI operation is within the permitted scope for this task type",
            "Review input parameters and source data for completeness",
            "Initiate the AI operation through the approved interface",
            "Wait for HITL checkpoint notification before proceeding",
            "Review AI-generated output against acceptance criteria",
            "Document review decision with rationale in the audit trail",
            "Apply electronic signature to approve or reject the output",
            "If approved, advance the document through the governance workflow",
            "Retain all generation artifacts for the regulatory retention period",
        ]
    elif tier == "medium":
        return [
            "Verify user authorization for the requested AI operation",
            "Confirm the operation scope aligns with permitted uses",
            "Initiate the AI operation through the approved interface",
            "Review AI output for accuracy and completeness",
            "Acknowledge HITL checkpoint (non-blocking)",
            "Document any deviations or concerns in the audit trail",
            "Proceed with human decision-making informed by AI output",
        ]
    else:  # low
        return [
            "Initiate the AI operation through the approved interface",
            "Review returned results for relevance",
            "Verify information against source documents before acting",
        ]


def _get_regulatory_citation(tier: str, task_type_id: str) -> str:
    """Get the primary regulatory citation for a control requirement.

    Args:
        tier: The effective risk tier.
        task_type_id: The task type identifier.

    Returns:
        Inline citation string with regulation and article reference.
    """
    citations: dict[str, dict[str, str]] = {
        "high": {
            "document_generation": (
                "EU AI Act Article 14 — Human Oversight; "
                "21 CFR 11.10(a) — Validation"
            ),
            "multi_agent_audit": (
                "EU AI Act Article 17 — Quality Management System; "
                "21 CFR 11.10(e) — Audit Trails"
            ),
            "training_content_generation": (
                "EU AI Act Article 14 — Human Oversight; "
                "EU GMP Annex 11 Section 4 — Validation"
            ),
        },
        "medium": {
            "change_impact_analysis": (
                "EU AI Act Article 9 — Risk Management System; "
                "EU GMP Annex 11 Section 1 — Risk Management"
            ),
            "traceability_gap_discovery": (
                "EU AI Act Article 9 — Risk Management System; "
                "ISO 13485 Section 7.5.6 — Validation of Processes"
            ),
        },
        "low": {
            "rag_knowledge_query": (
                "EU GMP Annex 11 Section 7 — Data Storage and Integrity"
            ),
            "document_search": (
                "Regulatory reference: Industry best practice — "
                "no specific article applicable"
            ),
            "template_analysis": (
                "Regulatory reference: Industry best practice — "
                "no specific article applicable"
            ),
        },
    }
    tier_citations = citations.get(tier, {})
    return tier_citations.get(
        task_type_id,
        (
            "EU AI Act Article 14 — Human Oversight; "
            "EU GMP Annex 11 Section 1 — Risk Management"
        ),
    )


def assemble_policy_section(
    task_type: Any,
    tier: str,
    tier_def: Any,
    risk_factors: list[str],
    sector_module: SectorModule | None = None,
) -> str:
    """Assemble a single Policy_Section for an AI task type.

    Each Policy_Section contains exactly 5 subsections:
    (a) Permitted Uses, (b) Restrictions, (c) Compliance Procedure,
    (d) Required Evidence, (e) Consequences of Non-Compliance.

    Args:
        task_type: The AI task type record.
        tier: Effective risk tier for this task type.
        tier_def: Tier definition with control set details.
        risk_factors: Risk factors for this task type.
        sector_module: Optional sector module for sector-specific overlay.

    Returns:
        Markdown string for the complete policy section.
    """
    tid = task_type.task_type_id
    citation = _get_regulatory_citation(tier, tid)
    steps = _get_compliance_steps(tier, tid)

    section = f"### Policy: {task_type.display_name}\n\n"
    section += (
        f"**Risk Tier:** {tier.capitalize()} | "
        f"**Regulatory Basis:** {citation}\n\n"
    )

    # (a) Permitted Uses
    section += "**(a) Permitted Uses**\n\n"
    section += (
        f"- Use {task_type.display_name} for its intended purpose within "
        f"the scope defined by module reference {task_type.module_reference}\n"
    )
    section += (
        "- Operate within the boundaries of the assigned risk tier controls\n"
    )
    if tier == "low":
        section += (
            "- Use outputs as informational reference without formal approval\n"
        )
    elif tier == "medium":
        section += (
            "- Use outputs to inform human decision-making with "
            "appropriate review\n"
        )
    else:
        section += (
            "- Use outputs only after HITL review and formal approval "
            "through the governance workflow\n"
        )
    section += "\n"

    # (b) Restrictions
    section += "**(b) Restrictions**\n\n"
    if tier_def and tier_def.hitl_required:
        section += (
            f"- HITL checkpoint is mandatory before output visibility "
            f"({citation})\n"
        )
    if tier_def and tier_def.expiry_hours:
        section += (
            f"- Unreviewed outputs expire after {tier_def.expiry_hours} hours "
            f"and must be regenerated ({citation})\n"
        )
    if tier_def and tier_def.rate_limit:
        section += (
            f"- Rate limited to {tier_def.rate_limit} requests per user "
            f"per hour ({citation})\n"
        )
    section += (
        "- Output must not be used for purposes outside the defined scope\n"
    )
    if sector_module and tid in sector_module.risk_elevation_rules:
        section += (
            f"- **Sector restriction (Supplementary to base policy):** "
            f"{sector_module.risk_elevation_rules[tid]}\n"
        )
    section += "\n"

    # (c) Compliance Procedure
    section += "**(c) Compliance Procedure**\n\n"
    for i, step in enumerate(steps, 1):
        section += f"{i}. {step}\n"
    section += "\n"

    # (d) Required Evidence
    section += "**(d) Required Evidence and Documentation**\n\n"
    if tier == "high":
        section += (
            "- Complete audit trail of generation request and parameters "
            "(21 CFR 11.10(e) — Audit Trails)\n"
        )
        section += (
            "- HITL review record with reviewer identity and decision "
            "(EU AI Act Article 14 — Human Oversight)\n"
        )
        section += (
            "- Electronic signature on approval "
            "(21 CFR 11.50 — Signature Manifestations)\n"
        )
        section += (
            "- Validation evidence for the AI system "
            "(EU GMP Annex 11 Section 4 — Validation)\n"
        )
    elif tier == "medium":
        section += (
            "- Audit trail of operation execution "
            "(EU GMP Annex 11 Section 9 — Audit Trails)\n"
        )
        section += (
            "- HITL acknowledgment record "
            "(EU AI Act Article 14 — Human Oversight)\n"
        )
        section += (
            "- Documentation of human decision based on AI output "
            "(EU GMP Annex 11 Section 7 — Data Storage and Integrity)\n"
        )
    else:
        section += (
            "- System-generated audit log entry "
            "(EU GMP Annex 11 Section 9 — Audit Trails)\n"
        )
        section += (
            "- User acknowledgment of informational nature of output "
            "(Regulatory reference: Industry best practice — "
            "no specific article applicable)\n"
        )
    section += "\n"

    # (e) Consequences of Non-Compliance
    section += "**(e) Consequences of Non-Compliance**\n\n"
    section += (
        "- Non-compliance events are recorded in the immutable audit trail "
        "(Phase 6.3) and flagged for quality review\n"
    )
    section += (
        "- Compliance scorecard (Phase 5.2) is updated to reflect the "
        "deviation, impacting the user's compliance rating\n"
    )
    if tier == "high":
        section += (
            "- Unauthorized use of High-tier AI outputs may result in "
            "regulatory non-compliance findings and corrective action "
            "requirements\n"
        )
        section += (
            "- Bypassing HITL checkpoints constitutes a critical deviation "
            "requiring immediate investigation\n"
        )
    elif tier == "medium":
        section += (
            "- Failure to acknowledge HITL checkpoints is logged as a "
            "minor deviation requiring documented justification\n"
        )
    else:
        section += (
            "- Misuse of informational outputs as controlled records "
            "constitutes a documentation integrity violation\n"
        )
    section += "\n"

    return section


def assemble_policy_sections(
    risk_context: RiskFrameworkContext,
    sector_module: SectorModule | None = None,
) -> str:
    """Assemble all Policy_Sections for active AI task types.

    Args:
        risk_context: Aggregated risk framework data.
        sector_module: Optional sector module for sector-specific overlays.

    Returns:
        Markdown string containing all policy sections.
    """
    section = "\n---\n\n## AI Feature Usage Policies\n\n"
    section += (
        "Each AI feature has a dedicated policy section defining permitted "
        "uses, restrictions, compliance procedures, required evidence, and "
        "consequences of non-compliance.\n\n"
    )

    for task_type in risk_context.task_types:
        tid = task_type.task_type_id
        tier = risk_context.effective_tiers.get(tid, "low")
        tier_def = risk_context.tier_definitions.get(tier)
        risk_factors = risk_context.risk_factors_map.get(tid, [])
        section += assemble_policy_section(
            task_type, tier, tier_def, risk_factors, sector_module
        )

    return section


def assemble_human_oversight_requirements(
    risk_context: RiskFrameworkContext,
) -> str:
    """Assemble the Human Oversight Requirements section.

    Args:
        risk_context: Aggregated risk framework data.

    Returns:
        Markdown string for the human oversight section.
    """
    section = "\n---\n\n## Human Oversight Requirements\n\n"
    section += (
        "Human oversight is a fundamental requirement of the EU AI Act "
        "(Article 14) and is enforced through AlcoaBase's HITL checkpoint "
        "system. The level of oversight varies by risk tier.\n\n"
    )
    section += "| Risk Tier | HITL Required | Blocks Visibility | Review Type |\n"
    section += "|-----------|---------------|-------------------|-------------|\n"
    section += (
        "| High | Yes | Yes — output hidden until approved | "
        "Full review with electronic signature "
        "(EU AI Act Article 14 — Human Oversight) |\n"
    )
    section += (
        "| Medium | Yes | No — output visible, acknowledgment required | "
        "Acknowledgment review "
        "(EU AI Act Article 14 — Human Oversight) |\n"
    )
    section += (
        "| Low | No | No — immediate visibility | "
        "User discretion "
        "(Regulatory reference: Industry best practice — "
        "no specific article applicable) |\n"
    )
    section += "\n"
    section += (
        "**Key Principle:** No AI-generated output classified as High-tier "
        "shall be visible to end users or enter controlled document workflows "
        "without explicit human review and approval "
        "(EU AI Act Article 14 — Human Oversight; "
        "21 CFR 11.10(k) — Authority Checks).\n"
    )
    return section


def assemble_audit_requirements() -> str:
    """Assemble the Audit and Evidence Requirements section.

    Returns:
        Markdown string for the audit requirements section.
    """
    section = "\n---\n\n## Audit and Evidence Requirements\n\n"
    section += (
        "All AI operations within AlcoaBase are subject to comprehensive "
        "audit logging in compliance with ALCOA+ data integrity principles "
        "(EU GMP Annex 11 Section 9 — Audit Trails; "
        "21 CFR 11.10(e) — Audit Trails).\n\n"
    )
    section += "### Audit Depth by Tier\n\n"
    section += "| Tier | Audit Depth | Records Captured |\n"
    section += "|------|-------------|------------------|\n"
    section += (
        "| High | Full | Request parameters, input data, model version, "
        "output content, HITL decision, reviewer identity, timestamps, "
        "electronic signature "
        "(21 CFR 11.10(e) — Audit Trails) |\n"
    )
    section += (
        "| Medium | Standard | Request parameters, output summary, "
        "HITL acknowledgment, timestamps "
        "(EU GMP Annex 11 Section 9 — Audit Trails) |\n"
    )
    section += (
        "| Low | Minimal | Request timestamp, user identity, "
        "operation type "
        "(EU GMP Annex 11 Section 9 — Audit Trails) |\n"
    )
    section += "\n"
    section += (
        "**Retention:** All audit records are retained for the duration "
        "specified by the regulatory retention policy (minimum 15 years for "
        "GxP records) (21 CFR 11.10(b) — Accurate and Complete Copies).\n\n"
    )
    section += (
        "**Immutability:** Audit trail entries cannot be modified or deleted. "
        "No DELETE endpoints are exposed for audit tables "
        "(EU GMP Annex 11 Section 9 — Audit Trails).\n"
    )
    return section


def assemble_prohibited_uses() -> str:
    """Assemble the Prohibited Uses section.

    Returns:
        Markdown string for the prohibited uses section.
    """
    section = "\n---\n\n## Prohibited Uses\n\n"
    section += (
        "The following operations are explicitly prohibited regardless of "
        "risk tier assignment. Violations constitute critical deviations "
        "requiring immediate investigation and corrective action.\n\n"
    )
    for i, use in enumerate(PROHIBITED_USES, 1):
        section += f"{i}. **{use}**\n"
    section += "\n"
    section += (
        "Any attempt to perform a prohibited operation is blocked by system "
        "controls and logged as a critical audit event "
        "(EU AI Act Article 14 — Human Oversight; "
        "21 CFR 11.10(k) — Authority Checks).\n"
    )
    return section


def assemble_roles_and_responsibilities() -> str:
    """Assemble the Roles and Responsibilities section.

    Returns:
        Markdown string for the roles and responsibilities section.
    """
    section = "\n---\n\n## Roles and Responsibilities\n\n"
    section += (
        "| Responsibility | Assigned Role | Regulatory Basis |\n"
        "|---------------|---------------|------------------|\n"
        "| Approving AI outputs (HITL reviewer) | quality_manager, "
        "document_administrator | EU AI Act Article 14 — Human Oversight |\n"
        "| Monitoring compliance | quality_manager | "
        "EU GMP Annex 11 Section 1 — Risk Management |\n"
        "| Configuring risk profiles | system_administrator, "
        "document_administrator | "
        "EU AI Act Article 9 — Risk Management System |\n"
        "| Conducting periodic reviews | quality_manager, "
        "system_administrator | "
        "EU AI Act Article 61 — Post-Market Monitoring |\n"
        "| Investigating deviations | quality_manager | "
        "21 CFR 11.10(k) — Authority Checks |\n"
        "| Maintaining audit trail integrity | system_administrator | "
        "21 CFR 11.10(e) — Audit Trails |\n"
    )
    return section


def assemble_periodic_review() -> str:
    """Assemble the Periodic Review section.

    Returns:
        Markdown string for the periodic review section.
    """
    section = "\n---\n\n## Periodic Review\n\n"
    section += (
        "This guideline document must be reviewed within the period defined "
        "by the `review_cycle_days` setting (default: 365 days) from the ALC "
        "regulatory baseline configuration, or whenever the Company Risk "
        "Profile is modified (tier override added, removed, or changed), "
        "whichever occurs first "
        "(EU AI Act Article 61 — Post-Market Monitoring).\n\n"
    )
    section += "**Review triggers:**\n\n"
    section += "- Annual review cycle expiration (review_cycle_days setting)\n"
    section += "- Company Risk Profile modification (tier override change)\n"
    section += "- New AI task type registration\n"
    section += "- Regulatory framework update or new guidance publication\n"
    section += "- Significant incident or deviation related to AI operations\n"
    return section


def assemble_glossary() -> str:
    """Assemble the Glossary section.

    Returns:
        Markdown string for the glossary section.
    """
    section = "\n---\n\n## Glossary\n\n"
    section += "| Term | Definition |\n"
    section += "|------|------------|\n"
    section += (
        "| ALCOA+ | Attributable, Legible, Contemporaneous, Original, "
        "Accurate + Complete, Consistent, Enduring, Available |\n"
    )
    section += (
        "| HITL | Human-In-The-Loop — a checkpoint requiring human review "
        "before AI output is accepted |\n"
    )
    section += (
        "| Risk Tier | Classification level (High, Medium, Low) determining "
        "the control set applied to an AI operation |\n"
    )
    section += (
        "| Control Set | Collection of controls (HITL, audit depth, "
        "validations, labeling, expiry, rate limits) for a risk tier |\n"
    )
    section += (
        "| Policy Section | A discrete section covering one AI feature's "
        "usage policy with 5 mandatory subsections |\n"
    )
    section += (
        "| GxP | Good Practice regulations (GMP, GLP, GCP) governing "
        "pharmaceutical and medical device industries |\n"
    )
    section += (
        "| CSV | Computer System Validation — formal process to ensure "
        "computerised systems meet regulatory requirements |\n"
    )
    section += (
        "| RAG | Retrieval-Augmented Generation — AI technique combining "
        "document retrieval with language model generation |\n"
    )
    return section


def assemble_urs_references(
    urs_available: bool,
    risk_context: RiskFrameworkContext,
) -> str:
    """Assemble the URS Traceability References section.

    Args:
        urs_available: Whether the Enhanced URS document exists.
        risk_context: Risk framework context for module references.

    Returns:
        Markdown string for the URS references section.
    """
    section = "\n---\n\n## URS Traceability References\n\n"

    if not urs_available:
        section += (
            "> **Notice:** URS cross-references unavailable — generate URS "
            "(Phase 8.3) for full traceability.\n"
        )
        return section

    section += (
        "The following URS Requirement_IDs are cross-referenced from the "
        "Enhanced User Requirement Specifications (Phase 8.3) to establish "
        "traceability between this guideline and formal requirements.\n\n"
    )

    # Map module references to URS requirement IDs
    module_map: dict[str, str] = {
        "5.4": "GEN",
        "5.2": "MAA",
        "5.3": "ATE",
        "5.5": "CIA",
        "5.6": "TRC",
        "4.2": "RAG",
        "4.1": "SRCH",
        "2.4": "PDF",
    }

    for i, task_type in enumerate(risk_context.task_types, 1):
        module_ref = task_type.module_reference
        module_code = module_map.get(module_ref, "AI")
        req_id = f"REQ-{module_code}-{i:02d}"
        section += (
            f"- **{task_type.display_name}**: Implements: {req_id}\n"
        )

    return section


def assemble_regulatory_reference_table(
    frameworks: list[RegulatoryFramework],
) -> str:
    """Assemble the Regulatory Reference Table section.

    Lists all cited regulations with article references, requirement
    summaries, and how ALC addresses each requirement.

    Args:
        frameworks: List of regulatory frameworks to include.

    Returns:
        Markdown string for the regulatory reference table section.
    """
    section = "\n---\n\n## Regulatory Reference Table\n\n"
    section += (
        "| Regulation | Article/Section | Requirement Summary | "
        "ALC Implementation |\n"
    )
    section += (
        "|------------|-----------------|--------------------"
        "|--------------------|\n"
    )

    # ALC implementation descriptions per framework
    alc_implementations: dict[str, str] = {
        "EU_AI_Act": (
            "Risk-based tiering with HITL checkpoints, audit trails, "
            "and quality management integration"
        ),
        "FDA_21CFR11": (
            "Electronic signatures (PAdES), validated systems, "
            "immutable audit trails, authority checks"
        ),
        "EU_GMP_Annex11": (
            "Computerised system validation, data integrity controls, "
            "risk-based security, audit trail enforcement"
        ),
        "ISO_13485": (
            "Design control integration, software validation, "
            "process monitoring, QMS documentation"
        ),
        "IVDR_2017_746": (
            "Performance evaluation documentation, conformity assessment "
            "support, clinical evidence management"
        ),
    }

    for fw in frameworks:
        impl = alc_implementations.get(fw.identifier, "Implemented via ALC controls")
        for article in fw.key_articles:
            section += (
                f"| {fw.display_name} | {article} | "
                f"Regulatory requirement for {article.split(' — ')[-1] if ' — ' in article else article} | "
                f"{impl} |\n"
            )

    return section


def assemble_sector_regulatory_context(
    sector: SectorModule,
) -> str:
    """Assemble the Sector Regulatory Context section.

    Args:
        sector: The sector module configuration.

    Returns:
        Markdown string for the sector regulatory context section.
    """
    section = "\n---\n\n## Sector Regulatory Context\n\n"
    section += (
        f"This section details the regulatory frameworks applicable to "
        f"AI usage within the {sector.sector_label} regulatory environment. "
        f"Each regulation listed below includes specific article references "
        f"that inform the sector-specific controls in this guideline.\n\n"
    )
    for reg in sector.applicable_regulations:
        section += f"### {reg.display_name}\n\n"
        for article in reg.key_articles:
            section += f"- {article}\n"
        section += "\n"
    return section


def assemble_sector_risk_considerations(
    sector: SectorModule,
    risk_context: RiskFrameworkContext,
) -> str:
    """Assemble the Sector-Specific Risk Considerations section.

    Adds at least one additional risk factor per AI task type beyond
    the base framework risk factors.

    Args:
        sector: The sector module configuration.
        risk_context: Aggregated risk framework data.

    Returns:
        Markdown string for the sector risk considerations section.
    """
    section = "\n---\n\n## Sector-Specific Risk Considerations\n\n"
    section += (
        f"The {sector.sector_label} regulatory environment introduces "
        f"additional risk factors beyond the base AI Risk & Compliance "
        f"Framework. These sector-specific considerations may elevate "
        f"risk tier recommendations for certain AI operations.\n\n"
    )

    # Sector-specific additional risk factors per task type
    sector_risk_factors: dict[str, dict[str, str]] = {
        "pharma_gmp": {
            "document_generation": (
                "GMP data integrity requirements (ALCOA+) impose additional "
                "validation burden on AI-generated batch records and SOPs"
            ),
            "multi_agent_audit": (
                "GMP audit findings directly impact product release decisions "
                "and regulatory inspection outcomes"
            ),
            "training_content_generation": (
                "GMP personnel qualification requirements demand verified "
                "competency; AI training materials must meet GMP standards"
            ),
            "change_impact_analysis": (
                "GMP change control procedures require comprehensive impact "
                "assessment for any process modification"
            ),
            "traceability_gap_discovery": (
                "GMP traceability requirements extend to all quality-critical "
                "records and their interdependencies"
            ),
            "rag_knowledge_query": (
                "GMP document retrieval must ensure only current, approved "
                "versions are referenced in responses"
            ),
            "document_search": (
                "GMP search results must respect document lifecycle status "
                "to prevent use of superseded content"
            ),
            "template_analysis": (
                "GMP template validation requires formal qualification of "
                "any automated analysis tools"
            ),
        },
        "medtech_iso13485": {
            "document_generation": (
                "Design control requirements (ISO 13485 Section 7.3) mandate "
                "formal review of all design inputs including AI-generated content"
            ),
            "multi_agent_audit": (
                "Medical device QMS audits must comply with ISO 13485 internal "
                "audit requirements and notified body expectations"
            ),
            "training_content_generation": (
                "IEC 62304 software lifecycle training must address safety "
                "classification-specific competency requirements"
            ),
            "change_impact_analysis": (
                "MDR Article 83 vigilance requirements demand comprehensive "
                "impact assessment for device-related changes"
            ),
            "traceability_gap_discovery": (
                "ISO 13485 design traceability requirements extend from user "
                "needs through verification and validation records"
            ),
            "rag_knowledge_query": (
                "Medical device technical documentation queries must respect "
                "design history file integrity and version control"
            ),
            "document_search": (
                "ISO 13485 document control requires search results to "
                "clearly indicate document approval status"
            ),
            "template_analysis": (
                "Design control templates must be validated per ISO 13485 "
                "Section 4.1.6 software validation requirements"
            ),
        },
        "ivd_ivdr": {
            "document_generation": (
                "IVDR Article 56 performance study documentation requires "
                "validated generation processes for IVD technical files"
            ),
            "multi_agent_audit": (
                "IVDR Article 48 conformity assessment documentation must "
                "demonstrate complete quality system compliance"
            ),
            "training_content_generation": (
                "IVDR Annex XIII clinical evidence requirements extend to "
                "personnel competency for performance evaluation tasks"
            ),
            "change_impact_analysis": (
                "IVDR post-market performance follow-up requires systematic "
                "impact assessment for any IVD modification"
            ),
            "traceability_gap_discovery": (
                "IVDR common specifications require complete traceability "
                "from intended purpose through performance evaluation"
            ),
            "rag_knowledge_query": (
                "IVD performance evaluation queries must reference only "
                "validated analytical data and approved specifications"
            ),
            "document_search": (
                "IVDR documentation search must distinguish between "
                "self-certified and notified body-assessed documents"
            ),
            "template_analysis": (
                "IVD common specification templates require validation "
                "against IVDR Article 9 requirements"
            ),
        },
    }

    factors = sector_risk_factors.get(sector.sector_id, {})

    for task_type in risk_context.task_types:
        tid = task_type.task_type_id
        tier = risk_context.effective_tiers.get(tid, "low")
        section += f"### {task_type.display_name}\n\n"
        section += f"- **Base Risk Tier:** {tier.capitalize()}\n"
        additional_factor = factors.get(
            tid,
            f"{sector.sector_label} regulatory requirements apply additional "
            f"controls to this operation type",
        )
        section += f"- **Additional Sector Risk Factor:** {additional_factor}\n"
        if tid in sector.risk_elevation_rules:
            section += (
                f"- **Elevation Recommendation:** "
                f"{sector.risk_elevation_rules[tid]}\n"
            )
        section += "\n"

    return section


def assemble_sector_risk_mapping_table(
    sector: SectorModule,
    risk_context: RiskFrameworkContext,
) -> str:
    """Assemble the Sector Risk Mapping Table.

    Maps each AI task type to its base tier, sector elevation recommendation,
    additional controls, and regulatory reference.

    Args:
        sector: The sector module configuration.
        risk_context: Aggregated risk framework data.

    Returns:
        Markdown string for the sector risk mapping table.
    """
    section = "\n---\n\n## Sector Risk Mapping Table\n\n"
    section += (
        "| AI Task Type | Base Risk Tier | Sector Elevation | "
        "Additional Controls | Regulatory Reference |\n"
    )
    section += (
        "|-------------|---------------|------------------|"
        "--------------------|-----------------------|\n"
    )

    for task_type in risk_context.task_types:
        tid = task_type.task_type_id
        base_tier = risk_context.effective_tiers.get(tid, "low")

        if tid in sector.risk_elevation_rules:
            elevation = _get_elevation_recommendation(base_tier)
            additional = _get_additional_controls(sector, tid)
            reg_ref = sector.risk_elevation_rules[tid].split(" requires")[0]
        else:
            elevation = "No elevation"
            additional = "None — base controls sufficient"
            reg_ref = (
                "Regulatory reference: Industry best practice — "
                "no specific article applicable"
            )

        section += (
            f"| {task_type.display_name} | {base_tier.capitalize()} | "
            f"{elevation} | {additional} | {reg_ref} |\n"
        )

    return section


def _get_elevation_recommendation(base_tier: str) -> str:
    """Get the sector elevation recommendation based on base tier.

    Args:
        base_tier: The base risk tier.

    Returns:
        Elevation recommendation string.
    """
    if base_tier == "low":
        return "Elevate to Medium"
    elif base_tier == "medium":
        return "Elevate to High"
    else:
        return "No elevation"


def _get_additional_controls(
    sector: SectorModule, task_type_id: str
) -> str:
    """Get additional sector-specific controls for an elevated task type.

    Args:
        sector: The sector module configuration.
        task_type_id: The task type identifier.

    Returns:
        Description of additional controls.
    """
    controls: dict[str, dict[str, str]] = {
        "pharma_gmp": {
            "document_generation": (
                "GMP data integrity review, CSV qualification evidence"
            ),
            "multi_agent_audit": (
                "GMP audit trail verification, validated system evidence"
            ),
            "training_content_generation": (
                "GMP competency assessment validation, ICH Q10 compliance check"
            ),
        },
        "medtech_iso13485": {
            "document_generation": (
                "Design input review per ISO 13485 Section 7.3"
            ),
            "change_impact_analysis": (
                "MDR vigilance assessment, post-market surveillance review"
            ),
            "traceability_gap_discovery": (
                "IEC 62304 software risk traceability verification"
            ),
        },
        "ivd_ivdr": {
            "document_generation": (
                "IVDR performance study documentation review"
            ),
            "multi_agent_audit": (
                "IVDR conformity assessment documentation verification"
            ),
            "training_content_generation": (
                "IVDR clinical evidence competency verification"
            ),
        },
    }
    sector_controls = controls.get(sector.sector_id, {})
    return sector_controls.get(task_type_id, "Sector-specific review required")


def assemble_validation_requirements(sector: SectorModule) -> str:
    """Assemble the Validation Requirements section for a sector guideline.

    Args:
        sector: The sector module configuration.

    Returns:
        Markdown string for the validation requirements section.
    """
    section = "\n---\n\n## Validation Requirements\n\n"
    section += (
        f"AI systems operating within the {sector.sector_label} regulatory "
        f"environment must meet the following validation expectations to "
        f"ensure outputs are fit for their intended purpose.\n\n"
    )

    validation_content: dict[str, str] = {
        "pharma_gmp": (
            "### GMP Validation Expectations\n\n"
            "- AI systems must be validated per EU GMP Annex 11 Section 4 "
            "requirements for computerised systems "
            "(EU GMP Annex 11 Section 4 — Validation)\n"
            "- Validation must follow GAMP 5 risk-based approach with "
            "software categorization (Category 3, 4, or 5) "
            "(Regulatory reference: Industry best practice — "
            "no specific article applicable)\n"
            "- Acceptance criteria must be predefined for each AI output type "
            "(EU GMP Annex 11 Section 4 — Validation)\n"
            "- Periodic revalidation is required when AI models are updated "
            "(EU GMP Annex 11 Section 4 — Validation)\n"
            "- Validation documentation must include IQ, OQ, and PQ protocols "
            "(21 CFR 11.10(a) — Validation of Systems)\n"
        ),
        "medtech_iso13485": (
            "### ISO 13485 Validation Expectations\n\n"
            "- AI systems must be validated per ISO 13485 Section 4.1.6 "
            "software validation requirements "
            "(ISO 13485 Section 4.1.6 — Software Validation)\n"
            "- Software safety classification per IEC 62304 determines "
            "validation rigor (Class A, B, or C) "
            "(IEC 62304 Section 5 — Software Development Process)\n"
            "- Design verification and validation must include AI component "
            "testing (ISO 13485 Section 7.3 — Design and Development)\n"
            "- Acceptance criteria must address intended use and foreseeable "
            "misuse scenarios "
            "(ISO 13485 Section 7.5.6 — Validation of Processes)\n"
            "- Validation records must be maintained in the design history "
            "file (FDA 21 CFR 820 §820.30 — Design Controls)\n"
        ),
        "ivd_ivdr": (
            "### IVDR Validation Expectations\n\n"
            "- AI systems supporting IVD processes must demonstrate "
            "analytical performance per IVDR Article 56 "
            "(IVDR Article 56 — Performance Studies)\n"
            "- Validation must address sensitivity, specificity, and "
            "reproducibility of AI-assisted analyses "
            "(IVDR Annex XIII — Clinical Evidence and Performance Evaluation)\n"
            "- Common specifications compliance must be verified for "
            "AI-generated IVD documentation "
            "(IVDR Article 9 — Common Specifications)\n"
            "- Performance evaluation data must support the intended purpose "
            "claims (IVDR Article 56 — Performance Studies)\n"
            "- Validation must be repeated when AI models are retrained or "
            "updated (IVDR Article 9 — Common Specifications)\n"
        ),
    }

    section += validation_content.get(
        sector.sector_id,
        "Validation requirements per applicable sector regulations.\n",
    )
    return section


def assemble_record_keeping_requirements(sector: SectorModule) -> str:
    """Assemble the Record Keeping Requirements section for a sector guideline.

    Args:
        sector: The sector module configuration.

    Returns:
        Markdown string for the record keeping requirements section.
    """
    section = "\n---\n\n## Record Keeping Requirements\n\n"
    section += (
        f"Records generated by AI operations within the {sector.sector_label} "
        f"environment must comply with the following retention and format "
        f"requirements.\n\n"
    )

    record_content: dict[str, str] = {
        "pharma_gmp": (
            "- **Retention Period:** Minimum 15 years for GxP-relevant records, "
            "or product lifecycle + 1 year, whichever is longer "
            "(21 CFR 11.10(b) — Accurate and Complete Copies)\n"
            "- **Format:** Electronic records must be maintained in validated "
            "systems with audit trail capability "
            "(EU GMP Annex 11 Section 7 — Data Storage and Integrity)\n"
            "- **Integrity:** All records must maintain ALCOA+ data integrity "
            "principles throughout their lifecycle "
            "(EU GMP Annex 11 Section 7 — Data Storage and Integrity)\n"
            "- **Backup:** Regular backup with verified restoration capability "
            "(EU GMP Annex 11 Section 7 — Data Storage and Integrity)\n"
            "- **Access:** Records must be readily retrievable for regulatory "
            "inspection within 24 hours "
            "(21 CFR 11.10(b) — Accurate and Complete Copies)\n"
        ),
        "medtech_iso13485": (
            "- **Retention Period:** Minimum lifetime of the medical device "
            "plus 15 years, or as specified by applicable regulations "
            "(ISO 13485 Section 4.2.5 — Control of Records)\n"
            "- **Format:** Records must be legible, readily identifiable, "
            "and retrievable "
            "(ISO 13485 Section 4.2.5 — Control of Records)\n"
            "- **Design History:** AI-related design records must be "
            "maintained in the Design History File "
            "(FDA 21 CFR 820 §820.30 — Design Controls)\n"
            "- **Traceability:** Records must support complete traceability "
            "from user needs through verification "
            "(ISO 13485 Section 7.3 — Design and Development)\n"
            "- **Post-Market:** Surveillance records must be maintained for "
            "the device lifetime "
            "(MDR 2017/745 Article 83 — Vigilance Requirements)\n"
        ),
        "ivd_ivdr": (
            "- **Retention Period:** Minimum 10 years after the last IVD "
            "device is placed on the market "
            "(IVDR Article 10 — General Obligations)\n"
            "- **Format:** Technical documentation must be maintained in "
            "structured, searchable format "
            "(IVDR Article 48 — Conformity Assessment Procedures)\n"
            "- **Performance Data:** All performance evaluation records must "
            "be retained and accessible to notified bodies "
            "(IVDR Article 56 — Performance Studies)\n"
            "- **Clinical Evidence:** Records supporting clinical evidence "
            "claims must be complete and traceable "
            "(IVDR Annex XIII — Clinical Evidence and Performance Evaluation)\n"
            "- **Common Specifications:** Compliance records for common "
            "specifications must be maintained separately "
            "(IVDR Article 9 — Common Specifications)\n"
        ),
    }

    section += record_content.get(
        sector.sector_id,
        "Record keeping per applicable sector regulations.\n",
    )
    return section


def assemble_dedicated_subsections(sector: SectorModule) -> str:
    """Assemble the dedicated subsections for a sector guideline.

    Each sector has 4 dedicated subsections covering sector-specific topics.

    Args:
        sector: The sector module configuration.

    Returns:
        Markdown string for all dedicated subsections.
    """
    section = "\n---\n\n## Dedicated Sector Subsections\n\n"

    subsection_content: dict[str, list[str]] = {
        "pharma_gmp": [
            (
                "### GMP Data Integrity Requirements (ALCOA+ Applied to AI Outputs)\n\n"
                "AI outputs within GMP-regulated processes must comply with ALCOA+ "
                "data integrity principles as defined in EU GMP Annex 11 Section 7. "
                "This means all AI-generated records must be:\n\n"
                "- **Attributable:** Linked to the requesting user and the AI system "
                "that produced the output (EU GMP Annex 11 Section 7 — Data Storage "
                "and Integrity)\n"
                "- **Legible:** Presented in human-readable format with clear "
                "identification of AI-generated content\n"
                "- **Contemporaneous:** Timestamped at the moment of generation with "
                "server-synchronized UTC time\n"
                "- **Original:** Stored as the primary record in the validated system "
                "with cryptographic integrity verification\n"
                "- **Accurate:** Validated against acceptance criteria before entering "
                "controlled workflows\n\n"
                "All AI operations must maintain complete audit trails demonstrating "
                "compliance with these principles throughout the record lifecycle.\n"
            ),
            (
                "### Computer System Validation Expectations for AI-Assisted Processes\n\n"
                "AI components within AlcoaBase are classified under GAMP 5 software "
                "categories for validation purposes "
                "(Regulatory reference: Industry best practice — "
                "no specific article applicable):\n\n"
                "- **Category 3 (Non-configured):** AI inference engine (vLLM) — "
                "validated through installation qualification and operational testing\n"
                "- **Category 4 (Configured):** Risk classification rules, tier "
                "definitions, control sets — validated through configuration "
                "verification and functional testing\n"
                "- **Category 5 (Custom):** Content generation logic, policy assembly "
                "functions — validated through full IQ/OQ/PQ lifecycle with "
                "documented test protocols\n\n"
                "Validation must be repeated when AI models are updated, retrained, "
                "or when system configuration changes affect AI behavior "
                "(EU GMP Annex 11 Section 4 — Validation).\n"
            ),
            (
                "### AI Model Qualification Requirements for GxP-Regulated Activities\n\n"
                "AI models used in GxP-regulated activities must undergo formal "
                "qualification following ICH Q9 risk assessment methodology "
                "(ICH Q9 Section 4 — Risk Assessment Methodology):\n\n"
                "- **Risk Identification:** Document potential failure modes of the "
                "AI model and their impact on product quality and patient safety\n"
                "- **Risk Analysis:** Assess probability and severity of each failure "
                "mode using the risk tier classification framework\n"
                "- **Risk Evaluation:** Determine acceptability of residual risk after "
                "control measures (HITL, validation, audit depth) are applied\n"
                "- **Risk Control:** Implement and verify effectiveness of control "
                "measures defined in the tier Control_Set\n\n"
                "Model qualification records must be maintained and reviewed during "
                "periodic guideline reviews or when models are updated.\n"
            ),
            (
                "### Change Control Procedures for AI Model Updates\n\n"
                "Any modification to AI models, configurations, or control parameters "
                "must follow EU GMP Chapter 4 change control requirements "
                "(EU GMP Chapter 4 Section 4.2 — Change Control Requirements):\n\n"
                "- **Change Request:** Document the proposed change, rationale, and "
                "expected impact on AI outputs and risk classifications\n"
                "- **Impact Assessment:** Evaluate effects on validated state, risk "
                "tier assignments, and downstream processes using Change Impact "
                "Analysis (Phase 5.5)\n"
                "- **Approval:** Obtain quality_manager approval before implementing "
                "changes to High-tier AI operations\n"
                "- **Implementation:** Execute change with full audit trail and "
                "revalidation as determined by impact assessment\n"
                "- **Verification:** Confirm AI system performs as expected after "
                "change implementation through defined acceptance criteria\n\n"
                "Emergency changes must be documented retrospectively within 24 hours "
                "and reviewed at the next periodic review.\n"
            ),
        ],
        "medtech_iso13485": [
            (
                "### Design Control Integration for AI Outputs as Design Inputs\n\n"
                "AI-generated outputs that serve as design inputs must comply with "
                "ISO 13485 Section 7.3 design and development requirements "
                "(ISO 13485 Section 7.3 — Design and Development):\n\n"
                "- **Design Input Review:** All AI-generated design inputs must be "
                "reviewed for adequacy, completeness, and unambiguity before "
                "acceptance into the design history file\n"
                "- **Verification:** AI outputs used as design inputs must be "
                "verified against user needs and intended use requirements\n"
                "- **Traceability:** Maintain bidirectional traceability between "
                "AI-generated inputs and downstream design outputs\n"
                "- **Change Control:** Any modification to AI-generated design "
                "inputs must follow the design change procedure\n\n"
                "Design input reviews must be documented with reviewer identity, "
                "date, and acceptance decision in the design history file "
                "(FDA 21 CFR 820 §820.30 — Design Controls).\n"
            ),
            (
                "### Software Lifecycle Requirements for AI Components (IEC 62304)\n\n"
                "AI components within AlcoaBase are classified per IEC 62304 safety "
                "classification for medical device software "
                "(IEC 62304 Section 5 — Software Development Process):\n\n"
                "- **Class A (No injury possible):** AI operations with Low risk tier "
                "where outputs are informational only\n"
                "- **Class B (Non-serious injury possible):** AI operations with "
                "Medium risk tier where outputs inform clinical decisions\n"
                "- **Class C (Death or serious injury possible):** AI operations with "
                "High risk tier where outputs directly affect patient safety\n\n"
                "Documentation requirements scale with safety classification:\n"
                "- Class A: Software development plan, requirements, testing\n"
                "- Class B: Above plus architecture, detailed design, integration testing\n"
                "- Class C: Above plus unit testing, code review, traceability matrix\n\n"
                "All AI software maintenance activities must follow IEC 62304 "
                "Section 6 maintenance process requirements "
                "(IEC 62304 Section 6 — Software Maintenance Process).\n"
            ),
            (
                "### Risk Management Integration (ISO 14971 Applied to AI Content)\n\n"
                "AI-generated content within the medical device QMS must be assessed "
                "using ISO 14971 risk management principles "
                "(IEC 62304 Section 7 — Software Risk Management Process):\n\n"
                "- **Hazard Identification:** Identify potential hazards from "
                "incorrect, incomplete, or misleading AI outputs that could affect "
                "device safety or performance\n"
                "- **Risk Estimation:** Estimate probability and severity of harm "
                "from each identified hazard, considering the AI risk tier\n"
                "- **Risk Evaluation:** Compare estimated risk against acceptability "
                "criteria defined in the risk management plan\n"
                "- **Risk Control:** Implement controls (HITL checkpoints, "
                "validation, audit depth) proportional to the risk level\n"
                "- **Residual Risk:** Document residual risk after controls and "
                "confirm overall benefit-risk is acceptable\n\n"
                "Risk management records must be maintained throughout the device "
                "lifecycle and updated when AI models change "
                "(MDR 2017/745 Article 10 — General Obligations of Manufacturers).\n"
            ),
            (
                "### Post-Market Surveillance for AI-Assisted Decisions\n\n"
                "AI-assisted decisions within the medical device QMS are subject to "
                "post-market surveillance requirements "
                "(MDR 2017/745 Article 83 — Vigilance Requirements):\n\n"
                "- **Monitoring:** Continuously monitor AI output quality and "
                "accuracy through compliance scorecards (Phase 5.2)\n"
                "- **Trend Analysis:** Analyze patterns in AI output rejections, "
                "HITL overrides, and deviation reports\n"
                "- **Incident Reporting:** Report any serious incident where AI "
                "output contributed to a safety concern per MDR vigilance timelines\n"
                "- **Corrective Action:** Implement CAPA when AI performance "
                "degrades below acceptance criteria\n"
                "- **Periodic Safety Update:** Include AI performance data in "
                "periodic safety update reports (PSUR)\n\n"
                "Post-market surveillance data must inform periodic guideline "
                "reviews and risk profile updates.\n"
            ),
        ],
        "ivd_ivdr": [
            (
                "### Performance Evaluation Requirements for AI-Assisted Analytical Processes\n\n"
                "AI systems supporting IVD analytical processes must demonstrate "
                "performance per IVDR Article 56 requirements "
                "(IVDR Article 56 — Performance Studies):\n\n"
                "- **Analytical Performance:** Validate sensitivity, specificity, "
                "accuracy, precision, and reproducibility of AI-assisted analyses\n"
                "- **Interference Testing:** Assess potential interference from "
                "AI processing on analytical results\n"
                "- **Stability:** Demonstrate consistent AI performance across "
                "different sample types and conditions\n"
                "- **Comparison Studies:** Compare AI-assisted results against "
                "reference methods or predicate devices\n"
                "- **Clinical Performance:** Validate diagnostic sensitivity and "
                "specificity when AI supports clinical decision-making\n\n"
                "Performance evaluation data must be included in the technical "
                "documentation and made available to notified bodies upon request.\n"
            ),
            (
                "### Common Specifications Compliance for AI-Generated IVD Documentation\n\n"
                "AI-generated documentation for IVD devices must comply with EU "
                "common specifications as defined in IVDR Article 9 "
                "(IVDR Article 9 — Common Specifications):\n\n"
                "- **Format Compliance:** AI-generated documents must follow the "
                "structure and content requirements of applicable common specifications\n"
                "- **Content Accuracy:** Generated content must accurately reflect "
                "the device's performance characteristics and intended purpose\n"
                "- **Deviation Justification:** Any deviation from common "
                "specifications must be explicitly justified with equivalent or "
                "superior evidence\n"
                "- **Update Tracking:** When common specifications are updated, "
                "AI-generated documentation must be regenerated and reviewed\n\n"
                "Compliance with common specifications must be documented and "
                "maintained as part of the conformity assessment evidence "
                "(IVDR Article 48 — Conformity Assessment Procedures).\n"
            ),
            (
                "### Clinical Evidence Requirements for AI-Supported Performance Studies\n\n"
                "When AI supports IVD performance studies, clinical evidence "
                "requirements per IVDR Annex XIII apply "
                "(IVDR Annex XIII — Clinical Evidence and Performance Evaluation):\n\n"
                "- **Study Design:** AI-assisted study designs must be reviewed "
                "and approved by qualified clinical personnel\n"
                "- **Data Integrity:** AI-processed clinical data must maintain "
                "full traceability to source specimens and results\n"
                "- **Statistical Analysis:** AI-generated statistical analyses "
                "must be validated against manual calculations for a representative "
                "subset\n"
                "- **Bias Assessment:** Evaluate and document potential AI bias "
                "in patient population selection or result interpretation\n"
                "- **Literature Review:** AI-assisted literature reviews must be "
                "verified by qualified personnel for completeness and relevance\n\n"
                "Clinical evidence generated with AI assistance must be clearly "
                "identified in the technical documentation.\n"
            ),
            (
                "### Notified Body Expectations for AI Usage Documentation\n\n"
                "Documentation of AI usage must meet notified body expectations "
                "for conformity assessment per IVDR Article 48 "
                "(IVDR Article 48 — Conformity Assessment Procedures):\n\n"
                "- **Transparency:** Clearly document where and how AI is used "
                "in the quality management system and technical documentation\n"
                "- **Validation Evidence:** Provide complete validation records "
                "for all AI systems used in regulated processes\n"
                "- **Risk Assessment:** Include AI-specific risk assessment in "
                "the overall risk management documentation\n"
                "- **Change History:** Maintain complete change history for AI "
                "models and configurations with impact assessments\n"
                "- **Performance Monitoring:** Demonstrate ongoing monitoring of "
                "AI system performance with defined acceptance criteria\n\n"
                "Notified bodies may request additional documentation or "
                "demonstrations of AI system behavior during assessment visits.\n"
            ),
        ],
    }

    content_list = subsection_content.get(sector.sector_id, [])
    for content in content_list:
        section += f"\n{content}\n"

    return section


def assemble_cross_references(
    sector: SectorModule,
    urs_available: bool,
    risk_context: RiskFrameworkContext,
) -> str:
    """Assemble the Cross-References section for a sector guideline.

    Args:
        sector: The sector module configuration.
        urs_available: Whether the Enhanced URS document exists.
        risk_context: Risk framework context for module references.

    Returns:
        Markdown string for the cross-references section.
    """
    section = "\n---\n\n## Cross-References\n\n"
    section += (
        f"This {sector.sector_label} sector guideline is supplementary to "
        f"the master cross-sector guideline and must be read in conjunction "
        f"with it.\n\n"
    )
    section += (
        f"- **Master Guideline:** {MASTER_GUIDELINE_TITLE}\n"
    )

    if urs_available:
        section += (
            "- **URS Document:** AlcoaBase — Enhanced User Requirement "
            "Specifications\n"
        )
        # Add URS requirement references
        module_map: dict[str, str] = {
            "5.4": "GEN",
            "5.2": "MAA",
            "5.3": "ATE",
            "5.5": "CIA",
            "5.6": "TRC",
            "4.2": "RAG",
            "4.1": "SRCH",
            "2.4": "PDF",
        }
        section += "\n**URS Requirement References:**\n\n"
        for i, task_type in enumerate(risk_context.task_types, 1):
            module_ref = task_type.module_reference
            module_code = module_map.get(module_ref, "AI")
            req_id = f"REQ-{module_code}-{i:02d}"
            section += (
                f"- {task_type.display_name}: Implements: {req_id}\n"
            )
    else:
        section += (
            "\n> **Notice:** URS cross-references unavailable — generate "
            "URS (Phase 8.3) for full traceability.\n"
        )

    return section


# ---------------------------------------------------------------------------
# Top-Level Document Assembly Functions
# ---------------------------------------------------------------------------


def assemble_master_guideline(
    risk_context: RiskFrameworkContext,
    version_number: int,
    urs_available: bool,
) -> str:
    """Assemble the complete master cross-sector guideline document.

    Combines all required sections in the specified order:
    Document Header, Purpose and Scope, Regulatory Framework Overview,
    Risk Classification Summary, AI Feature Usage Policies,
    Human Oversight Requirements, Audit and Evidence Requirements,
    Prohibited Uses, Roles and Responsibilities, Periodic Review,
    Glossary, URS Traceability References, Regulatory Reference Table.

    Args:
        risk_context: Aggregated risk framework data.
        version_number: Version number to embed in header.
        urs_available: Whether to include URS_Reference_Blocks.

    Returns:
        Complete master guideline Markdown string.
    """
    parts: list[str] = [
        assemble_document_header(
            MASTER_GUIDELINE_TITLE, version_number, REGULATORY_FRAMEWORKS
        ),
        assemble_purpose_and_scope(),
        assemble_regulatory_overview(REGULATORY_FRAMEWORKS),
        assemble_risk_classification_summary(risk_context),
        assemble_policy_sections(risk_context),
        assemble_human_oversight_requirements(risk_context),
        assemble_audit_requirements(),
        assemble_prohibited_uses(),
        assemble_roles_and_responsibilities(),
        assemble_periodic_review(),
        assemble_glossary(),
        assemble_urs_references(urs_available, risk_context),
        assemble_regulatory_reference_table(REGULATORY_FRAMEWORKS),
    ]
    return "\n".join(parts)


def assemble_sector_guideline(
    sector: SectorModule,
    risk_context: RiskFrameworkContext,
    version_number: int,
    urs_available: bool,
) -> str:
    """Assemble a complete sector-specific guideline document.

    Combines all required sector sections in the specified order:
    Document Header, Sector Regulatory Context, Sector-Specific Risk
    Considerations, AI Feature Usage Policies (with sector overlay),
    Sector Risk Mapping Table, Validation Requirements,
    Record Keeping Requirements, Dedicated Subsections,
    Roles and Responsibilities, Periodic Review,
    Cross-References, Regulatory Reference Table.

    Args:
        sector: The sector module configuration.
        risk_context: Aggregated risk framework data.
        version_number: Version number to embed in header.
        urs_available: Whether to include URS cross-references.

    Returns:
        Complete sector guideline Markdown string.
    """
    # Build the combined frameworks list for the reference table.
    # Sector guidelines cite cross-sector regulations (EU AI Act, etc.) in
    # shared policy sections and oversight/audit sections, so the reference
    # table must include those alongside sector-specific regulations to satisfy
    # Requirement 7.2 (>= 1 row per distinct regulation cited in body).
    sector_fw_ids = {fw.identifier for fw in sector.applicable_regulations}
    combined_frameworks = list(sector.applicable_regulations)
    for fw in REGULATORY_FRAMEWORKS:
        if fw.identifier not in sector_fw_ids:
            combined_frameworks.append(fw)

    parts: list[str] = [
        assemble_document_header(
            sector.title, version_number, sector.applicable_regulations
        ),
        assemble_sector_regulatory_context(sector),
        assemble_sector_risk_considerations(sector, risk_context),
        assemble_policy_sections(risk_context, sector_module=sector),
        assemble_sector_risk_mapping_table(sector, risk_context),
        assemble_validation_requirements(sector),
        assemble_record_keeping_requirements(sector),
        assemble_dedicated_subsections(sector),
        assemble_roles_and_responsibilities(),
        assemble_periodic_review(),
        assemble_cross_references(sector, urs_available, risk_context),
        assemble_regulatory_reference_table(combined_frameworks),
    ]
    return "\n".join(parts)
