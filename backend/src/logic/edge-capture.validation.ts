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
 * AWS-1 — campos del evento que envía el celular junto con la foto.
 *
 * `capture_id` lo genera el celular y se usa como clave idempotente y como nombre
 * del objeto en S3, por eso solo admite caracteres seguros para una key.
 */
export const edgeCaptureFieldsSchema = z.object({
  capture_id: z
    .string({ message: 'capture_id es obligatorio.' })
    .trim()
    .regex(
      /^[A-Za-z0-9_-]{1,64}$/,
      'capture_id solo admite letras, números, guion y guion bajo (máximo 64).',
    ),
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
});

export type EdgeCaptureFields = z.infer<typeof edgeCaptureFieldsSchema>;

/**
 * Key del objeto en S3. Es fija por `capture_id`: un reenvío apunta a la misma foto.
 */
export function buildEdgeCaptureKey(captureId: string): string {
  return `${EDGE_CAPTURES_PREFIX}${captureId}.jpg`;
}
