"""EDG-4: envio a AWS, fallo visible y reintento con el mismo capture_id sin duplicados.

Usa un servidor local que imita POST /api/edge-captures (AWS-1/AWS-2): exige la clave en
X-Device-Key, guarda cada capture_id una sola vez (201 nuevo, 200 si ya existia) y
devuelve received_at e image_key. No toca el servidor real.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import email
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from unittest import mock

import cv2
import numpy as np

EDGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EDGE_DIR))

from capture import Uploader  # noqa: E402
from events import Event, EventStore, new_capture_id, now_iso  # noqa: E402
from retry import select_events  # noqa: E402
from sender import (  # noqa: E402
    SIMULATED_FAILURE_URL,
    UploadConfig,
    read_device_key,
    send_and_record,
)

KEY = "clave-de-prueba"
FIELDS = (
    "capture_id",
    "captured_at",
    "device_id",
    "model_version",
    "predicted_class",
    "confidence",
    "latency_ms",
    "crop",
)


class FakeEndpoint(BaseHTTPRequestHandler):
    """POST /api/edge-captures con las respuestas del contrato."""

    records: ClassVar[dict[str, dict]] = {}
    requests: ClassVar[list[dict]] = []
    delay_s = 0.0

    def log_message(self, *_args):  # sin ruido en la salida de las pruebas
        pass

    def reply(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        time.sleep(self.delay_s)
        if self.headers.get("X-Device-Key") != KEY:
            self.reply(401, {"error": "Clave de dispositivo ausente o incorrecta."})
            return
        body = self.rfile.read(int(self.headers["Content-Length"]))
        message = email.message_from_bytes(
            f"Content-Type: {self.headers['Content-Type']}\r\n\r\n".encode() + body
        )
        form, image = {}, None
        for part in message.get_payload():
            name = part.get_param("name", header="content-disposition")
            if name == "image":
                image = (part.get_content_type(), part.get_payload(decode=True))
            else:
                form[name] = part.get_payload(decode=True).decode()
        missing = [f for f in FIELDS if not form.get(f)]
        if missing or image is None or image[0] != "image/jpeg":
            self.reply(400, {"error": f"Faltan campos o imagen JPEG: {missing}"})
            return
        type(self).requests.append({"form": form, "image": image[1]})
        capture_id = form["capture_id"]
        created = capture_id not in self.records
        if created:
            self.records[capture_id] = {
                "capture_id": capture_id,
                "received_at": "2026-10-10T21:00:00.000Z",
                "image_key": f"edge-captures/{capture_id}.jpg",
            }
        self.reply(201 if created else 200, self.records[capture_id])


class SenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeEndpoint)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        port = cls.server.server_address[1]
        cls.cfg = UploadConfig(
            api_url=f"http://127.0.0.1:{port}/api/edge-captures",
            key_header="X-Device-Key",
            key_env="EDGE_DEVICE_KEY",
            key_file=None,
            timeout_s=5,
            auto_send=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        FakeEndpoint.records = {}
        FakeEndpoint.requests = []
        FakeEndpoint.delay_s = 0.0
        self.tmp = Path(tempfile.mkdtemp())
        self.store = EventStore(self.tmp / "events.db")
        self.event = self.make_event()

    def tearDown(self):
        self.store.close()

    def make_event(self) -> Event:
        capture_id = new_capture_id()
        photo = self.tmp / f"{capture_id}.jpg"
        cv2.imwrite(str(photo), np.full((480, 640, 3), 90, dtype=np.uint8))
        event = Event(
            capture_id=capture_id,
            captured_at=now_iso(),
            device_id="edge-prueba",
            model_version="modelo-de-prueba",
            predicted_class="dog",
            confidence=0.93,
            latency_ms=18.5,
            crop=(128, 48, 384, 384),
            photo_path=str(photo),
            photo_sha256="0" * 64,
        )
        self.store.add(event)
        return event

    def send(self, cfg=None, key=KEY):
        return send_and_record(self.store, self.event, cfg or self.cfg, key, self.tmp)

    def test_sends_photo_fields_and_key_and_marks_sent(self):
        result = self.send()

        self.assertTrue(result.ok)
        self.assertEqual(result.http_status, 201)
        [request] = FakeEndpoint.requests
        form = request["form"]
        self.assertEqual(form["capture_id"], self.event.capture_id)
        self.assertEqual(form["captured_at"], self.event.captured_at)
        self.assertEqual(form["predicted_class"], "dog")
        self.assertEqual(float(form["confidence"]), 0.93)
        self.assertEqual(float(form["latency_ms"]), 18.5)
        self.assertEqual(json.loads(form["crop"]), {"x": 128, "y": 48, "width": 384, "height": 384})
        self.assertEqual(request["image"], Path(self.event.photo_path).read_bytes())

        saved = self.store.get(self.event.capture_id)
        self.assertEqual(saved.status, "enviado")
        self.assertEqual(saved.received_at, "2026-10-10T21:00:00.000Z")
        self.assertEqual(saved.image_key, f"edge-captures/{self.event.capture_id}.jpg")
        self.assertEqual(saved.send_http_status, 201)
        self.assertGreater(saved.send_ms, 0)
        self.assertEqual(saved.latency_ms, 18.5)  # el envio no se suma a la inferencia

    def test_failed_send_then_retry_keeps_the_same_id_and_one_record(self):
        failed = self.send(replace(self.cfg, api_url=SIMULATED_FAILURE_URL))
        self.assertFalse(failed.ok)
        self.assertFalse(failed.permanent)
        self.assertIn("Sin conexion", failed.error)
        self.assertEqual(self.store.get(self.event.capture_id).status, "error")

        self.assertEqual(self.send().http_status, 201)  # el reintento llega
        self.assertEqual(self.send().http_status, 200)  # repetirlo no duplica
        self.assertEqual(list(FakeEndpoint.records), [self.event.capture_id])
        sent_ids = {r["form"]["capture_id"] for r in FakeEndpoint.requests}
        self.assertEqual(sent_ids, {self.event.capture_id})
        self.assertEqual(self.store.get(self.event.capture_id).status, "enviado")

    def test_wrong_key_is_rejected_and_not_retried_with_todos(self):
        result = self.send(key="otra-clave")
        self.assertEqual(result.http_status, 401)
        self.assertTrue(result.permanent)
        self.assertIn("Clave de dispositivo", result.error)

        args = mock.Mock(capture_id=None, incluir_rechazados=False)
        self.assertEqual(select_events(self.store, args), [])
        args.incluir_rechazados = True
        self.assertEqual(len(select_events(self.store, args)), 1)

    def test_timeout_is_an_error_and_the_event_can_be_retried(self):
        FakeEndpoint.delay_s = 1.0
        result = self.send(replace(self.cfg, timeout_s=0.3))
        self.assertFalse(result.ok)
        self.assertIn("Tiempo de espera", result.error)
        args = mock.Mock(capture_id=None, incluir_rechazados=False)
        self.assertEqual(len(select_events(self.store, args)), 1)

    def test_missing_key_fails_without_sending(self):
        result = self.send(key=None)
        self.assertFalse(result.ok)
        self.assertIn("Falta la clave", result.error)
        self.assertEqual(FakeEndpoint.requests, [])

    def test_key_comes_from_env_or_from_key_file(self):
        key_file = self.tmp / "device.env"
        key_file.write_text("# comentario\nEDGE_DEVICE_KEY=desde-archivo\n")
        cfg = replace(self.cfg, key_file=key_file)
        with mock.patch.dict(os.environ, {"EDGE_DEVICE_KEY": ""}):
            self.assertEqual(read_device_key(cfg), "desde-archivo")
        with mock.patch.dict(os.environ, {"EDGE_DEVICE_KEY": "desde-entorno"}):
            self.assertEqual(read_device_key(cfg), "desde-entorno")

    def test_background_uploader_sends_without_blocking_and_survives_failures(self):
        down = Uploader(replace(self.cfg, api_url=SIMULATED_FAILURE_URL), self.store.path, KEY)
        start = time.perf_counter()
        down.submit(self.event.capture_id)
        self.assertLess(time.perf_counter() - start, 0.05)  # submit no espera a la red
        down.close(timeout=5)
        self.assertEqual(self.store.get(self.event.capture_id).status, "error")
        self.assertTrue(down.last_failed)

        up = Uploader(self.cfg, self.store.path, KEY)
        up.submit(self.event.capture_id)
        up.close(timeout=5)
        self.assertEqual(self.store.get(self.event.capture_id).status, "enviado")
        self.assertIn("enviado", up.last_text)


if __name__ == "__main__":
    unittest.main()
