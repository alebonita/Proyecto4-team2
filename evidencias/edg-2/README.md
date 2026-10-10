# EDG-2 — Clasificación local en la laptop edge

**Criterio del ticket:** cada captura muestra clase, confianza y tiempo en milisegundos, y el
programa sigue clasificando con la red apagada después de cargar el modelo.

Código: [`edge/classifier.py`](../../edge/classifier.py), [`edge/capture.py`](../../edge/capture.py)
y la prueba [`edge/tests/test_classifier.py`](../../edge/tests/test_classifier.py). Instalación y
uso: [`edge/README.md`](../../edge/README.md).

## Estado

| Comprobación | Estado |
|---|---|
| Variante INT8 oficial de MOD-3 cargada en la laptop edge (SHA-256 `9c28368a…`) | ✅ |
| Prueba con imágenes de validación conocidas y accuracy en las 128 | ✅ 5/5 pruebas |
| Captura → clase, confianza y ms en la terminal | ✅ por SSH |
| Captura → clase, confianza y ms en la **ventana** | ✅ consola física (`run_display.sh`) |
| Clasificación con la **red desconectada** | ✅ 4 capturas sin red, verificadas con el registro del sistema |
| Predicción que cambia con objetos de distintas clases | ✅ 8/8 correctas (4 perros, 4 gatos) |

## Modelo en la laptop edge

| | |
|---|---|
| Archivo | `edge/models/dog-cat-resnet18-1.0.0-int8.onnx` (11 367 590 bytes, no está en git) |
| SHA-256 | `9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd`, igual al de MOD-3 |
| Runtime | onnxruntime 1.30.0, `CPUExecutionProvider`, Python 3.14.4 |
| Equipo | MacBook Air 6,1, Intel Core i5-4260U (Haswell: AVX2, sin AVX-512 ni VNNI) |

`config.yaml` trae ese SHA-256: con otro archivo, el programa no arranca.

## Prueba física con y sin red (2026-10-10)

En la consola física de la laptop (`run_display.sh`, vista previa en su pantalla) se presentaron
fotos de perros y gatos en la pantalla de un celular dentro del recuadro verde. A mitad de la
prueba se desconectó el adaptador de red USB, la única conexión del equipo (no tiene wifi).

**Red desconectada de 19:44:06 a 19:46:08 UTC**, según el registro del sistema
(`journalctl`): el kernel registra la desconexión del adaptador, `systemd-networkd` reporta
`Lost carrier` y `DHCP lease lost`, no hay ningún `Gained carrier` ni dirección DHCP en ese
intervalo, y `tailscaled` falla con `network is unreachable` hasta las 19:46:22.

| Foto | Hora (UTC) | Red | Se ve | Clase | Confianza |
|---|---|---|---|---|---|
| [`capture_20261010_194112_397.jpg`](capturas/capture_20261010_194112_397.jpg) | 19:41:12 | con red | perro | dog | 1.0000 |
| [`capture_20261010_194233_417.jpg`](capturas/capture_20261010_194233_417.jpg) | 19:42:33 | con red | perro | dog | 0.9997 |
| [`capture_20261010_194325_916.jpg`](capturas/capture_20261010_194325_916.jpg) | 19:43:25 | con red | gato | cat | 0.9501 |
| [`capture_20261010_194348_901.jpg`](capturas/capture_20261010_194348_901.jpg) | 19:43:48 | con red | gato | cat | 0.7399 |
| [`capture_20261010_194433_016.jpg`](capturas/capture_20261010_194433_016.jpg) | 19:44:33 | **sin red** | gato | cat | 0.9992 |
| [`capture_20261010_194501_329.jpg`](capturas/capture_20261010_194501_329.jpg) | 19:45:01 | **sin red** | gato | cat | 0.9941 |
| [`capture_20261010_194523_024.jpg`](capturas/capture_20261010_194523_024.jpg) | 19:45:23 | **sin red** | perro | dog | 0.9979 |
| [`capture_20261010_194538_264.jpg`](capturas/capture_20261010_194538_264.jpg) | 19:45:38 | **sin red** | perro | dog | 0.7212 |

**8/8 correctas** y la clase cambia con el animal presentado. La salida de la terminal no se
guarda (eso llega con el historial de EDG-3), así que clase y confianza se reprodujeron después
sobre las mismas fotos con el mismo modelo, el mismo recorte (`crop_fraction: 0.8`) y el mismo
código; la inferencia es determinista. Las fotos guardadas son el cuadro completo, sin el
recuadro dibujado.

## Arranque y capturas por SSH (2026-10-10)

```
Modelo:      dog-cat-resnet18-1.0.0-int8.onnx
SHA-256:     9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd
Version:     dog-cat-resnet18-1.0.0-int8
onnxruntime: 1.30.0
Proveedor:   CPUExecutionProvider
Camara 0 lista. Las fotos se guardan en /home/steph/Proyecto4-team2/edge/captures
Modo sin ventana (no hay pantalla). Espacio: foto y clasificacion. q: salir.
Foto guardada: /home/steph/Proyecto4-team2/edge/captures/capture_20261010_192926_749.jpg
  Clase: cat  confianza: 0.9402  tiempo: 19.9 ms (preprocesamiento + inferencia)
Foto guardada: /home/steph/Proyecto4-team2/edge/captures/capture_20261010_192929_758.jpg
  Clase: cat  confianza: 0.9501  tiempo: 15.0 ms (preprocesamiento + inferencia)
```

La cámara apuntaba al techo, así que la clase no significa nada aquí; lo que se comprueba es
que cada captura imprime clase, confianza y tiempo. Al cargar el modelo se hace una
clasificación de calentamiento: sin ella, la primera captura marcaba 71–84 ms porque incluía la
preparación de onnxruntime y de Pillow. La latencia se mide formalmente en EDG-5.

## Prueba

```
$ python -m unittest discover -s tests -v
test_classifies_without_network ... ok
test_known_validation_images ... ok
test_validation_accuracy_within_rubric_limit ... ok
test_center_crop_fits_the_frame ... ok
test_converts_bgr_to_rgb_and_normalizes ... ok

Ran 5 tests in 2.340s
OK
```

- `test_known_validation_images`: las 5 imágenes de MOD-2/MOD-3 (dos seguras, una media, una
  dudosa y un error del modelo) dan la clase del original.
- `test_validation_accuracy_within_rubric_limit`: en las 128 de validación, la accuracy medida
  **en este equipo** no cae más de 2 puntos porcentuales respecto al original.
- `test_classifies_without_network`: la clasificación corre con los sockets bloqueados.
- `test_converts_bgr_to_rgb_and_normalizes`: un píxel azul en BGR llega al canal 2 (B) del tensor.

## Calidad en la laptop edge: el INT8 depende del CPU

Las 128 predicciones del INT8 en la laptop edge están en
[`predicciones_validacion_edge.csv`](predicciones_validacion_edge.csv), junto a las del original
y las de MOD-4 (mismo archivo INT8, otra computadora):

| | Accuracy | Caída vs original | Errores |
|---|---|---|---|
| Original (PyTorch, MOD-1) | 125/128 (0.9766) | — | img131, img263, img633 |
| INT8 en la computadora de MOD-4 | 125/128 (0.9766) | 0.00 pp | img131, img263, img633 |
| **INT8 en la laptop edge** | **124/128 (0.9688)** | **0.78 pp** | img106, img263, img289, img633 |

La caída queda dentro del límite de 2 puntos de la rúbrica, pero **tres recortes cambian de clase
respecto a MOD-4** con el mismo archivo:

| Recorte | Real | INT8 en MOD-4 | INT8 en la laptop edge | P(dog) en la laptop |
|---|---|---|---|---|
| `img106-ann134` | dog | dog | cat | 0.194 |
| `img131-ann149` | cat | dog | cat | 0.361 |
| `img289-ann331` | dog | dog | cat | 0.110 |

**Causa.** En CPUs x86 con AVX2 y sin VNNI, como este i5 de 2014, onnxruntime multiplica
activaciones uint8 por pesos int8 con una instrucción (`vpmaddubsw`) cuya suma intermedia de 16
bits se satura. La documentación de cuantización de onnxruntime recomienda `reduce_range` (pesos
de 7 bits) para esos CPUs. En una Mac M3 el mismo archivo da exactamente los resultados de MOD-4.

**Comprobación.** Desde el fp32 oficial se cuantizaron tres variantes con la configuración de MOD-3,
cambiando solo lo indicado, y se midieron en la laptop edge contra el fp32 en la misma máquina
(latencia: 10 de calentamiento y 100 medidas, solo inferencia):

| En la laptop edge | Accuracy | Misma clase que fp32 | máx. \|Δ P(dog)\| vs fp32 | p50 | p95 |
|---|---|---|---|---|---|
| fp32 oficial (MOD-2) | 125/128 | 128/128 | — | 11.4 ms | 11.9 ms |
| **INT8 oficial (MOD-3, U8S8)** | 124/128 | 125/128 | 0.885 | 9.4 ms | 9.8 ms |
| U8S8 regenerado en Mac | 124/128 | 125/128 | 0.885 | 9.3 ms | 10.5 ms |
| S8S8 | 124/128 | 125/128 | 0.885 | 15.3 ms | 16.8 ms |
| **U8S8 con `reduce_range=True`** | 126/128 | **127/128** | **0.210** | 9.3 ms | 9.9 ms |

`reduce_range` reduce la desviación de 0.885 a 0.210 sin perder velocidad, lo que confirma que la
causa es la saturación. S8S8 no ayuda en este CPU y es más lento. Cambiar la variante es decisión
de MOD-3 (ver el PR de EDG-2); mientras tanto la laptop usa el INT8 oficial, que cumple la rúbrica.

## Preprocesamiento: por qué Pillow y no el resize de OpenCV

El original redimensiona con torchvision (`Resize(128, antialias=True)`). Sin PyTorch en la laptop,
se compararon dos formas de replicarlo contra las probabilidades del original en PyTorch
(`prob_original_dog` de MOD-4), con las 128 imágenes de validación y el fp32:

| Redimensión | máx. \|Δ P(dog)\| | media |
|---|---|---|
| **Pillow, bilineal** (la que usa `classifier.py`) | **0.0023** | 0.00009 |
| OpenCV `INTER_LINEAR` | 0.4995 | 0.0179 |

El filtro bilineal de Pillow aplica antialias, igual que torchvision con `antialias=True`; el de
OpenCV no, y llega a mover la probabilidad casi 0.5.
