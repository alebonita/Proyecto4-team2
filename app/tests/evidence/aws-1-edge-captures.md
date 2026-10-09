# Evidencia AWS-1: POST /edge-captures en el portal desplegado

Ejecución: 2026-10-08, contra el portal en AWS (`http://18.216.36.30`, Elastic IP de
la instancia `i-02234c3f51db2446e`, `us-east-2`). Commit `0a58832` de
`feat/aws-1-edge-captures`. Peticiones desde fuera de AWS, por internet, con un JPEG
real de 64×48 generado con sharp.

## Envíos

| # | Petición | Respuesta |
|---|---|---|
| 1 | Captura nueva `aws1-prueba-20261008182407` | **201** con el registro |
| 2 | El mismo `capture_id` otra vez | **200** con el registro existente (mismo `received_at`) |
| 3 | Dos envíos **simultáneos** de `aws1-prueba-20261008182407-b` | Uno **201** y el otro **200** |
| 4 | `confidence=1.5` | **400** `confidence debe estar entre 0 y 1.` |
| 5 | Foto PNG | **400** `La foto debe ser JPEG (image/jpeg).` |
| 6 | `predicted_class=bird` | **400** `predicted_class debe ser una de: dog, cat.` |
| 7 | Preflight `OPTIONS` con `Origin: https://celular.example.com` | **204**, `Access-Control-Allow-Origin: *`, `Allow-Methods: POST, OPTIONS` |

Respuesta del envío 1 (la del 2 es idéntica):

```json
{"capture_id":"aws1-prueba-20261008182407","captured_at":"2026-10-09T00:30:00.000Z","device_id":"pixel-prueba","model_version":"1.0.0","predicted_class":"dog","confidence":0.91,"latency_ms":42.5,"received_at":"2026-10-09T00:24:08.000Z","image_key":"edge-captures/aws1-prueba-20261008182407.jpg"}
```

## Lo que quedó guardado

**MariaDB** (`edge_captures`, con `UNIQUE(capture_id)`): **una fila** por cada
`capture_id`, también en el caso simultáneo. Ninguna fila para los envíos rechazados.

```text
capture_id                    filas  image_key
aws1-prueba-20261008182407    1      edge-captures/aws1-prueba-20261008182407.jpg
aws1-prueba-20261008182407-b  1      edge-captures/aws1-prueba-20261008182407-b.jpg
```

**S3** (`mlops-p4-equipo-452857281704`, **versionado**, así que una segunda
escritura se vería como otra versión):

```text
edge-captures/aws1-prueba-20261008182407-b.jpg  286  IsLatest=True   (1 versión)
edge-captures/aws1-prueba-20261008182407.jpg    286  IsLatest=True   (1 versión)
marcadores de borrado: 0
objetos de los envíos rechazados: ninguno
```

La foto descargada de S3 es idéntica byte a byte (`cmp`) a la enviada, con
`ContentType image/jpeg` y cifrado `AES256`. La escribió el backend con el rol
`portal-proyecto4-ec2` de la instancia, sin access keys.

## Modo local (MinIO)

En el mismo contenedor, sin `EDGE_CAPTURES_BUCKET`, la foto va al MinIO del stack:
la primera escritura entra, la segunda devuelve `false` sin sobrescribir (MinIO
respeta `If-None-Match: *`) y el contenido guardado es el original. El objeto de
prueba se borró después.

## Tests

`npm test` en `backend/`: **159 passed** en 14 archivos, incluidos los nuevos
`edge-capture-validation`, `edge-capture-service` y `edge-capture-http`.
`npm run lint`, `npm run typecheck` y `npm run build` sin errores.
