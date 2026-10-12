"""EDG-5: mide en esta laptop cuanto tarda cada modelo (preprocesamiento + inferencia).

    python benchmark.py          # fp32 de MOD-2 contra la variante de config.yaml
    python benchmark.py --original models/a.onnx --optimizado models/b.onnx --hilos 2

Para cada modelo: crea una sesion de onnxruntime en CPU con el mismo numero de hilos, toma
la misma imagen fija del repositorio, hace 10 repeticiones de calentamiento y 100 medidas.
Cada repeticion mide con time.perf_counter el preprocesamiento (el mismo de classifier.py:
recorte, BGR -> RGB, 128x128 con Pillow, normalizacion) mas la inferencia y el softmax. No
incluye leer el archivo de la imagen ni el envio a AWS.

Escribe en artifacts/p4/ (desde la raiz del repositorio):
  benchmark.csv                variante, repeticion, es_calentamiento, ms (una fila por repeticion)
  benchmark-condiciones.json   equipo, runtime, hilos, entrada, modelos (SHA-256 y bytes),
                               corriente, carga del sistema y fecha

Al terminar imprime p50 y p95 de cada variante (interpolacion lineal sobre las 100
mediciones validas) y la diferencia entre ambas.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from capture import DEFAULT_CONFIG, EDGE_DIR, ConfigError, load_config
from classifier import PROVIDER, preprocess, sha256_of, softmax

REPO = EDGE_DIR.parent
# Imagen fija: un recorte de validacion del Proyecto 3 que esta en el repositorio.
DEFAULT_IMAGE = REPO / "evidencias/mod-01/validation/dog/img102-ann118.png"
DEFAULT_ORIGINAL = EDGE_DIR / "models/dog-cat-resnet18-1.0.0-fp32.onnx"
DEFAULT_OUTPUT = REPO / "artifacts/p4"
WARMUP = 10
MEASURED = 100


def measure(path: Path, image: np.ndarray, cfg, threads: int) -> list[float]:
    """110 tiempos en ms: los primeros WARMUP son calentamiento."""
    options = ort.SessionOptions()
    options.intra_op_num_threads = threads
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(path), sess_options=options, providers=[PROVIDER])
    name = session.get_inputs()[0].name
    height, width = image.shape[:2]
    crop = (0, 0, width, height)
    times = []
    for _ in range(WARMUP + MEASURED):
        start = time.perf_counter()
        tensor = preprocess(image, crop, cfg)
        softmax(session.run(None, {name: tensor})[0][0].astype(np.float64))
        times.append((time.perf_counter() - start) * 1000)
    return times


def percentiles(values: list[float]) -> tuple[float, float]:
    p50, p95 = np.percentile(values, [50, 95], method="linear")
    return float(p50), float(p95)


def power_status() -> str:
    """Si la laptop esta conectada a la corriente (Linux)."""
    supplies = Path("/sys/class/power_supply")
    for online in supplies.glob("*/online"):
        try:
            return (
                "conectada a la corriente" if online.read_text().strip() == "1" else "con bateria"
            )
        except OSError:
            continue
    return "no disponible"


def heavy_processes() -> dict:
    """Carga del sistema y servicios pesados conocidos, para documentar las condiciones."""
    info = {"loadavg_1_5_15": None, "k3s_activo": None}
    with contextlib.suppress(OSError):
        info["loadavg_1_5_15"] = [float(x) for x in Path("/proc/loadavg").read_text().split()[:3]]
    try:
        state = subprocess.run(
            ["systemctl", "is-active", "k3s"], capture_output=True, text=True, timeout=5
        ).stdout.strip()
        info["k3s_activo"] = state == "active"
    except (OSError, subprocess.SubprocessError):
        pass
    return info


def equipment() -> dict:
    import device_info

    return dict(device_info.collect())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark de los modelos en esta laptop.")
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument(
        "--optimizado", type=Path, help="por defecto, model.path de config.yaml (el desplegado)"
    )
    parser.add_argument(
        "--hilos", type=int, help="hilos de onnxruntime (por defecto, nucleos fisicos)"
    )
    parser.add_argument("--imagen", type=Path, default=DEFAULT_IMAGE)
    parser.add_argument("--salida", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 2
    cfg = config["model"]
    models = {"original": args.original, "optimizado": args.optimizado or cfg.path}
    for variant, path in models.items():
        if not path.is_file():
            print(f"No existe el modelo {variant}: {path}", file=sys.stderr)
            return 1
    image = cv2.imread(str(args.imagen), cv2.IMREAD_COLOR)
    if image is None:
        print(f"No se pudo leer la imagen {args.imagen}", file=sys.stderr)
        return 1

    import device_info

    threads = args.hilos or device_info.physical_cores() or os.cpu_count() or 1
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    load_before = heavy_processes()
    results = {}
    for variant, path in models.items():
        print(f"Midiendo {variant}: {path.name} ({WARMUP} calentamiento + {MEASURED} medidas)...")
        results[variant] = measure(path, image, cfg, threads)
    load_after = heavy_processes()

    args.salida.mkdir(parents=True, exist_ok=True)
    csv_path = args.salida / "benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["variante", "repeticion", "es_calentamiento", "ms"])
        for variant, times in results.items():
            for i, ms in enumerate(times, start=1):
                writer.writerow([variant, i, "true" if i <= WARMUP else "false", f"{ms:.4f}"])

    summary = {}
    for variant, times in results.items():
        p50, p95 = percentiles(times[WARMUP:])
        summary[variant] = {"p50_ms": round(p50, 4), "p95_ms": round(p95, 4)}
    conditions = {
        "fecha": started,
        "equipo": equipment(),
        "alimentacion": power_status(),
        "carga_del_sistema": {"antes": load_before, "despues": load_after},
        "python": platform.python_version(),
        "onnxruntime": ort.__version__,
        "proveedor": PROVIDER,
        "hilos": {"intra_op": threads, "inter_op": 1},
        "entrada": {
            "tensor": [1, 3, cfg.input_size, cfg.input_size],
            "imagen": str(args.imagen.resolve().relative_to(REPO)),
            "imagen_sha256": sha256_of(args.imagen),
            "imagen_pixeles": list(image.shape[1::-1]),
        },
        "medicion": {
            "calentamiento": WARMUP,
            "medidas": MEASURED,
            "reloj": "time.perf_counter",
            "incluye": "preprocesamiento (recorte, BGR->RGB, resize 128x128 Pillow, "
            "normalizacion) + inferencia + softmax; sin lectura de archivo ni envio",
            "percentiles": "numpy.percentile, method='linear', sobre las 100 medidas",
        },
        "modelos": {
            variant: {
                "archivo": path.name,
                "sha256": sha256_of(path),
                "bytes": path.stat().st_size,
            }
            for variant, path in models.items()
        },
        "resultados": summary,
    }
    json_path = args.salida / "benchmark-condiciones.json"
    json_path.write_text(json.dumps(conditions, ensure_ascii=False, indent=2) + "\n", "utf-8")

    original, optimized = summary["original"], summary["optimizado"]
    print()
    for variant, values in summary.items():
        print(f"{variant:<11} p50 = {values['p50_ms']:7.2f} ms   p95 = {values['p95_ms']:7.2f} ms")
    for key in ("p50_ms", "p95_ms"):
        diff = original[key] - optimized[key]
        print(
            f"diferencia {key[:3]}: {diff:+.2f} ms "
            f"({100 * diff / original[key]:+.1f} % a favor del optimizado)"
        )
    sizes = {v: conditions["modelos"][v]["bytes"] for v in models}
    print(
        f"tamano: {sizes['original']:,} -> {sizes['optimizado']:,} bytes "
        f"({100 * (1 - sizes['optimizado'] / sizes['original']):.2f} % menos)"
    )
    print(f"\n-> {csv_path}\n-> {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
