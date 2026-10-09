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

## Archivos

- `predictions_validation.csv`: una fila por recorte (128). Columnas: `crop_id`, `true_class`, `pred_original`, `pred_optimized`, y las probabilidades de cada clase para los dos modelos.
- `metrics.json`: accuracy, F1 macro, precision/recall/F1/soporte por clase, errores, caída en pp, coincidencias, hashes de los modelos y del manifiesto, y versiones.
- `compare_output.txt`: la salida del comando.

Recalculé accuracy y F1 macro por separado, solo desde el CSV, y salen los mismos valores (0.976562 y 0.976550).

## Comando usado

Desde esta carpeta. No hace falta `best.pt`, porque el original se toma de las predicciones de MOD-1. Sí hacen falta los dos `.onnx`, generados con su script o bajados del bucket (ver `../mod-02/README.md` y `../mod-03/README.md`):

```bash
pip install -r ../mod-02/requirements.txt
python compare_quality.py     # -> predictions_validation.csv, metrics.json
```

Salida:

```
validación: 128 recortes (dog=61, cat=67)
runtime: onnxruntime 1.30.0 (Python, CPUExecutionProvider)
original   accuracy=0.9766 (125/128)  F1 macro=0.9765  dog: F1=0.9760  cat: F1=0.9771  errores: img131-ann149, img263-ann299, img633-ann627
optimizada accuracy=0.9766 (125/128)  F1 macro=0.9765  dog: F1=0.9760  cat: F1=0.9771  errores: img131-ann149, img263-ann299, img633-ann627
caída de accuracy: 0.00 pp   caída de F1 macro: 0.00 pp
misma clase que el original: 128/128   max |Δ prob|: 0.0573
control ONNX fp32 (MOD-2): 128/128
```

Entorno: Linux x86_64, Python 3.13 y CPU (ver `metrics.json`). El mismo comando se puede repetir en la laptop edge. Las clases deben coincidir; las probabilidades INT8 pueden variar en los últimos decimales según el CPU.
