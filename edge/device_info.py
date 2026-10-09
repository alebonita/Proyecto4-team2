"""EDG-1: datos del equipo para la ficha de entrega.

Imprime marca y modelo (si el sistema los expone), procesador, nucleos, memoria RAM,
sistema operativo, camaras detectadas y version de Python. Solo usa la biblioteca
estandar, asi que corre sin instalar nada.

    python3 device_info.py
"""

from __future__ import annotations

import glob
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

UNKNOWN = "no disponible"


def _read(path: str) -> str | None:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    return text or None


def _run(*command: str) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _clean(value: str | None) -> str | None:
    """Descarta los valores de relleno que algunos fabricantes dejan en la BIOS."""
    if value is None:
        return None
    placeholders = {
        "to be filled by o.e.m.",
        "default string",
        "system product name",
        "unknown",
        "none",
    }
    return None if value.strip().lower() in placeholders else value.strip()


def brand_and_model() -> str:
    if sys.platform.startswith("linux"):
        vendor = _clean(_read("/sys/class/dmi/id/sys_vendor"))
        product = _clean(_read("/sys/class/dmi/id/product_name"))
        version = _clean(_read("/sys/class/dmi/id/product_version"))
        parts = [part for part in (vendor, product, version) if part]
        return " ".join(parts) if parts else UNKNOWN
    if sys.platform == "darwin":
        identifier = _run("sysctl", "-n", "hw.model")
        return f"Apple {identifier}" if identifier else UNKNOWN
    if sys.platform == "win32":
        output = _run("wmic", "computersystem", "get", "manufacturer,model", "/format:list")
        if output:
            pairs = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
            joined = " ".join(value.strip() for value in pairs.values() if value.strip())
            return joined or UNKNOWN
    return UNKNOWN


def processor() -> str:
    if sys.platform.startswith("linux"):
        cpuinfo = _read("/proc/cpuinfo") or ""
        match = re.search(r"^model name\s*:\s*(.+)$", cpuinfo, re.MULTILINE)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    if sys.platform == "darwin":
        brand = _run("sysctl", "-n", "machdep.cpu.brand_string")
        if brand:
            return brand
    return platform.processor() or platform.machine() or UNKNOWN


def physical_cores() -> int | None:
    if sys.platform.startswith("linux"):
        output = _run("lscpu", "-p=core,socket")
        if output:
            pairs = {line for line in output.splitlines() if line and not line.startswith("#")}
            if pairs:
                return len(pairs)
    if sys.platform == "darwin":
        value = _run("sysctl", "-n", "hw.physicalcpu")
        if value and value.isdigit():
            return int(value)
    return None


def cores() -> str:
    logical = os.cpu_count()
    physical = physical_cores()
    if logical is None:
        return UNKNOWN
    return f"{physical} fisicos, {logical} logicos" if physical else f"{logical} logicos"


def ram() -> str:
    total_bytes = None
    if sys.platform.startswith("linux"):
        match = re.search(r"^MemTotal:\s+(\d+) kB", _read("/proc/meminfo") or "", re.MULTILINE)
        if match:
            total_bytes = int(match.group(1)) * 1024
    elif sys.platform == "darwin":
        value = _run("sysctl", "-n", "hw.memsize")
        if value and value.isdigit():
            total_bytes = int(value)
    if total_bytes is None:
        return UNKNOWN
    return f"{total_bytes / 1024**3:.1f} GiB (memoria que ve el sistema)"


def operating_system() -> str:
    if sys.platform.startswith("linux"):
        release = _read("/etc/os-release") or ""
        match = re.search(r'^PRETTY_NAME="?([^"\n]+)"?$', release, re.MULTILINE)
        name = match.group(1) if match else platform.system()
        return f"{name} (kernel {platform.release()}, {platform.machine()})"
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


def cameras() -> str:
    if not sys.platform.startswith("linux"):
        return "la lista de camaras solo se consulta en Linux"
    found = []
    for node in sorted(glob.glob("/sys/class/video4linux/video*")):
        name = _read(f"{node}/name") or "sin nombre"
        found.append(f"/dev/{os.path.basename(node)}: {name}")
    return "; ".join(found) if found else "ninguna detectada (/dev/video* no existe)"


def collect() -> list[tuple[str, str]]:
    return [
        ("Marca y modelo", brand_and_model()),
        ("Procesador", processor()),
        ("Nucleos", cores()),
        ("Memoria RAM", ram()),
        ("Sistema operativo", operating_system()),
        ("Camaras", cameras()),
        ("Version de Python", platform.python_version()),
    ]


def main() -> int:
    rows = collect()
    width = max(len(label) for label, _ in rows)
    for label, value in rows:
        print(f"{label:<{width}} : {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
