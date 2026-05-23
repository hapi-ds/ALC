# Implementation Plan: Training-Gated Access Control

## Overview

This plan implements Phase 3.5 of AlcoaBase's training enforcement — adding a comprehension quiz requirement before users can mark training tasks complete or pass the training gate. The implementation proceeds from data model → backend service → API endpoints → enhanced backend guards → frontend store → frontend components → property-based tests.

## Tasks

- [x] 1. Database model and migration
  - [x] 1.1 Create QuizAttempt SQLAlchemy model
    - Add `QuizAttempt` class to `src/backend/src/alcoabase/models/training.py`
    - Include all fields: id, user_id, content_id, sop_document_uuid, sop_version, answers (JSON), score, total_questions, passed, attempted_at, company_id
    - Apply `AuditMixin` for SQLAlchemy-Continuum versioning
    - Add indexes: user_id, content_id, sop_document_uuid, composite (user_id, content_id, passed)
    - Register model in `__init__.py` exports if needed
    - _Requirements: 1.1, 1.5, 11.1_

  - [x] 1.2 Create Alembic migration for quiz_attempts table
    - Generate migration with `alembic revision --autogenerate`
    - Verify migration creates `quiz_attempts` table with all columns and indexes
    - Verify migration creates `quiz_attempts_version` table (from AuditMixin/Continuum)
    - _Requirements: 1.1, 1.5_

- [x] 2. Backend QuizService implementation
  - [x] 2.1 Implement QuizService core methods
    - Create `src/backend/src/alcoabase/services/quiz_service.py`
    - Implement `compute_pass_threshold(total_questions)` → `math.ceil(total_questions * 0.8)`
    - Implement `evaluate_and_persist(session, content_id, user_id, answers, company_id)` — retrieve TrainingContent, validate status is "approved", compare answers via exact string match, compute score, determine pass/fail, persist QuizAttempt
    - Implement `has_user_passed(session, user_id, content_id)` — check existence of any QuizAttempt with passed=True
    - Implement `get_best_score(session, user_id, content_id)` — return max score or None
    - Implement `get_user_results(session, user_id, content_id, limit=50)` — return attempts ordered by attempted_at descending
    - Handle edge cases: content not found (404), content not approved (400), user not found (404), total_questions < 1 rejection
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 2.2 Write property tests for pass threshold computation
    - **Property 2: Pass threshold computation**
    - Test that for any positive integer total_questions and any score 0 ≤ score ≤ total_questions, passed is true iff score >= ceil(total_questions * 0.8)
    - Use Hypothesis with `@settings(max_examples=100)`
    - Target file: `src/backend/tests/test_quiz_properties.py`
    - **Validates: Requirements 1.2**

  - [x] 2.3 Write property tests for score computation
    - **Property 3: Score computation with partial and extraneous answers**
    - Test that for any set of quiz questions and any submitted answers map, score equals count of matching answers where question_id exists in quiz AND answer matches exactly
    - Use Hypothesis with `@settings(max_examples=100)`
    - Target file: `src/backend/tests/test_quiz_properties.py`
    - **Validates: Requirements 2.2, 2.5, 2.6**

  - [x] 2.4 Write property tests for has_passed aggregation and best_score
    - **Property 5: has_passed aggregation**
    - Test that has_passed is true iff at least one attempt has passed=True
    - **Property 6: best_score computation**
    - Test that best_score equals max score among all attempts, or null for empty list
    - Use Hypothesis with `@settings(max_examples=100)`
    - Target file: `src/backend/tests/test_quiz_properties.py`
    - **Validates: Requirements 3.3, 4.2, 4.3**

- [x] 3. Quiz API endpoints
  - [x] 3.1 Implement POST /api/training/quiz/submit endpoint
    - Add Pydantic request/response schemas for quiz submission
    - Add endpoint to existing training router at `src/backend/src/alcoabase/api/training.py`
    - Wire to QuizService.evaluate_and_persist
    - Return attempt_id, score, total_questions, passed, passing_score_threshold, correct_answers, attempted_at
    - Ensure X-Change-Reason header is required (handled by audit middleware)
    - _Requirements: 2.1, 2.2, 2.7, 2.8_

  - [x] 3.2 Implement GET /api/training/quiz/results/{content_id} endpoint
    - Add Pydantic response schema for quiz results list
    - Add endpoint to training router
    - Accept user_id query parameter (required, positive integer)
    - Return results list (ordered by attempted_at desc, limit 50) and has_passed boolean
    - Handle missing/invalid user_id with 422
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 3.3 Implement GET /api/training/quiz/passed/{content_id} endpoint
    - Add Pydantic response schema for pass status
    - Add endpoint to training router
    - Accept user_id query parameter (required, positive integer)
    - Return content_id, user_id, has_passed, best_score
    - Handle missing/invalid user_id with 422
    - Return has_passed=false, best_score=null when no attempts exist
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 3.4 Add HTTP 405 handler for PUT/PATCH/DELETE on quiz attempt endpoints
    - Reject any update or delete operations on quiz attempt records
    - Return HTTP 405 with detail "Quiz attempt records are immutable and cannot be modified or deleted."
    - _Requirements: 11.2_

  - [x] 3.5 Write property tests for results ordering and immutability
    - **Property 7: Results ordering**
    - Test that results are ordered by attempted_at descending and limited to 50
    - **Property 8: Quiz attempt immutability**
    - Test that PUT/PATCH/DELETE on quiz attempts returns 405
    - Use Hypothesis with `@settings(max_examples=100)`
    - Target file: `src/backend/tests/test_quiz_properties.py`
    - **Validates: Requirements 3.1, 11.2**

- [x] 4. Checkpoint - Ensure all backend quiz service and API tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Enhanced TrainingService guards
  - [x] 5.1 Enhance TrainingService.complete_training_task with quiz prerequisite
    - Modify `src/backend/src/alcoabase/services/training_service.py`
    - After existing validations, derive content_id as `{sop_document_uuid}_v{sop_version}`
    - Call QuizService.has_user_passed to verify quiz pass
    - Return HTTP 400 if quiz not passed, content not generated, or SOP reference missing
    - Proceed with existing completion flow if quiz passed
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 5.2 Enhance TrainingService.check_training_gate with dual verification
    - Modify `check_training_gate` in `src/backend/src/alcoabase/services/training_service.py`
    - After existing TrainingRecord check, also verify quiz pass via QuizService.has_user_passed
    - Return HTTP 403 with specific message if record exists but quiz not passed
    - Return HTTP 403 with existing message if no valid record
    - Allow action if both conditions met
    - Resolve SOP_Name from document title, fallback to sop_document_uuid
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 5.3 Write property tests for task completion guard and gate dual verification
    - **Property 9: Task completion requires quiz pass**
    - Test that task completion succeeds only if user has passed quiz for derived content_id
    - **Property 10: Backend training gate dual verification**
    - Test that gate allows iff both valid TrainingRecord AND quiz passed
    - **Property 12: Version-specific quiz pass enforcement**
    - Test that quiz pass for content_id v{N} does not satisfy gate for v{M} where M ≠ N
    - Use Hypothesis with `@settings(max_examples=100)`
    - Target file: `src/backend/tests/test_quiz_properties.py`
    - **Validates: Requirements 5.1, 6.1, 12.1, 12.2**

- [x] 6. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Frontend types and TrainingStore extensions
  - [x] 7.1 Add frontend TypeScript types for quiz
    - Add QuizAttemptResult, QuizPassStatus, QuizResultsResponse, QuizAttemptHistoryEntry interfaces to `src/frontend/src/components/training/types.ts`
    - _Requirements: 10.1_

  - [x] 7.2 Extend TrainingStore with quiz state and actions
    - Add quiz state fields to the existing Zustand store: currentQuizAttempt, isSubmittingQuiz, quizSubmitError, quizResults, isLoadingQuizResults, quizResultsError, quizPassCache, isCheckingQuizPass, quizPassError
    - Implement submitQuiz action with request deduplication, X-Change-Reason header, quizPassCache update on pass, gate cache invalidation
    - Implement fetchQuizResults action with request deduplication
    - Implement checkQuizPassed action with cache-first strategy and request deduplication
    - Implement clearQuizPassCache action
    - Wire gate cache invalidation on quiz pass (invalidate quizPassCache entry for derived content_id)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_

  - [x] 7.3 Write property tests for frontend store quiz logic
    - **Property 13: Quiz pass cache consistency**
    - Test that first checkQuizPassed call makes network request and caches; subsequent calls return cached value without network request
    - **Property 14: Gate cache invalidation on state change**
    - Test that quiz pass or task completion invalidates corresponding gate cache and quizPassCache entries
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Target file: `src/frontend/src/__tests__/stores/quizProperties.test.ts`
    - **Validates: Requirements 10.5, 10.8, 9.5**

- [x] 8. Frontend QuizTakingUI component
  - [x] 8.1 Implement QuizTakingUI component
    - Create `src/frontend/src/components/training/QuizTakingUI.tsx`
    - Implement states: idle (Take Quiz button or Quiz Passed badge), taking (sequential question form with radio buttons, progress indicator), submitting (loading on submit button), results (score display, per-question feedback, pass/fail), error (error message with conditional retry)
    - Show "Take Quiz" button for approved content with quiz questions
    - Show "Quiz Passed" badge with best score if already passed (check quizPassCache)
    - Require all questions answered before enabling submit
    - Display progress indicator "{answered_count} of {total_questions} answered"
    - Randomize answer option order once when quiz starts
    - On pass: show success message and enable Mark Complete
    - On fail: show failure message with "Retake Quiz" button
    - On network error: show error with retry, retain answers
    - On HTTP 400/404: show error detail without retry
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11_

  - [x] 8.2 Write unit tests for QuizTakingUI
    - Test renders "Take Quiz" button for approved content
    - Test shows "Quiz Passed" badge when already passed
    - Test disables submit until all questions answered
    - Test shows loading state during submission
    - Test displays results panel on success
    - Test shows success message on pass, failure message on fail
    - Test handles network error with retry
    - Test handles 400/404 without retry
    - Target file: `src/frontend/src/__tests__/components/QuizTakingUI.test.tsx`
    - _Requirements: 7.1, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11_

- [x] 9. Frontend TrainingTaskCard and TrainingGateGuard enhancements
  - [x] 9.1 Enhance TrainingTaskCard with quiz pass guard
    - Modify existing TrainingTaskCard component
    - Disable "Mark Complete" button with tooltip "Pass the quiz to enable task completion" when quiz not passed
    - Show loading spinner while checking quiz pass status (isCheckingQuizPass)
    - Show error icon with retry on network failure
    - Enable "Mark Complete" when quizPassCache shows true for content_id
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 9.2 Enhance TrainingGateGuard with dual verification
    - Modify existing TrainingGateGuard component
    - Add checkQuizPassed call alongside existing task completion check
    - Block navigation with specific message if task complete but quiz not passed
    - Block navigation with existing message if task not complete
    - Allow navigation if both conditions met
    - Cache combined gate result, invalidate on task completion or quiz pass
    - Show error with retry on network failure (fail-closed)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 9.3 Write property test for frontend gate dual verification
    - **Property 11: Frontend training gate dual verification**
    - Test that TrainingGateGuard allows navigation iff both task completed AND quiz passed
    - Use fast-check with `fc.assert(property, { numRuns: 100 })`
    - Target file: `src/frontend/src/__tests__/stores/quizProperties.test.ts`
    - **Validates: Requirements 9.1**

  - [x] 9.4 Write unit tests for TrainingTaskCard quiz guard
    - Test "Mark Complete" disabled when quiz not passed
    - Test "Mark Complete" enabled when quiz passed
    - Test loading spinner during pass check
    - Test error icon with retry on network failure
    - Target file: `src/frontend/src/__tests__/components/TrainingTaskCard.test.tsx`
    - _Requirements: 8.1, 8.2, 8.4, 8.5_

- [x] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python/FastAPI/SQLAlchemy async with Hypothesis for PBT
- Frontend uses React/TypeScript/Zustand with Vitest and fast-check for PBT
- API prefix is `/api` (NOT `/api/v1`) for training endpoints
- Training router prefix is `/training` (full paths: `/api/training/quiz/*`)
- X-Change-Reason header required on all POST requests (enforced by audit middleware)
- Quiz attempts are immutable (append-only) for ALCOA+ audit compliance
