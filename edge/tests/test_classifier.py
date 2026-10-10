"""EDG-2: el clasificador local da la clase esperada con imagenes de validacion conocidas.

La referencia son las predicciones de MOD-4 (evidencias/mod-04/predictions_validation.csv),
obtenidas con el mismo modelo y onnxruntime en Python. Las imagenes son recortes de
validacion del Proyecto 3 (evidencias/mod-01/validation/), que pasan por el mismo camino
que un cuadro de la camara: lectura BGR con OpenCV, preprocess() e inferencia.

    python -m unittest discover -s tests -v

Las pruebas que necesitan el modelo se saltan si el .onnx no esta en model.path. Para
probar otro archivo: EDGE_CONFIG=/ruta/a/otro-config.yaml.
"""

from __future__ import annotations

import csv
import os
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

EDGE_DIR = Path(__file__).resolve().parents[1]
REPO = EDGE_DIR.parent
sys.path.insert(0, str(EDGE_DIR))

from capture import load_config  # noqa: E402
from classifier import Classifier, center_crop, preprocess  # noqa: E402

VALIDATION = REPO / "evidencias/mod-01/validation_manifest.csv"
REFERENCE = REPO / "evidencias/mod-04/predictions_validation.csv"
# SHA-256 de la variante INT8 de MOD-3, con la que MOD-4 calculo las probabilidades.
INT8_SHA256 = "9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd"
# Las mismas 5 de MOD-2 y MOD-3: dos seguras, una media, una dudosa y un error del modelo.
KNOWN = ["img102-ann118", "img31-ann38", "img125-ann141", "img560-ann562", "img263-ann299"]
# INT8 puede variar en los ultimos decimales segun el CPU (evidencias/mod-04/README.md).
PROB_TOLERANCE = 0.02

CONFIG = load_config(Path(os.environ.get("EDGE_CONFIG", EDGE_DIR / "config.yaml")))
MODEL = CONFIG["model"]


def read_rows(path: Path) -> dict[str, dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["crop_id"]: row for row in csv.DictReader(handle)}


def classify_file(classifier: Classifier, path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)  # BGR, como un cuadro de la camara
    height, width = image.shape[:2]
    return classifier.classify(image, (0, 0, width, height))  # el recorte es la imagen entera


class PreprocessTest(unittest.TestCase):
    def test_converts_bgr_to_rgb_and_normalizes(self):
        blue_bgr = np.zeros((10, 10, 3), dtype=np.uint8)
        blue_bgr[..., 0] = 255  # azul puro en BGR
        tensor = preprocess(blue_bgr, (0, 0, 10, 10), MODEL)
        size = MODEL.input_size
        self.assertEqual(tensor.shape, (1, 3, size, size))
        self.assertEqual(tensor.dtype, np.float32)
        red, blue = tensor[0, 0, 0, 0], tensor[0, 2, 0, 0]  # canal 0 = R, canal 2 = B
        self.assertAlmostEqual(float(red), (0.0 - MODEL.mean[0]) / MODEL.std[0], places=5)
        self.assertAlmostEqual(float(blue), (1.0 - MODEL.mean[2]) / MODEL.std[2], places=5)

    def test_center_crop_fits_the_frame(self):
        self.assertEqual(center_crop(640, 480, 0.8), (128, 48, 384, 384))
        x, y, w, h = center_crop(1280, 720, 1.0)
        self.assertTrue(x >= 0 and y >= 0 and x + w <= 1280 and y + h <= 720)


@unittest.skipUnless(MODEL.path.is_file(), f"no esta el modelo {MODEL.path}")
class ClassifierTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier = Classifier(MODEL)
        cls.validation = read_rows(VALIDATION)
        cls.reference = read_rows(REFERENCE)
        cls.is_int8 = cls.classifier.sha256 == INT8_SHA256

    def expected(self, crop_id: str) -> str:
        # Con la variante INT8, la clase de MOD-4; con otro ONNX (p. ej. el fp32 de MOD-2,
        # que coincide 128/128 con el original), la del original.
        column = "pred_optimized" if self.is_int8 else "pred_original"
        return self.reference[crop_id][column]

    def test_known_validation_images(self):
        for crop_id in KNOWN:
            with self.subTest(crop_id=crop_id):
                row = self.validation[crop_id]
                pred = classify_file(self.classifier, REPO / "evidencias/mod-01" / row["path"])
                self.assertEqual(pred.label, self.expected(crop_id))
                self.assertGreaterEqual(pred.confidence, 0.5)
                self.assertLessEqual(pred.confidence, 1.0)
                self.assertGreater(pred.latency_ms, 0)
                if self.is_int8:
                    ref = float(self.reference[crop_id][f"prob_optimized_{pred.label}"])
                    self.assertAlmostEqual(pred.confidence, ref, delta=PROB_TOLERANCE)

    def test_classifies_without_network(self):
        row = self.validation[KNOWN[0]]
        refuse = mock.Mock(side_effect=AssertionError("la clasificacion intento usar la red"))
        with (
            mock.patch.object(socket.socket, "connect", refuse),
            mock.patch.object(socket, "create_connection", refuse),
            mock.patch.object(socket, "getaddrinfo", refuse),
        ):
            pred = classify_file(self.classifier, REPO / "evidencias/mod-01" / row["path"])
        self.assertEqual(pred.label, self.expected(KNOWN[0]))
        refuse.assert_not_called()

    def test_all_validation_images_match_reference(self):
        mismatches = []
        for crop_id, row in self.validation.items():
            pred = classify_file(self.classifier, REPO / "evidencias/mod-01" / row["path"])
            if pred.label != self.expected(crop_id):
                mismatches.append(crop_id)
        self.assertEqual(mismatches, [], f"{len(mismatches)}/{len(self.validation)} distintos")


if __name__ == "__main__":
    unittest.main()
