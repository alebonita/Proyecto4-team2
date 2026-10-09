import { Navigate, Route, Routes } from "react-router-dom";
import { AnnotateScreen } from "@/components/annotate/AnnotateScreen";
import { AppLayout } from "@/components/layout/AppLayout";
import { UploadScreen } from "@/components/upload/UploadScreen";
import { EdgeCapturesPage } from "@/edge/pages/EdgeCaptures";
import { EvaluationPage } from "@/ml/pages/Evaluation";
import { ExperimentsPage } from "@/ml/pages/Experiments";
import { InferencePage } from "@/ml/pages/Inference";
import { ModelsPage } from "@/ml/pages/Models";
import { TrainingPage } from "@/ml/pages/Training";
import { DashboardPage } from "@/pages/Dashboard";
import { SearchPage } from "@/pages/SearchPage";
import { AnalyzersPage } from "@/pipeline/pages/Analyzers";
import { CopilotPage } from "@/pipeline/pages/Copilot";
import { OverviewPage } from "@/pipeline/pages/Overview";
import { ProjectionsPage } from "@/pipeline/pages/Projections";
import { SettingsPage } from "@/pipeline/pages/Settings";
import { SplitsPage } from "@/pipeline/pages/Splits";
import { VersionsPage } from "@/pipeline/pages/Versions";

export function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route
        path="/dashboard"
        element={
          <AppLayout>
            <DashboardPage />
          </AppLayout>
        }
      />
      {/* SearchPage se envuelve con AppLayout internamente (no aquí), porque
          necesita pasarle su propio contenido de filtros como sidebarExtra
          — ver SearchPage.tsx. */}
      <Route path="/search" element={<SearchPage />} />
      <Route
        path="/upload"
        element={
          <AppLayout>
            <UploadScreen />
          </AppLayout>
        }
      />
      {/* Annotate es un modo de enfoque de pantalla completa a propósito: sin
          nav global, con su propio botón "Volver". Ver GlobalNav.tsx. */}
      <Route path="/annotate/:imageId" element={<AnnotateScreen />} />

      {/* P2-14: dashboard de calidad de dataset (Frente 7) — mismo portal,
          mismo AppLayout/GlobalNav que el resto; no tiene nav ni shell
          propio (ver GlobalNav.tsx). */}
      <Route path="/pipeline" element={<Navigate to="/pipeline/overview" replace />} />
      <Route
        path="/pipeline/overview"
        element={
          <AppLayout>
            <OverviewPage />
          </AppLayout>
        }
      />
      <Route
        path="/pipeline/analyzers"
        element={
          <AppLayout>
            <AnalyzersPage />
          </AppLayout>
        }
      />
      <Route
        path="/pipeline/splits"
        element={
          <AppLayout>
            <SplitsPage />
          </AppLayout>
        }
      />
      <Route
        path="/pipeline/versions"
        element={
          <AppLayout>
            <VersionsPage />
          </AppLayout>
        }
      />
      <Route
        path="/pipeline/copilot"
        element={
          <AppLayout>
            <CopilotPage />
          </AppLayout>
        }
      />
      <Route
        path="/pipeline/settings"
        element={
          <AppLayout>
            <SettingsPage />
          </AppLayout>
        }
      />

      <Route
        path="/pipeline/projections"
        element={
          <AppLayout>
            <ProjectionsPage />
          </AppLayout>
        }
      />

      {/* APP-01: pantallas de modelos — mismo portal y mismo AppLayout/GlobalNav. */}
      <Route path="/ml" element={<Navigate to="/ml/training" replace />} />
      <Route
        path="/ml/training"
        element={
          <AppLayout>
            <TrainingPage />
          </AppLayout>
        }
      />
      <Route
        path="/ml/experiments"
        element={
          <AppLayout>
            <ExperimentsPage />
          </AppLayout>
        }
      />
      <Route
        path="/ml/evaluation"
        element={
          <AppLayout>
            <EvaluationPage />
          </AppLayout>
        }
      />
      <Route
        path="/ml/models"
        element={
          <AppLayout>
            <ModelsPage />
          </AppLayout>
        }
      />
      <Route
        path="/ml/inference"
        element={
          <AppLayout>
            <InferencePage />
          </AppLayout>
        }
      />

      {/* POR-1 (Proyecto 4): Capturas Edge — mismo portal y mismo AppLayout/GlobalNav. */}
      <Route path="/edge" element={<Navigate to="/edge/captures" replace />} />
      <Route
        path="/edge/captures"
        element={
          <AppLayout>
            <EdgeCapturesPage />
          </AppLayout>
        }
      />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
