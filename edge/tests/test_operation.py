"""EDG-6: el programa aguanta el uso continuo de la demo.

- La captura por intervalo dispara a tiempo y no acumula capturas atrasadas.
- Un error al guardar la foto no tumba el programa y queda en el archivo de registro.
- Si la camara deja de entregar imagen, se libera y se reabre sola.
- 300 capturas seguidas con el modelo real no hacen crecer la memoria (solo Linux, donde se
  puede leer la memoria del proceso; se salta si no esta el modelo).

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import cv2
import numpy as np

EDGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EDGE_DIR))

import capture  # noqa: E402
import operation  # noqa: E402
from capture import Camera, CameraError, Capturer, FrameSaver, load_config  # noqa: E402
from classifier import Prediction  # noqa: E402
from events import EventStore  # noqa: E402
from operation import Heartbeat, IntervalTrigger, rss_mb, setup_logging  # noqa: E402


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class FakeClassifier:
    cfg = SimpleNamespace(version="modelo-de-prueba")

    def classify(self, frame, crop):
        return Prediction("dog", 0.9, 10.0, {"dog": 0.9, "cat": 0.1})


class IntervalTest(unittest.TestCase):
    def test_fires_on_activation_and_then_every_interval(self):
        clock = FakeClock()
        trigger = IntervalTrigger(10, clock)
        self.assertFalse(trigger.due())  # inactivo
        self.assertTrue(trigger.toggle())
        self.assertTrue(trigger.due())  # la primera sale al activar
        clock.now += 9.9
        self.assertFalse(trigger.due())
        clock.now += 0.1
        self.assertTrue(trigger.due())
        self.assertEqual(trigger.status(), "Intervalo: cada 10 s (i: parar)")

    def test_does_not_pile_up_late_captures(self):
        clock = FakeClock()
        trigger = IntervalTrigger(10, clock)
        trigger.toggle()
        trigger.due()
        clock.now += 35  # una pausa larga no genera tres capturas seguidas
        self.assertTrue(trigger.due())
        self.assertFalse(trigger.due())

    def test_stops_and_cannot_start_without_interval(self):
        trigger = IntervalTrigger(10, FakeClock())
        trigger.toggle()
        self.assertFalse(trigger.toggle())
        self.assertFalse(trigger.due())
        self.assertFalse(IntervalTrigger(None).toggle())


class LoggingAndErrorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.log_file = self.tmp / "logs" / "edge.log"
        setup_logging(self.log_file)
        self.store = EventStore(self.tmp / "events.db")

    def tearDown(self):
        self.store.close()
        for handler in operation.log.handlers:
            handler.close()
        operation.log.handlers[:] = [logging.NullHandler()]

    def test_save_error_is_shown_logged_and_does_not_stop_the_program(self):
        saver = FrameSaver(cv2, self.tmp / "captures", 90)
        capturer = Capturer(saver, FakeClassifier(), 0.8, self.store, "edge-prueba")
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        with mock.patch.object(saver, "save", side_effect=CameraError("disco lleno")):
            capturer.capture(frame)  # no lanza
        self.assertTrue(capturer.last_failed)
        self.assertIn("disco lleno", capturer.last_text)
        self.assertEqual(self.store.all(), [])

        capturer.capture(frame)  # la siguiente captura funciona
        self.assertEqual(len(self.store.all()), 1)
        text = self.log_file.read_text()
        self.assertIn("ERROR", text)
        self.assertIn("disco lleno", text)
        self.assertIn("Clase: dog", text)

    def test_heartbeat_writes_captures_and_memory(self):
        clock = FakeClock()
        heartbeat = Heartbeat(60, clock)
        heartbeat.tick(3)
        clock.now += 60
        heartbeat.tick(7)
        self.assertIn("Estado: 7 capturas", self.log_file.read_text())


class CameraReconnectTest(unittest.TestCase):
    def test_camera_that_stops_is_released_and_reopened(self):
        caps = [mock.Mock(name="cap1"), mock.Mock(name="cap2")]
        config = {"camera_index": 0, "width": None, "height": None, "warmup_frames": 0}
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        with (
            mock.patch.object(capture, "open_camera", side_effect=caps),
            mock.patch.object(
                capture, "read_frame", side_effect=[CameraError("sin imagen"), frame]
            ),
            mock.patch.object(capture, "RECONNECT_SECONDS", 0),
            mock.patch.object(capture, "report"),
        ):
            camera = Camera(cv2, config)
            self.assertIsNone(camera.read())  # deja de entregar imagen
            caps[0].release.assert_called_once()
            self.assertIn("Error de camara", camera.error)
            self.assertIs(camera.read(), frame)  # se reabrio sola
            self.assertIs(camera.cap, caps[1])
            self.assertIsNone(camera.error)


CONFIG = load_config(Path(os.environ.get("EDGE_CONFIG", EDGE_DIR / "config.yaml")))


@unittest.skipUnless(rss_mb() is not None, "solo Linux puede leer la memoria del proceso")
@unittest.skipUnless(CONFIG["model"].path.is_file(), "no esta el modelo")
class MemoryTest(unittest.TestCase):
    def test_300_captures_do_not_grow_memory(self):
        from classifier import Classifier

        tmp = Path(tempfile.mkdtemp())
        classifier = Classifier(CONFIG["model"])  # una sola sesion de onnxruntime
        with EventStore(tmp / "events.db") as store:
            saver = FrameSaver(cv2, tmp / "captures", 90)
            capturer = Capturer(saver, classifier, 0.8, store, "edge-prueba")
            rng = np.random.default_rng(0)
            frames = [rng.integers(0, 255, (480, 640, 3), dtype=np.uint8) for _ in range(4)]
            for i in range(50):  # calentamiento: memoria de onnxruntime, SQLite y OpenCV
                capturer.capture(frames[i % 4])
            before = rss_mb()
            for i in range(300):
                capturer.capture(frames[i % 4])
            after = rss_mb()
            self.assertEqual(len(store.all()), 350)
        print(f"\nmemoria: {before:.1f} MB -> {after:.1f} MB en 300 capturas", file=sys.__stderr__)
        self.assertLess(after - before, 15, f"{before:.1f} MB -> {after:.1f} MB")


if __name__ == "__main__":
    unittest.main()
