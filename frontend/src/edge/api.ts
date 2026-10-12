import { z } from "zod";
import { getJson } from "@/api/client";
import type { EdgeCapture } from "./types";

/**
 * POR-2 — GET /edge-captures (AWS-2): las capturas que el dispositivo edge envió a
 * AWS, de la más reciente a la más antigua, cada una con una URL firmada de S3 para su
 * foto. Esa URL caduca a los 15 minutos (EDGE_CAPTURE_URL_TTL_SECONDS en el backend),
 * así que hay que volver a pedir la lista para tener URLs nuevas.
 */
export const EDGE_CAPTURE_URL_TTL_MS = 15 * 60 * 1000;

/** Máximo que acepta el backend por página. */
export const EDGE_CAPTURES_PAGE_SIZE = 100;

const cropSchema = z.object({
  x: z.number().int().nonnegative(),
  y: z.number().int().nonnegative(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
});

export const edgeCaptureSchema = z.object({
  capture_id: z.string().min(1),
  captured_at: z.string().min(1),
  received_at: z.string().min(1),
  device_id: z.string().min(1),
  model_version: z.string().min(1),
  predicted_class: z.string().min(1),
  confidence: z.number().min(0).max(1),
  latency_ms: z.number().nonnegative(),
  crop: cropSchema.nullable(),
  image_key: z.string().min(1),
  image_url: z.string().min(1),
}) satisfies z.ZodType<EdgeCapture>;

export const edgeCaptureListSchema = z.object({
  items: z.array(edgeCaptureSchema),
  page: z.number().int().positive(),
  pageSize: z.number().int().positive(),
  total: z.number().int().nonnegative(),
});

export interface EdgeCaptureList {
  captures: EdgeCapture[];
  /** Total de capturas en AWS (puede ser mayor que las que se muestran). */
  total: number;
}

export type LoadEdgeCaptures = (signal?: AbortSignal) => Promise<EdgeCaptureList>;

/** Primera página (las más recientes) con URLs de foto recién firmadas. */
export const fetchEdgeCaptures: LoadEdgeCaptures = async (signal) => {
  const data = await getJson(
    `/edge-captures?page=1&pageSize=${EDGE_CAPTURES_PAGE_SIZE}`,
    edgeCaptureListSchema,
    { signal }
  );
  return { captures: data.items, total: data.total };
};
