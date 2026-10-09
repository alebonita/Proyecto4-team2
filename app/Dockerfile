FROM public.ecr.aws/docker/library/python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv

WORKDIR /app

RUN useradd --system --no-create-home appuser

COPY pyproject.toml uv.lock ./
ENV UV_HTTP_TIMEOUT=180
ENV UV_CONCURRENT_DOWNLOADS=2
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev --no-build

COPY ingestion/ ./ingestion/
COPY analyzers/ ./analyzers/
COPY policies/ ./policies/
COPY splits/ ./splits/
COPY storage/ ./storage/
COPY presentation/ ./presentation/
COPY projections/ ./projections/
COPY copilot/ ./copilot/
COPY tracking/ ./tracking/
COPY training/ ./training/
COPY classification/ ./classification/
COPY crops/ ./crops/
COPY manifests/ ./manifests/

# El volumen nombrado reports_data (docker-compose.yml) se inicializa la
# primera vez con el contenido/dueño de este directorio si ya existe en la
# imagen — por eso se crea y se le da dueño ANTES de montar el volumen y de
# bajar a appuser, si no, la primera escritura de gate.py truena con
# PermissionError (el volumen nace root:root).
RUN mkdir -p /app/reports /home/appuser/.cache/torch/hub/checkpoints \
    && chown appuser:appuser /app/reports \
    && chown -R appuser:appuser /home/appuser

ENV PATH="/app/.venv/bin:$PATH"
ENV HOME=/home/appuser
ENV TORCH_HOME=/home/appuser/.cache/torch
USER appuser

CMD ["python", "-m", "presentation.main"]
