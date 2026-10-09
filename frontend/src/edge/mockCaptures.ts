import type { EdgeCapture } from "./types";

/**
 * POR-1 — Datos de prueba de "Capturas Edge".
 *
 * Sirven para construir y revisar la sección antes de conectarla a
 * GET /edge-captures. No son capturas reales del dispositivo: la página lo
 * indica con un aviso visible. Las fotos son SVG en línea (sin red ni S3) y
 * las clases son las del modelo del Proyecto 3 (`dog-cat-resnet18`: cat, dog).
 *
 * El arreglo está desordenado a propósito: la página debe ordenarlo de la
 * captura más reciente a la más antigua.
 */

const PALETTE = {
  cat: { bg: "#EFECFD", fg: "#7C6FEA" },
  dog: { bg: "#E3F5EE", fg: "#2FAF87" },
} as const;

/** Placeholder 4:3 con la etiqueta de la clase, como data URI. */
function placeholder(label: "cat" | "dog", n: number): string {
  const { bg, fg } = PALETTE[label];
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480"><rect width="640" height="480" fill="${bg}"/><circle cx="320" cy="210" r="90" fill="${fg}" opacity="0.25"/><text x="320" y="225" font-family="sans-serif" font-size="56" font-weight="600" text-anchor="middle" fill="${fg}">${label}</text><text x="320" y="400" font-family="monospace" font-size="22" text-anchor="middle" fill="${fg}">foto de prueba #${n}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

const DEVICE = "laptop-edge-01";
const MODEL = "dog-cat-resnet18-1.0.0-int8";

function capture(
  n: number,
  id: string,
  capturedAt: string,
  receivedAt: string,
  label: "cat" | "dog",
  confidence: number,
  latencyMs: number,
  crop: EdgeCapture["crop"] = null
): EdgeCapture {
  return {
    capture_id: id,
    captured_at: capturedAt,
    received_at: receivedAt,
    device_id: DEVICE,
    model_version: MODEL,
    predicted_class: label,
    confidence,
    latency_ms: latencyMs,
    crop,
    image_key: `edge-captures/${DEVICE}/${id}.jpg`,
    image_url: placeholder(label, n),
  };
}

export const MOCK_EDGE_CAPTURES: readonly EdgeCapture[] = [
  capture(
    3,
    "demo-0003-7c1e",
    "2026-10-08T18:42:10-06:00",
    "2026-10-09T00:42:11.204Z",
    "dog",
    0.973,
    41.8
  ),
  capture(
    1,
    "demo-0001-a91f",
    "2026-10-08T18:40:02-06:00",
    "2026-10-09T00:40:03.551Z",
    "cat",
    0.912,
    44.2
  ),
  capture(
    6,
    "demo-0006-51bd",
    "2026-10-08T18:47:55-06:00",
    "2026-10-09T00:47:56.090Z",
    "cat",
    0.588,
    39.6,
    { x: 160, y: 120, width: 320, height: 240 }
  ),
  capture(
    2,
    "demo-0002-3d40",
    "2026-10-08T18:41:31-06:00",
    "2026-10-09T00:41:32.017Z",
    "dog",
    0.861,
    43.1
  ),
  capture(
    5,
    "demo-0005-e2a8",
    "2026-10-08T18:45:20-06:00",
    "2026-10-09T00:45:21.330Z",
    "dog",
    0.994,
    40.3
  ),
  capture(
    4,
    "demo-0004-b6f2",
    "2026-10-08T18:44:08-06:00",
    "2026-10-09T00:44:09.712Z",
    "cat",
    0.756,
    42.5
  ),
];
