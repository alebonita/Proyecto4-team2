"""EDG-3: lista en la terminal los ultimos eventos del historial local.

    python list_events.py          # los ultimos 10
    python list_events.py -n 25

Muestra ID, hora, clase, confianza y estado de envio, del mas reciente al mas antiguo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from capture import DEFAULT_CONFIG, ConfigError, load_config
from events import EventStore


def format_rows(events) -> list[str]:
    lines = [f"{'capture_id':<36}  {'hora (captured_at)':<29}  {'clase':<5}  conf.   estado"]
    for e in events:
        lines.append(
            f"{e.capture_id:<36}  {e.captured_at:<29}  {e.predicted_class:<5}  "
            f"{e.confidence:.4f}  {e.status}"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lista los ultimos eventos del historial.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="ruta de config.yaml")
    parser.add_argument("-n", type=int, default=10, help="cuantos eventos mostrar (10)")
    args = parser.parse_args(argv)
    if args.n < 1:
        parser.error("-n debe ser 1 o mas")

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
        events = store.latest(args.n)
        counts = store.count_by_status()
    print("\n".join(format_rows(events)))
    summary = ", ".join(f"{status}: {n}" for status, n in counts.items())
    print(f"\n{sum(counts.values())} eventos en total ({summary})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
