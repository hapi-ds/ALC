import { useEffect } from "react";
import { Routes, Route } from "react-router-dom";
import { MainLayout } from "@/components/layout";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { VirtualFoldersPage } from "@/pages/VirtualFoldersPage";
import { TemplateListPage } from "@/pages/TemplateListPage";
import { TemplateBuilderPage } from "@/pages/TemplateBuilderPage";
import { TemplateDetailPage } from "@/pages/TemplateDetailPage";
import { WorkflowsPage } from "@/pages/WorkflowsPage";
import { TrainingPage } from "@/pages/TrainingPage";
import { SearchPage } from "@/pages/SearchPage";
import { KnowledgePage } from "@/pages/KnowledgePage";
import { AgentsPage } from "@/pages/AgentsPage";
import { ValidationPage } from "@/pages/ValidationPage";
import { SignaturesPage } from "@/pages/SignaturesPage";
import { ReviewPage } from "@/pages/ReviewPage";
import { AdminPage } from "@/pages/AdminPage";
import { ReportListPage } from "@/pages/ReportListPage";
import { ReportDataEntryPage } from "@/pages/ReportDataEntryPage";
import { ReportDetailPage } from "@/pages/ReportDetailPage";
import { ComparisonViewPage } from "@/pages/ComparisonViewPage";
import { LoginPage } from "@/pages/LoginPage";
import { RouteGuard } from "@/components/auth/RouteGuard";
import { useAuthStore } from "@/stores/authStore";
import { useSessionTimer } from "@/hooks/useSessionTimer";

/**
 * Wrapper component rendered inside RouteGuard that activates
 * the session timer (inactivity + token expiry monitoring) and
 * renders the protected route tree.
 */
function AuthenticatedApp() {
  useSessionTimer();

  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route index element={<DocumentsPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="folders" element={<VirtualFoldersPage />} />
        <Route path="folders/:folderId" element={<VirtualFoldersPage />} />
        <Route path="templates" element={<TemplateListPage />} />
        <Route path="templates/new" element={<TemplateBuilderPage />} />
        <Route path="templates/:uuid" element={<TemplateDetailPage />} />
        <Route path="reports" element={<ReportListPage />} />
        <Route path="reports/new" element={<ReportDataEntryPage />} />
        <Route path="reports/new/:documentUuid" element={<ReportDataEntryPage />} />
        <Route path="reports/:reportId/compare" element={<ComparisonViewPage />} />
        <Route path="reports/:reportId" element={<ReportDetailPage />} />
        <Route path="workflows" element={<WorkflowsPage />} />
        <Route path="training" element={<TrainingPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="knowledge" element={<KnowledgePage />} />
        <Route path="agents" element={<AgentsPage />} />
        <Route path="validation" element={<ValidationPage />} />
        <Route path="signatures" element={<SignaturesPage />} />
        <Route path="review" element={<ReviewPage />} />
        <Route path="admin" element={<AdminPage />} />
      </Route>
    </Routes>
  );
}

function App() {
  const initialize = useAuthStore((state) => state.initialize);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />

      {/* Protected routes */}
      <Route
        path="/*"
        element={
          <RouteGuard>
            <AuthenticatedApp />
          </RouteGuard>
        }
      />
    </Routes>
  );
}

export default App;
