"""EDG-4: reenvia a AWS eventos del historial con su mismo capture_id.

    python retry.py <capture_id>       # ese evento, este en el estado que este
    python retry.py --todos            # los que estan en error o pendientes
    python retry.py --todos --incluir-rechazados   # tambien los rechazados con 400/401
    python retry.py <capture_id> --simular-fallo    # demostrar el fallo sin tocar el servidor

El servidor guarda cada capture_id una sola vez: 201 si es nuevo, 200 si ya existia. Al
reenviar no se genera un ID nuevo, asi que un reintento nunca duplica el registro. Despues
de un envio exitoso se consulta GET <api_url>/<capture_id> para mostrar el registro en AWS.
Los rechazos 400 y 401 no se reenvian con --todos: hay que corregir el dato o la clave.

Codigos de salida: 0 todos enviados, 1 alguno fallo, 2 configuracion o uso.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from capture import DEFAULT_CONFIG, EDGE_DIR, ConfigError, load_config
from events import EventStore
from sender import (
    PERMANENT_STATUSES,
    SIMULATED_FAILURE_URL,
    describe,
    read_device_key,
    send_and_record,
)


def fetch_remote(api_url: str, capture_id: str, timeout: float) -> dict | None:
    """El registro de AWS para ese capture_id, o None si no se pudo consultar."""
    import requests

    try:
        response = requests.get(f"{api_url}/{capture_id}", timeout=timeout)
        return response.json() if response.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def select_events(store: EventStore, args: argparse.Namespace) -> list:
    if args.capture_id:
        event = store.get(args.capture_id)
        return [event] if event else []
    events = store.with_status("error", "pendiente")
    if args.incluir_rechazados:
        return events
    return [e for e in events if e.send_http_status not in PERMANENT_STATUSES]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reenvia eventos a AWS con su mismo capture_id.")
    parser.add_argument("capture_id", nargs="?", help="capture_id del evento a reenviar")
    parser.add_argument(
        "--todos", action="store_true", help="todos los eventos en error o pendientes"
    )
    parser.add_argument(
        "--incluir-rechazados", action="store_true", help="con --todos, incluir 400 y 401"
    )
    parser.add_argument(
        "--simular-fallo", action="store_true", help="enviar a una URL donde nada escucha"
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="ruta de config.yaml")
    args = parser.parse_args(argv)
    if bool(args.capture_id) == args.todos:
        parser.error("indica un capture_id o --todos (solo uno)")

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 2
    upload = config["upload"]
    if args.simular_fallo:
        upload = replace(upload, api_url=SIMULATED_FAILURE_URL)
        print(f"SIMULANDO FALLO: los envios van a {SIMULATED_FAILURE_URL} y van a fallar.")
    key = read_device_key(upload)

    with EventStore(config["events_db"]) as store:
        events = select_events(store, args)
        if not events:
            target = args.capture_id or "en error o pendientes"
            print(f"No hay eventos {target} para reenviar.")
            return 1 if args.capture_id else 0

        failed = 0
        for event in events:
            result = send_and_record(store, event, upload, key, EDGE_DIR)
            print(f"{event.capture_id}  {event.predicted_class}  {describe(result)}")
            if not result.ok:
                failed += 1
                continue
            remote = fetch_remote(upload.api_url, event.capture_id, upload.timeout_s)
            if remote:
                print(
                    f"  En AWS: capture_id {remote.get('capture_id')}, "
                    f"received_at {remote.get('received_at')}, image_key {remote.get('image_key')}"
                )
        counts = store.count_by_status()

    print(f"\n{len(events) - failed}/{len(events)} enviados. Historial: {counts}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
