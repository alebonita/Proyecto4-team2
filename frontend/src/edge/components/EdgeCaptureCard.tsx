import { useState } from "react";
import type { EdgeCapture } from "../types";

const DATE_FORMAT = new Intl.DateTimeFormat("es-MX", {
  dateStyle: "medium",
  timeStyle: "medium",
});

export function formatCaptureDate(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : DATE_FORMAT.format(date);
}

export function formatConfidence(confidence: number): string {
  return `${(confidence * 100).toFixed(1)} %`;
}

/** Confianza baja (< 0.6) en ámbar: el evaluador ve rápido qué predicción dudar. */
function confidenceTone(confidence: number): string {
  if (confidence >= 0.85) return "bg-status-done-soft text-status-done";
  if (confidence >= 0.6) return "bg-status-progress-soft text-status-progress";
  return "bg-status-pending-soft text-status-pending";
}

function Field({
  label,
  value,
  mono = false,
}: Readonly<{ label: string; value: string; mono?: boolean }>) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-ink-faint">{label}</dt>
      <dd className={`break-all text-xs text-ink ${mono ? "font-mono" : ""}`} title={value}>
        {value}
      </dd>
    </div>
  );
}

/**
 * Recuadro de la región clasificada sobre la foto. Usa el tamaño natural de la
 * imagen para convertir los píxeles del `crop` a porcentajes.
 */
function CropOverlay({
  crop,
  size,
}: Readonly<{ crop: NonNullable<EdgeCapture["crop"]>; size: { w: number; h: number } }>) {
  const style = {
    left: `${(crop.x / size.w) * 100}%`,
    top: `${(crop.y / size.h) * 100}%`,
    width: `${(crop.width / size.w) * 100}%`,
    height: `${(crop.height / size.h) * 100}%`,
  };
  return (
    <div
      data-testid="crop-overlay"
      className="pointer-events-none absolute rounded border-2 border-accent-lilac"
      style={style}
      aria-hidden
    />
  );
}

export function EdgeCaptureCard({ capture }: Readonly<{ capture: EdgeCapture }>) {
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const capturedLabel = formatCaptureDate(capture.captured_at);

  return (
    <article
      aria-label={`Captura ${capture.capture_id}`}
      className="flex flex-col overflow-hidden rounded-2xl border border-border bg-surface shadow-card"
    >
      <div className="relative aspect-[4/3] bg-sidebar">
        <img
          src={capture.image_url}
          alt={`Foto de la captura ${capture.capture_id}, clasificada como ${capture.predicted_class}`}
          className="h-full w-full object-cover"
          loading="lazy"
          onLoad={(event) => {
            const img = event.currentTarget;
            if (img.naturalWidth && img.naturalHeight) {
              setSize({ w: img.naturalWidth, h: img.naturalHeight });
            }
          }}
        />
        {capture.crop && size && <CropOverlay crop={capture.crop} size={size} />}
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-base font-semibold capitalize text-ink">
            {capture.predicted_class}
          </span>
          <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${confidenceTone(capture.confidence)}`}
          >
            {formatConfidence(capture.confidence)}
          </span>
        </div>

        <dl className="grid grid-cols-2 gap-x-3 gap-y-2">
          <Field label="ID de captura" value={capture.capture_id} mono />
          <div className="min-w-0">
            <dt className="text-[11px] uppercase tracking-wide text-ink-faint">Capturada</dt>
            <dd className="truncate text-xs text-ink">
              <time dateTime={capture.captured_at} title={capture.captured_at}>
                {capturedLabel}
              </time>
            </dd>
          </div>
          <Field label="Dispositivo" value={capture.device_id} mono />
          <Field label="Versión del modelo" value={capture.model_version} mono />
          <Field label="Latencia local" value={`${capture.latency_ms.toFixed(1)} ms`} />
          <Field
            label="Recorte"
            value={
              capture.crop
                ? `${capture.crop.width}×${capture.crop.height} en (${capture.crop.x}, ${capture.crop.y})`
                : "Imagen completa"
            }
          />
        </dl>
      </div>
    </article>
  );
}
