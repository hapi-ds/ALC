# Workflow Editor User Guide

This guide explains how to use the BPMN Workflow Visual Editor to design document lifecycle workflows, enforce signature requirements, and configure training triggers.

## Overview

The Workflow Editor lets you visually design the lifecycle of a document type (e.g., SOP, Protocol, Report). Each workflow defines:

- **States** — the stages a document passes through (Draft, Review, Approved, etc.)
- **Transitions** — the allowed paths between states
- **Signature requirements** — which transitions require a PAdES digital signature
- **Training triggers** — which transitions trigger training assignments for affected staff
- **Risk level** — determines how strict the review path is

## Getting Started

1. Navigate to **Workflows** in the sidebar
2. Click **New Workflow** to create a new workflow, or click an existing row to edit

## Designing a Workflow

### The BPMN Canvas

The editor provides a visual canvas with a restricted palette:

| Element | Purpose |
|---------|---------|
| **Start Event** (circle) | Entry point — where documents begin their lifecycle |
| **End Event** (bold circle) | Terminal state — documents reaching this are complete |
| **Task** (rounded rectangle) | A workflow state (e.g., "Draft", "CTO Review", "Approved") |
| **Sequence Flow** (arrow) | A transition between states |

### Building a Workflow Step by Step

1. **Add states**: Drag "Task" elements from the palette onto the canvas. Name each one by double-clicking (e.g., "Draft", "QA Review", "CTO Approval", "Approved", "Effective").

2. **Connect states**: Use the connect tool (or hover over an element's edge) to draw arrows between tasks. These arrows define which transitions are allowed.

3. **Connect start/end**: Draw an arrow from the Start Event to your first state (e.g., "Draft"). Draw arrows from terminal states to the End Event.

### Example: SOP Lifecycle with CTO Signature

```
Start → Draft → QA Review → CTO Approval → Approved → Effective → End
```

## Setting Workflow Metadata

In the right sidebar, fill in:

| Field | Description |
|-------|-------------|
| **Workflow Name** | Human-readable name (e.g., "SOP Lifecycle") |
| **Document Tag** | Binds this workflow to a document type (e.g., "SOP"). One workflow per tag. |
| **Risk Level** | low / medium / high / critical — affects review strictness |

## Enforcing Signatures on Transitions

This is how you require a specific role (e.g., CTO) to digitally sign before a document can advance.

### How It Works

1. **Design the transition** in the BPMN diagram. For example, create a task called "CTO Approval" and connect it to "Approved".

2. **Mark the transition as signature-required** in the **Transition Configuration** panel (right sidebar). You'll see a list of all transitions extracted from your diagram. Check the **Signature** checkbox next to the transition you want to enforce.

   Example: Check "Signature" on `CTO Approval→Approved`

3. **Save** the workflow.

### What Happens at Runtime

When a document reaches the "CTO Approval" state and someone attempts to transition it to "Approved":

- The system requires a **PAdES digital signature** before the transition is allowed
- The user must re-authenticate and provide their electronic signature
- The signature is cryptographically bound to the document version
- An audit trail records who signed, when, and the document hash

### Enforcing Role-Based Signatures

The signature requirement ensures *someone* must sign — but to enforce that specifically the **CTO** must sign, you design your workflow states to reflect organizational roles:

**Pattern: Role-specific approval states**

```
Draft → QA Review → CTO Approval → Approved → Effective
```

- Only users with the CTO role should have permission to transition documents *out of* the "CTO Approval" state
- Combined with the signature requirement on `CTO Approval→Approved`, this ensures the CTO must personally sign

**Pattern: Sequential multi-role approval**

```
Draft → Author Review → QA Review → CTO Approval → Regulatory Approval → Effective
```

Mark signatures on:
- `QA Review→CTO Approval` (QA signs off)
- `CTO Approval→Regulatory Approval` (CTO signs off)
- `Regulatory Approval→Effective` (Regulatory signs off)

## Configuring Training Triggers

When a document is approved and becomes effective, staff who work with that document type may need training on the new version.

### How to Set Up

1. In the **Transition Configuration** panel, check the **Training** checkbox next to the transition that should trigger training.

   Example: Check "Training" on `Approved→Effective`

2. Save the workflow.

### What Happens at Runtime

When a document transitions through a training-trigger transition:
- The system creates training tasks for all users assigned to that document type
- Training records track completion status
- Documents cannot be used in production until affected staff complete training

## Risk Levels

| Level | Meaning | Recommendation |
|-------|---------|----------------|
| **Low** | Standard documents with minimal compliance impact | Single review state is sufficient |
| **Medium** | Documents with moderate compliance impact | At least one review state |
| **High** | Documents with significant compliance impact | At least two sequential review states before approval |
| **Critical** | Documents with maximum compliance impact (e.g., batch records) | Multiple review states with signatures at each transition |

When you set risk level to "high" or "critical", the editor displays a warning and recommends at least two sequential review states before approval.

## Version History

Every time you save structural changes (diagram modifications, transition configuration changes), a new version is automatically created.

- View version history in the **Version History** panel (bottom of right sidebar)
- Click a version to preview it in read-only mode
- Click **Restore** to revert to a previous version (creates a new version with the old content)

Metadata-only changes (name, risk level) do not create new versions.

## Auto-Assignment Configuration (Future)

The Auto-Assignment Configuration panel accepts JSON rules for AI-driven reviewer suggestions. This feature will be activated when the Agent Registry (Phase 5.1) is integrated. You can pre-configure rules now.

## Validation

Click **Validate** to check your workflow for structural issues:

- Missing Start Event
- Missing End Event
- No Task elements
- Unreachable states (states not connected to the main flow)
- Invalid signature transition references

Fix any reported errors before saving.

## Tips

- **Name your tasks clearly** — task names become the state names shown to users throughout the system
- **Keep workflows linear for high-risk documents** — branching adds complexity and audit risk
- **Use the risk level** — it signals to reviewers how carefully they should evaluate documents
- **Validate before saving** — catches structural issues early
- **Check the version history** — you can always restore a previous version if something goes wrong
