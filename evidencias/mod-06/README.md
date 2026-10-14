# MOD-6 — Modelos publicados en un Release de GitHub

**Criterio del ticket:** el Release existe, cada archivo se descarga y su SHA-256 coincide con el documentado.
**Evidencia:** el enlace al Release: **https://github.com/alebonita/Proyecto4-team2/releases/tag/modelos-v1.0.0**

Los pesos no están en git (`*.pt` y `*.onnx` están en `.gitignore`). Hasta ahora solo estaban en el bucket de S3 del equipo, que pide credenciales de AWS. El Release los deja descargables para cualquiera que vea el repo, sin AWS.

## Archivos

| Archivo | Qué es | Bytes | SHA-256 | Documentado en |
|---|---|---|---|---|
| `best.pt` | Original: ResNet18 perro/gato del Proyecto 3 (PyTorch) | 45 043 841 | `84d6c88b4bd84c3e6f0229dd23f7f188ff85622bbb39e5c3988a97598fa90d52` | `../mod-01/README.md`, `../mod-02/model/SHA256SUMS` |
| `dog-cat-resnet18-1.0.0-fp32.onnx` | Original exportado a ONNX, sin optimizar (MOD-2) | 44 961 942 | `6628f3cf24673a5045d51723b97dcfca85ebc1d511d49793bb6c0b0731c7035f` | `../mod-02/README.md` |
| **`dog-cat-resnet18-1.0.0-int8-rr.onnx`** | **Optimizado adoptado**: INT8 con `reduce_range` (MOD-3b); el que usa la laptop edge | 11 367 590 | `1d4a85fad5b2dcab28692bd5f81b5089092cf3a551b7862a63c544c94dcb5ea0` | `../mod-03/README.md`, `../mod-03/model/SHA256SUMS` |
| `dog-cat-resnet18-1.0.0-int8.onnx` | Primera variante INT8 (MOD-3); se conserva como registro | 11 367 590 | `9c28368acaf04e184e0712946c08e319d2b7ee2dc83d3f8ef0367d0b9c8935cd` | `../mod-03/README.md`, `../mod-03/model/SHA256SUMS` |
| `SHA256SUMS` | Los cuatro hashes de arriba | — | — | `SHA256SUMS` (esta carpeta) |

Los tres `.onnx` son los mismos que están en `s3://mlops-p4-equipo-452857281704/models/dog-cat-resnet18/1.0.0/onnx/`, y son los que se midieron en MOD-4, MOD-5 y EDG-5.

## Comprobación

`verify_release.py` descarga cada archivo desde el Release, calcula su SHA-256 y lo compara con `SHA256SUMS`. Solo usa la biblioteca estándar:

```bash
python verify_release.py      # -> verify_release_output.txt; código 1 si algo no coincide
```

Resultado guardado (se generó después de crear el Release): `verify_release_output.txt`.

A mano (Linux/macOS):

```bash
TAG=https://github.com/alebonita/Proyecto4-team2/releases/download/modelos-v1.0.0
for f in SHA256SUMS best.pt dog-cat-resnet18-1.0.0-fp32.onnx \
         dog-cat-resnet18-1.0.0-int8-rr.onnx dog-cat-resnet18-1.0.0-int8.onnx; do
  curl -fsSLO "$TAG/$f"
done
sha256sum -c SHA256SUMS        # macOS: shasum -a 256 -c SHA256SUMS
```

En Windows (PowerShell): `Get-FileHash .\dog-cat-resnet18-1.0.0-int8-rr.onnx -Algorithm SHA256`.
