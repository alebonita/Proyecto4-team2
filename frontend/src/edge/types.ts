/**
 * POR-1 — Forma de una captura de "Capturas Edge" tal como la devuelve
 * GET /edge-captures (AWS-2): los mismos campos que envía el dispositivo edge,
 * más `received_at`, `image_key` y una URL temporal `image_url` para ver la foto.
 *
 * Mantener los nombres iguales al backend permite cambiar los datos de prueba
 * por la API real sin tocar las tarjetas.
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
