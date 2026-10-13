"""EDG-1 a EDG-6: captura, clasificacion local, historial y envio a AWS desde el edge.

Abre la webcam con OpenCV. Al presionar una tecla guarda el cuadro actual como JPEG y
clasifica el recorte fijo marcado en la vista previa con el modelo ONNX local
(classifier.py), sin ninguna llamada de red:

- Barra espaciadora: guarda la foto y muestra clase, confianza y milisegundos.
- q: cierra el programa.

Al arrancar imprime el archivo del modelo, su SHA-256, la version, la version de
onnxruntime y el proveedor de ejecucion.

Cada captura clasificada queda como evento en el historial SQLite (events.py): ID unico,
fecha con zona horaria, dispositivo, version del modelo, clase, confianza, ms, recorte,
foto y estado de envio. export_events.py y list_events.py lo consultan.

Cada evento se envia a AWS en un hilo aparte (sender.py): la captura y la clasificacion
no esperan a la red y siguen funcionando sin ella. Si el envio falla, el evento queda en
error y se reenvia con el mismo capture_id con retry.py. --simular-fallo manda los
envios a una URL donde nada escucha, para demostrar el fallo y el reintento.

Para operar de forma continua (EDG-6): la tecla i activa o detiene una captura cada
capture_interval_s segundos; si la camara se desconecta, el programa la reabre solo; un
error de camara, inferencia, historial o envio se muestra y el programa sigue; y todo
queda en el archivo de registro log_file (operation.py).

Hay dos modos, y se elige solo:

- Con ventana: si el equipo tiene pantalla, muestra la vista previa en vivo.
- Sin pantalla (por ejemplo Ubuntu Server por SSH): no hay donde dibujar una
  ventana, asi que las teclas se leen de la terminal y la camara sigue
  capturando cuadros en segundo plano. Se puede forzar con --headless.

Camara, carpeta de salida, modelo, clases, preprocesamiento y recorte salen de
config.yaml.

Codigos de salida: 0 normal, 1 camara, modelo o ejecucion, 2 configuracion.
"""

from __future__ import annotations

import argparse
import glob
import os
import select
import sys
import time
from pathlib import Path

from operation import Heartbeat, IntervalTrigger, log, report, setup_logging

EDGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = EDGE_DIR / "config.yaml"
WINDOW_TITLE = "Captura edge - espacio: foto, i: intervalo, q: salir"
KEY_SPACE = " "
KEY_QUIT = "q"
KEY_INTERVAL = "i"
RECONNECT_SECONDS = 2.0
ERROR_PAUSE_SECONDS = 0.5
MAX_CONSECUTIVE_READ_FAILURES = 30
POLL_SECONDS = 0.03


class ConfigError(Exception):
    """config.yaml falta, no se puede leer o tiene valores invalidos."""


class CameraError(Exception):
    """La camara no esta disponible o dejo de entregar imagen."""


def _is_int(value: object, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def load_config(path: Path) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError(
            "Falta PyYAML. Activa el entorno virtual e instala las dependencias: "
            "pip install -r requirements.txt"
        ) from exc

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"No existe el archivo de configuracion: {path}") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ConfigError(f"No se pudo leer {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} no es un YAML valido: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path} debe ser un mapa de clave: valor.")

    config = {
        "camera_index": raw.get("camera_index", 0),
        "output_dir": raw.get("output_dir", "captures"),
        "jpeg_quality": raw.get("jpeg_quality", 95),
        "preview": raw.get("preview", "auto"),
        "warmup_frames": raw.get("warmup_frames", 5),
        "width": raw.get("width"),
        "height": raw.get("height"),
        "crop_fraction": raw.get("crop_fraction", 0.8),
        "device_id": raw.get("device_id"),
        "events_db": raw.get("events_db", "events.db"),
        "log_file": raw.get("log_file", "logs/edge.log"),
        "capture_interval_s": raw.get("capture_interval_s", 10),
    }
    if not _is_int(config["camera_index"], 0):
        raise ConfigError("camera_index debe ser un entero mayor o igual a 0 (ej. 0).")
    if not isinstance(config["output_dir"], str) or not config["output_dir"].strip():
        raise ConfigError("output_dir debe ser un texto no vacio (ej. captures).")
    if not _is_int(config["jpeg_quality"], 1) or config["jpeg_quality"] > 100:
        raise ConfigError("jpeg_quality debe ser un entero entre 1 y 100.")
    if not (config["preview"] == "auto" or isinstance(config["preview"], bool)):
        raise ConfigError("preview debe ser auto, true o false.")
    if not _is_int(config["warmup_frames"], 0):
        raise ConfigError("warmup_frames debe ser un entero mayor o igual a 0.")
    for key in ("width", "height"):
        if config[key] is not None and not _is_int(config[key], 1):
            raise ConfigError(f"{key} debe ser un entero positivo o quedar vacio.")
    if (config["width"] is None) != (config["height"] is None):
        raise ConfigError("width y height se definen juntos, o ninguno de los dos.")
    fraction = config["crop_fraction"]
    if (
        isinstance(fraction, bool)
        or not isinstance(fraction, (int, float))
        or not 0 < fraction <= 1
    ):
        raise ConfigError("crop_fraction debe ser un numero mayor que 0 y hasta 1 (ej. 0.8).")
    device_id = config["device_id"]
    if not isinstance(device_id, str) or not device_id.strip() or len(device_id) > 128:
        raise ConfigError("device_id debe ser un texto de 1 a 128 caracteres (ej. edge-mba-01).")
    config["device_id"] = device_id.strip()
    if not isinstance(config["events_db"], str) or not config["events_db"].strip():
        raise ConfigError("events_db debe ser la ruta del historial (ej. events.db).")
    events_db = Path(config["events_db"]).expanduser()
    config["events_db"] = events_db if events_db.is_absolute() else path.parent / events_db
    if not isinstance(config["log_file"], str) or not config["log_file"].strip():
        raise ConfigError("log_file debe ser la ruta del archivo de registro (ej. logs/edge.log).")
    log_file = Path(config["log_file"]).expanduser()
    config["log_file"] = log_file if log_file.is_absolute() else path.parent / log_file
    interval = config["capture_interval_s"]
    if interval is not None and (
        isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval < 1
    ):
        raise ConfigError("capture_interval_s debe ser un numero de segundos >= 1 o quedar vacio.")

    try:
        from classifier import parse_model_config
    except ImportError as exc:
        raise ConfigError(
            f"Falta una dependencia ({exc}). Activa el entorno virtual e instala las "
            "dependencias: pip install -r requirements.txt"
        ) from exc
    try:
        config["model"] = parse_model_config(raw.get("model"), raw.get("preprocess"), path.parent)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    from sender import parse_upload_config

    try:
        config["upload"] = parse_upload_config(raw.get("upload"))
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc

    output_dir = Path(config["output_dir"]).expanduser()
    config["output_dir"] = output_dir if output_dir.is_absolute() else path.parent / output_dir
    return config


def camera_hint(index: int) -> str:
    """Mensaje accionable cuando la camara no abre."""
    lines = [f"No se pudo abrir la camara con indice {index}."]
    if sys.platform.startswith("linux"):
        devices = sorted(glob.glob("/dev/video*"))
        if not devices:
            lines.append(
                "No existe ningun /dev/video*: el sistema no detecta una camara. "
                "Revisa que la webcam este conectada a un puerto USB y busca su nombre con: lsusb"
            )
        else:
            lines.append(f"Dispositivos de video encontrados: {', '.join(devices)}")
            lines.append(
                "Si el indice no es el correcto, cambia camera_index en config.yaml "
                "(/dev/video0 es el indice 0). Muchas webcams crean dos nodos y solo el "
                "primero captura."
            )
            blocked = [d for d in devices if not os.access(d, os.R_OK | os.W_OK)]
            if blocked:
                lines.append(
                    f"Sin permiso sobre {', '.join(blocked)}. Agrega tu usuario al grupo video: "
                    "sudo usermod -aG video $USER y vuelve a abrir la sesion SSH."
                )
    else:
        lines.append(
            "Revisa que la camara este conectada, que ningun otro programa la use "
            "y que el sistema le haya dado permiso a la terminal."
        )
    lines.append("Tambien puede estar ocupada por otro proceso (otra instancia de este programa).")
    return "\n".join(lines)


def open_camera(cv2, index: int, width: int | None, height: int | None, warmup_frames: int):
    backend = cv2.CAP_V4L2 if sys.platform.startswith("linux") else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        raise CameraError(camera_hint(index))
    if width and height:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    # Los primeros cuadros salen oscuros mientras la camara ajusta exposicion.
    for _ in range(warmup_frames):
        cap.read()
    ok, _frame = cap.read()
    if not ok:
        cap.release()
        raise CameraError(
            f"La camara {index} abrio pero no entrega imagen. "
            "Desconecta y vuelve a conectar la webcam, o prueba otro camera_index."
        )
    return cap


def read_frame(cap, failures: list[int]):
    """Un cuadro; tolera fallos sueltos y se rinde tras demasiados seguidos."""
    ok, frame = cap.read()
    if ok:
        failures[0] = 0
        return frame
    failures[0] += 1
    if failures[0] >= MAX_CONSECUTIVE_READ_FAILURES:
        raise CameraError(
            "La camara dejo de entregar imagen (se desconecto o la uso otro programa)."
        )
    return None


class FrameSaver:
    def __init__(self, cv2, output_dir: Path, quality: int):
        self._cv2 = cv2
        self._dir = output_dir
        self._quality = quality
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CameraError(
                f"No se pudo crear la carpeta de capturas {output_dir}: {exc}"
            ) from exc

    def save(self, frame, name: str) -> Path:
        path = self._dir / name
        ok = self._cv2.imwrite(str(path), frame, [self._cv2.IMWRITE_JPEG_QUALITY, self._quality])
        if not ok or not path.is_file():
            raise CameraError(
                f"No se pudo guardar la foto en {path}. Revisa permisos y espacio en disco."
            )
        return path


class Capturer:
    """Guarda la foto, la clasifica en local, registra el evento y recuerda el resultado."""

    def __init__(
        self, saver: FrameSaver, classifier, crop_fraction: float, store, device_id, uploader=None
    ):
        self._saver = saver
        self._classifier = classifier
        self._crop_fraction = crop_fraction
        self._store = store
        self._device_id = device_id
        self._uploader = uploader
        self.last_text: str | None = None
        self.last_failed = False
        self.count = 0

    def status_lines(self) -> list[tuple[str, bool]]:
        """Lineas de la ventana: ultimo resultado local y ultimo envio, con su estado."""
        lines = [(self.last_text, self.last_failed)]
        if self._uploader is not None:
            lines.append((self._uploader.last_text, self._uploader.last_failed))
        return [(text, failed) for text, failed in lines if text]

    def crop_for(self, frame) -> tuple[int, int, int, int]:
        from classifier import center_crop

        height, width = frame.shape[:2]
        return center_crop(width, height, self._crop_fraction)

    def capture(self, frame) -> None:
        from classifier import sha256_of
        from events import Event, new_capture_id, now_iso

        # El ID y la fecha se generan una sola vez por captura y nombran la foto.
        capture_id, captured_at = new_capture_id(), now_iso()
        stamp = captured_at[:23].translate(str.maketrans("T.", "__", "-:"))
        try:
            path = self._saver.save(frame, f"capture_{stamp}_{capture_id}.jpg")
        except CameraError as exc:  # disco lleno o sin permiso: se avisa y el programa sigue
            self._fail(f"Error al guardar la foto: {exc}")
            return
        self.count += 1
        report(f"Foto guardada: {path}")
        crop = self.crop_for(frame)
        try:
            pred = self._classifier.classify(frame, crop)
        except Exception as exc:  # la inferencia falla: se avisa y el programa sigue
            self._fail(f"Error de inferencia: {exc}")
            return
        report(
            f"  Clase: {pred.label}  confianza: {pred.confidence:.4f}  "
            f"tiempo: {pred.latency_ms:.1f} ms (preprocesamiento + inferencia)"
        )
        self.last_text = f"{pred.label}  {pred.confidence:.2f}  {pred.latency_ms:.0f} ms"
        self.last_failed = False

        event = Event(
            capture_id=capture_id,
            captured_at=captured_at,
            device_id=self._device_id,
            model_version=self._classifier.cfg.version,
            predicted_class=pred.label,
            confidence=pred.confidence,
            latency_ms=pred.latency_ms,
            crop=crop,
            photo_path=_relative_to_edge(path),
            photo_sha256=sha256_of(path),
        )
        try:
            self._store.add(event)
        except Exception as exc:  # el historial falla: se avisa y el programa sigue
            self._fail(f"Error del historial: {exc}")
            return
        report(f"  Evento: {capture_id}  {captured_at}  estado: {event.status}")
        if self._uploader is not None:
            self._uploader.submit(capture_id)

    def _fail(self, message: str) -> None:
        self.last_text, self.last_failed = message, True
        report(f"  {message}", error=True)


class Camera:
    """La camara del programa: si deja de entregar imagen, la libera y la reabre sola."""

    def __init__(self, cv2, config: dict):
        self._cv2 = cv2
        self._config = config
        self.cap = self._open()  # al arrancar, un error de camara si detiene el programa
        self.error: str | None = None
        self._failures = [0]
        self._retry_at = 0.0

    def _open(self):
        c = self._config
        return open_camera(
            self._cv2, c["camera_index"], c["width"], c["height"], c["warmup_frames"]
        )

    def read(self):
        """Un cuadro, o None mientras la camara esta desconectada (se reintenta sola)."""
        now = time.monotonic()
        if self.cap is None:
            if now < self._retry_at:
                return None
            try:
                self.cap = self._open()
            except CameraError:
                self._retry_at = now + RECONNECT_SECONDS
                return None
            self._failures, self.error = [0], None
            report("Camara reconectada.")
        try:
            return read_frame(self.cap, self._failures)
        except CameraError as exc:
            self.error = "Error de camara: no entrega imagen. Reintentando..."
            report(f"{self.error} ({exc})", error=True)
            self.release()
            self._retry_at = now + RECONNECT_SECONDS
            return None

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class Uploader:
    """Envia los eventos en un hilo aparte: captura y clasificacion no esperan a la red."""

    def __init__(self, cfg, db_path: Path, key: str | None):
        import queue
        import threading

        self._cfg = cfg
        self._db_path = db_path
        self._key = key
        self._queue: queue.Queue[str | None] = queue.Queue()
        self.last_text: str | None = None
        self.last_failed = False
        self._thread = threading.Thread(target=self._run, name="envio-aws", daemon=True)
        self._thread.start()

    def submit(self, capture_id: str) -> None:
        self._queue.put(capture_id)

    def close(self, timeout: float) -> None:
        """Espera los envios en curso hasta `timeout` s; los que no salgan quedan pendientes."""
        if not self._queue.empty():
            report("Esperando los envios en curso...")
        self._queue.put(None)
        self._thread.join(timeout)

    def _run(self) -> None:
        from events import EventStore
        from sender import describe, send_and_record, short_status

        with EventStore(self._db_path) as store:  # conexion propia de este hilo
            while (capture_id := self._queue.get()) is not None:
                try:
                    event = store.get(capture_id)
                    result = send_and_record(store, event, self._cfg, self._key, EDGE_DIR)
                except Exception as exc:  # un fallo inesperado no debe matar el hilo
                    self.last_text, self.last_failed = f"AWS: error - {exc}"[:70], True
                    report(f"  Envio {capture_id}: error inesperado: {exc}", error=True)
                    continue
                self.last_text, self.last_failed = short_status(result), not result.ok
                report(f"  Envio {capture_id}: {describe(result)}", error=not result.ok)


def _relative_to_edge(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(EDGE_DIR))
    except ValueError:
        return str(path.resolve())


def draw_overlay(cv2, frame, crop, lines: list[tuple[str, bool]]):
    """Copia del cuadro con el recorte y las lineas de estado; la foto guardada va limpia."""
    shown = frame.copy()
    if crop is not None:
        x, y, w, h = crop
        cv2.rectangle(shown, (x, y), (x + w, y + h), (0, 255, 0), 2)
    top = 0
    for text, failed in lines:
        color = (0, 0, 255) if failed else (255, 255, 255)
        scale = 0.7 if top == 0 else 0.5
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        cv2.rectangle(shown, (0, top), (tw + 16, top + th + 16), (0, 0, 0), -1)
        cv2.putText(shown, text, (8, top + th + 8), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)
        top += th + 16
    return shown


def has_display() -> bool:
    if sys.platform.startswith("linux"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return True


class TerminalKeys:
    """Lee teclas sueltas de la terminal sin esperar Enter."""

    def __init__(self, fd: int | None = None):
        self._fd = sys.stdin.fileno() if fd is None else fd
        self._saved = None

    def __enter__(self) -> "TerminalKeys":
        try:
            import termios
            import tty
        except ImportError as exc:
            raise CameraError(
                "El modo sin ventana necesita una terminal Linux o macOS. "
                "Usa un equipo con pantalla para la vista previa."
            ) from exc
        if not os.isatty(self._fd):
            raise CameraError(
                "El modo sin ventana necesita una terminal interactiva "
                "(en SSH no uses redirecciones ni nohup)."
            )
        self._termios = termios
        self._saved = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, *_exc) -> None:
        if self._saved is not None:
            self._termios.tcsetattr(self._fd, self._termios.TCSADRAIN, self._saved)

    def poll(self, timeout: float) -> str:
        ready, _, _ = select.select([self._fd], [], [], timeout)
        return os.read(self._fd, 1).decode("utf-8", "ignore") if ready else ""


def toggle_interval(interval: IntervalTrigger) -> None:
    if not interval.seconds:
        report("Captura por intervalo: capture_interval_s no esta configurado.", error=True)
    elif interval.toggle():
        report(f"Captura por intervalo ACTIVADA: cada {interval.seconds:g} s (i para detener).")
    else:
        report("Captura por intervalo detenida.")


def screen_lines(capturer: Capturer, camera: Camera, interval: IntervalTrigger):
    lines = capturer.status_lines()
    if interval.active:
        lines.append((interval.status(), False))
    if camera.error:
        lines.append((camera.error, True))
    return lines


def unexpected(capturer: Capturer, exc: Exception) -> None:
    """Un error no previsto se registra con su traza y el programa sigue."""
    log.exception("Error inesperado")
    capturer.last_text, capturer.last_failed = f"Error inesperado: {exc}"[:70], True
    report(f"Error inesperado (el programa sigue): {exc}", error=True)
    time.sleep(ERROR_PAUSE_SECONDS)  # sin un ciclo de errores a toda velocidad


def run_with_window(cv2, camera: Camera, capturer: Capturer, interval: IntervalTrigger) -> None:
    import numpy as np

    cv2.namedWindow(WINDOW_TITLE)
    heartbeat = Heartbeat()
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    report("Vista previa abierta. Espacio: foto. i: captura por intervalo. q: salir.")
    try:
        while True:
            try:
                frame = camera.read()
                if frame is not None:
                    blank = np.zeros_like(frame)
                    crop = capturer.crop_for(frame)
                else:
                    crop = None  # camara desconectada: pantalla negra con el error
                lines = screen_lines(capturer, camera, interval)
                cv2.imshow(
                    WINDOW_TITLE,
                    draw_overlay(cv2, frame if frame is not None else blank, crop, lines),
                )
                key = cv2.waitKey(int(POLL_SECONDS * 1000)) & 0xFF
                if key == ord(KEY_QUIT):
                    break
                if key == ord(KEY_INTERVAL):
                    toggle_interval(interval)
                if frame is not None and (key == ord(KEY_SPACE) or interval.due()):
                    capturer.capture(frame)
                heartbeat.tick(capturer.count)
                if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                    break  # se cerro la ventana con la X
            except Exception as exc:  # la demo no se cae por un error no previsto
                unexpected(capturer, exc)
    finally:
        cv2.destroyAllWindows()


def run_in_terminal(
    camera: Camera, capturer: Capturer, keys: TerminalKeys, interval: IntervalTrigger
) -> None:
    heartbeat = Heartbeat()
    last_frame = None
    report("Modo sin ventana. Espacio: foto. i: captura por intervalo. q: salir.")
    with keys:
        while True:
            try:
                frame = camera.read()  # consume cuadros para no guardar uno viejo
                if frame is not None:
                    last_frame = frame
                elif camera.cap is None:
                    last_frame = None  # sin camara no se captura un cuadro viejo
                key = keys.poll(POLL_SECONDS).lower()
                if key == KEY_QUIT:
                    break
                if key == KEY_INTERVAL:
                    toggle_interval(interval)
                if last_frame is not None and (key == KEY_SPACE or interval.due()):
                    capturer.capture(last_frame)
                heartbeat.tick(capturer.count)
            except Exception as exc:  # la demo no se cae por un error no previsto
                unexpected(capturer, exc)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura fotos con la webcam del dispositivo edge."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="ruta de config.yaml")
    parser.add_argument("--headless", action="store_true", help="forzar el modo sin ventana")
    parser.add_argument(
        "--simular-fallo",
        action="store_true",
        help="enviar a una URL donde nada escucha, para demostrar el fallo y el reintento",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 2
    setup_logging(config["log_file"])
    log.info("---- Inicio de capture.py ----")

    try:
        import cv2
    except ImportError as exc:
        print(
            f"No se pudo importar OpenCV ({exc}).\n"
            "Activa el entorno virtual (source .venv/bin/activate) y revisa el README: "
            "en Ubuntu hacen falta libgl1 y libglib2.0-0.",
            file=sys.stderr,
        )
        return 1

    preview = config["preview"]
    use_window = preview is True or (preview == "auto" and has_display())
    if args.headless:
        use_window = False
    if use_window and not has_display():
        report("Aviso: preview esta activado pero no hay pantalla; se usa el modo sin ventana.")
        use_window = False

    from classifier import Classifier, ModelError

    try:
        classifier = Classifier(config["model"])
    except ModelError as exc:
        report(f"Error del modelo: {exc}", error=True)
        return 1
    for label, value in classifier.describe():
        report(f"{label + ':':<13}{value}")

    from events import EventStore

    try:
        store = EventStore(config["events_db"])
    except Exception as exc:  # sqlite3.Error u OSError
        report(f"No se pudo abrir el historial {config['events_db']}: {exc}", error=True)
        return 1
    total = sum(store.count_by_status().values())
    report(f"{'Historial:':<13}{config['events_db']} ({total} eventos)")
    report(f"{'Dispositivo:':<13}{config['device_id']}")
    report(f"{'Registro:':<13}{config['log_file']}")

    from dataclasses import replace

    from sender import SIMULATED_FAILURE_URL, describe_key_source, read_device_key

    upload = config["upload"]
    uploader = None
    if args.simular_fallo:
        upload = replace(upload, api_url=SIMULATED_FAILURE_URL)
        report(f"SIMULANDO FALLO: los envios van a {SIMULATED_FAILURE_URL} y van a fallar.")
    if upload.auto_send:
        uploader = Uploader(upload, config["events_db"], read_device_key(upload))
        report(f"{'Envio:':<13}{upload.api_url} (clave: {describe_key_source(upload)})")
    else:
        report(f"{'Envio:':<13}desactivado (upload.auto_send: false); usa retry.py")

    camera = None
    interval = IntervalTrigger(config["capture_interval_s"])
    try:
        camera = Camera(cv2, config)
        saver = FrameSaver(cv2, config["output_dir"], config["jpeg_quality"])
        report(
            f"Camara {config['camera_index']} lista. Las fotos se guardan en {config['output_dir']}"
        )
        capturer = Capturer(
            saver, classifier, config["crop_fraction"], store, config["device_id"], uploader
        )
        if use_window:
            run_with_window(cv2, camera, capturer, interval)
        else:
            run_in_terminal(camera, capturer, TerminalKeys(), interval)
    except CameraError as exc:
        report(f"Error: {exc}", error=True)
        return 1
    except KeyboardInterrupt:
        report("\nInterrumpido.")
    finally:
        if camera is not None:
            camera.release()
        if uploader is not None:
            uploader.close(timeout=upload.timeout_s + 2)
        store.close()
        log.info("---- Fin de capture.py ----")
    return 0


if __name__ == "__main__":
    sys.exit(main())
