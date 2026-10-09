# OPS-03: servidor MLflow persistente. Runs en MariaDB y artefactos en MinIO
# (ver entrypoint.py); el contenedor no guarda estado propio.
FROM public.ecr.aws/docker/library/python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv

WORKDIR /srv/mlflow

RUN useradd --system --no-create-home mlflow

COPY requirements.txt ./
ENV UV_HTTP_TIMEOUT=180
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --no-build -r requirements.txt

COPY entrypoint.py ./

USER mlflow
EXPOSE 5000

CMD ["python", "/srv/mlflow/entrypoint.py"]
