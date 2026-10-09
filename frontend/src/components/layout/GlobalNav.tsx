import {
  Bot,
  Boxes,
  Camera,
  ChartScatter,
  ClipboardCheck,
  Dumbbell,
  FlaskConical,
  Gauge,
  History,
  LayoutDashboard,
  ScanSearch,
  Search,
  Settings as SettingsIcon,
  SplitSquareHorizontal,
  Upload,
  Zap,
} from "lucide-react";
import type { ComponentType, ReactNode, SVGProps } from "react";
import { NavLink } from "react-router-dom";

interface NavItem {
  label: string;
  to: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}

const ANNOTATION_NAV_ITEMS: NavItem[] = [
  { label: "Tablero", to: "/dashboard", icon: LayoutDashboard },
  { label: "Buscar", to: "/search", icon: Search },
  { label: "Subir fotografías", to: "/upload", icon: Upload },
];

const PIPELINE_NAV_ITEMS: NavItem[] = [
  { label: "Overview", to: "/pipeline/overview", icon: Gauge },
  { label: "Analyzers", to: "/pipeline/analyzers", icon: ScanSearch },
  { label: "Splits", to: "/pipeline/splits", icon: SplitSquareHorizontal },
  { label: "Versions", to: "/pipeline/versions", icon: History },
  { label: "PCA / t-SNE", to: "/pipeline/projections", icon: ChartScatter },
  { label: "Copilot", to: "/pipeline/copilot", icon: Bot },
  { label: "Settings", to: "/pipeline/settings", icon: SettingsIcon },
];

const ML_NAV_ITEMS: NavItem[] = [
  { label: "Training", to: "/ml/training", icon: Dumbbell },
  { label: "Experiments", to: "/ml/experiments", icon: FlaskConical },
  { label: "Evaluation", to: "/ml/evaluation", icon: ClipboardCheck },
  { label: "Models", to: "/ml/models", icon: Boxes },
  { label: "Inference", to: "/ml/inference", icon: Zap },
];

/** POR-1 (Proyecto 4): capturas que clasifica el dispositivo edge y llegan a AWS. */
const EDGE_NAV_ITEMS: NavItem[] = [{ label: "Capturas Edge", to: "/edge/captures", icon: Camera }];

function NavLinkList({ items }: { items: NavItem[] }) {
  return (
    <>
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-accent-lilac-soft text-accent-lilac"
                  : "text-ink-muted hover:bg-surface hover:text-ink"
              }`
            }
          >
            <Icon className="h-4 w-4 shrink-0" aria-hidden />
            <span className="whitespace-nowrap">{item.label}</span>
          </NavLink>
        );
      })}
    </>
  );
}

/**
 * Navegación global de la app: única fuente de verdad para el sidebar/header
 * de las pantallas del portal (anotación + pipeline de calidad de
 * datasets + modelos, APP-01). Un solo portal, un solo menú — las 6 pantallas del pipeline no
 * abren ni existen como una app/nav separada (antes vivían en su propio
 * `PipelineNav`; ver historial de `PipelineLayout.tsx`, eliminado).
 * Annotate (pantalla de anotación) NO usa este nav a propósito — es un modo
 * de enfoque de pantalla completa, con su propio botón "Volver" hacia la
 * pantalla de origen (mismo patrón que Figma/Canva al editar).
 *
 * `children` es contenido específico de la pantalla (p. ej. los filtros de
 * Búsqueda) que se renderiza dentro de este mismo sidebar, debajo del nav,
 * en vez de vivir en un segundo `<aside>` aparte.
 */
export function GlobalNav({ children }: { children?: ReactNode }) {
  return (
    <aside className="flex w-full shrink-0 flex-col border-b border-border bg-sidebar lg:h-screen lg:w-64 lg:overflow-y-auto lg:border-b-0 lg:border-r">
      <div className="flex items-center gap-2 px-5 py-5">
        <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-accent-lilac" aria-hidden />
        <span className="truncate text-sm font-semibold text-ink">Portal de Anotación</span>
      </div>

      <nav className="flex flex-wrap gap-1 overflow-x-auto px-3 pb-3 lg:flex-col lg:overflow-visible lg:px-3 lg:pb-6">
        <NavLinkList items={ANNOTATION_NAV_ITEMS} />
        <div className="my-2 h-px w-full shrink-0 bg-border lg:my-2" aria-hidden />
        <NavLinkList items={PIPELINE_NAV_ITEMS} />
        <div className="my-2 h-px w-full shrink-0 bg-border lg:my-2" aria-hidden />
        <NavLinkList items={ML_NAV_ITEMS} />
        <div className="my-2 h-px w-full shrink-0 bg-border lg:my-2" aria-hidden />
        <NavLinkList items={EDGE_NAV_ITEMS} />
      </nav>

      {children && <div className="border-t border-border px-5 py-5">{children}</div>}
    </aside>
  );
}
