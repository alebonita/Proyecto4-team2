"""MOD-2 — exporta el modelo ORIGINAL del Proyecto 3 a ONNX, sin optimizar.

Parte de los mismos pesos que MOD-1 (`../mod-01/model/best.pt`, SHA-256 84d6c88b…)
y de la misma arquitectura y clases (se importan de `../mod-01/predict.py`, no se
copian). No cuantiza, no poda, no cambia la precisión: float32 igual que el original.

    python export_onnx.py

Genera:
  model/dog-cat-resnet18-1.0.0-fp32.onnx   el modelo exportado
  model/SHA256SUMS                         SHA-256 del .onnx y del best.pt de origen
  inputs/<crop_id>.bin                     las 5 entradas ya preprocesadas (float32, 1x3x128x128)
  inputs/expected.json                     clase y probabilidades del ORIGINAL (PyTorch) en esas 5
  export_log.json                          versiones, opset, nombres de entrada/salida y hashes

Después, `node verify_web.mjs` carga el .onnx con onnxruntime-web y compara.
"""

import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import onnx
import onnxruntime as ort
import torch
import torchvision
from PIL import Image

HERE = Path(__file__).resolve().parent
MOD01 = HERE.parent / "mod-01"
sys.path.insert(0, str(MOD01))
import predict as mod01  # noqa: E402  arquitectura, clases y carga de MOD-1

OUT_MODEL = HERE / "model" / "dog-cat-resnet18-1.0.0-fp32.onnx"
OPSET = 17
INPUT_NAME, OUTPUT_NAME = "input", "logits"

# 5 recortes de validación elegidos de antemano para cubrir casos distintos, no al azar:
SAMPLES = [
    ("img102-ann118", "dog muy seguro"),
    ("img31-ann38", "cat muy seguro"),
    ("img125-ann141", "cat con confianza media"),
    ("img560-ann562", "dog dudoso (≈0.61)"),
    ("img263-ann299", "cat que el original confunde con dog (≈0.54, caso límite)"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def main() -> None:
    model = mod01.load_model()  # verifica el SHA-256 de best.pt y carga en modo eval
    dummy = torch.zeros(1, 3, mod01.IMAGE_SIZE, mod01.IMAGE_SIZE)

    OUT_MODEL.parent.mkdir(exist_ok=True)
    torch.onnx.export(
        model,
        (dummy,),
        str(OUT_MODEL),
        dynamo=False,  # exportador TorchScript: grafo estable y sin dependencias extra
        opset_version=OPSET,
        input_names=[INPUT_NAME],
        output_names=[OUTPUT_NAME],
        do_constant_folding=True,
    )
    onnx.checker.check_model(onnx.load(str(OUT_MODEL)), full_check=True)

    with open(MOD01 / "validation_manifest.csv", newline="") as f:
        manifest = {row["crop_id"]: row for row in csv.DictReader(f)}

    inputs_dir = HERE / "inputs"
    inputs_dir.mkdir(exist_ok=True)
    session = ort.InferenceSession(str(OUT_MODEL), providers=["CPUExecutionProvider"])
    expected = []
    for crop_id, why in SAMPLES:
        row = manifest[crop_id]
        image_path = MOD01 / row["path"]
        assert sha256(image_path) == row["sha256"], f"imagen alterada: {crop_id}"
        tensor = mod01.PREPROCESS(Image.open(image_path).convert("RGB")).unsqueeze(0)
        array = tensor.numpy().astype(np.float32)
        (inputs_dir / f"{crop_id}.bin").write_bytes(array.tobytes())  # little-endian float32

        with torch.no_grad():
            torch_logits = model(tensor)[0].numpy()
        ort_logits = session.run([OUTPUT_NAME], {INPUT_NAME: array})[0][0]
        torch_probs = softmax(torch_logits)
        expected.append(
            {
                "crop_id": crop_id,
                "why": why,
                "image": f"../mod-01/{row['path']}",
                "image_sha256": row["sha256"],
                "true_class": row["class"],
                "original_class": mod01.CLASSES[int(torch_logits.argmax())],
                "original_probs": dict(zip(mod01.CLASSES, map(float, torch_probs), strict=True)),
                "original_logits": list(map(float, torch_logits)),
                "onnxruntime_python_class": mod01.CLASSES[int(ort_logits.argmax())],
                "max_abs_diff_logits_python": float(np.abs(torch_logits - ort_logits).max()),
            }
        )
    (inputs_dir / "expected.json").write_text(
        json.dumps(
            {
                "classes": mod01.CLASSES,
                "input_name": INPUT_NAME,
                "output_name": OUTPUT_NAME,
                "input_shape": [1, 3, mod01.IMAGE_SIZE, mod01.IMAGE_SIZE],
                "input_dtype": "float32 little-endian, NCHW, ya normalizado (ver MOD-1)",
                "samples": expected,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    onnx_hash = sha256(OUT_MODEL)
    (OUT_MODEL.parent / "SHA256SUMS").write_text(
        f"{onnx_hash}  {OUT_MODEL.name}\n{mod01.EXPECTED_SHA256}  ../../mod-01/model/best.pt\n"
    )
    log = {
        "source_weights": "../mod-01/model/best.pt",
        "source_sha256": mod01.EXPECTED_SHA256,
        "onnx_file": f"model/{OUT_MODEL.name}",
        "onnx_sha256": onnx_hash,
        "onnx_bytes": OUT_MODEL.stat().st_size,
        "source_bytes": (MOD01 / "model" / "best.pt").stat().st_size,
        "precision": "float32 (sin optimizar)",
        "opset": OPSET,
        "exporter": "torch.onnx.export(dynamo=False)",
        "input": {"name": INPUT_NAME, "shape": [1, 3, mod01.IMAGE_SIZE, mod01.IMAGE_SIZE]},
        "output": {"name": OUTPUT_NAME, "shape": [1, len(mod01.CLASSES)], "classes": mod01.CLASSES},
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "onnx": onnx.__version__,
            "onnxruntime": ort.__version__,
            "numpy": np.__version__,
        },
        "platform": platform.platform(),
    }
    (HERE / "export_log.json").write_text(json.dumps(log, indent=2) + "\n")

    print(f"best.pt SHA-256 OK: {mod01.EXPECTED_SHA256}")
    print(f"ONNX: {OUT_MODEL.relative_to(HERE)} ({log['onnx_bytes']} bytes)")
    print(f"ONNX SHA-256: {onnx_hash}")
    for s in expected:
        print(
            f"  {s['crop_id']:<14} original={s['original_class']:<3} "
            f"onnxruntime(python)={s['onnxruntime_python_class']:<3} "
            f"Δlogits={s['max_abs_diff_logits_python']:.2e}"
        )


if __name__ == "__main__":
    main()
