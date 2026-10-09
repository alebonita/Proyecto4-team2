# MOD-1b — Conjunto de calibración (150 imágenes de entrenamiento)

La variante optimizada (MOD-3) se calibra con estas 150 imágenes. Todas son del split de
**entrenamiento** del Proyecto 3; ninguna es de validación ni de test, que se reservan para
comparar la calidad del original y la variante.

| | |
|---|---|
| Lista de IDs | [`calibration-ids.csv`](calibration-ids.csv): `crop_id`, `clase`, `split`, `sha256` |
| Manifiesto de origen | [`../mod-01/manifest_v0.1.1.json`](../mod-01/manifest_v0.1.1.json), `manifest_hash` `sha256:178b28bd…cb2b2` |
| Selección | 75 `dog` + 75 `cat` del split `train` (de 221 y 248), semilla fija `20261009` |
| Script | [`scripts/p4/select_calibration.py`](../../scripts/p4/select_calibration.py) (solo biblioteca estándar) |
| Imágenes | **No están en git.** Se comparten con Hannah en `calibracion.zip` por Drive |
| `calibracion.zip` | 150 PNG en `calibracion/{dog,cat}/`, 17 342 549 bytes, **SHA-256 `fd53f5f7448e3db8fc8978927fa83375d4564a40528bf711b35c45f0ffd559d5`** |

## Qué se comprobó

El script se detiene con error si falla cualquiera de estas condiciones:

- `reports/crops.json` es exactamente el que cita el manifiesto (`provenance.crops_sha256`).
- Las 150 son del split `train`, 75 por clase.
- Ninguna comparte `crop_id`, imagen de origen (`source_image_id`) ni grupo de duplicados
  (`duplicate_group`) con validación o test. Así una foto casi idéntica a una de validación
  tampoco entra en la calibración.
- Cada imagen copiada tiene el mismo SHA-256 que registra `crops.json`.

Verificación independiente del script (2026-10-09): los 150 `crop_id` no aparecen en los 128
de [`../mod-01/validation_manifest.csv`](../mod-01/validation_manifest.csv) ni en los 71 de test
del manifiesto, y las 150 imágenes del zip coinciden en clase y SHA-256 con el CSV.

La selección es reproducible: con la misma semilla y el mismo manifiesto salen los mismos 150
IDs y el mismo zip byte a byte (fecha fija dentro del zip).

## Cómo se generó

Desde la raíz del repositorio, con lectura del bucket original del Proyecto 3 (cuenta
`280764207006`, perfil SSO `mlops-p2`; ver el README principal):

```bash
aws sso login --profile mlops-p2
dvc remote modify --local p2-origen profile mlops-p2
dvc pull -r p2-origen data/crops            # los 668 recortes del release v0.1.1
python3 scripts/p4/select_calibration.py    # -> calibracion/, calibracion.zip y este CSV
```

Salida:

```
Manifiesto: v0.1.1 (sha256:178b28bddb1bef5c05975fc7150710658627e31af08a1a12d94b98f9e99cb2b2)
Semilla: 20261009
  dog: 75
  cat: 75
Total: 150, todas del split train
Ningún recorte, imagen de origen ni grupo de duplicados de validación o test.
```

`calibracion/` y `calibracion.zip` están en `.gitignore`.

## Para quien recibe el zip

Comprueba que llegó completo antes de usarlo:

```bash
shasum -a 256 calibracion.zip   # fd53f5f7448e3db8fc8978927fa83375d4564a40528bf711b35c45f0ffd559d5
```

Úsalo solo para calibrar la cuantización. Para medir la calidad de la variante se usan los
128 recortes de validación de MOD-01, que no están en este conjunto.
