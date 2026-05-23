# Training Management User Guide

This guide explains how to use the Training Management features in AlcoaBase. It covers viewing your training tasks, completing training, reviewing training content, managing training records, and understanding the training gate that controls document access.

## Overview

When a document workflow transitions to the "InTraining" state, AlcoaBase automatically assigns training tasks to relevant users. The Training Management UI provides:

- A personal dashboard showing your pending and completed training tasks
- Training content viewer with procedural steps, safety points, and quizzes
- A training records panel showing your completion history
- An admin view for monitoring organization-wide training progress
- A training gate that blocks document access until training is complete

## Accessing the Training Dashboard

Navigate to the **Training** page from the main navigation. The dashboard displays:

1. **Status Overview** — Three stat cards showing Pending, Completed, and Total task counts, plus an overall completion percentage.
2. **Tab Navigation** — Switch between "My Tasks", "Records", and (for admins) "Admin: SOP Training Status".

## My Tasks Tab

### Viewing Tasks

Your assigned training tasks appear as cards showing:
- Task title (truncated at 80 characters if long)
- SOP document UUID and version
- Completion status (Pending or Completed with timestamp)

### Filtering Tasks

Use the filter controls at the top to show:
- **All** — every assigned task
- **Pending** — only incomplete tasks
- **Completed** — only finished tasks

Tasks are automatically sorted with pending tasks first (oldest first), followed by completed tasks (most recent first).

### Viewing Training Content

Click any task card to load its training content below the task list. The content viewer displays:

- **Summary** — overview of what the training covers
- **Procedural Steps** — numbered steps to follow, with safety-critical steps highlighted in red with warning icons and safety notes
- **Safety Points** — important safety information in an amber warning panel
- **Quiz Questions** — multiple-choice questions with shuffled answer options

For quiz questions, click **"Reveal Answer"** to see the correct answer and its SOP section reference. Click again to hide it.

### Completing a Task

1. Click the **"Mark Complete"** button on a pending task card.
2. A confirmation dialog appears showing the task details.
3. Enter a **change reason** (3–500 characters) explaining why you're marking this complete.
4. Click **"Confirm"** to submit.

> **Note:** The "Mark Complete" button is only enabled after you have passed the comprehension quiz for that SOP version. See the [Comprehension Quiz Guide](quiz-comprehension-guide.md) for details on taking and passing the quiz.

The dialog shows a character counter and validates your input. If submission fails (e.g., network error), the error appears inline and your input is preserved so you can retry.

## Records Tab

The Records tab shows your training completion history:

- Each record displays the SOP UUID, version, completion date, and a validity badge
- **Valid** (green) — this is the most recent training for that SOP
- **Invalidated** (red) — a newer version of training exists for this SOP

### Sorting and Grouping

- Use the **Sort by** dropdown to order records by Completion Date (default), SOP UUID, or Version
- Records are grouped by SOP UUID — click the chevron toggle to expand/collapse historical versions within a group

## Admin: SOP Training Status Tab

This tab is only visible to users with the **admin** role.

### SOP Selector

Use the dropdown to select which SOP document and version to inspect. The view updates to show:

- **Progress Bar** — visual completion percentage with numeric label
- **Stats Summary** — Total Tasks, Completed, and Pending counts
- **Training Complete Badge** — appears when all users have finished training
- **User Breakdown Table** — shows each assigned user's ID, status (Completed/Pending), and completion date

### Content Review

Below the status display, the **Content Review** section shows training content items awaiting approval:

1. Click a pending item to open it in the content viewer (review mode).
2. Review the content — all sections are visible even for pending/draft content.
3. Click **"Approve"** or **"Reject"** to update the content status.
4. A success notification appears briefly after each action.

## Training Gate (Document Access Control)

When a document's workflow state is "InTraining", AlcoaBase enforces a training gate:

### How It Works

- When you navigate to a document in "InTraining" status, the system checks whether you have a completed training record AND have passed the comprehension quiz for that SOP version.
- **Both conditions met** — you see the document normally, plus a green banner confirming your training status.
- **Training incomplete** — access is blocked with a full-page message: "Training Required — Action denied: Valid training record for this SOP Version X.X is missing."
- **Training complete but quiz not passed** — access is blocked with: "Training task completed but comprehension quiz has not been passed for this SOP version."
- A **"Go to Training"** link takes you directly to the Training page.

For full details on the quiz requirement, see the [Comprehension Quiz Guide](quiz-comprehension-guide.md).

### Training Status Banner

On the document detail page, an inline banner shows your training status:
- **Amber banner** — "Training required: You have not completed training for {SOP Name} v{version}. Complete training to gain full access."
- **Green banner** — "Training complete: You have completed training for {SOP Name} v{version}. Completed on {date}."

Both banners include a "View Training" link for quick navigation.

### Timeout Handling

If the training status check takes longer than 10 seconds (e.g., due to network issues), an error state appears with a **"Retry"** button.

## Accessibility

The Training Management UI is built with accessibility in mind:

- All interactive elements have proper ARIA labels and roles
- Loading states are announced via `aria-live` regions
- The task completion dialog implements a focus trap (Tab/Shift+Tab cycle within the dialog)
- Filter controls use `role="radiogroup"` with `aria-checked` attributes
- Error messages use `role="alert"` with `aria-live="assertive"`
- The training gate blocking message uses `role="alert"` for screen reader announcement

## Keyboard Navigation

- **Tab/Shift+Tab** — navigate between interactive elements
- **Enter/Space** — activate buttons and filter options
- **Escape** — close the task completion dialog (unless submission is in progress)
