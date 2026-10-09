import { z } from 'zod';

/**
 * Clases que predice el modelo (class_map de dog-cat-resnet18: dog=0, cat=1).
 */
export const EDGE_MODEL_CLASSES = ['dog', 'cat'] as const;

/**
 * Prefijo de las fotos de Capturas Edge dentro del bucket (AWS-1).
 */
export const EDGE_CAPTURES_PREFIX = 'edge-captures/';

/**
 * Los campos llegan como texto en multipart/form-data. Sin el `min(1)`, un campo
 * vacío se convertiría en 0 y pasaría la validación.
 */
function numericField(name: string) {
  return z
    .string({ message: `${name} es obligatorio.` })
    .trim()
    .min(1, `${name} es obligatorio.`)
    .pipe(z.coerce.number({ message: `${name} debe ser un número.` }));
}

/**
 * `capture_id` lo genera el dispositivo edge y se usa como clave idempotente y como
 * nombre del objeto en S3, por eso solo admite caracteres seguros para una key.
 */
export const captureIdSchema = z
  .string({ message: 'capture_id es obligatorio.' })
  .trim()
  .regex(
    /^[A-Za-z0-9_-]{1,64}$/,
    'capture_id solo admite letras, números, guion y guion bajo (máximo 64).',
  );

/**
 * AWS-2 — recorte clasificado dentro de la foto, en píxeles: esquina superior
 * izquierda (`x`, `y`), `width` y `height`. Que quepa en la foto se comprueba en el
 * servicio, que es quien conoce sus dimensiones.
 */
export const edgeCaptureCropSchema = z
  .object({
    x: z.number({ message: 'crop.x debe ser un número.' }).min(0, 'crop.x no puede ser negativo.'),
    y: z.number({ message: 'crop.y debe ser un número.' }).min(0, 'crop.y no puede ser negativo.'),
    width: z
      .number({ message: 'crop.width debe ser un número.' })
      .positive('crop.width debe ser mayor que 0.'),
    height: z
      .number({ message: 'crop.height debe ser un número.' })
      .positive('crop.height debe ser mayor que 0.'),
  })
  .strict();

export type EdgeCaptureCrop = z.infer<typeof edgeCaptureCropSchema>;

/**
 * En multipart, `crop` llega como texto JSON: `{"x":10,"y":20,"width":100,"height":80}`.
 * Es opcional: sin el campo, o vacío, la captura no lleva recorte.
 */
const cropField = z.preprocess(
  (value) =>
    value === undefined || (typeof value === 'string' && value.trim() === '') ? undefined : value,
  z
    .string({ message: 'crop debe ser texto JSON.' })
    .transform((raw, ctx) => {
      try {
        return JSON.parse(raw) as unknown;
      } catch {
        ctx.addIssue({
          code: 'custom',
          message: 'crop debe ser JSON: {"x":…,"y":…,"width":…,"height":…}.',
        });
        return z.NEVER;
      }
    })
    .pipe(edgeCaptureCropSchema)
    .optional(),
);

/**
 * AWS-1 — campos del evento que envía el dispositivo edge (laptop) junto con la foto.
 */
export const edgeCaptureFieldsSchema = z.object({
  capture_id: captureIdSchema,
  captured_at: z.iso
    .datetime({
      offset: true,
      message: 'captured_at debe ser una fecha ISO 8601 con zona horaria.',
    })
    .transform((value) => new Date(value)),
  device_id: z
    .string({ message: 'device_id es obligatorio.' })
    .trim()
    .min(1, 'device_id es obligatorio.')
    .max(128),
  model_version: z
    .string({ message: 'model_version es obligatorio.' })
    .trim()
    .min(1, 'model_version es obligatorio.')
    .max(64),
  predicted_class: z.enum(EDGE_MODEL_CLASSES, {
    message: `predicted_class debe ser una de: ${EDGE_MODEL_CLASSES.join(', ')}.`,
  }),
  confidence: numericField('confidence').pipe(
    z
      .number()
      .min(0, 'confidence debe estar entre 0 y 1.')
      .max(1, 'confidence debe estar entre 0 y 1.'),
  ),
  latency_ms: numericField('latency_ms').pipe(
    z.number().min(0, 'latency_ms no puede ser negativo.'),
  ),
  crop: cropField,
});

export type EdgeCaptureFields = z.infer<typeof edgeCaptureFieldsSchema>;

/**
 * AWS-2 — paginación simple de GET /edge-captures (query params).
 */
export const edgeCaptureListQuerySchema = z.object({
  page: z.coerce
    .number({ message: 'page debe ser un número.' })
    .int('page debe ser entero.')
    .min(1, 'page debe ser 1 o mayor.')
    .default(1),
  pageSize: z.coerce
    .number({ message: 'pageSize debe ser un número.' })
    .int('pageSize debe ser entero.')
    .min(1, 'pageSize debe estar entre 1 y 100.')
    .max(100, 'pageSize debe estar entre 1 y 100.')
    .default(20),
});

export type EdgeCaptureListQuery = z.infer<typeof edgeCaptureListQuerySchema>;

/**
 * Key del objeto en S3. Es fija por `capture_id`: un reenvío apunta a la misma foto.
 */
export function buildEdgeCaptureKey(captureId: string): string {
  return `${EDGE_CAPTURES_PREFIX}${captureId}.jpg`;
}
