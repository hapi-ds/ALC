# Implementation Plan: Multimodal Knowledge Base

## Overview

This plan implements two multimodal capabilities for the knowledge base: (1) Diagram & Flowchart Understanding during document indexing via vision model interpretation, and (2) Video-to-SOP Alignment with frame extraction, analysis, audio transcription, step comparison, and discrepancy reporting. Implementation follows a dependency-first order: database models → configuration → core services → API layer → frontend integration.

## Tasks

- [x] 1. Database models and configuration
  - [x] 1.1 Create database models for video alignment tables
    - Create `src/backend/src/alcoabase/models/video.py` with SQLAlchemy models: `VideoMetadata`, `VideoStepSequence`, `VideoSOPLink`, `DiscrepancyReport`, `ProcessingJob`
    - Define all columns, foreign keys, indexes, and constraints as specified in the design (unique constraint on video_sop_link, index on job_id, etc.)
    - Register models in `src/backend/src/alcoabase/models/__init__.py`
    - _Requirements: 4.3, 5.4, 6.6, 8.1, 9.5, 10.6_

  - [x] 1.2 Create Alembic migration for new tables
    - Generate migration with `uv run alembic revision --autogenerate -m "add_multimodal_knowledge_base_tables"`
    - Verify migration creates: `video_metadata`, `video_step_sequences`, `video_sop_links`, `discrepancy_reports`, `processing_jobs`
    - _Requirements: 4.3, 6.6, 8.1, 9.5, 10.6_

  - [x] 1.3 Add multimodal configuration settings
    - Extend `src/backend/src/alcoabase/config.py` Settings class with: `ENABLE_VISUAL_INDEXING`, `VISUAL_BOOST_FACTOR`, `MAX_VISUAL_PAGES_PER_DOCUMENT`, `VIDEO_MAX_FILE_SIZE_BYTES`, `VIDEO_MAX_FRAMES`, `FRAME_SIMILARITY_THRESHOLD`, `ALIGNMENT_MATCH_THRESHOLD`, `FFMPEG_PATH`, `FFPROBE_PATH`
    - Use Pydantic Field with validation constraints (ge, le) as specified in design
    - _Requirements: 3.5, 5.5, 12.5_

  - [x] 1.4 Create Pydantic request/response schemas for video alignment
    - Create `src/backend/src/alcoabase/schemas/video_alignment.py` with: `LinkSOPRequest`, `SOPLinkResponse`, `JobStatusResponse`, `JobStatusDetailResponse`, `MatchedStepResponse`, `DiscrepancyStepResponse`, `OrderMismatchResponse`, `DiscrepancyReportResponse`, `IndexingResult` extension with visual fields
    - _Requirements: 10.3, 10.5, 10.6, 10.7_

  - [x] 1.5 Write property test for video upload validation (Property 10)
    - **Property 10: Video upload validation**
    - Generate random (content_type, file_size) pairs and verify accept/reject logic
    - **Validates: Requirements 4.1, 4.2**

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Visual Content Detection service
  - [x] 3.1 Implement VisualContentDetector class
    - Create `src/backend/src/alcoabase/services/visual_content_detector.py`
    - Implement `detect_visual_pages()`: render pages to PNG at 150 DPI, compute text_area_ratio, check for image/drawing objects
    - Implement `_classify_page()`: detect arrow connectors (flowchart), axis lines (chart), shapes (diagram), or mixed
    - Enforce max_visual_pages=100 cap, page_timeout_seconds=30, sequential processing
    - Handle PDF via PyMuPDF (fitz) and DOCX via python-docx
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 3.2 Write property test for visual content classification (Property 1)
    - **Property 1: Visual content classification correctness**
    - Generate random (text_area_ratio, has_images) pairs, verify classification if and only if ratio < 0.3 AND has images
    - **Validates: Requirements 1.1, 1.2, 1.7**

  - [x] 3.3 Write property test for classification type assignment (Property 2)
    - **Property 2: Visual classification type assignment**
    - Generate pages with various shape/connector patterns, verify correct VisualType
    - **Validates: Requirements 1.3**

  - [x] 3.4 Write property test for visual page processing cap (Property 3)
    - **Property 3: Visual page processing cap**
    - Generate documents with 50-200 visual pages, verify max 100 returned
    - **Validates: Requirements 1.5**

- [x] 4. Visual content indexing pipeline
  - [x] 4.1 Extend KnowledgeService with visual indexing methods
    - Add `index_document_with_visuals()` to `src/backend/src/alcoabase/services/knowledge_service.py`
    - Implement `_interpret_visual_page()`: render page at 300 DPI (max 4096x4096), base64 encode, call Vision_Model with diagram-specific prompt (Type, Elements, Connections, Summary), retry once on failure, discard responses < 20 chars
    - Implement `_create_visual_chunks()`: chunk description (512 tokens, 50 overlap), attach metadata (content_type, is_visual, visual_type, source_page, document_uuid, version)
    - Process visual pages sequentially, enforce 300s total timeout, track visual_indexing_status
    - Handle mock mode with placeholder text
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 12.1, 12.2, 12.3, 12.4, 12.7, 12.8_

  - [x] 4.2 Write property test for description minimum length (Property 5)
    - **Property 5: Visual description minimum length validation**
    - Generate strings of length 0-100, verify accept/reject at 20-char threshold
    - **Validates: Requirements 2.7**

  - [x] 4.3 Write property test for Visual_Chunk metadata correctness (Property 6)
    - **Property 6: Visual_Chunk metadata correctness**
    - Generate random descriptions + metadata, verify all required fields present and correct
    - **Validates: Requirements 2.3, 2.5**

  - [x] 4.4 Write property test for mock mode isolation (Property 4)
    - **Property 4: Mock mode isolation (no HTTP requests)**
    - Generate random operations in mock mode, verify no HTTP calls made and placeholder content returned
    - **Validates: Requirements 1.6, 2.8, 6.10, 7.9**

  - [x] 4.5 Write property test for text indexing independence (Property 19)
    - **Property 19: Text indexing independence from visual processing**
    - Generate documents with visual failures, verify text chunks always indexed
    - **Validates: Requirements 12.1, 12.2**

  - [x] 4.6 Write property test for visual indexing status (Property 20)
    - **Property 20: Visual indexing status correctness**
    - Generate various indexing outcomes, verify correct status assignment
    - **Validates: Requirements 12.3, 12.5, 12.6**

  - [x] 4.7 Write property test for re-indexing cleanup (Property 21)
    - **Property 21: Re-indexing removes stale Visual_Chunks**
    - Generate re-index scenarios, verify old chunks removed before new ones created
    - **Validates: Requirements 12.4**

- [x] 5. RAG Pipeline visual content retrieval
  - [x] 5.1 Extend RAGPipeline with visual chunk handling
    - Add `_apply_visual_boost()` to `src/backend/src/alcoabase/services/rag_pipeline.py`: boost Visual_Chunk scores by configurable factor (default 1.5x) when query contains process-related keywords
    - Add `_limit_visual_chunks()`: cap Visual_Chunks at 3 per query, fill remaining slots with text chunks
    - Update `_build_context()`: format Visual_Chunks with `[Source N: {title} v{version} - {visual_type} on page {source_page}]` pattern
    - Update citation response to include `content_type` and `visual_type` fields
    - _Requirements: 3.1, 3.2, 3.3, 3.5, 3.6, 3.7_

  - [x] 5.2 Write property test for visual boost (Property 8)
    - **Property 8: Visual chunk relevance boost for process queries**
    - Generate queries with/without keywords + result sets, verify boost applied correctly
    - **Validates: Requirements 3.5**

  - [x] 5.3 Write property test for visual chunk limit (Property 9)
    - **Property 9: Visual chunk limit per query**
    - Generate result sets with 0-10 visual chunks, verify max 3 in final context
    - **Validates: Requirements 3.6**

  - [x] 5.4 Write property test for visual citation formatting (Property 7)
    - **Property 7: Visual source citation formatting**
    - Generate Visual_Chunks with random metadata, verify citation pattern
    - **Validates: Requirements 3.2, 3.3**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. JobTracker service
  - [x] 7.1 Implement JobTracker class
    - Create `src/backend/src/alcoabase/services/job_tracker.py`
    - Implement `create_job()`: generate UUID job_id, check for conflicts (same document + operation in PROCESSING state), insert into processing_jobs table
    - Implement `update_progress()`, `complete_job()`, `fail_job()`, `get_job()`, `has_active_job()`
    - Raise `JobConflictError` when concurrent operation detected
    - _Requirements: 5.4, 5.8, 6.9, 7.8, 10.6, 10.7, 10.8_

  - [x] 7.2 Write property test for concurrent operation conflict detection (Property 12)
    - **Property 12: Concurrent operation conflict detection**
    - Generate job states + new requests, verify conflict detection and job_id in response
    - **Validates: Requirements 5.8, 6.9, 7.8, 10.8**

- [x] 8. AlignmentService - Frame extraction and analysis
  - [x] 8.1 Implement frame extraction in AlignmentService
    - Create `src/backend/src/alcoabase/services/alignment_service.py`
    - Implement `extract_frames()`: download video from MinIO, run ffmpeg subprocess to extract PNG frames at interval, auto-adjust interval if frames > 500, cap resolution at 1920x1080, store frame metadata, clean up on failure
    - Integrate with JobTracker for async job tracking and conflict detection
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [x] 8.2 Implement frame analysis in AlignmentService
    - Implement `analyze_frames()`: load extracted frames, call Vision_Model sequentially with frame-specific prompt (action, equipment, PPE, text, concise description), consolidate similar frames (cosine similarity > 0.85) into Step_Sequence, store in database
    - Handle frame failures (mark as "unanalyzed"), abort if > 50% fail, mock mode with placeholder descriptions
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10_

  - [x] 8.3 Write property test for frame count calculation (Property 11)
    - **Property 11: Frame extraction count and interval calculation**
    - Generate random (duration, interval) pairs, verify frame count = min(ceil(D/I), 500) and interval adjustment
    - **Validates: Requirements 5.1, 5.5**

  - [x] 8.4 Write property test for frame consolidation (Property 13)
    - **Property 13: Frame consolidation into steps**
    - Generate frame embedding sequences with known similarities, verify consolidation logic
    - **Validates: Requirements 6.5, 6.6**

  - [x] 8.5 Write property test for frame analysis abort threshold (Property 14)
    - **Property 14: Frame analysis abort threshold**
    - Generate random frame counts + failure patterns, verify abort at > 50% failure
    - **Validates: Requirements 6.8**

- [x] 9. AlignmentService - Audio transcription and SOP operations
  - [x] 9.1 Implement audio transcription in AlignmentService
    - Implement `transcribe_audio()`: extract audio via ffmpeg (WAV 16kHz mono), segment into 30s chunks, process through speech-to-text model, store transcript segments with timestamps
    - Handle no audio track (return empty), model unavailable (503), extraction failure (422), mock mode
    - Implement transcript merge with Step_Sequence by timestamp overlap
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9_

  - [x] 9.2 Implement SOP linking in AlignmentService
    - Implement `link_sop()`: validate SOP exists, same tenant, correct document_type, max 10 links, no duplicates
    - Create association record with video_document_uuid, sop_document_uuid, sop_version, linked_at
    - _Requirements: 8.1, 8.2, 8.3, 8.10_

  - [x] 9.3 Implement alignment and discrepancy report generation
    - Implement `align()`: load Step_Sequence, extract SOP steps via Chat_Model, compare using semantic similarity (threshold 0.7), classify matched/missing/extra/order_mismatch
    - Implement severity classification via Chat_Model (critical/major/minor), fallback to "major" on failure
    - Generate recommendations via Chat_Model, fallback to generic text on failure
    - Calculate alignment_score, set requires_review if < 0.5, store Discrepancy_Report
    - _Requirements: 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_

  - [x] 9.4 Write property test for audio transcript merge (Property 15)
    - **Property 15: Audio transcript segment merge by timestamp overlap**
    - Generate step sequences + transcript segments, verify assignment by greatest overlap duration
    - **Validates: Requirements 7.7**

  - [x] 9.5 Write property test for step comparison classification (Property 16)
    - **Property 16: Step comparison classification**
    - Generate step pairs with known cosine similarities, verify matched/missing/extra/order_mismatch classification
    - **Validates: Requirements 8.7, 9.1**

  - [x] 9.6 Write property test for severity fallback (Property 17)
    - **Property 17: Discrepancy severity fallback**
    - Generate discrepancies with mock Chat_Model failures, verify default "major" severity and generic recommendation
    - **Validates: Requirements 9.4, 9.9**

  - [x] 9.7 Write property test for requires-review flag (Property 18)
    - **Property 18: Requires-review flag threshold**
    - Generate random alignment scores, verify requires_review=true when score < 0.5
    - **Validates: Requirements 9.10**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Video Alignment API router
  - [x] 11.1 Create video alignment router with all endpoints
    - Create `src/backend/src/alcoabase/api/video_alignment.py` with FastAPI router (prefix `/knowledge/videos`)
    - Implement endpoints: `POST /{document_uuid}/extract-frames`, `POST /{document_uuid}/analyze-frames`, `POST /{document_uuid}/transcribe-audio`, `POST /{document_uuid}/link-sop`, `POST /{document_uuid}/align`, `GET /{document_uuid}/report`, `GET /jobs/{job_id}`
    - Validate required headers (Authorization, X-User-Id, X-Company-Id, X-Change-Reason for POST)
    - Validate document_uuid format, existence, tenant scoping, document_type="Training Video"
    - Return appropriate HTTP status codes (201, 202, 404, 403, 409, 422)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [x] 11.2 Extend video upload handling in document service
    - Update `src/backend/src/alcoabase/services/document_service.py` to accept video content types (video/mp4, video/x-msvideo, video/quicktime, video/webm)
    - Validate file size (> 0 bytes, <= 2 GB) and content type
    - Run ffprobe with 30s timeout to extract metadata (duration, resolution, frame_count, codec)
    - Store video metadata in `video_metadata` table; set null on ffprobe failure
    - Set document_type to "Training Video", do NOT auto-trigger frame extraction
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [x] 11.3 Register video alignment router in main router
    - Add video alignment router to `src/backend/src/alcoabase/api/router.py`
    - Ensure prefix resolves to `/api/knowledge/videos/...`
    - _Requirements: 10.1_

  - [x] 11.4 Write unit tests for video alignment API endpoints
    - Test all endpoint validations: missing headers, invalid UUID, document not found, wrong tenant, wrong document_type
    - Test HTTP 409 conflict responses include existing job_id
    - Test HTTP 422 precondition failures with clear error messages
    - _Requirements: 10.2, 10.4, 10.8_

- [x] 12. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 13. Frontend - Visual citation rendering
  - [x] 13.1 Update Knowledge Page citation rendering for visual content
    - Update citation components in `src/frontend/src/pages/` (Knowledge page) to detect `content_type: "visual"` in citations
    - Render visual citations with a distinct icon indicator and `visual_type` badge alongside document title and page reference
    - _Requirements: 3.4_

- [x] 14. Frontend - Video Alignment UI
  - [x] 14.1 Create Video Alignment section in Knowledge Page
    - Add "Video Alignment" section to the Video_Document detail view
    - Display latest Discrepancy_Report with alignment score percentage badge (green 80%+, yellow 50-79%, red <50%)
    - Render side-by-side comparison view (video steps left, SOP steps right) with visual connectors for matched pairs
    - Color-code discrepancies: red (critical), orange (major), yellow (minor) with severity legend
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 14.2 Implement video step detail view and summary panel
    - On step click: display frame thumbnails for timestamp range, full description, audio transcript text
    - Summary panel: alignment score, total steps counts, matched/missing/extra/reordered counts, generation date, linked SOP title with link
    - _Requirements: 11.4, 11.5_

  - [x] 14.3 Implement job progress tracking and action prompts
    - When no report exists: show prompt with action buttons (Extract Frames → Analyze Frames → Align)
    - While processing: poll `GET /api/knowledge/videos/jobs/{job_id}` every 5 seconds, show progress percentage and estimated time
    - Auto-render results on completion, show error on failure
    - Handle API errors (network, 5xx, timeout 15s) with error message and retry button
    - _Requirements: 11.6, 11.7, 11.8_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (21 properties total)
- Unit tests validate specific examples and edge cases
- The design uses Python (FastAPI, SQLAlchemy, Pydantic, pytest, Hypothesis) throughout
- Frontend uses React with TypeScript (Vite + Vitest)
- All backend commands run from `src/backend/` with `uv run pytest --tb=short -q`
- ffmpeg/ffprobe calls are mocked in unit tests via `unittest.mock`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3", "1.4"] },
    { "id": 1, "tasks": ["1.2", "1.5"] },
    { "id": 2, "tasks": ["3.1", "7.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "7.2"] },
    { "id": 4, "tasks": ["4.1", "5.1"] },
    { "id": 5, "tasks": ["4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["8.1"] },
    { "id": 7, "tasks": ["8.2", "8.3"] },
    { "id": 8, "tasks": ["8.4", "8.5", "9.1", "9.2"] },
    { "id": 9, "tasks": ["9.3", "9.4"] },
    { "id": 10, "tasks": ["9.5", "9.6", "9.7"] },
    { "id": 11, "tasks": ["11.1", "11.2"] },
    { "id": 12, "tasks": ["11.3", "11.4"] },
    { "id": 13, "tasks": ["13.1", "14.1"] },
    { "id": 14, "tasks": ["14.2", "14.3"] }
  ]
}
```
