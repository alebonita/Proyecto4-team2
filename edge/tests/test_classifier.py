"""EDG-2: el clasificador local da la clase esperada con imagenes de validacion conocidas.

Las imagenes son recortes de validacion del Proyecto 3 (evidencias/mod-01/validation/) y
pasan por el mismo camino que un cuadro de la camara: lectura BGR con OpenCV,
preprocess() e inferencia. La referencia es el modelo original (MOD-1).

Las probabilidades de un modelo INT8 cambian segun el CPU (en CPUs con AVX2 sin VNNI,
como el de la laptop edge, onnxruntime satura parte de los productos INT8). Por eso las
pruebas comparan clases y accuracy, no probabilidades exactas.

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
ORIGINAL = REPO / "evidencias/mod-01/predictions_original_validation.csv"
# Las mismas 5 de MOD-2 y MOD-3: dos seguras, una media, una dudosa y un error del modelo
# (img263-ann299 es un gato que el original predice como perro: se espera "dog").
KNOWN = ["img102-ann118", "img31-ann38", "img125-ann141", "img560-ann562", "img263-ann299"]
# Caida maxima de accuracy que permite la rubrica, en puntos porcentuales.
MAX_ACCURACY_DROP_PP = 2.0

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
        cls.original = read_rows(ORIGINAL)

    def classify_crop(self, crop_id: str):
        path = REPO / "evidencias/mod-01" / self.validation[crop_id]["path"]
        return classify_file(self.classifier, path)

    def test_known_validation_images(self):
        for crop_id in KNOWN:
            with self.subTest(crop_id=crop_id):
                pred = self.classify_crop(crop_id)
                self.assertEqual(pred.label, self.original[crop_id]["pred_original"])
                self.assertGreaterEqual(pred.confidence, 0.5)
                self.assertLessEqual(pred.confidence, 1.0)
                self.assertGreater(pred.latency_ms, 0)

    def test_classifies_without_network(self):
        refuse = mock.Mock(side_effect=AssertionError("la clasificacion intento usar la red"))
        with (
            mock.patch.object(socket.socket, "connect", refuse),
            mock.patch.object(socket, "create_connection", refuse),
            mock.patch.object(socket, "getaddrinfo", refuse),
        ):
            pred = self.classify_crop(KNOWN[0])
        self.assertEqual(pred.label, self.original[KNOWN[0]]["pred_original"])
        refuse.assert_not_called()

    def test_validation_accuracy_within_rubric_limit(self):
        correct = sum(
            self.classify_crop(crop_id).label == row["class"]
            for crop_id, row in self.validation.items()
        )
        original = sum(r["pred_original"] == r["true_class"] for r in self.original.values())
        drop_pp = 100 * (original - correct) / len(self.validation)
        self.assertLessEqual(
            drop_pp,
            MAX_ACCURACY_DROP_PP,
            f"{correct}/{len(self.validation)} correctas en este equipo contra {original} del "
            f"original: caida de {drop_pp:.2f} pp",
        )


if __name__ == "__main__":
    unittest.main()
