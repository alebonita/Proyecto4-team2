# Evidencia AWS-2: consulta de capturas, clave del dispositivo y crop

Ejecución: 2026-10-08 (hora de México), contra el portal en AWS
(`http://18.216.36.30`, Elastic IP de la instancia `i-02234c3f51db2446e`,
`us-east-2`). Commit `f4299a8` de `feat/aws-2-consulta-capturas`. Peticiones desde
fuera de AWS, por internet.

**Foto de prueba:** JPEG de **1280×720 y 482,150 bytes**, tamaño real de un fotograma
de webcam, generado con sharp con textura y ruido para que no se comprima de más.

## Envío (`POST /api/edge-captures`)

La clave `EDGE_DEVICE_KEY` (64 caracteres) se generó con `openssl rand -hex 32` en el
`.env` del servidor. Nunca se imprimió ni entró al repo.

| # | Petición | Respuesta |
|---|---|---|
| 1 | Sin `X-Device-Key` | **401** `Clave de dispositivo ausente o incorrecta` |
| 2 | Con una clave incorrecta | **401** |
| 3 | JPEG de 482 KB, clave correcta, `crop` `{"x":320,"y":180,"width":640,"height":360}` | **201** en 0.76 s |
| 4 | El mismo `capture_id` otra vez | **200** con el registro existente |
| 5 | Dos capturas más, con `captured_at` 10:00 y 11:00, sin `crop` | **201** cada una |
| 6 | `crop` que se sale de la foto (`x` 1000 + `width` 400 > 1280) | **400** `el recorte se sale de la foto (1280x720)` |
| 7 | Preflight `OPTIONS` con `Origin` | Sin cabeceras `Access-Control-*` (ya no hay CORS) |

## Consulta (`GET /api/edge-captures`, abierta)

```text
page 1 pageSize 10 total 5
  2026-10-09T00:30:00.000Z  aws1-prueba-20261008182407-b   crop=None
  2026-10-09T00:30:00.000Z  aws1-prueba-20261008182407     crop=None
  2026-10-08T18:00:00.000Z  aws2-prueba-191201             crop={'x': 320, 'y': 180, 'width': 640, 'height': 360}
  2026-10-08T17:00:00.000Z  aws2-prueba-191201-c           crop=None
  2026-10-08T16:00:00.000Z  aws2-prueba-191201-a           crop=None
ordenado de más reciente a más antigua: True
```

Las dos capturas de AWS-1 tienen la misma `captured_at`. Desempatan por `id`
descendente: `-b` es la más nueva y va primero.

- **URL firmada:** la `image_url` de `aws2-prueba-191201` responde **HTTP 200**,
  `image/jpeg`, 482,150 bytes, **idéntica byte a byte** (`cmp`) a la enviada. Tiene
  `X-Amz-Expires=900` (15 minutos).
- **Bucket privado:** la misma key sin firma responde **403**.
- `GET /api/edge-captures/aws2-prueba-191201` devuelve el registro con su `crop`.
- **Errores:** una captura inexistente da **404**, y `pageSize=500` da **400**.

## Comando de solo lectura (`scripts/p4/consulta-aws.sh`)

`AWS_PROFILE=<perfil> PORTAL_URL=http://18.216.36.30 bash scripts/p4/consulta-aws.sh aws2-prueba-191201`:

```text
== La foto en S3: s3://mlops-p4-equipo-452857281704/edge-captures/aws2-prueba-191201.jpg (s3api head-object) ==
|  Cifrado      |  AES256                            |
|  Modificada   |  2026-10-09T01:12:04+00:00         |
|  Tamano_bytes |  482150                            |
|  Tipo         |  image/jpeg                        |
|  Version      |  3KsQp72QS0rGbdEQEFde2jekMy6a12uT  |

== Registro guardado con la foto (metadatos del objeto) ==
|  capture-id      |  aws2-prueba-191201                          |
|  captured-at     |  2026-10-08T18:00:00.000Z                    |
|  confidence      |  0.91                                        |
|  crop            |  {"x":320,"y":180,"width":640,"height":360}  |
|  device-id       |  laptop-prueba                               |
|  latency-ms      |  38.2                                        |
|  model-version   |  1.0.0                                       |
|  predicted-class |  dog                                         |
|  received-at     |  2026-10-09T01:12:03.000Z                    |

== Versiones del objeto (1 = nunca se sobrescribió) ==
|  Bytes  |  482150  |  Ultima | True  |  Version | 3KsQp72QS0rGbdEQEFde2jekMy6a12uT |
```

El registro de MariaDB, que el script consulta por la API del portal sin imprimir la
URL firmada, tiene el **mismo `received_at`** (`2026-10-09T01:12:03.000Z`) y el mismo
`crop`. Con un `capture_id` que no existe, el script responde
`No se encontró la foto…` y sale con código 1.

## Logs del servidor

En las 1,046 líneas de log de `backend` y `frontend` después de las pruebas:

- la clave del dispositivo: **0** apariciones;
- `X-Amz-Signature` (URL firmadas): **0**;
- `X-Device-Key`: **0**.

## Permiso de IAM agregado

Al rol `portal-proyecto4-ec2` (política `s3-models-read-edge-captures-write`) se le
agregó el statement `ReadEdgeCaptures`: `s3:GetObject` sobre
`arn:aws:s3:::mlops-p4-equipo-452857281704/edge-captures/*`. Sin ese permiso las URL
firmadas se generan, pero S3 responde 403 al abrirlas.

## Limpieza

Se borraron las dos capturas `aws1-prueba-20261008182407*`: sus versiones en S3 y sus
filas en `edge_captures`. Quedan las tres `aws2-prueba-191201*` como datos de prueba.

## Tests

- `backend/`, `npm test`: **201 passed** en 15 archivos. Incluyen el orden (SQL
  generado), la lista vacía, el rechazo sin clave (401), el 503 sin clave
  configurada y el campo `crop`.
- `npm run lint`, `npm run typecheck` y `npm run build`: sin errores.
- `app/`: los 7 archivos de tests que leen `docker-compose.yml` dan **83 passed**.
