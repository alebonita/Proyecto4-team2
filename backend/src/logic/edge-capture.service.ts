import sharp from 'sharp';

import { env } from '../config/env.js';
import {
  createEdgeCaptureRow,
  type EdgeCapture,
  findEdgeCaptureByCaptureId,
  putEdgeCaptureObject,
} from '../data/index.js';
import { buildEdgeCaptureKey, edgeCaptureFieldsSchema } from './edge-capture.validation.js';
import { ValidationError } from './errors.js';

export interface EdgeCaptureImageInput {
  mimeType: string;
  sizeBytes: number;
  buffer: Buffer;
}

export interface SaveEdgeCaptureInput {
  image: EdgeCaptureImageInput;
  fields: unknown;
}

/**
 * Registro de una captura tal como lo devuelve la API: los mismos nombres de campo
 * que envía el celular, más `received_at` e `image_key`.
 */
export interface EdgeCaptureRecord {
  capture_id: string;
  captured_at: string;
  device_id: string;
  model_version: string;
  predicted_class: string;
  confidence: number;
  latency_ms: number;
  received_at: string;
  image_key: string;
}

export interface SaveEdgeCaptureResult {
  created: boolean;
  capture: EdgeCaptureRecord;
}

function toRecord(row: EdgeCapture): EdgeCaptureRecord {
  return {
    capture_id: row.captureId,
    captured_at: row.capturedAt.toISOString(),
    device_id: row.deviceId,
    model_version: row.modelVersion,
    predicted_class: row.predictedClass,
    confidence: row.confidence,
    latency_ms: row.latencyMs,
    received_at: row.receivedAt.toISOString(),
    image_key: row.imageKey,
  };
}

/**
 * Solo se aceptan fotos JPEG dentro del tamaño máximo. Sharp confirma que el
 * contenido sea realmente un JPEG, no solo que lo diga el tipo MIME.
 */
async function assertJpeg(image: EdgeCaptureImageInput): Promise<void> {
  if (image.mimeType !== 'image/jpeg') {
    throw new ValidationError('La foto debe ser JPEG (image/jpeg).');
  }

  if (image.sizeBytes <= 0 || image.sizeBytes > env.MAX_UPLOAD_SIZE_BYTES) {
    throw new ValidationError('La foto excede el tamaño máximo permitido.');
  }

  let format: string | undefined;
  try {
    format = (await sharp(image.buffer).metadata()).format;
  } catch {
    throw new ValidationError('El archivo no es una imagen válida.');
  }

  if (format !== 'jpeg') {
    throw new ValidationError('La foto debe ser JPEG (image/jpeg).');
  }
}

/**
 * AWS-1 — guarda una captura del celular: la foto en S3 (prefijo edge-captures/) y el
 * evento en MariaDB.
 *
 * Es idempotente por `capture_id`: si ya existe, no se crea otro registro ni otra
 * foto y se devuelve el registro existente.
 */
export async function saveEdgeCapture(input: SaveEdgeCaptureInput): Promise<SaveEdgeCaptureResult> {
  const parsed = edgeCaptureFieldsSchema.safeParse(input.fields);
  if (!parsed.success) {
    throw new ValidationError(
      `Captura inválida: ${parsed.error.issues
        .map((issue) => `${issue.path.join('.') || 'campos'}: ${issue.message}`)
        .join('; ')}`,
    );
  }
  const fields = parsed.data;
  await assertJpeg(input.image);

  // Reenvío después de que la primera petición terminó: no se toca S3.
  const existing = await findEdgeCaptureByCaptureId(fields.capture_id);
  if (existing) {
    return { created: false, capture: toRecord(existing) };
  }

  // La key es fija por capture_id y la escritura nunca sobrescribe. Si la foto ya
  // está (un intento anterior que falló al insertar, o una petición simultánea), se
  // conserva la que llegó primero. Por eso no se borra la foto si el INSERT falla:
  // un reintento la encuentra y solo completa el registro.
  const imageKey = buildEdgeCaptureKey(fields.capture_id);
  await putEdgeCaptureObject(imageKey, input.image.buffer);

  try {
    const row = await createEdgeCaptureRow({
      captureId: fields.capture_id,
      capturedAt: fields.captured_at,
      deviceId: fields.device_id,
      modelVersion: fields.model_version,
      predictedClass: fields.predicted_class,
      confidence: fields.confidence,
      latencyMs: fields.latency_ms,
      imageKey,
    });

    return { created: true, capture: toRecord(row) };
  } catch (error) {
    /*
     * Dos envíos del mismo capture_id pueden llegar a la vez:
     *
     * A: no existe -> sube la foto
     * B: no existe -> la foto ya está (412/409), no se reescribe
     * A: INSERT gana
     * B: INSERT choca con UNIQUE(capture_id)
     *
     * Después del choque se vuelve a consultar y se devuelve el registro ganador.
     */
    const winner = await findEdgeCaptureByCaptureId(fields.capture_id);

    if (winner) {
      return { created: false, capture: toRecord(winner) };
    }

    throw error;
  }
}
