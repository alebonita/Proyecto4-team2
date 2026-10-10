# EDG-3 — Historial local de capturas

**Criterio del ticket:** cada captura crea un registro completo con su foto, el historial se
conserva al cerrar el programa y se puede exportar como JSON.

Código: [`edge/events.py`](../../edge/events.py), [`edge/capture.py`](../../edge/capture.py),
[`edge/export_events.py`](../../edge/export_events.py), [`edge/list_events.py`](../../edge/list_events.py)
y la prueba [`edge/tests/test_events.py`](../../edge/tests/test_events.py). Campos y comandos:
"Historial de capturas" en [`edge/README.md`](../../edge/README.md).

Este historial es la versión **local** de las capturas que se contrasta con AWS y el portal:
sus campos son los del contrato del endpoint (AWS-1/AWS-2), y `capture_id` va también en el
nombre de la foto.

## Prueba en la laptop edge (2026-10-10)

Dos capturas, cerrar el programa, volver a abrirlo y una captura más (por SSH, con el INT8
oficial; la cámara apuntaba al techo, así que la clase no significa nada aquí):

```
=== corrida 1
Historial:   /home/steph/Proyecto4-team2/edge/events.db (0 eventos)
Dispositivo: edge-macbookair-01
  Clase: cat  confianza: 0.9347  tiempo: 26.9 ms (preprocesamiento + inferencia)
  Evento: d5b5e774-14cf-47bf-9454-4142f3070479  2026-10-10T20:11:19.515+00:00  estado: pendiente
  Clase: cat  confianza: 0.9221  tiempo: 20.7 ms (preprocesamiento + inferencia)
  Evento: d8d1c0d5-7e14-43b3-8636-dae8b21b985a  2026-10-10T20:11:22.543+00:00  estado: pendiente
=== corrida 2 (programa reabierto)
Historial:   /home/steph/Proyecto4-team2/edge/events.db (2 eventos)
  Clase: cat  confianza: 0.9286  tiempo: 20.2 ms (preprocesamiento + inferencia)
  Evento: 234dfe99-9e2e-449b-8929-04a1d2635113  2026-10-10T20:11:34.737+00:00  estado: pendiente
```

Al reabrir, el historial ya tenía los 2 eventos de la corrida anterior.

```
$ python list_events.py
capture_id                            hora (captured_at)             clase  conf.   estado
234dfe99-9e2e-449b-8929-04a1d2635113  2026-10-10T20:11:34.737+00:00  cat    0.9286  pendiente
d8d1c0d5-7e14-43b3-8636-dae8b21b985a  2026-10-10T20:11:22.543+00:00  cat    0.9221  pendiente
d5b5e774-14cf-47bf-9454-4142f3070479  2026-10-10T20:11:19.515+00:00  cat    0.9347  pendiente

3 eventos en total (pendiente: 3, enviado: 0, error: 0)

$ python export_events.py -o /tmp/eventos.json
3 eventos exportados a /tmp/eventos.json
```

El JSON exportado está en [`eventos_ejemplo.json`](eventos_ejemplo.json). Cada evento trae
`capture_id`, `captured_at` (con zona horaria), `device_id`, `model_version`,
`predicted_class`, `confidence`, `latency_ms`, `crop`, `photo_path`, `photo_sha256` y
`status`; `received_at`, `image_key`, `send_error` y `send_ms` quedan en `null` hasta el envío
a AWS (EDG-4).

## Pruebas

`python -m unittest discover -s tests -v -b`: 11/11 en la laptop edge (5 de EDG-2 y 6 de EDG-3).

| Prueba | Qué comprueba |
|---|---|
| `test_capture_creates_a_complete_event_with_its_photo` | Todos los campos; UUID válido y aceptado por el patrón del servidor; fecha con zona horaria; la foto existe, lleva el ID en el nombre y su SHA-256 coincide |
| `test_each_capture_gets_its_own_id` | Tres capturas, tres IDs distintos |
| `test_history_survives_closing_and_reopening` | Cerrar y reabrir la base devuelve el mismo evento |
| `test_export_has_every_event_with_contract_fields` | El JSON tiene todos los eventos, con los campos del contrato y en orden cronológico |
| `test_list_shows_id_time_class_confidence_and_status` | La lista muestra ID, hora, clase, confianza y estado |
| `test_rejects_an_invalid_status` | Solo se aceptan `pendiente`, `enviado` y `error` |
