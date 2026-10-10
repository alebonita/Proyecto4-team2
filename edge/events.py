"""EDG-3: historial local de capturas en SQLite.

Cada captura produce un evento con los campos del contrato del endpoint (AWS-1/AWS-2):
capture_id, captured_at, device_id, model_version, predicted_class, confidence,
latency_ms y crop. Se guarda junto con la ruta y el SHA-256 de su foto y un estado de
envio (pendiente, enviado o error). El historial vive en un archivo SQLite, asi que se
conserva al cerrar y volver a abrir el programa; export_events.py lo exporta a JSON.

El envio a AWS (EDG-4) llena received_at, image_key, send_error, send_http_status y
send_ms; send_ms se mide aparte y nunca se suma a latency_ms.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

STATUSES = ("pendiente", "enviado", "error")

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    capture_id      TEXT PRIMARY KEY,
    captured_at     TEXT NOT NULL,
    device_id       TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    predicted_class TEXT NOT NULL,
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    latency_ms      REAL NOT NULL CHECK (latency_ms >= 0),
    crop_x          INTEGER NOT NULL,
    crop_y          INTEGER NOT NULL,
    crop_width      INTEGER NOT NULL,
    crop_height     INTEGER NOT NULL,
    photo_path      TEXT NOT NULL,
    photo_sha256    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pendiente'
                    CHECK (status IN ('pendiente', 'enviado', 'error')),
    received_at     TEXT,
    image_key       TEXT,
    send_error      TEXT,
    send_ms         REAL,
    send_http_status INTEGER
);
CREATE INDEX IF NOT EXISTS events_captured_at ON events (captured_at);
"""
# Columnas agregadas despues de EDG-3: se crean en historiales que ya existian.
ADDED_COLUMNS = {"send_http_status": "INTEGER"}


def new_capture_id() -> str:
    """UUID4 en texto: cabe en el patron del servidor ([A-Za-z0-9_-], hasta 64)."""
    return str(uuid.uuid4())


def now_iso() -> str:
    """Fecha y hora local con zona horaria, ISO 8601 con milisegundos."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@dataclass(frozen=True)
class Event:
    capture_id: str
    captured_at: str
    device_id: str
    model_version: str
    predicted_class: str
    confidence: float
    latency_ms: float
    crop: tuple[int, int, int, int]
    photo_path: str
    photo_sha256: str
    status: str = "pendiente"
    received_at: str | None = None
    image_key: str | None = None
    send_error: str | None = None
    send_ms: float | None = None
    send_http_status: int | None = None

    def to_dict(self) -> dict:
        x, y, width, height = self.crop
        return {
            "capture_id": self.capture_id,
            "captured_at": self.captured_at,
            "device_id": self.device_id,
            "model_version": self.model_version,
            "predicted_class": self.predicted_class,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "crop": {"x": x, "y": y, "width": width, "height": height},
            "photo_path": self.photo_path,
            "photo_sha256": self.photo_sha256,
            "status": self.status,
            "received_at": self.received_at,
            "image_key": self.image_key,
            "send_error": self.send_error,
            "send_ms": self.send_ms,
            "send_http_status": self.send_http_status,
        }


class EventStore:
    """Historial en un archivo SQLite; cada evento se confirma al guardarlo."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        # timeout: el envio en segundo plano usa su propia conexion al mismo archivo.
        self._db = sqlite3.connect(path, timeout=10)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        existing = {row["name"] for row in self._db.execute("PRAGMA table_info(events)")}
        with self._db:
            for name, kind in ADDED_COLUMNS.items():
                if name not in existing:
                    self._db.execute(f"ALTER TABLE events ADD COLUMN {name} {kind}")

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> EventStore:
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def add(self, event: Event) -> None:
        if event.status not in STATUSES:
            raise ValueError(f"estado invalido: {event.status}")
        x, y, width, height = event.crop
        with self._db:
            self._db.execute(
                "INSERT INTO events (capture_id, captured_at, device_id, model_version, "
                "predicted_class, confidence, latency_ms, crop_x, crop_y, crop_width, "
                "crop_height, photo_path, photo_sha256, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.capture_id,
                    event.captured_at,
                    event.device_id,
                    event.model_version,
                    event.predicted_class,
                    event.confidence,
                    event.latency_ms,
                    x,
                    y,
                    width,
                    height,
                    event.photo_path,
                    event.photo_sha256,
                    event.status,
                ),
            )

    def mark_sent(
        self, capture_id: str, received_at: str | None, image_key: str | None, http_status, ms
    ) -> None:
        with self._db:
            self._db.execute(
                "UPDATE events SET status = 'enviado', received_at = ?, image_key = ?, "
                "send_error = NULL, send_http_status = ?, send_ms = ? WHERE capture_id = ?",
                (received_at, image_key, http_status, ms, capture_id),
            )

    def mark_error(self, capture_id: str, error: str, http_status, ms) -> None:
        with self._db:
            self._db.execute(
                "UPDATE events SET status = 'error', send_error = ?, send_http_status = ?, "
                "send_ms = ? WHERE capture_id = ?",
                (error, http_status, ms, capture_id),
            )

    def with_status(self, *statuses: str) -> list[Event]:
        marks = ", ".join("?" for _ in statuses)
        rows = self._db.execute(
            f"SELECT * FROM events WHERE status IN ({marks}) ORDER BY captured_at, rowid",
            statuses,
        )
        return [_to_event(row) for row in rows]

    def get(self, capture_id: str) -> Event | None:
        row = self._db.execute(
            "SELECT * FROM events WHERE capture_id = ?", (capture_id,)
        ).fetchone()
        return _to_event(row) if row else None

    def all(self) -> list[Event]:
        """Todos los eventos, del mas antiguo al mas reciente."""
        rows = self._db.execute("SELECT * FROM events ORDER BY captured_at, rowid")
        return [_to_event(row) for row in rows]

    def latest(self, limit: int) -> list[Event]:
        """Los ultimos `limit` eventos, del mas reciente al mas antiguo."""
        rows = self._db.execute(
            "SELECT * FROM events ORDER BY captured_at DESC, rowid DESC LIMIT ?", (limit,)
        )
        return [_to_event(row) for row in rows]

    def count_by_status(self) -> dict[str, int]:
        rows = self._db.execute("SELECT status, COUNT(*) FROM events GROUP BY status")
        counts = dict.fromkeys(STATUSES, 0)
        counts.update(dict(rows))
        return counts


def _to_event(row: sqlite3.Row) -> Event:
    return Event(
        capture_id=row["capture_id"],
        captured_at=row["captured_at"],
        device_id=row["device_id"],
        model_version=row["model_version"],
        predicted_class=row["predicted_class"],
        confidence=row["confidence"],
        latency_ms=row["latency_ms"],
        crop=(row["crop_x"], row["crop_y"], row["crop_width"], row["crop_height"]),
        photo_path=row["photo_path"],
        photo_sha256=row["photo_sha256"],
        status=row["status"],
        received_at=row["received_at"],
        image_key=row["image_key"],
        send_error=row["send_error"],
        send_ms=row["send_ms"],
        send_http_status=row["send_http_status"],
    )
