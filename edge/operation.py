"""EDG-6: piezas para operar de forma continua durante la demo.

- Registro local: cada mensaje importante (arranque, capturas, envios y errores de camara,
  inferencia o envio) va a la terminal y a un archivo que rota solo (logs/edge.log).
- Captura por intervalo: con una tecla se activa o se detiene una captura cada N segundos.
- Latido: cada minuto se anota cuantas capturas van y la memoria del proceso, para
  comprobar que no crece durante una sesion larga.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import time
from pathlib import Path

log = logging.getLogger("edge")
log.addHandler(logging.NullHandler())  # sin setup_logging (p. ej. en pruebas) no se escribe nada


def setup_logging(path: Path) -> None:
    """Archivo de registro con rotacion: 1 MB por archivo, se conservan 3 anteriores."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S%z")
    )
    log.handlers[:] = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False


def report(message: str, error: bool = False) -> None:
    """Un mensaje a la terminal (stderr si es error) y al archivo de registro."""
    print(message, file=sys.stderr if error else sys.stdout, flush=True)
    (log.error if error else log.info)(message.strip())


class IntervalTrigger:
    """Captura cada `seconds` segundos mientras este activo; se activa y se detiene con toggle."""

    def __init__(self, seconds: float | None, clock=time.monotonic):
        self.seconds = seconds
        self.active = False
        self._clock = clock
        self._next = 0.0

    def toggle(self) -> bool:
        """Cambia el estado y lo devuelve. La primera captura sale al activar."""
        if not self.seconds:
            return False
        self.active = not self.active
        self._next = self._clock()
        return self.active

    def due(self) -> bool:
        if not self.active:
            return False
        now = self._clock()
        if now < self._next:
            return False
        self._next += self.seconds
        if self._next <= now:  # si una captura tardo mas que el intervalo, no se acumulan
            self._next = now + self.seconds
        return True

    def status(self) -> str | None:
        return f"Intervalo: cada {self.seconds:g} s (i: parar)" if self.active else None


def rss_mb() -> float | None:
    """Memoria residente del proceso en MB (Linux); None donde no se puede leer."""
    try:
        pages = int(Path("/proc/self/statm").read_text().split()[1])
    except (OSError, IndexError, ValueError):
        return None
    return pages * os.sysconf("SC_PAGE_SIZE") / 1024**2


class Heartbeat:
    """Cada `every_s` segundos anota en el registro las capturas hechas y la memoria."""

    def __init__(self, every_s: float = 60.0, clock=time.monotonic):
        self._every = every_s
        self._clock = clock
        self._next = clock() + every_s

    def tick(self, captures: int) -> None:
        now = self._clock()
        if now < self._next:
            return
        self._next = now + self._every
        memory = rss_mb()
        detail = f"{memory:.1f} MB" if memory is not None else "no disponible"
        log.info(f"Estado: {captures} capturas en esta sesion, memoria del proceso {detail}")
