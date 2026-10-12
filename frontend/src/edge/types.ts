/**
 * POR-1/POR-2 — Forma de una captura de "Capturas Edge" tal como la devuelve
 * GET /edge-captures (AWS-2): los mismos campos que envía el dispositivo edge,
 * más `received_at`, `image_key` y una URL temporal `image_url` para ver la foto.
 *
 * Los nombres son los mismos del backend; `api.ts` valida la respuesta con zod
 * antes de mostrarla.
 */
export interface EdgeCaptureCrop {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface EdgeCapture {
  capture_id: string;
  /** Fecha de captura en el dispositivo, ISO 8601 con zona horaria. */
  captured_at: string;
  /** Fecha de recepción en AWS, ISO 8601. */
  received_at: string;
  device_id: string;
  /** Versión del artefacto optimizado que hizo la inferencia local. */
  model_version: string;
  predicted_class: string;
  /** Entre 0 y 1. */
  confidence: number;
  latency_ms: number;
  crop: EdgeCaptureCrop | null;
  image_key: string;
  image_url: string;
}
