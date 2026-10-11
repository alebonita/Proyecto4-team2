"""EDG-3: cada captura crea un evento completo con su foto, el historial se conserva al
cerrar y volver a abrir, y se exporta a JSON.

No necesita la camara ni el modelo: usa un clasificador de prueba y cuadros sinteticos.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

EDGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EDGE_DIR))

from capture import Capturer, FrameSaver  # noqa: E402
from classifier import Prediction, sha256_of  # noqa: E402
from events import EventStore  # noqa: E402
from export_events import export  # noqa: E402
from list_events import format_rows  # noqa: E402

# Patron que acepta el servidor para capture_id (backend/src/logic/edge-capture.validation.ts).
SERVER_CAPTURE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CONTRACT_FIELDS = {
    "capture_id",
    "captured_at",
    "device_id",
    "model_version",
    "predicted_class",
    "confidence",
    "latency_ms",
    "crop",
}


class FakeClassifier:
    cfg = SimpleNamespace(version="modelo-de-prueba")

    def classify(self, frame, crop):
        return Prediction("cat", 0.875, 12.5, {"dog": 0.125, "cat": 0.875})


class CaptureHistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "events.db"
        self.store = EventStore(self.db)
        saver = FrameSaver(cv2, self.tmp / "captures", 90)
        self.capturer = Capturer(saver, FakeClassifier(), 0.8, self.store, "edge-prueba")
        self.frame = np.full((480, 640, 3), 128, dtype=np.uint8)

    def tearDown(self):
        self.store.close()

    def test_capture_creates_a_complete_event_with_its_photo(self):
        self.capturer.capture(self.frame)
        [event] = self.store.all()

        uuid.UUID(event.capture_id)  # es un UUID
        self.assertRegex(event.capture_id, SERVER_CAPTURE_ID)
        self.assertIsNotNone(datetime.fromisoformat(event.captured_at).tzinfo)
        self.assertEqual(event.device_id, "edge-prueba")
        self.assertEqual(event.model_version, "modelo-de-prueba")
        self.assertEqual(event.predicted_class, "cat")
        self.assertEqual(event.confidence, 0.875)
        self.assertEqual(event.latency_ms, 12.5)
        self.assertEqual(event.crop, (128, 48, 384, 384))
        self.assertEqual(event.status, "pendiente")

        photo = Path(event.photo_path)
        self.assertTrue(photo.is_file())
        self.assertIn(event.capture_id, photo.name)  # la foto se rastrea por su ID
        self.assertEqual(event.photo_sha256, sha256_of(photo))

    def test_each_capture_gets_its_own_id(self):
        for _ in range(3):
            self.capturer.capture(self.frame)
        ids = [event.capture_id for event in self.store.all()]
        self.assertEqual(len(set(ids)), 3)

    def test_history_survives_closing_and_reopening(self):
        self.capturer.capture(self.frame)
        [before] = self.store.all()
        self.store.close()

        self.store = EventStore(self.db)
        self.assertEqual(self.store.get(before.capture_id), before)

    def test_export_has_every_event_with_contract_fields(self):
        for _ in range(2):
            self.capturer.capture(self.frame)
        data = json.loads(json.dumps(export(self.store, "edge-prueba")))

        self.assertEqual(data["total"], 2)
        self.assertEqual(data["by_status"], {"pendiente": 2, "enviado": 0, "error": 0})
        for item in data["events"]:
            self.assertLessEqual(CONTRACT_FIELDS, item.keys())
            self.assertEqual(set(item["crop"]), {"x", "y", "width", "height"})
            self.assertIn(item["status"], ("pendiente", "enviado", "error"))
        times = [item["captured_at"] for item in data["events"]]
        self.assertEqual(times, sorted(times))  # del mas antiguo al mas reciente

    def test_list_shows_id_time_class_confidence_and_status(self):
        self.capturer.capture(self.frame)
        [event] = self.store.latest(10)
        line = format_rows([event])[1]
        for value in (event.capture_id, event.captured_at, "cat", "0.8750", "pendiente"):
            self.assertIn(value, line)

    def test_rejects_an_invalid_status(self):
        self.capturer.capture(self.frame)
        [event] = self.store.all()
        with self.assertRaises(ValueError):
            self.store.add(event.__class__(**{**event.__dict__, "capture_id": "x", "status": "?"}))


if __name__ == "__main__":
    unittest.main()
