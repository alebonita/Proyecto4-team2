# POR-2 — Conectar Capturas Edge a datos reales

**Criterio del ticket:** muestra foto, clase, confianza, fecha, ID, dispositivo y versión; tiene botón de actualizar y mensajes de carga, lista vacía y error.
**Evidencia:** captura de cada estado (abajo).

## Qué cambió respecto a POR-1

- **Datos reales.** La sección pide `GET /api/edge-captures?page=1&pageSize=100` (AWS-2), que lista las capturas que el dispositivo edge guardó en AWS, de la más reciente a la más antigua. La respuesta se valida con zod (`frontend/src/edge/api.ts`) antes de mostrarse. Si llega con otro formato, se muestra como error y no se pinta nada a medias.
- **Sin datos de ejemplo.** Se borró `mockCaptures.ts` y el aviso «Datos de prueba». No queda ninguna captura escrita en el código.
- **Las fotos caducan a los 15 minutos.** Cada `image_url` es una URL firmada de S3 con 15 minutos de vida (`EDGE_CAPTURE_URL_TTL_SECONDS = 900` en el backend). Por eso:
  - **«Actualizar» vuelve a pedir la lista** y, con ella, URLs nuevas para todas las fotos.
  - La página **renueva sola las URLs a los 14 minutos**, un minuto antes de que caduquen, sin quitar las tarjetas de la pantalla. Si esa renovación falla, avisa y sugiere «Actualizar».
  - Si una foto no carga (por ejemplo, porque la página estuvo abierta mucho tiempo sin red), la tarjeta dice **«No se pudo cargar la foto»** en vez de mostrar una imagen rota. Al actualizar llega otra URL y la foto se vuelve a intentar.
- Si en AWS hay más de 100 capturas, muestra las 100 más recientes y lo indica («Las 100 más recientes de N capturas»).

## Capturas de cada estado

Se tomaron con el portal en local (`npm run dev`), respondiendo `/api/edge-captures` con la misma forma que devuelve el backend real. Las fotos son recortes de la validación del Proyecto 3. Así cada estado es reproducible: la lista vacía o un error 502 no se pueden provocar a voluntad en el portal desplegado.

| Estado | Captura |
|---|---|
| Con capturas: foto, clase, confianza, ID, fecha, dispositivo, versión, latencia y recorte; la más reciente primero | `1-con-capturas.png` |
| Cargando | `2-cargando.png` |
| Lista vacía | `3-lista-vacia.png` |
| Error del servidor, con «Reintentar» | `4-error.png` |
| Foto con el enlace caducado | `5-foto-caducada.png` |

**Pendiente de tomar en el portal desplegado en AWS** (`http://18.216.36.30/edge/captures`): una captura con las capturas reales que envió la laptop edge (EDG-4). Esa URL no es accesible desde el entorno donde se tomaron las otras.

## Pruebas

`frontend/tests/edge-captures.test.tsx`, 11 pruebas con `fetch` simulado y la forma real de la API:

- abre desde el menú y llama a `/api/edge-captures?page=1&pageSize=100`
- sin datos de ejemplo; cada tarjeta muestra foto, clase, confianza, fecha, ID, dispositivo, versión y recorte, ordenadas por fecha
- carga, lista vacía, error 500 con «Reintentar», y respuesta con otro formato
- **«Actualizar» vuelve a pedir la lista y la foto usa la URL nueva**
- **renovación automática a los 14 minutos sin quitar las tarjetas**
- **foto que no carga, con mensaje, y que se recupera al actualizar**
- aviso cuando hay más capturas que las de la página

Verificado en local: `npm run lint`, `npm run typecheck`, `npm test` (20 archivos, 524 pruebas) y `npm run build` en verde.
