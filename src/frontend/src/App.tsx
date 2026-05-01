import { Routes, Route } from "react-router-dom";
import { MainLayout } from "@/components/layout";
import { DocumentsPage } from "@/pages/DocumentsPage";
import { VirtualFoldersPage } from "@/pages/VirtualFoldersPage";
import { TemplatesPage } from "@/pages/TemplatesPage";
import { WorkflowsPage } from "@/pages/WorkflowsPage";
import { TrainingPage } from "@/pages/TrainingPage";
import { SearchPage } from "@/pages/SearchPage";
import { KnowledgePage } from "@/pages/KnowledgePage";
import { AgentsPage } from "@/pages/AgentsPage";
import { ValidationPage } from "@/pages/ValidationPage";
import { SignaturesPage } from "@/pages/SignaturesPage";
import { ReviewPage } from "@/pages/ReviewPage";
import { AdminPage } from "@/pages/AdminPage";

function App() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route index element={<DocumentsPage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="folders" element={<VirtualFoldersPage />} />
        <Route path="templates" element={<TemplatesPage />} />
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

export default App;
