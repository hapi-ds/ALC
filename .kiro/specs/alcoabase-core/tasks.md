# Tasks: AlcoaBase Core

## Task 1: Project Scaffolding and Infrastructure Setup

- [ ] 1.1 Create Docker Compose configuration with services: PostgreSQL, MinIO, OpenSearch, Redis, backend (FastAPI), frontend (React/Vite), vLLM, Celery worker, CSV runner (Playwright)
- [ ] 1.2 Create backend Python project with `uv` and `pyproject.toml` using `src/` layout (`src/backend/src/alcoabase/`)
- [ ] 1.3 Create FastAPI application entry point (`main.py`) with CORS, middleware registration, and API router
- [ ] 1.4 Create Pydantic Settings configuration (`config.py`) loading from environment variables: database URL, MinIO credentials, Redis URL, OpenSearch URL, vLLM base URL, and model configuration (MODEL_CHAT_NAME, MODEL_CHAT_PATH, MODEL_CHAT_MAX_GPU_MEMORY_GB, MODEL_EMBEDDING_NAME, MODEL_EMBEDDING_PATH, MODEL_EMBEDDING_DIMENSION, MODEL_OCR_NAME, MODEL_OCR_PATH, GPU_DEVICE_ID, MODEL_MANAGER_MODE)
- [ ] 1.5 Create SQLAlchemy 2.0 async engine and session factory (`database.py`) with SQLAlchemy-Continuum plugin initialization
- [ ] 1.6 Create frontend React project with Vite, TypeScript, Tailwind CSS, and shadcn/ui
- [ ] 1.7 Create `.env.example` with all required environment variables documented, including model configuration section (chat LLM name/path/memory, embedding model name/path/dimension, OCR model name/path, GPU device ID, model manager mode)
- [ ] 1.8 Create Dockerfiles for backend (multi-stage, non-root), frontend (multi-stage nginx), and CSV runner (Playwright base image)

## Task 2: Database Models and Audit Infrastructure

- [ ] 2.1 Create `AuditMixin` class with SQLAlchemy-Continuum `__versioned__` configuration that excludes `is_csv_validation_record`
- [ ] 2.2 Create `User` and `Role` models with ABAC permission fields
- [ ] 2.3 Create `Document` model with Document-UUID, title, folder_path, document_type, current_status, tags relationship, versions relationship, and `is_csv_validation_record` flag
- [ ] 2.4 Create `DocumentVersion` model with major/minor version, storage_key, file_hash, change_reason
- [ ] 2.5 Create `Template` and `TemplateField` models with JSON schema, status (Draft/ReadOnly), and Field-UUID fields
- [ ] 2.6 Create `Report` and `ReportFieldValue` models for extracted PDF data storage
- [ ] 2.7 Create `WorkflowDefinition` model with `document_tag` (unique, indexed), `bpmn_xml`, `signature_required_transitions` (JSON list of transition strings, e.g. `["Review→Approved"]`), `training_trigger_transitions` (JSON list), and `is_active` flag; create `DocumentState` model for tracking current document state
- [ ] 2.8 Create `SignatureRecord` model for PAdES signature event logging
- [ ] 2.9 Create `TrainingTask` and `TrainingRecord` models with SOP version linkage and completion status
- [ ] 2.10 Create `AgentDefinition` model for persisted agent configurations
- [ ] 2.11 Create `VirtualFolder` model with name (unique), tag_filter (JSON), sort_order, is_system_default flag, and created_by foreign key
- [ ] 2.12 Create Alembic migration configuration and initial migration
- [ ] 2.13 Create audit middleware that injects user_id, reason_for_change, and server-side UTC timestamp into Continuum transaction context

## Task 3: UUID Generation Service

- [ ] 3.1 Create `UUIDService` with `generate_document_uuid()` using PostgreSQL year-based sequence (`YYYY-NNNNN` format)
- [ ] 3.2 Create `generate_field_uuid()` method producing `FLD-{hex8}` format Field-UUIDs
- [ ] 3.3 Create Pydantic schemas for UUID validation (Document-UUID pattern, Field-UUID pattern)
- [ ] 3.4 Write property-based tests: Document-UUID format compliance and uniqueness across 1000 generations
- [ ] 3.5 Write property-based tests: Field-UUID format compliance and uniqueness within generated batches

## Task 4: Document Service (CRUD + Versioning)

- [ ] 4.1 Create `StorageService` wrapping MinIO (aioboto3) with upload, download, and delete operations
- [ ] 4.2 Create `DocumentService` with `create_document()`: generate UUID, store file in MinIO, persist metadata in PostgreSQL in single transaction, rollback on MinIO failure
- [ ] 4.3 Create `create_version()` method: increment major/minor version, store new file, retain all previous versions
- [ ] 4.4 Create `get_document()` and `get_version()` retrieval methods
- [ ] 4.5 Create `search_documents()` method: filter by tag, folder_path, Document-UUID with pagination
- [ ] 4.6 Create Pydantic request/response schemas for document endpoints
- [ ] 4.7 Create FastAPI router `/api/documents` with POST (create), POST (version), GET (retrieve), GET (search) endpoints
- [ ] 4.8 Create virtual folder CRUD: `POST /api/virtual-folders` (create with name, tag_filter JSON, sort_order), `GET /api/virtual-folders` (list all), `GET /api/virtual-folders/{id}/documents` (dynamic query matching tag_filter), `PUT /api/virtual-folders/{id}` (update), `DELETE /api/virtual-folders/{id}` (reject deletion of system defaults)
- [ ] 4.9 Create seed data for default virtual folders: "All SOPs" (tags=SOP), "All Reports" (tags=Report), "All Templates" (tags=Template), "Approved Documents" (status=Approved), "Documents In Training" (status=InTraining)
- [ ] 4.10 Write unit tests for DocumentService: creation, versioning, search, error handling on storage failure
- [ ] 4.11 Write unit tests for virtual folders: CRUD operations, dynamic document filtering by tag_filter, system default deletion protection

## Task 5: Template Service and Visual Form Builder

- [ ] 5.1 Create `TemplateService` with `create_template()`: generate Document-UUID, assign Field-UUIDs to all fields, validate uniqueness, set status to ReadOnly
- [ ] 5.2 Create template immutability enforcement: reject modifications to ReadOnly templates with HTTP 400
- [ ] 5.3 Create Pydantic schemas for template JSON schema validation (field types: Text, Float, Integer, Date, Boolean)
- [ ] 5.4 Create FastAPI router `/api/templates` with POST (create), GET (retrieve), GET (list) endpoints
- [ ] 5.5 Write property-based tests: Field-UUID uniqueness within template for templates with 1-100 fields
- [ ] 5.6 Write property-based tests: ReadOnly immutability — all modification attempts rejected after status set

## Task 6: PDF Generator (ReportLab)

- [ ] 6.1 Create `PDFGenerator` with `generate_offline_pdf()`: create AcroForm PDF from template JSON schema with field names set to Field-UUIDs
- [ ] 6.2 Implement Document-UUID embedding as hidden AcroForm field `__DOC_UUID__` in generated PDFs
- [ ] 6.3 Implement field type constraints in AcroForm (text fields, numeric validation hints)
- [ ] 6.4 Create FastAPI endpoint `POST /api/templates/{uuid}/download-pdf` with ReadOnly status validation (reject non-ReadOnly with HTTP 400)
- [ ] 6.5 Integrate MinIO storage for generated PDFs and audit trail recording
- [ ] 6.6 Write property-based tests: for all generated PDFs, every Field-UUID in template has exactly one corresponding AcroForm field

## Task 7: PDF Extractor (PyMuPDF)

- [ ] 7.1 Create `PDFExtractor` with `extract_data()`: read `__DOC_UUID__` hidden field, match to template
- [ ] 7.2 Implement field value extraction by Field-UUID AcroForm field names (no OCR, no visual label dependency)
- [ ] 7.3 Implement type validation: validate each extracted value against template field type (Float, Text, etc.)
- [ ] 7.4 Implement atomic persistence: persist all extracted values to PostgreSQL or reject entirely on any validation failure (no partial data)
- [ ] 7.5 Create FastAPI endpoint `POST /api/reports/upload-pdf` with error responses for unknown Document-UUID (HTTP 400) and type validation failures (HTTP 400 with all errors)
- [ ] 7.6 Write property-based tests: PDF round-trip integrity — `extract(generate(template, data)) == data` for random templates and values
- [ ] 7.7 Write property-based tests: Document-UUID round-trip — extracted UUID equals embedded UUID for all generated PDFs
- [ ] 7.8 Write property-based tests: type validation rejection — invalid values (non-numeric in Float fields) are rejected with no partial persistence

## Task 8: Workflow Engine (SpiffWorkflow)

- [ ] 8.1 Create `WorkflowEngine` with SpiffWorkflow integration: load BPMN XML definitions, validate transitions against workflow
- [ ] 8.2 Implement tag-based workflow resolution: match document tags against `WorkflowDefinition.document_tag` to resolve the applicable BPMN workflow; return HTTP 400 if no workflow is defined for the document's tag
- [ ] 8.3 Implement state transition enforcement: accept valid transitions, reject invalid with HTTP 400 and unchanged state
- [ ] 8.4 Implement BPMN workflow validation on admin save: detect unreachable states, missing terminal states, unique `document_tag` constraint, and validate that all entries in `signature_required_transitions` reference valid transitions in the BPMN definition
- [ ] 8.5 Implement audit trail recording for all state transitions (user_id, timestamp, previous_state, new_state)
- [ ] 8.6 Implement configurable trigger hooks: check `signature_required_transitions` list to delegate to Signature_Service for any matching transition; check `training_trigger_transitions` list to trigger Training_Service for matching transitions
- [ ] 8.7 Create seed data for default SOP workflow (tag="SOP": Draft → Review → Approved → InTraining → Active, signature on Review→Approved, training trigger on Approved→InTraining) and default Report workflow (tag="Report": Draft → RecordsFilled → Reviewed → Approved, signature on all transitions)
- [ ] 8.8 Create FastAPI router `/api/workflows` with POST (create workflow with document_tag binding), PUT (update workflow), POST (request transition), GET (document state), GET (list workflows) endpoints
- [ ] 8.9 Write property-based tests: for all states and target states, only BPMN-defined transitions are accepted
- [ ] 8.10 Write property-based tests: BPMN validation detects unreachable states, missing terminals, and invalid signature_required_transitions references in random graph structures
- [ ] 8.11 Write unit tests: tag-based workflow resolution returns correct workflow for document tag, returns HTTP 400 for unregistered tags

## Task 9: Signature Service (PAdES)

- [ ] 9.1 Create `SignatureService` with re-authentication enforcement: verify password/PIN before signing; accept transition-specific reason from Workflow_Engine (e.g., "Records completed by analyst", "Reviewed by supervisor", "Approved by QA")
- [ ] 9.2 Implement PAdES PDF signing using pyHanko with user x.509 certificates
- [ ] 9.3 Implement visual signature stamp embedding: signer name, date, time, and transition-specific reason for signature
- [ ] 9.4 Implement incremental PAdES signatures: support multiple signatures accumulating on the same PDF (e.g., analyst signs RecordsFilled, then reviewer signs Reviewed, then QA signs Approved)
- [ ] 9.5 Implement audit trail recording for all signature events (signer user_id, timestamp, Document-UUID, transition, reason)
- [ ] 9.6 Create FastAPI endpoint `POST /api/signatures/sign` with re-authentication flow, accepting document_uuid, transition identifier, and reason
- [ ] 9.7 Write property-based tests: for all signed PDFs, any byte modification invalidates the PAdES signature
- [ ] 9.8 Write unit tests: incremental signatures — PDF with N sequential signatures validates all N signatures; modifying bytes after any signature invalidates from that point forward

## Task 10: Training Service (ABAC Gate)

- [ ] 10.1 Create `TrainingService` with automatic training assignment: on SOP major version approval, transition to InTraining and generate tasks for all assigned-role users
- [ ] 10.2 Implement training task generation: "Read and understand [SOP-Name] v[Version]" per user, with audit trail recording
- [ ] 10.3 Implement training completion tracking: when all users complete tasks, auto-transition SOP from InTraining to Active
- [ ] 10.4 Implement training execution gate: `check_training_gate()` verifying valid training record for exact SOP version, returning HTTP 403 with specific error message for untrained users
- [ ] 10.5 Implement training record invalidation: on new major SOP version activation, invalidate all previous major version training records
- [ ] 10.6 Create FastAPI router `/api/training` with GET (tasks), POST (complete task), GET (training status) endpoints
- [ ] 10.7 Write property-based tests: training gate permits access if and only if valid training record exists for exact SOP version
- [ ] 10.8 Write property-based tests: training task generation creates exactly one task per assigned-role user with no duplicates or omissions

## Task 11: Audit Service and Immutability Enforcement

- [ ] 11.1 Configure SQLAlchemy-Continuum to auto-create version tables for all AuditMixin models
- [ ] 11.2 Implement reason-for-change requirement: reject modifications without X-Change-Reason header
- [ ] 11.3 Implement server-side UTC timestamp injection independent of client clock
- [ ] 11.4 Implement DELETE endpoint blocking: API router explicitly excludes DELETE for all `*_version` tables, middleware returns HTTP 403 for any DELETE attempt on audit tables
- [ ] 11.5 Create FastAPI endpoint `GET /api/audit/{record_type}/{record_id}` returning version history in chronological order
- [ ] 11.6 Write property-based tests: audit trail completeness — N modifications produce exactly N version entries with monotonically increasing, gap-free sequence
- [ ] 11.7 Write property-based tests: audit trail immutability — DELETE attempts on all audit endpoints return HTTP 403

## Task 12: Knowledge Service (Document Indexing + Search)

- [ ] 12.1 Create `KnowledgeService` with document text extraction: support digital PDF (PyMuPDF), DOCX (python-docx), and plain text formats
- [ ] 12.2 Implement scanned PDF detection: check if PDF pages contain extractable text; if not, delegate to OCR_Engine for vision-LLM-based text extraction
- [ ] 12.3 Implement text chunking: 512-token chunks with 50-token overlap
- [ ] 12.4 Implement multilingual vector embedding generation via Model_Manager: call `ensure_model(EMBEDDING)` to load the multilingual embedding model, then generate embeddings
- [ ] 12.5 Implement OpenSearch indexing: store chunks + multilingual embeddings with Document-UUID, version, metadata, and detected language
- [ ] 12.6 Create Celery task for async document indexing with retry on model unavailability (exponential backoff); task calls Model_Manager to load required models on-demand
- [ ] 12.7 Implement hybrid search: combine BM25 lexical + kNN semantic search in OpenSearch using multilingual embeddings for cross-language query support
- [ ] 12.8 Implement ABAC filtering on search results: exclude documents user lacks permission for
- [ ] 12.9 Implement CSV record exclusion: filter out `is_csv_validation_record = True` from all standard searches
- [ ] 12.10 Create FastAPI router `/api/search` with POST (hybrid search) endpoint returning ranked results with Document-UUID, title, version, excerpt, relevance score
- [ ] 12.11 Write unit tests for text extraction (digital and scanned), chunking, multilingual embedding generation, and search result filtering

## Task 13: RAG Pipeline (Conversational Knowledge Queries)

- [ ] 13.1 Create `RAGPipeline` with LlamaIndex integration: retrieve top-k chunks from Knowledge_Service, pass as context to LLM_Engine
- [ ] 13.2 Implement source citation extraction: Document-UUID, title, version, page/section for each referenced source
- [ ] 13.3 Implement grounded response enforcement: return "no matching content found" when no relevant chunks are retrieved
- [ ] 13.4 Implement conversation context management: maintain chat history for follow-up question resolution
- [ ] 13.5 Implement ABAC enforcement on RAG: filter retrieved chunks by user document permissions
- [ ] 13.6 Create FastAPI router `/api/knowledge` with POST (query) and POST (conversation) endpoints
- [ ] 13.7 Write unit tests for citation extraction, grounding enforcement, and ABAC filtering

## Task 14: Document Generator (AI-Powered)

- [ ] 14.1 Create `DocumentGenerator` with source document retrieval via Knowledge_Service and DSPy pipeline execution
- [ ] 14.2 Implement style matching: analyze source document structure (headers, sections, formatting) and apply to generated content
- [ ] 14.3 Implement chat history incorporation: extract user-directed content from conversation history
- [ ] 14.4 Implement Draft creation: store generated document in Document_Service with source metadata and agent linkage
- [ ] 14.5 Implement generation provenance audit trail: record source Document-UUIDs, Agent_Definition ID, and timestamp
- [ ] 14.6 Create FastAPI endpoint `POST /api/documents/generate` with agent selection and generation parameters
- [ ] 14.7 Write unit tests for document generation flow, provenance recording, and Draft creation

## Task 15: Agent Registry (YAML-Based)

- [ ] 15.1 Create JSON Schema for Agent_Definition YAML v1 (`agents/schema/agent-definition-v1.json`) with required fields: name, description, schema_version, system_prompt, dspy_modules, knowledge_scopes
- [ ] 15.2 Create `AgentRegistry` with YAML loading, validation against JSON Schema, and descriptive error reporting for invalid files
- [ ] 15.3 Implement agent import/export: export as YAML bytes, import with validation
- [ ] 15.4 Implement schema version checking: reject files with unsupported schema versions with descriptive error
- [ ] 15.5 Create example Agent_Definition YAML files: SOP drafting agent, deviation report agent, protocol summary agent
- [ ] 15.6 Implement DSPy pipeline configuration from Agent_Definition: system prompt, module chain, temperature, knowledge scopes
- [ ] 15.7 Implement agent selection audit trail recording: user_id, agent_id, timestamp
- [ ] 15.8 Create FastAPI router `/api/agents` with GET (list), POST (import), GET (export), POST (select) endpoints
- [ ] 15.9 Write property-based tests: YAML validation rejects all invalid definitions and accepts all valid ones
- [ ] 15.10 Write property-based tests: agent YAML portability round-trip — export then import produces equivalent definition

## Task 16: Training Content Generator (LLM-Powered)

- [ ] 16.1 Create `TrainingContentGenerator` with DSPy pipeline for training summary generation (diff between SOP versions)
- [ ] 16.2 Implement comprehension quiz generation: questions, correct answers, and SOP section references
- [ ] 16.3 Implement key procedural steps and safety points extraction
- [ ] 16.4 Create Celery task for async training content generation triggered on SOP InTraining status
- [ ] 16.5 Implement coordinator review gate: training content requires approval before presentation to trainees
- [ ] 16.6 Implement audit trail recording for training content generation events
- [ ] 16.7 Create FastAPI endpoints for training content review and approval
- [ ] 16.8 Write unit tests for training content generation pipeline and review gate

## Task 17: CSV Runner (URS Traceability + Validation)

- [ ] 17.1 Create URS parser (`urs-parser.ts`): read Requirements/URS.md and extract all REQ-XX-NN identifiers
- [ ] 17.2 Create traceability matrix builder: map REQ-IDs to Playwright test case IDs, flag untested requirements
- [ ] 17.3 Create Playwright test files tagged by URS REQ-ID (one file per requirement: req-dm-01.spec.ts, req-pdf-01.spec.ts, etc.)
- [ ] 17.4 Implement CSV Test User authentication and `is_csv_validation_record` auto-tagging middleware
- [ ] 17.5 Implement CSV record exclusion from standard user searches
- [ ] 17.6 Create validation certificate PDF generator: test results, timestamps, module versions, traceability matrix, URS version hash (SHA-256)
- [ ] 17.7 Implement certificate signing via Signature_Service and storage in Document_Service as "Validation Report"
- [ ] 17.8 Implement failure report generation on non-100% pass rate with failed test REQ-IDs
- [ ] 17.9 Write unit tests for URS parser and traceability matrix builder

## Task 18: Model Manager, OCR Engine, and Data Sovereignty

- [ ] 18.1 Create `ModelManager` service with `ModelRole` enum (CHAT, EMBEDDING, OCR) and async lock for serialized model swaps
- [ ] 18.2 Implement `ensure_model(role)`: unload current model if different, load requested model via vLLM API, wait for readiness health check, return vLLM API URL
- [ ] 18.3 Implement `get_status()` health endpoint: return currently loaded model role, model name, GPU memory usage, and readiness status
- [ ] 18.4 Implement `unload_current()` for explicit GPU memory release
- [ ] 18.5 Implement model configuration via Pydantic Settings from `.env`: MODEL_CHAT_NAME/PATH/MAX_GPU_MEMORY_GB, MODEL_EMBEDDING_NAME/PATH/DIMENSION, MODEL_OCR_NAME/PATH, GPU_DEVICE_ID, MODEL_MANAGER_MODE (gpu/cpu/mock)
- [ ] 18.6 Create `OCREngine` service: detect scanned PDFs (no extractable text), convert PDF pages to images via PyMuPDF `get_pixmap()`, send to vision model via Model_Manager, concatenate extracted text
- [ ] 18.7 Integrate Model_Manager into all AI consumers: RAG_Pipeline, Document_Generator, Document_Reviewer, Training_Content_Generator, and Knowledge_Service call `ensure_model()` before inference
- [ ] 18.8 Configure vLLM Docker container with NVIDIA Blackwell GPU passthrough and CPU fallback mode
- [ ] 18.9 Configure Docker Compose network with no outbound internet access for AI containers
- [ ] 18.10 Create model weight volume mount configuration (`/models/`) for air-gapped deployment with pre-downloaded weights
- [ ] 18.11 Implement CPU-mock mode for Model_Manager: return mock embeddings (random vectors of correct dimension) and mock LLM responses for development/testing
- [ ] 18.12 Create FastAPI endpoint `GET /api/models/status` returning current model, GPU memory, readiness
- [ ] 18.13 Document air-gapped deployment procedure in README including model download instructions
- [ ] 18.14 Write unit tests: model swap serialization (concurrent requests wait for lock), error handling on failed model load, mock mode returns correct-dimension embeddings
- [ ] 18.15 Write unit tests: OCR_Engine correctly detects scanned vs. digital PDFs, extracts text from scanned pages

## Task 19: Frontend Core Shell

- [ ] 19.1 Create application shell with React Router, navigation, and layout components
- [ ] 19.2 Create Zustand stores for authentication, documents, templates, and search state
- [ ] 19.3 Create document management pages: file browser, upload, version history, tag management
- [ ] 19.4 Create virtual folder sidebar: display system default and user-created virtual folders in navigation, open virtual folder to show dynamically filtered document list, create/edit/delete virtual folders
- [ ] 19.4 Create template visual form builder with drag-and-drop (react-hook-form + @hello-pangea/dnd)
- [ ] 19.5 Create workflow BPMN editor interface for admin workflow definition
- [ ] 19.6 Create training dashboard: task list, completion tracking, training content viewer
- [ ] 19.7 Create search interface: hybrid search with results display, relevance scores
- [ ] 19.8 Create RAG chat interface: conversational queries with source citations
- [ ] 19.9 Create agent selection UI: list agents, select for RAG/generation, import/export
- [ ] 19.10 Create validation dashboard: trigger CSV run, view results, download certificates
- [ ] 19.11 Create re-authentication dialog for electronic signature flows
- [ ] 19.12 Create document review UI: trigger AI review, display structured review report with per-chapter results, findings by severity, and recommendations
- [ ] 19.13 Create admin dashboard with user management, role assignment, and system configuration

## Task 21: Document Reviewer (AI-Powered Review)

- [ ] 21.1 Create `DocumentReviewer` service with review agent resolution: match document tag to `Review_Agent_Definition.target_document_tag`, allow manual agent override, return HTTP 400 if no matching review agent found
- [ ] 21.2 Implement structure check DSPy module: parse document headings/sections, compare against `required_chapters` list from Review_Agent_Definition, report missing/incomplete/out-of-order required sections
- [ ] 21.3 Implement content review DSPy module: evaluate each section against `compliance_checklist` items, retrieve similar approved documents via Knowledge_Service for comparison, classify findings by `severity_rules` (Critical, Major, Minor, Informational)
- [ ] 21.4 Implement `ReviewReport` and `ReviewFinding` Pydantic models: per-chapter pass/fail, findings with severity/section/description/recommendation, overall status (Pass, Pass with Findings, Fail)
- [ ] 21.5 Implement review report persistence: store review report linked to Document-UUID, document version, review agent ID, and reviewer user ID; record review event in audit trail
- [ ] 21.6 Create FastAPI endpoint `POST /api/documents/{uuid}/review` accepting optional `review_agent_id` parameter, returning structured ReviewReport
- [ ] 21.7 Extend Agent_Registry to support `agent_type: "review"` with additional schema fields: `target_document_tag`, `required_chapters` (ordered list with required/optional flag), `compliance_checklist`, `severity_rules`
- [ ] 21.8 Update JSON Schema (`agent-definition-v1.json`) to include review agent fields as conditional requirements when `agent_type == "review"`
- [ ] 21.9 Create example Review_Agent_Definition YAML files: SOP review agent (required chapters: Purpose, Scope, Responsibilities, Procedure, Safety, References, Revision History), deviation report review agent, validation protocol review agent
- [ ] 21.10 Implement review agent import/export via Agent_Registry (same portability as generation agents)
- [ ] 21.11 Write property-based tests: for documents with random subsets of required chapters removed, all omissions are detected by the structure check
- [ ] 21.12 Write property-based tests: review agent tag matching resolves correct agent for matching tags, returns error for unmatched tags
- [ ] 21.13 Write property-based tests: review agent YAML portability round-trip — export then import produces equivalent definition including required_chapters, compliance_checklist, and severity_rules
- [ ] 21.14 Write unit tests: review report structure validation, finding severity classification, audit trail recording

## Task 22: Integration Testing and End-to-End Verification

- [ ] 22.1 Create pytest fixtures for database setup, MinIO mock, and test user creation
- [ ] 22.2 Write integration tests for complete document lifecycle: create → version → search → retrieve
- [ ] 22.3 Write integration tests for complete PDF workflow: template create → PDF generate → fill → upload → extract → verify data
- [ ] 22.4 Write integration tests for complete workflow lifecycle: Draft → Review → Approved → InTraining → Active
- [ ] 22.5 Write integration tests for training gate: untrained user blocked, trained user permitted
- [ ] 22.6 Write integration tests for audit trail: verify version entries for all CRUD operations
- [ ] 22.7 Write integration tests for CSV isolation: validation records excluded from standard searches
- [ ] 22.8 Write integration tests for AI document review: submit document → receive structured review report with chapter results and findings
- [ ] 22.9 Run full Playwright CSV test suite and verify traceability matrix generation
