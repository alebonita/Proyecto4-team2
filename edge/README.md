# Dispositivo edge: captura y clasificación local (EDG-1, EDG-2)

Programa que abre la webcam y, al presionar la barra espaciadora, guarda una foto JPEG
y clasifica el objeto en la propia laptop con el modelo optimizado (ONNX INT8) y
onnxruntime en CPU, sin llamar a ningún servidor. Es la parte "cámara y clasificación
local" del recorrido del Proyecto 4. Depende de OpenCV, NumPy, PyYAML, onnxruntime y
Pillow; no incluye PyTorch ni nada de entrenamiento.

Hardware de referencia: MacBook Air Intel con Ubuntu Server y una webcam USB
Acteck HD (UVC). Los datos exactos del equipo salen de `python device_info.py`.

## Contenido

| Archivo | Para qué sirve |
|---|---|
| `capture.py` | Vista previa, captura de fotos y clasificación |
| `classifier.py` | Carga del modelo ONNX, preprocesamiento e inferencia local |
| `tests/` | Prueba con imágenes de validación conocidas |
| `run_display.sh` | Arranca `capture.py` con vista previa en la pantalla del equipo (consola física) |
| `config.yaml` | Cámara, carpeta de salida, recorte, modelo y preprocesamiento |
| `device_info.py` | Imprime marca y modelo, procesador, RAM, sistema operativo y cámaras |
| `requirements.txt` | Dependencias con versiones fijas |

## Instalación desde cero (Ubuntu Server 24.04 o superior)

Requiere Python 3.12 o superior. Las versiones fijadas de `requirements.txt` tienen
paquetes binarios para Python 3.12 a 3.14 en Linux x86_64, así que no se compila nada.

**1. Paquetes del sistema.** OpenCV necesita dos bibliotecas que Ubuntu Server no trae
(`libgl1` y `libglib2.0-0`), y `git` sirve para descargar el repositorio:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip libgl1 libglib2.0-0
python3 --version
```

La última línea debe mostrar 3.12 o superior.

**2. Descarga el repositorio:**

```bash
git clone https://github.com/alebonita/Proyecto4-team2.git
cd Proyecto4-team2
```

**3. Permiso para usar la cámara.** El dispositivo `/dev/video0` pertenece al grupo
`video`. Por SSH tu usuario no recibe ese permiso solo:

```bash
sudo usermod -aG video $USER
```

Cierra la sesión SSH y vuelve a entrar. Comprueba que aparece `video`:

```bash
groups
```

**4. Conecta la webcam y confirma que el sistema la ve:**

```bash
ls /dev/video*
```

Debe aparecer al menos `/dev/video0`.

**5. Entorno virtual y dependencias**, dentro de la carpeta `edge/` del repositorio:

```bash
cd edge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**6. Modelo.** El `.onnx` no está en git (pesa 10.8 MB). Es la variante INT8 de MOD-3,
`dog-cat-resnet18-1.0.0-int8.onnx`, que está en el bucket del equipo. En una computadora
con acceso a ese bucket:

```bash
aws s3 cp s3://mlops-p4-equipo-452857281704/models/dog-cat-resnet18/1.0.0/onnx/dog-cat-resnet18-1.0.0-int8.onnx . \
  --region us-east-2 --profile <tu-perfil>
shasum -a 256 dog-cat-resnet18-1.0.0-int8.onnx
# 9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd
```

Cópialo a `edge/models/` en la laptop edge (por ejemplo con
`scp dog-cat-resnet18-1.0.0-int8.onnx usuario@equipo-edge:ruta/al/repo/edge/models/`).
`config.yaml` trae ese SHA-256: si el archivo es otro, el programa no arranca. También se
puede regenerar idéntico con el script de MOD-3 (`evidencias/mod-03/README.md`).

**7. Prueba del modelo.** Clasifica recortes de validación conocidos y compara con las
predicciones de MOD-4; incluye las 128 imágenes de validación y una corrida con la red
bloqueada:

```bash
python -m unittest discover -s tests -v
```

Deben pasar las 5 pruebas.

**8. Datos del equipo (para la ficha de entrega):**

```bash
python device_info.py
```

**9. Arranque por SSH (sin ventana):**

```bash
python capture.py
```

**10. Vista previa en la pantalla del equipo.** Ubuntu Server no tiene escritorio, así
que para ver la cámara en vivo se instala un servidor gráfico mínimo (Xorg y el gestor
de ventanas openbox, sin escritorio ni inicio de sesión gráfico). No arranca solo con el
sistema ni consume recursos mientras no se use:

```bash
sudo apt install -y --no-install-recommends xserver-xorg xinit openbox
```

Luego, **con el teclado y la pantalla del equipo** (no por SSH), inicia sesión y corre:

```bash
Proyecto4-team2/edge/run_display.sh
```

Se abre la ventana con la cámara; con `q` se cierra y se vuelve a la consola de texto.
Este es el modo para la demostración: no depende de la red, así que sigue funcionando
al desconectar el cable de red, mientras que una sesión SSH se corta.

## Uso

| Tecla | Acción |
|---|---|
| Barra espaciadora | Guarda el cuadro actual en `captures/capture_AAAAMMDD_HHMMSS_mmm.jpg` y clasifica el recorte |
| `q` | Cierra el programa |

Al arrancar imprime qué modelo cargó, para poder demostrarlo:

```
Modelo:      dog-cat-resnet18-1.0.0-int8.onnx
SHA-256:     9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd
Version:     dog-cat-resnet18-1.0.0-int8
onnxruntime: 1.30.0
Proveedor:   CPUExecutionProvider
```

Cada captura imprime la clase, la confianza (softmax, entre 0 y 1) y los milisegundos de
preprocesamiento más inferencia:

```
Foto guardada: .../captures/capture_20261010_011010_237.jpg
  Clase: cat  confianza: 0.9133  tiempo: 23.6 ms (preprocesamiento + inferencia)
```

Se clasifica un **recorte fijo**: el cuadrado verde de la vista previa (por defecto,
centrado y con el 80 % del lado corto del cuadro). El objeto se presenta dentro de ese
recuadro, porque el modelo se entrenó con recortes de un solo objeto. La foto guardada es
el cuadro completo, sin el recuadro dibujado. En la ventana, el último resultado queda
arriba a la izquierda.

La clasificación es local: la sesión de onnxruntime se crea una vez al arrancar, solo con
`CPUExecutionProvider`, y no hay llamadas de red. Sigue funcionando con la red
desconectada.

El preprocesamiento replica el del modelo original (`evidencias/mod-01/README.md`):
recorte, BGR → RGB, redimensión directa a 128 × 128 bilineal con antialias, división
entre 255 y normalización con la media y desviación de ImageNet. La redimensión usa
Pillow porque es el filtro que torchvision replica con `antialias=True`; el `resize` de
OpenCV no aplica antialias y llega a cambiar la probabilidad hasta 0.5.

El programa elige el modo según el equipo:

- **Con pantalla** (`run_display.sh` en la consola física, o un equipo con escritorio):
  abre una ventana con la vista previa en vivo. Las teclas se presionan con la ventana
  en foco.
- **Sin pantalla** (Ubuntu Server, SSH): no existe una ventana donde dibujar, así que
  lee las teclas de la terminal mientras la cámara sigue capturando cuadros. No se ve
  la imagen en vivo; el resultado se comprueba abriendo las fotos de `captures/`.
  Se puede forzar con `python capture.py --headless`.

Cada foto guardada imprime su ruta. Para revisarlas desde otra computadora:

```bash
scp 'usuario@equipo-edge:ruta/al/repo/edge/captures/*.jpg' .
```

## Configuración (`config.yaml`)

| Clave | Valor por defecto | Descripción |
|---|---|---|
| `camera_index` | `0` | Cámara a usar: `0` es `/dev/video0` |
| `output_dir` | `captures` | Carpeta de las fotos. Una ruta relativa se toma desde `edge/` |
| `jpeg_quality` | `95` | Calidad JPEG de 1 a 100 |
| `preview` | `auto` | `auto`, `true` o `false` |
| `warmup_frames` | `5` | Cuadros descartados al abrir (ajuste de exposición) |
| `width`, `height` | vacío | Resolución opcional; se definen las dos o ninguna |
| `crop_fraction` | `0.8` | Lado del recorte que se clasifica, como fracción del lado corto del cuadro |
| `model.path` | `models/dog-cat-resnet18-1.0.0-int8.onnx` | Archivo ONNX. Una ruta relativa se toma desde `edge/` |
| `model.version` | `dog-cat-resnet18-1.0.0-int8` | Versión que se imprime y se registra con cada captura |
| `model.sha256` | el de la variante INT8 | Si no coincide, el programa no arranca. Vacío: no se comprueba |
| `model.classes` | `[dog, cat]` | Clases en el orden de salida del modelo |
| `preprocess.*` | 128, RGB, ImageNet | Tamaño de entrada, orden de canales, media y desviación |

Para probar otro ONNX sin tocar `config.yaml`, copia el archivo, cambia `model.*` y
arranca con `python capture.py --config otra-config.yaml`.

## Problemas frecuentes

| Mensaje o síntoma | Causa y solución |
|---|---|
| `No existe ningun /dev/video*` | El sistema no detecta la cámara. Revisa el puerto USB y busca la webcam con `lsusb` |
| `Sin permiso sobre /dev/video0` | Falta el grupo `video`: paso 3 y volver a entrar por SSH |
| `No se pudo abrir la camara con indice 0` pero existe `/dev/video0` | Otro proceso la usa, o el índice es otro: prueba `camera_index: 1` |
| `No se pudo importar OpenCV ... libGL.so.1` | Falta `libgl1`: paso 1 |
| `No existe el modelo .../models/...onnx` | Falta el paso 6: copia el `.onnx` a `edge/models/` |
| `... no es el modelo esperado: SHA-256 ...` | El archivo no es la variante INT8 de MOD-3. Vuelve a bajarlo y comprueba su SHA-256 |
| `Falta onnxruntime` | El entorno virtual no está activo o faltan dependencias: paso 5 |
| `ModuleNotFoundError` o `Falta PyYAML` | El entorno virtual no está activo: `source .venv/bin/activate` |
| `Ejecuta este script desde la consola fisica` | `run_display.sh` se corrió por SSH. Córrelo con el teclado del equipo, o usa `python capture.py` por SSH |
| `Faltan xinit u openbox` | Falta el paso 10 |
| La pantalla del equipo está en negro | La consola se apaga sola: presiona una tecla. Si sigue en negro, el brillo está en 0 (ver abajo) |
| `El modo sin ventana necesita una terminal interactiva` | Se ejecutó sin terminal (por ejemplo con `nohup` o redirecciones). Ejecútalo directo en la sesión SSH |

## Verificación en el dispositivo

Con el entorno instalado solo con estos pasos, `python capture.py` abre la cámara y,
al presionar la barra espaciadora, aparece un JPEG nuevo en `captures/`:

```bash
ls -l captures/
```

Verificado el 2026-10-09 en el dispositivo edge, instalando desde cero con estos pasos:

| Dato | Valor (`python device_info.py`) |
|---|---|
| Marca y modelo | Apple MacBook Air (MacBookAir6,1) |
| Procesador | Intel Core i5-4260U @ 1.40GHz, 2 núcleos físicos, 4 lógicos |
| Memoria RAM | 3.3 GiB visibles para el sistema |
| Sistema operativo | Ubuntu 26.04.1 LTS (kernel 7.0.0-38-generic, x86_64) |
| Cámara | Webcam USB externa Acteck HD (UVC, chip IMC Networks `13d3:784b`, se anuncia como "Integrated Camera"); 640×480 en `/dev/video0`. La FaceTime HD interna no tiene driver en Ubuntu y no aparece como `/dev/video*` |
| Python | 3.14.4 |

Probados los dos modos: sin ventana por SSH (`python capture.py`) y con vista previa
en la pantalla del equipo (`run_display.sh`). En ambos, la barra espaciadora guarda una
foto de 640×480 en `captures/` y `q` cierra el programa.

**Pantalla de este equipo.** La laptop trabaja como servidor encendido todo el tiempo y
un servicio (`backlight-off.service`) pone el brillo en 0 al arrancar. Para la demo se
prende desde SSH y se apaga al terminar; al reiniciar vuelve a apagarse sola:

```bash
echo 80 | sudo tee /sys/class/backlight/acpi_video0/brightness   # prender
sudo systemctl start backlight-off                               # apagar
```

Evidencia de la verificación (fotos y datos del equipo): [`evidencias/edg-1/`](../evidencias/edg-1/README.md).
