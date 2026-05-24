# Implementation Plan: AI-Enhanced Training Ecosystem

## Overview

This plan implements the AI-Enhanced Training Ecosystem (Phase 5.3) in incremental steps. It builds on the existing training management system (3.3), Educational Specialist agent archetype (5.1), InferenceClient (4.3), KnowledgeService (4.2), and Celery infrastructure. Each task builds on previous work, starting with database models and schemas, then layering in services, Celery tasks, API routers, QuizService extensions, frontend components, and tests.

## Tasks

- [ ] 1. Database models and Alembic migration
  - [-] 1.1 Create training ecosystem database models
    - Create `src/backend/src/alcoabase/models/training_ecosystem.py`
    - Implement enums: GapType, PriorityLevel, MaterialType, QuestionType, DifficultyLevel, SessionStatus
    - Implement `TrainingSchedule` model with AuditMixin: id, user_id (FK), company_id (FK), schedule_data (JSONB), compliance_percentage, total_items, completed_items, generated_at, last_recalculated_at, created_at, updated_at
    - Add UniqueConstraint on (user_id, company_id) and CheckConstraint completed_items <= total_items
    - Implement `SkillGap` model: id, user_id, company_id, document_id, document_version_id, gap_type, priority, days_overdue, blocks_access, identified_at, resolved_at, created_at
    - Add UniqueConstraint on (user_id, document_id, document_version_id, gap_type)
    - Implement `TrainingMaterial` model with AuditMixin: id, document_id, document_version_id, company_id, material_type, content_data (JSONB), learning_objectives (JSON), estimated_duration_minutes, status, generated_by_agent_id, inference_duration_ms, reviewed_by, reviewed_at, created_at, updated_at
    - Add UniqueConstraint on (document_id, document_version_id, material_type)
    - Implement `GeneratedQuestion` model with AuditMixin: id, document_id, document_version_id, company_id, question_text (Text), question_type, correct_answer (Text), distractors (JSON), explanation (Text), difficulty_level, bloom_taxonomy_level, sop_section_ref, status, reviewed_by, reviewed_at, created_at, updated_at
    - Implement `VirtualAuditSession` model with AuditMixin: id, user_id, document_id, document_version_id, company_id, status, overall_score, passed, turns_completed, total_turns, session_data (JSONB), summary_data (JSONB), started_at, completed_at, created_at
    - Add CheckConstraint turns_completed <= total_turns
    - Implement `DynamicFeedbackCache` model: id, question_id (FK), document_version_id (FK), paragraph_text (Text), section_reference, page_number, similarity_score, explanation (Text), created_at
    - Add UniqueConstraint on (question_id, document_version_id)
    - Add all composite indexes per design: user_id+company_id, document_id+document_version_id, status indexes
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_

  - [~] 1.2 Register models and create Alembic migration
    - Import all new models in `src/backend/src/alcoabase/models/__init__.py`
    - Ensure SQLAlchemy-Continuum picks up versioned models (TrainingSchedule, TrainingMaterial, GeneratedQuestion, VirtualAuditSession)
    - Generate Alembic migration adding training_schedules, skill_gaps, training_materials, generated_questions, virtual_audit_sessions, dynamic_feedback_cache tables
    - Include all foreign keys, indexes, unique constraints, and check constraints
    - _Requirements: 8.1–8.8_

- [ ] 2. Pydantic schemas
  - [~] 2.1 Create training ecosystem Pydantic schemas
    - Create `src/backend/src/alcoabase/schemas/training_ecosystem.py`
    - Implement request schemas: ScheduleGenerateRequest, MaterialGenerateRequest, QuestionGenerateRequest, RolePlayStartRequest, RolePlayRespondRequest (max_length=2000)
    - Implement response schemas: JobAcceptedResponse, TrainingScheduleResponse, SkillGapResponse, CompanyGapReportResponse, TrainingMaterialResponse, GeneratedQuestionResponse, VirtualAuditSessionResponse, TurnEvaluationResponse, DynamicFeedbackResponse
    - Add Field constraints: question_count (ge=5, le=20), response_text (max_length=2000)
    - All numeric fields with proper ge/le constraints per design
    - _Requirements: 9.1–9.15_

- [ ] 3. Core service layer — Training Planner
  - [~] 3.1 Implement TrainingPlannerService
    - Create `src/backend/src/alcoabase/services/training_planner.py`
    - Implement `compute_priority(deadline, blocks_access)` pure function with deadline proximity rules (Critical ≤7d, High ≤30d, Medium ≤90d, Low >90d) and access-gate elevation
    - Implement `compute_compliance_percentage(completed, total)` returning round((completed/total)*100, 1) with 100.0 when total=0
    - Implement `request_schedule_generation(user_id, company_id)`: validate user exists and has assigned documents, dispatch Celery task, return job_id
    - Implement `get_schedule(user_id, company_id)`: retrieve current TrainingSchedule
    - Implement `get_company_gaps(company_id, limit, offset)`: aggregated skill gap report with top documents, top users, per-framework compliance
    - Implement `get_user_gaps(user_id, company_id)`: individual skill gap detail
    - Implement `recalculate_gaps(company_id)`: compare required documents vs completed training records, create/resolve SkillGap records
    - _Requirements: 1.1–1.10, 2.1–2.8_

  - [~] 3.2 Write property test for priority assignment (Property 1)
    - **Property 1: Priority assignment is deterministic and rule-based**
    - Generate random deadline datetimes and blocks_access booleans; verify priority matches deadline proximity rules and elevation logic
    - **Validates: Requirements 1.3**

  - [~] 3.3 Write property test for skill gap set difference (Property 2)
    - **Property 2: Skill gap identification is the set difference of required vs completed training**
    - Generate random sets of required documents and completed training records; verify gaps equal R \ C exactly
    - **Validates: Requirements 1.4, 2.1**

  - [~] 3.4 Write property test for compliance percentage (Property 3)
    - **Property 3: Compliance percentage is bounded and correctly computed**
    - Generate random completed/total pairs where completed ≤ total; verify result in [0.0, 100.0] and matches formula
    - **Validates: Requirements 1.7, 2.2, 5.5**

- [ ] 4. Core service layer — Training Material Generator
  - [~] 4.1 Implement TrainingMaterialGeneratorService
    - Create `src/backend/src/alcoabase/services/training_material_generator.py`
    - Implement `request_generation(document_id, document_version_id, company_id, material_types)`: validate document exists, dispatch Celery task, return job_id
    - Implement `get_materials(document_id, company_id, material_type, status, limit, offset)`: retrieve with filtering and pagination
    - Implement `approve_material(material_id, reviewer_id, company_id)`: validate status is pending_review, update to approved
    - Implement `reject_material(material_id, reviewer_id, company_id)`: validate status is pending_review, update to rejected
    - Implement `generate_material_content(document_content, material_type, previous_content)`: core LLM generation logic using Educational Specialist archetype
    - Handle document chunking when content exceeds context window
    - _Requirements: 3.1–3.12_

  - [~] 4.2 Write property test for content starts pending_review (Property 5)
    - **Property 5: All AI-generated content starts in pending_review status**
    - Generate random material types and generation parameters; verify initial status is always "pending_review"
    - **Validates: Requirements 3.6, 4.7**

- [ ] 5. Core service layer — Question Generator
  - [~] 5.1 Implement QuestionGeneratorService
    - Create `src/backend/src/alcoabase/services/question_generator.py`
    - Implement `request_generation(document_id, document_version_id, company_id, question_count, difficulty_distribution)`: validate document, dispatch Celery task, return job_id
    - Implement `get_questions(document_id, company_id, status, difficulty_level, question_type, limit, offset)`: retrieve with filtering
    - Implement `approve_question(question_id, reviewer_id, company_id)` and `reject_question(question_id, reviewer_id, company_id)`
    - Implement `grade_answer(question, user_answer)`: route to appropriate grading method based on question_type
    - Implement `grade_fill_in_blank(correct_answer, user_answer)`: semantic similarity via embedding model, threshold 0.85, fallback to exact match
    - Implement `grade_scenario_based(question_text, correct_answer, source_paragraph, user_answer)`: LLM evaluation, threshold 0.70, fallback to exact match
    - Handle empty/null answers: mark incorrect with confidence_score 0.0 without invoking inference
    - Record grading metadata: grading_method, confidence_score, time_to_grade_ms
    - _Requirements: 4.1–4.14, 5.1–5.9_

  - [~] 5.2 Write property test for difficulty distribution (Property 6)
    - **Property 6: Question difficulty distribution satisfies constraints**
    - Generate random N (5–20); verify at least 30% basic, at least 30% intermediate, at most 30% advanced, sum equals N
    - **Validates: Requirements 4.4**

  - [~] 5.3 Write property test for no duplicate (section_ref, type) pairs (Property 7)
    - **Property 7: No duplicate question (section_ref, question_type) pairs per generation batch**
    - Generate random question sets; verify no two questions share (sop_section_ref, question_type) within a batch
    - **Validates: Requirements 4.5**

  - [~] 5.4 Write property test for grading method selection (Property 8)
    - **Property 8: Grading method selection and threshold application**
    - Generate random question types and answers; verify correct grading method is selected and thresholds applied (exact for MC/TF, 0.85 for fill_in_blank, 0.70 for scenario_based, 0.0 for empty)
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.6**

- [~] 6. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Core service layer — Role-Play Engine
  - [~] 7.1 Implement RolePlayEngineService
    - Create `src/backend/src/alcoabase/services/roleplay_engine.py`
    - Implement `compute_total_turns(section_count)`: 5 for <10, 7 for 10–20, 10 for >20 sections
    - Implement `compute_session_score(turns)`: weighted average (accuracy 50%, completeness 30%, reference 20%)
    - Implement `start_session(document_id, document_version_id, user_id, company_id)`: check for existing in-progress session (return it if found), create VirtualAuditSession, generate first auditor question via InferenceClient with temperature 0.4
    - Implement `submit_response(session_id, response_text, company_id)`: validate session is in_progress, dispatch evaluate_roleplay_response Celery task, return evaluation + next question
    - Implement `get_session(session_id, company_id)` and `get_user_history(user_id, company_id, ...)`
    - Implement `abandon_stale_sessions()`: mark sessions inactive for 60+ minutes as abandoned, compute score on completed turns
    - Implement progressive difficulty: foundational (first 40%), applied (next 35%), analytical (remaining 25%)
    - Handle session completion: compute overall score, determine pass/fail (≥0.70 AND ≥3 turns), generate summary
    - _Requirements: 6.1–6.13_

  - [~] 7.2 Write property test for turn count determination (Property 9)
    - **Property 9: Virtual audit turn count is determined by document section count**
    - Generate random section_count integers; verify turn count is 5 (<10), 7 (10–20), or 10 (>20)
    - **Validates: Requirements 6.3**

  - [~] 7.3 Write property test for session score and pass/fail (Property 10)
    - **Property 10: Virtual audit session score and pass/fail determination**
    - Generate random turn scores (factual_accuracy, completeness, document_reference_quality all in [0,1]); verify weighted average and pass/fail logic (≥0.70 AND ≥3 turns)
    - **Validates: Requirements 6.5, 6.6**

  - [~] 7.4 Write property test for progressive difficulty distribution (Property 11)
    - **Property 11: Progressive difficulty distribution across virtual audit turns**
    - Generate random total_turns (5, 7, 10); verify first 40% foundational, next 35% applied, remaining analytical
    - **Validates: Requirements 6.2**

- [ ] 8. Core service layer — Dynamic Feedback
  - [~] 8.1 Implement DynamicFeedbackService
    - Create `src/backend/src/alcoabase/services/dynamic_feedback.py`
    - Implement `get_feedback(question_id, user_id, company_id)`: check failed attempt exists (return 403 if not), check cache, generate if uncached
    - Implement `generate_feedback(question)`: query KnowledgeService with question text + correct answer scoped to source document, select paragraph with similarity ≥ 0.75, generate explanation via InferenceClient
    - Implement `invalidate_cache(document_version_id)`: delete all DynamicFeedbackCache entries for the version
    - Implement `has_failed_attempt(question_id, user_id, company_id)`: check QuizAttempt records
    - Handle fallback: if no paragraph above 0.75 threshold, return sop_section_ref with generic message
    - Handle InferenceClient unavailability: return paragraph without explanation, substitute generic message
    - Cache results keyed by (question_id, document_version_id)
    - _Requirements: 7.1–7.10_

  - [~] 8.2 Write property test for feedback requires failed attempt (Property 12)
    - **Property 12: Dynamic feedback requires at least one failed attempt**
    - Generate random user/question combinations with varying attempt histories; verify 403 when zero failed attempts, 200 when at least one
    - **Validates: Requirements 7.7, 9.12**

  - [~] 8.3 Write property test for cache invalidation (Property 13)
    - **Property 13: Feedback cache invalidation on new document version**
    - Generate cached entries, simulate new version publish; verify all previous version entries are invalidated
    - **Validates: Requirements 7.6**

- [ ] 9. Celery task definitions
  - [~] 9.1 Implement training ecosystem Celery tasks
    - Create `src/backend/src/alcoabase/tasks/training_tasks.py`
    - Implement `generate_training_schedule` task: retrieve user role and assigned documents, get Educational Specialist archetype via AgentRegistryService, construct schedule generation prompt, call InferenceClient, parse response into TrainingSchedule, persist to DB, update job_tracker
    - Implement `generate_training_materials` task: retrieve document content from MinIO via StorageService, generate each material type via InferenceClient, persist TrainingMaterial records with status=pending_review, record inference_duration_ms
    - Implement `generate_questions` task: retrieve document content, generate questions with difficulty distribution, validate no duplicate (section_ref, type) pairs, persist GeneratedQuestion records with status=pending_review
    - Implement `evaluate_roleplay_response` task: evaluate user response on 3 dimensions (factual_accuracy, completeness, document_reference_quality), generate next question or compute session summary, update VirtualAuditSession
    - Implement `recalculate_skill_gaps` task: compare required vs completed training for all users in company, create/resolve SkillGap records
    - All tasks: route to "ai_operations" queue, soft_time_limit=600, max_retries=3, exponential backoff with jitter
    - All tasks: report progress via job_tracker (create_job, update_progress, complete_job/fail_job)
    - Handle SoftTimeLimitExceeded: catch and mark job as failed with reason "timeout"
    - Handle partial failures: preserve partial records, record failure with count of successful records
    - _Requirements: 12.1–12.10_

  - [~] 9.2 Add Celery beat schedule entries
    - Add `recalculate-skill-gaps-every-6-hours` to celery_app.conf.beat_schedule (crontab every 6 hours, queue=ai_operations)
    - Add `abandon-stale-roleplay-sessions` to celery_app.conf.beat_schedule (crontab every 15 minutes, queue=ai_operations)
    - _Requirements: 2.5, 6.13, 12.5_

  - [~] 9.3 Write property test for partial records preserved on failure (Property 16)
    - **Property 16: Partial records are preserved on task failure**
    - Simulate task failures after producing partial records; verify persisted records remain and job_tracker records failure with count
    - **Validates: Requirements 12.9**

- [~] 10. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. FastAPI routers
  - [~] 11.1 Implement training planner router
    - Create `src/backend/src/alcoabase/api/training_planner.py`
    - POST /api/training/planner/generate — accept {user_id}, require X-Change-Reason, return 202 with job_id
    - GET /api/training/planner/schedule/{user_id} — return current schedule with compliance percentage
    - GET /api/training/planner/gaps — company-wide gap report with limit/offset pagination
    - GET /api/training/planner/gaps/{user_id} — individual user gaps
    - Scope all to X-Company-Id header, return 400 if missing, 404 for non-existent resources
    - _Requirements: 1.6, 1.7, 1.8, 2.1, 2.4, 2.6, 2.7, 2.8_

  - [~] 11.2 Implement training materials router
    - Create `src/backend/src/alcoabase/api/training_materials.py`
    - POST /api/training/materials/generate — accept {document_id, document_version_id, material_types}, require X-Change-Reason, return 202
    - GET /api/training/materials/{document_id} — list materials with material_type, status, limit, offset filters
    - PATCH /api/training/materials/{material_id}/approve — require X-Change-Reason
    - PATCH /api/training/materials/{material_id}/reject — require X-Change-Reason
    - _Requirements: 9.1, 9.2, 9.3_

  - [~] 11.3 Implement training questions router
    - Create `src/backend/src/alcoabase/api/training_questions.py`
    - POST /api/training/questions/generate — accept {document_id, document_version_id, question_count, difficulty_distribution}, require X-Change-Reason, return 202
    - GET /api/training/questions/{document_id} — list questions with status, difficulty_level, question_type, limit, offset filters
    - PATCH /api/training/questions/{question_id}/approve — require X-Change-Reason
    - PATCH /api/training/questions/{question_id}/reject — require X-Change-Reason
    - _Requirements: 9.4, 9.5, 9.6_

  - [~] 11.4 Implement training roleplay router
    - Create `src/backend/src/alcoabase/api/training_roleplay.py`
    - POST /api/training/roleplay/start — accept {document_id, document_version_id, user_id}, require X-Change-Reason, return session_id + first_question + total_turns
    - POST /api/training/roleplay/{session_id}/respond — accept {response_text max 2000}, require X-Change-Reason, return evaluation + next_question + session_complete + current_score
    - GET /api/training/roleplay/{session_id} — return full session state
    - GET /api/training/roleplay/history/{user_id} — paginated session history with document_id, status, passed, limit, offset filters
    - Return 409 for respond on completed/abandoned sessions, 422 for response exceeding 2000 chars
    - _Requirements: 9.7, 9.8, 9.9, 9.10, 9.13_

  - [~] 11.5 Implement training feedback router
    - Create `src/backend/src/alcoabase/api/training_feedback.py`
    - GET /api/training/feedback/{question_id} — return dynamic feedback (correct_answer, paragraph_text, section_reference, page_number, explanation)
    - Return 403 if user has no failed attempts for the question
    - _Requirements: 9.11, 9.12_

  - [~] 11.6 Register new routers in router.py
    - Add training_planner, training_materials, training_questions, training_roleplay, and training_feedback routers to the central router in `src/backend/src/alcoabase/api/router.py`
    - _Requirements: 9.1–9.15_

  - [~] 11.7 Write property test for company-scoped tenant isolation (Property 4)
    - **Property 4: Company-scoped tenant isolation**
    - Generate multi-company training data (schedules, gaps, materials, questions, sessions); verify listing returns only data for the specified company
    - **Validates: Requirements 1.8, 2.6, 3.10, 6.12, 7.8, 9.15**

  - [~] 11.8 Write unit tests for API endpoints
    - Test all HTTP status codes: 202, 200, 400, 403, 404, 409, 422
    - Test X-Change-Reason header enforcement on POST/PATCH mutations
    - Test pagination and filtering on all list endpoints
    - Test response_text max length validation (2000 chars)
    - Test feedback 403 when no failed attempts
    - Test roleplay 409 on completed/abandoned sessions
    - _Requirements: 9.1–9.15_

- [ ] 12. QuizService extensions for training gate integration
  - [~] 12.1 Extend QuizService for AI-generated questions and semantic grading
    - Modify `src/backend/src/alcoabase/services/quiz_service.py`
    - Implement `evaluate_and_persist_enhanced(session, content_id, user_id, answers, company_id)`: route each answer to appropriate grading method (exact for MC/TF, semantic for fill_in_blank, LLM for scenario_based), fallback to exact match if inference unavailable
    - Implement `register_approved_questions(document_id, document_version_id, document_uuid, sop_version, company_id)`: register approved questions as active question set with content_id format {document_uuid}_v{sop_version}
    - Implement `has_user_passed_enhanced(session, user_id, content_id)`: return true if passed quiz OR passed virtual audit exists
    - Create synthetic QuizAttempt record when virtual audit passes (passed=true, score=turns_above_0.70, total_questions=total_turns, answers={})
    - Ensure only approved questions are served in active assessments
    - Mark previous version question sets as inactive when new version approved
    - Maintain backward compatibility with existing POST /api/training/quiz/submit, GET /api/training/quiz/passed/{content_id}, GET /api/training/quiz/results/{content_id}
    - _Requirements: 11.1–11.8_

  - [~] 12.2 Write property test for training gate OR logic (Property 14)
    - **Property 14: Training gate satisfaction via quiz OR virtual audit**
    - Generate random combinations of quiz attempts and virtual audit sessions; verify has_user_passed returns true iff at least one passed quiz OR one passed virtual audit exists
    - **Validates: Requirements 11.2, 11.3**

  - [~] 12.3 Write property test for only approved questions served (Property 15)
    - **Property 15: Only approved questions are served in active assessments**
    - Generate questions with various statuses (pending_review, approved, rejected, draft); verify only approved questions appear in active assessments
    - **Validates: Requirements 11.4, 4.10**

- [~] 13. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Frontend — Training Ecosystem Page and Store
  - [~] 14.1 Create TypeScript types and API client functions
    - Create `src/frontend/src/types/training-ecosystem.ts` with interfaces: TrainingSchedule, SkillGap, TrainingMaterial, GeneratedQuestion, VirtualAuditSession, TurnEvaluation, DynamicFeedback, CompanyGapReport, Job
    - Create `src/frontend/src/lib/training-ecosystem-api.ts` with typed API functions for all training planner, materials, questions, roleplay, and feedback endpoints
    - Use existing apiClient with X-Change-Reason header on mutations
    - _Requirements: 10.1, 10.8_

  - [~] 14.2 Create Zustand store for training ecosystem state
    - Create `src/frontend/src/stores/trainingEcosystemStore.ts`
    - State: schedule, skillGaps, materials (keyed by document_id), questions (keyed by document_id), activeSession, sessionHistory, pendingJobs, loading states
    - Actions: fetchSchedule, fetchGaps, generateMaterials, generateQuestions, startRolePlay, submitResponse, pollJobs
    - Polling logic: refresh pending jobs every 15 seconds
    - _Requirements: 10.7, 10.8_

  - [~] 14.3 Implement TrainingEcosystemPage and TrainingSchedulePanel
    - Create `src/frontend/src/pages/TrainingEcosystemPage.tsx`
    - Route at /training/ecosystem with sub-panels for schedule, materials, assessments, role-play
    - Create `src/frontend/src/components/training/TrainingSchedulePanel.tsx`
    - Display training items sorted by priority (Critical first) then deadline (earliest first)
    - Show document title (truncated 120 chars), priority badge (color-coded), deadline, completion status, "Start Training" button
    - Progress bar showing completed_items / total_items percentage
    - Skeleton loading state and empty state message
    - _Requirements: 10.1, 10.2, 10.9_

  - [~] 14.4 Implement SkillGapAlert component
    - Create `src/frontend/src/components/training/SkillGapAlert.tsx`
    - Dismissible banner at top of training page when Critical or High priority gaps exist
    - Show gap count and link to /training/ecosystem?view=gaps
    - _Requirements: 10.3_

  - [~] 14.5 Implement TrainingMaterialViewer component
    - Create `src/frontend/src/components/training/TrainingMaterialViewer.tsx`
    - Render only approved materials to trainee role users
    - Render formats: executive_summary as card, detailed_walkthrough as step-by-step accordion, presentation_outline as slide-deck carousel, safety_highlights as warning panel with distinct border and icon
    - _Requirements: 10.4_

  - [~] 14.6 Implement VirtualAuditInterface component
    - Create `src/frontend/src/components/training/VirtualAuditInterface.tsx`
    - Chat-style interface: auditor questions left-aligned, user responses right-aligned
    - Per-turn score indicators (green ≥0.70, yellow ≥0.40, red <0.40)
    - Progress bar showing turns completed vs total_turns
    - Response input with 2000 character limit indicator
    - _Requirements: 10.5_

  - [~] 14.7 Implement DynamicFeedbackPanel component
    - Create `src/frontend/src/components/training/DynamicFeedbackPanel.tsx`
    - Display correct answer highlighted in green
    - Show source paragraph with relevant sentence highlighted
    - Section reference as clickable link navigating to document viewer
    - LLM-generated explanation text
    - _Requirements: 10.6_

  - [~] 14.8 Implement generation actions and job monitoring
    - Add "Generate Materials" and "Generate Quiz" action buttons on documents requiring training (visible to coordinator/admin roles only)
    - Disable buttons when generation job is pending/in_progress, show current job status
    - Implement JobMonitor component with 15-second polling for job status updates
    - _Requirements: 10.7, 10.8_

  - [~] 14.9 Add route and navigation for TrainingEcosystemPage
    - Register /training/ecosystem route in App.tsx
    - Add navigation link in sidebar
    - _Requirements: 10.1_

- [~] 15. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 16. Frontend and backend tests
  - [~] 16.1 Write frontend component tests
    - Create tests in `src/frontend/src/__tests__/training-ecosystem/`
    - Test TrainingEcosystemPage: renders schedule, materials, assessments
    - Test TrainingSchedulePanel: priority sorting, progress bar, empty state, skeleton loading
    - Test VirtualAuditInterface: chat bubbles, score indicators, turn progress
    - Test DynamicFeedbackPanel: paragraph highlighting, section links
    - Test TrainingMaterialViewer: renders each material type correctly
    - Test Zustand store: state management, API integration
    - _Requirements: 10.1–10.9_

  - [~] 16.2 Write backend unit tests for services
    - Create tests in `src/backend/tests/unit/test_training_ecosystem/`
    - Test TrainingPlannerService: priority computation edge cases, compliance percentage, schedule generation logic
    - Test TrainingMaterialGeneratorService: material structure validation, chunking logic, approve/reject flows
    - Test QuestionGeneratorService: question validation, distribution enforcement, grading method routing
    - Test RolePlayEngineService: turn management, score computation, session lifecycle, abandon logic
    - Test DynamicFeedbackService: cache hit/miss, fallback behavior, threshold handling
    - Test QuizService extensions: enhanced grading, bridge record creation, register_approved_questions
    - _Requirements: 1.1–12.10_

  - [~] 16.3 Write backend integration tests
    - Create tests in `src/backend/tests/integration/test_training_ecosystem/`
    - Test full material generation pipeline: request → Celery task → DB persistence → retrieval
    - Test full question generation pipeline: request → generation → approval → quiz availability
    - Test virtual audit full session: start → N responses → completion → bridge record creation
    - Test dynamic feedback with RAG: question → retrieval → explanation
    - Test training gate integration: approve questions → submit quiz → verify gate passes
    - Test skill gap recalculation: create training record → verify gap resolved
    - _Requirements: 1.1–12.10_

- [~] 17. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (16 properties)
- Tasks marked with `*` are optional and can be skipped for faster MVP
- The existing `QuizService` is extended (not replaced) to maintain backward compatibility with training gate (3.5)
- All backend API endpoints use the `/api` prefix (not `/api/v1`)
- All mutating requests require the `X-Change-Reason` header per AuditMiddleware conventions
- Frontend uses the existing `apiClient` for consistent auth and header handling
- Celery tasks use the existing `celery_app` and route to the `ai_operations` queue
- The Educational Specialist archetype YAML (from 5.1) provides system prompts and temperature settings at runtime
- All AI inference goes through the existing InferenceClient (4.3) with retry logic and timeout handling
- RAG-powered feedback uses the existing KnowledgeService (4.2) hybrid search
- Job status tracking uses the existing JobTracker service for consistent frontend polling

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["3.1", "4.1", "5.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "4.2", "5.2", "5.3", "5.4", "7.1", "8.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4", "8.2", "8.3", "9.1"] },
    { "id": 5, "tasks": ["9.2", "9.3"] },
    { "id": 6, "tasks": ["11.1", "11.2", "11.3", "11.4", "11.5"] },
    { "id": 7, "tasks": ["11.6", "12.1"] },
    { "id": 8, "tasks": ["11.7", "11.8", "12.2", "12.3"] },
    { "id": 9, "tasks": ["14.1", "14.2"] },
    { "id": 10, "tasks": ["14.3", "14.4", "14.5", "14.6", "14.7", "14.8"] },
    { "id": 11, "tasks": ["14.9"] },
    { "id": 12, "tasks": ["16.1", "16.2", "16.3"] }
  ]
}
```
