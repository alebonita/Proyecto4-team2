"""Selecciona el conjunto de calibración de la variante optimizada (MOD-3).

Toma 150 recortes del split de entrenamiento del manifiesto del Proyecto 3 (75 dog y
75 cat) con una semilla fija, comprueba que ninguno pertenezca a validación ni a test,
y los copia desde el dataset local bajado con DVC a `calibracion/`, fuera de Git:

    calibracion/
        dog/<crop_id>.png
        cat/<crop_id>.png
    calibracion.zip              # el mismo contenido, para compartir

Solo la lista de IDs va al repositorio: `evidencias/calibracion/calibration-ids.csv`
con columnas crop_id, clase, split y sha256.

Uso, desde la raíz del repositorio y con los recortes ya bajados
(`dvc pull -r p2-origen data/crops`):

    python3 scripts/p4/select_calibration.py

Solo usa la biblioteca estándar. Códigos de salida: 0 bien, 1 error de datos.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import sys
import zipfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = REPO / "evidencias/mod-01/manifest_v0.1.1.json"
DEFAULT_CROPS_JSON = REPO / "reports/crops.json"
DEFAULT_CROPS_DIR = REPO / "data/crops"
DEFAULT_OUTPUT_DIR = REPO / "calibracion"
DEFAULT_CSV = REPO / "evidencias/calibracion/calibration-ids.csv"

CLASSES = ("dog", "cat")  # mismo orden que la salida del modelo
PER_CLASS = 75
SEED = 20261009
CALIBRATION_SPLIT = "train"
HELD_OUT_SPLITS = ("validation", "test")
# Fecha fija dentro del zip: el mismo contenido produce el mismo SHA-256.
ZIP_DATE = (2026, 10, 9, 0, 0, 0)


class DataError(Exception):
    """El manifiesto, crops.json o los recortes locales no son consistentes."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"No existe {path}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"{path} no es JSON válido: {exc}") from exc


def check_crops_json(manifest: dict, crops_json_path: Path) -> dict[str, dict]:
    """crops.json debe ser exactamente el que cita el manifiesto."""
    expected = manifest["provenance"]["crops_sha256"].removeprefix("sha256:")
    actual = sha256_of(crops_json_path)
    if actual != expected:
        raise DataError(
            f"{crops_json_path} no corresponde al manifiesto: SHA-256 {actual}, "
            f"se esperaba {expected}."
        )
    return {crop["crop_id"]: crop for crop in load_json(crops_json_path)["crops"]}


def select(records: list[dict], seed: int, per_class: int) -> list[dict]:
    """per_class recortes de entrenamiento por clase, reproducibles con la semilla."""
    rng = random.Random(seed)
    chosen: list[dict] = []
    for cls in CLASSES:
        pool = sorted(
            (r for r in records if r["split"] == CALIBRATION_SPLIT and r["class"] == cls),
            key=lambda r: r["crop_id"],
        )
        if len(pool) < per_class:
            raise DataError(f"Solo hay {len(pool)} recortes de {cls} en entrenamiento.")
        chosen.extend(sorted(rng.sample(pool, per_class), key=lambda r: r["crop_id"]))
    return chosen


def check_no_leakage(chosen: list[dict], records: list[dict]) -> None:
    """Ningún recorte, imagen de origen o grupo de duplicados de validación o test."""
    held_out = [r for r in records if r["split"] in HELD_OUT_SPLITS]
    for key in ("crop_id", "source_image_id", "duplicate_group"):
        forbidden = {r[key] for r in held_out}
        overlap = sorted({str(r[key]) for r in chosen if r[key] in forbidden})
        if overlap:
            raise DataError(f"{key} compartido con validación o test: {', '.join(overlap)}")
    not_train = [r["crop_id"] for r in chosen if r["split"] != CALIBRATION_SPLIT]
    if not_train:
        raise DataError(f"Recortes fuera de entrenamiento: {', '.join(not_train)}")


def copy_crops(
    chosen: list[dict], crops: dict[str, dict], crops_dir: Path, output_dir: Path
) -> list[dict]:
    """Copia cada recorte verificando su SHA-256 contra crops.json."""
    if output_dir.exists():
        # Sin restos de una selección anterior, pero solo si es una carpeta de este script.
        unexpected = [
            p
            for p in output_dir.rglob("*")
            if p.is_file() and not (p.suffix == ".png" and p.parent.name in CLASSES)
        ]
        if unexpected:
            raise DataError(
                f"{output_dir} tiene archivos que no son de una calibración "
                f"(p. ej. {unexpected[0]}); usa otra --output-dir."
            )
        shutil.rmtree(output_dir)
    rows = []
    for record in chosen:
        crop = crops[record["crop_id"]]
        source = crops_dir / crop["crop_path"]
        if not source.is_file():
            raise DataError(
                f"Falta {source}. Baja los recortes con: dvc pull -r p2-origen data/crops"
            )
        digest = sha256_of(source)
        if digest != crop["sha256"]:
            raise DataError(f"{source} no coincide con crops.json (SHA-256 {digest}).")
        target = output_dir / record["class"] / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rows.append(
            {
                "crop_id": record["crop_id"],
                "clase": record["class"],
                "split": record["split"],
                "sha256": digest,
            }
        )
    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["crop_id", "clase", "split", "sha256"], lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_zip(output_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as archive:
        for file in sorted(output_dir.rglob("*.png")):
            info = zipfile.ZipInfo(f"calibracion/{file.relative_to(output_dir)}", ZIP_DATE)
            info.external_attr = 0o644 << 16
            archive.writestr(info, file.read_bytes())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--crops-json", type=Path, default=DEFAULT_CROPS_JSON)
    parser.add_argument("--crops-dir", type=Path, default=DEFAULT_CROPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--seed", type=int, default=SEED)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        manifest = load_json(args.manifest)
        crops = check_crops_json(manifest, args.crops_json)
        records = manifest["records"]
        chosen = select(records, args.seed, PER_CLASS)
        check_no_leakage(chosen, records)
        rows = copy_crops(chosen, crops, args.crops_dir, args.output_dir)
    except DataError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    write_csv(rows, args.csv)
    zip_path = args.output_dir.with_suffix(".zip")
    write_zip(args.output_dir, zip_path)

    counts = Counter(row["clase"] for row in rows)
    splits = Counter(row["split"] for row in rows)
    print(f"Manifiesto: {manifest['dataset_version']} ({manifest['manifest_hash']})")
    print(f"Semilla: {args.seed}")
    for cls in CLASSES:
        print(f"  {cls}: {counts[cls]}")
    print(f"Total: {len(rows)}, todas del split {', '.join(sorted(splits))}")
    print("Ningún recorte, imagen de origen ni grupo de duplicados de validación o test.")
    print(f"Imágenes: {args.output_dir}")
    print(f"Zip: {zip_path} (SHA-256 {sha256_of(zip_path)})")
    print(f"Lista de IDs: {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
