#!/usr/bin/env bash
# Reintenta un comando con espera creciente (10 s, 20 s, 30 s, 40 s).
#
# Para descargar imágenes en el CI: los runners de GitHub comparten IP y los registros
# responden a veces "toomanyrequests: Rate exceeded" (ECR Public limita peticiones por
# segundo). Es un rechazo temporal; esperar y volver a pedir lo resuelve.
#
# Uso: bash .github/scripts/retry.sh docker compose pull --ignore-buildable mariadb
set -u

attempts=5
for attempt in $(seq 1 "$attempts"); do
  if "$@"; then
    exit 0
  fi
  if [ "$attempt" -lt "$attempts" ]; then
    wait=$((attempt * 10))
    echo "::warning::Intento $attempt de $attempts falló: $*. Reintento en ${wait} s."
    sleep "$wait"
  fi
done
echo "::error::Falló después de $attempts intentos: $*"
exit 1
