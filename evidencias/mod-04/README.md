# MOD-4 — Comparación de calidad sobre la validación del Proyecto 3

**Criterio del ticket:** CSV con una fila por imagen (ID, clase real, predicción original, predicción optimizada); accuracy, F1 macro y resultados por clase calculados.
**Evidencia:** `predictions_validation.csv` y este reporte.

## Qué se comparó

| | |
|---|---|
| Validación | Los **128 recortes de validación del Proyecto 3** (`../mod-01/validation_manifest.csv`: 61 dog, 67 cat). Antes de usar cada imagen se verifica su SHA-256 |
| Original | `best.pt` del P3 en PyTorch (`84d6c88b…`). Sus predicciones salen de `../mod-01/predictions_original_validation.csv` (MOD-1) |
| Optimizada | Variante **INT8** de MOD-3 (`9c28368a…935cd`, 10.8 MB) |
| Runtime de la optimizada | **onnxruntime 1.30.0 de Python, CPU**: el mismo runtime que usa la laptop edge |
| Preprocesamiento | El mismo para las dos: `PREPROCESS` de `../mod-01/predict.py` (RGB, 128×128, normalización ImageNet) |

Las 150 imágenes con que se calibró la variante (MOD-1b) son de entrenamiento: **ninguna está en esta validación**. El test (71 recortes) no se usó.

## Resultado

| Modelo | Accuracy | F1 macro | Errores |
|---|---|---|---|
| Original (PyTorch) | **0.9766** (125/128) | **0.9765** | 3 |
| Optimizada INT8 (onnxruntime Python) | **0.9766** (125/128) | **0.9765** | 3 |
| **Caída** | **0.00 pp** | **0.00 pp** | |

La rúbrica permite una caída de hasta 2 puntos porcentuales; aquí es cero. **La variante da la misma clase que el original en 128 de 128 recortes.**

### Por clase

| Clase | Soporte | Precision orig. → opt. | Recall orig. → opt. | F1 orig. → opt. |
|---|---|---|---|---|
| dog | 61 | 0.9531 → 0.9531 | 1.0000 → 1.0000 | 0.9760 → 0.9760 |
| cat | 67 | 1.0000 → 1.0000 | 0.9552 → 0.9552 | 0.9771 → 0.9771 |

### Errores

Los dos modelos fallan en **los mismos 3 recortes**. En los 3 un gato se predice como perro:

| Recorte | Real | P(dog) original | P(dog) optimizada |
|---|---|---|---|
| `img131-ann149` | cat | 0.716 | 0.702 |
| `img263-ann299` | cat | 0.545 | 0.571 |
| `img633-ann627` | cat | 0.547 | 0.571 |

Son errores del modelo del Proyecto 3, no de la optimización: la variante no corrige ni agrega ninguno. Dos de los tres ya estaban cerca de 0.5 en el original, y siguen siendo los únicos casos cerca del límite. Cuantizar mueve las probabilidades como máximo **0.057** (en `img106-ann134`, un dog que sigue en 0.76) y no cruza el umbral en ningún recorte.

### Control de la conversión

El script también corre el **ONNX float32 de MOD-2** con onnxruntime de Python sobre los mismos 128 y obtiene **128/128 con la misma clase que el original**. Así se confirma que exportar a ONNX no cambia nada y que la única diferencia, mínima, viene de la cuantización.

## Variante `int8-rr` y la laptop edge (Intel sin VNNI)

En EDG-2, Stephy corrió la variante `int8` en la laptop edge (Intel Core i5-4260U, AVX2 sin VNNI) y obtuvo **124/128**, con 3 recortes que cambian de clase respecto a esta tabla. Por eso se generó en MOD-3 la variante **`int8-rr`** (`reduce_range=True`, pesos de 7 bits). Criterio acordado con la PM:

> Nos quedamos con `int8-rr` si da lo mismo en las dos computadoras y al menos 124/128. Si sale peor que `int8`, se regresa a `int8` y se documenta.

### Resultados por computadora

Mismas 128 entradas en las dos computadoras: el `.npz` con su SHA-256, ver «Entradas».

| Variante | Computadora | CPU (VNNI) | Accuracy | Misma clase que el original | Errores | Fuente |
|---|---|---|---|---|---|---|
| Original (PyTorch) | — | — | 125/128 (0.9766) | — | img131, img263, img633 | MOD-1 |
| `int8` | MOD-4 | Xeon 2.10 GHz (**sí**) | 125/128 (0.9766) | 128/128 | img131, img263, img633 | `metrics.json` |
| `int8` | laptop edge | i5-4260U (**no**) | 124/128 (0.9688) | 125/128 | img106, img263, img289, img633 | `metrics_intel.json` (Stephy) |
| **`int8-rr`** | MOD-4 | Xeon 2.10 GHz (**sí**) | **126/128 (0.9844)** | **127/128** | img131, img263 | `metrics_int8-rr.json` |
| **`int8-rr`** | laptop edge | i5-4260U (**no**) | **126/128 (0.9844)** | **127/128** | img131, img263 | `metrics_int8-rr_intel.json` (Stephy) |

En esta computadora, `int8-rr` **no pierde nada y corrige un error del original**: `img633-ann627` (gato) pasa de P(dog) 0.547 a 0.406 y queda bien clasificado. Por eso coincide con el original en 127/128 y no en 128/128: la única diferencia es ese acierto. Accuracy y F1 macro suben de 0.9766/0.9765 a **0.9844/0.9844** (caída de **−0.78 pp**, es decir, mejora). Los otros dos errores (`img131`, `img263`) siguen igual.

| Clase (`int8-rr`, MOD-4) | Soporte | Precision | Recall | F1 |
|---|---|---|---|---|
| dog | 61 | 0.9683 | 1.0000 | 0.9839 |
| cat | 67 | 1.0000 | 0.9701 | 0.9848 |

El cambio máximo de probabilidad respecto al original es 0.214 (`img526-ann521`, un gato que sigue en P(dog) 0.34, bien clasificado).

### Las dos computadoras, recorte por recorte

Stephy corrió el mismo script, con las mismas 128 entradas (`.npz` `29a6b2a2…`) y los mismos archivos (`9c28368a…` y `1d4a85fa…`), en la laptop edge: Intel Core i5-4260U, `vnni: "no"`, onnxruntime 1.30.0. Comparando sus CSV con los de esta computadora:

| Variante | Recortes con distinta clase entre las dos compus | Máx. \|Δ P(dog)\| entre las dos compus |
|---|---|---|
| `int8` | **3** (`img106-ann134`, `img131-ann149`, `img289-ann331`) | 0.813 |
| **`int8-rr`** | **0** | **0.000000** |

Con `int8`, el mismo archivo da resultados distintos según el CPU. Con **`int8-rr`, las 128 predicciones son idénticas en las dos computadoras**, hasta el sexto decimal de la probabilidad. Esto confirma que la diferencia venía de la saturación en CPUs sin VNNI, y que con pesos de 7 bits desaparece. La explicación detallada va en MOD-5.

### Decisión

Se cumplen las dos condiciones de la PM:

1. **Lo mismo en las dos computadoras:** 128/128 recortes con la misma clase y la misma probabilidad.
2. **Al menos 124/128 en la laptop edge:** da **126/128** (accuracy 0.9844, F1 macro 0.9844), 2 aciertos más que `int8` en esa laptop y 1 más que el original.

**Se adopta `int8-rr` (`dog-cat-resnet18-1.0.0-int8-rr.onnx`, SHA-256 `1d4a85fad5b2dcab28692bd5f81b5089092cf3a551b7862a63c544c94dcb5ea0`) como variante optimizada del proyecto.** La variante `int8` se conserva en el repo y en el bucket como registro de la comparación.

Para repetir la medición en otra computadora (no hace falta PyTorch):

```bash
python compare_quality.py --variant int8 --tag intel      # int8
python compare_quality.py --variant int8-rr --tag intel   # int8-rr
```

Genera `predictions_validation[_int8-rr]_<tag>.csv` y `metrics[_int8-rr]_<tag>.json`, con el CPU y si tiene VNNI, sin pisar los archivos de esta computadora.

### Entradas

`inputs/validation_resized_uint8.npz` (5 410 353 bytes, SHA-256 `29a6b2a2deb0e6accbf4cec3c9ad575ba9ef35c76950e4085a1228744795a3b3`) guarda los 128 recortes ya redimensionados a 128×128 con torchvision (uint8). El script solo los normaliza, en el mismo orden de operaciones que torchvision. `python compare_quality.py --build-inputs` (con PyTorch) regenera el archivo desde los PNG y **comprueba que el tensor sea idéntico byte a byte al `PREPROCESS` de MOD-1 en los 128**. Regenerarlo da el mismo SHA-256. Así, la comparación no depende de que la otra computadora tenga PyTorch ni de su versión de Pillow.

Con este cambio, la corrida de `int8` reproduce **exactamente** el mismo `predictions_validation.csv` que antes (se comparó con `cmp`).

## Archivos

- `predictions_validation.csv`: una fila por recorte (128). Columnas: `crop_id`, `true_class`, `pred_original`, `pred_optimized`, y las probabilidades de cada clase para los dos modelos.
- `metrics.json`: accuracy, F1 macro, precision/recall/F1/soporte por clase, errores, caída en pp, coincidencias, hashes de los modelos y del manifiesto, y versiones.
- `compare_output.txt`: la salida del comando.
- `predictions_validation_int8-rr.csv`, `metrics_int8-rr.json` y `compare_output_int8-rr.txt`: lo mismo para la variante `int8-rr`.
- `predictions_validation_intel.csv`, `metrics_intel.json`, `predictions_validation_int8-rr_intel.csv` y `metrics_int8-rr_intel.json`: las dos variantes en la laptop edge (Stephy).
- `inputs/validation_resized_uint8.npz`: las 128 entradas (ver «Entradas»).

Recalculé accuracy y F1 macro por separado, solo desde el CSV, y salen los mismos valores (0.976562 y 0.976550).

## Comando usado

Desde esta carpeta. No hace falta `best.pt` ni PyTorch: el original se toma de las predicciones de MOD-1 y las entradas, del `.npz`. Sí hacen falta los `.onnx`, generados con su script o bajados del bucket (ver `../mod-02/README.md` y `../mod-03/README.md`):

```bash
pip install numpy onnxruntime==1.30.0
python compare_quality.py                      # int8    -> predictions_validation.csv, metrics.json
python compare_quality.py --variant int8-rr    # int8-rr -> predictions_validation_int8-rr.csv, metrics_int8-rr.json
```

Salida de `int8`:

```
variante: int8 (dog-cat-resnet18-1.0.0-int8.onnx, SHA-256 9c28368acaf0…)
CPU: Intel(R) Xeon(R) Processor @ 2.10GHz  VNNI: ['avx512_vnni', 'avx_vnni']
runtime: onnxruntime 1.30.0 (Python, CPUExecutionProvider)
original   accuracy=0.9766 (125/128)  F1 macro=0.9765  dog: F1=0.9760  cat: F1=0.9771  errores: img131-ann149, img263-ann299, img633-ann627
optimizada accuracy=0.9766 (125/128)  F1 macro=0.9765  dog: F1=0.9760  cat: F1=0.9771  errores: img131-ann149, img263-ann299, img633-ann627
caída de accuracy: 0.00 pp   caída de F1 macro: 0.00 pp
misma clase que el original: 128/128   max |Δ prob|: 0.0573
control ONNX fp32 (MOD-2): 128/128
```

Salida de `int8-rr`:

```
variante: int8-rr (dog-cat-resnet18-1.0.0-int8-rr.onnx, SHA-256 1d4a85fad5b2…)
CPU: Intel(R) Xeon(R) Processor @ 2.10GHz  VNNI: ['avx512_vnni', 'avx_vnni']
runtime: onnxruntime 1.30.0 (Python, CPUExecutionProvider)
original   accuracy=0.9766 (125/128)  F1 macro=0.9765  dog: F1=0.9760  cat: F1=0.9771  errores: img131-ann149, img263-ann299, img633-ann627
optimizada accuracy=0.9844 (126/128)  F1 macro=0.9844  dog: F1=0.9839  cat: F1=0.9848  errores: img131-ann149, img263-ann299
caída de accuracy: -0.78 pp   caída de F1 macro: -0.78 pp
misma clase que el original: 127/128   max |Δ prob|: 0.2142
control ONNX fp32 (MOD-2): 128/128
```

Entorno: Linux x86_64, Python 3.13, CPU Xeon con VNNI (ver `metrics*.json`). **El INT8 sí depende del CPU:** el mismo archivo `int8` da 125/128 aquí y 124/128 en la laptop edge sin VNNI. Por eso la tabla de arriba lleva las dos computadoras.
