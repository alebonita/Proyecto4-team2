"""Clasifica en esta laptop entradas conocidas, para contrastarlas con los registros.

    python classify_image.py img102-ann118 img263-ann299   # crop_id de la validacion del P3
    python classify_image.py foto.jpg                      # cualquier imagen (completa)
    python classify_image.py --todas --csv salida.csv      # las 128 de validacion

Usa exactamente el camino del programa de captura: lectura BGR con OpenCV, el
preprocesamiento de classifier.py y el modelo de config.yaml (cuyo SHA-256 imprime). Para
cada recorte de validacion muestra tambien la clase real, la del modelo original (MOD-1) y
la que registro MOD-4 para la misma variante en esta laptop, si existe ese registro.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
from capture import DEFAULT_CONFIG, EDGE_DIR, ConfigError, load_config
from classifier import Classifier, ModelError

REPO = EDGE_DIR.parent
MOD01 = REPO / "evidencias/mod-01"
# Lo que MOD-4 registro para cada variante corrida en esta laptop (--tag intel).
MOD4_EDGE = {
    "dog-cat-resnet18-1.0.0-int8-rr": REPO
    / "evidencias/mod-04/predictions_validation_int8-rr_intel.csv",
    "dog-cat-resnet18-1.0.0-int8": REPO / "evidencias/mod-04/predictions_validation_intel.csv",
}


def read_csv(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["crop_id"]: row for row in csv.DictReader(handle)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clasifica entradas conocidas en esta laptop.")
    parser.add_argument("entradas", nargs="*", help="crop_id de la validacion o rutas de imagen")
    parser.add_argument("--todas", action="store_true", help="las 128 imagenes de validacion")
    parser.add_argument("--csv", type=Path, help="guardar los resultados en un CSV")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    if not args.entradas and not args.todas:
        parser.error("indica crop_id o rutas de imagen, o --todas")

    try:
        config = load_config(args.config)
        classifier = Classifier(config["model"])
    except (ConfigError, ModelError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    for label, value in classifier.describe():
        print(f"{label + ':':<13}{value}")

    validation = read_csv(MOD01 / "validation_manifest.csv")
    original = read_csv(MOD01 / "predictions_original_validation.csv")
    mod4 = read_csv(MOD4_EDGE.get(classifier.cfg.version, Path()))
    entries = list(validation) if args.todas else args.entradas

    rows = []
    print(f"\n{'entrada':<16} {'real':<5} {'orig.':<5} {'MOD-4':<5} {'edge':<5} conf.   P(dog)  ms")
    for entry in entries:
        if entry in validation:
            path, true = MOD01 / validation[entry]["path"], validation[entry]["class"]
        else:
            path, true = Path(entry), ""
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if image is None:
            print(f"{entry:<16} no se pudo leer {path}", file=sys.stderr)
            continue
        height, width = image.shape[:2]
        pred = classifier.classify(image, (0, 0, width, height))
        orig = original.get(entry, {}).get("pred_original", "")
        ref = mod4.get(entry, {}).get("pred_optimized", "")
        rows.append(
            {
                "entrada": entry,
                "clase_real": true,
                "pred_original": orig,
                "pred_mod4_misma_laptop": ref,
                "pred_edge": pred.label,
                "confianza": f"{pred.confidence:.6f}",
                "prob_dog": f"{pred.probabilities.get('dog', 0):.6f}",
                "prob_cat": f"{pred.probabilities.get('cat', 0):.6f}",
                "ms": f"{pred.latency_ms:.2f}",
            }
        )
        print(
            f"{entry[:16]:<16} {true:<5} {orig:<5} {ref:<5} {pred.label:<5} "
            f"{pred.confidence:.4f}  {pred.probabilities.get('dog', 0):.4f}  {pred.latency_ms:.1f}"
        )

    labeled = [r for r in rows if r["clase_real"]]
    if labeled:
        correct = sum(r["pred_edge"] == r["clase_real"] for r in labeled)
        print(f"\nCorrectas: {correct}/{len(labeled)}")
        with_ref = [r for r in labeled if r["pred_mod4_misma_laptop"]]
        if with_ref:
            same = sum(r["pred_edge"] == r["pred_mod4_misma_laptop"] for r in with_ref)
            print(f"Misma clase que MOD-4 en esta laptop: {same}/{len(with_ref)}")
    if args.csv and rows:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        print(f"-> {args.csv}")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
