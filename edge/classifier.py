"""EDG-2: clasificacion local con onnxruntime en CPU.

Carga el modelo ONNX una sola vez y clasifica un recorte del cuadro de la camara sin
ninguna llamada de red. El preprocesamiento replica el del modelo original del
Proyecto 3 (evidencias/mod-01/README.md):

1. Recorte del objeto y conversion BGR (OpenCV) -> RGB.
2. Redimension directa a input_size x input_size, bilineal con antialias. Se usa Pillow
   porque su filtro bilineal es el que torchvision replica con antialias=True; el
   resize de OpenCV no aplica antialias y da otros valores.
3. [0, 255] -> [0, 1] y normalizacion por canal con mean/std.
4. Tensor NCHW float32 de forma 1 x 3 x input_size x input_size.

La salida son logits; softmax da la confianza entre 0 y 1.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

PROVIDER = "CPUExecutionProvider"


class ModelError(Exception):
    """El modelo no existe, no es el esperado o no es compatible con la configuracion."""


@dataclass(frozen=True)
class ModelConfig:
    path: Path
    version: str
    classes: tuple[str, ...]
    sha256: str | None
    input_size: int
    channel_order: str
    mean: tuple[float, float, float]
    std: tuple[float, float, float]


@dataclass(frozen=True)
class Prediction:
    label: str
    confidence: float
    latency_ms: float
    probabilities: dict[str, float]


def _numbers(value: object, name: str) -> tuple[float, float, float]:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    ):
        raise ValueError(f"{name} debe ser una lista de 3 numeros (uno por canal).")
    return (float(value[0]), float(value[1]), float(value[2]))


def parse_model_config(model: object, preprocess: object, base_dir: Path) -> ModelConfig:
    """Valida las secciones model y preprocess de config.yaml. Lanza ValueError."""
    if not isinstance(model, dict):
        raise ValueError("falta la seccion model (path, version, classes).")
    if not isinstance(preprocess, dict):
        raise ValueError("falta la seccion preprocess (input_size, channel_order, mean, std).")

    path = model.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError("model.path debe ser la ruta del archivo .onnx.")
    version = model.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("model.version debe ser un texto (ej. dog-cat-resnet18-1.0.0-int8).")
    classes = model.get("classes")
    if (
        not isinstance(classes, list)
        or len(classes) < 2
        or not all(isinstance(c, str) and c for c in classes)
        or len(set(classes)) != len(classes)
    ):
        raise ValueError("model.classes debe ser la lista de clases en el orden de salida.")
    sha256 = model.get("sha256")
    if sha256 is not None and (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or any(c not in "0123456789abcdef" for c in sha256)
    ):
        raise ValueError("model.sha256 debe ser un SHA-256 en hexadecimal o quedar vacio.")

    size = preprocess.get("input_size")
    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ValueError("preprocess.input_size debe ser un entero positivo (ej. 128).")
    order = preprocess.get("channel_order")
    if order not in ("RGB", "BGR"):
        raise ValueError("preprocess.channel_order debe ser RGB o BGR.")
    std = _numbers(preprocess.get("std"), "preprocess.std")
    if any(s <= 0 for s in std):
        raise ValueError("preprocess.std debe tener valores mayores que 0.")

    model_path = Path(path).expanduser()
    return ModelConfig(
        path=model_path if model_path.is_absolute() else base_dir / model_path,
        version=version.strip(),
        classes=tuple(classes),
        sha256=sha256,
        input_size=size,
        channel_order=order,
        mean=_numbers(preprocess.get("mean"), "preprocess.mean"),
        std=std,
    )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def center_crop(width: int, height: int, fraction: float) -> tuple[int, int, int, int]:
    """Cuadrado centrado con `fraction` del lado corto: (x, y, ancho, alto) en pixeles."""
    side = max(1, round(min(width, height) * fraction))
    return ((width - side) // 2, (height - side) // 2, side, side)


def preprocess(frame_bgr: np.ndarray, crop: tuple[int, int, int, int], cfg: ModelConfig):
    """Recorte BGR de OpenCV -> tensor 1 x 3 x S x S listo para el modelo."""
    import cv2
    from PIL import Image

    x, y, w, h = crop
    region = np.ascontiguousarray(frame_bgr[y : y + h, x : x + w])
    if cfg.channel_order == "RGB":
        region = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)
    size = (cfg.input_size, cfg.input_size)
    resized = Image.fromarray(region).resize(size, Image.Resampling.BILINEAR)
    pixels = np.asarray(resized, dtype=np.float32) / 255.0
    pixels = (pixels - np.array(cfg.mean, dtype=np.float32)) / np.array(cfg.std, dtype=np.float32)
    return np.ascontiguousarray(pixels.transpose(2, 0, 1)[np.newaxis])


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = np.exp(logits - logits.max())
    return shifted / shifted.sum()


class Classifier:
    """Sesion de onnxruntime en CPU creada una sola vez al arrancar."""

    def __init__(self, cfg: ModelConfig):
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise ModelError(
                "Falta onnxruntime. Activa el entorno virtual e instala las dependencias: "
                "pip install -r requirements.txt"
            ) from exc

        if not cfg.path.is_file():
            raise ModelError(
                f"No existe el modelo {cfg.path}. Copialo a esa ruta o cambia model.path en "
                "config.yaml (ver 'Modelo' en el README)."
            )
        self.sha256 = sha256_of(cfg.path)
        if cfg.sha256 and self.sha256 != cfg.sha256:
            raise ModelError(
                f"{cfg.path.name} no es el modelo esperado: SHA-256 {self.sha256}, "
                f"config.yaml pide {cfg.sha256}."
            )

        try:
            self._session = ort.InferenceSession(str(cfg.path), providers=[PROVIDER])
        except Exception as exc:  # onnxruntime lanza sus propias excepciones
            raise ModelError(f"onnxruntime no pudo cargar {cfg.path.name}: {exc}") from exc

        inputs = self._session.get_inputs()
        outputs = self._session.get_outputs()
        if len(inputs) != 1:
            raise ModelError(f"El modelo tiene {len(inputs)} entradas; se esperaba 1.")
        shape = inputs[0].shape
        expected = [1, 3, cfg.input_size, cfg.input_size]
        fixed = [dim if isinstance(dim, int) else None for dim in shape]
        if len(shape) != 4 or any(
            f is not None and f != e for f, e in zip(fixed, expected, strict=True)
        ):
            raise ModelError(f"La entrada del modelo es {shape}; config.yaml indica {expected}.")
        width = outputs[0].shape[-1]
        if isinstance(width, int) and width != len(cfg.classes):
            raise ModelError(
                f"El modelo da {width} salidas y config.yaml declara {len(cfg.classes)} clases."
            )

        self.cfg = cfg
        self.onnxruntime_version = ort.__version__
        self.provider = self._session.get_providers()[0]
        self._input_name = inputs[0].name

    def describe(self) -> list[tuple[str, str]]:
        return [
            ("Modelo", self.cfg.path.name),
            ("SHA-256", self.sha256),
            ("Version", self.cfg.version),
            ("onnxruntime", self.onnxruntime_version),
            ("Proveedor", self.provider),
        ]

    def classify(self, frame_bgr: np.ndarray, crop: tuple[int, int, int, int]) -> Prediction:
        """Preprocesamiento + inferencia locales; latency_ms mide los dos."""
        start = time.perf_counter()
        tensor = preprocess(frame_bgr, crop, self.cfg)
        logits = self._session.run(None, {self._input_name: tensor})[0][0]
        probs = softmax(logits.astype(np.float64))
        latency_ms = (time.perf_counter() - start) * 1000
        best = int(probs.argmax())
        return Prediction(
            label=self.cfg.classes[best],
            confidence=float(probs[best]),
            latency_ms=latency_ms,
            probabilities={c: float(p) for c, p in zip(self.cfg.classes, probs, strict=True)},
        )
