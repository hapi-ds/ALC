/**
 * AgentsPage
 *
 * Main page for agent management. Integrates AgentList, AgentDetail,
 * and AgentForm components with a simple view-state machine:
 *
 *   list → detail (card click)
 *   list → create ("New Agent" button)
 *   detail → list (back)
 *   detail → edit (edit button)
 *   create → list (cancel / success)
 *   edit → detail (cancel / success)
 *
 * References:
 *   - Design doc Section 8: Frontend Components
 *   - Requirements 10.1, 10.2, 10.3, 10.4, 10.5
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { AgentList } from "@/components/agents/AgentList";
import { AgentDetail } from "@/components/agents/AgentDetail";
import { AgentForm } from "@/components/agents/AgentForm";
import type { AgentResponse } from "@/lib/agents-api";

// ---------------------------------------------------------------------------
// View state types
// ---------------------------------------------------------------------------

type ViewState =
  | { view: "list" }
  | { view: "detail"; agent: AgentResponse }
  | { view: "create" }
  | { view: "edit"; agent: AgentResponse };

// ---------------------------------------------------------------------------
// AgentsPage component
// ---------------------------------------------------------------------------

export function AgentsPage() {
  const [viewState, setViewState] = useState<ViewState>({ view: "list" });

  // Transition: list → detail (user clicks agent card)
  const handleSelect = (agent: AgentResponse) => {
    setViewState({ view: "detail", agent });
  };

  // Transition: list → create (user clicks "New Agent")
  const handleNewAgent = () => {
    setViewState({ view: "create" });
  };

  // Transition: detail → list (user clicks "Back")
  const handleBack = () => {
    setViewState({ view: "list" });
  };

  // Transition: detail → edit (user clicks "Edit")
  const handleEdit = () => {
    if (viewState.view === "detail") {
      setViewState({ view: "edit", agent: viewState.agent });
    }
  };

  // Transition: create → list (cancel or success)
  const handleCreateCancel = () => {
    setViewState({ view: "list" });
  };

  const handleCreateSuccess = () => {
    setViewState({ view: "list" });
  };

  // Transition: edit → detail (cancel or success)
  const handleEditCancel = () => {
    if (viewState.view === "edit") {
      setViewState({ view: "detail", agent: viewState.agent });
    }
  };

  const handleEditSuccess = (updatedAgent: AgentResponse) => {
    setViewState({ view: "detail", agent: updatedAgent });
  };

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">Agents</h2>
          <p className="text-sm text-muted-foreground">
            Manage AI agents for document generation and review
          </p>
        </div>
        {viewState.view === "list" && (
          <div className="flex gap-2">
            <Button onClick={handleNewAgent}>
              <Plus className="h-4 w-4 mr-2" aria-hidden="true" />
              New Agent
            </Button>
          </div>
        )}
      </div>

      {/* View content */}
      {viewState.view === "list" && <AgentList onSelect={handleSelect} />}

      {viewState.view === "detail" && (
        <AgentDetail
          agent={viewState.agent}
          onEdit={handleEdit}
          onBack={handleBack}
        />
      )}

      {viewState.view === "create" && (
        <AgentForm onSuccess={handleCreateSuccess} onCancel={handleCreateCancel} />
      )}

      {viewState.view === "edit" && (
        <AgentForm
          agent={viewState.agent}
          onSuccess={handleEditSuccess}
          onCancel={handleEditCancel}
        />
      )}
    </div>
  );
}
