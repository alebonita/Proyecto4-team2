# EDG-5 — Benchmark en la laptop edge

**Criterio del ticket:** existe un CSV con cada tiempo de ambos modelos, las filas de
calentamiento marcadas y los datos del hardware.

Script: [`edge/benchmark.py`](../../edge/benchmark.py). Resultados:
[`artifacts/p4/benchmark.csv`](../../artifacts/p4/benchmark.csv) (variante, repeticion,
es_calentamiento, ms) y [`artifacts/p4/benchmark-condiciones.json`](../../artifacts/p4/benchmark-condiciones.json).

## Resultado (2026-10-12, laptop edge)

| | Original exportado (MOD-2, fp32) | Optimizado (MOD-3, INT8 `reduce_range`) | Diferencia |
|---|---|---|---|
| Archivo | `dog-cat-resnet18-1.0.0-fp32.onnx` | `dog-cat-resnet18-1.0.0-int8-rr.onnx` | |
| SHA-256 | `6628f3cf…7035f` | `1d4a85fa…cb5ea0` | |
| Tamaño | 44 961 942 bytes | 11 367 590 bytes | **−74.72 %** |
| **p50** | **13.38 ms** | **11.28 ms** | **−2.10 ms (−15.7 %)** |
| **p95** | **15.23 ms** | **11.94 ms** | **−3.29 ms (−21.6 %)** |
| Mín. / máx. | 13.16 / 19.74 ms | 11.13 / 14.11 ms | |
| Mediciones | 100 válidas + 10 de calentamiento | 100 válidas + 10 de calentamiento | |

El p95 del optimizado (11.94 ms) es menor que el **mínimo** del original (13.16 ms): la mejora
no está dentro de la variabilidad de las mediciones. Una segunda corrida completa, en las
mismas condiciones, dio p50 13.58 → 11.29 ms (−16.8 %) y p95 14.15 → 11.59 ms (−18.1 %).

**Recálculo independiente:** los percentiles se recalcularon desde el CSV con una función de
interpolación lineal escrita aparte (sin numpy): p50 13.3807 / 11.2771 ms y p95 15.2263 /
11.9371 ms, iguales a los del script salvo el redondeo a 4 decimales del CSV.

## Qué se mide

Cada repetición mide con `time.perf_counter` el **preprocesamiento + la inferencia + el softmax**,
con el mismo código del programa de captura (`classifier.preprocess`: recorte, BGR → RGB,
128 × 128 bilineal con Pillow y normalización ImageNet). No incluye leer el archivo de la
imagen ni el envío a AWS (EDG-4 lo mide aparte, `send_ms`). Los dos modelos usan:

- la misma imagen fija del repositorio: `evidencias/mod-01/validation/dog/img102-ann118.png`;
- onnxruntime 1.30.0, `CPUExecutionProvider`, con **2 hilos** (`intra_op`, los núcleos físicos)
  e `inter_op` 1;
- entrada `1 × 3 × 128 × 128`;
- 10 repeticiones de calentamiento (marcadas `es_calentamiento = true`) y 100 medidas;
- percentiles con `numpy.percentile(method="linear")` sobre las 100 medidas.

## Condiciones

| | |
|---|---|
| Equipo | Apple MacBook Air (MacBookAir6,1) |
| Procesador | Intel Core i5-4260U @ 1.40GHz, 2 núcleos físicos / 4 lógicos (AVX2, sin VNNI) |
| RAM | 3.3 GiB visibles para el sistema |
| Sistema operativo | Ubuntu 26.04.1 LTS, kernel 7.0, x86_64; Python 3.14.4 |
| Alimentación | **Conectada a la corriente** |
| Carga del sistema | loadavg 0.28 / 0.32 / 0.38 al empezar |
| Otros procesos | Sin programas abiertos. La laptop es también un nodo k3s siempre encendido: el servicio estaba activo, con carga baja, y fue igual para los dos modelos |

Los dos modelos se midieron uno tras otro en la misma ejecución, con la misma imagen y los
mismos hilos. Todo queda en `benchmark-condiciones.json`.

## Intercambio entre recursos y calidad en este hardware

En la laptop edge, la variante INT8 `reduce_range`:

- pesa **74.7 % menos** (10.8 MB contra 42.9 MB);
- tarda **~16 % menos en p50** y **~22 % menos en p95**;
- **no pierde calidad en este equipo**: 126/128 en la validación del Proyecto 3 contra 125/128
  del original (MOD-4 corrido en la laptop edge, `--variant int8-rr --tag intel`).

Se eligió `reduce_range` (pesos de 7 bits) por este CPU: sin VNNI, onnxruntime satura parte de
los productos INT8 de 8 bits, y la primera variante INT8 bajaba a 124/128 con probabilidades
que cambiaban hasta 0.88 (ver [`../edg-2/README.md`](../edg-2/README.md)). Con `reduce_range` la
velocidad es la misma (ver la comparación de variantes en EDG-2) y la calidad se conserva.
La ganancia de latencia es moderada porque el CPU no tiene instrucciones INT8 dedicadas; la
reducción de tamaño es completa.

## Cómo repetirlo

En la laptop edge, con los dos `.onnx` en `edge/models/`:

```bash
cd edge
.venv/bin/python benchmark.py --optimizado models/dog-cat-resnet18-1.0.0-int8-rr.onnx
```

(Cuando `config.yaml` apunte a la variante `int8-rr`, basta `python benchmark.py`.)
