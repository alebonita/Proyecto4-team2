import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageHeader } from "@/pipeline/components/PageHeader";
import { EdgeCaptureCard } from "../components/EdgeCaptureCard";
import { MOCK_EDGE_CAPTURES } from "../mockCaptures";
import type { EdgeCapture } from "../types";

export type LoadEdgeCaptures = () => Promise<readonly EdgeCapture[]>;

/** POR-1: por ahora la sección muestra datos de prueba, sin llamar a la API. */
export const loadMockEdgeCaptures: LoadEdgeCaptures = () => Promise.resolve(MOCK_EDGE_CAPTURES);

/** Más reciente primero, por `captured_at`. No modifica el arreglo recibido. */
export function sortNewestFirst(captures: readonly EdgeCapture[]): EdgeCapture[] {
  return [...captures].sort(
    (a, b) => new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime()
  );
}

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; captures: EdgeCapture[] };

function LoadingGrid() {
  return (
    <div
      role="status"
      aria-label="Cargando capturas"
      className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
    >
      {[0, 1, 2].map((key) => (
        <div key={key} className="overflow-hidden rounded-2xl border border-border bg-surface">
          <Skeleton className="aspect-[4/3] rounded-none" />
          <div className="space-y-2 p-4">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyCaptures() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-border-strong bg-surface px-6 py-16 text-center">
      <p className="text-sm font-medium text-ink">Todavía no hay capturas</p>
      <p className="max-w-sm text-sm text-ink-muted">
        Cuando el dispositivo edge envíe su primera foto clasificada, aparecerá aquí. Usa
        «Actualizar» para volver a consultar.
      </p>
    </div>
  );
}

/**
 * POR-1 — Sección «Capturas Edge» del portal (Proyecto 4).
 *
 * Galería de las fotos que clasifica el dispositivo edge: foto, clase,
 * confianza, fecha, ID de captura, dispositivo y versión del modelo, de la más
 * reciente a la más antigua. Hoy usa datos de prueba (`mockCaptures.ts`);
 * `load` permite cambiarlos por GET /edge-captures sin tocar la página.
 */
export function EdgeCapturesPage({
  load = loadMockEdgeCaptures,
  isMock = load === loadMockEdgeCaptures,
}: Readonly<{ load?: LoadEdgeCaptures; isMock?: boolean }>) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const requestId = useRef(0);

  const refresh = useCallback(async () => {
    const current = ++requestId.current;
    setState({ status: "loading" });
    try {
      const captures = sortNewestFirst(await load());
      if (current !== requestId.current) return;
      setState({ status: "ready", captures });
      setRefreshedAt(new Date());
    } catch (error) {
      if (current !== requestId.current) return;
      setState({
        status: "error",
        message:
          error instanceof Error && error.message
            ? error.message
            : "Revisa tu conexión e inténtalo de nuevo.",
      });
    }
  }, [load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const count = state.status === "ready" ? state.captures.length : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Capturas Edge"
        subtitle="Fotos clasificadas localmente por el dispositivo edge y enviadas a AWS, de la más reciente a la más antigua."
      >
        {refreshedAt && (
          <span className="text-xs text-ink-muted">
            Actualizado {refreshedAt.toLocaleTimeString("es-MX")}
          </span>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void refresh()}
          isLoading={state.status === "loading"}
        >
          {state.status !== "loading" && <RefreshCw className="h-3.5 w-3.5" aria-hidden />}
          Actualizar
        </Button>
      </PageHeader>

      {isMock && (
        <p
          role="note"
          className="rounded-xl border border-status-pending/30 bg-status-pending-soft px-4 py-3 text-sm text-status-pending"
        >
          <strong className="font-semibold">Datos de prueba.</strong> Estas tarjetas no vienen del
          dispositivo ni de AWS; la sección se conectará a las capturas reales en el siguiente paso.
        </p>
      )}

      {state.status === "loading" && <LoadingGrid />}

      {state.status === "error" && (
        <ErrorState
          title="No se pudieron cargar las capturas."
          message={state.message}
          onRetry={() => void refresh()}
        />
      )}

      {state.status === "ready" && count === 0 && <EmptyCaptures />}

      {state.status === "ready" && count !== null && count > 0 && (
        <section aria-label="Capturas" className="space-y-3">
          <p className="text-sm text-ink-muted">
            {count} {count === 1 ? "captura" : "capturas"}
          </p>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {state.captures.map((capture) => (
              <EdgeCaptureCard key={capture.capture_id} capture={capture} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
