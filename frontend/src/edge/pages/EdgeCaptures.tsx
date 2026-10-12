import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { PageHeader } from "@/pipeline/components/PageHeader";
import { EDGE_CAPTURE_URL_TTL_MS, fetchEdgeCaptures, type LoadEdgeCaptures } from "../api";
import { EdgeCaptureCard } from "../components/EdgeCaptureCard";
import type { EdgeCapture } from "../types";

/**
 * Las URL de las fotos caducan a los 15 min; la página vuelve a pedir la lista un
 * minuto antes para que nunca se queden rotas en pantalla.
 */
export const AUTO_RENEW_MS = EDGE_CAPTURE_URL_TTL_MS - 60 * 1000;

/** Más reciente primero, por `captured_at`. No modifica el arreglo recibido. */
export function sortNewestFirst(captures: readonly EdgeCapture[]): EdgeCapture[] {
  return [...captures].sort(
    (a, b) => new Date(b.captured_at).getTime() - new Date(a.captured_at).getTime()
  );
}

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; captures: EdgeCapture[]; total: number };

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
        Cuando el dispositivo edge envíe su primera foto clasificada a AWS, aparecerá aquí. Usa
        «Actualizar» para volver a consultar.
      </p>
    </div>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error && error.message
    ? error.message
    : "Revisa tu conexión e inténtalo de nuevo.";
}

/**
 * POR-1/POR-2 — Sección «Capturas Edge» del portal (Proyecto 4).
 *
 * Galería de las capturas que el dispositivo edge clasificó y envió a AWS
 * (GET /edge-captures): foto, clase, confianza, fecha, ID de captura, dispositivo y
 * versión del modelo, de la más reciente a la más antigua.
 *
 * Cada foto es una URL firmada de S3 que caduca a los 15 minutos. «Actualizar» vuelve
 * a pedir la lista (y con ella URLs nuevas); además la página la renueva sola antes de
 * que caduquen, sin quitar las tarjetas de la pantalla mientras tanto.
 */
export function EdgeCapturesPage({
  load = fetchEdgeCaptures,
  autoRenewMs = AUTO_RENEW_MS,
}: Readonly<{ load?: LoadEdgeCaptures; autoRenewMs?: number }>) {
  const [state, setState] = useState<State>({ status: "loading" });
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);
  const [renewing, setRenewing] = useState(false);
  const [renewError, setRenewError] = useState<string | null>(null);
  const requestId = useRef(0);
  const controller = useRef<AbortController | null>(null);

  /**
   * `background`: renovar las URLs dejando las tarjetas visibles (renovación automática).
   * Sin `background` (botón, reintento y primera carga) se muestra el estado de carga.
   */
  const refresh = useCallback(
    async (background = false) => {
      const current = ++requestId.current;
      controller.current?.abort();
      controller.current = new AbortController();
      if (background) setRenewing(true);
      else setState({ status: "loading" });
      try {
        const { captures, total } = await load(controller.current.signal);
        if (current !== requestId.current) return;
        setState({ status: "ready", captures: sortNewestFirst(captures), total });
        setRefreshedAt(new Date());
        setRenewError(null);
      } catch (error) {
        if (current !== requestId.current) return;
        if (background) setRenewError(errorMessage(error));
        else setState({ status: "error", message: errorMessage(error) });
      } finally {
        if (current === requestId.current) setRenewing(false);
      }
    },
    [load]
  );

  useEffect(() => {
    void refresh();
    return () => controller.current?.abort();
  }, [refresh]);

  // Renueva las URL firmadas antes de que caduquen. Se reprograma en cada carga.
  useEffect(() => {
    if (state.status !== "ready" || state.captures.length === 0 || !refreshedAt) return;
    const timer = setTimeout(() => void refresh(true), autoRenewMs);
    return () => clearTimeout(timer);
  }, [state, refreshedAt, autoRenewMs, refresh]);

  const loading = state.status === "loading";
  const count = state.status === "ready" ? state.captures.length : null;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Capturas Edge"
        subtitle="Fotos clasificadas localmente por el dispositivo edge y enviadas a AWS, de la más reciente a la más antigua."
      >
        {refreshedAt && (
          <span className="text-xs text-ink-muted">
            {renewing
              ? "Renovando fotos…"
              : `Actualizado ${refreshedAt.toLocaleTimeString("es-MX")}`}
          </span>
        )}
        <Button
          variant="secondary"
          size="sm"
          onClick={() => void refresh()}
          isLoading={loading || renewing}
        >
          {!(loading || renewing) && <RefreshCw className="h-3.5 w-3.5" aria-hidden />}
          Actualizar
        </Button>
      </PageHeader>

      {renewError && state.status === "ready" && (
        <p
          role="alert"
          className="rounded-xl border border-status-pending/30 bg-status-pending-soft px-4 py-3 text-sm text-status-pending"
        >
          No se pudieron renovar las fotos ({renewError}). Las fotos caducan a los 15 minutos; usa
          «Actualizar» para volver a pedirlas.
        </p>
      )}

      {loading && <LoadingGrid />}

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
            {state.total > count
              ? `Las ${count} más recientes de ${state.total} capturas`
              : `${count} ${count === 1 ? "captura" : "capturas"}`}
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
