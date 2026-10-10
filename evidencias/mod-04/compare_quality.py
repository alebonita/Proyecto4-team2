"""MOD-4 — compara la calidad del original y la variante optimizada sobre la MISMA
validación del Proyecto 3 (los 128 recortes de MOD-1), con onnxruntime de Python, que es
el runtime de la laptop edge.

    python compare_quality.py

Para cada recorte lee el PNG, verifica su SHA-256 contra el manifiesto, le aplica el MISMO
preprocesamiento del original (`PREPROCESS` de ../mod-01/predict.py) y corre:
  - la variante optimizada INT8 de MOD-3 (onnxruntime, CPU) -> pred_optimized
  - el ONNX float32 de MOD-2 (onnxruntime, CPU)              -> control de la conversión
La predicción original es la de PyTorch de MOD-1 (../mod-01/predictions_original_validation.csv).

Escribe en esta carpeta:
  predictions_validation.csv  una fila por recorte: crop_id, clase real, predicción original,
                              predicción optimizada y probabilidades de ambas
  metrics.json                accuracy, F1 macro y resultados por clase (original y optimizada),
                              caída en puntos porcentuales, coincidencias, hashes y versiones
Sale con código 1 si falta un recorte, un hash no coincide o falta un modelo.
"""

import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

HERE = Path(__file__).resolve().parent
EVID = HERE.parent
MOD01 = EVID / "mod-01"
sys.path.insert(0, str(MOD01))
import predict as mod01  # noqa: E402  clases y preprocesamiento del original (MOD-1)

MODELS = {
    "optimized": (
        EVID / "mod-03" / "model" / "dog-cat-resnet18-1.0.0-int8.onnx",
        "9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd",
    ),
    "onnx_fp32": (
        EVID / "mod-02" / "model" / "dog-cat-resnet18-1.0.0-fp32.onnx",
        "6628f3cf24673a5045d51723b97dcfca85ebc1d511d49793bb6c0b0731c7035f",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / e.sum()


def metrics(rows: list[dict], pred_key: str) -> dict:
    """Accuracy, precision/recall/F1 por clase y F1 macro sobre el mapa de clases completo."""
    per_class = {}
    for c in mod01.CLASSES:
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


def session(name: str) -> tuple[ort.InferenceSession, Path, str]:
    path, expected = MODELS[name]
    if not path.is_file():
        raise SystemExit(f"Falta {path}. Ver el README de esa carpeta (bucket o script).")
    actual = sha256(path)
    if actual != expected:
        raise SystemExit(f"SHA-256 distinto en {path.name}: {actual} (esperado {expected})")
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"]), path, actual


def predict(sess: ort.InferenceSession, array: np.ndarray) -> np.ndarray:
    logits = sess.run(None, {sess.get_inputs()[0].name: array})[0][0]
    return softmax(logits.astype(np.float64))


def main() -> None:
    with open(MOD01 / "validation_manifest.csv", newline="") as f:
        manifest = list(csv.DictReader(f))
    with open(MOD01 / "predictions_original_validation.csv", newline="") as f:
        original = {row["crop_id"]: row for row in csv.DictReader(f)}
    ids = [r["crop_id"] for r in manifest]
    if len(ids) != 128 or len(set(ids)) != 128 or set(ids) != set(original):
        raise SystemExit("Manifiesto y predicciones del original deben cubrir los mismos 128 IDs.")

    opt_sess, opt_path, opt_hash = session("optimized")
    fp32_sess, fp32_path, fp32_hash = session("onnx_fp32")

    rows, fp32_agree = [], 0
    for item in manifest:
        image_path = MOD01 / item["path"]
        if sha256(image_path) != item["sha256"]:
            raise SystemExit(f"SHA-256 distinto en {item['path']}")
        tensor = mod01.PREPROCESS(Image.open(image_path).convert("RGB")).unsqueeze(0)
        array = tensor.numpy().astype(np.float32)
        opt_probs = predict(opt_sess, array)
        fp32_probs = predict(fp32_sess, array)
        orig = original[item["crop_id"]]
        if orig["true_class"] != item["class"]:
            raise SystemExit(f"La etiqueta de {item['crop_id']} no coincide con el manifiesto.")
        fp32_agree += mod01.CLASSES[int(np.argmax(fp32_probs))] == orig["pred_original"]
        rows.append(
            {
                "crop_id": item["crop_id"],
                "true_class": item["class"],
                "pred_original": orig["pred_original"],
                "pred_optimized": mod01.CLASSES[int(np.argmax(opt_probs))],
                **{f"prob_original_{c}": orig[f"prob_{c}"] for c in mod01.CLASSES},
                **{
                    f"prob_optimized_{c}": f"{p:.6f}"
                    for c, p in zip(mod01.CLASSES, opt_probs, strict=True)
                },
            }
        )

    with open(HERE / "predictions_validation.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    m_orig, m_opt = metrics(rows, "pred_original"), metrics(rows, "pred_optimized")
    agree = sum(r["pred_original"] == r["pred_optimized"] for r in rows)
    max_prob_diff = max(
        abs(float(r[f"prob_original_{c}"]) - float(r[f"prob_optimized_{c}"]))
        for r in rows
        for c in mod01.CLASSES
    )
    result = {
        "validation": {
            "manifest": "../mod-01/validation_manifest.csv",
            "manifest_sha256": sha256(MOD01 / "validation_manifest.csv"),
            "samples": len(rows),
            "support": {c: m_orig["per_class"][c]["support"] for c in mod01.CLASSES},
            "classes": mod01.CLASSES,
        },
        "original": {
            "model": "best.pt del Proyecto 3 (PyTorch), SHA-256 " + mod01.EXPECTED_SHA256,
            "predictions": "../mod-01/predictions_original_validation.csv",
            **m_orig,
        },
        "optimized": {
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
            "model": f"../mod-02/model/{fp32_path.name}",
            "sha256": fp32_hash,
            "same_class_as_original": f"{fp32_agree}/{len(rows)}",
        },
        "versions": {
            "python": platform.python_version(),
            "onnxruntime": ort.__version__,
            "numpy": np.__version__,
            "pillow": Image.__version__,
            "torch (solo preprocesamiento)": mod01.torch.__version__,
        },
        "platform": platform.platform(),
    }
    (HERE / "metrics.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")

    print(
        f"validación: {len(rows)} recortes (dog={result['validation']['support']['dog']}, "
        f"cat={result['validation']['support']['cat']})"
    )
    print(f"runtime: {result['optimized']['runtime']}")
    for label, m in (("original", m_orig), ("optimizada", m_opt)):
        per = "  ".join(f"{c}: F1={m['per_class'][c]['f1']:.4f}" for c in mod01.CLASSES)
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
    print("-> predictions_validation.csv, metrics.json")


if __name__ == "__main__":
    main()
