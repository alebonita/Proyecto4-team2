"""MOD-1 — carga el modelo final del Proyecto 3 y predice, sin depender de su código.

Requiere: torch, torchvision y pillow (probado con torch 2.14.0 / torchvision 0.29.0).

    python predict.py                      # verifica SHA-256 y predice una imagen de validación
    python predict.py ruta/a/imagen.png    # predice una imagen cualquiera
    python predict.py --all                # evalúa los 128 recortes de validation_manifest.csv
"""

import csv
import hashlib
import sys
from pathlib import Path

import torch
from PIL import Image
from torch import nn
from torchvision.models import resnet18
from torchvision.transforms import v2

HERE = Path(__file__).resolve().parent
WEIGHTS = HERE / "model" / "best.pt"
EXPECTED_SHA256 = "84d6c88b4bd84c3e6f0229dd23f7f188ff85622bbb39e5c3988a97598fa90d52"

# Índice de salida del modelo -> clase (class_map del checkpoint: dog=0, cat=1).
CLASSES = ["dog", "cat"]
IMAGE_SIZE = 128
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)

PREPROCESS = v2.Compose(
    [
        v2.ToImage(),  # PIL RGB, HWC uint8 -> tensor CHW uint8
        v2.Resize((IMAGE_SIZE, IMAGE_SIZE), antialias=True),  # cuadrado, sin conservar aspecto
        v2.ToDtype(torch.float32, scale=True),  # [0, 255] -> [0, 1]
        v2.Normalize(mean=MEAN, std=STD),
    ]
)


class DogCatResNet18(nn.Module):
    """ResNet18 sin su `fc` (512 características) + cabeza Linear-ReLU-Dropout-Linear."""

    def __init__(self, hidden: int = 128, dropout: float = 0.2):
        super().__init__()
        self.backbone = resnet18(weights=None)
        self.backbone.fc = nn.Identity()
        self.head = nn.Sequential(
            nn.Linear(512, hidden), nn.ReLU(), nn.Dropout(dropout), nn.Linear(hidden, len(CLASSES))
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.backbone(x))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_model() -> nn.Module:
    actual = sha256(WEIGHTS)
    if actual != EXPECTED_SHA256:
        raise SystemExit(f"SHA-256 distinto: {actual} (esperado {EXPECTED_SHA256})")
    payload = torch.load(WEIGHTS, map_location="cpu", weights_only=True)
    assert payload["class_map"] == {name: i for i, name in enumerate(CLASSES)}, payload["class_map"]
    assert payload["preprocessing"]["image_size"] == IMAGE_SIZE, payload["preprocessing"]
    assert payload["config"]["hidden_layers"] == [128], payload["config"]
    model = DogCatResNet18(payload["config"]["hidden_layers"][0], payload["config"]["dropout"])
    model.load_state_dict(payload["state_dict"])  # strict: falla si alguna capa no coincide
    return model.eval()


@torch.no_grad()
def predict(model: nn.Module, path: Path) -> tuple[str, list[float]]:
    image = Image.open(path).convert("RGB")
    probs = torch.softmax(model(PREPROCESS(image).unsqueeze(0)), dim=1)[0].tolist()
    return CLASSES[max(range(len(CLASSES)), key=probs.__getitem__)], probs


def main(args: list[str]) -> None:
    model = load_model()
    print(f"best.pt SHA-256 OK: {EXPECTED_SHA256}")
    with open(HERE / "validation_manifest.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    if args == ["--all"]:
        results = []
        for row in rows:
            label, probs = predict(model, HERE / row["path"])
            results.append({"crop_id": row["crop_id"], "true_class": row["class"],
                            "pred_original": label,
                            **{f"prob_{c}": f"{p:.6f}" for c, p in zip(CLASSES, probs)}})
            if label != row["class"]:
                print(f"  error: {row['crop_id']} real={row['class']} predicho={label}")
        with open(HERE / "predictions_original_validation.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys(), lineterminator="\n")
            writer.writeheader()
            writer.writerows(results)
        correct = sum(r["true_class"] == r["pred_original"] for r in results)
        print(f"validation: {correct}/{len(rows)} correctas, accuracy={correct / len(rows):.4f}")
        f1s = []
        for c in CLASSES:
            tp = sum(r["true_class"] == c and r["pred_original"] == c for r in results)
            pred = sum(r["pred_original"] == c for r in results)
            support = sum(r["true_class"] == c for r in results)
            precision, recall = tp / pred if pred else 0.0, tp / support if support else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            f1s.append(f1)
            print(f"  {c}: precision={precision:.4f} recall={recall:.4f} f1={f1:.4f} soporte={support}")
        print(f"F1 macro={sum(f1s) / len(f1s):.4f}  -> predictions_original_validation.csv")
        return
    path = Path(args[0]) if args else HERE / rows[0]["path"]
    expected = next((r["class"] for r in rows if HERE / r["path"] == path.resolve()), None)
    label, probs = predict(model, path)
    print(f"{path.name}: {label}  " + "  ".join(f"{c}={p:.4f}" for c, p in zip(CLASSES, probs)))
    if expected:
        print(f"clase real: {expected} -> {'OK' if label == expected else 'ERROR'}")


if __name__ == "__main__":
    main(sys.argv[1:])
