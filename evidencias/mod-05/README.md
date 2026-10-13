# MOD-5 — Reporte antes/después

**Criterio del ticket:** una tabla con el tamaño, la accuracy, el F1 y la latencia de los dos modelos, y un párrafo que explique qué se ganó y qué se perdió.
**Evidencia:** este reporte. Los números salen de `reporte.json`, que genera `build_report.py` a partir de las mediciones de MOD-2, MOD-3, MOD-4 y EDG-5. Este ticket no corre modelos nuevos.

## Los dos modelos

- **Original:** `best.pt`, el ResNet18 perro/gato del Proyecto 3 (SHA-256 `84d6c88b…`).
  - La calidad se midió con PyTorch.
  - La latencia se midió con su exportación ONNX fp32 de MOD-2 (`6628f3cf…`), porque la laptop edge no tiene PyTorch. Son los mismos pesos sin optimizar: en MOD-4, el ONNX fp32 da la misma clase que `best.pt` en 128/128.
- **Optimizado:** `dog-cat-resnet18-1.0.0-int8-rr.onnx`, con SHA-256 `1d4a85fad5b2dcab28692bd5f81b5089092cf3a551b7862a63c544c94dcb5ea0`.
  - Es una cuantización estática INT8 con `reduce_range=True` (MOD-3b).
  - Es la variante que la PM adoptó en MOD-4.

## Tabla

| | Original | **Optimizado (int8-rr)** | Cambio |
|---|---|---|---|
| **Tamaño** | 44 961 942 bytes (42.9 MB, ONNX fp32)<br>`best.pt`: 45 043 841 bytes | **11 367 590 bytes (10.8 MB)** | **−74.72 %** (≈ 4× más chico) |
| **Accuracy** (128 de validación) | 0.9766 (125/128) | **0.9844 (126/128)** | +0.78 pp |
| **F1 macro** | 0.9765 | **0.9844** | +0.78 pp |
| **Latencia p50** (laptop edge) | 13.38 ms | **11.28 ms** | **−2.10 ms (−15.7 %)** |
| **Latencia p95** (laptop edge) | 15.23 ms | **11.94 ms** | **−3.29 ms (−21.6 %)** |

Cómo se midió cada fila:

- **Calidad.** Son los mismos 128 recortes de validación de MOD-1 (61 dog, 67 cat). El optimizado da **exactamente las mismas 128 predicciones** en las dos computadoras: la laptop edge sin VNNI y un Xeon con VNNI (`metrics_int8-rr_intel.json` y `metrics_int8-rr.json`).
- **Latencia.** Es la de EDG-5, en la laptop edge:
  - Equipo: MacBook Air 6,1, Intel Core i5-4260U, Ubuntu 26.04, onnxruntime 1.30.0 en CPU, 2 hilos, conectada a la corriente y con k3s activo.
  - Mismo recorte, 10 corridas de calentamiento y 100 medidas por modelo.
  - Cada medida incluye el preprocesamiento, la inferencia y el softmax.
  - `build_report.py` recalcula los percentiles desde `artifacts/p4/benchmark.csv` y coincide con EDG-5.
  - Rangos de las medidas: el original va de 13.16 a 19.74 ms y el optimizado de 11.13 a 14.11 ms. **El p95 del optimizado es menor que el mínimo del original**, así que la mejora no se debe a la variación entre medidas.
  - Una segunda corrida completa dio p50 13.58 → 11.29 ms y p95 14.15 → 11.59 ms.

## Qué se ganó y qué se perdió

**Ganamos tamaño y velocidad sin perder calidad.**

- El modelo pesa **74.7 % menos** (de 42.9 MB a 10.8 MB). Se descarga, se guarda y se carga en memoria con menos recursos. Esto importa en una laptop de 2014 con 3.3 GiB de RAM.
- En esa misma laptop responde **~16 % más rápido en p50 y ~22 % más rápido en p95**. Además, la latencia es más estable: el peor caso del optimizado (14.1 ms) es menor que el p95 del original (15.2 ms).
- La accuracy y el F1 no bajaron: subieron 0.78 pp. **Esa subida no es una mejora del modelo.** Corresponde a un solo recorte (`img633-ann627`, cat) que el original clasificaba mal y el optimizado clasifica bien. Con 128 imágenes, la conclusión honesta es que **la calidad se mantuvo igual**.

**Perdimos fidelidad numérica, independencia del CPU y reproducibilidad exacta.**

- **Fidelidad numérica.** Las probabilidades ya no son idénticas a las del original: la diferencia máxima es 0.214, y 1 de 128 recortes cambia de clase (127/128 iguales). La cuantización redondea los pesos y las activaciones a 8 bits.
- **Independencia del CPU.** El resultado de un INT8 depende del CPU. La primera variante (`int8`) daba resultados distintos en la laptop edge, como se explica en la siguiente sección. Por eso hubo que generar `int8-rr` y medir la calidad en las dos computadoras.
- **Mejora de velocidad menor que la de tamaño.** El modelo es 4× más chico, pero solo ~16 % más rápido. Este CPU no tiene instrucciones VNNI para acelerar INT8. Además, cada medida incluye el preprocesamiento, que no cambia. Solo con la inferencia, EDG-2 midió 11.4 → 9.3 ms.
- **Reproducibilidad exacta.** El proceso es más complejo: ahora hacen falta 150 imágenes de calibración (MOD-1b). El archivo solo es idéntico byte a byte en la misma plataforma: en otra, la calibración puede dar un hash distinto, aunque con las mismas clases (MOD-3).

## Por qué el INT8 depende del CPU (sin VNNI)

La laptop edge tiene un **Intel Core i5-4260U (Haswell, 2014)**. Ese CPU tiene AVX2, pero **no tiene VNNI** (AVX-512 VNNI / AVX-VNNI). Sin VNNI, onnxruntime multiplica las activaciones `uint8` por los pesos `int8` con la instrucción `vpmaddubsw`:

1. La instrucción multiplica pares de bytes.
2. Suma cada par en un entero de **16 bits con saturación**.
3. Si la suma pasa de 32 767, se queda en 32 767 en vez de dar el valor real.

Con pesos de 8 bits (hasta ±127) y activaciones de 8 bits (hasta 255), una sola pareja puede llegar a 2 × 255 × 127 = 64 770, el doble del límite. Esas sumas se truncan y el resultado se desvía.

En un CPU con VNNI, la instrucción `vpdpbusd` acumula directamente en 32 bits y no se satura. Por eso **el mismo archivo da resultados distintos en cada computadora**:

| Variante | Correctas con VNNI (Xeon) | Correctas en la laptop edge (sin VNNI) | Clases distintas entre computadoras | máx. \|Δ P(dog)\| entre computadoras |
|---|---|---|---|---|
| `int8` (8 bits) | 125/128 | 124/128 | **3** (`img106-ann134`, `img131-ann149`, `img289-ann331`) | **0.813** |
| **`int8-rr` (7 bits)** | 126/128 | 126/128 | **0** | **0.000** |

**La solución es `reduce_range=True`.** Los pesos se guardan con 7 bits (hasta ±63). Así, la pareja más grande es 2 × 255 × 63 = 32 130, menor que 32 767, y la suma ya no se satura. Es lo que recomienda la documentación de cuantización de onnxruntime para CPUs sin VNNI.

EDG-2 lo comprobó en la laptop:

- La desviación contra fp32 bajó de 0.885 a 0.210.
- La velocidad no cambió: p50 9.4 ms con `int8` y 9.3 ms con `int8-rr`.
- Una variante S8S8 no corrigió la desviación y además era más lenta.

Las dos variantes pesan lo mismo porque cada peso sigue ocupando 1 byte.

## Cómo reproducir

Desde esta carpeta. Solo usa la biblioteca estándar de Python y no necesita los modelos:

```bash
python build_report.py      # imprime la tabla y escribe reporte.json
```

`build_report.py` comprueba tres cosas antes de escribir el reporte:

- Que EDG-5 midió los mismos archivos (mismos SHA-256) que evaluó MOD-4.
- Que el optimizado da las mismas correctas en las dos computadoras.
- Que los percentiles recalculados coinciden con los que reportó EDG-5.

La salida guardada está en `build_report_output.txt`.

| Dato | Archivo de origen |
|---|---|
| Tamaño y hashes | `../mod-02/export_log.json`, `../mod-03/conversion_log_reduce_range.json` |
| Accuracy y F1 | `../mod-04/metrics_int8-rr.json` (Xeon con VNNI), `../mod-04/metrics_int8-rr_intel.json` (laptop edge) |
| Comparación VNNI | `../mod-04/metrics*.json` y `../mod-04/predictions_validation*.csv` |
| Latencia | `../../artifacts/p4/benchmark.csv`, `../../artifacts/p4/benchmark-condiciones.json` (EDG-5) |
| Causa medida en la laptop | `../edg-2/README.md` |
