# Requirements Document

## Introduction

This feature implements a Multi-Agent "Always-On" Auditing system that extends the existing Agent Registry (5.1) and Document Reviewer into a full parallel review orchestration pipeline. When a document is submitted for review, it is dispatched to N configured auditor agents in parallel. Each agent produces an independent review report with findings, severity ratings, and recommendations. A supervisory "Master Auditor" agent then synthesizes all individual reports into a unified executive summary with prioritized action items and an overall compliance score. The system includes company-specific audit profiles, a review dashboard with findings UI, compliance scorecards, missing link detection (training/signature gaps), and anomaly detection in audit logs.

## Glossary

- **Review_Pipeline**: An orchestrated sequence of parallel agent reviews followed by master summarization for a single document or set of documents. Persisted as a database record tracking status and results.
- **Review_Session**: A single execution of the review pipeline for one document, containing individual agent reports and the master summary.
- **Auditor_Agent**: An agent definition (from 5.1) with agent_type "review" that is assigned to a review pipeline to produce an independent review report.
- **Master_Auditor**: A specialized supervisory agent that receives all individual review reports and produces a unified executive summary with consensus findings, contradictions, and an overall compliance score.
- **Audit_Profile**: A company-scoped configuration that determines which auditor agents are assigned, what regulatory frameworks apply, severity thresholds, and required review quorum.
- **Review_Quorum**: The minimum number of agent reviews that must complete before the Master Auditor can produce a summary. Configurable per audit profile.
- **Compliance_Score**: A numeric score (0.0–100.0) representing overall audit readiness, computed from individual agent findings weighted by severity.
- **Compliance_Scorecard**: A per-company real-time dashboard metric showing the aggregate "Audit Readiness" score across all reviewed documents.
- **Missing_Link**: A document that is in "Approved" or "Active" status but lacks required training records (3.3) or electronic signatures (3.4).
- **Anomaly_Detection**: Automated monitoring of the audit trail for suspicious patterns such as back-dated signatures, workflow bypasses, or unusual access patterns.
- **Finding_Severity**: Classification of review findings: Critical, Major, Minor, Informational (reuses existing `FindingSeverity` enum from `document_reviewer.py`).
- **Review_Status**: Status of a review session: Pending, InProgress, Completed, Failed, Cancelled.
- **InferenceClient**: The existing async HTTP client for vLLM communication (from 4.3).
- **AgentRegistryService**: The existing agent registry with CRUD, archetypes, and tuning parameters (from 5.1).

## Requirements

### Requirement 1: Review Pipeline Orchestration

**User Story:** As a quality manager, I want to submit a document for multi-agent review and have it automatically dispatched to all configured auditor agents in parallel, so that I receive comprehensive, independent assessments without manual coordination.

#### Acceptance Criteria

1. THE Review_Pipeline SHALL accept a document submission containing: document_id, document_version_id, and an optional audit_profile_id override. If no audit_profile_id is provided, the pipeline SHALL use the company's default audit profile.
2. WHEN a document is submitted for review, THE Review_Pipeline SHALL resolve the list of assigned auditor agents from the active audit profile and dispatch review tasks to each agent in parallel using Celery async tasks.
3. THE Review_Pipeline SHALL create a Review_Session database record with status "Pending" upon submission, transition to "InProgress" when the first agent task begins, and transition to "Completed" when the Master Auditor summary is produced.
4. WHEN all individual agent reviews have completed (or the quorum threshold is met), THE Review_Pipeline SHALL automatically trigger the Master Auditor summarization step.
5. IF an individual agent review task fails (inference timeout, connection error, or invalid response), THEN THE Review_Pipeline SHALL mark that agent's review as "Failed" with the error reason, continue processing other agents, and still trigger the Master Auditor if the quorum is met with the remaining successful reviews.
6. IF fewer agent reviews complete successfully than the configured quorum, THEN THE Review_Pipeline SHALL mark the Review_Session as "Failed" with a message indicating insufficient quorum and listing which agents failed.
7. THE Review_Pipeline SHALL enforce a maximum review timeout of 30 minutes per individual agent review task. If an agent task exceeds this timeout, it SHALL be marked as "Failed" with reason "timeout".
8. THE Review_Pipeline SHALL expose a POST /api/reviews endpoint that initiates a review session and returns the session ID with HTTP 202 (Accepted).
9. THE Review_Pipeline SHALL expose a GET /api/reviews/{session_id} endpoint that returns the current review session status, individual agent report statuses, and the master summary (if completed).
10. THE Review_Pipeline SHALL scope all operations to the company identified by the X-Company-Id header, and the POST endpoint SHALL require the X-Change-Reason header.

### Requirement 2: Individual Agent Review Execution

**User Story:** As a system, I want each auditor agent to independently analyze a document using its configured personality, tuning parameters, and evaluation rubric, so that reviews reflect each agent's specialized expertise.

#### Acceptance Criteria

1. WHEN an auditor agent review task executes, THE system SHALL retrieve the document content from MinIO storage, the agent's contextual_tuning parameters from the AgentRegistryService, and the agent's evaluation_rubric (if defined).
2. THE system SHALL construct a review prompt that includes: the agent's system_prompt (with appended evaluation_rubric if present), the full document text content, and instructions to produce a structured JSON response containing findings, severity ratings, chapter assessments, and recommendations.
3. THE system SHALL invoke the InferenceClient.chat_completion() method with the agent's contextual_tuning parameters (temperature, max_tokens, top_p, frequency_penalty, presence_penalty) for the review inference call.
4. WHEN the inference response is received, THE system SHALL parse the response into a structured ReviewReport (reusing the existing model from document_reviewer.py) containing: findings (with severity, chapter, description, recommendation), chapter_results, overall_status, and summary.
5. IF the inference response cannot be parsed into a valid ReviewReport structure, THEN THE system SHALL mark the agent review as "Failed" with reason "invalid_response" and store the raw response text for debugging.
6. THE system SHALL persist each completed agent ReviewReport to the database with a foreign key to the Review_Session and the agent_definition_id.
7. THE system SHALL record the inference duration (wall-clock time from request to response) for each agent review for performance monitoring.

### Requirement 3: Master Auditor Summarization

**User Story:** As a quality manager, I want a supervisory agent to synthesize all individual review reports into a single executive summary that identifies consensus findings, flags contradictions, and provides a prioritized action list, so that I can quickly understand the overall compliance posture.

#### Acceptance Criteria

1. THE Master_Auditor SHALL be a predefined agent archetype with schema_version "2.0", archetype "Master Auditor", strictness 0.95, temperature 0.1, verbosity "detailed", and max_tokens 8192.
2. WHEN triggered, THE Master_Auditor SHALL receive as input: all individual agent ReviewReports (serialized as JSON), the document metadata (title, type, version, tags), and the company's regulatory framework.
3. THE Master_Auditor SHALL produce a MasterReviewSummary containing: consensus_findings (findings agreed upon by 2+ agents), contradictions (findings where agents disagree on severity or presence), prioritized_action_items (ordered by severity then frequency), overall_compliance_score (0.0–100.0), executive_summary (text), and risk_assessment (Critical/High/Medium/Low).
4. THE Master_Auditor SHALL compute the overall_compliance_score using the formula: 100 - (sum of severity_weights * finding_count), where severity_weights are: Critical=25, Major=10, Minor=3, Informational=0.5, capped at a minimum of 0.0.
5. THE Master_Auditor SHALL identify a finding as "consensus" when 2 or more individual agent reports contain findings with the same severity level referencing the same chapter/section.
6. THE Master_Auditor SHALL identify a "contradiction" when one agent reports a finding as Critical or Major for a chapter/section while another agent reports no finding or only Informational for the same chapter/section.
7. THE Master_Auditor SHALL persist the MasterReviewSummary to the database linked to the Review_Session.
8. IF the Master_Auditor inference call fails, THEN THE Review_Pipeline SHALL mark the session as "Completed" with a flag indicating "summary_failed", preserving all individual agent reports as still accessible.

### Requirement 4: Company-Specific Audit Profiles

**User Story:** As a company administrator, I want to configure audit profiles that determine which agents review our documents, what regulatory frameworks apply, and what quorum is required, so that reviews are tailored to our specific compliance needs.

#### Acceptance Criteria

1. THE system SHALL store Audit_Profiles in the database with the following fields: id, company_id, name (max 200 chars), description (max 2000 chars), regulatory_frameworks (array of strings, e.g., ["ISO 13485", "GMP", "GDP"]), assigned_agent_ids (array of agent definition IDs), quorum (integer, minimum 1), severity_thresholds (JSON object with keys critical, major, minor, informational mapping to numeric weights), is_default (boolean), is_active (boolean), created_at, updated_at.
2. THE system SHALL enforce that each company has exactly one audit profile with is_default=true. If a new profile is set as default, the previous default SHALL be unset.
3. THE system SHALL expose CRUD endpoints for audit profiles: POST /api/audit-profiles, GET /api/audit-profiles, GET /api/audit-profiles/{profile_id}, PUT /api/audit-profiles/{profile_id}, DELETE /api/audit-profiles/{profile_id} (soft-delete).
4. WHEN an audit profile is created or updated with assigned_agent_ids, THE system SHALL validate that all referenced agent IDs exist, are active, have agent_type "review", and belong to the same company (or are global agents activated for the company).
5. THE system SHALL validate that quorum does not exceed the number of assigned_agent_ids. If quorum > len(assigned_agent_ids), return HTTP 422 with an error message.
6. THE system SHALL scope all audit profile operations to the company identified by the X-Company-Id header, and all mutating requests SHALL require the X-Change-Reason header.
7. THE system SHALL provide a GET /api/audit-profiles/frameworks endpoint that returns the list of supported regulatory frameworks: ["ISO 13485", "GMP", "GDP", "GLP", "GCP", "ISO 9001", "ISO 14001", "21 CFR Part 11", "EU GMP Annex 11", "IVDR"].

### Requirement 5: Review Dashboard & Findings UI

**User Story:** As a quality manager, I want a dashboard showing review status per document, individual agent reports side-by-side, the master summary, a finding severity heatmap, and action item tracking, so that I can efficiently manage review outcomes.

#### Acceptance Criteria

1. THE ReviewDashboardPage SHALL display a list of all review sessions for the current company, showing: document title, document type, submission date, review status (Pending/InProgress/Completed/Failed), compliance score (if completed), and number of findings by severity.
2. WHEN a user clicks on a review session, THE ReviewDashboardPage SHALL display the session detail view containing: individual agent reports in a side-by-side comparison layout, the master summary with consensus findings and contradictions highlighted, and the prioritized action items list.
3. THE ReviewDashboardPage SHALL display a severity heatmap visualization showing finding distribution across document chapters/sections, with color coding: Critical (red), Major (orange), Minor (yellow), Informational (blue).
4. THE ReviewDashboardPage SHALL provide action item tracking where each action item can be marked as: Open, In Progress, Resolved, or Dismissed. Status changes SHALL require a change reason and be persisted to the database.
5. THE ReviewDashboardPage SHALL provide filtering by: review status, date range, document type, compliance score range, and assigned audit profile.
6. THE ReviewDashboardPage SHALL display real-time progress for in-progress reviews, showing which agents have completed and which are still running, with elapsed time per agent.
7. THE ReviewDashboardPage SHALL provide an "Approve" and "Reject" action for completed reviews. Approval/rejection SHALL require a change reason and update the review session status to "Approved" or "Rejected".

### Requirement 6: Compliance Scorecards

**User Story:** As a company administrator, I want a real-time "Audit Readiness" score for my company that aggregates compliance scores across all reviewed documents, so that I can monitor our overall compliance posture at a glance.

#### Acceptance Criteria

1. THE system SHALL compute a company-level Compliance_Scorecard by averaging the overall_compliance_score of all completed review sessions within the last 90 days (configurable per audit profile).
2. THE system SHALL expose a GET /api/compliance/scorecard endpoint that returns: overall_score (0.0–100.0), trend (improving/stable/declining based on 30-day comparison), total_documents_reviewed, documents_with_critical_findings, documents_with_open_action_items, score_by_document_type (breakdown), and last_updated timestamp.
3. THE system SHALL classify the overall_score into risk bands: Excellent (90–100), Good (75–89), Needs Attention (50–74), At Risk (25–49), Critical (0–24).
4. THE system SHALL recalculate the scorecard whenever a new review session completes or an action item status changes.
5. THE system SHALL scope the scorecard to the company identified by the X-Company-Id header.

### Requirement 7: Missing Link Detection

**User Story:** As a compliance officer, I want the system to proactively flag documents that are approved but missing required training records or electronic signatures, so that compliance gaps are identified before an external audit.

#### Acceptance Criteria

1. THE system SHALL provide a GET /api/compliance/missing-links endpoint that returns a list of documents in "Approved" or "Active" status that are missing: required training records (no valid training completion for the current document version), or required electronic signatures (document lacks a PAdES signature when the workflow requires one).
2. THE system SHALL check training record completeness by verifying that all users assigned to the document's training task (from 3.3) have a "Passed" training record for the current document version.
3. THE system SHALL check signature completeness by verifying that the document's current version has a valid PAdES signature when the document's workflow definition includes a signature gate.
4. THE system SHALL classify missing links by severity: "Critical" if both training and signature are missing, "Major" if either training or signature is missing.
5. THE system SHALL include in each missing link record: document_id, document_uuid, document_title, document_type, current_status, missing_items (array of "training" and/or "signature"), affected_user_count (for training gaps), and days_since_approval.
6. THE system SHALL scope missing link detection to the company identified by the X-Company-Id header.
7. THE Master_Auditor SHALL include missing link findings in its review summary when reviewing a document that has missing links, adding them as Critical or Major findings with recommendations to resolve the gaps.

### Requirement 8: Anomaly Detection in Audit Logs

**User Story:** As a compliance officer, I want the system to monitor the audit trail for suspicious patterns such as back-dated signatures, workflow bypasses, or unusual access patterns, so that potential compliance violations are flagged early.

#### Acceptance Criteria

1. THE system SHALL provide a Celery periodic task (running every 15 minutes) that scans the audit trail for anomalous patterns within the last 24 hours.
2. THE system SHALL detect the following anomaly types: "backdated_signature" (signature timestamp is more than 5 minutes before the audit log entry timestamp), "workflow_bypass" (document status changed without a corresponding workflow transition record), "bulk_approval" (same user approved more than 10 documents within a 1-hour window), "off_hours_mutation" (mutating operations performed outside configured business hours), and "rapid_version_churn" (more than 5 versions of the same document created within 1 hour).
3. WHEN an anomaly is detected, THE system SHALL create an AnomalyAlert database record containing: anomaly_type, severity (Critical for backdated_signature and workflow_bypass, Major for bulk_approval, Minor for off_hours_mutation and rapid_version_churn), description, affected_document_id (if applicable), affected_user_id (if applicable), detected_at timestamp, and is_resolved (boolean, default false).
4. THE system SHALL expose a GET /api/compliance/anomalies endpoint that returns anomaly alerts for the current company, filterable by: anomaly_type, severity, is_resolved, and date range.
5. THE system SHALL expose a PATCH /api/compliance/anomalies/{anomaly_id}/resolve endpoint that marks an anomaly as resolved with a required resolution_note and change reason.
6. THE system SHALL scope all anomaly detection and queries to the company identified by the X-Company-Id header.
7. THE system SHALL not generate duplicate anomaly alerts for the same event (deduplicate by anomaly_type + affected_document_id + affected_user_id + detection window).

### Requirement 9: Review Pipeline Database Models

**User Story:** As a backend developer, I want well-defined database models for review sessions, agent reviews, master summaries, audit profiles, action items, and anomaly alerts, so that all review data is persisted with full audit trail support.

#### Acceptance Criteria

1. THE ReviewSession model SHALL include: id, company_id (FK), document_id (FK), document_version_id (FK), audit_profile_id (FK), status (enum: Pending, InProgress, Completed, Failed, Approved, Rejected), submitted_by (FK to users), submitted_at, completed_at (nullable), compliance_score (nullable float 0.0–100.0), summary_failed (boolean default false), created_at, updated_at.
2. THE AgentReview model SHALL include: id, session_id (FK to ReviewSession), agent_definition_id (FK), status (enum: Pending, InProgress, Completed, Failed), report_data (JSONB storing the full ReviewReport), error_reason (nullable string), inference_duration_ms (nullable integer), started_at (nullable), completed_at (nullable), created_at.
3. THE MasterReviewSummary model SHALL include: id, session_id (FK to ReviewSession, unique), summary_data (JSONB storing the full MasterReviewSummary), compliance_score (float 0.0–100.0), risk_assessment (string), created_at.
4. THE AuditProfile model SHALL include: id, company_id (FK), name (String 200), description (Text nullable), regulatory_frameworks (JSON array), assigned_agent_ids (JSON array), quorum (integer), severity_thresholds (JSON), is_default (boolean), is_active (boolean), created_at, updated_at.
5. THE ActionItem model SHALL include: id, session_id (FK to ReviewSession), finding_id (string), title (String 500), description (Text), severity (string), status (enum: Open, InProgress, Resolved, Dismissed), assigned_to (nullable FK to users), resolved_at (nullable), resolution_note (nullable Text), created_at, updated_at.
6. THE AnomalyAlert model SHALL include: id, company_id (FK), anomaly_type (String 100), severity (String 50), description (Text), affected_document_id (nullable FK), affected_user_id (nullable FK), detected_at, is_resolved (boolean default false), resolved_at (nullable), resolution_note (nullable Text), created_at.
7. ALL models SHALL use the AuditMixin for SQLAlchemy-Continuum versioning where applicable (ReviewSession, AuditProfile, ActionItem).

### Requirement 10: Review Pipeline API Endpoints

**User Story:** As a frontend developer, I want comprehensive REST endpoints for managing review sessions, viewing results, and tracking action items, so that the review dashboard can be fully functional.

#### Acceptance Criteria

1. THE system SHALL expose POST /api/reviews that accepts {document_id, document_version_id, audit_profile_id (optional)} and returns HTTP 202 with {session_id, status: "Pending"}.
2. THE system SHALL expose GET /api/reviews that returns a paginated list of review sessions for the current company, supporting query params: status, document_type, date_from, date_to, min_score, max_score, limit (default 20), offset (default 0).
3. THE system SHALL expose GET /api/reviews/{session_id} that returns the full review session detail including: session metadata, list of agent reviews with their reports, and the master summary (if available).
4. THE system SHALL expose POST /api/reviews/{session_id}/approve and POST /api/reviews/{session_id}/reject that update the session status and require X-Change-Reason header.
5. THE system SHALL expose GET /api/reviews/{session_id}/action-items that returns action items for a session, and PATCH /api/reviews/{session_id}/action-items/{item_id} that updates an action item's status.
6. THE system SHALL expose POST /api/reviews/{session_id}/action-items that creates a new action item from a finding, accepting {finding_id, title, description, severity, assigned_to (optional)}.
7. THE system SHALL return HTTP 404 for review sessions that do not exist or do not belong to the requesting company.
8. THE system SHALL return HTTP 409 if a review is submitted for a document that already has an active (Pending or InProgress) review session.

### Requirement 11: Frontend Review Dashboard Components

**User Story:** As a quality manager, I want a polished review dashboard with real-time status updates, side-by-side report comparison, severity heatmaps, and action item management, so that I can efficiently oversee the review process.

#### Acceptance Criteria

1. THE ReviewDashboardPage SHALL be accessible at route /reviews and display a filterable list of review sessions with columns: Document, Type, Status (with color-coded badge), Score, Findings (grouped by severity icons), Submitted Date, and Actions.
2. THE ReviewSessionDetail component SHALL display: a progress tracker showing agent completion status, individual agent reports in expandable cards with findings tables, the master summary in a highlighted section, and a severity heatmap chart.
3. THE AgentReportComparison component SHALL display 2–4 agent reports side-by-side with synchronized scrolling, highlighting findings that appear in multiple reports (consensus) and findings that conflict between agents (contradictions).
4. THE SeverityHeatmap component SHALL render a grid visualization with chapters/sections on one axis and severity levels on the other, using color intensity to indicate finding density.
5. THE ActionItemTracker component SHALL display action items in a kanban-style board with columns: Open, In Progress, Resolved, Dismissed. Drag-and-drop between columns SHALL trigger status update with a change reason prompt.
6. THE ComplianceScorecard component SHALL display: the overall score as a large gauge/dial, the risk band label and color, trend indicator (arrow up/down/flat), and breakdown by document type as a bar chart.
7. THE ReviewDashboardPage SHALL use polling (every 10 seconds) to update in-progress review sessions without full page reload.
8. THE ReviewDashboardPage SHALL include a "Submit for Review" button on document detail pages that opens a modal to select an audit profile and confirm submission.

