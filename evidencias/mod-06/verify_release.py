"""MOD-6 — Comprueba el Release de GitHub con los modelos.

Descarga cada archivo de SHA256SUMS desde el Release público, calcula su SHA-256 y lo
compara con el documentado (el mismo de MOD-1, MOD-2 y MOD-3). Solo biblioteca estándar.

Uso (desde esta carpeta):  python verify_release.py
Salida: verify_release_output.txt (lo mismo que se imprime) y código 1 si algo no coincide.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = "alebonita/Proyecto4-team2"
TAG = "modelos-v1.0.0"
HERE = Path(__file__).resolve().parent
RELEASE_URL = f"https://github.com/{REPO}/releases/tag/{TAG}"
DOWNLOAD_URL = f"https://github.com/{REPO}/releases/download/{TAG}/{{name}}"


def expected() -> list[tuple[str, str]]:
    rows = []
    for line in (HERE / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            rows.append((name.strip(), digest))
    return rows


def download_sha256(url: str) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(url, timeout=120) as resp:
        while chunk := resp.read(1 << 20):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def main() -> int:
    lines = [
        f"Release: {RELEASE_URL}",
        f"Fecha: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
    ]
    ok = True
    for name, digest in expected():
        url = DOWNLOAD_URL.format(name=name)
        try:
            got, size = download_sha256(url)
        except Exception as exc:  # noqa: BLE001 (se reporta y se marca como fallo)
            ok = False
            lines.append(f"FALLA  {name}: no se pudo descargar ({exc})")
            continue
        match = got == digest
        ok &= match
        lines.append(
            f"{'OK   ' if match else 'FALLA'}  {name}  {size:,} bytes  sha256={got}"
        )
        if not match:
            lines.append(f"       esperado sha256={digest}")
    lines += ["", "Todos coinciden." if ok else "Hay archivos que NO coinciden."]
    text = "\n".join(lines)
    print(text)
    (HERE / "verify_release_output.txt").write_text(text + "\n", encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
