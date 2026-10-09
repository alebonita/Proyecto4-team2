import { createHash, timingSafeEqual } from 'node:crypto';

import sharp, { type Metadata } from 'sharp';

import { env } from '../config/env.js';
import {
  countEdgeCaptures,
  createEdgeCaptureRow,
  type EdgeCapture,
  findEdgeCaptureByCaptureId,
  getEdgeCaptureImageUrl,
  listEdgeCaptureRows,
  putEdgeCaptureObject,
} from '../data/index.js';
import {
  buildEdgeCaptureKey,
  captureIdSchema,
  type EdgeCaptureCrop,
  edgeCaptureFieldsSchema,
  edgeCaptureListQuerySchema,
} from './edge-capture.validation.js';
import { NotFoundError, ValidationError } from './errors.js';

/**
 * Duración de las URL firmadas de las fotos (15 minutos).
 */
export const EDGE_CAPTURE_URL_TTL_SECONDS = 900;

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
 * que envía el dispositivo edge, más `received_at` e `image_key`.
 */
export interface EdgeCaptureRecord {
  capture_id: string;
  captured_at: string;
  received_at: string;
  device_id: string;
  model_version: string;
  predicted_class: string;
  confidence: number;
  latency_ms: number;
  crop: EdgeCaptureCrop | null;
  image_key: string;
}

/**
 * AWS-2 — captura con una URL temporal firmada para ver su foto desde S3.
 */
export interface EdgeCaptureView extends EdgeCaptureRecord {
  image_url: string;
}

export interface SaveEdgeCaptureResult {
  created: boolean;
  capture: EdgeCaptureRecord;
}

export interface ListEdgeCapturesResult {
  items: EdgeCaptureView[];
  page: number;
  pageSize: number;
  total: number;
}

function toCrop(row: EdgeCapture): EdgeCaptureCrop | null {
  if (
    row.cropX === null ||
    row.cropY === null ||
    row.cropWidth === null ||
    row.cropHeight === null
  ) {
    return null;
  }
  return { x: row.cropX, y: row.cropY, width: row.cropWidth, height: row.cropHeight };
}

function toRecord(row: EdgeCapture): EdgeCaptureRecord {
  return {
    capture_id: row.captureId,
    captured_at: row.capturedAt.toISOString(),
    received_at: row.receivedAt.toISOString(),
    device_id: row.deviceId,
    model_version: row.modelVersion,
    predicted_class: row.predictedClass,
    confidence: row.confidence,
    latency_ms: row.latencyMs,
    crop: toCrop(row),
    image_key: row.imageKey,
  };
}

async function toView(row: EdgeCapture): Promise<EdgeCaptureView> {
  return {
    ...toRecord(row),
    image_url: await getEdgeCaptureImageUrl(row.imageKey, EDGE_CAPTURE_URL_TTL_SECONDS),
  };
}

/**
 * Solo se aceptan fotos JPEG dentro del tamaño máximo. Sharp confirma que el
 * contenido sea realmente un JPEG, no solo que lo diga el tipo MIME, y da sus
 * dimensiones para validar el recorte.
 */
async function assertJpeg(
  image: EdgeCaptureImageInput,
): Promise<{ width: number; height: number }> {
  if (image.mimeType !== 'image/jpeg') {
    throw new ValidationError('La foto debe ser JPEG (image/jpeg).');
  }

  if (image.sizeBytes <= 0 || image.sizeBytes > env.MAX_UPLOAD_SIZE_BYTES) {
    throw new ValidationError('La foto excede el tamaño máximo permitido.');
  }

  let metadata: Metadata;
  try {
    metadata = await sharp(image.buffer).metadata();
  } catch {
    throw new ValidationError('El archivo no es una imagen válida.');
  }

  if (metadata.format !== 'jpeg' || !metadata.width || !metadata.height) {
    throw new ValidationError('La foto debe ser JPEG (image/jpeg).');
  }

  return { width: metadata.width, height: metadata.height };
}

/**
 * Copia del registro que se guarda como metadatos del objeto en S3 (AWS-2), para que
 * `aws s3api head-object` muestre la foto y su registro con permisos de solo lectura.
 */
function toObjectMetadata(record: Omit<EdgeCaptureRecord, 'image_key'>): Record<string, string> {
  const metadata: Record<string, string> = {
    'capture-id': record.capture_id,
    'captured-at': record.captured_at,
    'received-at': record.received_at,
    'device-id': record.device_id,
    'model-version': record.model_version,
    'predicted-class': record.predicted_class,
    confidence: String(record.confidence),
    'latency-ms': String(record.latency_ms),
  };
  if (record.crop) {
    metadata.crop = JSON.stringify(record.crop);
  }
  return metadata;
}

/**
 * AWS-2 — clave del dispositivo edge (`X-Device-Key`) contra `EDGE_DEVICE_KEY`.
 *
 * Compara los SHA-256 con `timingSafeEqual`: tarda lo mismo acierte o no y sin
 * importar el largo, así que el tiempo de respuesta no da pistas de la clave.
 */
export function checkEdgeDeviceKey(
  provided: string | undefined,
): 'ok' | 'not-configured' | 'rejected' {
  const expected = env.EDGE_DEVICE_KEY;
  if (expected === undefined) {
    return 'not-configured';
  }
  if (!provided) {
    return 'rejected';
  }
  const digest = (value: string) => createHash('sha256').update(value).digest();
  return timingSafeEqual(digest(provided), digest(expected)) ? 'ok' : 'rejected';
}

/**
 * AWS-1 — guarda una captura del dispositivo edge (laptop): la foto en S3 (prefijo
 * edge-captures/) y el evento en MariaDB.
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
  const size = await assertJpeg(input.image);

  // AWS-2: el recorte tiene que caber dentro de la foto.
  const crop = fields.crop ?? null;
  if (crop && (crop.x + crop.width > size.width || crop.y + crop.height > size.height)) {
    throw new ValidationError(
      `Captura inválida: crop: el recorte se sale de la foto (${size.width}x${size.height}).`,
    );
  }

  // Reenvío después de que la primera petición terminó: no se toca S3.
  const existing = await findEdgeCaptureByCaptureId(fields.capture_id);
  if (existing) {
    return { created: false, capture: toRecord(existing) };
  }

  // received_at se fija aquí (al segundo, como lo guarda MariaDB) para que el registro
  // y la copia en los metadatos de S3 digan lo mismo.
  const receivedAt = new Date(Math.floor(Date.now() / 1000) * 1000);

  // La key es fija por capture_id y la escritura nunca sobrescribe. Si la foto ya
  // está (un intento anterior que falló al insertar, o una petición simultánea), se
  // conserva la que llegó primero. Por eso no se borra la foto si el INSERT falla:
  // un reintento la encuentra y solo completa el registro.
  const imageKey = buildEdgeCaptureKey(fields.capture_id);
  await putEdgeCaptureObject(
    imageKey,
    input.image.buffer,
    toObjectMetadata({
      capture_id: fields.capture_id,
      captured_at: fields.captured_at.toISOString(),
      received_at: receivedAt.toISOString(),
      device_id: fields.device_id,
      model_version: fields.model_version,
      predicted_class: fields.predicted_class,
      confidence: fields.confidence,
      latency_ms: fields.latency_ms,
      crop,
    }),
  );

  try {
    const row = await createEdgeCaptureRow({
      captureId: fields.capture_id,
      capturedAt: fields.captured_at,
      deviceId: fields.device_id,
      modelVersion: fields.model_version,
      predictedClass: fields.predicted_class,
      confidence: fields.confidence,
      latencyMs: fields.latency_ms,
      cropX: crop?.x ?? null,
      cropY: crop?.y ?? null,
      cropWidth: crop?.width ?? null,
      cropHeight: crop?.height ?? null,
      imageKey,
      receivedAt,
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

/**
 * AWS-2 — capturas de la más reciente a la más antigua por `captured_at`, con
 * paginación simple y una URL firmada por foto.
 */
export async function listEdgeCaptures(query: unknown): Promise<ListEdgeCapturesResult> {
  const parsed = edgeCaptureListQuerySchema.safeParse(query);
  if (!parsed.success) {
    throw new ValidationError(parsed.error.issues[0]?.message ?? 'Paginación inválida.');
  }
  const { page, pageSize } = parsed.data;

  const [rows, total] = await Promise.all([
    listEdgeCaptureRows({ limit: pageSize, offset: (page - 1) * pageSize }),
    countEdgeCaptures(),
  ]);

  return { items: await Promise.all(rows.map(toView)), page, pageSize, total };
}

/**
 * AWS-2 — una sola captura por su `capture_id`, con la URL firmada de su foto.
 */
export async function getEdgeCapture(captureId: unknown): Promise<EdgeCaptureView> {
  const parsed = captureIdSchema.safeParse(captureId);
  if (!parsed.success) {
    throw new ValidationError(parsed.error.issues[0]?.message ?? 'capture_id inválido.');
  }

  const row = await findEdgeCaptureByCaptureId(parsed.data);
  if (!row) {
    throw new NotFoundError('Captura no encontrada.');
  }

  return toView(row);
}
