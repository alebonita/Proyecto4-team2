# MOD-1 — Modelo base del Proyecto 3

Modelo que el Proyecto 4 va a optimizar. Aquí no se entrenó ni se cambió nada: solo se recuperó, se verificó y se documentó.

Cubre la parte "modelo existente" del entregable 1 (*Modelo existente y variante optimizada*) y la evidencia *Identificación del modelo existente* del prompt de evaluación:

| Lo que se pide | Dónde está |
|---|---|
| Referencia al modelo propio del Proyecto 3 | [Referencia a la entrega del Proyecto 3](#referencia-a-la-entrega-del-proyecto-3) y `model/model-card.md` |
| Pesos originales | `model/best.pt` |
| Versión, run ID y hashes SHA-256 | [Identidad del modelo](#identidad-del-modelo), [Archivo de pesos](#archivo-de-pesos) y `SHA256SUMS` |
| Mapa de clases | [Clases](#clases-orden-de-salida-del-modelo) |
| Preprocesamiento | [Preprocesamiento](#preprocesamiento-el-mismo-de-validación-test-e-inferencia) |
| El modelo carga y predice una imagen conocida | `predict.py` y [Cómo reproducir](#cómo-reproducir) |
| Manifiesto de validación y predicciones del original por muestra (para la comparación de calidad) | `manifest_v0.1.1.json`, `validation_manifest.csv` y `predictions_original_validation.csv` |

## Identidad del modelo

| Campo | Valor |
|---|---|
| Nombre / versión | `dog-cat-resnet18` **1.0.0** |
| Run ID de MLflow | `bb448230424146349a969253d30db43b` (run `ml07-v1-r03-sgd`, candidato congelado de ML-08) |
| Checkpoint en MLflow | `runs:/bb448230424146349a969253d30db43b/checkpoints/best.pt` |
| Dataset / manifiesto | release `v0.1.1`, `manifest_hash` `sha256:178b28bddb1bef5c05975fc7150710658627e31af08a1a12d94b98f9e99cb2b2` |
| Arquitectura | ResNet18 (ImageNet `IMAGENET1K_V1`) con `fc` = identidad → cabeza `Linear(512,128) → ReLU → Dropout(0.2) → Linear(128,2)` |
| Métricas P3 | validation 125/128 (0.9766); test 68/71, accuracy 0.9577, F1 macro 0.9548 |

## Referencia a la entrega del Proyecto 3

Para contrastar que este es el modelo propio del equipo:

- Repositorio: <https://github.com/White-eclipse1/Proyecto-03-team5>, commit final `57abc45556727dfc32e64fd4739059f94ac442df` (2026-10-03).
- `reports/models/registry.json`: entrada `dog-cat-resnet18` 1.0.0 con el mismo run ID, SHA-256, `class_map` y preprocesamiento.
- `reports/candidates/ml08_candidate.json`: el run `bb448230…` es el candidato congelado (mejor `best_val_loss` de las 12 corridas de la matriz `ml07-v1`).
- `reports/models/s3_publications.json`: publicación en S3 del 2026-10-02 con el mismo SHA-256.
- `data/models.dvc` → `data/models/dog-cat-resnet18/1.0.0/` (paquete versionado con DVC).
- `model/model-card.md` en esta carpeta es la ficha original del P3, copiada sin cambios (SHA-256 `b3dd3e51…7a8703`, igual al del registro).

## Archivo de pesos

| | |
|---|---|
| En esta carpeta | `model/best.pt` (45 043 841 bytes) |
| Original en S3 | `s3://mlops-p2-dvc-cache-280764207006/models/dog-cat-resnet18/1.0.0/checkpoint/best.pt` (us-east-1) |
| Original en MLflow | artefacto `checkpoints/best.pt` del run de arriba |
| **SHA-256** | `84d6c88b4bd84c3e6f0229dd23f7f188ff85622bbb39e5c3988a97598fa90d52` |

El SHA-256 coincide con el registrado en `reports/models/registry.json` y `reports/models/s3_publications.json` del Proyecto 3. Para comprobarlo: `shasum -a 256 model/best.pt`.

El `.pt` es un diccionario de PyTorch (`torch.load(..., weights_only=True)`) con `state_dict`, `config`, `class_map` y `preprocessing`; no es un modelo completo serializado, así que hay que construir la arquitectura antes de cargar los pesos (ver `predict.py`).

## Clases (orden de salida del modelo)

| Índice | Clase |
|---|---|
| 0 | `dog` |
| 1 | `cat` |

Ojo: **dog va primero**, no en orden alfabético. La salida son 2 logits; se aplica softmax y la clase es el índice mayor.

## Preprocesamiento (el mismo de validación, test e inferencia)

1. Abrir la imagen y convertir a **RGB** (no BGR; si se usa OpenCV, convertir con `cv2.COLOR_BGR2RGB`).
2. Redimensionar a **128 × 128** directamente (cuadrado, sin conservar proporción ni recortar), interpolación bilineal con antialias.
3. Pasar a float y dividir entre 255 → rango [0, 1].
4. Normalizar por canal con la media y desviación de ImageNet:
   - mean = `[0.485, 0.456, 0.406]`
   - std = `[0.229, 0.224, 0.225]`
5. Formato del tensor: **NCHW**, float32, forma `1 × 3 × 128 × 128`.

La entrada del modelo es el **recorte de una caja** (un solo objeto), no la imagen completa.

## Datos de validación

- `manifest_v0.1.1.json`: manifiesto completo del release (668 recortes: 469 train, 128 validation, 71 test). SHA-256 `64b86b23fdfa84991b1656dfddab9d3157630028fd6f73a0ecc934b3ef02ae6f`.
- `validation_manifest.csv`: los 128 recortes de validación (67 cat, 61 dog) con su clase, ruta y SHA-256 (cada uno verificado contra `crops.json` del P3).
- `validation/{cat,dog}/*.png`: las imágenes.

- `predictions_original_validation.csv`: una fila por muestra con `crop_id`, clase real, clase predicha por el modelo original y probabilidades. Es la mitad "original" de la comparación de calidad; la variante optimizada debe agregar su columna `pred_optimized` sobre los mismos 128 `crop_id`.

El test (71 recortes) se dejó fuera a propósito: en el P3 se usó una sola vez para evaluar el candidato, y no debe usarse para calibrar ni ajustar la variante.

### Línea base del original en validación

| Clase | Precision | Recall | F1 | Soporte |
|---|---|---|---|---|
| dog | 0.9531 | 1.0000 | 0.9760 | 61 |
| cat | 1.0000 | 0.9552 | 0.9771 | 67 |
| **Total** | | | **F1 macro 0.9765** | **accuracy 0.9766 (125/128)** |

Errores: `img131-ann149`, `img263-ann299`, `img633-ann627`, los tres son cat predichos como dog.

## Cómo reproducir

Requiere Python 3.12 (verificado con 3.12.6 en una MacBook con Apple M3, macOS 15.7.1, CPU).

```bash
pip install -r requirements.txt   # torch 2.14.0, torchvision 0.29.0, pillow 10.4.0
shasum -a 256 -c SHA256SUMS       # todos los archivos de la carpeta están íntegros
python predict.py                 # verifica SHA-256 y predice una imagen de validación
python predict.py img.png         # predice otra imagen
python predict.py --all           # los 128 de validación + predictions_original_validation.csv
```

Resultado obtenido el 2026-10-05:

```
best.pt SHA-256 OK: 84d6c88b4bd84c3e6f0229dd23f7f188ff85622bbb39e5c3988a97598fa90d52
img102-ann118.png: dog  dog=1.0000  cat=0.0000
clase real: dog -> OK

validation: 125/128 correctas, accuracy=0.9766
F1 macro=0.9765
  errores: img131-ann149, img263-ann299, img633-ann627 (los tres cat → dog)
```

125/128 = 0.9765625 es exactamente el `best_val_accuracy` que registró MLflow para este run, y las probabilidades de `predict.py` son idénticas (diferencia máxima 0.0) a las del código de inferencia del P3 (`training/inference.py`) en las 128 imágenes. Con esto el modelo de la carpeta es el mismo que entrenamos, y el script es una referencia válida para comparar el modelo convertido u optimizado.
