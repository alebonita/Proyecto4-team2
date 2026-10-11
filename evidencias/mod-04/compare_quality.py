"""MOD-4 — compara la calidad del original y una variante optimizada sobre la MISMA
validación del Proyecto 3 (los 128 recortes de MOD-1), con onnxruntime de Python, que es
el runtime de la laptop edge.

    python compare_quality.py                                # variante int8 (MOD-3)
    python compare_quality.py --variant int8-rr              # variante int8 con reduce_range
    python compare_quality.py --variant int8-rr --tag intel  # en otra compu: no pisa archivos

No necesita PyTorch. Las 128 entradas vienen ya redimensionadas en
inputs/validation_resized_uint8.npz (uint8, 3x128x128) y aquí solo se normalizan, con el
mismo orden de operaciones que torchvision, así que el tensor es idéntico byte a byte al
`PREPROCESS` de ../mod-01/predict.py. Así la comparación usa exactamente las mismas entradas
en cualquier computadora. Con PyTorch instalado, `--build-inputs` regenera ese .npz desde los
PNG y comprueba la igualdad byte a byte en los 128 recortes.

Corre, con onnxruntime (CPU):
  - la variante elegida de MOD-3                -> pred_optimized
  - el ONNX float32 de MOD-2                    -> control de la conversión
La predicción original es la de PyTorch de MOD-1 (../mod-01/predictions_original_validation.csv).

Escribe en esta carpeta (el sufijo depende de --variant y --tag; sin ninguno, los nombres de
siempre):
  predictions_validation[_<variant>][_<tag>].csv  una fila por recorte: crop_id, clase real,
                                                 predicción original, predicción optimizada
                                                 y probabilidades de ambas
  metrics[_<variant>][_<tag>].json                accuracy, F1 macro, resultados por clase,
                                                 caída en pp, coincidencias, hashes, CPU y
                                                 versiones
Sale con código 1 si falta un recorte, un hash no coincide o falta un modelo.
"""

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort

HERE = Path(__file__).resolve().parent
EVID = HERE.parent
MOD01 = EVID / "mod-01"

# Iguales a ../mod-01/predict.py (con --build-inputs se comprueba que sigan iguales).
CLASSES = ["dog", "cat"]
IMAGE_SIZE = 128
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
ORIGINAL_SHA256 = "84d6c88b4bd84c3e6f0229dd23f7f188ff85622bbb39e5c3988a97598fa90d52"

INPUTS = HERE / "inputs" / "validation_resized_uint8.npz"
INPUTS_SHA256 = "29a6b2a2deb0e6accbf4cec3c9ad575ba9ef35c76950e4085a1228744795a3b3"

VARIANTS = {
    "int8": (
        EVID / "mod-03" / "model" / "dog-cat-resnet18-1.0.0-int8.onnx",
        "9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd",
    ),
    "int8-rr": (
        EVID / "mod-03" / "model" / "dog-cat-resnet18-1.0.0-int8-rr.onnx",
        "1d4a85fad5b2dcab28692bd5f81b5089092cf3a551b7862a63c544c94dcb5ea0",
    ),
}
FP32 = (
    EVID / "mod-02" / "model" / "dog-cat-resnet18-1.0.0-fp32.onnx",
    "6628f3cf24673a5045d51723b97dcfca85ebc1d511d49793bb6c0b0731c7035f",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def normalize(resized: np.ndarray) -> np.ndarray:
    """uint8 (3,128,128) -> float32 (1,3,128,128), en el orden de torchvision:
    ToDtype(scale=True) multiplica por 1/255 y Normalize resta la media y divide por std."""
    f = np.float32
    mean = np.array(MEAN, f).reshape(3, 1, 1)
    std = np.array(STD, f).reshape(3, 1, 1)
    x = (resized.astype(f) * f(1 / 255) - mean) / std
    return x[np.newaxis].astype(f)


def cpu_info() -> dict:
    """Modelo del CPU y si tiene VNNI (afecta al INT8 en x86, ver MOD-5)."""
    name, flags = platform.processor() or "desconocido", ""
    try:
        if sys.platform.startswith("linux"):
            text = Path("/proc/cpuinfo").read_text()
            found = re.search(r"^model name\s*:\s*(.+)$", text, re.M)
            name = found.group(1) if found else name
            found = re.search(r"^flags\s*:\s*(.+)$", text, re.M)
            flags = found.group(1) if found else ""
        elif sys.platform == "darwin":

            def sysctl(key: str) -> str:
                return subprocess.run(
                    ["sysctl", "-n", key], capture_output=True, text=True, check=False
                ).stdout.strip()

            name = sysctl("machdep.cpu.brand_string") or name
            flags = " ".join(
                sysctl(k) for k in ("machdep.cpu.features", "machdep.cpu.leaf7_features")
            ).lower()
        elif sys.platform == "win32":
            name = platform.processor() or name
    except OSError:
        pass
    tokens = set(flags.replace(".", "_").split())
    vnni = sorted(t for t in tokens if "vnni" in t)
    return {
        "model": name,
        "machine": platform.machine(),
        "vnni": vnni or ("no" if tokens else "desconocido"),
        "avx2": ("avx2" in tokens) if tokens else "desconocido",
    }


def metrics(rows: list[dict], pred_key: str) -> dict:
    """Accuracy, precision/recall/F1 por clase y F1 macro sobre el mapa de clases completo."""
    per_class = {}
    for c in CLASSES:
        tp = sum(r["true_class"] == c and r[pred_key] == c for r in rows)
        predicted = sum(r[pred_key] == c for r in rows)
        support = sum(r["true_class"] == c for r in rows)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[c] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
            "correct": tp,
        }
    correct = sum(r["true_class"] == r[pred_key] for r in rows)
    return {
        "correct": correct,
        "total": len(rows),
        "accuracy": correct / len(rows),
        "f1_macro": sum(v["f1"] for v in per_class.values()) / len(per_class),
        "per_class": per_class,
        "errors": [
            {"crop_id": r["crop_id"], "true": r["true_class"], "predicted": r[pred_key]}
            for r in rows
            if r["true_class"] != r[pred_key]
        ],
    }


def session(path: Path, expected: str) -> tuple[ort.InferenceSession, str]:
    if not path.is_file():
        raise SystemExit(f"Falta {path}. Ver el README de esa carpeta (bucket o script).")
    actual = sha256(path)
    if actual != expected:
        raise SystemExit(f"SHA-256 distinto en {path.name}: {actual} (esperado {expected})")
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]), actual


def run(sess: ort.InferenceSession, array: np.ndarray) -> np.ndarray:
    logits = sess.run(None, {sess.get_inputs()[0].name: array})[0][0]
    return softmax(logits.astype(np.float64))


def load_manifest() -> list[dict]:
    with open(MOD01 / "validation_manifest.csv", newline="") as f:
        return list(csv.DictReader(f))


def build_inputs() -> None:
    """Regenera el .npz desde los PNG (requiere PyTorch) y comprueba la igualdad byte a byte."""
    sys.path.insert(0, str(MOD01))
    import predict as mod01  # clases y preprocesamiento del original (MOD-1)
    from PIL import Image
    from torchvision.transforms import v2

    if (mod01.CLASSES, mod01.IMAGE_SIZE, mod01.MEAN, mod01.STD) != (
        CLASSES,
        IMAGE_SIZE,
        MEAN,
        STD,
    ):
        raise SystemExit("Las constantes no coinciden con ../mod-01/predict.py.")
    resize = v2.Compose([v2.ToImage(), v2.Resize((IMAGE_SIZE, IMAGE_SIZE), antialias=True)])
    ids, images = [], []
    for item in load_manifest():
        path = MOD01 / item["path"]
        if sha256(path) != item["sha256"]:
            raise SystemExit(f"SHA-256 distinto en {item['path']}")
        image = Image.open(path).convert("RGB")
        resized = resize(image).numpy()
        reference = mod01.PREPROCESS(image).unsqueeze(0).numpy()
        if not np.array_equal(normalize(resized), reference):
            raise SystemExit(f"La normalización no es idéntica a PREPROCESS en {item['crop_id']}")
        ids.append(item["crop_id"])
        images.append(resized)
    INPUTS.parent.mkdir(exist_ok=True)
    np.savez_compressed(INPUTS, crop_id=np.array(ids), image=np.stack(images))
    print(f"{len(ids)} recortes: normalización idéntica byte a byte a PREPROCESS (MOD-1)")
    print(f"-> {INPUTS.relative_to(HERE)}  SHA-256 {sha256(INPUTS)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--variant", choices=sorted(VARIANTS), default="int8")
    parser.add_argument("--tag", default="", help="etiqueta de la compu, p. ej. intel")
    parser.add_argument("--build-inputs", action="store_true", help="regenera el .npz (torch)")
    args = parser.parse_args()
    if args.build_inputs:
        build_inputs()
        return
    if args.tag and not re.fullmatch(r"[a-z0-9-]+", args.tag):
        raise SystemExit("--tag solo admite minúsculas, números y guiones.")

    manifest = load_manifest()
    with open(MOD01 / "predictions_original_validation.csv", newline="") as f:
        original = {row["crop_id"]: row for row in csv.DictReader(f)}
    ids = [r["crop_id"] for r in manifest]
    if len(ids) != 128 or len(set(ids)) != 128 or set(ids) != set(original):
        raise SystemExit("Manifiesto y predicciones del original deben cubrir los mismos 128 IDs.")

    if not INPUTS.is_file() or sha256(INPUTS) != INPUTS_SHA256:
        raise SystemExit(f"{INPUTS.name} falta o no tiene el SHA-256 esperado ({INPUTS_SHA256}).")
    with np.load(INPUTS) as data:
        npz_ids, images = list(data["crop_id"]), data["image"]
    if npz_ids != ids:
        raise SystemExit("Los IDs del .npz no coinciden con el manifiesto.")

    opt_path, opt_expected = VARIANTS[args.variant]
    opt_sess, opt_hash = session(opt_path, opt_expected)
    fp32_sess, fp32_hash = session(*FP32)

    rows, fp32_agree = [], 0
    for item, resized in zip(manifest, images, strict=True):
        array = normalize(resized)
        opt_probs = run(opt_sess, array)
        fp32_probs = run(fp32_sess, array)
        orig = original[item["crop_id"]]
        if orig["true_class"] != item["class"]:
            raise SystemExit(f"La etiqueta de {item['crop_id']} no coincide con el manifiesto.")
        fp32_agree += CLASSES[int(np.argmax(fp32_probs))] == orig["pred_original"]
        rows.append(
            {
                "crop_id": item["crop_id"],
                "true_class": item["class"],
                "pred_original": orig["pred_original"],
                "pred_optimized": CLASSES[int(np.argmax(opt_probs))],
                **{f"prob_original_{c}": orig[f"prob_{c}"] for c in CLASSES},
                **{
                    f"prob_optimized_{c}": f"{p:.6f}"
                    for c, p in zip(CLASSES, opt_probs, strict=True)
                },
            }
        )

    suffix = "".join(
        f"_{part}" for part in (args.variant if args.variant != "int8" else "", args.tag) if part
    )
    csv_path = HERE / f"predictions_validation{suffix}.csv"
    json_path = HERE / f"metrics{suffix}.json"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    m_orig, m_opt = metrics(rows, "pred_original"), metrics(rows, "pred_optimized")
    agree = sum(r["pred_original"] == r["pred_optimized"] for r in rows)
    max_prob_diff = max(
        abs(float(r[f"prob_original_{c}"]) - float(r[f"prob_optimized_{c}"]))
        for r in rows
        for c in CLASSES
    )
    cpu = cpu_info()
    result = {
        "validation": {
            "manifest": "../mod-01/validation_manifest.csv",
            "manifest_sha256": sha256(MOD01 / "validation_manifest.csv"),
            "inputs": f"inputs/{INPUTS.name}",
            "inputs_sha256": INPUTS_SHA256,
            "samples": len(rows),
            "support": {c: m_orig["per_class"][c]["support"] for c in CLASSES},
            "classes": CLASSES,
        },
        "original": {
            "model": "best.pt del Proyecto 3 (PyTorch), SHA-256 " + ORIGINAL_SHA256,
            "predictions": "../mod-01/predictions_original_validation.csv",
            **m_orig,
        },
        "optimized": {
            "variant": args.variant,
            "model": f"../mod-03/model/{opt_path.name}",
            "sha256": opt_hash,
            "runtime": f"onnxruntime {ort.__version__} (Python, CPUExecutionProvider)",
            **m_opt,
        },
        "accuracy_drop_pp": 100 * (m_orig["accuracy"] - m_opt["accuracy"]),
        "f1_macro_drop_pp": 100 * (m_orig["f1_macro"] - m_opt["f1_macro"]),
        "same_class_as_original": f"{agree}/{len(rows)}",
        "disagreements": [r["crop_id"] for r in rows if r["pred_original"] != r["pred_optimized"]],
        "max_abs_diff_prob": max_prob_diff,
        "control_onnx_fp32": {
            "model": f"../mod-02/model/{FP32[0].name}",
            "sha256": fp32_hash,
            "same_class_as_original": f"{fp32_agree}/{len(rows)}",
        },
        "machine": {"tag": args.tag or "mod-04", "cpu": cpu},
        "versions": {
            "python": platform.python_version(),
            "onnxruntime": ort.__version__,
            "numpy": np.__version__,
        },
        "platform": platform.platform(),
    }
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    print(f"variante: {args.variant} ({opt_path.name}, SHA-256 {opt_hash[:12]}…)")
    print(f"CPU: {cpu['model']}  VNNI: {cpu['vnni']}")
    print(f"runtime: {result['optimized']['runtime']}")
    for label, m in (("original", m_orig), ("optimizada", m_opt)):
        per = "  ".join(f"{c}: F1={m['per_class'][c]['f1']:.4f}" for c in CLASSES)
        errs = ", ".join(e["crop_id"] for e in m["errors"]) or "-"
        print(
            f"{label:<10} accuracy={m['accuracy']:.4f} ({m['correct']}/{m['total']})  "
            f"F1 macro={m['f1_macro']:.4f}  {per}  errores: {errs}"
        )
    print(
        f"caída de accuracy: {result['accuracy_drop_pp']:.2f} pp   "
        f"caída de F1 macro: {result['f1_macro_drop_pp']:.2f} pp"
    )
    print(
        f"misma clase que el original: {result['same_class_as_original']}   "
        f"max |Δ prob|: {max_prob_diff:.4f}"
    )
    print(f"control ONNX fp32 (MOD-2): {result['control_onnx_fp32']['same_class_as_original']}")
    print(f"-> {csv_path.name}, {json_path.name}")


if __name__ == "__main__":
    main()
