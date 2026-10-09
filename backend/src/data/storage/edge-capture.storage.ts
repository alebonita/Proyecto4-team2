import {
  GetObjectCommand,
  PutObjectCommand,
  S3Client,
  S3ServiceException,
} from '@aws-sdk/client-s3';
import { getSignedUrl } from '@aws-sdk/s3-request-presigner';

import { env } from '../../config/env.js';

/**
 * AWS-1 — almacenamiento de las fotos de Capturas Edge.
 *
 * En AWS (`EDGE_CAPTURES_BUCKET` definido) escribe en el bucket de S3 del equipo con
 * las credenciales del rol de la instancia (cadena por defecto del SDK, sin access
 * keys). Sin esa variable (desarrollo local) usa el MinIO del stack, que habla la
 * misma API de S3, en el bucket del portal. La key es la misma en los dos casos.
 */
const useTeamBucket = env.EDGE_CAPTURES_BUCKET !== undefined;

export const edgeCapturesBucket = env.EDGE_CAPTURES_BUCKET ?? env.MINIO_BUCKET;

const s3 = useTeamBucket
  ? new S3Client({ region: env.EDGE_CAPTURES_REGION })
  : new S3Client({
      region: 'us-east-1',
      endpoint: `${env.MINIO_USE_SSL ? 'https' : 'http'}://${env.MINIO_ENDPOINT}:${env.MINIO_PORT}`,
      forcePathStyle: true,
      credentials: {
        accessKeyId: env.MINIO_ACCESS_KEY,
        secretAccessKey: env.MINIO_SECRET_KEY,
      },
    });

/**
 * Los metadatos de S3 viajan como cabeceras HTTP: solo ASCII imprimible. Cualquier
 * otro carácter se codifica como en una URL (`%XX`).
 */
function toHeaderSafe(value: string): string {
  return value.replace(/[^\x20-\x7e]/g, (char) => encodeURIComponent(char));
}

/**
 * Guarda la foto sin sobrescribir nunca un objeto existente.
 *
 * `If-None-Match: *` hace que S3 rechace la escritura si la key ya existe (412), o si
 * otra petición la está escribiendo en ese momento (409). En ambos casos ya hay una
 * foto para esa captura, así que no se crea otra y se devuelve `false`.
 *
 * AWS-2: `metadata` copia el registro en el propio objeto, para que un comando de solo
 * lectura de AWS CLI (`head-object`) muestre la foto y su registro sin entrar al
 * servidor.
 */
export async function putEdgeCaptureObject(
  key: string,
  buffer: Buffer,
  metadata: Record<string, string> = {},
): Promise<boolean> {
  try {
    await s3.send(
      new PutObjectCommand({
        Bucket: edgeCapturesBucket,
        Key: key,
        Body: buffer,
        ContentType: 'image/jpeg',
        IfNoneMatch: '*',
        Metadata: Object.fromEntries(
          Object.entries(metadata).map(([name, value]) => [name, toHeaderSafe(value)]),
        ),
      }),
    );
    return true;
  } catch (error) {
    const status = error instanceof S3ServiceException ? error.$metadata.httpStatusCode : undefined;

    if (status === 412 || status === 409) {
      return false;
    }

    throw error;
  }
}

/**
 * AWS-2 — URL temporal firmada para ver la foto desde S3 sin credenciales.
 *
 * Firmar no consulta a S3: la URL se calcula con las credenciales del rol. Solo abre
 * la foto si ese rol tiene `s3:GetObject` sobre la key, y dura lo que diga
 * `expiresInSeconds` o lo que les quede a esas credenciales, lo que pase antes. En
 * local apunta al MinIO del stack (`MINIO_ENDPOINT`).
 */
export async function getEdgeCaptureImageUrl(
  key: string,
  expiresInSeconds: number,
): Promise<string> {
  return getSignedUrl(s3, new GetObjectCommand({ Bucket: edgeCapturesBucket, Key: key }), {
    expiresIn: expiresInSeconds,
  });
}
