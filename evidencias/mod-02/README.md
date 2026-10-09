# MOD-2 — Exportar el original a ONNX (sin optimizar)

**Criterio del ticket:** el archivo carga en el runtime web y da la misma clase que el original en 5 imágenes.
**Evidencia:** archivo, SHA-256 y comando usado (abajo).

Este ONNX es el **mismo modelo del Proyecto 3**, solo cambiado de formato. No está cuantizado ni podado, y sigue en float32. Es el punto de partida para la variante optimizada y la referencia para separar el efecto de la conversión del efecto de la optimización.

## Archivo

| | |
|---|---|
| Archivo | `model/dog-cat-resnet18-1.0.0-fp32.onnx` (44 961 942 bytes) |
| **SHA-256** | `6628f3cf24673a5045d51723b97dcfca85ebc1d511d49793bb6c0b0731c7035f` |
| Origen | `../mod-01/model/best.pt`, SHA-256 `84d6c88b4bd84c3e6f0229dd23f7f188ff85622bbb39e5c3988a97598fa90d52` (MOD-1) |
| Bucket del equipo | `s3://mlops-p4-equipo-452857281704/models/dog-cat-resnet18/1.0.0/onnx/dog-cat-resnet18-1.0.0-fp32.onnx` (us-east-2) |
| Formato | ONNX, opset 17, float32, exportador `torch.onnx.export(dynamo=False)` |
| Entrada | `input`: float32 `1 × 3 × 128 × 128`, NCHW, RGB normalizado con media/desviación de ImageNet (igual que MOD-1) |
| Salida | `logits`: `1 × 2`, índice 0 = `dog`, 1 = `cat` (mismo `class_map` que el original) |

Como `best.pt`, el `.onnx` **no está en git** por su tamaño: está en el bucket del equipo (comando abajo) y se regenera idéntico con `export_onnx.py`. Exportarlo dos veces dio el mismo SHA-256. `model/SHA256SUMS` guarda los hashes del `.onnx` y del `best.pt` de origen.

## Resultado en el runtime web

`onnxruntime-web` 1.22.0 (backend WASM), Node 22.22.0, con las mismas entradas que recibe el original:

| Recorte | Caso | Real | Original (PyTorch) | ONNX en runtime web | Prob. web | Δ máx. logits |
|---|---|---|---|---|---|---|
| `img102-ann118` | dog muy seguro | dog | dog | **dog** ✓ | 1.000000 | 3.8e-6 |
| `img31-ann38` | cat muy seguro | cat | cat | **cat** ✓ | 0.999999 | 9.5e-7 |
| `img125-ann141` | cat con confianza media | cat | cat | **cat** ✓ | 0.906053 | 2.7e-6 |
| `img560-ann562` | dog dudoso | dog | dog | **dog** ✓ | 0.606288 | 1.4e-6 |
| `img263-ann299` | cat que el original confunde (caso límite) | cat | dog | **dog** ✓ | 0.544658 | 1.1e-6 |

**5/5 con la misma clase que el original.** Las 5 se eligieron de antemano para cubrir casos distintos: dos predicciones seguras, una media, una dudosa y un error del original con probabilidad cercana a 0.5. En ese último el ONNX repite el mismo error, que es lo esperado en una conversión fiel: la clase debe coincidir con el original, no con la etiqueta real. Las diferencias de logits son del orden de 1e-6, error de redondeo de float32.

Salidas completas: `verify_web_output.txt` y `resultados_web.json` (runtime web), y `export_output.txt` y `export_log.json` (exportación, con versiones). `inputs/expected.json` contiene las probabilidades y logits del original.

## Comandos usados

Desde esta carpeta, con `../mod-01/model/best.pt` presente (ver «Archivo de pesos» en `../mod-01/README.md`):

```bash
# 1. Exportar (Python; versiones en requirements.txt)
pip install -r requirements.txt
python export_onnx.py          # -> model/*.onnx, model/SHA256SUMS, inputs/, export_log.json

# 2. Verificar el hash
sha256sum -c model/SHA256SUMS  # (macOS: shasum -a 256 -c model/SHA256SUMS)

# 3. Cargar en el runtime web y comparar con el original
npm install                    # onnxruntime-web 1.22.0 (package.json / package-lock.json)
node verify_web.mjs            # 5/5 -> resultados_web.json; sale con código 1 si alguna no coincide
```

Para usar la copia del bucket en lugar de exportar:

```bash
aws s3 cp s3://mlops-p4-equipo-452857281704/models/dog-cat-resnet18/1.0.0/onnx/dog-cat-resnet18-1.0.0-fp32.onnx \
  model/ --region us-east-2 --profile <tu-perfil>
sha256sum -c model/SHA256SUMS
node verify_web.mjs
```

`export_onnx.py` no copia la arquitectura: importa `DogCatResNet18`, `CLASSES`, `PREPROCESS` y `load_model()` de `../mod-01/predict.py`, que además verifica el SHA-256 de `best.pt` antes de cargarlo. También pasa el `.onnx` por `onnx.checker` y lo compara con `onnxruntime` en Python.

## Qué compara y qué no

- `inputs/*.bin` son los tensores ya preprocesados con el `PREPROCESS` del original (los genera `export_onnx.py`). Así se compara **el modelo convertido** con el original, con exactamente la misma entrada.
- Lo que **no** se prueba aquí es el preprocesamiento en JavaScript (leer la imagen, resize 128×128 bilineal con antialias y normalizar). Ese paso se comprueba cuando el dispositivo edge procese imágenes de la cámara.
- Entorno de la exportación: Linux x86_64, Python 3.13.16 y CPU. Con torch/torchvision 2.14.0/0.29.0, las mismas del Proyecto 3, `../mod-01/predict.py --all` vuelve a dar 125/128 y los mismos 3 errores de MOD-1.
