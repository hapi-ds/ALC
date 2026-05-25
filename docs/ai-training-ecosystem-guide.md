# AI-Enhanced Training Ecosystem

The AI-Enhanced Training Ecosystem transforms AlcoaBase's static training management into an intelligent, adaptive learning platform. It uses the Educational Specialist agent archetype to generate personalized schedules, training materials, comprehension assessments, and interactive virtual audits — all with full ALCOA+ audit trail compliance.

---

## Overview

The ecosystem comprises five interconnected capabilities:

1. **AI Training Planner** — Generates personalized training schedules and identifies skill gaps
2. **AI Training Material Generator** — Produces structured educational content from SOPs
3. **Automated Question Generator** — Creates comprehension quizzes with semantic grading
4. **Virtual Audit Engine** — Interactive role-play sessions testing document comprehension
5. **Dynamic Feedback** — Points users to exact source paragraphs when they answer incorrectly

All AI operations run asynchronously via Celery (routed to the `ai_operations` queue). Generated content requires coordinator approval before being served to trainees.

---

## Accessing the Training Ecosystem

Navigate to **AI Training** in the sidebar (or visit `/training/ecosystem`). The page has four tabs:

- **Schedule** — Your personalized training plan with priority-sorted items
- **Materials** — AI-generated educational content for each document
- **Assessments** — Quiz results and dynamic feedback
- **Virtual Audit** — Interactive conversational assessment

---

## AI Training Planner

### Generating a Schedule

Coordinators can generate a personalized training schedule for any user:

1. Use the API: `POST /api/training/planner/generate` with `{"user_id": <id>}`
2. The system analyzes the user's role, assigned documents, existing training records, and compliance deadlines
3. A schedule is produced with items sorted by priority

### Priority Levels

| Priority | Criteria | Access-Gate Elevation |
|----------|----------|----------------------|
| Critical | Deadline ≤ 7 days or overdue | — |
| High | Deadline ≤ 30 days | Medium → High |
| Medium | Deadline ≤ 90 days | Low → Medium |
| Low | Deadline > 90 days | — |

Documents that gate access via training-gated control (Phase 3.5) are elevated by one priority level.

### Skill Gap Analysis

- **Company-wide report**: `GET /api/training/planner/gaps` — shows total users with gaps, top documents needing training, per-framework compliance
- **Individual gaps**: `GET /api/training/planner/gaps/{user_id}` — specific documents a user needs to complete

Skill gaps are recalculated automatically every 6 hours via Celery beat.

---

## AI Training Material Generator

### Generating Materials

Coordinators trigger material generation from the document detail page or via API:

```
POST /api/training/materials/generate
{
  "document_id": 1,
  "document_version_id": 2,
  "material_types": ["executive_summary", "detailed_walkthrough", "safety_highlights"]
}
```

If `material_types` is omitted, all five types are generated.

### Material Types

| Type | Rendered As | Description |
|------|-------------|-------------|
| `executive_summary` | Card | Concise overview with key points |
| `detailed_walkthrough` | Accordion | Step-by-step procedural guide |
| `key_takeaways` | Bullet list | Critical information highlights |
| `presentation_outline` | Slide carousel | Slide-by-slide outline with speaker notes |
| `safety_highlights` | Warning panel | Safety-critical information with emphasis |

### Approval Workflow

All generated materials start in `pending_review` status. Coordinators must approve before trainees can see them:

- `PATCH /api/training/materials/{id}/approve`
- `PATCH /api/training/materials/{id}/reject`

Only approved materials are displayed to trainee-role users.

---

## Automated Question Generator

### Generating Questions

```
POST /api/training/questions/generate
{
  "document_id": 1,
  "document_version_id": 2,
  "question_count": 10,
  "difficulty_distribution": {"basic": 0.4, "intermediate": 0.4, "advanced": 0.2}
}
```

Constraints enforced:
- Minimum 5, maximum 20 questions per generation
- At least 30% basic, at least 30% intermediate, at most 30% advanced
- No duplicate `(sop_section_ref, question_type)` pairs in a batch

### Question Types

| Type | Grading Method | Threshold |
|------|---------------|-----------|
| `multiple_choice` | Exact match | — |
| `true_false` | Exact match | — |
| `fill_in_blank` | Semantic similarity (embedding) | ≥ 0.85 |
| `scenario_based` | LLM evaluation | ≥ 0.70 |

Empty or null answers are marked incorrect with confidence 0.0 without invoking inference.

### Approval and Registration

After coordinator approval, questions are registered as the active quiz set:

```
POST /api/training/quiz/register
```

This links approved questions to the training gate so that passing the quiz (or virtual audit) satisfies the comprehension verification requirement.

---

## Virtual Audit Engine

### Starting a Session

```
POST /api/training/roleplay/start
{
  "document_id": 1,
  "document_version_id": 2,
  "user_id": 42
}
```

Returns `session_id`, `first_question`, and `total_turns`.

### Session Rules

- **Turn count**: 5 turns (< 10 sections), 7 turns (10–20 sections), 10 turns (> 20 sections)
- **Progressive difficulty**: First 40% foundational → next 35% applied → remaining 25% analytical
- **Scoring**: Weighted average per turn — factual accuracy (50%), completeness (30%), document reference quality (20%)
- **Passing**: Overall score ≥ 0.70 AND at least 3 turns completed
- **Incomplete**: Fewer than 3 turns → marked "Incomplete" regardless of score

### Submitting Responses

```
POST /api/training/roleplay/{session_id}/respond
{"response_text": "Your answer here (max 2000 characters)"}
```

Returns per-turn evaluation scores, next question, and running session score.

### Stale Session Handling

Sessions with no activity for 60+ minutes are automatically marked as "abandoned" (checked every 15 minutes via Celery beat). Score is computed on completed turns only.

### Training Gate Integration

A passed virtual audit creates a synthetic `QuizAttempt` record, maintaining backward compatibility with the existing training gate. Users can satisfy the comprehension requirement via either path:

- ✅ Passed quiz (80% threshold), OR
- ✅ Passed virtual audit (≥ 0.70 score, ≥ 3 turns)

---

## Dynamic Feedback

When a user answers a question incorrectly, they can request paragraph-level feedback:

```
GET /api/training/feedback/{question_id}
```

**Requirements**: The user must have at least one failed attempt (returns 403 otherwise).

**Response includes**:
- `correct_answer` — The correct answer text
- `paragraph_text` — Exact source paragraph from the document (via RAG retrieval)
- `section_reference` — Clickable link to the document section
- `page_number` — Page in the source document
- `explanation` — LLM-generated explanation connecting the paragraph to the answer

### Caching and Invalidation

Feedback is cached by `(question_id, document_version_id)`. When a new document version is published, all cached feedback for the previous version is automatically invalidated.

### Fallback Behavior

- No paragraph above 0.75 similarity → returns `sop_section_ref` with a generic review message
- InferenceClient unavailable → returns paragraph without LLM explanation, substitutes: "Review the highlighted paragraph for the correct information."

---

## API Reference

### Training Planner

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/training/planner/generate` | Request schedule generation (async, 202) |
| GET | `/api/training/planner/schedule/{user_id}` | Get user's training schedule |
| GET | `/api/training/planner/gaps` | Company-wide skill gap report |
| GET | `/api/training/planner/gaps/{user_id}` | Individual user skill gaps |

### Training Materials

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/training/materials/generate` | Request material generation (async, 202) |
| GET | `/api/training/materials/{document_id}` | List materials (filterable) |
| PATCH | `/api/training/materials/{id}/approve` | Approve material |
| PATCH | `/api/training/materials/{id}/reject` | Reject material |

### Training Questions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/training/questions/generate` | Request question generation (async, 202) |
| GET | `/api/training/questions/{document_id}` | List questions (filterable) |
| PATCH | `/api/training/questions/{id}/approve` | Approve question |
| PATCH | `/api/training/questions/{id}/reject` | Reject question |

### Role-Play Virtual Audit

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/training/roleplay/start` | Start virtual audit session |
| POST | `/api/training/roleplay/{session_id}/respond` | Submit response |
| GET | `/api/training/roleplay/{session_id}` | Get session state |
| GET | `/api/training/roleplay/history/{user_id}` | Session history |

### Dynamic Feedback

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/training/feedback/{question_id}` | Get paragraph-level feedback |

### Common Headers

All mutating endpoints (POST, PATCH) require:
- `X-Change-Reason` — Audit trail reason (enforced by AuditMiddleware)
- `X-Company-Id` — Tenant isolation
- `X-User-Id` — User attribution

---

## Celery Tasks

All training AI tasks route to the `ai_operations` queue with:
- `soft_time_limit`: 600 seconds (10 minutes)
- `max_retries`: 3 with exponential backoff + jitter
- Progress reporting via JobTracker

### Periodic Tasks (Celery Beat)

| Schedule | Task | Description |
|----------|------|-------------|
| Every 6 hours | `recalculate_skill_gaps` | Recompute gaps for all companies |
| Every 15 minutes | `abandon_stale_sessions` | Mark inactive sessions as abandoned |

---

## Configuration

Add to your `.env`:

```env
# AI Training Ecosystem (Phase 5.3)
# Celery queue for AI training operations (shared with other AI tasks)
CELERY_AI_QUEUE=ai_operations

# Skill gap recalculation interval (hours)
SKILL_GAP_RECALC_INTERVAL_HOURS=6

# Stale session timeout (minutes) — sessions with no activity are abandoned
ROLEPLAY_STALE_SESSION_MINUTES=60

# Semantic similarity threshold for fill-in-blank grading
FILL_IN_BLANK_THRESHOLD=0.85

# LLM evaluation threshold for scenario-based grading
SCENARIO_BASED_THRESHOLD=0.70

# RAG similarity threshold for dynamic feedback paragraph selection
FEEDBACK_SIMILARITY_THRESHOLD=0.75
```

---

## Roles and Permissions

| Action | Coordinator/Admin | Trainee |
|--------|-------------------|---------|
| Generate materials/questions | ✅ | ❌ |
| Approve/reject content | ✅ | ❌ |
| View approved materials | ✅ | ✅ |
| Take quizzes | ✅ | ✅ |
| Start virtual audits | ✅ | ✅ |
| View feedback | ✅ | ✅ (after failed attempt) |
| View skill gap reports | ✅ | Own gaps only |
