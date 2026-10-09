# POR-1 — Sección Capturas Edge en el menú del portal

**Criterio del ticket:** se abre desde la navegación del portal y muestra tarjetas con datos de prueba.
**Evidencia:** `capturas-edge-portal.png`.

## Qué se hizo

- Nueva entrada **«Capturas Edge»** en el menú lateral (`GlobalNav`), en su propio grupo debajo de Modelos.
- Ruta `/edge/captures` (y `/edge` redirige a ella) dentro del mismo `AppLayout` que el resto del portal: no es una página aislada.
- Galería de tarjetas con: foto, clase predicha, confianza, ID de captura, fecha de captura, dispositivo, versión del modelo optimizado, latencia local y recorte (dibujado sobre la foto cuando existe).
- Orden de la más reciente a la más antigua por `captured_at`.
- Botón **Actualizar** y mensajes de carga, lista vacía y error con **Reintentar**.
- Aviso visible de **«Datos de prueba»** mientras la sección no esté conectada a AWS.

Los campos usan los mismos nombres que `GET /edge-captures` (AWS-2), así que el siguiente paso solo cambia la función `load` de la página por la llamada a la API.

## Cómo reproducir la captura

```bash
cd frontend
npm ci
npm run dev
# Abrir http://localhost:5173 y hacer clic en «Capturas Edge» en el menú lateral
```

## Pruebas

`frontend/tests/edge-captures.test.tsx` (6 pruebas): abre la sección desde el menú, tarjetas con los datos de prueba, orden por fecha, lista vacía, error con reintento y botón Actualizar.

Verificado el 2026-10-08 en local: `npm run lint`, `npm run typecheck`, `npm test` (20 archivos, 519 pruebas) y `npm run build` en verde.

## Pendiente (fuera de este ticket)

- Conectar la sección a `GET /edge-captures` para mostrar capturas reales desde AWS.
- Capturas reales del dispositivo y despliegue en el portal de AWS.
