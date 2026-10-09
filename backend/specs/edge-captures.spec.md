# SPEC-EDGE-001 — Capturas Edge (AWS-1, AWS-2)

## Objetivo

Recibir la foto y el evento que envía el **dispositivo edge (laptop)**, un programa en
Python que clasifica con el modelo optimizado, y guardarlos en los servicios de AWS del
proyecto: la foto en el bucket de S3 del equipo y el evento en MariaDB. Después, darle
al portal la consulta de esas capturas.

## Enviar una captura: `POST /edge-captures`

Detrás de nginx: `POST /api/edge-captures`.

**Encabezado obligatorio:** `X-Device-Key` con la clave del dispositivo. Se compara
con `EDGE_DEVICE_KEY` del servidor.

**Cuerpo:** `multipart/form-data`.

| Campo | Tipo | Regla |
|---|---|---|
| `image` | archivo | JPEG (`image/jpeg`, verificado con sharp), hasta `MAX_UPLOAD_SIZE_BYTES` |
| `capture_id` | texto | 1 a 64 caracteres `A-Z a-z 0-9 _ -`. Lo genera el dispositivo |
| `captured_at` | texto | Fecha ISO 8601 con zona horaria |
| `device_id` | texto | 1 a 128 caracteres |
| `model_version` | texto | 1 a 64 caracteres |
| `predicted_class` | texto | Una de las clases del modelo: `dog`, `cat` |
| `confidence` | número | Entre 0 y 1 |
| `latency_ms` | número | Mayor o igual a 0 |
| `crop` | texto JSON, opcional | `{"x":…,"y":…,"width":…,"height":…}` en píxeles: `x`, `y` ≥ 0; `width`, `height` > 0; debe caber en la foto |

**Respuesta:** el registro, con los mismos campos más `received_at` e `image_key`. Si no
hay recorte, `crop` es `null`.

| Caso | HTTP |
|---|---|
| Sin `X-Device-Key` o con una clave incorrecta | `401` |
| El servidor no tiene `EDGE_DEVICE_KEY` | `503` (no queda abierto) |
| Captura nueva | `201` |
| `capture_id` ya registrado | `200` con el registro existente |
| Campo, recorte o foto inválidos | `400` |
| Foto mayor al máximo | `413` |

## Consultar capturas (abierto para el portal, sin clave)

- **`GET /edge-captures?page=1&pageSize=20`:** capturas **de la más reciente a la más
  antigua por `captured_at`**; a igual fecha, por `id` descendente.
  - `page` empieza en 1; `pageSize` va de 1 a 100, con 20 por defecto.
  - Respuesta: `{ items, page, pageSize, total }`. Con `items: []` si no hay
    capturas.
- **`GET /edge-captures/:capture_id`:** una sola captura. Responde `404` si no existe y
  `400` si el `capture_id` no es válido.

Cada captura trae `capture_id`, `captured_at`, `received_at`, `device_id`,
`model_version`, `predicted_class`, `confidence`, `latency_ms`, `crop`, `image_key` e
**`image_url`**: una URL temporal firmada de S3, válida 15 minutos, que abre la foto
sin credenciales.

## Reglas de negocio

1. La foto se guarda en S3 en `edge-captures/<capture_id>.jpg`, y el evento en la
   tabla `edge_captures`, con `received_at`, `image_key` y el recorte en `crop_x`,
   `crop_y`, `crop_width` y `crop_height`, que pueden quedar vacías.
2. **Idempotente por `capture_id`:** si ya existe, no se crea otro registro ni otra
   foto y se responde con el registro existente.
3. La escritura en S3 usa `If-None-Match: *` y nunca sobrescribe. Si dos envíos del
   mismo `capture_id` llegan a la vez, queda la foto del primero, y el que pierde el
   `INSERT` (índice único) responde con el registro ganador.
4. Si el `INSERT` falla después de subir la foto, la foto no se borra: el rol del
   servidor no tiene `DeleteObject` y la key es fija. Un reintento la encuentra y
   solo completa el registro.
5. Si la clave o la validación fallan, no se escribe nada en S3 ni en MariaDB. La
   clave se revisa **antes** de leer la foto.
6. El objeto de S3 lleva una copia del registro en sus metadatos (`capture-id`,
   `captured-at`, `received-at`, `device-id`, `model-version`, `predicted-class`,
   `confidence`, `latency-ms` y `crop`). Así `aws s3api head-object` muestra la foto
   y su registro con permisos de solo lectura. El `received_at` es el mismo en S3 y en
   MariaDB.
7. **Sin CORS:** quien envía es un programa, no una página web de otro origen. Las
   consultas del portal pasan por el mismo origen (nginx).
8. Nunca se registran en los logs la clave del dispositivo, credenciales ni URL
   firmadas. La comparación de la clave es de tiempo constante.

## Configuración

| Variable | Uso |
|---|---|
| `EDGE_DEVICE_KEY` | Clave del dispositivo edge, mínimo 16 caracteres. Solo en el `.env` del servidor, nunca en el repo |
| `EDGE_CAPTURES_BUCKET` | Bucket de S3 del equipo. En AWS, credenciales del rol de la instancia. Sin valor (desarrollo local), la foto va a MinIO, en `MINIO_BUCKET`, y la URL firmada apunta al MinIO del stack |
| `EDGE_CAPTURES_REGION` | Región del bucket (`us-east-2` por defecto) |

**Permisos del rol del servidor:**
- `s3:PutObject` en `edge-captures/*`, para guardar;
- `s3:GetObject` en `edge-captures/*`, para que las URL firmadas abran la foto. Firmar
  no consulta a S3, pero la URL se ejecuta con los permisos del rol.

## Flujo esperado

UI → Logic → Data → S3 (o MinIO en local) / MariaDB
