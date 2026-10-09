# SPEC-EDGE-001 — Capturas Edge (AWS-1)

## Objetivo

Recibir la foto y el evento que envía la página del celular después de clasificar
con el modelo optimizado, y guardarlos en los servicios de AWS del proyecto: la foto
en el bucket de S3 del equipo y el evento en MariaDB.

## Endpoint

`POST /edge-captures` (detrás de nginx: `POST /api/edge-captures`),
`multipart/form-data`:

| Campo | Tipo | Regla |
|---|---|---|
| `image` | archivo | JPEG (`image/jpeg`, verificado con sharp), hasta `MAX_UPLOAD_SIZE_BYTES` |
| `capture_id` | texto | 1 a 64 caracteres `A-Z a-z 0-9 _ -`. Lo genera el celular |
| `captured_at` | texto | Fecha ISO 8601 con zona horaria |
| `device_id` | texto | 1 a 128 caracteres |
| `model_version` | texto | 1 a 64 caracteres |
| `predicted_class` | texto | Una de las clases del modelo: `dog`, `cat` |
| `confidence` | número | Entre 0 y 1 |
| `latency_ms` | número | Mayor o igual a 0 |

Respuesta: el registro, con los mismos campos más `received_at` e `image_key`.

| Caso | HTTP |
|---|---|
| Captura nueva | `201` |
| `capture_id` ya registrado | `200` con el registro existente |
| Campo o foto inválidos | `400` |
| Foto mayor al máximo | `413` |

## Reglas de negocio

1. La foto se guarda en S3 en `edge-captures/<capture_id>.jpg`, y el evento en la
   tabla `edge_captures`, con `received_at` e `image_key`.
2. **Idempotente por `capture_id`:** si ya existe, no se crea otro registro ni otra
   foto y se responde con el registro existente.
3. La escritura en S3 usa `If-None-Match: *` y nunca sobrescribe. Si dos envíos del
   mismo `capture_id` llegan a la vez, queda la foto del primero, y el que pierde el
   `INSERT` (índice único) responde con el registro ganador.
4. Si el `INSERT` falla después de subir la foto, la foto no se borra: el rol del
   servidor no tiene `DeleteObject` y la key es fija. Un reintento la encuentra y
   solo completa el registro.
5. Si la validación falla, no se escribe nada en S3 ni en MariaDB.
6. CORS solo en esta ruta: los orígenes de `EDGE_CAPTURES_ALLOWED_ORIGINS` (`*` por
   defecto). Las cabeceras también van en las respuestas de error.

## Configuración

| Variable | Uso |
|---|---|
| `EDGE_CAPTURES_BUCKET` | Bucket de S3 del equipo. En AWS, credenciales del rol de la instancia. Sin valor (desarrollo local), la foto va a MinIO, en `MINIO_BUCKET` |
| `EDGE_CAPTURES_REGION` | Región del bucket (`us-east-2` por defecto) |
| `EDGE_CAPTURES_ALLOWED_ORIGINS` | Orígenes permitidos por CORS, separados por coma, o `*` |

## Flujo esperado

UI → Logic → Data → S3 (o MinIO en local) / MariaDB
