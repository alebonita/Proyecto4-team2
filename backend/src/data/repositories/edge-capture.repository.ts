import { count, desc, eq } from 'drizzle-orm';

import { db } from '../db/client.js';
import { type EdgeCapture, edgeCaptures, type NewEdgeCapture } from '../db/schema.js';

/**
 * Busca una captura ya registrada por el `capture_id` que generó el dispositivo edge.
 *
 * AWS-1 usa esta consulta para que un reenvío del mismo evento sea idempotente, y
 * AWS-2 para consultar una sola captura.
 */
export async function findEdgeCaptureByCaptureId(captureId: string): Promise<EdgeCapture | null> {
  const rows = await db
    .select()
    .from(edgeCaptures)
    .where(eq(edgeCaptures.captureId, captureId))
    .limit(1);

  return rows[0] ?? null;
}

/**
 * Persiste el evento de una captura. Falla si el `capture_id` ya existe
 * (índice único), y la capa Logic resuelve ese choque.
 */
export async function createEdgeCaptureRow(capture: NewEdgeCapture): Promise<EdgeCapture> {
  const result = await db.insert(edgeCaptures).values(capture).$returningId();
  const created = result[0];

  if (!created) {
    throw new Error('No se pudo crear el registro de la captura.');
  }

  const rows = await db.select().from(edgeCaptures).where(eq(edgeCaptures.id, created.id)).limit(1);

  const row = rows[0];

  if (!row) {
    throw new Error('No se pudo recuperar el registro de la captura recién creado.');
  }

  return row;
}

export interface ListEdgeCapturesOptions {
  limit: number;
  offset: number;
}

/**
 * AWS-2 — consulta de una página de capturas, de la más reciente a la más antigua
 * por `captured_at`. El `id` desempata dos capturas con la misma fecha, para que la
 * paginación sea estable. Se exporta sin ejecutar para poder probar el orden.
 */
export function buildEdgeCaptureListQuery({ limit, offset }: ListEdgeCapturesOptions) {
  return db
    .select()
    .from(edgeCaptures)
    .orderBy(desc(edgeCaptures.capturedAt), desc(edgeCaptures.id))
    .limit(limit)
    .offset(offset);
}

export async function listEdgeCaptureRows(
  options: ListEdgeCapturesOptions,
): Promise<EdgeCapture[]> {
  return buildEdgeCaptureListQuery(options);
}

export async function countEdgeCaptures(): Promise<number> {
  const rows = await db.select({ total: count() }).from(edgeCaptures);
  return rows[0]?.total ?? 0;
}
