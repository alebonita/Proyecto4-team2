"""EDG-1: programa base de captura del dispositivo edge.

Abre la webcam con OpenCV y guarda el cuadro actual como JPEG:

- Barra espaciadora: guarda una foto en la carpeta de capturas.
- q: cierra el programa.

Hay dos modos, y se elige solo:

- Con ventana: si el equipo tiene pantalla, muestra la vista previa en vivo.
- Sin pantalla (por ejemplo Ubuntu Server por SSH): no hay donde dibujar una
  ventana, asi que las teclas se leen de la terminal y la camara sigue
  capturando cuadros en segundo plano. Se puede forzar con --headless.

El indice de la camara y la carpeta de salida salen de config.yaml.

Codigos de salida: 0 normal, 1 camara o ejecucion, 2 configuracion.
"""

from __future__ import annotations

import argparse
import glob
import os
import select
import sys
from datetime import datetime
from pathlib import Path

EDGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = EDGE_DIR / "config.yaml"
WINDOW_TITLE = "Captura edge - espacio: foto, q: salir"
KEY_SPACE = " "
KEY_QUIT = "q"
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

    def save(self, frame) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        path = self._dir / f"capture_{stamp}.jpg"
        ok = self._cv2.imwrite(str(path), frame, [self._cv2.IMWRITE_JPEG_QUALITY, self._quality])
        if not ok or not path.is_file():
            raise CameraError(
                f"No se pudo guardar la foto en {path}. Revisa permisos y espacio en disco."
            )
        return path


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


def run_with_window(cv2, cap, saver: FrameSaver) -> None:
    cv2.namedWindow(WINDOW_TITLE)
    failures = [0]
    print("Vista previa abierta. Espacio: guardar foto. q: salir.")
    try:
        while True:
            frame = read_frame(cap, failures)
            if frame is not None:
                cv2.imshow(WINDOW_TITLE, frame)
            key = cv2.waitKey(int(POLL_SECONDS * 1000)) & 0xFF
            if frame is not None and key == ord(KEY_SPACE):
                print(f"Foto guardada: {saver.save(frame)}")
            elif key == ord(KEY_QUIT):
                break
            if cv2.getWindowProperty(WINDOW_TITLE, cv2.WND_PROP_VISIBLE) < 1:
                break  # se cerro la ventana con la X
    finally:
        cv2.destroyAllWindows()


def run_in_terminal(cap, saver: FrameSaver, keys: TerminalKeys) -> None:
    failures = [0]
    last_frame = None
    print("Modo sin ventana (no hay pantalla). Espacio: guardar foto. q: salir.")
    with keys:
        while True:
            frame = read_frame(cap, failures)  # consume cuadros para no guardar uno viejo
            if frame is not None:
                last_frame = frame
            key = keys.poll(POLL_SECONDS)
            if key == KEY_SPACE and last_frame is not None:
                print(f"Foto guardada: {saver.save(last_frame)}")
            elif key.lower() == KEY_QUIT:
                break


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Captura fotos con la webcam del dispositivo edge."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="ruta de config.yaml")
    parser.add_argument("--headless", action="store_true", help="forzar el modo sin ventana")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 2

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
        print("Aviso: preview esta activado pero no hay pantalla; se usa el modo sin ventana.")
        use_window = False

    cap = None
    try:
        cap = open_camera(
            cv2, config["camera_index"], config["width"], config["height"], config["warmup_frames"]
        )
        saver = FrameSaver(cv2, config["output_dir"], config["jpeg_quality"])
        print(
            f"Camara {config['camera_index']} lista. Las fotos se guardan en {config['output_dir']}"
        )
        if use_window:
            run_with_window(cv2, cap, saver)
        else:
            run_in_terminal(cap, saver, TerminalKeys())
    except CameraError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrumpido.")
    finally:
        if cap is not None:
            cap.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
