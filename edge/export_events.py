"""EDG-3: exporta el historial local de capturas a JSON.

    python export_events.py                    # a la terminal
    python export_events.py -o eventos.json    # a un archivo

Es la version "local" de las capturas que se contrasta con AWS y el portal: un objeto con
el dispositivo, la fecha de exportacion, el conteo por estado y la lista de eventos del mas
antiguo al mas reciente.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from capture import DEFAULT_CONFIG, ConfigError, load_config
from events import EventStore, now_iso


def export(store: EventStore, device_id: str) -> dict:
    events = store.all()
    return {
        "exported_at": now_iso(),
        "device_id": device_id,
        "total": len(events),
        "by_status": store.count_by_status(),
        "events": [event.to_dict() for event in events],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Exporta el historial de capturas a JSON.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="ruta de config.yaml")
    parser.add_argument("-o", "--output", type=Path, help="archivo de salida (por defecto, stdout)")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"Error de configuracion: {exc}", file=sys.stderr)
        return 2
    if not config["events_db"].is_file():
        print(
            f"No existe el historial {config['events_db']}: aun no hay capturas.", file=sys.stderr
        )
        return 1

    with EventStore(config["events_db"]) as store:
        data = export(store, config["device_id"])
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"{data['total']} eventos exportados a {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
