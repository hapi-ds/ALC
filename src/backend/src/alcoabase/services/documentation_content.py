"""Documentation Suite content templates and section definitions.

Contains the template constants, section configurations, and content
assembly functions for generating User Guide and Admin Guide documents.
Content is deterministic and version-controlled; dynamic cross-reference
data is injected at generation time from governance document queries.

The module defines:
- USER_GUIDE_TITLE: Title for the User Guide document
- ADMIN_GUIDE_TITLE: Title for the Admin Guide document
- USER_GUIDE_SECTIONS: Ordered list of UserGuideSection configurations
- ADMIN_GUIDE_SECTIONS: Ordered list of AdminGuideSection configurations
- DOCUMENTATION_TAGS: Tags applied to both documents ["DOC-GUIDE", "ALC-GOV"]
- DOCUMENTATION_DOCUMENT_TYPE: Document type for both guides
- Template assembly functions for each document section

References:
    - Design: .kiro/specs/Step_8-5_documentation-suite-user-admin-guides/design.md
    - Requirements: 1.2–1.10, 2.2–2.10, 6.1–6.7, 7.1–7.7
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcedureBlock:
    """A numbered procedure within a guide section.

    Attributes:
        title: Descriptive title for the procedure (e.g., "Uploading a Document").
        steps: List of 3-15 numbered steps, each starting with a bold action verb.
        screenshot_slug: Kebab-case slug for the screenshot path.
    """

    title: str
    steps: list[str]
    screenshot_slug: str


@dataclass(frozen=True)
class UserGuideSection:
    """Configuration for a section in the User Guide.

    Attributes:
        section_id: Machine-readable identifier (e.g., "document-management").
        title: Human-readable section title.
        overview: Plain language overview (minimum 50 characters).
        procedures: List of ProcedureBlock instances for this section.
        tips: At least 2 practical recommendations.
        cross_ref_sections: Related section IDs within the guide.
        urs_requirement_ids: URS requirement IDs (e.g., ["REQ-DOC-01"]).
        ai_guidelines_ref: Whether to include AI guidelines cross-reference.
    """

    section_id: str
    title: str
    overview: str
    procedures: list[ProcedureBlock]
    tips: list[str]
    cross_ref_sections: list[str]
    urs_requirement_ids: list[str]
    ai_guidelines_ref: bool = False


@dataclass(frozen=True)
class AdminGuideSection:
    """Configuration for a section in the Admin Guide.

    Attributes:
        section_id: Machine-readable identifier (e.g., "user-management").
        title: Human-readable section title.
        overview: Administrative function overview (minimum 80 characters).
        prerequisites: Required roles/permissions for described operations.
        procedures: List of ProcedureBlock instances for this section.
        security_considerations: Audit implications and compliance impact.
        cross_ref_sections: Related admin section IDs.
        user_guide_refs: Related User Guide section IDs.
        urs_requirement_ids: URS requirement IDs.
        ai_guidelines_ref: Whether to include AI guidelines cross-reference.
    """

    section_id: str
    title: str
    overview: str
    prerequisites: list[str]
    procedures: list[ProcedureBlock]
    security_considerations: str
    cross_ref_sections: list[str]
    user_guide_refs: list[str]
    urs_requirement_ids: list[str]
    ai_guidelines_ref: bool = False


@dataclass
class CrossReferenceContext:
    """Aggregated cross-reference data for guide content assembly.

    Loaded once at the start of generation and passed to all content
    assembly functions to avoid repeated DB queries.

    Attributes:
        urs_available: Whether the Enhanced_URS document exists.
        urs_document_uuid: URS document UUID if available.
        urs_document_title: URS document title if available.
        ai_guidelines_available: Whether AI Guidelines documents exist.
        ai_guidelines_documents: List of AI Guidelines document metadata.
        governance_documents: All ALC-GOV documents for reference section.
    """

    urs_available: bool
    urs_document_uuid: str | None = None
    urs_document_title: str | None = None
    ai_guidelines_available: bool = False
    ai_guidelines_documents: list[dict] = field(default_factory=list)
    governance_documents: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USER_GUIDE_TITLE: str = "AlcoaBase — Comprehensive User Guide"

ADMIN_GUIDE_TITLE: str = "AlcoaBase — Technical Administrator Guide"

DOCUMENTATION_TAGS: list[str] = ["DOC-GUIDE", "ALC-GOV"]

DOCUMENTATION_DOCUMENT_TYPE: str = "Documentation Guide"


# ---------------------------------------------------------------------------
# User Guide Section Definitions
# ---------------------------------------------------------------------------

USER_GUIDE_SECTIONS: list[UserGuideSection] = [
    UserGuideSection(
        section_id="getting-started",
        title="Getting Started",
        overview=(
            "This section guides you through your first interaction with AlcoaBase, "
            "covering system access prerequisites, the login process with re-authentication, "
            "main navigation overview, and a quick-start workflow to upload your first document."
        ),
        procedures=[
            ProcedureBlock(
                title="Logging In to AlcoaBase",
                steps=[
                    "**Navigate** to the AlcoaBase login page in your browser — *the login form appears with username and password fields*",
                    "**Enter** your username in the Username field — *the field accepts your input and displays the characters*",
                    "**Enter** your password in the Password field — *the field accepts your input and masks the characters*",
                    "**Click** the **Sign In** button — *the system authenticates your credentials and redirects to the dashboard*",
                    "**Verify** that the dashboard displays your name and assigned company — *your user profile appears in the top-right corner*",
                ],
                screenshot_slug="logging-in",
            ),
            ProcedureBlock(
                title="Navigating the Main Dashboard",
                steps=[
                    "**Locate** the sidebar navigation menu on the left side of the screen — *the menu displays icons and labels for each module*",
                    "**Click** the **Documents** menu item — *the document management view loads with your accessible documents*",
                    "**Click** the **Workflows** menu item — *the workflow overview displays active document states*",
                    "**Click** the **Training** menu item — *your assigned training tasks and completion status appear*",
                    "**Click** the **Search** menu item — *the hybrid search interface loads with the query input field*",
                ],
                screenshot_slug="navigating-dashboard",
            ),
            ProcedureBlock(
                title="Quick-Start: Uploading Your First Document",
                steps=[
                    "**Click** the **Documents** menu item in the sidebar — *the document management view loads*",
                    "**Click** the **Upload Document** button in the top-right corner — *the upload dialog opens*",
                    "**Select** a file from your computer using the file picker — *the filename appears in the upload form*",
                    "**Enter** a descriptive title in the Title field — *the title field displays your input*",
                    "**Select** a folder path from the dropdown — *the folder path is set for the document*",
                    "**Click** the **Upload** button to submit — *the document is uploaded and a success notification appears*",
                    "**Navigate** to the virtual folder to verify the document appears — *your document is listed with its assigned UUID*",
                ],
                screenshot_slug="quick-start-upload",
            ),
        ],
        tips=[
            "Bookmark the AlcoaBase URL in your browser for quick access to the platform.",
            "If your session expires, you will be prompted to re-authenticate — this is a security feature required by GxP compliance.",
            "Use the dashboard overview to quickly check pending training tasks and documents awaiting your review.",
        ],
        cross_ref_sections=["document-management", "workflows"],
        urs_requirement_ids=["REQ-DM-01", "REQ-AUTH-01"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="document-management",
        title="Document Management",
        overview=(
            "Document Management is the core module for uploading, organizing, versioning, "
            "and managing documents within AlcoaBase. This section covers single and bulk uploads, "
            "virtual folder navigation, document versioning with change reasons, and metadata editing."
        ),
        procedures=[
            ProcedureBlock(
                title="Uploading a Single Document",
                steps=[
                    "**Navigate** to the Documents section via the sidebar menu — *the document list view loads*",
                    "**Click** the **Upload Document** button — *the upload dialog opens with file selection and metadata fields*",
                    "**Select** a file from your local system using the file picker — *the filename and size are displayed*",
                    "**Enter** a descriptive title in the Title field — *the title is set for the document record*",
                    "**Select** the document type from the dropdown (e.g., SOP, Protocol, Report) — *the type is assigned*",
                    "**Choose** a folder path for the document — *the folder location is set*",
                    "**Add** relevant tags by typing in the Tags field — *tags appear as chips below the input*",
                    "**Click** **Upload** to submit the document — *the system generates a Document-UUID and confirms upload success*",
                ],
                screenshot_slug="uploading-single-document",
            ),
            ProcedureBlock(
                title="Using Bulk Upload via CLI",
                steps=[
                    "**Open** a terminal on the server or your local machine with network access — *the command prompt appears*",
                    "**Run** the bulk upload command with the target directory path — *the CLI tool scans the directory for files*",
                    "**Review** the summary of files to be uploaded displayed by the CLI — *file count and total size are shown*",
                    "**Confirm** the upload by entering 'y' when prompted — *the upload process begins with a progress indicator*",
                    "**Verify** the completion message showing documents created — *each document receives a UUID and is indexed*",
                ],
                screenshot_slug="bulk-upload-cli",
            ),
            ProcedureBlock(
                title="Creating and Navigating Virtual Folders",
                steps=[
                    "**Navigate** to the Documents section — *the document list view loads*",
                    "**Click** the **Folders** tab in the navigation bar — *the virtual folder tree is displayed*",
                    "**Click** **Create Folder** to add a new virtual folder — *the folder creation dialog opens*",
                    "**Enter** a folder name and optional tag filter — *the folder configuration is set*",
                    "**Click** **Save** to create the folder — *the new folder appears in the folder tree*",
                    "**Click** on any folder to view its contents — *documents matching the folder criteria are listed*",
                ],
                screenshot_slug="virtual-folders",
            ),
            ProcedureBlock(
                title="Versioning a Document",
                steps=[
                    "**Navigate** to the document you want to version — *the document detail view loads*",
                    "**Click** the **Upload New Version** button — *the version upload dialog opens*",
                    "**Select** the updated file from your local system — *the new file is staged for upload*",
                    "**Enter** a change reason describing what was modified — *the change reason is recorded for audit*",
                    "**Click** **Upload Version** to submit — *the system increments the major version number and stores the new content*",
                    "**Verify** the version history shows the new entry — *the version list displays all versions with timestamps*",
                ],
                screenshot_slug="versioning-document",
            ),
            ProcedureBlock(
                title="Editing Document Metadata",
                steps=[
                    "**Navigate** to the document whose metadata you want to edit — *the document detail view loads*",
                    "**Click** the **Edit Metadata** button — *the metadata editing form appears*",
                    "**Modify** the title, tags, or document type as needed — *the fields update with your changes*",
                    "**Enter** a change reason for the metadata update — *the reason is captured for the audit trail*",
                    "**Click** **Save Changes** to apply — *the metadata is updated and the audit trail records the change*",
                ],
                screenshot_slug="editing-metadata",
            ),
        ],
        tips=[
            "Always provide a meaningful change reason when uploading new versions — this is required for GxP audit compliance.",
            "Use tags consistently across documents to enable effective virtual folder filtering and search.",
            "Check the version history before uploading a new version to understand the document's change history.",
        ],
        cross_ref_sections=["getting-started", "workflows", "electronic-signatures"],
        urs_requirement_ids=["REQ-DM-01", "REQ-DM-02", "REQ-DM-03"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="template-builder",
        title="Template Builder",
        overview=(
            "The Template Builder allows you to create structured data entry forms with "
            "various field types, drag-and-drop layout capabilities, and reusable templates "
            "that generate both React forms and offline PDF equivalents."
        ),
        procedures=[
            ProcedureBlock(
                title="Creating a New Template",
                steps=[
                    "**Navigate** to the Template Builder via the sidebar menu — *the template list view loads*",
                    "**Click** the **Create Template** button — *the template editor opens with a blank canvas*",
                    "**Enter** a template name in the Title field — *the template name is set*",
                    "**Select** a document type category for the template — *the category is assigned*",
                    "**Click** **Save** to create the initial template — *the template is saved and the editor remains open for field configuration*",
                ],
                screenshot_slug="creating-template",
            ),
            ProcedureBlock(
                title="Adding Fields with Drag-and-Drop",
                steps=[
                    "**Locate** the field palette on the left side of the template editor — *available field types are listed*",
                    "**Drag** a field type (e.g., Text, Number, Date, Dropdown) from the palette — *the field follows your cursor*",
                    "**Drop** the field onto the desired position in the form layout — *the field is placed and a configuration panel opens*",
                    "**Configure** the field properties (label, required, validation rules) — *the field settings are applied*",
                    "**Repeat** for additional fields until the form structure is complete — *all fields appear in the layout preview*",
                    "**Click** **Save Template** to persist your changes — *the template is saved with all field configurations*",
                ],
                screenshot_slug="adding-fields-drag-drop",
            ),
        ],
        tips=[
            "Preview your template before saving to verify the form layout matches your intended data collection structure.",
            "Use consistent field naming conventions across templates to enable cross-document reporting and search.",
        ],
        cross_ref_sections=["report-data-entry", "document-management"],
        urs_requirement_ids=["REQ-PDF-01", "REQ-PDF-02"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="report-data-entry",
        title="Report Data Entry and PDF Extraction",
        overview=(
            "This section covers filling out template-based forms for data entry, uploading "
            "offline PDF reports for extraction, and understanding the Dual-UUID concept that "
            "maps offline PDF data back to the PostgreSQL database records."
        ),
        procedures=[
            ProcedureBlock(
                title="Filling Out a Template Form",
                steps=[
                    "**Navigate** to the document requiring data entry — *the document detail view loads with the associated form*",
                    "**Click** the **Enter Data** button — *the template form opens with all configured fields*",
                    "**Fill** in each required field following the field labels and validation hints — *fields accept your input and show validation status*",
                    "**Review** the completed form for accuracy — *all fields display their entered values*",
                    "**Click** **Submit** to save the data entry — *the form data is persisted and linked to the document record*",
                ],
                screenshot_slug="filling-template-form",
            ),
            ProcedureBlock(
                title="Uploading an Offline PDF for Extraction",
                steps=[
                    "**Navigate** to the Report Data Entry section — *the data entry interface loads*",
                    "**Click** the **Upload Offline PDF** button — *the PDF upload dialog opens*",
                    "**Select** the completed offline PDF from your local system — *the file is staged for processing*",
                    "**Click** **Extract Data** to initiate the Dual-UUID extraction process — *the system processes the PDF and maps fields to database records*",
                    "**Review** the extracted data displayed in the form view — *extracted values appear in their corresponding fields*",
                    "**Confirm** the extraction results by clicking **Accept** — *the data is committed to the database with full traceability*",
                ],
                screenshot_slug="uploading-offline-pdf",
            ),
        ],
        tips=[
            "Always verify extracted PDF data against the original paper document before accepting — automated extraction may require manual correction.",
            "The Dual-UUID system ensures every offline data point is traceable back to both the PDF source and the database record.",
        ],
        cross_ref_sections=["template-builder", "document-management"],
        urs_requirement_ids=["REQ-PDF-03", "REQ-PDF-04"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="workflows",
        title="Workflows",
        overview=(
            "Workflows define the lifecycle states of documents in AlcoaBase. This section "
            "explains how to understand document states, trigger transitions between states, "
            "and view the complete workflow history for audit purposes."
        ),
        procedures=[
            ProcedureBlock(
                title="Understanding Document States",
                steps=[
                    "**Navigate** to a document with an active workflow — *the document detail view shows the current state badge*",
                    "**Locate** the workflow state indicator in the document header — *the current state (e.g., Draft, Review, Approved) is displayed*",
                    "**Click** the **Workflow History** tab — *the complete state transition history is shown with timestamps and actors*",
                    "**Review** each transition entry to understand the document's lifecycle progression — *entries show who triggered each transition and when*",
                ],
                screenshot_slug="understanding-document-states",
            ),
            ProcedureBlock(
                title="Triggering a Workflow Transition",
                steps=[
                    "**Navigate** to the document you want to advance — *the document detail view loads with available actions*",
                    "**Click** the **Advance Workflow** button — *available transitions are displayed based on the current state*",
                    "**Select** the target state from the available transitions — *the transition is highlighted*",
                    "**Enter** a change reason explaining why the transition is being made — *the reason is captured for audit*",
                    "**Click** **Confirm Transition** to execute — *the document state changes and the workflow history is updated*",
                    "**Verify** the new state is reflected in the document header — *the state badge updates to the new state*",
                ],
                screenshot_slug="triggering-workflow-transition",
            ),
        ],
        tips=[
            "Always check which transitions are available from the current state before attempting to advance a document.",
            "Workflow transitions are recorded in the audit trail — ensure your change reason accurately describes the purpose of the transition.",
            "Contact your administrator to configure workflow definitions — see Admin Guide Section 10 for workflow administration details.",
        ],
        cross_ref_sections=["document-management", "electronic-signatures"],
        urs_requirement_ids=["REQ-WF-01", "REQ-WF-02", "REQ-WF-03"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="training-management",
        title="Training Management",
        overview=(
            "Training Management ensures users maintain required competencies before "
            "performing regulated tasks. This section covers viewing assigned training, "
            "completing training tasks, and interacting with comprehension quizzes."
        ),
        procedures=[
            ProcedureBlock(
                title="Viewing Assigned Training",
                steps=[
                    "**Navigate** to the Training section via the sidebar menu — *your training dashboard loads with assigned tasks*",
                    "**Review** the list of assigned training items — *each item shows the document title, due date, and completion status*",
                    "**Click** on a training item to view its details — *the training requirements and associated document are displayed*",
                    "**Note** the due date and priority level for each training task — *overdue items are highlighted in red*",
                ],
                screenshot_slug="viewing-assigned-training",
            ),
            ProcedureBlock(
                title="Completing a Training Task",
                steps=[
                    "**Click** on the training task you want to complete — *the training detail view opens*",
                    "**Read** the associated document or training material thoroughly — *the document content is displayed for study*",
                    "**Click** **Mark as Read** when you have finished reviewing the material — *the system records your acknowledgment*",
                    "**Click** **Take Quiz** to begin the comprehension assessment — *the quiz interface loads with questions*",
                    "**Answer** each quiz question based on the training material — *your answers are recorded*",
                    "**Submit** the quiz by clicking **Complete Quiz** — *your score is calculated and displayed*",
                    "**Verify** your training status shows as completed — *the training record is updated with your completion date*",
                ],
                screenshot_slug="completing-training-task",
            ),
        ],
        tips=[
            "Complete training tasks before their due date to maintain access to regulated operations that require valid training records.",
            "Review the associated document carefully before taking the quiz — a passing score is required to complete the training.",
            "If you fail a quiz, you can retake it after reviewing the material again.",
        ],
        cross_ref_sections=["workflows", "ai-agent-interaction"],
        urs_requirement_ids=["REQ-TRN-01", "REQ-TRN-02", "REQ-TRN-03"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="electronic-signatures",
        title="Electronic Signatures",
        overview=(
            "Electronic Signatures provide legally binding approval of documents within "
            "AlcoaBase, compliant with 21 CFR Part 11 requirements. This section covers "
            "the re-authentication process, signing documents, and viewing signature status."
        ),
        procedures=[
            ProcedureBlock(
                title="Signing a Document",
                steps=[
                    "**Navigate** to the document requiring your signature — *the document detail view loads with a Sign button*",
                    "**Click** the **Sign Document** button — *the re-authentication dialog appears*",
                    "**Enter** your username in the re-authentication form — *the username field accepts your input*",
                    "**Enter** your password to confirm your identity — *the password field accepts your input*",
                    "**Select** the signature meaning (e.g., Approved, Reviewed, Authored) — *the meaning is set for the signature*",
                    "**Click** **Apply Signature** to sign the document — *the system validates your credentials and applies the electronic signature*",
                    "**Verify** the signature status shows your name, timestamp, and meaning — *the signature record appears in the document*",
                ],
                screenshot_slug="signing-document",
            ),
            ProcedureBlock(
                title="Viewing Signature Status",
                steps=[
                    "**Navigate** to the document whose signatures you want to review — *the document detail view loads*",
                    "**Click** the **Signatures** tab — *all applied signatures are listed with signer details*",
                    "**Review** each signature entry showing signer name, timestamp, and meaning — *signature validity indicators are displayed*",
                    "**Verify** the signature chain is complete for the required approvals — *all required signers are listed with their status*",
                ],
                screenshot_slug="viewing-signature-status",
            ),
        ],
        tips=[
            "Re-authentication is required for every signature action — this is a regulatory requirement under 21 CFR Part 11 to ensure non-repudiation.",
            "Ensure you select the correct signature meaning (Approved, Reviewed, Authored) as this is recorded permanently in the audit trail.",
        ],
        cross_ref_sections=["workflows", "document-management"],
        urs_requirement_ids=["REQ-SIG-01", "REQ-SIG-02", "REQ-SIG-03"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="search-and-knowledge-base",
        title="Search and Knowledge Base",
        overview=(
            "The Search and Knowledge Base module provides hybrid search combining lexical "
            "and semantic matching, faceted filtering, and a RAG-powered Knowledge Base for "
            "asking natural language questions with source-attributed AI answers."
        ),
        procedures=[
            ProcedureBlock(
                title="Performing a Hybrid Search",
                steps=[
                    "**Navigate** to the Search section via the sidebar menu — *the search interface loads with the query input*",
                    "**Enter** your search query in the search field — *the field accepts your text input*",
                    "**Click** **Search** or press Enter to execute the query — *results appear ranked by relevance score*",
                    "**Review** the search results showing document titles, snippets, and relevance scores — *each result displays a relevance percentage*",
                    "**Apply** faceted filters (document type, tags, date range) to narrow results — *the result list updates based on your filters*",
                    "**Click** on a result to open the full document — *the document detail view loads*",
                ],
                screenshot_slug="performing-hybrid-search",
            ),
            ProcedureBlock(
                title="Using the RAG Knowledge Base",
                steps=[
                    "**Navigate** to the Knowledge Base section — *the conversational Q&A interface loads*",
                    "**Enter** a natural language question in the input field — *the field accepts your question*",
                    "**Click** **Ask** to submit your question — *the AI processes your query against indexed documents*",
                    "**Review** the AI-generated answer with source citations — *the answer includes references to specific documents and sections*",
                    "**Click** on a source citation to view the original document — *the source document opens at the relevant section*",
                    "**Continue** the conversation by asking follow-up questions — *the system maintains context from previous exchanges*",
                ],
                screenshot_slug="using-rag-knowledge-base",
            ),
        ],
        tips=[
            "Use specific keywords and document type filters to improve search precision for regulatory documents.",
            "The RAG Knowledge Base provides AI-generated answers with source attribution — always verify critical information against the cited source documents.",
            "Search results combine lexical matching (exact keywords) and semantic matching (meaning-based) for comprehensive coverage.",
        ],
        cross_ref_sections=["document-management", "ai-agent-interaction"],
        urs_requirement_ids=["REQ-SEARCH-01", "REQ-SEARCH-02", "REQ-RAG-01"],
        ai_guidelines_ref=True,
    ),
    UserGuideSection(
        section_id="ai-agent-interaction",
        title="AI Agent Interaction",
        overview=(
            "AI Agent Interaction covers the multi-agent review system that produces compliance "
            "audit reports, scorecards with severity ratings, master auditor summaries, and "
            "integration with the training ecosystem for AI-generated quizzes and role-play scenarios."
        ),
        procedures=[
            ProcedureBlock(
                title="Understanding Multi-Agent Review Reports",
                steps=[
                    "**Navigate** to a document that has been reviewed by AI agents — *the document detail view shows a Review Reports tab*",
                    "**Click** the **Review Reports** tab — *the list of agent review reports is displayed*",
                    "**Select** a review report to view its details — *the full report opens with findings from each agent archetype*",
                    "**Review** each agent's findings organized by severity (Critical, Major, Minor, Observation) — *findings are color-coded by severity*",
                    "**Read** the master auditor summary at the top of the report — *the summary synthesizes all agent findings into an overall assessment*",
                ],
                screenshot_slug="understanding-review-reports",
            ),
            ProcedureBlock(
                title="Interpreting Compliance Scorecards",
                steps=[
                    "**Navigate** to the Compliance section or a reviewed document — *the scorecard view is accessible*",
                    "**Locate** the compliance scorecard for the document or company — *the scorecard displays overall and per-category scores*",
                    "**Review** the overall compliance score and trend indicator — *the score shows the current compliance level*",
                    "**Examine** individual category scores (Data Integrity, Documentation, Training, etc.) — *each category shows its score and contributing factors*",
                    "**Click** on a category to view detailed findings — *the underlying agent findings for that category are listed*",
                ],
                screenshot_slug="interpreting-compliance-scorecards",
            ),
            ProcedureBlock(
                title="Using Training Ecosystem Features",
                steps=[
                    "**Navigate** to the Training section — *your training dashboard loads*",
                    "**Locate** AI-generated training materials linked to review findings — *materials are tagged with their source review*",
                    "**Click** on an AI-generated quiz to begin — *the quiz interface loads with questions derived from compliance findings*",
                    "**Complete** the quiz questions based on your understanding of the compliance requirements — *your answers are evaluated*",
                    "**Review** your results and any recommended follow-up materials — *the system suggests additional training based on your performance*",
                ],
                screenshot_slug="using-training-ecosystem",
            ),
        ],
        tips=[
            "Focus on Critical and Major findings first — these represent the highest compliance risk and should be addressed promptly.",
            "The master auditor summary provides a consolidated view — use it to quickly understand the overall compliance posture before diving into individual findings.",
            "AI-generated training materials are linked to specific compliance findings — completing them helps address identified knowledge gaps.",
        ],
        cross_ref_sections=["search-and-knowledge-base", "training-management", "ai-document-generator"],
        urs_requirement_ids=["REQ-AGENT-01", "REQ-AGENT-02", "REQ-AGENT-03"],
        ai_guidelines_ref=True,
    ),
    UserGuideSection(
        section_id="ai-document-generator",
        title="AI Document Generator",
        overview=(
            "The AI Document Generator enables creation of structured documents from templates "
            "using AI assistance. This section covers selecting generation templates, initiating "
            "document generation, and reviewing AI-generated output before approval."
        ),
        procedures=[
            ProcedureBlock(
                title="Generating a Document from Template",
                steps=[
                    "**Navigate** to the AI Document Generator via the sidebar menu — *the generator interface loads with available templates*",
                    "**Select** a document template from the available options — *the template details and required inputs are displayed*",
                    "**Fill** in the required input parameters for the generation — *the input fields accept your context data*",
                    "**Click** **Generate Document** to initiate AI generation — *the system processes your request and shows a progress indicator*",
                    "**Wait** for the generation to complete — *the generated document preview appears when ready*",
                    "**Review** the AI-generated content for accuracy and completeness — *the full document is displayed in preview mode*",
                    "**Click** **Accept** to save the generated document or **Reject** to discard — *the document is saved to the system or discarded based on your choice*",
                ],
                screenshot_slug="generating-document-from-template",
            ),
            ProcedureBlock(
                title="Reviewing AI-Generated Output",
                steps=[
                    "**Open** the generated document in the review interface — *the document content is displayed with AI-generated sections highlighted*",
                    "**Review** each section for factual accuracy and regulatory compliance — *sections are clearly delineated for review*",
                    "**Check** that all required fields and sections are populated — *the completeness indicator shows coverage*",
                    "**Edit** any sections that require correction or enhancement — *the inline editor allows modifications*",
                    "**Submit** the reviewed document for workflow processing — *the document enters the governance workflow at Draft state*",
                ],
                screenshot_slug="reviewing-ai-generated-output",
            ),
        ],
        tips=[
            "Always review AI-generated documents thoroughly before accepting — AI output requires human verification in regulated environments.",
            "Use the template preview to understand what inputs are needed before starting generation.",
            "Generated documents enter the governance workflow at Draft state and require formal review and approval before becoming active.",
        ],
        cross_ref_sections=["ai-agent-interaction", "workflows", "document-management"],
        urs_requirement_ids=["REQ-DOCGEN-01", "REQ-DOCGEN-02"],
        ai_guidelines_ref=True,
    ),
    UserGuideSection(
        section_id="related-governance-documents",
        title="Related Governance Documents",
        overview=(
            "This section provides a comprehensive list of all governance documents within "
            "the ALC corporate environment that are referenced throughout this guide, including "
            "their document UUIDs and current workflow states."
        ),
        procedures=[
            ProcedureBlock(
                title="Accessing Governance Documents",
                steps=[
                    "**Navigate** to the Governance folder in the Documents section — *the governance document list loads*",
                    "**Review** the list of governance documents with their titles and workflow states — *each document shows its current lifecycle state*",
                    "**Click** on a document title to open it — *the document detail view loads with full content*",
                    "**Check** the document's workflow state to confirm it is in an approved or active state — *the state badge indicates the current status*",
                ],
                screenshot_slug="accessing-governance-documents",
            ),
        ],
        tips=[
            "Governance documents tagged with ALC-GOV follow the formal document lifecycle — only documents in Approved or Active state should be referenced for compliance purposes.",
            "Use the document UUID to create precise cross-references in your own documentation.",
        ],
        cross_ref_sections=["document-management", "workflows"],
        urs_requirement_ids=["REQ-DM-01"],
        ai_guidelines_ref=False,
    ),
    UserGuideSection(
        section_id="appendices",
        title="Appendices",
        overview=(
            "The Appendices provide supplementary reference material including keyboard shortcuts "
            "for efficient navigation, a comprehensive glossary of platform terminology, "
            "troubleshooting guides for common issues, and URS traceability references."
        ),
        procedures=[
            ProcedureBlock(
                title="Using Keyboard Shortcuts",
                steps=[
                    "**Press** Ctrl+K (Cmd+K on macOS) to open the command palette — *the command palette overlay appears*",
                    "**Type** the name of the action you want to perform — *matching commands are filtered in real-time*",
                    "**Select** the desired command from the filtered list — *the action is executed immediately*",
                    "**Press** Escape to close the command palette without executing — *the overlay closes and you return to the previous view*",
                ],
                screenshot_slug="using-keyboard-shortcuts",
            ),
            ProcedureBlock(
                title="Troubleshooting Common Issues",
                steps=[
                    "**Identify** the error message or unexpected behavior you are experiencing — *note the exact error text if displayed*",
                    "**Check** the troubleshooting table below for your specific issue — *common issues are listed with their solutions*",
                    "**Follow** the recommended resolution steps for your issue — *the steps guide you through the fix*",
                    "**Contact** your system administrator if the issue persists after following the resolution steps — *provide the error details and steps you have already tried*",
                ],
                screenshot_slug="troubleshooting-common-issues",
            ),
        ],
        tips=[
            "Refer to the glossary when encountering unfamiliar terms — all platform-specific terminology is defined there.",
            "Keyboard shortcuts significantly speed up common operations — invest time learning the most frequently used shortcuts.",
        ],
        cross_ref_sections=["getting-started"],
        urs_requirement_ids=["REQ-DM-01", "REQ-AUTH-01"],
        ai_guidelines_ref=False,
    ),
]


# ---------------------------------------------------------------------------
# Admin Guide Section Definitions
# ---------------------------------------------------------------------------

ADMIN_GUIDE_SECTIONS: list[AdminGuideSection] = [
    AdminGuideSection(
        section_id="administration-overview",
        title="Administration Overview",
        overview=(
            "This section provides a comprehensive overview of administrative roles, responsibilities, "
            "and access levels within AlcoaBase. Administrators are responsible for maintaining system "
            "integrity, managing users, and ensuring regulatory compliance across all platform operations."
        ),
        prerequisites=["System Administrator or Document Administrator role assignment"],
        procedures=[
            ProcedureBlock(
                title="Accessing the Administration Dashboard",
                steps=[
                    "**Navigate** to the Admin section via the sidebar menu — *the administration dashboard loads with system overview panels*",
                    "**Verify** your role is displayed as System Administrator or Document Administrator — *your role badge appears in the header*",
                    "**Review** the system health indicators on the dashboard — *service status indicators show green/yellow/red for each component*",
                    "**Check** pending administrative tasks in the notification panel — *unresolved items are listed with priority indicators*",
                ],
                screenshot_slug="accessing-admin-dashboard",
            ),
        ],
        security_considerations=(
            "Administrative access provides elevated privileges that affect all users and system "
            "operations. All administrative actions are recorded in the immutable audit trail with "
            "full attribution (who, what, when, why). Unauthorized access attempts are logged and "
            "may trigger security alerts. Administrators must maintain valid training records for "
            "their administrative role."
        ),
        cross_ref_sections=["user-management", "rbac", "system-configuration"],
        user_guide_refs=["getting-started"],
        urs_requirement_ids=["REQ-ADMIN-01"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="user-management",
        title="User Management",
        overview=(
            "User Management covers the complete lifecycle of user accounts including creation, "
            "role assignment, company assignment, activation and deactivation, password reset, "
            "and permission template management. All user operations are subject to audit trail recording."
        ),
        prerequisites=[
            "System Administrator role",
            "Access to the User Management panel",
            "Knowledge of company structure and role hierarchy",
        ],
        procedures=[
            ProcedureBlock(
                title="Creating a New User",
                steps=[
                    "**Navigate** to Admin > User Management — *the user list view loads with all registered users*",
                    "**Click** the **Create User** button — *the user creation form opens*",
                    "**Enter** the username (must be unique across the system) — *the field validates uniqueness in real-time*",
                    "**Enter** the user's email address — *the email field validates format*",
                    "**Select** the user's role from the role dropdown — *available roles are listed based on your permissions*",
                    "**Assign** the user to a company from the company dropdown — *the company assignment determines data access scope*",
                    "**Set** an initial password or enable the password reset link option — *the authentication method is configured*",
                    "**Click** **Create User** to submit — *the user account is created and an audit trail entry is recorded*",
                ],
                screenshot_slug="creating-new-user",
            ),
            ProcedureBlock(
                title="Assigning Roles and Permissions",
                steps=[
                    "**Navigate** to the user's profile in User Management — *the user detail view loads*",
                    "**Click** the **Edit Roles** button — *the role assignment interface opens*",
                    "**Select** the appropriate role(s) for the user — *roles are listed with their permission descriptions*",
                    "**Review** the effective permissions that will be granted — *the permission summary updates based on selected roles*",
                    "**Enter** a change reason for the role modification — *the reason is captured for audit compliance*",
                    "**Click** **Save Changes** to apply the role assignment — *the user's permissions are updated immediately*",
                ],
                screenshot_slug="assigning-roles-permissions",
            ),
            ProcedureBlock(
                title="Activating and Deactivating Accounts",
                steps=[
                    "**Navigate** to the user's profile in User Management — *the user detail view loads*",
                    "**Click** the **Account Status** toggle — *the activation/deactivation confirmation dialog appears*",
                    "**Enter** a change reason explaining why the account status is being changed — *the reason is required for audit*",
                    "**Click** **Confirm** to apply the status change — *the account is activated or deactivated and the user is notified*",
                    "**Verify** the account status indicator reflects the new state — *the status badge updates accordingly*",
                ],
                screenshot_slug="activating-deactivating-accounts",
            ),
        ],
        security_considerations=(
            "User creation and role assignment directly impact system access control. Incorrect "
            "role assignments may grant unauthorized access to regulated data. All user management "
            "operations require the X-Change-Reason header for audit compliance. Deactivated users "
            "retain their audit history but cannot authenticate. Password resets should follow "
            "organizational security policies."
        ),
        cross_ref_sections=["rbac", "administration-overview"],
        user_guide_refs=["getting-started"],
        urs_requirement_ids=["REQ-ADMIN-02", "REQ-ADMIN-03"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="rbac",
        title="Role-Based Access Control",
        overview=(
            "Role-Based Access Control (RBAC) defines the permission model for AlcoaBase, including "
            "predefined system roles, custom role creation, and permission inheritance hierarchies. "
            "RBAC ensures users can only access data and perform actions appropriate to their responsibilities."
        ),
        prerequisites=[
            "System Administrator role",
            "Understanding of organizational role hierarchy",
            "Knowledge of regulatory access requirements",
        ],
        procedures=[
            ProcedureBlock(
                title="Reviewing Predefined Roles",
                steps=[
                    "**Navigate** to Admin > Role Management — *the role list view loads with all defined roles*",
                    "**Review** the predefined system roles (System Administrator, Document Administrator, Reviewer, Author, Viewer) — *each role shows its permission count*",
                    "**Click** on a role to view its detailed permissions — *the permission matrix displays all granted capabilities*",
                    "**Note** which permissions are inherited from parent roles — *inherited permissions are marked with an inheritance indicator*",
                ],
                screenshot_slug="reviewing-predefined-roles",
            ),
            ProcedureBlock(
                title="Creating a Custom Role",
                steps=[
                    "**Navigate** to Admin > Role Management — *the role list view loads*",
                    "**Click** the **Create Role** button — *the role creation form opens*",
                    "**Enter** a role name and description — *the fields accept your input*",
                    "**Select** a parent role for permission inheritance (optional) — *inherited permissions are automatically included*",
                    "**Toggle** individual permissions on or off as needed — *the permission matrix updates in real-time*",
                    "**Review** the complete effective permission set — *all granted permissions are summarized*",
                    "**Click** **Create Role** to save — *the custom role is created and available for user assignment*",
                ],
                screenshot_slug="creating-custom-role",
            ),
        ],
        security_considerations=(
            "RBAC configuration directly controls data access boundaries. Custom roles must be "
            "reviewed for least-privilege compliance. Permission inheritance can inadvertently grant "
            "excessive access — always review the effective permission set before saving. Role changes "
            "take effect immediately for all assigned users. All RBAC modifications are recorded in "
            "the audit trail."
        ),
        cross_ref_sections=["user-management", "administration-overview"],
        user_guide_refs=["getting-started"],
        urs_requirement_ids=["REQ-RBAC-01", "REQ-RBAC-02"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="system-configuration",
        title="System Configuration",
        overview=(
            "System Configuration covers AI hardware settings, storage quota management, backup "
            "configuration, system health monitoring, and service status overview. Proper configuration "
            "ensures optimal performance and compliance with data integrity requirements across all platform services."
        ),
        prerequisites=[
            "System Administrator role",
            "Access to the System Configuration panel",
            "Understanding of infrastructure components (PostgreSQL, Redis, OpenSearch, MinIO, vLLM)",
        ],
        procedures=[
            ProcedureBlock(
                title="Configuring AI Hardware Mode",
                steps=[
                    "**Navigate** to Admin > System Configuration > AI Settings — *the AI configuration panel loads*",
                    "**Review** the current hardware mode (GPU, CPU, or Mock) — *the active mode is highlighted*",
                    "**Select** the desired hardware mode from the options — *the mode selection updates with performance implications*",
                    "**Review** the performance impact warning for the selected mode — *estimated inference times are displayed*",
                    "**Enter** a change reason for the configuration change — *the reason is required for audit*",
                    "**Click** **Apply Configuration** to save — *the system applies the new hardware mode and restarts affected services*",
                    "**Verify** the service status indicators show healthy after the change — *all services return to green status*",
                ],
                screenshot_slug="configuring-ai-hardware-mode",
            ),
            ProcedureBlock(
                title="Monitoring System Health",
                steps=[
                    "**Navigate** to Admin > System Configuration > Health Monitor — *the health monitoring dashboard loads*",
                    "**Review** the service status panel showing Database, Redis, OpenSearch, MinIO, and vLLM connectivity — *each service shows a status indicator*",
                    "**Check** resource utilization metrics (CPU, memory, disk, GPU) — *current usage percentages are displayed*",
                    "**Review** any active alerts or warnings — *alerts are listed with severity and recommended actions*",
                    "**Click** on a service to view detailed health metrics — *the service detail panel shows connection pool status, latency, and error rates*",
                ],
                screenshot_slug="monitoring-system-health",
            ),
        ],
        security_considerations=(
            "System configuration changes affect all users and platform operations. Hardware mode "
            "changes may cause temporary service interruptions. Storage quota modifications impact "
            "data retention compliance. All configuration changes are recorded in the audit trail "
            "and require the X-Change-Reason header. This setting affects user experience as "
            "described in User Guide Section 8 (Search and Knowledge Base)."
        ),
        cross_ref_sections=["ai-model-layer", "storage-and-backup"],
        user_guide_refs=["search-and-knowledge-base", "ai-agent-interaction"],
        urs_requirement_ids=["REQ-SYS-01", "REQ-SYS-02"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="ai-model-layer",
        title="AI Model Layer Management",
        overview=(
            "AI Model Layer Management covers vLLM service configuration, model weight management, "
            "GPU allocation and CPU fallback settings, embedding model configuration for document "
            "indexing, OCR pipeline settings for scanned PDFs, and inference timeout and rate limit configuration."
        ),
        prerequisites=[
            "System Administrator role",
            "Understanding of AI/ML infrastructure (vLLM, GPU memory, model weights)",
            "Access to the AI Model Configuration panel",
            "Knowledge of inference performance requirements",
        ],
        procedures=[
            ProcedureBlock(
                title="Configuring vLLM Service Parameters",
                steps=[
                    "**Navigate** to Admin > AI Model Layer > vLLM Configuration — *the vLLM settings panel loads*",
                    "**Review** the current model configuration (model name, quantization, context length) — *active settings are displayed*",
                    "**Modify** the model selection if a different model is required — *available models are listed from the weights directory*",
                    "**Configure** GPU memory allocation percentage — *the slider adjusts memory reservation*",
                    "**Set** the maximum concurrent requests limit — *the field accepts the concurrency value*",
                    "**Enter** a change reason for the configuration update — *the reason is captured for audit*",
                    "**Click** **Apply** to save and restart the vLLM service — *the service restarts with new parameters*",
                    "**Verify** the vLLM health check returns healthy status — *the service status indicator turns green*",
                ],
                screenshot_slug="configuring-vllm-service",
            ),
            ProcedureBlock(
                title="Managing Model Weights",
                steps=[
                    "**Navigate** to Admin > AI Model Layer > Model Weights — *the model weight management view loads*",
                    "**Review** currently available model weights and their storage locations — *models are listed with size and last-modified date*",
                    "**Select** a model weight file to view its details — *model metadata including quantization level and parameter count are shown*",
                    "**Configure** the active model by selecting from available weights — *the selection is highlighted*",
                    "**Click** **Activate Model** to switch to the selected weights — *the system loads the new model weights*",
                ],
                screenshot_slug="managing-model-weights",
            ),
            ProcedureBlock(
                title="Configuring Embedding and OCR Settings",
                steps=[
                    "**Navigate** to Admin > AI Model Layer > Embedding & OCR — *the embedding and OCR configuration panel loads*",
                    "**Review** the current embedding model configuration — *the active model and dimension settings are displayed*",
                    "**Configure** OCR pipeline settings (language, DPI, preprocessing options) — *the OCR settings form accepts your values*",
                    "**Set** inference timeout values for embedding and OCR operations — *timeout fields accept duration in seconds*",
                    "**Configure** rate limits for AI operations per user per hour — *the rate limit field accepts the maximum value*",
                    "**Click** **Save Configuration** to apply all changes — *settings are persisted and services are notified*",
                ],
                screenshot_slug="configuring-embedding-ocr",
            ),
        ],
        security_considerations=(
            "AI model configuration changes affect inference quality and system performance for all "
            "users. Model weight changes require validation that the new model meets regulatory "
            "requirements for accuracy and reproducibility. GPU memory allocation changes may cause "
            "out-of-memory errors if set too high. Rate limits protect system stability but may "
            "impact user workflows if set too restrictively. All AI configuration changes are "
            "recorded in the audit trail."
        ),
        cross_ref_sections=["system-configuration", "compliance-monitoring"],
        user_guide_refs=["search-and-knowledge-base", "ai-agent-interaction", "ai-document-generator"],
        urs_requirement_ids=["REQ-AI-01", "REQ-AI-02", "REQ-AI-03"],
        ai_guidelines_ref=True,
    ),
    AdminGuideSection(
        section_id="storage-and-backup",
        title="Storage and Backup",
        overview=(
            "Storage and Backup administration covers MinIO object storage configuration, per-company "
            "storage quota management, automated backup schedule configuration, and data retention "
            "policy enforcement to ensure compliance with regulatory record-keeping requirements."
        ),
        prerequisites=[
            "System Administrator role",
            "Access to MinIO administration console",
            "Understanding of data retention regulatory requirements",
        ],
        procedures=[
            ProcedureBlock(
                title="Configuring MinIO Storage",
                steps=[
                    "**Navigate** to Admin > Storage & Backup > MinIO Configuration — *the storage configuration panel loads*",
                    "**Review** the current bucket configuration and access policies — *buckets are listed with their sizes and policies*",
                    "**Configure** storage quotas per company — *the quota form accepts size limits in GB*",
                    "**Set** lifecycle rules for automatic data tiering — *rules define when data moves between storage tiers*",
                    "**Click** **Apply Configuration** to save — *the storage settings are updated*",
                    "**Verify** the storage health check confirms connectivity — *the MinIO status indicator shows healthy*",
                ],
                screenshot_slug="configuring-minio-storage",
            ),
            ProcedureBlock(
                title="Managing Backup Schedules",
                steps=[
                    "**Navigate** to Admin > Storage & Backup > Backup Schedules — *the backup schedule management view loads*",
                    "**Review** existing backup schedules and their last execution status — *schedules show frequency, last run, and status*",
                    "**Click** **Create Schedule** to add a new backup schedule — *the schedule creation form opens*",
                    "**Configure** the backup frequency (daily, weekly, monthly) — *the frequency selector accepts your choice*",
                    "**Set** the retention period for backup copies — *the retention field accepts duration in days*",
                    "**Click** **Save Schedule** to activate — *the backup schedule is created and will execute at the configured time*",
                ],
                screenshot_slug="managing-backup-schedules",
            ),
        ],
        security_considerations=(
            "Storage configuration directly impacts data availability and regulatory compliance. "
            "Insufficient backup frequency may result in data loss during system failures. Retention "
            "policies must comply with regulatory requirements (typically 7-15 years for GxP records). "
            "Storage quota changes may prevent users from uploading documents if quotas are reduced. "
            "All storage configuration changes are recorded in the audit trail."
        ),
        cross_ref_sections=["system-configuration", "audit-trail-administration"],
        user_guide_refs=["document-management"],
        urs_requirement_ids=["REQ-STORAGE-01", "REQ-BACKUP-01"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="audit-trail-administration",
        title="Audit Trail Administration",
        overview=(
            "Audit Trail Administration provides tools for viewing, filtering, searching, and exporting "
            "the immutable audit log. The audit trail records every system action with full attribution "
            "(who, what, when, why) as required by ALCOA+ data integrity principles and 21 CFR Part 11."
        ),
        prerequisites=[
            "System Administrator or Document Administrator role",
            "Access to the Audit Trail viewer",
            "Understanding of ALCOA+ data integrity principles",
        ],
        procedures=[
            ProcedureBlock(
                title="Viewing and Filtering Audit Logs",
                steps=[
                    "**Navigate** to Admin > Audit Trail — *the audit log viewer loads with recent entries*",
                    "**Review** the audit entries showing timestamp, user, action, and change reason — *entries are displayed in reverse chronological order*",
                    "**Apply** date range filters to narrow the time window — *the log updates to show only entries within the selected range*",
                    "**Filter** by user, action type, or document to focus on specific activities — *the filtered results are displayed*",
                    "**Click** on an audit entry to view its full details — *the entry detail panel shows all recorded metadata*",
                ],
                screenshot_slug="viewing-filtering-audit-logs",
            ),
            ProcedureBlock(
                title="Exporting Audit Trail to PDF",
                steps=[
                    "**Configure** the desired filters for the export scope — *filters define which entries will be included*",
                    "**Click** the **Export to PDF** button — *the export dialog opens with format options*",
                    "**Select** the export format and date range — *the export parameters are configured*",
                    "**Click** **Generate Export** to create the PDF — *the system generates the audit trail PDF*",
                    "**Download** the generated PDF file — *the file downloads to your local system*",
                    "**Verify** the PDF contains all expected audit entries with timestamps and attribution — *the document is complete and formatted for regulatory review*",
                ],
                screenshot_slug="exporting-audit-trail-pdf",
            ),
        ],
        security_considerations=(
            "The audit trail is immutable — entries cannot be modified or deleted. Export operations "
            "are themselves recorded in the audit trail. Audit data may contain sensitive information "
            "about user activities and should be handled according to data protection policies. "
            "Regular audit trail review is a regulatory expectation for GxP-compliant systems."
        ),
        cross_ref_sections=["administration-overview", "compliance-monitoring"],
        user_guide_refs=["workflows", "electronic-signatures"],
        urs_requirement_ids=["REQ-AUDIT-01", "REQ-AUDIT-02", "REQ-AUDIT-03"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="compliance-monitoring",
        title="Compliance Monitoring",
        overview=(
            "Compliance Monitoring provides tools for interpreting company compliance scorecards, "
            "configuring audit readiness thresholds, reviewing multi-agent audit findings, managing "
            "risk-based workflow pathing, and monitoring AI Risk and Compliance Framework tier assignments."
        ),
        prerequisites=[
            "System Administrator or Compliance Officer role",
            "Understanding of regulatory compliance frameworks (GMP, ISO 13485, IVDR)",
            "Access to the Compliance Monitoring dashboard",
        ],
        procedures=[
            ProcedureBlock(
                title="Interpreting Compliance Scorecards",
                steps=[
                    "**Navigate** to Admin > Compliance Monitoring > Scorecards — *the scorecard dashboard loads with company-level metrics*",
                    "**Review** the overall compliance score and trend over time — *the score is displayed with a trend graph*",
                    "**Examine** individual category scores (Data Integrity, Documentation, Training, Workflows) — *each category shows its contribution to the overall score*",
                    "**Identify** categories below the configured threshold — *below-threshold categories are highlighted in amber or red*",
                    "**Click** on a category to drill down into contributing findings — *the detailed findings list appears*",
                    "**Review** recommended corrective actions for each finding — *actions are prioritized by severity and impact*",
                ],
                screenshot_slug="interpreting-compliance-scorecards",
            ),
            ProcedureBlock(
                title="Configuring Agent Review Thresholds",
                steps=[
                    "**Navigate** to Admin > Compliance Monitoring > Configuration — *the compliance configuration panel loads*",
                    "**Locate** the audit readiness threshold settings — *current thresholds are displayed for each category*",
                    "**Modify** threshold values for compliance categories — *the fields accept percentage values*",
                    "**Configure** the review quorum (minimum number of agents required for a valid review) — *the quorum field accepts an integer*",
                    "**Set** severity escalation rules for findings above threshold — *escalation rules define notification and workflow triggers*",
                    "**Enter** a change reason for the threshold modification — *the reason is captured for audit*",
                    "**Click** **Save Configuration** to apply — *thresholds are updated and take effect for subsequent reviews*",
                ],
                screenshot_slug="configuring-agent-review-thresholds",
            ),
        ],
        security_considerations=(
            "Compliance monitoring configuration directly affects regulatory readiness assessment. "
            "Lowering thresholds may mask compliance gaps during audits. Threshold changes should be "
            "reviewed by the quality management team before implementation. All compliance configuration "
            "changes are recorded in the audit trail. Risk tier assignments affect the level of human "
            "oversight required for AI operations."
        ),
        cross_ref_sections=["agent-registry-management", "audit-trail-administration"],
        user_guide_refs=["ai-agent-interaction"],
        urs_requirement_ids=["REQ-COMPLIANCE-01", "REQ-COMPLIANCE-02"],
        ai_guidelines_ref=True,
    ),
    AdminGuideSection(
        section_id="agent-registry-management",
        title="Agent Registry Management",
        overview=(
            "Agent Registry Management covers the YAML-based agent archetype configuration system, "
            "including understanding agent definition structure, adding and modifying agent archetypes, "
            "the hot-reload mechanism, and configuring company-specific audit profiles with agent assignment."
        ),
        prerequisites=[
            "System Administrator role",
            "Understanding of AI agent archetypes and their configuration parameters",
            "Access to the agent YAML configuration files or Agent Registry UI",
            "Knowledge of regulatory frameworks for audit profile configuration",
        ],
        procedures=[
            ProcedureBlock(
                title="Understanding Agent YAML Structure",
                steps=[
                    "**Navigate** to Admin > Agent Registry — *the agent registry view loads with all defined archetypes*",
                    "**Select** an agent archetype to view its configuration — *the YAML configuration is displayed in a structured view*",
                    "**Review** the personality section (name, domain expertise, communication style) — *personality attributes define the agent's review perspective*",
                    "**Review** the system prompts and evaluation rubrics — *these define how the agent evaluates documents*",
                    "**Note** the temperature and max_tokens settings — *these control generation behavior and output length*",
                    "**Review** the regulatory framework assignments — *frameworks determine which compliance standards the agent evaluates against*",
                ],
                screenshot_slug="understanding-agent-yaml",
            ),
            ProcedureBlock(
                title="Adding or Modifying an Agent Archetype",
                steps=[
                    "**Navigate** to Admin > Agent Registry — *the agent registry view loads*",
                    "**Click** **Add Agent** to create a new archetype or select an existing one to modify — *the agent editor opens*",
                    "**Configure** the agent personality (name, domain, expertise areas) — *personality fields accept your input*",
                    "**Define** the system prompt that guides the agent's review behavior — *the prompt editor accepts multi-line text*",
                    "**Set** the evaluation rubric with scoring criteria — *rubric fields define what the agent evaluates*",
                    "**Configure** temperature and max_tokens for generation control — *numeric fields accept the values*",
                    "**Click** **Save Agent** to persist the configuration — *the agent is saved and available for assignment*",
                    "**Verify** the hot-reload mechanism picks up the change — *the agent appears in the active registry within seconds*",
                ],
                screenshot_slug="adding-modifying-agent",
            ),
            ProcedureBlock(
                title="Configuring Company Audit Profiles",
                steps=[
                    "**Navigate** to Admin > Agent Registry > Audit Profiles — *the audit profile management view loads*",
                    "**Select** a company to configure its audit profile — *the company's current profile is displayed*",
                    "**Assign** agent archetypes to the company's review panel — *available agents are listed for selection*",
                    "**Configure** regulatory frameworks applicable to the company — *framework checkboxes allow multi-selection*",
                    "**Set** severity thresholds for finding escalation — *threshold fields accept numeric values*",
                    "**Configure** the review quorum (minimum agents required) — *the quorum field accepts an integer*",
                    "**Click** **Save Profile** to apply — *the audit profile is updated for the company*",
                ],
                screenshot_slug="configuring-audit-profiles",
            ),
        ],
        security_considerations=(
            "Agent configuration changes affect the quality and consistency of compliance reviews "
            "for all documents in the assigned companies. Incorrect temperature settings may produce "
            "unreliable or inconsistent review outputs. Agent modifications take effect immediately "
            "via hot-reload — test changes in a non-production profile first. All agent registry "
            "changes are recorded in the audit trail."
        ),
        cross_ref_sections=["compliance-monitoring", "ai-model-layer"],
        user_guide_refs=["ai-agent-interaction"],
        urs_requirement_ids=["REQ-AGENT-04", "REQ-AGENT-05", "REQ-AGENT-06"],
        ai_guidelines_ref=True,
    ),
    AdminGuideSection(
        section_id="workflow-administration",
        title="Workflow Administration",
        overview=(
            "Workflow Administration covers the BPMN visual editor for designing document lifecycle "
            "workflows, managing workflow definitions, and configuring document lifecycle states and "
            "transitions. Workflows enforce the governance process for all regulated documents."
        ),
        prerequisites=[
            "System Administrator role",
            "Understanding of BPMN notation and document lifecycle concepts",
            "Access to the Workflow Administration panel",
        ],
        procedures=[
            ProcedureBlock(
                title="Using the BPMN Workflow Editor",
                steps=[
                    "**Navigate** to Admin > Workflow Administration > Editor — *the BPMN visual editor loads*",
                    "**Select** an existing workflow to edit or click **Create Workflow** for a new one — *the workflow canvas opens*",
                    "**Drag** states (Draft, Review, Approved, InTraining, Active, Retired) onto the canvas — *state nodes appear on the canvas*",
                    "**Connect** states with transition arrows to define allowed state changes — *arrows indicate valid transitions*",
                    "**Configure** transition conditions and required permissions for each arrow — *the transition properties panel opens on click*",
                    "**Set** the document_tag that triggers this workflow (e.g., 'ALC-GOV') — *the tag field accepts the trigger value*",
                    "**Click** **Save Workflow** to persist the definition — *the workflow is saved and available for document assignment*",
                ],
                screenshot_slug="using-bpmn-workflow-editor",
            ),
            ProcedureBlock(
                title="Managing Workflow Definitions",
                steps=[
                    "**Navigate** to Admin > Workflow Administration > Definitions — *the workflow definition list loads*",
                    "**Review** existing workflow definitions with their assigned document tags — *each definition shows its trigger tag and state count*",
                    "**Click** on a workflow to view its state diagram — *the visual representation of states and transitions is displayed*",
                    "**Verify** the workflow covers all required lifecycle states — *all states are present in the diagram*",
                    "**Check** that transition permissions align with organizational roles — *permission requirements are listed for each transition*",
                ],
                screenshot_slug="managing-workflow-definitions",
            ),
        ],
        security_considerations=(
            "Workflow definitions control the governance process for regulated documents. Incorrect "
            "workflow configuration may allow documents to bypass required review steps. Changes to "
            "active workflows affect all documents currently in that lifecycle. Workflow modifications "
            "should be validated against regulatory requirements before deployment. All workflow "
            "administration changes are recorded in the audit trail. This setting affects user "
            "experience as described in User Guide Section 5 (Workflows)."
        ),
        cross_ref_sections=["administration-overview", "compliance-monitoring"],
        user_guide_refs=["workflows"],
        urs_requirement_ids=["REQ-WF-04", "REQ-WF-05"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="related-governance-documents",
        title="Related Governance Documents",
        overview=(
            "This section provides a comprehensive list of all governance documents within the ALC "
            "corporate environment that are referenced throughout this administrator guide, including "
            "their document UUIDs and current workflow states for traceability purposes."
        ),
        prerequisites=[
            "Access to the ALC Governance document folder",
        ],
        procedures=[
            ProcedureBlock(
                title="Accessing Governance Documents",
                steps=[
                    "**Navigate** to the Governance folder in the Documents section — *the governance document list loads with all ALC-GOV tagged documents*",
                    "**Review** the list of governance documents with their titles, UUIDs, and workflow states — *each document shows its current lifecycle state*",
                    "**Click** on a document title to open it for review — *the document detail view loads with full content*",
                    "**Verify** the document's workflow state is appropriate for reference (Approved or Active) — *the state badge indicates the current status*",
                ],
                screenshot_slug="accessing-governance-documents-admin",
            ),
        ],
        security_considerations=(
            "Governance documents contain controlled content subject to the formal document lifecycle. "
            "Only documents in Approved or Active state should be referenced for compliance purposes. "
            "Document access is controlled by RBAC permissions and company assignment."
        ),
        cross_ref_sections=["administration-overview", "compliance-monitoring"],
        user_guide_refs=["related-governance-documents"],
        urs_requirement_ids=["REQ-DM-01"],
        ai_guidelines_ref=False,
    ),
    AdminGuideSection(
        section_id="appendices",
        title="Appendices",
        overview=(
            "The Appendices provide supplementary reference material for administrators including "
            "CLI command reference, API endpoint summary, environment variable documentation, a "
            "comprehensive glossary of platform terminology, and troubleshooting guides for common "
            "administrative issues."
        ),
        prerequisites=[
            "System Administrator role for CLI and API access",
        ],
        procedures=[
            ProcedureBlock(
                title="Using CLI Administrative Commands",
                steps=[
                    "**Open** a terminal with access to the AlcoaBase backend environment — *the command prompt appears*",
                    "**Run** `uv run python -m alcoabase.scripts.generate_urs_alc` to generate the URS document — *the URS generation report is printed to stdout*",
                    "**Run** `uv run python -m alcoabase.scripts.generate_ai_guidelines` to generate AI guidelines — *the guidelines generation report is printed to stdout*",
                    "**Run** `uv run python -m alcoabase.scripts.generate_documentation` to generate user and admin guides — *the documentation generation report is printed to stdout*",
                    "**Run** `uv run python -m alcoabase.scripts.bulk_upload --directory /path/to/files` to bulk upload documents — *the upload progress and summary are displayed*",
                    "**Run** `uv run python -m alcoabase.scripts.ensure_tables` to verify database schema — *table verification results are printed*",
                    "**Verify** each command exits with code 0 on success — *a non-zero exit code indicates an error requiring investigation*",
                ],
                screenshot_slug="using-cli-commands",
            ),
            ProcedureBlock(
                title="Troubleshooting Common Administrative Issues",
                steps=[
                    "**Identify** the error message or unexpected behavior — *note the exact error text and context*",
                    "**Check** the system health dashboard for service connectivity issues — *service status indicators reveal infrastructure problems*",
                    "**Review** the audit trail for recent changes that may have caused the issue — *filter by time range around the issue occurrence*",
                    "**Consult** the troubleshooting table below for known issues and resolutions — *common issues are listed with step-by-step fixes*",
                    "**Escalate** to infrastructure support if the issue is not resolved by standard troubleshooting — *provide error details, timestamps, and steps already attempted*",
                ],
                screenshot_slug="troubleshooting-admin-issues",
            ),
        ],
        security_considerations=(
            "CLI commands execute with the permissions of the operating system user running them. "
            "Ensure CLI access is restricted to authorized administrators. API endpoints require "
            "proper authentication and role-based authorization. Environment variables may contain "
            "sensitive configuration — protect .env files with appropriate file system permissions."
        ),
        cross_ref_sections=["system-configuration", "administration-overview"],
        user_guide_refs=["appendices"],
        urs_requirement_ids=["REQ-SYS-01", "REQ-ADMIN-01"],
        ai_guidelines_ref=False,
    ),
]


# ---------------------------------------------------------------------------
# Content Assembly Functions
# ---------------------------------------------------------------------------


def assemble_document_header(
    title: str,
    version_number: int,
    target_audience: str,
) -> str:
    """Assemble the document header section with metadata table.

    Args:
        title: Document title.
        version_number: Current version number.
        target_audience: Target audience description (e.g., "End-Users").

    Returns:
        Markdown string for the document header section.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    platform_version = "1.0.0"

    header = f"# {title}\n\n"
    header += "## Document Header\n\n"
    header += "| Field | Value |\n"
    header += "|-------|-------|\n"
    header += f"| **Document Title** | {title} |\n"
    header += f"| **Document Type** | {DOCUMENTATION_DOCUMENT_TYPE} |\n"
    header += f"| **Version** | {version_number} |\n"
    header += f"| **Generated** | {timestamp} |\n"
    header += f"| **Target Audience** | {target_audience} |\n"
    header += f"| **Platform Version** | {platform_version} |\n"
    header += (
        "| **Classification** | Controlled Document — ALC Governance |\n"
    )
    header += "\n### Revision History\n\n"
    header += "| Version | Date | Author | Description |\n"
    header += "|---------|------|--------|-------------|\n"
    header += (
        f"| {version_number} | {timestamp} | "
        "Documentation Generator Service | Automated generation |\n"
    )
    header += "\n"
    return header


def assemble_table_of_contents(sections: list[UserGuideSection] | list[AdminGuideSection]) -> str:
    """Assemble the Table of Contents from section definitions.

    Generates a ToC listing all level-2 (sections) and level-3 (procedures)
    headings with section numbers.

    Args:
        sections: List of section configurations.

    Returns:
        Markdown string for the Table of Contents section.
    """
    toc = "## Table of Contents\n\n"
    for idx, section in enumerate(sections, 1):
        toc += f"- **{idx}. {section.title}**\n"
        for proc_idx, procedure in enumerate(section.procedures, 1):
            toc += f"  - {idx}.{proc_idx} {procedure.title}\n"
    toc += "\n"
    return toc


def assemble_user_guide_section(
    section: UserGuideSection,
    section_number: int,
    cross_refs: CrossReferenceContext,
) -> str:
    """Assemble a single User Guide section with all required subsections.

    Produces: overview, procedures with screenshots, tips, cross-references.

    Args:
        section: The UserGuideSection configuration.
        section_number: The section number (1-based).
        cross_refs: Cross-reference context for URS/AI Guidelines links.

    Returns:
        Markdown string for the complete section.
    """
    content = f"\n---\n\n## {section_number}. {section.title}\n\n"

    # (a) Overview
    content += f"{section.overview}\n\n"

    # (b) Procedures with screenshots
    for proc_idx, procedure in enumerate(section.procedures, 1):
        content += f"### {section_number}.{proc_idx} Procedure: {procedure.title}\n\n"
        for step_idx, step in enumerate(procedure.steps, 1):
            content += f"{step_idx}. {step}\n"
        content += "\n"
        # (c) Screenshot placeholder
        alt_text = f"{procedure.title} — {section.title}"
        content += (
            f"![{alt_text}](screenshots/{section.section_id}/"
            f"{procedure.screenshot_slug}.png)\n\n"
        )

    # (d) Tips and Best Practices
    content += "### Tips and Best Practices\n\n"
    for tip in section.tips:
        content += f"- {tip}\n"
    content += "\n"

    # (e) Cross-Reference Block
    content += _assemble_cross_reference_block(
        section=section,
        cross_refs=cross_refs,
        guide_type="user",
    )

    return content


def assemble_admin_guide_section(
    section: AdminGuideSection,
    section_number: int,
    cross_refs: CrossReferenceContext,
) -> str:
    """Assemble a single Admin Guide section with all required subsections.

    Produces: overview, prerequisites, procedures with screenshots,
    security considerations, cross-references.

    Args:
        section: The AdminGuideSection configuration.
        section_number: The section number (1-based).
        cross_refs: Cross-reference context for URS/AI Guidelines links.

    Returns:
        Markdown string for the complete section.
    """
    content = f"\n---\n\n## {section_number}. {section.title}\n\n"

    # (a) Overview
    content += f"{section.overview}\n\n"

    # (b) Prerequisites
    content += "### Prerequisites\n\n"
    for prereq in section.prerequisites:
        content += f"- {prereq}\n"
    content += "\n"

    # (c) Procedures with screenshots
    for proc_idx, procedure in enumerate(section.procedures, 1):
        content += f"### {section_number}.{proc_idx} Procedure: {procedure.title}\n\n"
        for step_idx, step in enumerate(procedure.steps, 1):
            content += f"{step_idx}. {step}\n"
        content += "\n"
        # (d) Screenshot placeholder
        alt_text = f"{procedure.title} — {section.title}"
        content += (
            f"![{alt_text}](screenshots/{section.section_id}/"
            f"{procedure.screenshot_slug}.png)\n\n"
        )

    # (e) Security Considerations
    content += "### Security Considerations\n\n"
    content += f"{section.security_considerations}\n\n"

    # (f) Cross-Reference Block
    content += _assemble_cross_reference_block(
        section=section,
        cross_refs=cross_refs,
        guide_type="admin",
    )

    return content


def _assemble_cross_reference_block(
    section: UserGuideSection | AdminGuideSection,
    cross_refs: CrossReferenceContext,
    guide_type: str,
) -> str:
    """Assemble the cross-reference block for a guide section.

    Includes URS requirement references, AI Guidelines references,
    inter-guide references, and intra-guide section references.

    Args:
        section: The section configuration (User or Admin).
        cross_refs: Cross-reference context with availability flags.
        guide_type: Either "user" or "admin".

    Returns:
        Markdown string for the cross-reference block.
    """
    block = "### Cross-References\n\n"

    # URS Requirement cross-references
    if cross_refs.urs_available and section.urs_requirement_ids:
        block += "**URS Traceability:**\n\n"
        for req_id in section.urs_requirement_ids:
            block += f"- Implements: {req_id}\n"
        if cross_refs.urs_document_uuid:
            block += (
                f"\n*Reference: {cross_refs.urs_document_title} "
                f"(UUID: {cross_refs.urs_document_uuid})*\n"
            )
        block += "\n"
    elif section.urs_requirement_ids:
        block += (
            "> URS cross-references unavailable — generate URS "
            "(Phase 8.3) for full traceability.\n\n"
        )

    # AI Guidelines cross-references
    if section.ai_guidelines_ref:
        if cross_refs.ai_guidelines_available and cross_refs.ai_guidelines_documents:
            block += "**AI Usage Guidelines:**\n\n"
            block += (
                "Consult the following AI Usage Guidelines for compliance "
                "requirements and permitted use policies:\n\n"
            )
            for doc in cross_refs.ai_guidelines_documents:
                doc_title = doc.get("title", "AI Usage Guidelines")
                doc_uuid = doc.get("uuid", "N/A")
                block += f"- {doc_title} (UUID: {doc_uuid})\n"
            block += "\n"
        else:
            block += (
                "> AI Usage Guidelines cross-references unavailable — "
                "generate guidelines (Phase 8.4) for compliance context.\n\n"
            )

    # Inter-guide cross-references
    if guide_type == "user" and isinstance(section, UserGuideSection):
        # User Guide references to Admin Guide
        if section.section_id in (
            "workflows", "search-and-knowledge-base",
            "ai-agent-interaction", "ai-document-generator",
        ):
            block += (
                "*Contact your administrator to configure related settings "
                "— see Admin Guide Section for administrative procedures.*\n\n"
            )
    elif guide_type == "admin" and isinstance(section, AdminGuideSection):
        # Admin Guide references to User Guide
        if section.user_guide_refs:
            refs = ", ".join(
                f"User Guide Section ({ref})" for ref in section.user_guide_refs
            )
            block += (
                f"*This setting affects user experience as described in "
                f"{refs}.*\n\n"
            )

    # Intra-guide section references
    if section.cross_ref_sections:
        block += "**Related Sections:**\n\n"
        for ref_id in section.cross_ref_sections:
            block += f"- See section: {ref_id}\n"
        block += "\n"

    return block


def assemble_related_governance_documents(
    cross_refs: CrossReferenceContext,
) -> str:
    """Assemble the Related Governance Documents section.

    Lists all ALC-GOV documents with title, UUID, and workflow state.

    Args:
        cross_refs: Cross-reference context containing governance documents.

    Returns:
        Markdown string for the Related Governance Documents section.
    """
    content = "\n### Related Governance Documents — Full Listing\n\n"

    if cross_refs.governance_documents:
        content += (
            "The following governance documents are available in the "
            "ALC corporate environment:\n\n"
        )
        content += "| Document Title | UUID | Workflow State |\n"
        content += "|----------------|------|----------------|\n"
        for doc in cross_refs.governance_documents:
            doc_title = doc.get("title", "Untitled")
            doc_uuid = doc.get("uuid", "N/A")
            doc_state = doc.get("state", "Unknown")
            content += f"| {doc_title} | {doc_uuid} | {doc_state} |\n"
        content += "\n"
    else:
        content += (
            "*No governance documents are currently available in the "
            "ALC corporate environment. Run Phase 8.2, 8.3, and 8.4 "
            "seed scripts to populate governance documents.*\n\n"
        )

    return content


def assemble_user_guide_appendices(cross_refs: CrossReferenceContext) -> str:
    """Assemble the User Guide appendices content.

    Includes keyboard shortcuts, glossary, troubleshooting, and URS
    traceability references.

    Args:
        cross_refs: Cross-reference context for URS traceability.

    Returns:
        Markdown string for the appendices content.
    """
    content = "\n### Keyboard Shortcuts\n\n"
    content += "| Shortcut | Action |\n"
    content += "|----------|--------|\n"
    content += "| Ctrl+K / Cmd+K | Open command palette |\n"
    content += "| Ctrl+S / Cmd+S | Save current form |\n"
    content += "| Ctrl+F / Cmd+F | Focus search field |\n"
    content += "| Escape | Close dialog or overlay |\n"
    content += "| Tab | Navigate between form fields |\n"
    content += "\n"

    content += "### Glossary\n\n"
    content += "| Term | Definition |\n"
    content += "|------|------------|\n"
    content += (
        "| ALCOA+ | Attributable, Legible, Contemporaneous, Original, "
        "Accurate + Complete, Consistent, Enduring, Available |\n"
    )
    content += (
        "| Document-UUID | Unique identifier assigned to each document "
        "in format YYYY-NNNNN |\n"
    )
    content += (
        "| GxP | Good Practice regulations (GMP, GLP, GCP, GDP) |\n"
    )
    content += (
        "| HITL | Human-In-The-Loop — mandatory human review checkpoint "
        "for AI operations |\n"
    )
    content += (
        "| RAG | Retrieval-Augmented Generation — AI technique combining "
        "document retrieval with language generation |\n"
    )
    content += (
        "| RBAC | Role-Based Access Control — permission model based on "
        "user roles |\n"
    )
    content += (
        "| URS | User Requirement Specifications — formal requirements "
        "document |\n"
    )
    content += (
        "| Workflow State | Current lifecycle position of a document "
        "(Draft, Review, Approved, InTraining, Active, Retired) |\n"
    )
    content += "\n"

    content += "### Troubleshooting\n\n"
    content += "| Issue | Possible Cause | Resolution |\n"
    content += "|-------|---------------|------------|\n"
    content += (
        "| Cannot log in | Expired password or deactivated account | "
        "Contact your administrator for password reset or account reactivation |\n"
    )
    content += (
        "| Document upload fails | File size exceeds quota or unsupported format | "
        "Check file size limits and supported formats in system configuration |\n"
    )
    content += (
        "| Search returns no results | Index not yet updated | "
        "Wait 30 seconds after upload for indexing to complete |\n"
    )
    content += (
        "| Workflow transition blocked | Missing required training or signature | "
        "Complete pending training tasks and apply required signatures |\n"
    )
    content += "\n"

    content += "### URS Traceability References\n\n"
    if cross_refs.urs_available:
        content += (
            f"This guide implements requirements from the "
            f"{cross_refs.urs_document_title} "
            f"(UUID: {cross_refs.urs_document_uuid}). "
            "Each section includes specific Requirement_ID cross-references "
            "in the format Implements: REQ-{MODULE}-{NN}.\n\n"
        )
    else:
        content += (
            "> URS cross-references unavailable — generate URS "
            "(Phase 8.3) for full traceability.\n\n"
        )

    return content


def assemble_admin_guide_appendices(cross_refs: CrossReferenceContext) -> str:
    """Assemble the Admin Guide appendices content.

    Includes CLI reference, API endpoints, environment variables,
    glossary, troubleshooting, and URS traceability.

    Args:
        cross_refs: Cross-reference context for URS traceability.

    Returns:
        Markdown string for the appendices content.
    """
    content = "\n### CLI Reference\n\n"
    content += "| Command | Description | Example |\n"
    content += "|---------|-------------|----------|\n"
    content += (
        "| `uv run python -m alcoabase.scripts.generate_urs_alc` | "
        "Generate the Enhanced URS document | "
        "`uv run python -m alcoabase.scripts.generate_urs_alc` |\n"
    )
    content += (
        "| `uv run python -m alcoabase.scripts.generate_ai_guidelines` | "
        "Generate AI Usage Guidelines documents | "
        "`uv run python -m alcoabase.scripts.generate_ai_guidelines` |\n"
    )
    content += (
        "| `uv run python -m alcoabase.scripts.generate_documentation` | "
        "Generate User Guide and Admin Guide | "
        "`uv run python -m alcoabase.scripts.generate_documentation` |\n"
    )
    content += (
        "| `uv run python -m alcoabase.scripts.bulk_upload` | "
        "Bulk upload documents from a directory | "
        "`uv run python -m alcoabase.scripts.bulk_upload --directory /path/to/files` |\n"
    )
    content += (
        "| `uv run python -m alcoabase.scripts.ensure_tables` | "
        "Verify and create database tables | "
        "`uv run python -m alcoabase.scripts.ensure_tables` |\n"
    )
    content += "\n"

    content += "### API Endpoints Summary\n\n"
    content += "| Method | Endpoint | Description | Auth Required |\n"
    content += "|--------|----------|-------------|---------------|\n"
    content += (
        "| POST | /api/admin/generate-documentation | "
        "Generate documentation suite | System/Document Administrator |\n"
    )
    content += (
        "| POST | /api/documents/upload | "
        "Upload a single document | Authenticated user |\n"
    )
    content += (
        "| GET | /api/documents | "
        "List documents with filtering | Authenticated user |\n"
    )
    content += (
        "| POST | /api/workflows/transition | "
        "Trigger workflow state transition | Authenticated user |\n"
    )
    content += (
        "| GET | /api/admin/users | "
        "List all users | System Administrator |\n"
    )
    content += "\n"

    content += "### Environment Variables\n\n"
    content += "| Variable | Description | Default | Component |\n"
    content += "|----------|-------------|---------|----------|\n"
    content += (
        "| DATABASE_URL | PostgreSQL connection string | required | Backend |\n"
    )
    content += (
        "| REDIS_URL | Redis connection string | redis://localhost:6379 | Backend |\n"
    )
    content += (
        "| MINIO_ENDPOINT | MinIO server endpoint | localhost:9000 | Storage |\n"
    )
    content += (
        "| MINIO_ACCESS_KEY | MinIO access key | required | Storage |\n"
    )
    content += (
        "| MINIO_SECRET_KEY | MinIO secret key | required | Storage |\n"
    )
    content += (
        "| OPENSEARCH_URL | OpenSearch connection URL | "
        "http://localhost:9200 | Search |\n"
    )
    content += (
        "| VLLM_BASE_URL | vLLM inference server URL | "
        "http://localhost:8000 | AI Inference |\n"
    )
    content += (
        "| AI_HARDWARE_MODE | AI hardware mode (gpu/cpu/mock) | "
        "mock | AI Inference |\n"
    )
    content += (
        "| JWT_SECRET_KEY | Secret key for JWT token signing | "
        "required | Authentication |\n"
    )
    content += (
        "| BACKUP_SCHEDULE | Cron expression for backup schedule | "
        "0 2 * * * | Backup |\n"
    )
    content += "\n"

    content += "### Glossary\n\n"
    content += "| Term | Definition |\n"
    content += "|------|------------|\n"
    content += (
        "| ALCOA+ | Attributable, Legible, Contemporaneous, Original, "
        "Accurate + Complete, Consistent, Enduring, Available |\n"
    )
    content += (
        "| Advisory Lock | PostgreSQL mechanism to prevent concurrent "
        "execution of critical operations |\n"
    )
    content += (
        "| BPMN | Business Process Model and Notation — standard for "
        "workflow visualization |\n"
    )
    content += (
        "| Document-UUID | Unique identifier assigned to each document "
        "in format YYYY-NNNNN |\n"
    )
    content += (
        "| GxP | Good Practice regulations (GMP, GLP, GCP, GDP) |\n"
    )
    content += (
        "| HITL | Human-In-The-Loop — mandatory human review checkpoint "
        "for AI operations |\n"
    )
    content += (
        "| Hot-Reload | Mechanism for applying configuration changes "
        "without service restart |\n"
    )
    content += (
        "| RBAC | Role-Based Access Control — permission model based on "
        "user roles |\n"
    )
    content += (
        "| vLLM | High-throughput LLM inference engine used for AI "
        "operations |\n"
    )
    content += "\n"

    content += "### Troubleshooting\n\n"
    content += "| Issue | Possible Cause | Resolution |\n"
    content += "|-------|---------------|------------|\n"
    content += (
        "| vLLM service unhealthy | GPU memory exhausted or model not loaded | "
        "Check GPU memory usage, restart vLLM service, verify model weights path |\n"
    )
    content += (
        "| Database connection refused | PostgreSQL service down or connection pool exhausted | "
        "Check PostgreSQL status, review connection pool settings |\n"
    )
    content += (
        "| MinIO upload fails | Storage quota exceeded or bucket not found | "
        "Check storage quotas, verify bucket exists and permissions are correct |\n"
    )
    content += (
        "| OpenSearch indexing delayed | Cluster health yellow/red or resource constraints | "
        "Check cluster health, review shard allocation and disk space |\n"
    )
    content += "\n"

    content += "### URS Traceability References\n\n"
    if cross_refs.urs_available:
        content += (
            f"This guide implements requirements from the "
            f"{cross_refs.urs_document_title} "
            f"(UUID: {cross_refs.urs_document_uuid}). "
            "Each section includes specific Requirement_ID cross-references "
            "in the format Implements: REQ-{MODULE}-{NN}.\n\n"
        )
    else:
        content += (
            "> URS cross-references unavailable — generate URS "
            "(Phase 8.3) for full traceability.\n\n"
        )

    return content


# ---------------------------------------------------------------------------
# Full Document Assembly Functions
# ---------------------------------------------------------------------------


def assemble_user_guide(
    cross_refs: CrossReferenceContext,
    version_number: int,
) -> str:
    """Assemble the complete User Guide document.

    Combines header, table of contents, all 12 sections, and appendices
    into a single Markdown document.

    Args:
        cross_refs: Cross-reference context for dynamic content.
        version_number: Version number to embed in header.

    Returns:
        Complete User Guide Markdown string.
    """
    parts: list[str] = []

    # Document header
    parts.append(
        assemble_document_header(
            title=USER_GUIDE_TITLE,
            version_number=version_number,
            target_audience="End-Users",
        )
    )

    # Table of Contents
    parts.append(assemble_table_of_contents(USER_GUIDE_SECTIONS))

    # All sections
    for idx, section in enumerate(USER_GUIDE_SECTIONS, 1):
        section_content = assemble_user_guide_section(
            section=section,
            section_number=idx,
            cross_refs=cross_refs,
        )
        parts.append(section_content)

        # Add Related Governance Documents listing in the dedicated section
        if section.section_id == "related-governance-documents":
            parts.append(assemble_related_governance_documents(cross_refs))

        # Add appendices content in the appendices section
        if section.section_id == "appendices":
            parts.append(assemble_user_guide_appendices(cross_refs))

    return "".join(parts)


def assemble_admin_guide(
    cross_refs: CrossReferenceContext,
    version_number: int,
) -> str:
    """Assemble the complete Admin Guide document.

    Combines header, table of contents, all 12 sections, and appendices
    into a single Markdown document.

    Args:
        cross_refs: Cross-reference context for dynamic content.
        version_number: Version number to embed in header.

    Returns:
        Complete Admin Guide Markdown string.
    """
    parts: list[str] = []

    # Document header
    parts.append(
        assemble_document_header(
            title=ADMIN_GUIDE_TITLE,
            version_number=version_number,
            target_audience="Administrators",
        )
    )

    # Table of Contents
    parts.append(assemble_table_of_contents(ADMIN_GUIDE_SECTIONS))

    # All sections
    for idx, section in enumerate(ADMIN_GUIDE_SECTIONS, 1):
        section_content = assemble_admin_guide_section(
            section=section,
            section_number=idx,
            cross_refs=cross_refs,
        )
        parts.append(section_content)

        # Add Related Governance Documents listing in the dedicated section
        if section.section_id == "related-governance-documents":
            parts.append(assemble_related_governance_documents(cross_refs))

        # Add appendices content in the appendices section
        if section.section_id == "appendices":
            parts.append(assemble_admin_guide_appendices(cross_refs))

    return "".join(parts)
