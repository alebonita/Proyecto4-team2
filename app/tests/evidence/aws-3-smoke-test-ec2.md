# Evidencia AWS-3: smoke test del portal en EC2 con el bucket del equipo

Ejecución: 2026-10-07 01:15 UTC, contra el portal desplegado en AWS
(`http://3.14.144.7`, instancia `i-02234c3f51db2446e`, `us-east-2`).

- **Código:** commit `2449a82` de `feat/aws-3-datos-bucket-equipo`.
  `tests/test_app10_portal_smoke.py` sin cambios.
- **Datos:** release `v0.1.1`, recortes, paquetes del modelo y snapshot de MLflow
  bajados con DVC (ver "Datos del proyecto" en el README).
- **Modelo:** `dog-cat-resnet18` 1.0.0 y 0.9.0 publicados en
  `s3://mlops-p4-equipo-452857281704/models/` con `ChecksumSHA256` y `VersionId`
  (`reports/models/s3_publications.json`).
- **Credenciales:** `ml-api` consulta S3 con el rol `portal-proyecto4-ec2` de la
  instancia (`AWS_EC2_METADATA_DISABLED=false` en `docker-compose.aws.yml`). Sin
  access keys y sin la cuenta anterior.

Antes de AWS-3, el mismo test fallaba en el paso 5 (Models,
`'unverifiable' == 'published'`) porque el modelo solo estaba publicado en el bucket
de la cuenta anterior y el servidor no tenía cómo consultarlo. Los pasos 6 y 7 no
llegaban a correr.

## Salida

```text
$ APP10_PORTAL_URL=http://3.14.144.7 uv run pytest tests/test_app10_portal_smoke.py -v
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-8.4.2, pluggy-1.6.0 -- /home/ubuntu/Proyecto4-team2/app/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/ubuntu/Proyecto4-team2/app
configfile: pyproject.toml
plugins: anyio-4.15.1
collecting ... collected 1 item

tests/test_app10_portal_smoke.py::test_full_flow_from_the_portal_with_traceable_ids PASSED [100%]

============================== 1 passed in 6.48s ===============================
```

## Cadena de IDs (`APP10_TRACE_OUT`)

| Paso | ID |
|---|---|
| Release P2 | `v0.1.1`; DVC `annotations` `c7cb86ae7ece94ef7b853620e464a4d7.dir`, `images` `951150dd4fb053f4665089fcb37a1c87.dir` |
| Manifiesto | `sha256:178b28bddb1bef5c05975fc7150710658627e31af08a1a12d94b98f9e99cb2b2` |
| Job de entrenamiento | `job-26300541296e4577b5e844b5465d2ed4` → run `4b3c86fbb40144608c6a9c061f06fcd8` |
| Candidato | run `bb448230424146349a969253d30db43b`, checkpoint sha256 `84d6c88b…fa90d52`, accuracy de test 0.9577 |
| Modelo en S3 | `dog-cat-resnet18` 1.0.0: `models/dog-cat-resnet18/1.0.0/{checkpoint/best.pt, model-card.md, package.json, dependencies.json}` |
| Inference | `inf-cc92cdd899084403`, recorte `img107-ann135` → `dog` (0.99995) |
| Cola de anotación | `image_id` 2. `created: false` porque la petición es idempotente y el registro lo creó la corrida anterior, que también pasó |

## Verificaciones relacionadas

- `GET /api/ml/models` por la IP pública: 1.0.0 y 0.9.0 con
  `publication.status = published`, bucket `mlops-p4-equipo-452857281704`,
  `us-east-2` y `servable = true`.
- Identidad vista desde `ml-api`:
  `arn:aws:sts::452857281704:assumed-role/portal-proyecto4-ec2/i-02234c3f51db2446e`.
- Permisos del rol probados desde `ml-api`: `PutObject` en `edge-captures/`, y
  `HeadObject` y `ListBucket` en `models/`, permitidos. `PutObject` en `models/`,
  `ListBucket` en `files/` y `DeleteObject` en `edge-captures/`: `AccessDenied`. El
  objeto de prueba se borró después, con todas sus versiones.
