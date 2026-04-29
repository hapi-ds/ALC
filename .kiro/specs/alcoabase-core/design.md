# Design Document: AlcoaBase Core

## Overview

AlcoaBase is a 100% local, open-source Document & Knowledge Management System for GxP-regulated environments. This design covers the backend architecture (Python/FastAPI), frontend structure (React/TypeScript), data layer (PostgreSQL, MinIO, OpenSearch), AI pipeline (vLLM, LlamaIndex, DSPy), and the validation framework (Playwright CSV Runner). All components run within a Docker Compose deployment with no external network dependencies.

## Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                           │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │   Frontend    │    │            Backend (FastAPI)          │   │
│  │  React/Vite   │───▶│                                      │   │
│  │  TypeScript   │    │  ┌────────────┐  ┌───────────────┐   │   │
│  │  Tailwind     │    │  │ Document   │  │ Template      │   │   │
│  │  shadcn/ui    │    │  │ Service    │  │ Service       │   │   │
│  │  Zustand      │    │  ├────────────┤  ├───────────────┤   │   │
│  └──────────────┘    │  │ Workflow   │  │ Signature     │   │   │
│                       │  │ Engine     │  │ Service       │   │   │
│                       │  ├────────────┤  ├───────────────┤   │   │
│                       │  │ Training   │  │ Audit         │   │   │
│                       │  │ Service    │  │ Service       │   │   │
│                       │  ├────────────┤  ├───────────────┤   │   │
│                       │  │ Knowledge  │  │ Agent         │   │   │
│                       │  │ Service    │  │ Registry      │   │   │
│                       │  ├────────────┤  ├───────────────┤   │   │
│                       │  │ PDF Gen    │  │ PDF Extractor │   │   │
│                       │  ├────────────┤  ├───────────────┤   │   │
│                       │  │ Document   │  │ Training      │   │   │
│                       │  │ Generator  │  │ Content Gen   │   │   │
│                       │  └────────────┘  └───────────────┘   │   │
│                       └──────────────────────────────────────┘   │
│                              │          │          │              │
│                    ┌─────────┘    ┌─────┘    ┌─────┘             │
│                    ▼              ▼          ▼                    │
│  ┌──────────────┐  ┌──────────┐  ┌────────────┐  ┌───────────┐  │
│  │  PostgreSQL   │  │  MinIO   │  │ OpenSearch  │  │   Redis   │  │
│  │  (SQLAlchemy  │  │  (S3     │  │ (Vectors + │  │  (Celery  │  │
│  │  Continuum)   │  │  Store)  │  │  Search)   │  │  Broker)  │  │
│  └──────────────┘  └──────────┘  └────────────┘  └───────────┘  │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  vLLM        │  │  Celery      │  │  CSV Runner          │   │
│  │  (Local LLM) │  │  Worker      │  │  (Playwright)        │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Project Directory Structure

```
alcoabase/
├── docker-compose.yml
├── .env.example
├── Requirements/
│   └── URS.md
├── src/
│   ├── backend/
│   │   ├── pyproject.toml
│   │   ├── src/
│   │   │   └── alcoabase/
│   │   │       ├── __init__.py
│   │   │       ├── main.py                    # FastAPI app entry point
│   │   │       ├── config.py                  # Pydantic Settings
│   │   │       ├── database.py                # SQLAlchemy engine + session
│   │   │       ├── models/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── document.py            # Document, DocumentVersion
│   │   │       │   ├── template.py            # Template, TemplateField
│   │   │       │   ├── report.py              # Report, ReportFieldValue
│   │   │       │   ├── workflow.py            # WorkflowDefinition, DocumentState
│   │   │       │   ├── signature.py           # SignatureRecord
│   │   │       │   ├── training.py            # TrainingTask, TrainingRecord
│   │   │       │   ├── user.py                # User, Role, Permission
│   │   │       │   ├── agent.py               # AgentDefinition
│   │   │       │   └── audit.py               # Audit mixin + Continuum config
│   │   │       ├── schemas/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── document.py            # Pydantic request/response schemas
│   │   │       │   ├── template.py
│   │   │       │   ├── report.py
│   │   │       │   ├── workflow.py
│   │   │       │   ├── signature.py
│   │   │       │   ├── training.py
│   │   │       │   ├── search.py
│   │   │       │   └── agent.py
│   │   │       ├── api/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── router.py              # Main API router
│   │   │       │   ├── documents.py           # /api/documents
│   │   │       │   ├── templates.py           # /api/templates
│   │   │       │   ├── reports.py             # /api/reports
│   │   │       │   ├── workflows.py           # /api/workflows
│   │   │       │   ├── signatures.py          # /api/signatures
│   │   │       │   ├── training.py            # /api/training
│   │   │       │   ├── search.py              # /api/search
│   │   │       │   ├── knowledge.py           # /api/knowledge (RAG chat)
│   │   │       │   ├── agents.py              # /api/agents
│   │   │       │   └── csv_validation.py      # /api/validation
│   │   │       ├── services/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── document_service.py
│   │   │       │   ├── template_service.py
│   │   │       │   ├── pdf_generator.py       # ReportLab PDF generation
│   │   │       │   ├── pdf_extractor.py       # PyMuPDF data extraction
│   │   │       │   ├── workflow_engine.py      # SpiffWorkflow integration
│   │   │       │   ├── signature_service.py   # PAdES signing
│   │   │       │   ├── training_service.py
│   │   │       │   ├── audit_service.py
│   │   │       │   ├── knowledge_service.py   # Indexing + search
│   │   │       │   ├── rag_pipeline.py        # LlamaIndex RAG
│   │   │       │   ├── document_generator.py  # AI doc generation
│   │   │       │   ├── training_content_generator.py
│   │   │       │   ├── agent_registry.py      # YAML agent loading
│   │   │       │   ├── storage_service.py     # MinIO abstraction
│   │   │       │   └── uuid_service.py        # Document-UUID + Field-UUID gen
│   │   │       ├── tasks/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── celery_app.py          # Celery configuration
│   │   │       │   ├── indexing_tasks.py       # Document embedding tasks
│   │   │       │   └── training_tasks.py       # Training generation tasks
│   │   │       └── middleware/
│   │   │           ├── __init__.py
│   │   │           ├── audit_middleware.py     # Request-level audit context
│   │   │           └── csv_tagging.py         # CSV validation record tagging
│   │   └── tests/
│   │       ├── conftest.py
│   │       ├── test_document_service.py
│   │       ├── test_template_service.py
│   │       ├── test_pdf_roundtrip.py          # Property-based round-trip tests
│   │       ├── test_workflow_engine.py
│   │       ├── test_signature_service.py
│   │       ├── test_training_service.py
│   │       ├── test_audit_service.py
│   │       ├── test_knowledge_service.py
│   │       ├── test_agent_registry.py
│   │       └── test_uuid_service.py
│   ├── frontend/
│   │   ├── package.json
│   │   ├── vite.config.ts
│   │   ├── tsconfig.json
│   │   ├── tailwind.config.ts
│   │   └── src/
│   │       ├── main.tsx
│   │       ├── App.tsx
│   │       ├── stores/                        # Zustand stores
│   │       ├── components/
│   │       │   ├── ui/                        # shadcn/ui components
│   │       │   ├── documents/
│   │       │   ├── templates/                 # Visual form builder
│   │       │   ├── workflows/                 # BPMN editor
│   │       │   ├── training/
│   │       │   ├── search/
│   │       │   ├── knowledge/                 # RAG chat interface
│   │       │   └── validation/
│   │       ├── pages/
│   │       ├── hooks/
│   │       ├── lib/
│   │       └── types/
│   └── csv-runner/
│       ├── package.json
│       ├── playwright.config.ts
│       ├── tests/
│       │   ├── req-dm-01.spec.ts              # Tagged by URS REQ-ID
│       │   ├── req-pdf-01.spec.ts
│       │   ├── req-pdf-02.spec.ts
│       │   ├── req-pdf-03.spec.ts
│       │   ├── req-wf-01.spec.ts
│       │   ├── req-sig-01.spec.ts
│       │   ├── req-trn-01.spec.ts
│       │   ├── req-trn-02.spec.ts
│       │   ├── req-aud-01.spec.ts
│       │   ├── req-csv-01.spec.ts
│       │   └── req-csv-02.spec.ts
│       ├── utils/
│       │   ├── urs-parser.ts                  # Parse URS.md for REQ-IDs
│       │   ├── traceability-matrix.ts         # Build REQ-ID → test mapping
│       │   └── certificate-generator.ts       # PDF certificate generation
│       └── Dockerfile
├── agents/
│   ├── schema/
│   │   └── agent-definition-v1.json           # JSON Schema for agent YAML
│   └── examples/
│       ├── sop-drafting-agent.yaml
│       ├── deviation-report-agent.yaml
│       └── protocol-summary-agent.yaml
└── docs/
```

## Component Designs

### 1. Database Layer (PostgreSQL + SQLAlchemy-Continuum)

**Technology:** SQLAlchemy 2.0 with async sessions, SQLAlchemy-Continuum for automatic audit versioning, Alembic for migrations.

**Core Models:**

```python
# src/backend/src/alcoabase/models/document.py
class Document(Base, AuditMixin):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_uuid: Mapped[str] = mapped_column(String(12), unique=True, index=True)  # YYYY-NNNNN
    title: Mapped[str] = mapped_column(String(500))
    folder_path: Mapped[str] = mapped_column(String(1000))
    document_type: Mapped[str] = mapped_column(String(100))  # SOP, Report, Template, ValidationReport
    current_status: Mapped[str] = mapped_column(String(50))  # Draft, Review, Approved, InTraining, Active
    is_csv_validation_record: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tags: Mapped[list["DocumentTag"]] = relationship(back_populates="document")
    versions: Mapped[list["DocumentVersion"]] = relationship(back_populates="document")

class DocumentVersion(Base, AuditMixin):
    __tablename__ = "document_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    major_version: Mapped[int] = mapped_column(default=1)
    minor_version: Mapped[int] = mapped_column(default=0)
    storage_key: Mapped[str] = mapped_column(String(500))  # MinIO object key
    file_hash: Mapped[str] = mapped_column(String(128))     # SHA-512
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    change_reason: Mapped[str] = mapped_column(Text)
```

```python
# src/backend/src/alcoabase/models/template.py
class Template(Base, AuditMixin):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_uuid: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(500))
    json_schema: Mapped[dict] = mapped_column(JSON)  # Immutable after ReadOnly
    status: Mapped[str] = mapped_column(String(20))   # Draft, ReadOnly
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    fields: Mapped[list["TemplateField"]] = relationship(back_populates="template")

class TemplateField(Base):
    __tablename__ = "template_fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id"))
    field_uuid: Mapped[str] = mapped_column(String(40), unique=True, index=True)  # FLD-XXXXXX
    field_type: Mapped[str] = mapped_column(String(20))  # Text, Float, Integer, Date, Boolean
    field_label: Mapped[str] = mapped_column(String(200))
    field_order: Mapped[int] = mapped_column()
```

```python
# src/backend/src/alcoabase/models/audit.py
class AuditMixin:
    """Mixin that enables SQLAlchemy-Continuum versioning on any model."""
    __versioned__ = {
        "exclude": ["is_csv_validation_record"]
    }
    # Continuum automatically creates {table}_version tables
    # with transaction_id, operation_type, and all column snapshots
```

**Key Design Decisions:**
- All GxP-relevant models inherit `AuditMixin` to get automatic Continuum versioning.
- `is_csv_validation_record` is excluded from versioning to avoid polluting audit trails.
- Document-UUID format `YYYY-NNNNN` uses year prefix + zero-padded sequence per year.
- Field-UUID format `FLD-{uuid4_hex[:8]}` provides compact, unique field identifiers.
- No DELETE endpoints are registered for any `*_version` tables. The API router explicitly omits them.

### 2. UUID Generation Service

**Technology:** Python `uuid` module + PostgreSQL sequence for Document-UUID.

```python
# src/backend/src/alcoabase/services/uuid_service.py
class UUIDService:
    async def generate_document_uuid(self, session: AsyncSession) -> str:
        """Generate YYYY-NNNNN format Document-UUID using DB sequence."""
        year = datetime.now(UTC).year
        next_val = await session.execute(text(f"SELECT nextval('doc_uuid_seq_{year}')"))
        seq = next_val.scalar_one()
        return f"{year}-{seq:05d}"

    def generate_field_uuid(self) -> str:
        """Generate FLD-XXXXXXXX format Field-UUID."""
        return f"FLD-{uuid4().hex[:8].upper()}"
```

**Invariants:**
- Document-UUIDs are unique across the system (enforced by DB unique constraint + sequence).
- Field-UUIDs are unique within a template (validated before save).

### 3. Document Service

**Technology:** FastAPI router + MinIO (boto3/aioboto3) for file storage.

**API Endpoints:**
- `POST /api/documents` — Upload new document, generate UUID, prompt for tags
- `POST /api/documents/{uuid}/versions` — Upload new version
- `GET /api/documents/{uuid}` — Get document metadata
- `GET /api/documents/{uuid}/versions/{version}` — Get specific version
- `GET /api/documents?tag=X&folder=Y` — Search documents

**Flow:**
1. User uploads file → Document_Service generates Document-UUID
2. File stored in MinIO at `documents/{uuid}/{major}.{minor}/{filename}`
3. Metadata persisted to PostgreSQL in a single transaction
4. If MinIO upload fails, transaction is rolled back (no partial records)
5. Celery task dispatched for async Knowledge_Service indexing

### 4. Template Service + PDF Generator + PDF Extractor

**Technology:** ReportLab (PDF generation), PyMuPDF/fitz (PDF extraction).

**Template Save Flow:**
1. Admin submits template JSON from visual editor
2. Template_Service generates Document-UUID for template
3. For each field in JSON schema, Template_Service generates Field-UUID
4. Validates all Field-UUIDs are unique within template
5. Persists template with status="ReadOnly" (immutable from this point)

**PDF Generation (ReportLab):**
```python
# src/backend/src/alcoabase/services/pdf_generator.py
class PDFGenerator:
    def generate_offline_pdf(self, template: Template) -> bytes:
        """Generate fillable AcroForm PDF from template JSON schema."""
        # 1. Create PDF canvas with ReportLab
        # 2. For each TemplateField:
        #    - Create AcroForm text field with field_name = field_uuid
        #    - Set field type constraints (text, numeric)
        # 3. Embed Document-UUID as hidden field "__DOC_UUID__"
        # 4. Return PDF bytes
```

**PDF Extraction (PyMuPDF):**
```python
# src/backend/src/alcoabase/services/pdf_extractor.py
class PDFExtractor:
    def extract_data(self, pdf_bytes: bytes) -> ExtractedReport:
        """Extract field values from completed offline PDF."""
        # 1. Open PDF with fitz
        # 2. Read hidden field "__DOC_UUID__" → match to template
        # 3. For each field in template:
        #    - Read AcroForm field by Field-UUID name
        #    - Validate value against expected type
        # 4. Return ExtractedReport with {field_uuid: value} mapping
```

**Round-Trip Guarantee:**
The PDF Generator and Extractor form a serializer/parser pair. The round-trip property is:
`extract(generate(template, data)) == data` for all valid templates and data.

### 5. Workflow Engine (SpiffWorkflow)

**Technology:** SpiffWorkflow for BPMN execution, stored as BPMN XML in PostgreSQL.

**Tag-Based Workflow Binding:**
Each BPMN workflow definition is bound to a **document tag** (e.g., `SOP`, `Report`, `Protocol`). When a document is created or tagged, the Workflow_Engine resolves the applicable workflow by matching the document's tags against registered workflow definitions. This means different document types follow different lifecycle paths — an SOP has a different workflow than a lab report or a deviation record.

**Workflow Definition Model:**
```python
# src/backend/src/alcoabase/models/workflow.py
class WorkflowDefinition(Base, AuditMixin):
    __tablename__ = "workflow_definitions"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    document_tag: Mapped[str] = mapped_column(String(100), unique=True, index=True)  # e.g. "SOP", "Report"
    bpmn_xml: Mapped[str] = mapped_column(Text)  # BPMN 2.0 XML definition
    signature_required_transitions: Mapped[list[str]] = mapped_column(JSON, default=list)
    # e.g. ["Review→Approved", "Draft→RecordsFilled"] — transitions that require PAdES signature
    training_trigger_transitions: Mapped[list[str]] = mapped_column(JSON, default=list)
    # e.g. ["Approved→InTraining"] — transitions that trigger training assignment
    is_active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
```

**Example: SOP Workflow (tag = "SOP"):**
```
Draft → Review → Approved → InTraining → Active
         ↑                                  │
         └──────── (new minor version) ─────┘
```
- Signature required on: `Review → Approved`
- Training triggered on: `Approved → InTraining` (automatic for major versions)

**Example: Lab Report Workflow (tag = "Report"):**
```
Draft → RecordsFilled → Reviewed → Approved
```
- Signature required on: `Draft → RecordsFilled`, `RecordsFilled → Reviewed`, `Reviewed → Approved`

**Workflow Resolution:**
```python
# src/backend/src/alcoabase/services/workflow_engine.py
class WorkflowEngine:
    async def _resolve_workflow(
        self, document: Document
    ) -> WorkflowDefinition:
        """Resolve the BPMN workflow for a document based on its tags."""
        # Match document tags against workflow_definitions.document_tag
        # If no match → raise HTTP 400 ("No workflow defined for document tag")
        # If multiple matches → use most specific tag (exact match preferred)

    async def request_transition(
        self, document_uuid: str, target_state: str, user_id: int
    ) -> TransitionResult:
        """Validate and execute state transition via SpiffWorkflow."""
        # 1. Load document and resolve BPMN definition via document tag
        # 2. Load current document state
        # 3. Ask SpiffWorkflow if transition is valid
        # 4. If invalid → raise HTTP 400, state unchanged
        # 5. If valid:
        #    a. Check if this transition is in signature_required_transitions
        #       → If yes, delegate to Signature_Service (re-auth + PAdES sign)
        #    b. Update state, record in audit trail
        #    c. Check if this transition is in training_trigger_transitions
        #       → If yes, trigger Training_Service for role-based task generation
```

**BPMN Validation:**
When an admin saves a new BPMN workflow, the engine validates:
- No unreachable states (all states reachable from initial state)
- No missing terminal states (at least one end event)
- All transitions reference valid states
- The `document_tag` is unique (one active workflow per tag)
- All entries in `signature_required_transitions` reference valid transitions in the BPMN definition

### 6. Signature Service (PAdES)

**Technology:** `endesive` or `pyHanko` for PAdES signing, x.509 certificates stored per-user.

**Configurable Signature Requirements:**
The Signature_Service does not hardcode which transitions require signatures. Instead, the `WorkflowDefinition.signature_required_transitions` list (see Section 5) defines which state transitions demand re-authentication and PAdES signing. This allows admins to configure signature requirements per document type. For example:
- **SOP workflow**: Signature required on `Review → Approved`
- **Lab Report workflow**: Signature required on `Draft → RecordsFilled` (analyst signs that records are complete), `RecordsFilled → Reviewed` (reviewer signs off), and `Reviewed → Approved` (QA final approval)

Each signature captures a different **reason** matching the transition context (e.g., "Records completed by analyst", "Reviewed by supervisor", "Approved by QA").

**Signing Flow:**
1. Workflow_Engine detects the requested transition is in `signature_required_transitions`
2. Frontend shows re-authentication dialog with the transition-specific reason pre-filled
3. User provides password/PIN → backend verifies credentials
4. If invalid → reject, document state unchanged
5. If valid → load user's x.509 certificate
6. Sign PDF with PAdES standard using `pyHanko`
7. Embed visual stamp: Name, Date, Time, Reason (derived from the transition, e.g., "Records filled", "Reviewed", "Approved by QA")
8. Store signed PDF in MinIO, record signature event in audit trail
9. Any subsequent byte modification invalidates the embedded signature
10. Multiple signatures accumulate on the same PDF (PAdES supports incremental signatures)

### 7. Training Service (ABAC)

**Technology:** Custom ABAC policy engine, Celery for async task generation.

**Training Assignment Flow:**
1. SOP reaches "Approved" status (major version) → Workflow_Engine triggers Training_Service
2. Training_Service transitions SOP to "InTraining"
3. Query all users with roles assigned to this SOP
4. Generate training task per user: "Read and understand [SOP-Name] v[Version]"
5. Dispatch Celery task for LLM-powered training content generation
6. When all users complete training → auto-transition SOP to "Active"

**Execution Gate:**
```python
# src/backend/src/alcoabase/services/training_service.py
class TrainingService:
    async def check_training_gate(
        self, user_id: int, sop_uuid: str, sop_version: str
    ) -> None:
        """Raise HTTP 403 if user lacks valid training for SOP version."""
        record = await self._get_training_record(user_id, sop_uuid, sop_version)
        if not record or not record.is_completed:
            raise HTTPException(
                status_code=403,
                detail=f"Action denied: Valid training record for {sop_name} Version {sop_version} is missing."
            )
```

### 8. Audit Service (SQLAlchemy-Continuum)

**Technology:** SQLAlchemy-Continuum auto-generates `*_version` tables.

**Design:**
- Every model with `AuditMixin` gets automatic versioning
- Continuum records: old values, new values, transaction_id, operation_type
- Custom middleware injects `user_id`, `reason_for_change`, and server-side UTC timestamp into the Continuum transaction context
- No DELETE endpoints registered for `*_version` tables
- API middleware rejects any DELETE request targeting audit tables with HTTP 403

**Audit Middleware:**
```python
# src/backend/src/alcoabase/middleware/audit_middleware.py
class AuditMiddleware:
    """Injects audit context (user_id, reason, timestamp) into each request."""
    async def __call__(self, request, call_next):
        # Extract user_id from JWT token
        # Extract reason_for_change from request header X-Change-Reason
        # Set server-side UTC timestamp
        # Store in Continuum transaction context
```

### 9. Knowledge Service (OpenSearch + LlamaIndex)

**Technology:** OpenSearch for vector storage + hybrid search, LlamaIndex for RAG orchestration, vLLM for local inference.

**Document Indexing Flow:**
1. Document uploaded → Celery task dispatched
2. Text extracted from PDF/DOCX/TXT using appropriate parser
3. Text chunked into overlapping segments (512 tokens, 50 token overlap)
4. Embeddings generated via local LLM_Engine
5. Chunks + embeddings stored in OpenSearch with metadata (Document-UUID, version, tags)
6. If LLM_Engine unavailable → task queued for retry (exponential backoff)

**Hybrid Search:**
```python
# src/backend/src/alcoabase/services/knowledge_service.py
class KnowledgeService:
    async def hybrid_search(
        self, query: str, user_id: int, limit: int = 20
    ) -> list[SearchResult]:
        """Combine lexical BM25 + semantic kNN search in OpenSearch."""
        # 1. Generate query embedding via LLM_Engine
        # 2. Execute OpenSearch hybrid query (BM25 + kNN)
        # 3. Filter by ABAC permissions for user
        # 4. Exclude is_csv_validation_record = True
        # 5. Return ranked results with excerpts
```

**RAG Pipeline:**
```python
# src/backend/src/alcoabase/services/rag_pipeline.py
class RAGPipeline:
    def __init__(self, knowledge_service, llm_engine, agent_definition):
        self.retriever = knowledge_service
        self.llm = llm_engine
        self.agent_config = agent_definition

    async def query(self, question: str, conversation_history: list) -> RAGResponse:
        """Retrieve relevant chunks and generate grounded answer."""
        # 1. Retrieve top-k chunks from Knowledge_Service
        # 2. Build prompt with agent system prompt + retrieved context + conversation history
        # 3. Generate response via local LLM_Engine
        # 4. Extract source citations (Document-UUID, title, version, page)
        # 5. If no relevant chunks found → return "no matching content" message
```

### 10. Document Generator (AI-Powered)

**Technology:** DSPy for pipeline composition, LlamaIndex for retrieval.

**Generation Flow:**
1. User selects agent + provides generation instructions (or uses chat history)
2. Document_Generator retrieves relevant source documents via Knowledge_Service
3. DSPy pipeline configured per Agent_Definition (system prompt, module chain)
4. LLM generates document matching source document structure/style
5. Generated document stored as Draft in Document_Service
6. Provenance recorded in audit trail (source UUIDs, agent ID, timestamp)

### 11. Agent Registry (YAML-Based)

**Technology:** Pydantic for YAML validation, JSON Schema for agent definition format.

**Agent Definition YAML Schema (v1):**
```yaml
# agents/examples/sop-drafting-agent.yaml
schema_version: "1.0"
name: "SOP Drafting Agent"
description: "Generates Standard Operating Procedure drafts based on existing SOPs"
system_prompt: |
  You are an expert technical writer for GxP-regulated environments.
  Generate SOPs that follow the organization's established format and style.
dspy_modules:
  - name: "retrieve"
    type: "ColBERTv2Retriever"
    params:
      top_k: 10
  - name: "generate"
    type: "ChainOfThought"
    params:
      temperature: 0.3
      max_tokens: 4096
knowledge_scopes:
  tags: ["SOP", "Procedure"]
example_usage: "Use this agent to draft new SOPs based on existing procedures."
```

**Registry Logic:**
```python
# src/backend/src/alcoabase/services/agent_registry.py
class AgentRegistry:
    def load_agents(self, agents_dir: Path) -> list[AgentDefinition]:
        """Load and validate all YAML agent definitions from directory."""
        # 1. Scan directory for .yaml files
        # 2. Parse each file with PyYAML
        # 3. Validate against JSON Schema (agents/schema/agent-definition-v1.json)
        # 4. Reject invalid files with descriptive errors
        # 5. Return list of validated AgentDefinition objects

    def export_agent(self, agent_id: str) -> bytes:
        """Export agent definition as YAML bytes."""

    def import_agent(self, yaml_bytes: bytes) -> AgentDefinition:
        """Import and validate agent definition from YAML bytes."""
```

### 12. Training Content Generator (LLM-Powered)

**Technology:** DSPy for structured generation, local vLLM.

**Generation Pipeline:**
1. SOP enters "InTraining" → Celery task dispatched
2. Retrieve current and previous SOP versions
3. Generate training summary (diff highlights) via DSPy ChainOfThought
4. Generate comprehension quiz (questions + answers + section refs)
5. Extract key procedural steps and safety points
6. Store materials linked to SOP UUID + version
7. Materials require coordinator review/approval before presentation to trainees

### 13. CSV Runner (Playwright)

**Technology:** Playwright for E2E testing, custom URS parser, ReportLab for certificate PDF.

**URS Parser:**
```typescript
// src/csv-runner/utils/urs-parser.ts
export function parseURS(ursContent: string): URSRequirement[] {
  // Parse Requirements/URS.md
  // Extract all REQ-XX-NN identifiers
  // Return structured list of requirements with IDs and descriptions
}
```

**Test Tagging Convention:**
Each Playwright test file is named by REQ-ID and uses test metadata:
```typescript
// src/csv-runner/tests/req-pdf-01.spec.ts
test.describe("REQ-PDF-01: Generation of Template and Field UUIDs", () => {
  test("template save generates Document-UUID and Field-UUIDs", async ({ page }) => {
    // ...
  });
});
```

**Traceability Matrix:**
After test execution, the CSV Runner:
1. Parses URS.md for all REQ-IDs
2. Scans test results for REQ-ID tags
3. Builds matrix: REQ-ID → [test_case_id, pass/fail]
4. Flags any REQ-ID with no test cases as "Untested"

**Certificate Generation:**
On 100% pass rate:
1. Generate PDF with test results, timestamps, module versions
2. Include complete traceability matrix
3. Include URS document version hash (SHA-256 of URS.md)
4. Sign with system x.509 certificate via Signature_Service
5. Store in Document_Service as "Validation Report"

### 14. CSV Record Isolation

**Technology:** FastAPI middleware for automatic tagging.

```python
# src/backend/src/alcoabase/middleware/csv_tagging.py
class CSVTaggingMiddleware:
    """Auto-tags all records created by CSV Test User."""
    async def __call__(self, request, call_next):
        if is_csv_test_user(request):
            # Set context flag so all ORM creates set is_csv_validation_record=True
            set_csv_context(True)
        response = await call_next(request)
        return response
```

### 15. Data Sovereignty Enforcement

**Design Constraints:**
- vLLM container runs locally within Docker Compose (GPU passthrough or CPU mode)
- No outbound network rules in Docker network configuration
- OpenSearch runs locally, no cloud connectors
- Model weights pre-downloaded and mounted as Docker volume
- CPU-mock mode: replace vLLM with a lightweight local model or mock responses for dev/test

## Correctness Properties

### Property 1: Document-UUID Uniqueness (Req 1, AC 1-2)
- **Type:** Invariant
- **Property:** For all generated Document-UUIDs, no two documents share the same UUID. Each UUID matches the pattern `YYYY-NNNNN` where YYYY is a valid year and NNNNN is a zero-padded 5-digit number.
- **Test approach:** Property-based test generating many UUIDs and asserting uniqueness + format compliance.

### Property 2: Field-UUID Uniqueness Within Template (Req 3, AC 2-3)
- **Type:** Invariant
- **Property:** For all templates with N fields, exactly N unique Field-UUIDs are assigned. Each Field-UUID matches the pattern `FLD-[A-F0-9]{8}`.
- **Test approach:** Property-based test with randomly generated template schemas of varying field counts.

### Property 3: Template Immutability After ReadOnly (Req 3, AC 4-5)
- **Type:** Invariant
- **Property:** Once a template status is set to "ReadOnly", no subsequent modification request changes the JSON schema. All modification attempts return HTTP 400.
- **Test approach:** Property-based test: save template → set ReadOnly → attempt N random modifications → all rejected.

### Property 4: PDF Round-Trip Integrity (Req 6, AC 1-3)
- **Type:** Round-trip
- **Property:** For all valid template schemas and field values, `extract(generate(template, values)) == values`. The Document-UUID extracted equals the Document-UUID embedded. Each Field-UUID maps to exactly one AcroForm field and one extracted value.
- **Test approach:** Property-based test with Hypothesis generating random templates (varying field counts, types) and random valid field values. Generate PDF, extract data, assert equality.

### Property 5: BPMN State Transition Validity (Req 7, AC 1-2)
- **Type:** Invariant
- **Property:** For all documents and all possible state transition requests, only transitions defined in the BPMN workflow are accepted. Invalid transitions return HTTP 400 and leave the document state unchanged.
- **Test approach:** Property-based test with random state + random target state. Verify acceptance/rejection matches BPMN definition.

### Property 6: BPMN Workflow Definition Validity (Req 7, AC 5)
- **Type:** Invariant
- **Property:** For all BPMN workflow definitions, the validator detects unreachable states and missing terminal states.
- **Test approach:** Property-based test generating random graph structures and verifying detection of invalid topologies.

### Property 7: PAdES Signature Tamper Detection (Req 8, AC 5)
- **Type:** Invariant
- **Property:** For all signed PDFs, any byte modification to the PDF content causes the PAdES signature to be reported as invalid.
- **Test approach:** Property-based test: sign PDF → randomly modify N bytes → verify signature is invalid.

### Property 8: Training Gate Enforcement (Req 10, AC 1-2)
- **Type:** Invariant
- **Property:** For all (user, SOP, version) tuples, report creation is permitted if and only if the user holds a valid, completed training record for that exact SOP version. Untrained users receive HTTP 403.
- **Test approach:** Property-based test with random user/SOP/version/training-status combinations.

### Property 9: Training Record Invalidation on Major Version (Req 10, AC 4)
- **Type:** Metamorphic
- **Property:** When a new major SOP version is activated, all training records for previous major versions of that SOP are invalidated. Users who were trained on v1.0 cannot create reports for v2.0.
- **Test approach:** Property-based test: create training records for version N → activate version N+1 → verify all version N records are invalid.

### Property 10: Audit Trail Completeness (Req 12, AC 1-3)
- **Type:** Invariant
- **Property:** For all audited records, the version sequence is monotonically increasing with no gaps. Each modification produces exactly one version entry. Querying returns all entries in chronological order.
- **Test approach:** Property-based test: perform N random modifications to a record → verify version sequence is [1, 2, ..., N] with no gaps.

### Property 11: Audit Trail Immutability (Req 11, AC 4-5)
- **Type:** Error condition
- **Property:** No API endpoint accepts DELETE requests for audit version tables. All DELETE attempts return HTTP 403.
- **Test approach:** Property-based test: for all audit table endpoints, attempt DELETE with various payloads → all return 403.

### Property 12: Search Result ABAC Filtering (Req 14, AC 3-4)
- **Type:** Invariant
- **Property:** For all search queries by a user, results contain only documents the user has permission to access. No CSV validation records appear in standard user searches.
- **Test approach:** Property-based test with random user permissions and document sets.

### Property 13: RAG Source Citation Completeness (Req 15, AC 2)
- **Type:** Invariant
- **Property:** For all RAG responses that reference document content, every referenced passage includes a source citation with Document-UUID, title, version, and page/section number.
- **Test approach:** Property-based test with various queries, verifying citation structure.

### Property 14: Agent YAML Validation (Req 19, AC 3; Req 20, AC 1-2)
- **Type:** Error condition
- **Property:** For all invalid YAML agent definitions (missing required fields, unsupported schema version, malformed YAML), the Agent_Registry rejects the file with a descriptive error. For all valid definitions, the agent loads successfully.
- **Test approach:** Property-based test with Hypothesis generating random YAML structures (valid and invalid).

### Property 15: Agent YAML Portability Round-Trip (Req 20, AC 4)
- **Type:** Round-trip
- **Property:** For all valid Agent_Definition YAML files, exporting from one instance and importing into another instance (same or newer schema version) produces an equivalent agent definition.
- **Test approach:** Property-based test: generate random valid agent definitions → export → import → assert equivalence.

### Property 16: URS Requirement ID Extraction (Req 21, AC 1)
- **Type:** Invariant
- **Property:** For all valid URS documents containing REQ-XX-NN identifiers, the parser extracts every requirement ID without omission or duplication.
- **Test approach:** Property-based test with generated URS documents containing varying numbers of REQ-IDs.

### Property 17: Training Task Generation Completeness (Req 9, AC 2)
- **Type:** Invariant
- **Property:** When an SOP enters "InTraining", for all users holding a role assigned to that SOP, exactly one training task is generated per user. No user is missed, no user receives duplicate tasks.
- **Test approach:** Property-based test with random role-to-user assignments.

### Property 18: PDF Extraction Type Validation (Req 5, AC 3, 6)
- **Type:** Error condition
- **Property:** For all extracted field values that do not match the expected data type (e.g., non-numeric value in a Float field), the extractor rejects the upload with validation errors and persists no partial data.
- **Test approach:** Property-based test with Hypothesis generating invalid field values for each type.

## Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| Web Framework | FastAPI | Async, Pydantic integration, OpenAPI docs |
| ORM | SQLAlchemy 2.0 | Mature, async support, Continuum plugin |
| Audit Trail | SQLAlchemy-Continuum | Automatic versioning, no custom code |
| Workflow | SpiffWorkflow | Python-native BPMN engine |
| PDF Generation | ReportLab | AcroForm support, Python-native |
| PDF Extraction | PyMuPDF (fitz) | Fast, reliable AcroForm reading |
| PDF Signing | pyHanko | PAdES standard, x.509 support |
| Background Jobs | Celery + Redis | Proven async task queue |
| Object Storage | MinIO | S3-compatible, self-hosted |
| Vector Search | OpenSearch | Hybrid search (BM25 + kNN) |
| LLM Inference | vLLM | High-performance local inference |
| RAG Framework | LlamaIndex | Mature retrieval + generation pipeline |
| Agent Framework | DSPy | Composable LLM pipelines |
| Frontend | React + Vite + TypeScript | Fast dev, type safety |
| UI Components | shadcn/ui + Tailwind | Accessible, customizable |
| State Management | Zustand | Lightweight, simple API |
| E2E Testing | Playwright | Cross-browser, reliable |
| Package Management | uv | Fast, modern Python packaging |
| Containerization | Docker Compose v2 | Multi-service orchestration |
