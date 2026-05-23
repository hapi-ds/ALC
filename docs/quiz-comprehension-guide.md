# Comprehension Quiz User Guide

This guide explains the comprehension quiz feature in AlcoaBase — a mandatory verification step that ensures users understand SOP content before they can complete training tasks or pass through the training gate.

## Overview

As part of ALCOA+ compliance, AlcoaBase requires users to pass a comprehension quiz before marking a training task as complete. This ensures that simply reading an SOP is not sufficient — users must demonstrate understanding of the material.

The quiz system enforces:

- **80% passing threshold** — users must answer at least 80% of questions correctly (rounded up)
- **Immutable audit trail** — every quiz attempt (pass or fail) is permanently recorded
- **Version-specific enforcement** — passing a quiz for SOP v1.0 does not satisfy the requirement for v2.0
- **Dual verification gate** — both task completion AND quiz pass are required to access regulated documents

## Taking a Quiz

### Prerequisites

Before a quiz is available:
1. The SOP must be in "InTraining" status
2. Training content must be generated and approved by a coordinator
3. The content must contain at least one quiz question

### Starting the Quiz

1. Navigate to the **Training** page and select a pending training task.
2. The training content viewer loads below, showing the summary, procedural steps, and safety points.
3. At the bottom of the content viewer, you'll see a **"Take Quiz"** button (only visible for approved content with quiz questions).
4. Click **"Take Quiz"** to begin.

### Answering Questions

- Questions are displayed sequentially with radio button options.
- Answer options are randomized each time you start a new attempt.
- A progress indicator shows "{answered} of {total} answered" with a visual progress bar.
- You must answer ALL questions before the Submit button becomes active.

### Submitting Answers

1. Once all questions are answered, click **"Submit Quiz"**.
2. A loading spinner appears while your answers are evaluated.
3. Results appear immediately after submission.

### Understanding Results

**On Pass (score ≥ 80%):**
- A green success panel shows your score (e.g., "4/5").
- Message: "Quiz passed! You may now mark this training task as complete."
- Per-question feedback shows which answers were correct.
- The "Mark Complete" button on the task card becomes enabled.

**On Fail (score < 80%):**
- A red failure panel shows your score.
- Message: "Quiz not passed. You need at least 80% correct answers. Please review the training material and try again."
- Per-question feedback shows your answer vs. the correct answer for each question.
- A **"Retake Quiz"** button lets you try again immediately.

### Error Handling

- **Network error** — an error message appears with a **"Retry"** button. Your answers are preserved so you don't need to re-enter them.
- **Content unavailable (400/404)** — an error message appears without a retry button, indicating the quiz is no longer available (e.g., content was unapproved).

## Quiz Pass Badge

Once you've passed a quiz, the "Take Quiz" button is replaced with a green **"Quiz Passed"** badge showing your best score (e.g., "Quiz Passed (4/5)"). You can still retake the quiz if desired, but the pass status is already recorded.

## Mark Complete Button States

The "Mark Complete" button on each training task card reflects your quiz status:

| State | Button Appearance |
|-------|-------------------|
| Checking quiz status | Loading spinner with "Checking…" |
| Quiz not passed | Disabled button with tooltip: "Pass the quiz to enable task completion" |
| Network error | Error icon with "Retry" button |
| Quiz passed | Enabled "Mark Complete" button |

## Training Gate (Dual Verification)

The training gate now enforces two conditions before allowing access to documents in "InTraining" status:

1. **Training task completed** — the user has marked their training task as done
2. **Quiz passed** — the user has at least one passing quiz attempt for that SOP version

### Gate Blocking Messages

| Condition | Message |
|-----------|---------|
| Task not complete | "Action denied: Valid training record for this SOP Version X.X is missing." |
| Task complete, quiz not passed | "Training task completed but comprehension quiz has not been passed for this SOP version." |
| Both conditions met | Document access granted |

### Fail-Closed Behavior

If the quiz status check fails due to a network error, access is blocked (fail-closed) with an error message and a "Retry" button. This ensures that network issues cannot be exploited to bypass the quiz requirement.

## Version-Specific Enforcement

Quiz passes are tied to a specific SOP version. If an SOP is updated to a new major version:

- Previous training records are invalidated
- Users must complete new training tasks
- Users must pass the quiz for the NEW version's content
- Passing the quiz for v1.0 does NOT satisfy the requirement for v2.0

## Scoring Rules

- **Exact string matching** — answers must match the correct answer exactly (case-sensitive)
- **Missing answers** — unanswered questions count as incorrect
- **Passing threshold** — `ceil(total_questions × 0.8)` correct answers required
- **Examples:** 5 questions → need 4 correct; 10 questions → need 8 correct; 3 questions → need 3 correct

## Audit Trail

Every quiz attempt is permanently recorded with:

- User ID and timestamp
- All submitted answers (as JSON)
- Score and total questions
- Pass/fail determination
- SOP document UUID and version

Quiz attempt records are **immutable** — they cannot be modified or deleted. Any attempt to update or delete a quiz record via the API returns HTTP 405 ("Quiz attempt records are immutable and cannot be modified or deleted."). This ensures a complete, tamper-proof audit trail for regulatory compliance.

## API Endpoints

For integrators and administrators, the quiz system exposes three endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/training/quiz/submit` | Submit quiz answers for evaluation |
| GET | `/api/training/quiz/results/{content_id}?user_id={id}` | Get quiz attempt history (up to 50 most recent) |
| GET | `/api/training/quiz/passed/{content_id}?user_id={id}` | Check if user has passed the quiz |

All POST requests require the `X-Change-Reason` header per ALCOA+ audit requirements.

## Accessibility

The quiz UI is built with accessibility in mind:

- Radio button groups use `role="radiogroup"` with proper `aria-label` attributes
- Progress bar uses `role="progressbar"` with `aria-valuenow`, `aria-valuemin`, `aria-valuemax`
- Results use `role="alert"` for screen reader announcement
- Error states use `role="alert"` with descriptive messages
- All buttons have descriptive `aria-label` attributes
- Loading states are communicated via `aria-live` regions
