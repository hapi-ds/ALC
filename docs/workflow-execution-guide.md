# Workflow Execution User Guide

This guide explains how to manage document state transitions using the workflow execution features in AlcoaBase. It covers viewing a document's current workflow state, triggering transitions, understanding gate requirements, and reviewing transition history.

## Overview

Once an admin has designed a workflow using the [Workflow Editor](workflow-editor-guide.md), documents tagged with that workflow's document type automatically gain lifecycle management. The workflow execution features appear on the document detail page and allow you to:

- See the current state of a document (e.g., Draft, Review, Approved)
- Advance the document to the next state via transition buttons
- Provide a mandatory change reason for every transition (ALCOA+ compliance)
- View gate indicators showing when signatures or training are required
- Review the full history of who changed the state, when, and why

## Viewing Document Workflow State

When you open a document that has an assigned workflow, the **Workflow State Panel** appears below the document metadata section.

### What You'll See

- **Workflow name** — which lifecycle workflow governs this document
- **Risk level badge** — color-coded indicator (gray=low, blue=medium, orange=high, red=critical)
- **Current state badge** — the document's current position in the lifecycle, color-coded:
  - Gray: Draft
  - Blue: Review
  - Green: Approved
  - Red: Rejected
- **Last updated** — when the state last changed, in your local date/time format
- **Transition buttons** — available next states you can move the document to

### No Workflow Assigned

If a document's tags don't match any active workflow definition, the workflow panels won't appear. This is normal for documents that don't require lifecycle management.

## Triggering a State Transition

To advance a document through its lifecycle:

1. **Click a transition button** in the Workflow State Panel. Each button is labeled with the target state (e.g., "QA Review", "Approved").

2. **Provide a change reason** in the confirmation dialog that appears. This is mandatory for ALCOA+ compliance:
   - Minimum 3 characters, maximum 500 characters
   - A character counter shows remaining space
   - The confirm button stays disabled until the reason is valid

3. **Review any gate warnings** displayed in the dialog:
   - **Yellow/amber warning** — this transition requires an electronic signature (PAdES)
   - **Blue informational** — this transition will trigger training assignments for affected staff
   - **Orange/red risk warning** — the document is under a high-risk or critical workflow

4. **Click Confirm** to execute the transition, or **Cancel** to abort.

### After a Successful Transition

- The state badge updates to show the new state
- The transition buttons refresh to show the next available transitions
- The document's status badge in the metadata section updates
- The transition history records the change

### If Something Goes Wrong

- Error messages appear inline in the dialog
- Your change reason text is preserved so you don't have to retype it
- Both buttons re-enable so you can retry or cancel
- If the request takes longer than 30 seconds, it times out automatically

## Understanding Gate Indicators

Transition buttons may display icons indicating pre-conditions:

| Icon | Meaning | What Happens |
|------|---------|--------------|
| 🔒 Lock | Requires electronic signature | After transition, you'll need to complete a PAdES digital signature (Phase 3.4) |
| 📖 Book | Triggers training assignment | After transition, training tasks are created for affected staff (Phase 3.3) |

Hover over a gate icon to see a tooltip explaining the requirement.

If a transition has both gates, both icons appear and both warnings show in the confirmation dialog.

> **Note:** Gate indicators are informational. If the system can't load gate information (e.g., network issue), buttons appear without icons but transitions still work normally.

## Reviewing Workflow History

The **Workflow History Timeline** appears below the Workflow State Panel. It shows every state transition that has occurred on the document.

### Reading the Timeline

Each entry shows:
- **Previous state → New state** — the transition that occurred (with a directional arrow)
- **User** — who triggered the transition (display name or user ID)
- **Timestamp** — when it happened, in your local date/time format
- **Change reason** — why the transition was made (truncated to 120 characters with a "Show more" toggle for longer reasons)

Entries are listed newest-first (reverse chronological order).

### Expanding the Timeline

- By default, the timeline is collapsed
- When expanded, it shows the 5 most recent entries
- If more than 5 entries exist, a **Show all** button appears to expand the full list (up to 50 entries visible inline, scrollable beyond that)

### Empty History

If a document has just been created and no transitions have occurred yet, the timeline displays a message indicating no transitions have been recorded.

## Direct URL Access

You can link directly to a document's workflow view using the `?tab=workflow` query parameter:

```
http://localhost:3000/documents/{document-id}?tab=workflow
```

This will:
- Auto-expand both the Workflow State Panel and History Timeline
- Scroll the Workflow State Panel into view

This is useful for sharing links in review communications or audit discussions.

## Keyboard Navigation & Accessibility

The workflow execution components are fully accessible:

- **Tab** navigates through the state display, then transition buttons left-to-right
- **Enter/Space** activates buttons
- **Escape** closes the confirmation dialog without executing a transition
- Focus is trapped within the confirmation dialog while it's open
- Focus returns to the triggering button when the dialog closes
- Screen readers announce loading states and state changes via ARIA live regions
- All interactive elements have visible focus indicators

## Tips

- **Write meaningful change reasons** — these appear in the audit trail and may be reviewed during regulatory audits
- **Check gate icons before clicking** — if you see a lock icon, be prepared to provide an electronic signature after the transition
- **Use the history timeline** — it's your audit trail showing the complete lifecycle of the document
- **Bookmark workflow URLs** — use `?tab=workflow` links to quickly access a document's workflow state
- **High-risk workflows** — if you see an orange or red risk badge, transitions are subject to enhanced review requirements; take extra care with your change reasons
