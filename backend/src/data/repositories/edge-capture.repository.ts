import { eq } from 'drizzle-orm';

import { db } from '../db/client.js';
import { type EdgeCapture, edgeCaptures, type NewEdgeCapture } from '../db/schema.js';

/**
 * Busca una captura ya registrada por el `capture_id` que generó el celular.
 *
 * AWS-1 usa esta consulta para que un reenvío del mismo evento sea idempotente.
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
