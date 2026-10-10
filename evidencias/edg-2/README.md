# EDG-2 — Clasificación local en la laptop edge

**Criterio del ticket:** cada captura muestra clase, confianza y tiempo en milisegundos, y el
programa sigue clasificando con la red apagada después de cargar el modelo.

Código: [`edge/classifier.py`](../../edge/classifier.py), [`edge/capture.py`](../../edge/capture.py)
y la prueba [`edge/tests/test_classifier.py`](../../edge/tests/test_classifier.py). Instalación y
uso: [`edge/README.md`](../../edge/README.md).

## Estado

| Comprobación | Estado |
|---|---|
| Prueba con imágenes de validación conocidas (5 + las 128) | ✅ en la laptop edge, con un ONNX fp32 de prueba |
| Captura → clase, confianza y ms en la terminal | ✅ en la laptop edge, por SSH |
| Modelo cargado, SHA-256, versión, onnxruntime y proveedor al arrancar | ✅ |
| Lo mismo con la **variante INT8 oficial** de MOD-3 (`9c28368a…`) | ⏳ pendiente: falta el archivo en la laptop |
| Clasificación con la **red desconectada**, en la consola física | ⏳ pendiente |

El ticket permite empezar con cualquier ONNX y cambiar a la variante real cuando esté lista: la
ruta, la versión y el SHA-256 del modelo salen de `config.yaml`.

## Modelo de prueba

Mientras llega el INT8 oficial se usó el ONNX fp32 regenerado con `evidencias/mod-02/export_onnx.py`
desde `best.pt` (SHA-256 `84d6c88b…`, verificado) en una Mac arm64. Da las mismas clases que el
original, pero no es idéntico byte a byte al de MOD-2 (`9e9ef251…` en lugar de `6628f3cf…`): los
logits cambian en el sexto decimal entre arm64 y Linux x86_64. Por eso **no** sirve como evidencia
del modelo desplegado, solo para probar el código.

## Prueba en la laptop edge (2026-10-10)

Python 3.14.4, onnxruntime 1.30.0, `CPUExecutionProvider`:

```
$ EDGE_CONFIG=/tmp/prueba-config.yaml python -m unittest discover -s tests -v
test_all_validation_images_match_reference ... ok
test_classifies_without_network ... ok
test_known_validation_images ... ok
test_center_crop_fits_the_frame ... ok
test_converts_bgr_to_rgb_and_normalizes ... ok

Ran 5 tests in 2.826s
OK
```

- `test_known_validation_images`: las 5 imágenes de MOD-2/MOD-3 (dos seguras, una media, una
  dudosa y un error del modelo) dan la clase de referencia de MOD-4.
- `test_all_validation_images_match_reference`: las 128 de validación, 128/128.
- `test_classifies_without_network`: la clasificación corre con los sockets bloqueados.
- `test_converts_bgr_to_rgb_and_normalizes`: un píxel azul en BGR llega al canal 2 (B) del tensor.

Captura con la cámara, por SSH:

```
Modelo:      prueba-fp32-mac.onnx
SHA-256:     9e9ef251087d7cbcbfdd9639aaacab3fb24bcbb47209c8b4038d54293d4ef3e6
Version:     prueba-fp32-mac
onnxruntime: 1.30.0
Proveedor:   CPUExecutionProvider
Camara 0 lista. Las fotos se guardan en /home/steph/Proyecto4-team2/edge/captures
Modo sin ventana (no hay pantalla). Espacio: foto y clasificacion. q: salir.
Foto guardada: ...
  Clase: cat  confianza: 0.9217  tiempo: 21.9 ms (preprocesamiento + inferencia)
Foto guardada: ...
  Clase: cat  confianza: 0.9073  tiempo: 15.3 ms (preprocesamiento + inferencia)
Foto guardada: ...
  Clase: cat  confianza: 0.9144  tiempo: 26.4 ms (preprocesamiento + inferencia)
```

La cámara apuntaba al techo, así que la clase no significa nada aquí; lo que se comprueba es
que cada captura imprime clase, confianza y tiempo. Al cargar el modelo se hace una
clasificación de calentamiento: sin ella, la primera captura marcaba 71–84 ms porque incluía
la preparación de onnxruntime y de Pillow. La latencia se mide formalmente en EDG-5.

## Preprocesamiento: por qué Pillow y no el resize de OpenCV

El original redimensiona con torchvision (`Resize(128, antialias=True)`). Sin PyTorch en la laptop,
se compararon dos formas de replicarlo contra las probabilidades del original en PyTorch
(`prob_original_dog` de MOD-4), con las 128 imágenes de validación:

| Redimensión | máx. \|Δ P(dog)\| | media |
|---|---|---|
| **Pillow, bilineal** (la que usa `classifier.py`) | **0.0023** | 0.00009 |
| OpenCV `INTER_LINEAR` | 0.4995 | 0.0179 |

El filtro bilineal de Pillow aplica antialias, igual que torchvision con `antialias=True`; el de
OpenCV no, y llega a mover la probabilidad casi 0.5.
