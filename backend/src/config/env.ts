import 'dotenv/config';
import { fileURLToPath } from 'node:url';
import { z } from 'zod';

/**
 * Valida las variables de entorno usadas por la aplicación.
 */
const envSchema = z.object({
  PIPELINE_CONFIG_ROOT: z
    .string()
    .min(1)
    .default(fileURLToPath(new URL('../../../app/', import.meta.url))),

  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),

  PORT: z.coerce.number().int().positive().default(3000),

  DATABASE_URL: z.string().min(1),

  MINIO_ENDPOINT: z.string().min(1),

  MINIO_PORT: z.coerce.number().int().positive().default(9000),

  MINIO_USE_SSL: z
    .enum(['true', 'false'])
    .default('false')
    .transform((value) => value === 'true'),

  MINIO_ACCESS_KEY: z.string().min(1),

  MINIO_SECRET_KEY: z.string().min(1),

  MINIO_BUCKET: z.string().min(3),

  // APP-09: reportes con los que se verifica la trazabilidad de la cola de anotación
  // (models/registry.json y crops.json). En Docker, ./reports montado de solo lectura.
  REPORTS_DIR: z
    .string()
    .min(1)
    .default(fileURLToPath(new URL('../../../reports/', import.meta.url))),

  MAX_UPLOAD_SIZE_BYTES: z.coerce
    .number()
    .int()
    .positive()
    .default(10 * 1024 * 1024),

  // AWS-1: bucket de S3 del equipo donde se guardan las fotos de Capturas Edge
  // (prefijo edge-captures/). En AWS las credenciales salen del rol de la instancia.
  // Sin valor (desarrollo local), las fotos van a MinIO, al mismo bucket del portal.
  EDGE_CAPTURES_BUCKET: z.preprocess(
    (value) => (typeof value === 'string' && value.trim() === '' ? undefined : value),
    z.string().trim().min(3).optional(),
  ),

  EDGE_CAPTURES_REGION: z.string().min(1).default('us-east-2'),

  // AWS-1: orígenes que pueden llamar a POST /edge-captures desde el navegador
  // (la página del celular vive en otro origen). Lista separada por comas, o `*`.
  EDGE_CAPTURES_ALLOWED_ORIGINS: z
    .string()
    .default('*')
    .transform((value) =>
      value
        .split(',')
        .map((origin) => origin.trim())
        .filter((origin) => origin.length > 0),
    ),
});

/**
 * Variables ya validadas y tipadas.
 * Si alguna configuración requerida falta, la aplicación falla al iniciar.
 */
export const env = envSchema.parse(process.env);
