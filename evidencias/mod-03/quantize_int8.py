"""MOD-3 — crea la variante optimizada: cuantización estática INT8 del ONNX original.

Parte del ONNX float32 de MOD-2 (mismo modelo del Proyecto 3) y lo cuantiza a INT8 con
onnxruntime, calibrando con las 150 imágenes de ENTRENAMIENTO de MOD-1b. No usa
validación ni test: esos se reservan para comparar la calidad (MOD-4).

    python quantize_int8.py                               # imágenes en <repo>/calibracion/
    python quantize_int8.py --calib-dir ruta/calibracion  # si descomprimiste el zip en otro lado

Antes de cuantizar, se verifica:
  - SHA-256 del ONNX original (MOD-2).
  - SHA-256 de cada una de las 150 imágenes contra ../calibracion/calibration-ids.csv,
    que todas sean del split train y que ninguna esté en la validación de MOD-1.

Genera:
  model/dog-cat-resnet18-1.0.0-int8.onnx   la variante optimizada
  model/SHA256SUMS                         SHA-256 de la variante y del ONNX de origen
  conversion_log.json                      entrada, salida, técnica, configuración,
                                           calibración, tamaños y versiones
"""

import argparse
import csv
import hashlib
import json
import platform
import sys
import tempfile
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
from onnxruntime.quantization import (
    CalibrationDataReader,
    CalibrationMethod,
    QuantFormat,
    QuantType,
    quantize_static,
)
from onnxruntime.quantization.shape_inference import quant_pre_process
from PIL import Image

HERE = Path(__file__).resolve().parent
EVID = HERE.parent
REPO = EVID.parent
MOD01 = EVID / "mod-01"
sys.path.insert(0, str(MOD01))
import predict as mod01  # noqa: E402  clases y preprocesamiento del original (MOD-1)

SOURCE = EVID / "mod-02" / "model" / "dog-cat-resnet18-1.0.0-fp32.onnx"
SOURCE_SHA256 = "6628f3cf24673a5045d51723b97dcfca85ebc1d511d49793bb6c0b0731c7035f"
CALIB_IDS = EVID / "calibracion" / "calibration-ids.csv"
OUT = HERE / "model" / "dog-cat-resnet18-1.0.0-int8.onnx"

SETTINGS = {
    "technique": "cuantización estática post-entrenamiento INT8 (onnxruntime.quantization)",
    "quant_format": "QDQ",
    "weight_type": "QInt8 (por canal)",
    "activation_type": "QUInt8",
    "per_channel": True,
    "calibrate_method": "MinMax",
    "preprocess": "quant_pre_process (inferencia de formas), skip_symbolic_shape=True",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_calibration(calib_dir: Path) -> list[Path]:
    with open(CALIB_IDS, newline="") as f:
        rows = list(csv.DictReader(f))
    with open(MOD01 / "validation_manifest.csv", newline="") as f:
        validation = {r["crop_id"] for r in csv.DictReader(f)}
    if len(rows) != 150 or any(r["split"] != "train" for r in rows):
        raise SystemExit("calibration-ids.csv debe tener 150 filas, todas del split train.")
    if validation & {r["crop_id"] for r in rows}:
        raise SystemExit("Hay imágenes de validación en la calibración.")
    paths = []
    for r in rows:
        path = calib_dir / r["clase"] / f"{r['crop_id']}.png"
        if not path.is_file():
            raise SystemExit(
                f"Falta {path}. Descomprime calibracion.zip de MOD-1b en la raíz del repo "
                "(ver ../calibracion/README.md) o usa --calib-dir."
            )
        if sha256(path) != r["sha256"]:
            raise SystemExit(f"SHA-256 distinto en {path}")
        paths.append(path)
    return paths


class CalibrationImages(CalibrationDataReader):
    """Entrega las imágenes con el MISMO preprocesamiento del original, una por una."""

    def __init__(self, paths: list[Path], input_name: str):
        self._iter = iter(paths)
        self._input_name = input_name

    def get_next(self):
        path = next(self._iter, None)
        if path is None:
            return None
        tensor = mod01.PREPROCESS(Image.open(path).convert("RGB")).unsqueeze(0)
        return {self._input_name: tensor.numpy().astype(np.float32)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--calib-dir", type=Path, default=REPO / "calibracion")
    args = parser.parse_args()

    if not SOURCE.is_file():
        raise SystemExit(f"Falta {SOURCE}: genéralo o bájalo (ver evidencias/mod-02/README.md).")
    if sha256(SOURCE) != SOURCE_SHA256:
        raise SystemExit(f"El ONNX original no tiene el SHA-256 esperado ({SOURCE_SHA256}).")
    calibration = load_calibration(args.calib_dir.resolve())
    input_name = onnx.load(str(SOURCE)).graph.input[0].name

    OUT.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        prepared = Path(tmp) / "prepared.onnx"
        quant_pre_process(str(SOURCE), str(prepared), skip_symbolic_shape=True)
        quantize_static(
            str(prepared),
            str(OUT),
            CalibrationImages(calibration, input_name),
            quant_format=QuantFormat.QDQ,
            weight_type=QuantType.QInt8,
            activation_type=QuantType.QUInt8,
            per_channel=True,
            calibrate_method=CalibrationMethod.MinMax,
        )
    onnx.checker.check_model(onnx.load(str(OUT)))
    ort.InferenceSession(str(OUT), providers=["CPUExecutionProvider"])  # carga en el runtime

    out_hash = sha256(OUT)
    source_bytes, out_bytes = SOURCE.stat().st_size, OUT.stat().st_size
    (OUT.parent / "SHA256SUMS").write_text(
        f"{out_hash}  {OUT.name}\n{SOURCE_SHA256}  ../../mod-02/model/{SOURCE.name}\n"
    )
    log = {
        "input": {
            "file": f"../mod-02/model/{SOURCE.name}",
            "sha256": SOURCE_SHA256,
            "bytes": source_bytes,
        },
        "output": {"file": f"model/{OUT.name}", "sha256": out_hash, "bytes": out_bytes},
        "size_reduction_pct": round(100 * (source_bytes - out_bytes) / source_bytes, 2),
        "origin_chain": "best.pt (P3, SHA-256 84d6c88b…) -> MOD-2 fp32 ONNX -> esta variante INT8",
        "settings": SETTINGS,
        "calibration": {
            "ids_csv": "../calibracion/calibration-ids.csv",
            "ids_csv_sha256": sha256(CALIB_IDS),
            "images": len(calibration),
            "split": "train (75 dog + 75 cat); ninguna de validación ni test",
            "zip_sha256_mod1b": "fd53f5f7448e3db8fc8978927fa83375d4564a40528bf711b35c45f0ffd559d5",
        },
        "classes": mod01.CLASSES,
        "input_tensor": {"name": input_name, "shape": [1, 3, mod01.IMAGE_SIZE, mod01.IMAGE_SIZE]},
        "versions": {
            "python": platform.python_version(),
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
            "numpy": np.__version__,
            "torch (solo preprocesamiento)": mod01.torch.__version__,
        },
        "platform": platform.platform(),
    }
    (HERE / "conversion_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False) + "\n")

    print(f"origen:   {SOURCE.name}  {source_bytes} bytes  SHA-256 {SOURCE_SHA256}")
    print(f"calibración: {len(calibration)} imágenes de train verificadas")
    print(f"variante: {OUT.name}  {out_bytes} bytes  SHA-256 {out_hash}")
    print(f"reducción de tamaño: {log['size_reduction_pct']} %")


if __name__ == "__main__":
    main()
