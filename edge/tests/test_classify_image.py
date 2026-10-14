"""classify_image.py clasifica entradas conocidas con el modelo y el camino del programa.

python -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

EDGE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EDGE_DIR))

import classify_image  # noqa: E402
from capture import load_config  # noqa: E402

CONFIG_PATH = Path(os.environ.get("EDGE_CONFIG", EDGE_DIR / "config.yaml"))
MODEL = load_config(CONFIG_PATH)["model"]


@unittest.skipUnless(MODEL.path.is_file(), f"no esta el modelo {MODEL.path}")
class ClassifyImageTest(unittest.TestCase):
    def run_cli(self, *args: str) -> str:
        out = StringIO()
        with redirect_stdout(out):
            code = classify_image.main([*args, "--config", str(CONFIG_PATH)])
        self.assertEqual(code, 0)
        return out.getvalue()

    def test_known_crop_ids_and_model_hash(self):
        output = self.run_cli("img102-ann118", "img31-ann38")
        self.assertIn(MODEL.path.name, output)
        self.assertIn("Correctas: 2/2", output)

    def test_any_image_path_and_csv(self):
        image = EDGE_DIR.parent / "evidencias/mod-01/validation/cat/img31-ann38.png"
        target = Path(tempfile.mkdtemp()) / "salida.csv"
        self.run_cli(str(image), "--csv", str(target))
        [row] = list(csv.DictReader(target.open()))
        self.assertEqual(row["pred_edge"], "cat")
        self.assertEqual(row["clase_real"], "")  # una ruta suelta no trae etiqueta


if __name__ == "__main__":
    unittest.main()
