# MOD-3 — Variante optimizada con un script reproducible

**Criterio del ticket:** el script genera la variante desde el original; pesa menos y carga en el runtime web.
**Evidencia:** script, registro de la conversión, archivo y SHA-256 (abajo).

## Técnica

**Cuantización estática INT8 post-entrenamiento** con `onnxruntime.quantization`: los pesos pasan de float32 a enteros de 8 bits (por canal) y las activaciones se cuantizan con rangos medidos en un conjunto de calibración. No se reentrena ni se cambia la arquitectura. Es el mismo modelo del Proyecto 3:

`best.pt` (P3, SHA-256 `84d6c88b…`) → ONNX float32 de MOD-2 (`6628f3cf…`) → **esta variante INT8**

| Configuración | Valor |
|---|---|
| Formato | QDQ (QuantizeLinear/DequantizeLinear), opset 17 |
| Pesos | QInt8, **por canal** |
| Activaciones | QUInt8 |
| Calibración | MinMax con **150 imágenes de entrenamiento** de MOD-1b (75 dog + 75 cat) |
| Preprocesamiento de calibración | El mismo del original: `PREPROCESS` de `../mod-01/predict.py` (RGB, 128×128, ImageNet) |

**Calibración sin validación ni test.** Las 150 imágenes vienen de `../calibracion/calibration-ids.csv` (MOD-1b, split `train`). Antes de cuantizar, el script comprueba el SHA-256 de cada imagen contra ese CSV, que las 150 sean de `train` y que ninguna esté en los 128 de validación. La validación se usa solo para comparar la calidad, en MOD-4.

## Archivo

| | Original (MOD-2) | **Variante (MOD-3)** |
|---|---|---|
| Archivo | `dog-cat-resnet18-1.0.0-fp32.onnx` | `model/dog-cat-resnet18-1.0.0-int8.onnx` |
| Precisión | float32 | **INT8** |
| Tamaño | 44 961 942 bytes (42.9 MB) | **11 367 590 bytes (10.8 MB)** |
| SHA-256 | `6628f3cf24673a5045d51723b97dcfca85ebc1d511d49793bb6c0b0731c7035f` | **`9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd`** |

**Pesa 74.72 % menos:** 100 × (44 961 942 − 11 367 590) / 44 961 942.

La variante está en el bucket del equipo, en `s3://mlops-p4-equipo-452857281704/models/dog-cat-resnet18/1.0.0/onnx/dog-cat-resnet18-1.0.0-int8.onnx` (us-east-2). Igual que los otros pesos, **no está en git**. El script la vuelve a generar idéntica: dos corridas dieron el mismo SHA-256.

## Carga en el runtime web

`verify_web.mjs` carga la variante con `onnxruntime-web` 1.22.0 (WASM) y la corre sobre las mismas 5 entradas de MOD-2:

| Recorte | Real | Original | Variante INT8 (web) | Prob. | Δ máx. logits |
|---|---|---|---|---|---|
| `img102-ann118` | dog | dog | **dog** ✓ | 1.000000 | 0.071 |
| `img31-ann38` | cat | cat | **cat** ✓ | 0.999998 | 0.288 |
| `img125-ann141` | cat | cat | **cat** ✓ | 0.898945 | 0.043 |
| `img560-ann562` | dog | dog | **dog** ✓ | 0.638797 | 0.074 |
| `img263-ann299` | cat | dog | **dog** ✓ | 0.570789 | 0.057 |

**5/5 con la misma clase que el original.** Ahora las diferencias de logits son de centésimas, no de millonésimas como en MOD-2. Es el efecto esperado de cuantizar, y no cambia ninguna clase. La comparación completa sobre los 128 de validación, con **onnxruntime de Python** (el runtime de la laptop edge), está en MOD-4.

## Comandos usados

Desde esta carpeta, con el ONNX de MOD-2 en `../mod-02/model/` y `calibracion.zip` de MOD-1b descomprimido en la raíz del repo (`calibracion/{dog,cat}/*.png`, en `.gitignore`):

```bash
pip install -r ../mod-02/requirements.txt   # onnx 1.23.2, onnxruntime 1.30.0, torch/torchvision del P3
python quantize_int8.py                     # -> model/*-int8.onnx, model/SHA256SUMS, conversion_log.json
sha256sum -c model/SHA256SUMS               # (macOS: shasum -a 256 -c model/SHA256SUMS)

npm install                                 # onnxruntime-web 1.22.0
node verify_web.mjs                         # 5/5 -> resultados_web.json
```

Salidas guardadas: `conversion_output.txt`, `conversion_log.json` (entrada, salida, configuración, calibración, tamaños y versiones), `verify_web_output.txt` y `resultados_web.json`.

Para usar la copia del bucket en lugar de generarla:

```bash
aws s3 cp s3://mlops-p4-equipo-452857281704/models/dog-cat-resnet18/1.0.0/onnx/dog-cat-resnet18-1.0.0-int8.onnx \
  model/ --region us-east-2 --profile <tu-perfil>
sha256sum -c model/SHA256SUMS
```

## Qué falta (otros tickets)

- **Calidad en los 128 de validación**: MOD-4.
- **Latencia p50/p95 en la laptop edge**: se mide en el dispositivo, no aquí. Este ticket solo demuestra la reducción de tamaño.
