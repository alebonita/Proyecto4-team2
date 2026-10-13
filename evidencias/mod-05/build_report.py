"""MOD-5 — Reporte antes/después: tamaño, accuracy, F1 y latencia de los dos modelos.

No corre ningún modelo: junta las mediciones que ya están en el repo y recalcula lo que se
puede recalcular, para que cada número del reporte tenga su origen.

  Tamaño     ../mod-02/export_log.json, ../mod-03/conversion_log_reduce_range.json
  Calidad    ../mod-04/metrics_int8-rr.json (CPU con VNNI) y metrics_int8-rr_intel.json (laptop edge)
  VNNI       ../mod-04/metrics.json y metrics_intel.json (primera variante int8) + predicciones
  Latencia   ../../artifacts/p4/benchmark.csv y benchmark-condiciones.json (EDG-5, laptop edge)

Uso (desde esta carpeta, solo biblioteca estándar):  python build_report.py
Salida: reporte.json y la tabla en pantalla.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MOD02 = ROOT / "evidencias" / "mod-02"
MOD03 = ROOT / "evidencias" / "mod-03"
MOD04 = ROOT / "evidencias" / "mod-04"
P4 = ROOT / "artifacts" / "p4"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def percentile(values: list[float], q: float) -> float:
    """Igual que numpy.percentile(method='linear')."""
    s = sorted(values)
    pos = (len(s) - 1) * q / 100
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def latency() -> dict:
    measures: dict[str, list[float]] = {}
    warmup: dict[str, int] = {}
    with (P4 / "benchmark.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            name = row["variante"]
            if row["es_calentamiento"].strip().lower() == "true":
                warmup[name] = warmup.get(name, 0) + 1
                continue
            measures.setdefault(name, []).append(float(row["ms"]))
    out = {}
    for name, ms in measures.items():
        out[name] = {
            "calentamiento": warmup.get(name, 0),
            "medidas": len(ms),
            "p50_ms": round(percentile(ms, 50), 4),
            "p95_ms": round(percentile(ms, 95), 4),
            "min_ms": round(min(ms), 4),
            "max_ms": round(max(ms), 4),
            "media_ms": round(statistics.fmean(ms), 4),
        }
    return out


def predictions(path: Path) -> dict[str, tuple[str, float]]:
    with path.open(encoding="utf-8", newline="") as f:
        return {
            r["crop_id"]: (r["pred_optimized"], float(r["prob_optimized_dog"]))
            for r in csv.DictReader(f)
        }


def between_machines(vnni_csv: str, edge_csv: str) -> dict:
    a = predictions(MOD04 / vnni_csv)
    b = predictions(MOD04 / edge_csv)
    flips = sorted(k for k in a if a[k][0] != b[k][0])
    return {
        "clase_distinta": len(flips),
        "recortes": flips,
        "max_abs_diff_p_dog": round(max(abs(a[k][1] - b[k][1]) for k in a), 6),
    }


def pct(before: float, after: float) -> float:
    return round(100 * (after - before) / before, 2)


def main() -> None:
    export = load(MOD02 / "export_log.json")
    conv = load(MOD03 / "conversion_log_reduce_range.json")
    cond = load(P4 / "benchmark-condiciones.json")
    rr_vnni = load(MOD04 / "metrics_int8-rr.json")
    rr_edge = load(MOD04 / "metrics_int8-rr_intel.json")
    i8_vnni = load(MOD04 / "metrics.json")
    i8_edge = load(MOD04 / "metrics_intel.json")

    fp32_bytes = export["onnx_bytes"]
    opt_bytes = cond["modelos"]["optimizado"]["bytes"]
    assert cond["modelos"]["original"]["sha256"] == export["onnx_sha256"], (
        "fp32 distinto en EDG-5"
    )
    assert cond["modelos"]["optimizado"]["sha256"] == rr_edge["optimized"]["sha256"], (
        "el benchmark no usó la variante evaluada en MOD-4"
    )
    assert rr_vnni["optimized"]["correct"] == rr_edge["optimized"]["correct"]

    lat = latency()
    orig, opt = lat["original"], lat["optimizado"]
    for name, key in (
        ("original", "p50_ms"),
        ("original", "p95_ms"),
        ("optimizado", "p50_ms"),
        ("optimizado", "p95_ms"),
    ):
        assert abs(lat[name][key] - cond["resultados"][name][key]) < 1e-3, (name, key)

    o, q = rr_edge["original"], rr_edge["optimized"]
    report = {
        "original": {
            "modelo": "best.pt del Proyecto 3 (calidad) / su ONNX fp32 de MOD-2 (latencia)",
            "best_pt_sha256": export["source_sha256"],
            "best_pt_bytes": export["source_bytes"],
            "onnx_fp32_sha256": export["onnx_sha256"],
            "onnx_fp32_bytes": fp32_bytes,
            "correctas": o["correct"],
            "accuracy": o["accuracy"],
            "f1_macro": o["f1_macro"],
            "latencia_laptop_edge": orig,
        },
        "optimizado": {
            "modelo": "INT8 estático, reduce_range=True (int8-rr, MOD-3b)",
            "sha256": q["sha256"],
            "bytes": opt_bytes,
            "correctas": q["correct"],
            "accuracy": q["accuracy"],
            "f1_macro": q["f1_macro"],
            "misma_clase_que_original": rr_edge["same_class_as_original"],
            "max_abs_diff_prob_vs_original": rr_edge["max_abs_diff_prob"],
            "latencia_laptop_edge": opt,
        },
        "cambio": {
            "tamano_pct_vs_onnx_fp32": pct(fp32_bytes, opt_bytes),
            "tamano_pct_vs_best_pt": pct(export["source_bytes"], opt_bytes),
            "conversion_log_pct": conv.get("size_reduction_pct"),
            "accuracy_pp": round(100 * (q["accuracy"] - o["accuracy"]), 4),
            "f1_macro_pp": round(100 * (q["f1_macro"] - o["f1_macro"]), 4),
            "p50_pct": pct(orig["p50_ms"], opt["p50_ms"]),
            "p95_pct": pct(orig["p95_ms"], opt["p95_ms"]),
            "p95_opt_menor_que_min_original": opt["p95_ms"] < orig["min_ms"],
        },
        "vnni": {
            "cpu_con_vnni": rr_vnni["machine"]["cpu"]["model"],
            "cpu_laptop_edge": rr_edge["machine"]["cpu"]["model"],
            "int8": {
                "correctas_con_vnni": i8_vnni["optimized"]["correct"],
                "correctas_laptop_edge": i8_edge["optimized"]["correct"],
                "entre_computadoras": between_machines(
                    "predictions_validation.csv", "predictions_validation_intel.csv"
                ),
            },
            "int8_rr": {
                "correctas_con_vnni": rr_vnni["optimized"]["correct"],
                "correctas_laptop_edge": rr_edge["optimized"]["correct"],
                "entre_computadoras": between_machines(
                    "predictions_validation_int8-rr.csv",
                    "predictions_validation_int8-rr_intel.csv",
                ),
            },
        },
        "condiciones_latencia": {
            k: cond[k]
            for k in (
                "fecha",
                "equipo",
                "onnxruntime",
                "proveedor",
                "hilos",
                "medicion",
            )
        },
    }
    (HERE / "reporte.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    rows = [
        (
            "Tamaño (bytes)",
            f"{fp32_bytes:,} (ONNX fp32)",
            f"{opt_bytes:,}",
            f"{report['cambio']['tamano_pct_vs_onnx_fp32']:+.2f} %",
        ),
        (
            "Accuracy (128 val.)",
            f"{o['accuracy']:.4f} ({o['correct']}/128)",
            f"{q['accuracy']:.4f} ({q['correct']}/128)",
            f"{report['cambio']['accuracy_pp']:+.2f} pp",
        ),
        (
            "F1 macro",
            f"{o['f1_macro']:.4f}",
            f"{q['f1_macro']:.4f}",
            f"{report['cambio']['f1_macro_pp']:+.2f} pp",
        ),
        (
            "Latencia p50 (ms)",
            f"{orig['p50_ms']:.2f}",
            f"{opt['p50_ms']:.2f}",
            f"{report['cambio']['p50_pct']:+.1f} %",
        ),
        (
            "Latencia p95 (ms)",
            f"{orig['p95_ms']:.2f}",
            f"{opt['p95_ms']:.2f}",
            f"{report['cambio']['p95_pct']:+.1f} %",
        ),
    ]
    print(f"{'':22} {'Original':26} {'Optimizado (int8-rr)':22} Cambio")
    for r in rows:
        print(f"{r[0]:22} {r[1]:26} {r[2]:22} {r[3]}")
    v = report["vnni"]
    print(
        f"\nVNNI  int8: {v['int8']['correctas_con_vnni']} vs {v['int8']['correctas_laptop_edge']}/128,"
        f" {v['int8']['entre_computadoras']['clase_distinta']} clases distintas"
        f" | int8-rr: {v['int8_rr']['correctas_con_vnni']} vs {v['int8_rr']['correctas_laptop_edge']}/128,"
        f" {v['int8_rr']['entre_computadoras']['clase_distinta']} clases distintas"
    )
    print("-> reporte.json")


if __name__ == "__main__":
    main()
