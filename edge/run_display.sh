#!/usr/bin/env bash
# Arranca capture.py con vista previa en la pantalla del propio equipo edge.
#
# Ubuntu Server no tiene escritorio: este script levanta un servidor grafico minimo
# (Xorg + openbox) solo mientras corre el programa, y lo cierra al salir con q.
# Se ejecuta desde la consola fisica (teclado y pantalla de la laptop), no por SSH.
#
#     ./run_display.sh            # mismas opciones que capture.py
set -euo pipefail

EDGE_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$EDGE_DIR/.venv/bin/python"

if [ -n "${DISPLAY:-}" ]; then
    # Ya dentro de la sesion grafica: openbox da el foco del teclado a la ventana.
    openbox &
    exec "$PYTHON" "$EDGE_DIR/capture.py" "$@"
fi

if [ ! -x "$PYTHON" ]; then
    echo "No existe $PYTHON. Crea el entorno virtual primero (README, paso 5)." >&2
    exit 1
fi
if ! command -v xinit >/dev/null || ! command -v openbox >/dev/null; then
    echo "Faltan xinit u openbox. Instalalos con el paso opcional del README:" >&2
    echo "  sudo apt install -y --no-install-recommends xserver-xorg xinit openbox" >&2
    exit 1
fi
TTY="$(tty)"
if ! [[ "$TTY" =~ ^/dev/tty([0-9]+)$ ]]; then
    echo "Ejecuta este script desde la consola fisica del equipo (tty1), no por SSH." >&2
    echo "Por SSH usa: python capture.py   (modo sin ventana)" >&2
    exit 1
fi

# Sin root, Xorg solo puede abrir la consola donde iniciaste sesion: hay que indicarla.
exec xinit "$EDGE_DIR/run_display.sh" "$@" -- :0 "vt${BASH_REMATCH[1]}" -keeptty -nolisten tcp
