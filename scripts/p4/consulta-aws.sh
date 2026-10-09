#!/usr/bin/env bash
# AWS-2 — Demuestra, con comandos de SOLO LECTURA de la AWS CLI, que una captura del
# dispositivo edge (laptop) está realmente en AWS: su foto existe en el bucket del
# equipo y el registro se guardó con ella (metadatos del objeto en S3).
#
# Uso:
#   AWS_PROFILE=<tu-perfil> bash scripts/p4/consulta-aws.sh <capture_id>
#
# Variables opcionales:
#   EDGE_CAPTURES_BUCKET  bucket (por defecto mlops-p4-equipo-452857281704)
#   AWS_REGION            región (por defecto us-east-2)
#   PORTAL_URL            p. ej. http://18.216.36.30: muestra además el registro de
#                         MariaDB a través de la API del portal (sin la URL firmada)
#
# No escribe ni borra nada. No imprime credenciales ni URL firmadas.
#
# Permisos de lectura que necesita la identidad que lo ejecuta:
#   - s3:GetObject sobre edge-captures/*   (head-object: existencia y metadatos)
#   - s3:ListBucket sobre el bucket        (para que una foto inexistente dé 404 y no 403)
#   - s3:ListBucketVersions                (opcional: lista las versiones del objeto)
#   - sts:GetCallerIdentity                (no requiere permiso explícito)
#
# Política mínima equivalente:
#   {
#     "Version": "2012-10-17",
#     "Statement": [
#       {"Effect": "Allow", "Action": "s3:GetObject",
#        "Resource": "arn:aws:s3:::mlops-p4-equipo-452857281704/edge-captures/*"},
#       {"Effect": "Allow", "Action": ["s3:ListBucket", "s3:ListBucketVersions"],
#        "Resource": "arn:aws:s3:::mlops-p4-equipo-452857281704",
#        "Condition": {"StringLike": {"s3:prefix": "edge-captures/*"}}}
#     ]
#   }
# Las identidades del proyecto del equipo (aws login) ya tienen esos permisos.

set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Uso: AWS_PROFILE=<tu-perfil> bash $0 <capture_id>" >&2
  exit 2
fi

CAPTURE_ID="$1"
BUCKET="${EDGE_CAPTURES_BUCKET:-mlops-p4-equipo-452857281704}"
REGION="${AWS_REGION:-us-east-2}"

# Mismo formato que acepta el backend: evita keys raras y rutas inesperadas.
if ! [[ "$CAPTURE_ID" =~ ^[A-Za-z0-9_-]{1,64}$ ]]; then
  echo "capture_id inválido: solo letras, números, guion y guion bajo (máximo 64)." >&2
  exit 2
fi

KEY="edge-captures/${CAPTURE_ID}.jpg"

echo "== Quién consulta (sts get-caller-identity) =="
aws sts get-caller-identity --query Arn --output text

echo
echo "== La foto en S3: s3://${BUCKET}/${KEY} (s3api head-object) =="
if ! aws s3api head-object --bucket "$BUCKET" --key "$KEY" --region "$REGION" \
  --query '{Tamano_bytes:ContentLength,Tipo:ContentType,Modificada:LastModified,Version:VersionId,Cifrado:ServerSideEncryption}' \
  --output table; then
  echo "No se encontró la foto de ${CAPTURE_ID} en el bucket (o no hay permiso de lectura)." >&2
  exit 1
fi

echo
echo "== Registro guardado con la foto (metadatos del objeto) =="
aws s3api head-object --bucket "$BUCKET" --key "$KEY" --region "$REGION" \
  --query 'Metadata' --output table

echo
echo "== Versiones del objeto (1 = nunca se sobrescribió) =="
if ! aws s3api list-object-versions --bucket "$BUCKET" --prefix "$KEY" --region "$REGION" \
  --query 'Versions[].{Version:VersionId,Ultima:IsLatest,Fecha:LastModified,Bytes:Size}' \
  --output table; then
  echo "(sin permiso s3:ListBucketVersions: se omite)"
fi

if [ -n "${PORTAL_URL:-}" ]; then
  echo
  echo "== Registro en MariaDB (GET ${PORTAL_URL%/}/api/edge-captures/${CAPTURE_ID}) =="
  # Se quita image_url para no imprimir la URL firmada.
  curl -fsS "${PORTAL_URL%/}/api/edge-captures/${CAPTURE_ID}" |
    python3 -c 'import json, sys; d = json.load(sys.stdin); d.pop("image_url", None); print(json.dumps(d, indent=2, ensure_ascii=False))'
fi
